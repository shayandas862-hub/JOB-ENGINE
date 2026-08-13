"""Merge register-matched aggregator ads into the queue (Wire 2).

Batches of matched, never-attempted ads become role_listings rows (or are
absorbed by an existing listing / stamped skipped); each batch commits, so a
stop loses nothing and the next start resumes at the unstamped remainder.
    python scripts/merge_ads.py [--batch 200] [--max-batches 50]
"""
from __future__ import annotations

import argparse
import sys

from criteria.loader import default_profile_id
from db.connection import get_conn
from discover.merge import merge_pending


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", type=int, default=200)
    ap.add_argument("--max-batches", type=int, default=50)
    args = ap.parse_args()

    totals: dict[str, int] = {}
    with get_conn() as conn:
        with conn.cursor() as cur:
            owner_id = default_profile_id(cur)
        for _ in range(args.max_batches):
            with conn.cursor() as cur:
                counts = merge_pending(cur, owner_id, limit=args.batch)
            conn.commit()   # per-batch: a stop never loses a stamped batch
            for k, v in counts.items():
                totals[k] = totals.get(k, 0) + v
            if sum(v for k, v in counts.items() if k != "companies_created") == 0:
                break

    print("merge: " + ", ".join(f"{k}={v}" for k, v in sorted(totals.items())),
          file=sys.stderr)


if __name__ == "__main__":
    main()
