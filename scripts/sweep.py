#!/usr/bin/env python3
"""Run one census-sweep batch: card the next N register organisations.

Usage:
    PYTHONPATH=src .venv/bin/python scripts/sweep.py [--batch N] [--pause S]
                                                     [--retry-errors] [--probe-only]
                                                     [--owner-lens [--workers N]]

--owner-lens is Pass 2 of the census: probe ONLY the cards Pass 1 matched
inside the owner's lens (registry-matched + THEIR promotion rule's industry
codes, never probed), active first — a rule-less database falls back to the
software bootstrap set. --software-only is the old spelling of the same
switch, kept as an alias. --workers N (owner-lens/hiring mode only) probes
with N parallel workers, each on its own connection, per-org commit kept.

Takes its OWN lock (.sweep.lock) so a sweep and the daily pipeline can run side
by side while two sweeps cannot. Per-item errors are recorded on the org's
census card and never fail the run; only a whole-run failure (lost DB
connection) exits non-zero. Progress and totals go to stderr.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROGRESS_EVERY = 25


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description="Run one census-sweep batch.")
    ap.add_argument("--batch", type=int, default=2000,
                    help="organisations to process this run (default 2000)")
    ap.add_argument("--pause", type=float, default=0.3,
                    help="polite pause between organisations, seconds (default 0.3)")
    ap.add_argument("--retry-errors", action="store_true",
                    help="re-process previously errored census cards instead")
    ap.add_argument("--probe-only", action="store_true",
                    help="skip registry enrichment even when the key is set")
    ap.add_argument("--owner-lens", "--software-only", dest="owner_lens",
                    action="store_true",
                    help="Pass 2: probe only registry-matched cards inside "
                         "the owner's lens (their rule's industry codes; "
                         "--software-only is the old spelling)")
    ap.add_argument("--hiring", action="store_true",
                    help="probe sponsors that aggregator ads prove are hiring "
                         "(never-probed first, busiest hirers first)")
    ap.add_argument("--workers", type=int, default=1,
                    help="parallel probe workers (owner-lens/hiring; default 1)")
    args = ap.parse_args(argv)
    if args.workers != 1 and not (args.owner_lens or args.hiring):
        ap.error("--workers requires --owner-lens or --hiring")
    if args.owner_lens and args.hiring:
        ap.error("--owner-lens and --hiring pick different batches")
    return args


def main(argv=None) -> None:
    args = parse_args(argv)
    from config import get_settings
    from db.connection import get_conn
    from discover.census_store import census_status_counts
    from discover.sweep import run_sweep
    from pipeline.lock import acquire_lock

    lock = acquire_lock(ROOT / ".sweep.lock")   # held for the whole run
    if lock is None:
        print("[sweep] another sweep is in progress — exiting", file=sys.stderr)
        return

    settings = get_settings()

    def progress(done, total):
        if done % PROGRESS_EVERY == 0 or done == total:
            print(f"[sweep] {done}/{total} orgs", file=sys.stderr)

    picker = None
    if args.hiring:
        from discover.probe_pick import pick_hiring_batch
        picker = pick_hiring_batch
    mode = "hiring-first" if args.hiring else "owner-lens"

    if (args.owner_lens or args.hiring) and args.workers > 1:
        from discover.probe_pick import run_lens_sweep_parallel
        print(f"[sweep] {mode} mode · {args.workers} workers", file=sys.stderr)
        report = run_lens_sweep_parallel(
            get_conn, settings, batch=args.batch, workers=args.workers,
            pause=args.pause, on_progress=progress, picker=picker)
        with get_conn() as conn, conn.cursor() as cur:
            counts = census_status_counts(cur)
    elif args.owner_lens or args.hiring:
        from discover.probe_pick import run_lens_sweep
        print(f"[sweep] {mode} mode", file=sys.stderr)
        with get_conn() as conn, conn.cursor() as cur:
            report = run_lens_sweep(cur, settings, batch=args.batch,
                                        pause=args.pause, commit=conn.commit,
                                        on_progress=progress, picker=picker)
            counts = census_status_counts(cur)
    else:
        with get_conn() as conn, conn.cursor() as cur:
            report = run_sweep(cur, settings, batch=args.batch, pause=args.pause,
                               retry_errors=args.retry_errors,
                               probe_only=args.probe_only,
                               commit=conn.commit, on_progress=progress)
            counts = census_status_counts(cur)

    print(f"[sweep] batch done: {report.picked} picked · "
          f"{report.boards_found} boards found · {report.no_board} no board · "
          f"{report.already_tracked} already tracked · {report.errors} errors · "
          f"{report.jobs_stored} jobs stored "
          f"({report.title_matches} title matches)", file=sys.stderr)
    print(f"[sweep] census: {counts['probed']}/{counts['total_unique_orgs']} "
          f"censused · {counts['boards_found']} boards · "
          f"{counts['census_jobs']} jobs · {counts['remaining']} remaining",
          file=sys.stderr)


if __name__ == "__main__":
    main()
