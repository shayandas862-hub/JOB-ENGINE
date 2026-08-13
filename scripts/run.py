"""The daily pipeline, one command:

    python scripts/run.py            # discover -> fetch -> read -> synonyms -> salary -> deadlines -> eval -> file -> nudge
    python scripts/run.py --dry-run  # preview the nudge digest: no sends, no stamps, no report

Each stage runs as its own process (they print their own counts to stderr; the
tail becomes the stage summary in pipeline_runs). One failing stage never stops
the loop, and the run report records exactly what happened.

Since Phase 9 task 3 the night has two halves. The **world** half — register,
classify, discover, fetch, read, synonyms, merge, jd_drip — runs ONCE: it is
the expensive data and it is shared, so a second owner costs nothing there.
The **personal** half then loops per owner, each with their own rule, window,
tray, board and phone. One owner's failure is recorded against that owner and
the loop moves on to the next; it never ends anyone else's night.

The owners this process handles come from `pipeline.owners.task_shard()`,
which reads Cloud Run's `CLOUD_RUN_TASK_INDEX` / `CLOUD_RUN_TASK_COUNT` and
falls back to 0 of 1. Tonight that is every owner, serially, exactly as
before. Raising the job's `taskCount` fans the same code out with no edit.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _python(root: Path = ROOT) -> str:
    """Interpreter for stage subprocesses: the repo venv when present (the
    laptop), else whatever runs this script (the container has no venv)."""
    venv = root / ".venv" / "bin" / "python"
    return str(venv) if venv.exists() else sys.executable


PY = _python()

sys.path.insert(0, str(ROOT / "src"))

from pipeline.orchestrator import failed_stages, run_stages  # noqa: E402
from pipeline.owners import (PERSONAL_STAGES, list_owner_ids,  # noqa: E402
                             personal_stage_cmd, shard_owners, task_shard)
from pipeline.report import finish_run, start_run            # noqa: E402

# Grounding-eval gate: below this share of verbatim-grounded skills, the
# reading stage is considered broken (decision-log 2026-07-10).
EVAL_MIN = "0.60"

STAGE_CMDS = [
    # The register refreshes itself weekly (skips fast when fresh) so sieve 1
    # never goes stale — before discovery, which leans on it.
    ("register",  ["scripts/refresh_register.py", "--if-stale", "7"]),
    # The refresh leaves newcomers with blank census cards; classify them the
    # same night so nothing waits on a human. Capped because Companies House
    # paces at 0.6 s/company: 2000 is ~20 min worst case (a week's newcomers
    # are ~1,800) and seconds on the six nights the census is already current.
    ("classify",  ["scripts/classify_sponsors.py", "--batch", "2000"]),
    # Discovery runs first so companies found today are fetched the same run.
    # (discover_companies.py, not discover.py: a scripts/discover.py module
    #  shadows the src/discover package on sys.path and breaks its own imports.)
    ("discover",  ["scripts/discover_companies.py"]),
    ("fetch",     ["scripts/fetch_jobs.py"]),
    ("read",      ["scripts/extract_skills.py"]),
    ("synonyms",  ["scripts/build_synonyms.py"]),
    # Phase 7.8: matched ads join the queue, then the owner's rule promotes
    # census cards — both before salary/deadlines so new rows get enriched
    # the same night.
    ("merge",     ["scripts/merge_ads.py"]),
    # Phase 8.5 / U5: freshly merged ad rows gain their full JD the same
    # night (Reed details, shared 950/day ledger), so salary/deadlines/tray
    # can enrich them in the stages below.
    ("jd_drip",   ["scripts/jd_drip.py"]),
    ("promote",   ["scripts/promote_by_rule.py"]),
    ("salary",    ["scripts/enrich_salary.py"]),
    ("deadlines", ["scripts/enrich_deadlines.py"]),
    ("eval",      ["scripts/eval_extraction.py", "--min", EVAL_MIN]),
    # Sieve-3: whatever the keyword read could only do crudely is staged for
    # a user's AI to read properly over MCP. The run never waits on it.
    ("stage_reading", ["scripts/stage_reading.py"]),
    # Filing runs after eval, before the nudge: CV + Notion card per gated listing.
    ("file",      ["scripts/file_applications.py"]),
]


def _subprocess_stage(args: list[str]):
    def run() -> str:
        proc = subprocess.run(
            [PY, *args],
            cwd=ROOT, capture_output=True, text=True,
            env={**os.environ, "PYTHONPATH": "src"},
        )
        tail = (proc.stderr or "").strip()
        print(tail, file=sys.stderr)
        if proc.returncode != 0:
            raise RuntimeError(f"exit {proc.returncode}: {tail[-300:]}")
        return tail[-300:]
    return run


def build_stages(owners: list[str] | None = None):
    """The night's stage list: world work once, then the personal pass per owner.

    Returns 3-tuples `(name, callable, owner)` for personal stages and
    2-tuples for world stages, which is what `run_stages` and the report fold
    read. With one owner this is the same fifteen stages in the same pinned
    order as before task 3 — the loop is simply one iteration long.
    """
    stages = [(name, _subprocess_stage(cmd)) for name, cmd in STAGE_CMDS
              if name not in PERSONAL_STAGES]
    personal = [(name, cmd) for name, cmd in STAGE_CMDS if name in PERSONAL_STAGES]
    for owner in (owners or []):
        stages += [(name, _subprocess_stage(personal_stage_cmd(cmd, owner)), owner)
                   for name, cmd in personal]
    return stages


def main() -> None:
    from criteria.loader import default_profile_id
    from db.connection import get_conn
    from notify.nudges import nudge_stage
    from notify.push import notify_failure, send_push
    from pipeline.lock import acquire_lock

    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="preview the nudge digest only; no sends, stamps, or report")
    args = ap.parse_args()

    index, count = task_shard()

    if args.dry_run:
        with get_conn() as conn, conn.cursor() as cur:
            for owner in shard_owners(list_owner_ids(cur), index, count):
                print(f"--- owner {owner} ---", file=sys.stderr)
                print(nudge_stage(cur, send=None, owner_id=owner, dry_run=True),
                      file=sys.stderr)
        return

    lock = acquire_lock(ROOT / ".run.lock")
    if lock is None:
        print("another pipeline run is in progress — exiting", file=sys.stderr)
        return

    from config import get_settings
    settings = get_settings()

    with get_conn() as conn:
        with conn.cursor() as cur:
            owners = shard_owners(list_owner_ids(cur), index, count)
            # The single Notion credential opens one person's board, so the
            # footer belongs to that owner alone — the filing stage refuses
            # for anyone else for the same reason (B-GAE-027).
            notion_owner = default_profile_id(cur) if settings.notion_ready else None
        if not owners:
            print(f"task {index}/{count} has no owners to run", file=sys.stderr)
            return

        # The operator's map from the report's owner numbers back to profiles.
        # It lives here, in the run's own stderr, and NOT in pipeline_runs:
        # that table is world-readable and a profile_id is the exact value a
        # cross-owner read attempt needs.
        for seq, owner in enumerate(owners, start=1):
            print(f"[owner {seq}] {owner}", file=sys.stderr)

        def _nudge_for(owner: str):
            def run() -> str:
                footer = (
                    "→ Applications board: https://www.notion.so/"
                    f"{settings.notion_database_id.replace('-', '')}"
                    if owner == notion_owner else "")
                with conn.cursor() as cur:
                    out = nudge_stage(cur, send=send_push, owner_id=owner,
                                      footer=footer)
                conn.commit()   # stamps survive even if reporting later fails
                return out
            return run

        stages = build_stages(owners)
        stages += [("nudge", _nudge_for(owner), owner) for owner in owners]

        with conn.cursor() as cur:
            run_id = start_run(cur)
        conn.commit()   # the run row survives whatever happens next

        seq_of = {owner: n for n, owner in enumerate(owners, start=1)}
        results = run_stages(stages,
                             on_result=lambda r: print(
                                 f"[stage] {r.name}"
                                 f"{f' (owner {seq_of[r.owner]})' if r.owner else ''}"
                                 f": {'ok' if r.ok else 'FAILED'} "
                                 f"({r.duration_s}s)", file=sys.stderr))

        failed = failed_stages(results)
        if failed:  # a broken run must never be silent
            with conn.cursor() as cur:
                notify_failure(cur, failed)

        with conn.cursor() as cur:
            finish_run(cur, run_id, results)

    broken = {(r.name, seq_of.get(r.owner)) for r in results if not r.ok}
    print(f"\nRun {run_id}: {len(owners)} owner(s), "
          f"{'FAILED: ' + ', '.join(sorted(f'{n}' + (f'[owner {s}]' if s else '') for n, s in broken)) if failed else 'all stages ok'}",
          file=sys.stderr)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
