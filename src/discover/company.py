"""Interactive discovery: name a company, or hand back a board URL.

``discover_company`` probes a named company with the existing ATS classifier. A
board hit joins the fetch list (with a sponsor-register verdict attached); a miss
returns the probe evidence so Claude can hunt the careers URL and pass it to
``classify_from_url``, which verifies that board and onboards it.

Logic only — the discovery MCP tools are thin wrappers over these and handle the
audit. Nothing here imports the MCP skin (the daily-loop-independence invariant).
"""
from __future__ import annotations

import re

import requests

from discover.onboarding import (
    REGISTER_SPONSOR_CONFIDENCE,
    UNVERIFIED_SPONSOR_CONFIDENCE,
    insert_classified_company,
)
from discover.register import load_known_sponsors, lookup_register_verdict
from fetch.ats import (
    ATS_ASHBY,
    ATS_GREENHOUSE,
    ATS_LEVER,
    ATS_UNKNOWN,
    ATS_WORKABLE,
    candidate_tokens,
    classify_company,
    probe_ashby,
    probe_greenhouse,
    probe_lever,
    probe_workable,
)
from normalise.text import norm

# A board slug in a known ATS URL. Case-insensitive; captures the first path
# segment after the host (Greenhouse also allows the /v1/boards/ API form).
_ATS_URL_PATTERNS = [
    (ATS_GREENHOUSE,
     re.compile(r"(?:boards|boards-api|job-boards)\.greenhouse\.io/(?:v1/boards/)?([a-z0-9\-]+)", re.I)),
    (ATS_LEVER, re.compile(r"jobs\.lever\.co/([a-z0-9\-]+)", re.I)),
    (ATS_ASHBY, re.compile(r"jobs\.ashbyhq\.com/([a-z0-9\-]+)", re.I)),
    (ATS_WORKABLE, re.compile(r"apply\.workable\.com/([a-z0-9\-]+)", re.I)),
]

_PROBE_BY_TYPE = {
    ATS_GREENHOUSE: probe_greenhouse,
    ATS_LEVER: probe_lever,
    ATS_ASHBY: probe_ashby,
    ATS_WORKABLE: probe_workable,
}


def parse_ats_url(url: str | None) -> tuple[str, str] | None:
    """Derive ``(ats_type, token)`` from a known ATS board URL, else None."""
    if not url:
        return None
    for ats_type, rx in _ATS_URL_PATTERNS:
        m = rx.search(url)
        if m:
            return ats_type, m.group(1)
    return None


def _probe_specific(ats_type: str, token: str, session=None):
    """Verify one specific (ats_type, token) board; returns a Classification or None."""
    probe = _PROBE_BY_TYPE.get(ats_type)
    if not probe:
        return None
    return probe(token, session or requests.Session())


def probe_token(ats_type: str, token: str, session=None):
    """Public seam for verifying a known/harvested board address with ONE call.

    Used by the census probe to try token-harvest hints before slug guessing.
    Returns the probe's Classification on a live board, else None."""
    return _probe_specific(ats_type, token, session)


def _verdict_summary(verdict: dict | None) -> dict:
    if verdict:
        return {"in_register": True, "sponsor_id": verdict["sponsor_id"],
                "rating": verdict["rating"], "route": verdict["route"]}
    return {"in_register": False}


def _onboard(cur, owner_id, company_name, classification, verdict) -> dict:
    """Insert a verified company with its register verdict; return a result dict."""
    company_id = insert_classified_company(
        cur, owner_id, company_name=company_name,
        sponsor_id=verdict["sponsor_id"] if verdict else None,
        city=verdict["town_city"] if verdict else None,
        classification=classification,
        sponsor_confidence=(REGISTER_SPONSOR_CONFIDENCE if verdict
                            else UNVERIFIED_SPONSOR_CONFIDENCE))
    return {"company_name": company_name, "outcome": "onboarded",
            "company_id": company_id, "ats_type": classification.ats_type,
            "ats_token": classification.ats_token, "careers_url": classification.careers_url,
            "n_jobs": classification.n_jobs, "sponsor_verdict": _verdict_summary(verdict)}


def discover_company(cur, owner_id, company_name: str, session=None) -> dict:
    """Probe a named company: onboard it, or return evidence for Claude to chase.

    Never re-adds a company already targeted for the owner. Attaches a
    sponsor-register verdict either way, so nothing is onboarded blind.
    """
    name_norm = norm(company_name)
    _, known_norms = load_known_sponsors(cur, owner_id)
    if name_norm in known_norms:
        return {"company_name": company_name, "outcome": "already_targeted"}

    verdict = lookup_register_verdict(cur, name_norm)
    c = classify_company(company_name, session)
    if c.ats_type != ATS_UNKNOWN and c.ats_token:
        return _onboard(cur, owner_id, company_name, c, verdict)

    return {
        "company_name": company_name, "outcome": "no_board",
        "evidence": {
            "company_name": company_name,
            "org_name_norm": name_norm,
            "tokens_tried": candidate_tokens(company_name),
            "probe": "no ATS board matched (greenhouse/lever/ashby/workable)",
        },
        "sponsor_verdict": _verdict_summary(verdict),
        "next": "find the ATS board URL and call classify_from_url",
    }


def classify_from_url(cur, owner_id, company_name: str, careers_url: str,
                      session=None) -> dict:
    """Onboard a company from an ATS board URL Claude found. Verifies before writing."""
    parsed = parse_ats_url(careers_url)
    if not parsed:
        return {"company_name": company_name, "careers_url": careers_url,
                "outcome": "unrecognized_url",
                "reason": "not a known ATS board URL (greenhouse/lever/ashby/workable)",
                "next": "provide the direct ATS board URL"}
    ats_type, token = parsed

    c = _probe_specific(ats_type, token, session)
    if c is None or not c.n_jobs:
        return {"company_name": company_name, "careers_url": careers_url,
                "outcome": "unverified",
                "reason": f"{ats_type} board '{token}' returned no jobs or did not respond"}
    c.company_name = company_name

    name_norm = norm(company_name)
    _, known_norms = load_known_sponsors(cur, owner_id)
    if name_norm in known_norms:
        return {"company_name": company_name, "outcome": "already_targeted"}

    verdict = lookup_register_verdict(cur, name_norm)
    return _onboard(cur, owner_id, company_name, c, verdict)
