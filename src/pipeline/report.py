"""Persist each daily run's story in pipeline_runs."""
from __future__ import annotations

import json


def start_run(cur) -> int:
    cur.execute(
        "insert into pipeline_runs (status) values ('running') returning run_id")
    return cur.fetchone()["run_id"]


def fold_stages(results) -> list[dict]:
    """N owners' stage results back into ONE object per stage name.

    Since Phase 9 task 3 a personal stage runs once per owner, so `results`
    can hold `promote` three times. This folds the repeats back down, and the
    reason it folds rather than appending is a consumer: `v_status_stages`
    counts `jsonb_array_elements(stages)` and the public status page renders
    the answer as "15 of 15 stages". Extra array elements would quietly turn
    that into 29 of 29 on a page the founder points other people at.

    So per-owner detail rides as an added FIELD on the existing object. The
    four fields that were always there keep their names and their meanings —
    `ok` is still "did this stage succeed", now across every owner it ran for.

    Owners are numbered, never named. `pipeline_runs` is world-readable (any
    key holder can call `get_run_report`), and a profile_id in there would
    hand out the exact value needed to attempt a cross-owner read. The
    seq -> owner mapping is printed to the run's own stderr, which is the
    operator's log and nobody else's.
    """
    order: list[str] = []
    runs: dict[str, list] = {}
    seq: dict[str, int] = {}
    for r in results:
        if r.name not in runs:
            runs[r.name] = []
            order.append(r.name)
        runs[r.name].append(r)
        owner = getattr(r, "owner", None)
        if owner is not None and owner not in seq:
            seq[owner] = len(seq) + 1

    stages = []
    for name in order:
        group = runs[name]
        failed = [r for r in group if not r.ok]
        # One run — a world stage, or a single-owner night — keeps its summary
        # verbatim, so the founder's report reads exactly as it did before
        # this existed.
        summary = group[0].summary if len(group) == 1 else (
            f"{len(group)} owners: {len(group) - len(failed)} ok, "
            f"{len(failed)} failed")
        stage = {
            "name": name,
            "ok": not failed,
            "summary": summary,
            "duration_s": round(sum(r.duration_s for r in group), 1),
        }
        if any(getattr(r, "owner", None) is not None for r in group):
            stage["owners"] = [
                {"seq": seq[r.owner], "ok": r.ok, "summary": r.summary,
                 "duration_s": r.duration_s}
                for r in group
            ]
        stages.append(stage)
    return stages


def finish_run(cur, run_id: int, results) -> None:
    """Stamp the run finished: 'ok' only when every stage succeeded."""
    status = "ok" if all(r.ok for r in results) else "failed"
    cur.execute(
        "update pipeline_runs set finished_at=now(), status=%s, stages=%s "
        "where run_id=%s",
        (status, json.dumps(fold_stages(results)), run_id))


_RUN_COLS = "run_id, started_at, finished_at, status, stages"


def latest_run(cur) -> dict | None:
    """The most recent daily run's report card, or None if none have run."""
    cur.execute(f"select {_RUN_COLS} from pipeline_runs order by run_id desc limit 1")
    return cur.fetchone()


def run_report(cur, run_id: int) -> dict | None:
    """One run's report card by id, or None if the run is unknown."""
    cur.execute(f"select {_RUN_COLS} from pipeline_runs where run_id = %s", (run_id,))
    return cur.fetchone()
