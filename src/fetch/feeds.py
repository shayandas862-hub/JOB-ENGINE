"""Tier-A ATS fetchers (Greenhouse, Lever, Ashby, Workable).

Pull jobs, extract title/location/url/JD text, filter to the UK, and build a
stable dedupe key. Parsers take an injectable session and are unit-tested with
mocked HTTP fixtures.
"""
from __future__ import annotations

import hashlib
import html
import re
import time
from dataclasses import dataclass

import requests

from fetch.ats import (
    ATS_ASHBY,
    ATS_GREENHOUSE,
    ATS_LEVER,
    ATS_WORKABLE,
    ATS_WORKDAY,
    HEADERS,
)
from normalise.text import norm

# Feeds can return large payloads; allow more time than the quick classifier probes.
FEED_TIMEOUT = 30

# Transient statuses worth retrying; a 404 is a real answer, not a blip.
RETRY_STATUSES = {429, 500, 502, 503, 504}
MAX_TRIES = 3
_sleep = time.sleep  # module-level so tests can stub the backoff


@dataclass
class Job:
    company_name: str
    source: str            # ats_type the job came from
    external_id: str
    title: str
    location: str
    url: str
    jd_text: str
    salary_text: str | None


# Unambiguous UK markers (word-bounded — avoids matching "uk" inside e.g. "Tukwila").
UK_STRONG_RE = re.compile(
    r"\b(united kingdom|u\.?k\.?|gbr?|england|scotland|wales|northern ireland)\b",
    re.I,
)

# UK city names — ambiguous on their own: many exist abroad ("Cambridge, MA",
# "London, Ontario"). They count only when nothing marks the location as foreign.
UK_CITY_RE = re.compile(
    r"\b(london|manchester|edinburgh|cambridge|oxford|bristol|leeds|glasgow|"
    r"birmingham|cardiff|belfast|newcastle|sheffield|nottingham|brighton|reading)\b",
    re.I,
)

NON_UK_RE = re.compile(
    r"\b(united states|u\.?s\.?a\.?|america|canada|ontario|australia|new zealand|"
    r"south africa)\b",
    re.I,
)

# "City, ST" — a US-state / Canadian-province / Australian-state code after a
# comma. Case-sensitive and comma-anchored so "London or Manchester" can never
# read as Oregon.
FOREIGN_REGION_CODE_RE = re.compile(
    r",\s*(A[LKZRB]|C[AOT]|D[EC]|FL|GA|HI|I[DLNA]|K[SY]|LA|M[EDAINSOTB]|"
    r"N[EVHJMYCDBLTSU]|O[HKRN]|P[AE]|QC|RI|S[CDK]|T[NXA]S?|UT|V[TAIC]{1,2}|"
    r"W[AVIY]|YT|NSW|QLD|ACT)\b"
)


def is_uk(location) -> bool:
    """True if a location (string or dict) looks UK-based.

    Strong markers (UK/GB/England/...) decide alone; bare UK city names count
    only when no foreign country, state, or province appears alongside them.
    """
    if not location:
        return False
    if isinstance(location, dict):
        cc = str(location.get("countryCode") or location.get("country") or "")
        text = " ".join(str(v) for v in location.values() if v)
    else:
        cc = ""
        text = str(location)
    code = cc.strip().upper()
    if code in ("GB", "GBR", "UK"):
        return True
    # A 2/3-letter country code that isn't UK is authoritative (full country
    # names like "United Kingdom" fall through to the text check instead).
    if code and len(code) <= 3 and code.isalpha():
        return False
    if UK_STRONG_RE.search(text):
        return True
    if UK_CITY_RE.search(text):
        return not (NON_UK_RE.search(text) or FOREIGN_REGION_CODE_RE.search(text))
    return False


def _strip_html(raw: str | None) -> str:
    if not raw:
        return ""
    text = re.sub(r"<[^>]+>", " ", raw)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def dedupe_key(company_name: str, title: str, url: str | None) -> str:
    # Title normalisation MUST be the shared norm() — see normalise/text.py.
    base = f"{company_name.lower()}|{norm(title)}|{(url or '').lower()}"
    return hashlib.sha1(base.encode("utf-8")).hexdigest()


