"""Fetch jobs from classified companies.

Dry-run (no DB) reports counts for the Milestone-1 checkpoint:
    python scripts/fetch_jobs.py --dry-run --companies <classified.json>

DB mode (default) writes UK jobs to role_listings with dedupe + job-rot,
logging the run in fetch_runs:
    python scripts/fetch_jobs.py
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import requests

from criteria.loader import SAMPLE_ROLE_PATTERNS, build_role_matcher, load_criteria
from fetch.feeds import fetch_company, is_uk


def _role_matcher():
    """Role-fit patterns come from the profile's target_roles (personal data
    lives in the DB, not code). Offline dry-runs fall back to generic samples."""
    if os.getenv("DATABASE_URL", "").strip():
        from db.connection import get_conn
        with get_conn() as conn, conn.cursor() as cur:
            return build_role_matcher(load_criteria(cur).role_patterns)
    print("no DATABASE_URL — dry-run using generic sample role patterns", file=sys.stderr)
    return build_role_matcher(SAMPLE_ROLE_PATTERNS)


# ---------------- dry-run (no DB) ----------------

def load_feed_companies(path: str) -> list[dict]:
    rows = json.load(open(path))
    return [
        r for r in rows
        if r.get("ats_type") and r["ats_type"] != "unknown" and r.get("ats_token")
    ]


def dry_run(companies: list[dict]) -> None:
    is_target_role = _role_matcher()
    session = requests.Session()
    tot_all = tot_uk = tot_fit = tot_fit_sal = 0
    print(f"Fetching {len(companies)} feed companies...\n", file=sys.stderr)
    for c in sorted(companies, key=lambda r: r["company_name"]):
        name, ats, token = c["company_name"], c["ats_type"], c["ats_token"]
        try:
            jobs = fetch_company(name, ats, token, session)
        except Exception as e:
            print(f"  {name:18} {ats:10} ERROR: {str(e)[:50]}", file=sys.stderr)
            continue
        uk = [j for j in jobs if is_uk(j.location)]
        fit = [j for j in uk if is_target_role(j.title)]
        fit_sal = sum(1 for j in fit if j.salary_text)
        tot_all += len(jobs); tot_uk += len(uk); tot_fit += len(fit); tot_fit_sal += fit_sal
        flag = "  <-- role matches" if fit else ""
        print(f"  {name:18} {ats:10} {len(fit):>2} fit / {len(uk):>3} UK / {len(jobs):>4} total{flag}",
              file=sys.stderr)
    print("\n=== CHECKPOINT (Milestone 1) ===", file=sys.stderr)
    print(f"feed companies fetched : {len(companies)}", file=sys.stderr)
    print(f"total jobs seen        : {tot_all}", file=sys.stderr)
    print(f"UK jobs                : {tot_uk}", file=sys.stderr)
    print(f"UK + role-fit jobs     : {tot_fit}", file=sys.stderr)
    pct = 100 * tot_fit_sal // max(tot_fit, 1)
    print(f"  of those, w/ salary  : {tot_fit_sal} ({pct}%)", file=sys.stderr)


# ---------------- DB mode (persist) ----------------

def db_run() -> None:
    from db.connection import get_conn
    from fetch.feeds import dedupe_key
    from history.events import plan_events, record_closed, record_events, reset_reads
    from persist.fetch_rules import close_vanished, fetch_outcome, finish_run, upsert_jobs

    session = requests.Session()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """select company_id, company_name, ats_type, ats_token, feed_status
                   from target_companies
                   where ats_type is not null and ats_type <> 'unknown' and ats_token is not null
                   order by company_name"""
            )
            companies = cur.fetchall()
            cur.execute("insert into fetch_runs (status) values ('running') returning run_id")
            run_id = cur.fetchone()["run_id"]
            # Companies with no usable feed are uncovered, not silent (GA-010).
            cur.execute(
                "update target_companies set feed_status='no_feed' "
                "where ats_type is null or ats_type='unknown' or ats_token is null")
        conn.commit()  # the run row survives even if a later company crashes

        rot_ids: list[int] = []
        fetched = 0
        total_seen = 0
        for c in companies:
            cid, name = c["company_id"], c["company_name"]
            try:
                jobs = fetch_company(name, c["ats_type"], c["ats_token"], session)
            except Exception as e:
                with conn.cursor() as cur:
                    cur.execute(
                        "update target_companies set feed_status='error', last_fetched_at=now() "
                        "where company_id=%s", (cid,))
                conn.commit()
                print(f"  {name:18} ERROR: {str(e)[:50]}", file=sys.stderr)
                continue
            # Keep-all (founder rule 2026-07-16): every job the feed returned is
            # stored labelled is_local/source; nothing is filtered here.
            uk_n = sum(1 for j in jobs if is_uk(j.location))
            status, rot_eligible = fetch_outcome(len(jobs), c["feed_status"])
            with conn.cursor() as cur:
                # history: compare against what we knew before this run
                cur.execute(
                    "select role_id, dedupe_key, role_status, content_fingerprint, "
                    "role_title, location, salary_text, jd_full "
                    "from role_listings where company_id=%s", (cid,))
                existing = {r["dedupe_key"]: r for r in cur.fetchall()}
                keyed = [(dedupe_key(name, j.title, j.url), j) for j in jobs]
                events = plan_events(name, existing, keyed)
                upsert_jobs(cur, cid, name, jobs, run_id)
                record_events(cur, events, run_id, cid)
                reset_reads(cur, events)   # description changed -> re-read that listing
                cur.execute(
                    "update target_companies set feed_status=%s, last_fetched_at=now() "
                    "where company_id=%s", (status, cid))
            conn.commit()  # one company = one transaction; a late crash costs one company
            if rot_eligible:
                rot_ids.append(cid)
            fetched += 1
            total_seen += len(jobs)
            note = "" if rot_eligible else "  (empty once - listings protected)"
            print(f"  {name:18} {len(jobs):>3} jobs ({uk_n} UK){note}", file=sys.stderr)

        # job-rot: close vanished listings, but only for rot-eligible companies
        # (with UK jobs this run, or empty for the second consecutive run).
        with conn.cursor() as cur:
            closed_ids = close_vanished(cur, rot_ids, run_id)
            record_closed(cur, closed_ids, run_id)
            closed = len(closed_ids)
            finish_run(cur, run_id, len(companies), total_seen)

    print(f"\nRun {run_id}: {total_seen} jobs stored (all labelled) across "
          f"{fetched} companies; {closed} stale listing(s) closed.", file=sys.stderr)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--companies", help="classified.json (dry-run mode)")
    args = ap.parse_args()
    if args.dry_run:
        dry_run(load_feed_companies(args.companies))
    else:
        db_run()


if __name__ == "__main__":
    main()
