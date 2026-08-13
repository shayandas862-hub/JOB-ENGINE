"""Pass 2 of the census: probe the OWNER'S lens first, in parallel.

Pass 1 (classify_sponsors) stamped every register org with its national-
registry industry codes. This module is the Pass-2 narrowing: hand out ONLY
the cards that are registry-matched, inside the owner's lens and never
probed, and run the existing probe over them — sequentially, or with N
workers for the one real efficiency win. The lens is the owner's promotion
rule's industry codes (U1: a care-home rule picks care-home cards with no
code edit); SOFTWARE_SIC survives only as the bootstrap fallback for a
rule-less database. The probe machinery itself (probe_org, upsert_probe,
SweepReport) is reused from discover.sweep untouched; there is deliberately
no registry call here — Pass 1 already did that. Blast radius unchanged:
every write goes through census_store.
"""
from __future__ import annotations

import queue
import threading
import time

from criteria.loader import build_role_matcher, default_profile_id, load_criteria
from discover.census_store import upsert_probe
from discover.classify import SOFTWARE_SIC
from discover.promote_rule import load_rule
from discover.sweep import SweepReport, load_tracked_orgs, probe_org

_sleep = time.sleep     # swappable pacing, same seam as the sweep


def owner_lens_codes(cur, owner_id) -> list[str]:
    """The owner's Pass-2 lens: their rule's industry codes.

    Falls back to the software bootstrap set when no rule (or an empty code
    set) exists, so a rule-less database behaves exactly as before U1."""
    rule = load_rule(cur, owner_id)
    codes = (rule or {}).get("industry_codes") or []
    return list(codes) if codes else list(SOFTWARE_SIC)


def pick_owner_lens_batch(cur, n) -> list[dict]:
    """The next N owner-lens cards that Pass 1 matched and Pass 2 hasn't probed.

    The exact narrowing: probe_outcome IS NULL (never probed),
    registry_outcome = 'matched' (confident registry hit), industry_codes
    overlapping the OWNER'S rule codes. Active companies first (dissolved
    ones can wait), then name order — deterministic, so a stopped run
    resumes exactly.
    """
    codes = owner_lens_codes(cur, default_profile_id(cur))
    cur.execute(
        "select org_name_norm, sponsor_id, organisation_name, town_city, "
        "is_skilled_worker, rating, ats_type, ats_token from sponsor_census "
        "where probe_outcome is null and registry_outcome = 'matched' "
        "and industry_codes && %(codes)s::text[] "
        "order by (registry_status = 'active') desc nulls last, org_name_norm "
        "limit %(n)s",
        {"n": n, "codes": codes})
    return cur.fetchall()


def pick_hiring_batch(cur, n) -> list[dict]:
    """The next N never-probed sponsors that aggregator ads prove are HIRING.

    The 2026-07-27 replacement for the dead URL-harvest: an ad tells us who is
    advertising right now, and finding that employer's board is free. Pass 2
    only probed the software-SIC lot, so most actively-hiring sponsors carry no
    probe outcome at all. Busiest hirers first (ad count), then name order —
    deterministic, so a stopped run resumes exactly.
    """
    cur.execute(
        "select sc.org_name_norm, sc.sponsor_id, sc.organisation_name, "
        "sc.town_city, sc.is_skilled_worker, sc.rating, sc.ats_type, "
        "sc.ats_token from sponsor_census sc "
        "join aggregator_ads a on a.matched_org_norm = sc.org_name_norm "
        "where sc.probe_outcome is null "
        "group by sc.org_name_norm, sc.sponsor_id, sc.organisation_name, "
        "sc.town_city, sc.is_skilled_worker, sc.rating, sc.ats_type, "
        "sc.ats_token "
        "order by count(*) desc, sc.org_name_norm limit %(n)s",
        {"n": n})
    return cur.fetchall()


