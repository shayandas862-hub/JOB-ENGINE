"""Census tools — the census's four switches on the MCP server.

run_sweep (Pass 2 probing, optionally software-only/parallel) and
run_classification (Pass 1 registry classification) start their scripts
DETACHED and return immediately: both take hours, and an MCP call must not
hold a chat hostage — the same reason start_pipeline detaches, and the only
tool that still waits is preview_pipeline, whose dry run takes seconds.
Output goes to log files under ops/; progress questions go
to sweep_status / classify_status — pure reads over census_store, and reads
never audit. Nothing here returns a secret; the spawned scripts load their
own keys from .env like every runner. Each script holds its own lock, so a
double-start exits instantly (visible in the log).
"""
from __future__ import annotations

import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from fastmcp import FastMCP

from audit import record as _audit
from budget.gate import OWNER_ENV
from budget.ledger import SOURCES
from budget.ledger import remaining as _remaining
from discover.census_store import census_status_counts as _counts
from discover.census_store import classify_status_counts as _classify_counts
from discover.classify import SOFTWARE_SIC as _SOFTWARE_SIC
from mcp_server.annotations import READ, writes
from mcp_server.contract import with_next
from mcp_server.identity import current_owner as _owner
from mcp_server.session import scoped_conn as get_conn
from pipeline.trigger import python_executable

ROOT = Path(__file__).resolve().parents[2]
LOG_DIR = ROOT / "ops" / "sweep-logs"
CLASSIFY_LOG_DIR = ROOT / "ops" / "classify-logs"
_spawn = subprocess.Popen        # injection seam — tests never spawn anything


def _spawn_detached(log_dir: Path, stem: str, script: str, args: list[str],
                    owner=None) -> str:
    """Start a runner script detached, logging to a stamped file; return its path.

    `owner` is what makes a user-triggered run cost that user their own budget
    as well as the shared one (task 5). It travels as an environment variable
    because the spend can be two processes away — run.py spawns the stage that
    makes the call — and environment crosses both hops without anything being
    threaded through. Absent means the nightly world half, which owes nobody.
    """
    log_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    log_path = log_dir / f"{stem}-{stamp}.log"
    env = {**os.environ, "PYTHONPATH": "src"}
    if owner:
        env[OWNER_ENV] = str(owner)
    with open(log_path, "w") as log:
        _spawn([python_executable(), str(ROOT / "scripts" / script), *args],
               cwd=str(ROOT), stdout=log, stderr=subprocess.STDOUT,
               env=env, start_new_session=True)
    return str(log_path)


def register(mcp: FastMCP) -> None:
    """Hang the four census tools on the server."""

    @mcp.tool(annotations=writes(open_world=True))
    def run_sweep(batch_size: int = 500, owner_lens: bool = False,
                  workers: int = 1) -> dict:
        """What: start a census-sweep batch DETACHED and return immediately —
        it cards register organisations (job board? live roles?) at ~5s each,
        so a big batch takes hours. owner_lens probes only cards inside the
        owner's lens; workers parallelises that mode (keep 4-6).
        When: growing census coverage, especially after a new lens is set; a
        double-start exits instantly on the sweep lock.
        Returns: {started, batch_size, log_path} — progress lives in the log.
        Next: sweep_status to watch the scoreboard move."""
        args = ["--batch", str(batch_size)]
        if owner_lens:
            args += ["--owner-lens"]
            if workers > 1:
                args += ["--workers", str(workers)]
        with get_conn() as conn, conn.cursor() as cur:
            owner = _owner(cur)
        log_path = _spawn_detached(LOG_DIR, "sweep", "sweep.py", args,
                                   owner=owner)
        result = {"started": True, "batch_size": batch_size,
                  "owner_lens": owner_lens, "workers": workers,
                  "log_path": log_path}
        with get_conn() as conn, conn.cursor() as cur:
            _audit(cur, "run_sweep",
                   {"batch_size": batch_size, "owner_lens": owner_lens,
                    "workers": workers}, result)
        return with_next(result, state="sweep started detached",
                         call="sweep_status", why="watch the scoreboard move")

    @mcp.tool(annotations=READ)
    def sweep_status() -> dict:
        """What: the census scoreboard — organisations carded, outcomes (board
        found / no board / already tracked / error), jobs recorded with title
        matches, how many remain, plus today's API budget per source.
        When: after run_sweep, or judging census coverage. Read-only.
        Returns: the counts, and `budget` per source (spent/cap/remaining for
        you and for the world; resets at midnight UTC).
        Next: list_software_companies to browse the promotable lot."""
        with get_conn() as conn, conn.cursor() as cur:
            counts = _counts(cur)
            owner = _owner(cur)
            counts["budget"] = {source: _remaining(cur, source, owner)
                                for source in SOURCES}
        return with_next(counts,
                         state=f"{counts.get('total_carded', '?')} carded",
                         call="list_software_companies",
                         why="browse the promotable software lot")

    @mcp.tool(annotations=writes(open_world=True))
    def run_classification(batch_size: int = 5000) -> dict:
        """What: start a Pass-1 classification batch DETACHED — each register
        organisation is looked up on the national company registry (UK:
        Companies House) and stamped with official industry codes.
        When: register organisations still lack industry codes (rate-capped
        upstream ~2,300/hr). A double-start exits instantly on its lock.
        Returns: {started, batch_size, log_path}.
        Next: classify_status to watch the scoreboard."""
        with get_conn() as conn, conn.cursor() as cur:
            owner = _owner(cur)
        log_path = _spawn_detached(CLASSIFY_LOG_DIR, "classify",
                                   "classify_sponsors.py",
                                   ["--batch", str(batch_size)], owner=owner)
        result = {"started": True, "batch_size": batch_size,
                  "log_path": log_path}
        with get_conn() as conn, conn.cursor() as cur:
            _audit(cur, "run_classification", {"batch_size": batch_size}, result)
        return with_next(result, state="classification started detached",
                         call="classify_status", why="watch the scoreboard move")

    @mcp.tool(annotations=READ)
    def classify_status() -> dict:
        """What: the Pass-1 scoreboard — organisations classified against the
        national registry, outcomes, software count by code, how many remain.
        When: after run_classification, or judging Pass-1 coverage. Read-only.
        Returns: the counts.
        Next: sweep_status for the probing side of the census."""
        with get_conn() as conn, conn.cursor() as cur:
            counts = _classify_counts(cur, _SOFTWARE_SIC)
        return with_next(counts,
                         state=f"{counts.get('classified', '?')} classified",
                         call="sweep_status",
                         why="the probing side of the census scoreboard")
