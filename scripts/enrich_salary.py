"""Parse a salary range into role_listings.salary_min / salary_max. No API.

Single source of truth: parse the stated salary_text (from the reader) first,
falling back to scanning the full JD only when no salary_text was captured.
    python scripts/enrich_salary.py
"""
from __future__ import annotations

import argparse
import sys

from analysis.salary import parse_salary
from db.connection import get_conn

# role_listings carries no owner_id: a listing reaches its owner through the
# company that was tracked for them. Measured 2026-08-12 before leaning on it —
# 894 companies, 0 with a null owner, 0 of 12,923 listings unreachable — so
# per-owner is a clean partition of the table and not a filter that drops rows.
OWNED_OPEN_ROLES = """
select rl.role_id, rl.jd_full, rl.salary_text
  from role_listings rl
  join target_companies tc using (company_id)
 where rl.role_status = 'open' and tc.owner_id = %s
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--owner", help="profile_id this pass runs for "
                                    "(defaults to the local owner)")
    args = ap.parse_args()

    with get_conn() as conn:
        with conn.cursor() as cur:
            from criteria.loader import default_profile_id
            owner_id = args.owner or default_profile_id(cur)
            cur.execute(OWNED_OPEN_ROLES, (owner_id,))
            rows = cur.fetchall()
        updates = []
        for r in rows:
            parsed = parse_salary(r["salary_text"]) or parse_salary(r["jd_full"])
            if parsed:
                updates.append((parsed[0], parsed[1], r["role_id"]))
        if updates:
            with conn.cursor() as cur:
                # One batched round trip; only touch rows whose values changed
                # so updated_at keeps meaning "something actually changed".
                cur.executemany(
                    "update role_listings set salary_min=%s, salary_max=%s, updated_at=now() "
                    "where role_id=%s and (salary_min is distinct from %s "
                    "or salary_max is distinct from %s)",
                    [(lo, hi, rid, lo, hi) for lo, hi, rid in updates],
                )
        print(f"set salary range on {len(updates)} of {len(rows)} open roles", file=sys.stderr)


if __name__ == "__main__":
    main()
