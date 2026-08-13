"""Nightly rule-based census promotion (the button became a rule).

Evaluates the owner's promotion rule over board_found census cards:
full passes promote through the audited bridge; borderline cards get a
capped promotion_review flag; everything else stays in the census.
    python scripts/promote_by_rule.py [--limit 500]
"""
from __future__ import annotations

import argparse
import sys

from criteria.loader import default_profile_id
from db.connection import get_conn
from discover.promote_rule import evaluate_rule


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=500)
    ap.add_argument("--owner", help="profile_id this pass runs for "
                                    "(defaults to the local owner)")
    args = ap.parse_args()

    with get_conn() as conn:
        with conn.cursor() as cur:
            owner_id = args.owner or default_profile_id(cur)
            counts = evaluate_rule(cur, owner_id, limit=args.limit)

    print("rule-promotion: " +
          ", ".join(f"{k}={v}" for k, v in sorted(counts.items())),
          file=sys.stderr)


if __name__ == "__main__":
    main()
