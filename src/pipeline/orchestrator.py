"""Run pipeline stages in order; one failure never stops the loop."""
from __future__ import annotations

import time
from dataclasses import dataclass

SUMMARY_MAX = 500   # stage summaries are tails, not transcripts


@dataclass(frozen=True)
class StageResult:
    name: str
    ok: bool
    summary: str
    duration_s: float
    # Which owner this run of the stage was for, or None for world work.
    # Defaulted so every existing 2-tuple caller is untouched (Phase 9 task 3).
    owner: str | None = None


def run_stages(stages, on_result=None) -> list[StageResult]:
    """stages: [(name, callable)] or [(name, callable, owner)]. A callable
    returns a summary string on success and raises on failure. Failures are
    recorded and the remaining stages still run — the daily loop degrades, it
    never silently dies.

    Since Phase 9 task 3 the same stage NAME may appear more than once, once
    per owner. Isolation is unchanged and that is the point: one owner's
    failed promote costs neither that owner the rest of their pass, nor any
    other owner theirs. `pipeline.report.finish_run` folds the repeats back
    into one array element per name.
    """
    results: list[StageResult] = []
    for stage in stages:
        name, fn, owner = (*stage, None)[:3]
        t0 = time.monotonic()
        try:
            summary = str(fn() or "")
            result = StageResult(name, True, summary[-SUMMARY_MAX:],
                                 round(time.monotonic() - t0, 1), owner)
        except Exception as err:
            result = StageResult(name, False, str(err)[-SUMMARY_MAX:],
                                 round(time.monotonic() - t0, 1), owner)
        results.append(result)
        if on_result:
            on_result(result)
    return results


def failed_stages(results: list[StageResult]) -> list[str]:
    """The names of the stages that failed, each named once.

    Deduped because a personal stage runs once per owner since task 3, and an
    alert that says "promote, promote, promote" is noise rather than detail —
    which owner it failed for is in the run report's per-owner lines.
    """
    return list(dict.fromkeys(r.name for r in results if not r.ok))