def _probe_one(cur, org, session, matcher, tracked, counts) -> tuple[int, int]:
    """Card one org (tracked-copy, probe, or error) and tally its outcome."""
    try:
        known = tracked.get(org["org_name_norm"])
        if known is not None:
            upsert_probe(cur, org, outcome="already_tracked",
                         ats_type=known["ats_type"], ats_token=known["ats_token"],
                         careers_url=known["careers_url"])
            counts["already_tracked"] += 1
            return (0, 0)
        outcome, stored, matched = probe_org(cur, org, session, matcher)
        counts[outcome] += 1
        return (stored, matched)
    except Exception as err:                    # per-org isolation, as the sweep
        upsert_probe(cur, org, outcome="error", probe_error=str(err))
        counts["error"] += 1
        return (0, 0)


def run_lens_sweep(cur, settings, *, batch=2000, pause=0.3, session=None,
                   commit=None, on_progress=None, picker=None) -> SweepReport:
    """One sequential probe batch; per-org commit = exact resume.

    `picker` swaps the batch source without touching the probe machinery:
    the owner-lens lot by default, or `pick_hiring_batch` for hiring-first."""
    import requests
    session = session or requests.Session()
    owner = default_profile_id(cur)
    matcher = build_role_matcher(load_criteria(cur, owner).role_patterns)
    tracked = load_tracked_orgs(cur, owner)
    orgs = (picker or pick_owner_lens_batch)(cur, batch)

    counts = {"board_found": 0, "no_board": 0, "already_tracked": 0, "error": 0}
    jobs_stored = title_matches = 0
    for done, org in enumerate(orgs, start=1):
        stored, matched = _probe_one(cur, org, session, matcher, tracked, counts)
        jobs_stored += stored
        title_matches += matched
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
                       title_matches=title_matches)


def run_lens_sweep_parallel(conn_factory, settings, *, batch=2000,
                            workers=4, pause=0.3,
                            on_progress=None, picker=None) -> SweepReport:
    """The Pass-2 efficiency win: N probe workers, each with its OWN connection.

    The main connection only picks the batch and loads criteria; each worker
    then opens its own connection (psycopg connections are one-per-thread) and
    keeps the per-org commit, so a crash or stop still resumes exactly. Overall
    politeness: each worker paces itself by `pause`, so total request rate is
    roughly workers/pause per second — keep workers modest (4–6).
    """
    import requests

    with conn_factory() as conn, conn.cursor() as cur:
        owner = default_profile_id(cur)
        matcher = build_role_matcher(load_criteria(cur, owner).role_patterns)
        tracked = load_tracked_orgs(cur, owner)
        orgs = (picker or pick_owner_lens_batch)(cur, batch)

    todo: queue.Queue = queue.Queue()
    for org in orgs:
        todo.put(org)

    lock = threading.Lock()
    counts = {"board_found": 0, "no_board": 0, "already_tracked": 0, "error": 0}
    totals = {"jobs": 0, "matches": 0, "done": 0}

    def worker() -> None:
        session = requests.Session()
        with conn_factory() as conn, conn.cursor() as cur:
            while True:
                try:
                    org = todo.get_nowait()
                except queue.Empty:
                    return
                local_counts = {k: 0 for k in counts}
                stored, matched = _probe_one(cur, org, session, matcher,
                                             tracked, local_counts)
                conn.commit()                      # per-org commit, per worker
                with lock:
                    for k, v in local_counts.items():
                        counts[k] += v
                    totals["jobs"] += stored
                    totals["matches"] += matched
                    totals["done"] += 1
                    if on_progress is not None:
                        on_progress(totals["done"], len(orgs))
                if pause:
                    _sleep(pause)

    threads = [threading.Thread(target=worker, daemon=True)
               for _ in range(max(1, workers))]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    return SweepReport(picked=len(orgs), boards_found=counts["board_found"],
                       no_board=counts["no_board"],
                       already_tracked=counts["already_tracked"],
                       errors=counts["error"], jobs_stored=totals["jobs"],
                       title_matches=totals["matches"])
