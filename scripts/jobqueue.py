"""Work the apply queue from the terminal — no SQL needed.

  python scripts/jobqueue.py                 # top of the ranked apply queue
  python scripts/jobqueue.py --gaps          # top skill gaps (what to learn)
  python scripts/jobqueue.py --applied 123   # mark role 123 as applied
  python scripts/jobqueue.py --limit 40      # show more rows

The founder's own terminal door, so the owner is the local profile — the
stdio/local fallback, exactly as CLAUDE.md scopes default_profile_id. It is
stated rather than assumed because migration 0051 made "no owner filter" mean
"everybody's rows" instead of "the only owner's rows".
"""
from __future__ import annotations

import argparse
import sys

from criteria.loader import default_profile_id
from db.connection import get_conn


def _history_bits(r) -> str:
    bits = [f"{r['age_days']}d old"]
    if r["last_changed_at"]:
        bits.append(f"changed {r['last_changed_at']:%d %b}")
    if r["deadline"]:
        label = "apply by" if r["deadline_source"] == "stated" else "apply by (est.)"
        bits.append(f"{label} {r['deadline']:%d %b}")
    return " | ".join(bits)


def show_queue(limit: int) -> None:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """select role_id, company_name, fit_rank, sponsor_signal,
                      coalesce(salary_wall,'unknown') as salary_wall, role_title, role_url,
                      age_days, last_changed_at, deadline, deadline_source
               from v_apply_queue where owner_id = %s limit %s""",
            (default_profile_id(cur), limit),
        )
        rows = cur.fetchall()
    print(f"\nAPPLY QUEUE - top {len(rows)} (fit -> sponsor -> recency)\n")
    for r in rows:
        print(f"[{r['role_id']:>4}] {r['fit_rank']:<4} | {r['sponsor_signal']:<13} | "
              f"{r['salary_wall']:<18} | {r['company_name']:<15} | {r['role_title'][:52]}")
        print(f"        {_history_bits(r)}")
        print(f"        {r['role_url']}")


def show_gaps(limit: int) -> None:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "select skill, skill_type, demand from v_skill_gap "
            "where owner_id = %s and i_have_it = false "
            "order by demand desc limit %s",
            (default_profile_id(cur), limit),
        )
        rows = cur.fetchall()
    print("\nTOP SKILL GAPS - what the fit roles want that you lack\n")
    for r in rows:
        print(f"  {r['demand']:>3} roles | {r['skill_type']:<11} | {r['skill']}")


def mark_applied(role_id: int) -> None:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "update role_listings r set application_status='applied', "
            "applied_date=current_date, updated_at=now() "
            "from target_companies c "
            "where c.company_id = r.company_id "
            "and r.role_id=%s and c.owner_id=%s returning r.role_title",
            (role_id, default_profile_id(cur)),
        )
        row = cur.fetchone()
    print(f"Marked role {role_id} applied: {row['role_title']}" if row
          else f"No role with id {role_id}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gaps", action="store_true")
    ap.add_argument("--applied", type=int)
    ap.add_argument("--limit", type=int, default=20)
    args = ap.parse_args()
    if args.applied:
        mark_applied(args.applied)
    elif args.gaps:
        show_gaps(args.limit)
    else:
        show_queue(args.limit)


if __name__ == "__main__":
    main()
