"""Re-download the licensed-sponsor register and diff it in (weekly).

    python scripts/refresh_register.py                # download + diff now
    python scripts/refresh_register.py --if-stale 7   # only if 7+ days old
    python scripts/refresh_register.py --csv file.csv # from a local file

Additions insert (new orgs get census cards); vanished (org, route) rows are
stamped licence_removed_at — never deleted. The daily loop runs this with
--if-stale 7, so the register refreshes itself weekly with no operator.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import requests

from db.connection import get_conn
from discover.register_refresh import (PUBLICATION_URL, find_csv_url,
                                       parse_register_csv, refresh,
                                       refresh_is_due)


def _download() -> tuple[str, str]:
    """(csv_text, filename) from the current GOV.UK publication."""
    session = requests.Session()
    session.headers["User-Agent"] = "goal-a-engine register refresh"
    page = session.get(PUBLICATION_URL, timeout=60)
    page.raise_for_status()
    url = find_csv_url(page.text)
    if not url:
        raise RuntimeError("no .csv link on the register publication page")
    data = session.get(url, timeout=300)
    data.raise_for_status()
    return data.text, url.rsplit("/", 1)[-1]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--if-stale", type=int, default=0, metavar="DAYS",
                    help="skip unless the last refresh is at least DAYS old")
    ap.add_argument("--csv", type=Path, default=None,
                    help="diff a local register CSV instead of downloading")
    args = ap.parse_args()

    with get_conn() as conn:
        with conn.cursor() as cur:
            if args.if_stale and not refresh_is_due(cur, days=args.if_stale):
                print("register: fresh enough — skipped", file=sys.stderr)
                return
        if args.csv:
            text, name = args.csv.read_text(), args.csv.name
        else:
            text, name = _download()
        rows = parse_register_csv(text)
        if not rows:
            raise RuntimeError("register CSV parsed to zero rows — not diffing")
        with conn.cursor() as cur:
            counts = refresh(cur, rows, source_file=name)

    print("register refresh: " +
          ", ".join(f"{k}={v}" for k, v in counts.items()), file=sys.stderr)


if __name__ == "__main__":
    main()
