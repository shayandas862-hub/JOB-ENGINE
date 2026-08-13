"""Stage sieve-1/2 survivors into the reading tray (sieve 3's inbox).

Runs in the daily loop after the keyword read: whatever the engine could
only read crudely is staged for a user's AI to read properly over MCP.
The engine itself never waits on this — the queue ranks either way.
    python scripts/stage_reading.py
"""
from __future__ import annotations

import argparse
import sys

from criteria.loader import default_profile_id
from db.connection import get_conn
from reading.stage import stage_ready


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--owner", help="profile_id this pass runs for "
                                    "(defaults to the local owner)")
    args = ap.parse_args()

    with get_conn() as conn:
        with conn.cursor() as cur:
            owner_id = args.owner or default_profile_id(cur)
            result = stage_ready(cur, owner_id)
    print(f"reading tray: staged {result['staged']} matches + "
          f"{result['near_miss']} near-misses of "
          f"{result['candidates']} candidates", file=sys.stderr)


if __name__ == "__main__":
    main()
