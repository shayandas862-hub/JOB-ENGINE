"""Filing stage: a tailored CV + a Notion card for each gate-passing listing.

Runs after eval and before the nudge, so the morning digest can link to a board
whose cards already carry the CVs. Also syncs 'Applied' back from Notion. Skipped
cleanly when Notion isn't configured — the rest of the loop is unaffected.

    python scripts/file_applications.py
"""
from __future__ import annotations

import argparse
import sys


def main() -> None:
    from config import get_settings
    from criteria.loader import default_profile_id
    from cv.filing import run_filing_stage
    from db.connection import get_conn

    ap = argparse.ArgumentParser()
    ap.add_argument("--owner", help="profile_id this pass runs for "
                                    "(defaults to the local owner)")
    args = ap.parse_args()

    settings = get_settings()
    with get_conn() as conn, conn.cursor() as cur:
        owner_id = args.owner or default_profile_id(cur)
        report = run_filing_stage(cur, settings, owner_id=owner_id)
    print(f"[file] {report['line']}", file=sys.stderr)


if __name__ == "__main__":
    main()
