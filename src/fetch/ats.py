"""ATS classification + lightweight probing.

Given a company name, work out which applicant-tracking system (ATS) hosts its
public job board by trying candidate URL "tokens" against each ATS's public API.
A hit also confirms the board works and roughly how many jobs it lists.

The functions here are pure (HTTP via an injectable session) and unit-tested
with mocked HTTP — no database access.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass

import requests

from normalise.text import norm, strip_legal_suffixes

# Tier-A ATS: clean public JSON feeds.
ATS_GREENHOUSE = "greenhouse"
ATS_LEVER = "lever"
ATS_ASHBY = "ashby"
ATS_WORKABLE = "workable"
# Workday (Phase 6): board slug can't be guessed by probe — onboarded from its
# careers URL, which is stored in ats_token. Fetched by src/fetch/workday.py.
ATS_WORKDAY = "workday"
ATS_UNKNOWN = "unknown"

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; goal-a-engine/0.1)"}
TIMEOUT = 8

# Transient statuses worth one more try — otherwise a rate-limited probe would
# silently classify a real board as 'unknown'.
RETRY_STATUSES = {429, 500, 502, 503, 504}
MAX_TRIES = 3
_sleep = time.sleep  # module-level so tests can stub the backoff


@dataclass
class Classification:
    company_name: str
    ats_type: str               # one of the ATS_* constants
    ats_token: str | None       # board slug, or None when unknown
    careers_url: str | None
    n_jobs: int | None          # jobs seen on the board during probe (pre-UK-filter)


def candidate_tokens(company_name: str) -> list[str]:
    """Plausible board slugs for a company name, most-likely first.

    Register names legally end in Ltd/Limited/PLC while board slugs use the
    bare brand ('Synthesia Limited' -> 'synthesia'), so legal-suffix-stripped
    variants are tried after the literal ones (added for the Phase 7.5 census,
    which probes companies under their register names).
    """
    name = company_name.strip().lower()
    core = strip_legal_suffixes(norm(company_name))
    tokens: list[str] = []
    for source in (name, core):
        if not source:
            continue
        base = re.sub(r"[^a-z0-9]+", "", source)                # "thought machine" -> "thoughtmachine"
        hyphen = re.sub(r"[^a-z0-9]+", "-", source).strip("-")  # -> "thought-machine"
        stripped = re.sub(r"(ai|labs|hq)$", "", base)           # "stabilityai" -> "stability"
        for tok in (base, hyphen, stripped):
            if tok and tok not in tokens:
                tokens.append(tok)
    return tokens


def _get_json(url: str, session: requests.Session, method: str = "GET", json_body=None):
    """Return parsed JSON on HTTP 200, else None. Transient failures retried."""
    for attempt in range(MAX_TRIES):
        try:
            if method == "POST":
                resp = session.post(url, headers=HEADERS, timeout=TIMEOUT, json=json_body or {})
            else:
                resp = session.get(url, headers=HEADERS, timeout=TIMEOUT)
        except requests.RequestException:
            if attempt == MAX_TRIES - 1:
                return None
            _sleep(2 ** attempt)
            continue
        if resp.status_code in RETRY_STATUSES and attempt < MAX_TRIES - 1:
            _sleep(2 ** attempt)
            continue
        if resp.status_code == 200:
            try:
                return resp.json()
            except ValueError:
                return None
        return None
    return None


def probe_greenhouse(token: str, session: requests.Session) -> Classification | None:
    data = _get_json(f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs", session)
    if isinstance(data, dict) and "jobs" in data:
        return Classification("", ATS_GREENHOUSE, token,
                              f"https://boards.greenhouse.io/{token}", len(data["jobs"]))
    return None


def probe_lever(token: str, session: requests.Session) -> Classification | None:
    data = _get_json(f"https://api.lever.co/v0/postings/{token}?mode=json", session)
    if isinstance(data, list):
        return Classification("", ATS_LEVER, token,
                              f"https://jobs.lever.co/{token}", len(data))
    return None


def probe_ashby(token: str, session: requests.Session) -> Classification | None:
    data = _get_json(f"https://api.ashbyhq.com/posting-api/job-board/{token}", session)
    if isinstance(data, dict) and "jobs" in data:
        return Classification("", ATS_ASHBY, token,
                              f"https://jobs.ashbyhq.com/{token}", len(data["jobs"]))
    return None


def probe_workable(token: str, session: requests.Session) -> Classification | None:
    data = _get_json(f"https://apply.workable.com/api/v3/accounts/{token}/jobs",
                     session, method="POST", json_body={})
    if isinstance(data, dict) and "results" in data:
        return Classification("", ATS_WORKABLE, token,
                              f"https://apply.workable.com/{token}/", len(data["results"]))
    return None


PROBES = (probe_greenhouse, probe_lever, probe_ashby, probe_workable)


def classify_company(company_name: str, session: requests.Session | None = None) -> Classification:
    """Try each candidate token against each ATS; first hit wins. Else 'unknown'."""
    session = session or requests.Session()
    for token in candidate_tokens(company_name):
        for probe in PROBES:
            result = probe(token, session)
            # Require a non-empty board: a 0-job hit is almost always a token
            # collision or a parked account (e.g. someone else's "wise" board).
            if result is not None and result.n_jobs:
                result.company_name = company_name
                return result
    return Classification(company_name, ATS_UNKNOWN, None, None, None)
