"""The daily discovery stage — orchestrates every source under per-source caps.

The scheduler runs this before fetch (scripts/discover_companies.py), so companies
discovered today are fetched the same run and reach tonight's digest. Sources:
  * register  — walk the sponsor register, onboard classifiable candidates.
  * adzuna / reed — pull jobs by criteria, cross-check each employer against the
    register, and onboard the matched sponsors not already tracked.
Each source is capped and reports one line; a failing source is isolated so the
stage degrades rather than dies. All writes happen in the caller's transaction.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import requests

from criteria.loader import default_profile_id, load_criteria
from discover.aggregators import search_adzuna, search_reed
from discover.company import discover_company
from discover.onboarding import onboard_candidates
from discover.register import find_candidates_for_profile
from discover.sponsor_match import cross_check_employer

DEFAULT_CAPS = {"register": 25, "adzuna": 50, "reed": 50, "onboard": 15}


@dataclass(frozen=True)
class SourceReport:
    source: str
    ok: bool
    line: str
    stats: dict = field(default_factory=dict)


def run_register_source(cur, profile_id, *, cap: int, session=None) -> SourceReport:
    """Walk the register (capped) and onboard candidates."""
    candidates = find_candidates_for_profile(cur, profile_id, limit=cap)
    results = onboard_candidates(cur, profile_id, candidates, session)
    onboarded = sum(1 for r in results if r.outcome == "onboarded")
    flagged = sum(1 for r in results if r.outcome == "flagged")
    stats = {"scanned": len(candidates), "onboarded": onboarded, "flagged": flagged}
    line = f"register: {len(candidates)} scanned, {onboarded} onboarded, {flagged} flagged"
    return SourceReport("register", True, line, stats)


def _search(settings, source, pattern, salary_floor, per_query, session):
    if source == "adzuna":
        return search_adzuna(settings.adzuna_app_id, settings.adzuna_app_key,
                             what=pattern, where="UK", results_per_page=per_query,
                             salary_min=salary_floor, session=session)
    return search_reed(settings.reed_api_key, keywords=pattern, location="UK",
                       results_to_take=per_query, minimum_salary=salary_floor,
                       session=session)


def run_aggregator_source(cur, settings, criteria, source, *, cap: int,
                          onboard_cap: int, session=None) -> SourceReport:
    """Pull one aggregator's jobs, cross-check employers, onboard matched sponsors."""
    jobs = []
    for pattern in criteria.role_patterns or []:
        jobs += _search(settings, source, pattern, criteria.salary_floor, cap, session)
    employers = sorted({j.company_name for j in jobs if j.company_name})

    matched = uncertain = onboarded = 0
    for employer in employers:
        verdict = cross_check_employer(cur, employer)
        if verdict.status == "matched":
            matched += 1
            if onboarded < onboard_cap:
                result = discover_company(cur, criteria.profile_id, employer, session)
                if result.get("outcome") == "onboarded":
                    onboarded += 1
        elif verdict.status == "uncertain":
            uncertain += 1

    stats = {"jobs": len(jobs), "employers": len(employers), "matched": matched,
             "onboarded": onboarded, "uncertain": uncertain}
    line = (f"{source}: {len(jobs)} jobs, {len(employers)} employers, {matched} sponsors, "
            f"{onboarded} onboarded, {uncertain} flagged")
    return SourceReport(source, True, line, stats)


def _safe(source: str, run) -> SourceReport:
    """Run one source, converting any failure into a reported (not raised) result."""
    try:
        return run()
    except Exception as err:                     # a bad source degrades, never dies
        return SourceReport(source, False, f"{source}: ERROR {err}", {})


def run_discovery(cur, settings, *, profile_id=None, caps=None, session=None) -> list[SourceReport]:
    """Run every configured discovery source under per-source caps; report each.

    Register always runs. Adzuna/Reed run only when their keys are set. Errors in
    one source are isolated so the others still complete.
    """
    caps = {**DEFAULT_CAPS, **(caps or {})}
    session = session or requests.Session()
    if profile_id is None:
        profile_id = default_profile_id(cur)
    criteria = load_criteria(cur, profile_id)

    reports = [_safe("register", lambda: run_register_source(
        cur, profile_id, cap=caps["register"], session=session))]
    for source, ready in (("adzuna", settings.adzuna_ready), ("reed", settings.reed_ready)):
        if ready:
            reports.append(_safe(source, lambda s=source: run_aggregator_source(
                cur, settings, criteria, s, cap=caps[s], onboard_cap=caps["onboard"],
                session=session)))
    return reports