def _get(url, session, method="GET", json_body=None):
    """GET/POST with exponential-backoff retry on transient failures."""
    for attempt in range(MAX_TRIES):
        try:
            if method == "POST":
                resp = session.post(url, headers=HEADERS, timeout=FEED_TIMEOUT,
                                    json=json_body or {})
            else:
                resp = session.get(url, headers=HEADERS, timeout=FEED_TIMEOUT)
        except (requests.ConnectionError, requests.Timeout):
            if attempt == MAX_TRIES - 1:
                raise
            _sleep(2 ** attempt)
            continue
        if resp.status_code in RETRY_STATUSES and attempt < MAX_TRIES - 1:
            _sleep(2 ** attempt)
            continue
        resp.raise_for_status()
        return resp.json()


def fetch_greenhouse(company_name, token, session) -> list[Job]:
    data = _get(f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true", session)
    jobs = []
    for j in data.get("jobs", []):
        loc = (j.get("location") or {}).get("name", "") or ""
        jd = _strip_html(j.get("content"))
        jobs.append(Job(company_name, ATS_GREENHOUSE, str(j.get("id")),
                        j.get("title", ""), loc, j.get("absolute_url", ""),
                        jd, None))  # salary_text filled by the reader (GA-007)
    return jobs


def fetch_lever(company_name, token, session) -> list[Job]:
    data = _get(f"https://api.lever.co/v0/postings/{token}?mode=json", session)
    jobs = []
    for j in data:
        loc = (j.get("categories") or {}).get("location", "") or ""
        jd = _strip_html(j.get("description") or j.get("descriptionPlain"))
        jobs.append(Job(company_name, ATS_LEVER, str(j.get("id")),
                        j.get("text", ""), loc, j.get("hostedUrl", ""),
                        jd, None))  # salary_text filled by the reader (GA-007)
    return jobs


def fetch_ashby(company_name, token, session) -> list[Job]:
    data = _get(f"https://api.ashbyhq.com/posting-api/job-board/{token}?includeCompensation=true", session)
    jobs = []
    for j in data.get("jobs", []):
        loc = j.get("location", "") or ""
        jd = _strip_html(j.get("descriptionHtml") or j.get("descriptionPlain"))
        jobs.append(Job(company_name, ATS_ASHBY, str(j.get("id") or j.get("jobUrl")),
                        j.get("title", ""), loc, j.get("jobUrl", ""),
                        jd, None))  # salary_text filled by the reader (GA-007)
    return jobs


def fetch_workable(company_name, token, session) -> list[Job]:
    data = _get(f"https://apply.workable.com/api/v3/accounts/{token}/jobs",
                session, method="POST", json_body={})
    jobs = []
    for j in data.get("results", []):
        loc = j.get("location") or {}
        parts = [loc.get("city"), loc.get("region"), loc.get("country")]
        loc_str = ", ".join(p for p in parts if p)
        if loc.get("countryCode"):
            loc_str = f"{loc_str} [{loc['countryCode']}]" if loc_str else loc["countryCode"]
        # Workable's list endpoint omits the JD body; fetched per-job later (Phase 3).
        jobs.append(Job(company_name, ATS_WORKABLE, str(j.get("shortcode") or j.get("id")),
                        j.get("title", ""), loc_str, j.get("url", ""), "", None))
    return jobs


FETCHERS = {
    ATS_GREENHOUSE: fetch_greenhouse,
    ATS_LEVER: fetch_lever,
    ATS_ASHBY: fetch_ashby,
    ATS_WORKABLE: fetch_workable,
}


def fetch_company(company_name, ats_type, token, session=None) -> list[Job]:
    """Dispatch to the right fetcher by ats_type. Empty list if unsupported.

    Workday boards can't be slug-probed, so ``token`` carries the careers URL and
    fetch_workday parses it. Imported lazily — workday.py imports from this
    module, so a top-level import would cycle."""
    session = session or requests.Session()
    if ats_type == ATS_WORKDAY:
        from fetch.workday import fetch_workday
        return fetch_workday(company_name, token, session) if token else []
    fetcher = FETCHERS.get(ats_type)
    if not fetcher or not token:
        return []
    return fetcher(company_name, token, session)
