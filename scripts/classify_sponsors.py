#!/usr/bin/env python3
"""Pass 1 of the census: map an official industry code onto every sponsor.

Usage:
    PYTHONPATH=src .venv/bin/python scripts/classify_sponsors.py [--batch N]

Walks the sponsor register and asks Companies House what each company actually
is (SIC industry code, status, age) — no job-board probing. Once every company
is classified, Pass 2 (scripts/sweep.py) probes jobs only at the software ones.

Its own lock (.classify.lock), so it can run alongside the job-probe sweep.
Per-company commits make a crash resume exactly. Per-item errors never fail the
run. Needs COMPANIES_HOUSE_API_KEY in .env.

Also the daily loop's `classify` stage (a capped --batch), where it tops up the
sponsors the weekly register refresh brought in. Everything the loop needs is a
quiet exit: no key or nothing left to classify both end at 0, never a failure.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROGRESS_EVERY = 100


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description="Classify sponsors by industry (Pass 1).")
    ap.add_argument("--batch", type=int, default=5000,
                    help="companies to classify this run (default 5000)")
    return ap.parse_args(argv)


def main(argv=None) -> None:
    args = parse_args(argv)
    from config import get_settings
    from db.connection import get_conn
    from discover.census_store import classify_status_counts
    from discover.classify import SOFTWARE_SIC, run_classify
    from pipeline.lock import acquire_lock

    lock = acquire_lock(ROOT / ".classify.lock")
    if lock is None:
        print("[classify] another classification run is in progress — exiting",
              file=sys.stderr)
        return

    settings = get_settings()
    if not settings.ch_ready:
        print("[classify] COMPANIES_HOUSE_API_KEY is not set — skipping "
              "(add it to .env; free key from "
              "developer.company-information.service.gov.uk)",
              file=sys.stderr)
        return

    def progress(done, total):
        if done % PROGRESS_EVERY == 0 or done == total:
            print(f"[classify] {done}/{total} companies", file=sys.stderr)

    with get_conn() as conn, conn.cursor() as cur:
        report = run_classify(cur, settings, batch=args.batch,
                              commit=conn.commit, on_progress=progress)
        if not report.picked:
            # The daily top-up's usual night: skip the scoreboard aggregate too.
            print("[classify] no unclassified sponsors — census is current",
                  file=sys.stderr)
            return
        counts = classify_status_counts(cur, SOFTWARE_SIC)

    print(f"[classify] batch done: {report.picked} classified · "
          f"{report.matched} matched · {report.ambiguous} ambiguous · "
          f"{report.not_found} not found · {report.errors} errors",
          file=sys.stderr)
    print(f"[classify] register: {counts['classified']}/{counts['total_unique_orgs']} "
          f"classified · {counts['software_companies']} software companies · "
          f"{counts['remaining']} remaining", file=sys.stderr)


if __name__ == "__main__":
    main()
