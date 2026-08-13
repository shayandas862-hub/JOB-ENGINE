"""The census sweep: every register organisation gets a card, batch by batch.

Not discovery, not tracking — a census. pick_batch hands out the next N
organisations that have no sponsor_census card yet (skilled-worker A-rated
first); the runner probes each for a job board with the existing classifier,
copies live jobs ONCE (no Gemini anywhere — titles are keyword-matched), and
records everything through census_store. Orgs already on the tracked list are
marked, never re-probed. Blast radius: the sweep's only writes go through
census_store — never target_companies, never review_items.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

import requests

from budget.gate import BudgetExhausted
from criteria.loader import build_role_matcher, default_profile_id, load_criteria
from discover import companies_house as registry   # the country seam: one import
from discover.census_store import (insert_census_jobs, update_probe_fetch,
                                   upsert_probe)
from discover.company import probe_token
from fetch.ats import ATS_UNKNOWN, classify_company
from fetch.feeds import fetch_company, is_uk
from normalise.text import norm

_sleep = time.sleep          # swappable pacing (tests stub it; retry backoff lives downstream)
_is_local = is_uk            # the country seam: another country swaps this one name
MAX_JOBS_PER_ORG = 500       # agency/shared boards can list thousands; the census caps

# Software-likelihood ordering (Postgres regex over the lowercased org_name_norm).
# The register has no industry column, so a name signal is the only lever — and it
# is used only to ORDER the census, never to filter it: every org is still probed
# eventually, but the clearly-tech-named ones go first, so the sponsoring software
# companies (the ones worth finding) surface early instead of after 100k care homes.
# \y = word boundary; short tokens (ai/ml/data) are bounded to avoid 'email'/'retail'.
TECH_NAME_PATTERN = (
    r"(software|technolog|\ytech\y|digital|\ydata|analyt|comput|cyber|\ycloud"
    r"|\ysystem|network|robot|quantum|fintech|biotech|infotech|informat"
    r"|semiconductor|\ysaas\y|\yai\y|\yml\y|artificial intel|machine learning"
    r"|cognitive|neural|platform|\yio\y|\yapps?\y)")


@dataclass(frozen=True)
class SweepReport:
    picked: int = 0
    boards_found: int = 0
    no_board: int = 0
    already_tracked: int = 0
    errors: int = 0
    jobs_stored: int = 0
    title_matches: int = 0
    budget_stopped: bool = False
    budget: dict | None = None


def pick_batch(cur, n, *, retry_errors=False) -> list[dict]:
    """The next N unprocessed organisations, one row per unique org_name_norm.

    Register rows repeat per route, so aggregate deterministically: the min-id
    row supplies the display name/town, bool_or answers "skilled worker on any
    route". Ordering puts software-likely names first (TECH_NAME_PATTERN), then
    skilled-worker A-rated orgs, then register id — so tech sponsors surface
    early without excluding anyone. With retry_errors, re-hand out previously
    errored census cards instead.
    """
    if retry_errors:
        cur.execute(
            "select org_name_norm, sponsor_id, organisation_name, town_city, "
            "is_skilled_worker, rating from sponsor_census "
            "where probe_outcome = 'error' order by probed_at limit %(n)s",
            {"n": n})
        return cur.fetchall()
    cur.execute(
        "select ls.org_name_norm, min(ls.id) as sponsor_id, "
        "(array_agg(ls.organisation_name order by ls.id))[1] as organisation_name, "
        "(array_agg(ls.town_city order by ls.id))[1] as town_city, "
        "bool_or(ls.is_skilled_worker) as is_skilled_worker, "
        "min(ls.rating) as rating "
        "from licensed_sponsors ls "
        "where ls.org_name_norm is not null and ls.org_name_norm <> '' "
        "and not exists (select 1 from sponsor_census sc "
        "where sc.org_name_norm = ls.org_name_norm) "
        "group by ls.org_name_norm "
        "order by (ls.org_name_norm ~ %(tech)s) desc, "
        "bool_or(ls.is_skilled_worker) desc nulls last, "
        "bool_or(ls.rating = %(a_rating)s) desc nulls last, min(ls.id) "
        "limit %(n)s",
        {"n": n, "a_rating": "A", "tech": TECH_NAME_PATTERN})
    return cur.fetchall()


def load_tracked_orgs(cur, owner_id) -> dict[str, dict]:
    """Norm-keyed map of orgs already on the tracked list (read-only).

    Keyed by BOTH the Python-normed company name and, when the company is
    register-linked, its register norm — catching orgs tracked under a
    different name than their register row. Values carry the ats fields so
    the census card can copy them without re-probing.
    """
    cur.execute(
        "select tc.company_name, tc.ats_type, tc.ats_token, tc.careers_url, "
        "ls.org_name_norm as linked_norm "
        "from target_companies tc "
        "left join licensed_sponsors ls on ls.id = tc.sponsor_id "
        "where tc.owner_id = %s",
        (owner_id,))
    tracked: dict[str, dict] = {}
    for r in cur.fetchall():
        info = {"ats_type": r["ats_type"], "ats_token": r["ats_token"],
                "careers_url": r["careers_url"]}
        for key in (norm(r["company_name"]), r["linked_norm"]):
            if key:
                tracked.setdefault(key, info)
    return tracked


def probe_org(cur, org, session, title_matcher) -> tuple[str, int, int]:
    """Probe one org for a board; on a hit, fetch its jobs ONCE and store them.

    ALL fetched jobs are stored, labelled is_local/title_match — locals first
    when the per-org cap bites; local_jobs_seen counts only the local ones.
    Returns (outcome, jobs_stored, title_matches). A 0-job board hit is
    'no_board' by design — classify_company treats it as a token collision.
    A failed fetch keeps the board_found verdict: local_jobs_seen stays NULL
    (fetch failed) vs 0 (fetched, none local) — the census can tell them apart.
    A card carrying harvested ats_type/ats_token hints is verified with ONE
    direct call first; slug guessing only runs when there is no live hint.
    """
    c = None
    if org.get("ats_type") and org.get("ats_token"):
        c = probe_token(org["ats_type"], org["ats_token"], session)
        if c is not None and (c.ats_type == ATS_UNKNOWN or not c.ats_token):
            c = None
    if c is None:
        c = classify_company(org["organisation_name"], session)
    if c.ats_type == ATS_UNKNOWN or not c.ats_token:
        upsert_probe(cur, org, outcome="no_board")
        return ("no_board", 0, 0)
    upsert_probe(cur, org, outcome="board_found", ats_type=c.ats_type,
                 ats_token=c.ats_token, careers_url=c.careers_url,
                 total_jobs_seen=c.n_jobs)
    try:
        jobs = fetch_company(org["organisation_name"], c.ats_type, c.ats_token,
                             session)
    except Exception as err:
        update_probe_fetch(cur, org["org_name_norm"], local_jobs_seen=None,
                           probe_error=f"fetch failed: {err}")
        return ("board_found", 0, 0)
    local = [j for j in jobs if _is_local(j.location)]
    foreign = [j for j in jobs if not _is_local(j.location)]
    kept = (local + foreign)[:MAX_JOBS_PER_ORG]      # locals first when capped
    stored, matched = insert_census_jobs(cur, org["org_name_norm"], kept,
                                         title_matcher, _is_local)
    update_probe_fetch(cur, org["org_name_norm"],
                       local_jobs_seen=min(len(local), MAX_JOBS_PER_ORG))
    return ("board_found", stored, matched)


def run_sweep(cur, settings, *, batch=2000, pause=0.3, retry_errors=False,
              probe_only=False, session=None, commit=None,
              on_progress=None) -> SweepReport:
    """One census batch: pick N, card each org, commit per org, pace politely.

    Per-org isolation: any error becomes that org's 'error' card and the sweep
    continues — one bad org costs one org. The commit callable (the script
    passes conn.commit) fires after EVERY org so a crash resumes exactly.
    settings/probe_only gate the registry enrichment layer once configured.
    """
    session = session or requests.Session()
    owner = default_profile_id(cur)
    title_matcher = build_role_matcher(load_criteria(cur, owner).role_patterns)
    tracked = load_tracked_orgs(cur, owner)
    orgs = pick_batch(cur, batch, retry_errors=retry_errors)

    counts = {"board_found": 0, "no_board": 0, "already_tracked": 0, "error": 0}
    jobs_stored = title_matches = 0
    budget = None
    for done, org in enumerate(orgs, start=1):
        try:
            known = tracked.get(org["org_name_norm"])
            if known is not None:
                upsert_probe(cur, org, outcome="already_tracked",
                             ats_type=known["ats_type"],
                             ats_token=known["ats_token"],
                             careers_url=known["careers_url"])
                outcome = "already_tracked"
            else:
                outcome, stored, matched = probe_org(cur, org, session,
                                                     title_matcher)
                jobs_stored += stored
                title_matches += matched
            if not probe_only and settings.ch_ready:
                registry.enrich_org(cur, org["org_name_norm"],
                                    org["organisation_name"],
                                    settings.companies_house_api_key, session)
        except BudgetExhausted as refusal:
            # ABOVE the catch-all, and this is the runner most likely to meet
            # it: the knock-on-demand sweep is started BY an owner, on their
            # lens, and enriches every organisation against the registry.
            # Swallowed below, one spent budget would card every remaining
            # organisation 'error' — and a card is what stops it being picked
            # again, so the damage would outlive the day it was caused.
            budget = refusal.receipts
            break
        except Exception as err:
            upsert_probe(cur, org, outcome="error", probe_error=str(err))
            outcome = "error"
        counts[outcome] += 1
        if commit is not None:
            commit()
        if on_progress is not None:
            on_progress(done, len(orgs))
        if pause:
            _sleep(pause)

    return SweepReport(picked=len(orgs), boards_found=counts["board_found"],
                       no_board=counts["no_board"],
                       already_tracked=counts["already_tracked"],
                       errors=counts["error"], jobs_stored=jobs_stored,
                       title_matches=title_matches,
                       budget_stopped=budget is not None, budget=budget)
