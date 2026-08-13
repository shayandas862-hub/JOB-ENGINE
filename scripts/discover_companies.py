"""Discovery stage: find jobs the engine was never pointed at.

Runs before fetch in the daily loop (scripts/run.py), so companies discovered
today are fetched the same run and reach tonight's digest. Walks the sponsor
register and (when their keys are set) the Adzuna/Reed APIs, onboarding matched
sponsors and flagging the ambiguous ones for review. Prints one capped line per
source — the tail becomes this stage's summary in pipeline_runs.

    python scripts/discover_companies.py
"""
from __future__ import annotations

import sys


def main() -> None:
    from config import get_settings
    from db.connection import get_conn
    from discover.daily import run_discovery

    settings = get_settings()
    with get_conn() as conn, conn.cursor() as cur:
        reports = run_discovery(cur, settings)

    for r in reports:
        print(f"[discover] {r.line}", file=sys.stderr)

    failed = [r.source for r in reports if not r.ok]
    if failed:
        # A source erroring is reported, not fatal — the stage still succeeded at
        # running discovery. The per-source ERROR line is in the summary above.
        print(f"[discover] sources with errors: {', '.join(failed)}", file=sys.stderr)


if __name__ == "__main__":
    main()
