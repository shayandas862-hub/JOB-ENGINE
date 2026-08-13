"""The UK registry plug-in: Companies House search → match → profile → card.

This module is what makes the census country-portable: the sweep imports it as
``registry`` and only ever calls ``enrich_org``. Another country later means
another module with the same one function — nothing else changes shape.

Contract confirmed 2026-07-11 against the live developer docs
(developer-specs.company-information.service.gov.uk): GET /search/companies
(q, items_per_page) and GET /company/{number}; auth is HTTP Basic with the API
key as the username and a blank password (the Reed shape); the public-data
rate limit is 600 requests per five minutes — PAUSE keeps us safely under it.

Matching mirrors sponsor_match: exact norm, then unique legal-suffix-stripped,
then single-ACTIVE disambiguation (dissolved namesakes are endemic in the
registry). Anything still plural is recorded 'ambiguous' — never guessed.
"""
from __future__ import annotations

import time

import requests

from budget.gate import charge_for
from discover.census_store import record_registry_result
from normalise.text import norm, strip_legal_suffixes as _strip_legal

CH_BASE = "https://api.company-information.service.gov.uk"
TIMEOUT = 15
PAUSE = 0.6                    # 600 req/5 min = 2/s ceiling; 0.6 s stays under it
SEARCH_RESULTS = 5
RETRY_STATUSES = {429, 500, 502, 503, 504}
MAX_TRIES = 3
_sleep = time.sleep            # swappable: tests stub pacing AND backoff


def _get_json(url, api_key, session, *, params=None):
    """GET JSON with transient-retry; None on any failure. Paces every call.

    The ONE place the registry is called, and so where its budget is enforced
    (task 5) — charged per attempt, refusal raised rather than swallowed, for
    the same reasons as the aggregator client."""
    session = session or requests.Session()
    try:
        for attempt in range(MAX_TRIES):
            charge_for(url)
            try:
                resp = session.get(url, params=params, auth=(api_key, ""),
                                   timeout=TIMEOUT)
            except requests.RequestException:
                if attempt == MAX_TRIES - 1:
                    return None
                _sleep(2 ** attempt)
                continue
            if resp.status_code in RETRY_STATUSES and attempt < MAX_TRIES - 1:
                _sleep(2 ** attempt)
                continue
            if resp.status_code != 200:
                return None
            return resp.json()
        return None
    finally:
        _sleep(PAUSE)


def search_companies(name, api_key, session) -> list[dict] | None:
    """Registry name search; None = the call failed, [] = genuinely no results."""
    data = _get_json(f"{CH_BASE}/search/companies", api_key, session,
                     params={"q": name, "items_per_page": SEARCH_RESULTS})
    if data is None:
        return None
    return [{"title": item.get("title", ""),
             "company_number": item.get("company_number"),
             "company_status": item.get("company_status"),
             "company_type": item.get("company_type"),
             "date_of_creation": item.get("date_of_creation")}
            for item in data.get("items", [])]


def get_profile(number, api_key, session) -> dict | None:
    """One company's registry profile (status, type, industry codes, age)."""
    data = _get_json(f"{CH_BASE}/company/{number}", api_key, session)
    if data is None:
        return None
    return {"company_number": data.get("company_number"),
            "company_status": data.get("company_status"),
            "type": data.get("type"),
            "sic_codes": data.get("sic_codes") or [],
            "date_of_creation": data.get("date_of_creation")}


def match_company(candidates, org_name_norm) -> tuple[str, dict | None]:
    """Deterministic register→registry match; plural stays 'ambiguous'."""
    if not candidates:
        return ("not_found", None)
    pool = [c for c in candidates if norm(c["title"]) == org_name_norm]
    if not pool:
        core = _strip_legal(org_name_norm)
        pool = [c for c in candidates if _strip_legal(norm(c["title"])) == core]
    if len(pool) == 1:
        return ("matched", pool[0])
    if len(pool) > 1:
        active = [c for c in pool if c.get("company_status") == "active"]
        if len(active) == 1:
            return ("matched", active[0])
        return ("ambiguous", None)
    return ("not_found", None)


def enrich_org(cur, org_name_norm, organisation_name, api_key,
               session=None) -> str:
    """Search → match → profile → registry columns; returns the outcome."""
    candidates = search_companies(organisation_name, api_key, session)
    if candidates is None:
        record_registry_result(cur, org_name_norm, "error",
                               error="registry search failed")
        return "error"
    outcome, hit = match_company(candidates, org_name_norm)
    if outcome != "matched":
        record_registry_result(cur, org_name_norm, outcome)
        return outcome
    profile = get_profile(hit["company_number"], api_key, session)
    if profile is None:
        record_registry_result(
            cur, org_name_norm, "error",
            error=f"profile fetch failed: {hit['company_number']}")
        return "error"
    record_registry_result(cur, org_name_norm, "matched",
                           number=profile["company_number"],
                           status=profile["company_status"],
                           company_type=profile["type"],
                           industry_codes=profile["sic_codes"],
                           incorporated=profile["date_of_creation"])
    return "matched"
