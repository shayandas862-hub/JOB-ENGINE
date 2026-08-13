"""Grounding eval over extracted skills — run after any extraction.

Reports what fraction of extracted skills appear verbatim in their job
description, and lists the ungrounded skill names (canonicalisations vs possible
hallucinations) for review. Read-only; never modifies data.

    PYTHONPATH=src python scripts/eval_extraction.py
    PYTHONPATH=src python scripts/eval_extraction.py --min 85   # exit 1 if below 85%
"""
from __future__ import annotations

import argparse
import sys

from db.connection import fetch_all
from read.eval import evaluate


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--min", type=float, default=None,
                    help="fail (exit 1) if grounded%% is below this threshold")
    ap.add_argument("--top", type=int, default=25, help="how many ungrounded names to list")
    ap.add_argument("--owner", help="profile_id this pass runs for "
                                    "(defaults to the local owner)")
    args = ap.parse_args()

    # Scoped to one owner's corpus through target_companies.owner_id. The
    # grounding score itself is owner-independent — a skill is either verbatim
    # in the JD or it is not — but the GATE is not: a shared average lets one
    # owner's broken extraction hide inside everyone else's good numbers, and
    # the stage that fails should be the stage of the person it failed for.
    from criteria.loader import default_profile_id
    from db.connection import get_conn

    if args.owner:
        owner_id = args.owner
    else:
        with get_conn() as conn, conn.cursor() as cur:
            owner_id = default_profile_id(cur)

    rows = fetch_all(
        """select rs.skill_asked, rs.skill_norm, rs.role_id, r.jd_full
           from role_skills rs
           join role_listings r on r.role_id = rs.role_id
           join target_companies tc on tc.company_id = r.company_id
           where r.role_status = 'open' and coalesce(r.jd_full, '') <> ''
             and tc.owner_id = %s""",
        (owner_id,)
    )
    rep = evaluate(rows)

    print(f"skills checked   : {rep.total}")
    print(f"grounded         : {rep.grounded} ({rep.pct}%)")
    print(f"ungrounded       : {rep.ungrounded}  (canonicalisation or hallucination — review)")
    print(f"\ntop {args.top} ungrounded skill names:")
    for name, count in sorted(rep.by_name.items(), key=lambda x: -x[1])[: args.top]:
        print(f"  {count:>4}  {name}")

    if args.min is not None and rep.pct < args.min:
        print(f"\nFAIL: grounded {rep.pct}% < required {args.min}%", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
