"""Nightly Reed JD drip (U5): full descriptions for ad-only listings.

Runs as a pipeline stage right after merge, so tonight's freshly merged ad
rows can gain their full JD and be enriched (salary, deadlines, tray) the
same run. Budget: shares Reed's ledgered ~950/day with the broad sweep and
never overspends it; every attempted call is ledgered. Per-item commit, so
a stop loses nothing. A bad item never fails the stage.
    python scripts/jd_drip.py [--cap 200]
"""
from __future__ import annotations

import argparse
import sys

from config import get_settings
from db.connection import get_conn
from fetch.jd_drip import run_drip


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cap", type=int, default=200,
                    help="the drip's own nightly cap (the shared 950/day "
                         "Reed budget is enforced on top; default 200)")
    args = ap.parse_args()

    with get_conn() as conn, conn.cursor() as cur:
        report = run_drip(cur, get_settings(), cap=args.cap,
                          commit=conn.commit)

    print("jd_drip: " + ", ".join(f"{k}={v}" for k, v in sorted(report.items())),
          file=sys.stderr)


if __name__ == "__main__":
    main()
