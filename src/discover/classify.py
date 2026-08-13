"""Pass 1 of the census: map an official industry code onto every sponsor.

The classification pass. It walks the whole sponsor register and asks Companies
House what each company actually IS — its SIC industry code, status, age — with
NO job-board probing at all. This is the sponsor-first narrowing: once every
company carries its real industry, Pass 2 (job probing, in sweep.py) runs only
on the ones that are genuinely software/IT/data, instead of all 141k blind.

Fast relative to probing: one registry lookup per company, rate-limited by
Companies House (600 requests / 5 min), so the whole register classifies in
~a day or two rather than the weeks blind probing would take.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

import requests

from budget.gate import BudgetExhausted
from discover import companies_house as registry
from discover.census_store import ensure_census_card, record_registry_result
from discover.sweep import TECH_NAME_PATTERN

_sleep = time.sleep

# UK SIC 2007 codes that mean "software / IT / data" — the Pass 2 target set.
# Pass 1 stores every company's raw codes; this set is only used to filter and
# to count "how many software companies have we found".
SOFTWARE_SIC = frozenset({
    "62011",  # ready-made interactive leisure & entertainment software
    "62012",  # business and domestic software development
    "62020",  # information technology consultancy activities
    "62090",  # other information technology service activities
    "63110",  # data processing, hosting and related activities
    "63120",  # web portals
    "58210",  # publishing of computer games
    "58290",  # other software publishing
    "26200",  # manufacture of computers and peripheral equipment
    "72190",  # other R&D on natural sciences and engineering (AI research often here)
})


@dataclass(frozen=True)
class ClassifyReport:
    picked: int = 0
    matched: int = 0
    ambiguous: int = 0
    not_found: int = 0
    errors: int = 0
    budget_stopped: bool = False
    budget: dict | None = None


def pick_classify_batch(cur, n) -> list[dict]:
    """The next N sponsors with no industry code yet (software-named first).

    Anti-join is on registry_checked_at (not on the card's existence), so
    already-probed companies whose card lacks a registry lookup are still
    picked and get classified — nothing done so far is wasted.
    """
    cur.execute(
        "select ls.org_name_norm, min(ls.id) as sponsor_id, "
        "(array_agg(ls.organisation_name order by ls.id))[1] as organisation_name, "
        "(array_agg(ls.town_city order by ls.id))[1] as town_city, "
        "bool_or(ls.is_skilled_worker) as is_skilled_worker, "
        "min(ls.rating) as rating "
        "from licensed_sponsors ls "
        "where ls.org_name_norm is not null and ls.org_name_norm <> '' "
        "and not exists (select 1 from sponsor_census sc "
        "where sc.org_name_norm = ls.org_name_norm "
        "and sc.registry_checked_at is not null) "
        "group by ls.org_name_norm "
        "order by (ls.org_name_norm ~ %(tech)s) desc, "
        "bool_or(ls.is_skilled_worker) desc nulls last, min(ls.id) "
        "limit %(n)s",
        {"n": n, "tech": TECH_NAME_PATTERN})
    return cur.fetchall()


def run_classify(cur, settings, *, batch=5000, session=None, commit=None,
                 on_progress=None) -> ClassifyReport:
    """Classify one batch: ensure a card, ask Companies House, record the code.

    Per-company error isolation (a bad lookup becomes that company's 'error'
    card, the pass continues) and per-company commit (exact crash-resume).
    Does no job-probing — the registry is the only thing it touches.
    """
    if not settings.ch_ready:
        raise RuntimeError(
            "COMPANIES_HOUSE_API_KEY not set — Pass 1 classification needs it.")
    session = session or requests.Session()
    orgs = pick_classify_batch(cur, batch)
    counts = {"matched": 0, "ambiguous": 0, "not_found": 0, "error": 0}
    budget = None
    for done, org in enumerate(orgs, start=1):
        try:
            ensure_census_card(cur, org)
            outcome = registry.enrich_org(
                cur, org["org_name_norm"], org["organisation_name"],
                settings.companies_house_api_key, session)
        except BudgetExhausted as refusal:
            # Deliberately ABOVE the catch-all below. Swallowed there, one
            # exhausted registry budget would stamp a fake 'error' card on
            # every remaining organisation in the batch — up to 2,000 wrong
            # rows, written confidently, from a condition that is simply
            # "come back tomorrow".
            budget = refusal.receipts
            break
        except Exception as err:
            record_registry_result(cur, org["org_name_norm"], "error", error=str(err))
            outcome = "error"
        counts[outcome] = counts.get(outcome, 0) + 1
        if commit is not None:
            commit()
        if on_progress is not None:
            on_progress(done, len(orgs))
    return ClassifyReport(
        picked=len(orgs), matched=counts["matched"], ambiguous=counts["ambiguous"],
        not_found=counts["not_found"], errors=counts["error"],
        budget_stopped=budget is not None, budget=budget)
