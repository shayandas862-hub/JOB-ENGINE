"""Set apply-by dates on open roles. Stated (parsed from the JD) always wins;
then the machine's own history (survival curves per role family, when the
family has enough closed listings behind it); the flat profile window is the
honest fallback. Advisory only — deadlines never filter the queue.

    PYTHONPATH=src python scripts/enrich_deadlines.py
"""
from __future__ import annotations

import argparse
import sys

from criteria.loader import default_profile_id
from db.connection import get_conn
from history.survival import MIN_SAMPLE, build_curves, choose_with_survival
from pipeline.owners import owner_window


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--owner", help="profile_id this pass runs for "
                                    "(defaults to the local owner)")
    args = ap.parse_args()

    with get_conn() as conn:
        with conn.cursor() as cur:
            # B-GAE-028: this used to read `apply_window_days` from the FIRST
            # profile by created_at and then write the resulting dates onto
            # every owner's listings — a per-owner value applied to everyone,
            # open-coded so no search for default_profile_id could find it.
            owner_id = args.owner or default_profile_id(cur)
            window = owner_window(cur, owner_id)
            curves = build_curves(cur)
            # stated deadlines are final; survival/flat estimates refresh as
            # listings age and the curves fill in
            cur.execute(
                """select rl.role_id, rl.jd_full, rl.role_title, rl.soc_code,
                          rl.created_at::date as first_seen
                   from role_listings rl
                   join target_companies tc using (company_id)
                   where rl.role_status = 'open'
                     and tc.owner_id = %s
                     and (rl.deadline is null
                          or rl.deadline_source in ('estimated', 'survival'))""",
                (owner_id,))
            rows = cur.fetchall()

        updates, tally = [], {"stated": 0, "survival": 0, "estimated": 0}
        for r in rows:
            d, source, _receipts = choose_with_survival(
                r["jd_full"], r["first_seen"], r["role_title"], r["soc_code"],
                curves, window_days=window)
            updates.append((d, source, r["role_id"], d, source))
            tally[source] += 1

        if updates:
            with conn.cursor() as cur:
                cur.executemany(
                    "update role_listings set deadline=%s, deadline_source=%s "
                    "where role_id=%s and (deadline is distinct from %s "
                    "or deadline_source is distinct from %s)",
                    updates)

    evidenced = sum(1 for c in curves.values() if c["n"] >= MIN_SAMPLE)
    print(f"deadlines on {len(updates)} open roles "
          f"({tally['stated']} stated, {tally['survival']} survival, "
          f"{tally['estimated']} estimated; {evidenced} families have "
          f"evidence; window {window}d)", file=sys.stderr)


if __name__ == "__main__":
    main()
