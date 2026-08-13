"""Aggregator broad sweep — download ad inventories into the keep-all raw layer.

Jobs-first (founder design 2026-07-22): no role-keyword map. Walk the widest
slice each source allows, store EVERY ad labelled, and match employers against
the sponsor register in SQL. Person-agnostic: slices are flags, not code —
another owner sweeps another category with the same engine.

Usage (PYTHONPATH=src .venv/bin/python scripts/agg_sweep.py ...):
  --status                    cursors + quota + counts; no API calls
  --source both               adzuna | reed | both (default both)
  --pages 40                  page budget per slice per invocation
  --reed-keywords TEXT        default None = the FULL Reed inventory
  --adzuna-category TEXT      Adzuna slice (category browse, no keyword leak);
                              default = the OWNER'S rule category (U1), then
                              it-jobs bootstrap; 'all' = whole inventory
  --reed-cap 950 --adzuna-cap 240   daily call caps (ledgered, hard refusal)

Board learning does NOT live here: following ad links was proven dead on
2026-07-27 (both sources keep users on their own domain, so no ATS token is
ever exposed). Ads instead tell us WHO is hiring, and the free board probe
finds their boards — `scripts/sweep.py --hiring`.

The wrapper `ops/run-aggregator.sh` loops this unattended with a stop file.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _print_status(cur, today=None) -> None:
    cur.execute(
        "select source, sum(ads_seen) as seen, "
        "count(*) filter (where pass_complete) as done, count(*) as slices "
        "from aggregator_cursor group by source order by source")
    for r in cur.fetchall():
        print(f"[agg] {r['source']}: {r['seen']} ads walked across "
              f"{r['slices']} slice(s), {r['done']} complete", file=sys.stderr)
    cur.execute(
        "select slice_key, next_page, ads_seen, total_reported, pass_complete "
        "from aggregator_cursor order by slice_key")
    rows = cur.fetchall()
    print("[agg] cursors:" if rows else "[agg] cursors: none yet", file=sys.stderr)
    for r in rows:
        state = "COMPLETE" if r["pass_complete"] else f"next page {r['next_page']}"
        print(f"[agg]   {r['slice_key']}: {r['ads_seen']} ads seen "
              f"(provider total ~{r['total_reported']}) · {state}", file=sys.stderr)
    # The ledger day MUST match the one run_slice writes (local date) — reading
    # it with Postgres current_date (UTC) showed the previous day's calls
    # between midnight and 01:00 BST (defect found live 2026-07-27).
    cur.execute("select source, calls from api_quota_ledger "
                "where day = %s order by source", (today or date.today(),))
    for r in cur.fetchall():
        print(f"[agg] quota today · {r['source']}: {r['calls']} calls",
              file=sys.stderr)
    cur.execute(
        "select count(*) as n, "
        "count(*) filter (where matched_org_norm is not null) as matched, "
        "count(distinct matched_org_norm) as orgs, "
        "count(*) filter (where is_local) as uk "
        "from aggregator_ads")
    c = cur.fetchone()
    print(f"[agg] stored: {c['n']} ads · {c['uk']} UK · {c['matched']} at "
          f"{c['orgs']} matched sponsors", file=sys.stderr)


def _adzuna_category(cli_value, cur):
    """The owner-lens resolution (U1): an explicit CLI value wins untouched;
    otherwise the owner's rule category, then the it-jobs bootstrap (a
    rule-less database behaves exactly as before U1). 'all' from either
    source means NO category narrowing — the whole-inventory walk Reed
    already does."""
    value = cli_value
    if value is None:
        from criteria.loader import default_profile_id
        from discover.promote_rule import load_rule
        rule = load_rule(cur, default_profile_id(cur))
        value = (rule or {}).get("adzuna_category") or "it-jobs"
    return None if value == "all" else value


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=["adzuna", "reed", "both"], default="both")
    ap.add_argument("--pages", type=int, default=40)
    ap.add_argument("--reed-keywords", default=None)
    ap.add_argument("--reed-location", default=None)
    ap.add_argument("--adzuna-category", default=None,
                    help="explicit category override; default = the owner's "
                         "rule category, then it-jobs; 'all' = whole inventory")
    ap.add_argument("--adzuna-what", default=None)
    ap.add_argument("--adzuna-where", default=None)
    ap.add_argument("--reed-cap", type=int, default=950)
    ap.add_argument("--adzuna-cap", type=int, default=240)
    ap.add_argument("--match-limit", type=int, default=200)
    ap.add_argument("--top-towns", type=int, default=40,
                    help="sponsor towns to partition by (Reed/Adzuna location "
                         "slices; default 40)")
    ap.add_argument("--town-radius", type=int, default=10,
                    help="miles around each town (Reed distanceFromLocation)")
    ap.add_argument("--harvest", action="store_true",
                    help="retired 2026-07-27 (dead link-following); use "
                         "scripts/sweep.py --hiring")
    ap.add_argument("--status", action="store_true")
    args = ap.parse_args()

    from db.connection import get_conn

    if args.status:
        with get_conn() as conn, conn.cursor() as cur:
            _print_status(cur)
        return

    from pipeline.lock import acquire_lock
    lock = acquire_lock(ROOT / ".aggregator.lock")   # held for the whole run
    if lock is None:
        print("[agg] another aggregator sweep is in progress — exiting",
              file=sys.stderr)
        return

    import requests

    from config import get_settings
    from discover.agg_partition import (plan_location_slices, retire_slices,
                                        split_band)
    from discover.agg_sweep import (combine_outcomes, overall_verdict,
                                    run_slice, slice_for)
    from discover.aggregators import page_adzuna, page_reed

    settings = get_settings()
    session = requests.Session()
    slices = []

    def _reed_place_client(place):
        """One (town, poster-type) slice — an exclusive partition, unlike salary."""
        return lambda page, _p=dict(place): page_reed(
            settings.reed_api_key, page=page, location=_p["loc"],
            distance_from_location=args.town_radius,
            posted_by_direct_employer=(_p["emp"] == "direct"),
            posted_by_recruiter=(_p["emp"] == "recruiter"),
            session=session)

    def _reed_client(band=None):
        band = band or {}
        return lambda page, _b=dict(band): page_reed(
            settings.reed_api_key, page=page, keywords=args.reed_keywords,
            location=args.reed_location, minimum_salary=_b.get("smin"),
            maximum_salary=_b.get("smax"), session=session)

    outcomes: dict[str, list] = {}
    with get_conn() as conn:
        with conn.cursor() as cur:
            adzuna_category = _adzuna_category(args.adzuna_category, cur)
        if args.source in ("reed", "both"):
            if not settings.reed_ready:
                print("[agg] reed: no key set — skipped", file=sys.stderr)
            elif args.reed_keywords or args.reed_location:
                # a custom narrow slice — assumed under Reed's 10k wall
                sl = slice_for("reed", keywords=args.reed_keywords,
                               location=args.reed_location)
                slices.append((sl, _reed_client(), args.reed_cap))
            else:
                # Full inventory past Reed's 10k wall. Salary bands are RETIRED
                # (2026-07-28: the salary filter overlaps — a zero-pound-wide
                # band still reports 12,176 results — so it cannot partition
                # anything). Location x poster-type ARE exclusive facts about a
                # job, so each pair opens its own 10k-deep window; the towns
                # come from this owner's own sponsor register.
                with conn.cursor() as cur:
                    retired = retire_slices(cur, "reed", param_key="smin")
                    places = plan_location_slices(cur, top_n=args.top_towns)
                conn.commit()
                if retired:
                    print(f"[agg] reed: retired {retired} futile salary band(s)",
                          file=sys.stderr)
                print(f"[agg] reed: walking {len(places)} location x poster "
                      f"slices", file=sys.stderr)
                for place in places:
                    sl = slice_for("reed", loc=place["loc"], emp=place["emp"])
                    slices.append((sl, _reed_place_client(place), args.reed_cap))
        if args.source in ("adzuna", "both"):
            if not settings.adzuna_ready:
                print("[agg] adzuna: no keys set — skipped", file=sys.stderr)
            elif args.adzuna_what or args.adzuna_where:
                # a custom narrow slice — assumed under Adzuna's silent clamp
                sl = slice_for("adzuna", category=adzuna_category,
                               what=args.adzuna_what, where=args.adzuna_where)
                slices.append((sl, lambda page: page_adzuna(
                    settings.adzuna_app_id, settings.adzuna_app_key, page=page,
                    category=adzuna_category, what=args.adzuna_what,
                    where=args.adzuna_where, session=session), args.adzuna_cap))
            else:
                # Adzuna clamps silently near 5k accessible results per query
                # (2026-07-25) and its salary filter overlaps exactly as Reed's
                # does (2026-07-28), so its salary bands are retired too. One
                # slice per sponsor town (its category already partitions the
                # other axis); Adzuna exposes no poster-type flag.
                with conn.cursor() as cur:
                    a_retired = retire_slices(cur, "adzuna", param_key="smin")
                    towns = []
                    for place in plan_location_slices(cur, top_n=args.top_towns):
                        if place["loc"] not in towns:
                            towns.append(place["loc"])
                conn.commit()
                if a_retired:
                    print(f"[agg] adzuna: retired {a_retired} futile salary "
                          f"band(s)", file=sys.stderr)
                print(f"[agg] adzuna: walking {len(towns)} location slices",
                      file=sys.stderr)
                for town in towns:
                    sl = slice_for("adzuna", category=adzuna_category,
                                   where=town)
                    slices.append((sl, lambda page, _t=town: page_adzuna(
                        settings.adzuna_app_id, settings.adzuna_app_key,
                        page=page, category=adzuna_category,
                        where=_t, session=session), args.adzuna_cap))

        def on_page(sl, page, n, total):
            print(f"[agg] {sl.slice_key} page {page}: +{n} ads "
                  f"(provider total ~{total})", file=sys.stderr)

        for sl, client, cap in slices:
            out = run_slice(conn, sl, client, daily_cap=cap,
                            page_budget=args.pages,
                            match_limit=args.match_limit, on_page=on_page)
            outcomes.setdefault(sl.source, []).append(out)
            print(f"[agg] outcome[{sl.slice_key}]: {out}", file=sys.stderr)
            if out == "depth_wall" and sl.source == "reed" and "smin" in sl.params:
                # An oversized band walled: split ONLY that range so its
                # unreachable remainder becomes reachable next cycle.
                with conn.cursor() as cur:
                    def counted(lo, hi):
                        _, total = page_reed(
                            settings.reed_api_key, page=1, results_to_take=1,
                            minimum_salary=lo, maximum_salary=hi,
                            session=session)
                        return total or 0
                    parts = split_band(cur, "reed", sl.params, counted,
                                       target=9_000)
                conn.commit()
                print(f"[agg] {sl.slice_key} hit the depth wall — re-split into "
                      f"{len(parts)} sub-band(s)", file=sys.stderr)
        with conn.cursor() as cur:
            _print_status(cur)

    combined = {src: combine_outcomes(outs) for src, outs in outcomes.items()}
    for src, out in combined.items():
        print(f"[agg] outcome[{src}]: {out}", file=sys.stderr)
    verdict = overall_verdict(combined)
    if verdict == "pass_complete":
        print("[agg] outcome: pass complete (all slices)", file=sys.stderr)
    elif verdict == "quota_exhausted":
        print("[agg] outcome: quota exhausted (drip resumes after midnight)",
              file=sys.stderr)
    elif verdict == "source_error":
        print("[agg] outcome: source error (transient — will retry)",
              file=sys.stderr)
    else:
        # At least one source still has budget AND pending work: no nap.
        print("[agg] outcome: page budget done (more remains)", file=sys.stderr)


if __name__ == "__main__":
    main()
