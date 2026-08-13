"""Trigger a pipeline run on demand by shelling the SAME scripts/run.py the
scheduler uses — never a forked second pipeline path.

run.py owns the run lock (a manual run while the daily run holds the flock
declines cleanly) and the --dry-run behaviour (preview only: no sends, stamps,
or report). Two entry points, split by how long they take:

  preview_pipeline()  dry run, seconds  -> waits, returns the output tail
  start_pipeline()    real run, ~12 min -> detaches, returns a log path

The subprocess runner/spawner is injectable so tests never spawn.
"""
from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from budget.gate import OWNER_ENV

ROOT = Path(__file__).resolve().parents[2]
RUN_LOG_DIR = ROOT / "ops" / "run-logs"


def python_executable(root: Path = ROOT) -> str:
    """Interpreter for spawned runners: the repo venv when present (the laptop,
    same one the scheduler uses), else whatever runs this process.

    Mirrors scripts/run.py's _python. The image has no .venv, so a hardcoded
    path here is a FileNotFoundError for every tool that spawns a script.
    """
    venv = root / ".venv" / "bin" / "python"
    return str(venv) if venv.exists() else sys.executable


def trigger_pipeline(dry_run: bool = False, runner=subprocess.run) -> dict:
    """Run scripts/run.py (optionally --dry-run) and return its outcome."""
    cmd = [python_executable(), str(ROOT / "scripts" / "run.py")]
    if dry_run:
        cmd.append("--dry-run")
    proc = runner(
        cmd,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": "src"},
    )
    output = ((proc.stderr or "") + (proc.stdout or "")).strip()
    summary = "\n".join(output.splitlines()[-15:])
    return {"dry_run": dry_run, "returncode": proc.returncode, "summary": summary}


def preview_pipeline(runner=subprocess.run) -> dict:
    """Preview tonight's digest SYNCHRONOUSLY — run.py --dry-run takes seconds
    (no fetches, sends, stamps, or report), so a caller can afford to wait."""
    return trigger_pipeline(dry_run=True, runner=runner)


def start_pipeline(spawn=subprocess.Popen, log_dir: Path | None = None,
                   owner=None) -> dict:
    """Start a REAL run DETACHED and return immediately; output goes to a
    stamped log file.

    A full run takes ~12 minutes. Hosted behind Cloud Run's 300s request
    timeout, waiting for it is a guaranteed 504 — so this never waits, and
    never pipes (a pipe would make the caller block on the reader too).
    run.py owns the run lock, so a double-start exits cleanly in the log.

    LIMIT, for Phase 8 task 3: detaching solves the 504, but a subprocess
    spawned inside a Cloud Run *service* is not durable — CPU is throttled
    once the response is sent, and the instance is reclaimed when it scales
    to zero, either of which kills the run mid-flight. Hosted, this should
    execute the existing `goal-a-daily` Cloud Run *Job* through the Jobs API
    instead of spawning locally. Correct as-is for stdio/local use.

    `owner` (task 5) is who pays. A run somebody ASKED for spends their API
    budget as well as the shared one; the scheduler's own 06:30 run passes
    nobody and spends only the world's. It rides the environment because the
    calls happen a further process down — run.py spawns each stage.
    """
    log_dir = log_dir or RUN_LOG_DIR
    log_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    log_path = log_dir / f"run-{stamp}.log"
    env = {**os.environ, "PYTHONPATH": "src"}
    if owner:
        env[OWNER_ENV] = str(owner)
    with open(log_path, "w") as log:
        spawn([python_executable(), str(ROOT / "scripts" / "run.py")],
              cwd=str(ROOT), stdout=log, stderr=subprocess.STDOUT,
              env=env, start_new_session=True)
    return {"started": True, "log_path": str(log_path)}
