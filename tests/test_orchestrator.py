"""Tests for the pipeline orchestrator — sequencing, failure isolation, reporting."""
from __future__ import annotations

import pytest

from tests.conftest import FakeCursor


def ok_stage(msg):
    return lambda: msg


def boom_stage(msg):
    def run():
        raise RuntimeError(msg)
    return run


def test_stages_run_in_order_and_all_results_are_captured():
    from pipeline.orchestrator import run_stages
    calls = []
    stages = [
        ("fetch", lambda: calls.append("fetch") or "756 jobs"),
        ("read", lambda: calls.append("read") or "11 roles"),
        ("salary", lambda: calls.append("salary") or "4 set"),
    ]
    results = run_stages(stages)
    assert calls == ["fetch", "read", "salary"]
    assert [r.name for r in results] == ["fetch", "read", "salary"]
    assert all(r.ok for r in results)
    assert results[0].summary == "756 jobs"
    assert all(r.duration_s >= 0 for r in results)


def test_a_failing_stage_is_recorded_and_later_stages_still_run():
    from pipeline.orchestrator import failed_stages, run_stages
    ran = []
    stages = [
        ("fetch", lambda: ran.append("fetch") or "ok"),
        ("read", boom_stage("exit 1: quota blown")),
        ("salary", lambda: ran.append("salary") or "ok"),
    ]
    results = run_stages(stages)
    assert ran == ["fetch", "salary"]              # failure never stops the loop
    assert [r.ok for r in results] == [True, False, True]
    assert "quota blown" in results[1].summary
    assert failed_stages(results) == ["read"]


def test_on_result_callback_fires_per_stage():
    from pipeline.orchestrator import run_stages
    seen = []
    run_stages([("a", ok_stage("x")), ("b", boom_stage("y"))],
               on_result=lambda r: seen.append((r.name, r.ok)))
    assert seen == [("a", True), ("b", False)]


def test_run_report_start_and_finish():
    from pipeline.orchestrator import StageResult
    from pipeline.report import finish_run, start_run
    cur = FakeCursor(rows=[{"run_id": 7}])
    assert start_run(cur) == 7
    sql, _ = cur.executed[0]
    assert "pipeline_runs" in sql and "returning run_id" in sql.lower()

    cur2 = FakeCursor()
    results = [StageResult("fetch", True, "756 jobs", 12.3),
               StageResult("read", False, "exit 1", 0.4)]
    finish_run(cur2, 7, results)
    sql, params = cur2.executed[0]
    assert "status" in sql and params[0] == "failed"       # any failure -> failed
    assert "fetch" in params[1] and "exit 1" in params[1]  # stages as JSON
    assert params[-1] == 7

    cur3 = FakeCursor()
    finish_run(cur3, 8, [StageResult("fetch", True, "ok", 1.0)])
    assert cur3.executed[0][1][0] == "ok"


# ---- reading run reports (Phase 5: the MCP get_run_report tool) ----

def test_latest_run_reads_the_most_recent_pipeline_run():
    from pipeline.report import latest_run
    cur = FakeCursor(rows=[{"run_id": 7, "status": "ok", "started_at": "…",
                            "finished_at": "…", "stages": [{"name": "fetch", "ok": True}]}])
    out = latest_run(cur)
    assert out["run_id"] == 7 and out["status"] == "ok"
    sql = cur.executed[0][0].lower()
    assert "from pipeline_runs" in sql
    assert "order by run_id desc" in sql and "limit 1" in sql


def test_latest_run_returns_none_when_no_runs_exist():
    from pipeline.report import latest_run
    assert latest_run(FakeCursor(rows=[])) is None


def test_run_report_reads_a_specific_run_by_id():
    from pipeline.report import run_report
    cur = FakeCursor(rows=[{"run_id": 3, "status": "failed", "stages": []}])
    out = run_report(cur, 3)
    assert out["run_id"] == 3 and out["status"] == "failed"
    sql, params = cur.executed[0]
    assert "from pipeline_runs" in sql.lower() and "run_id = %s" in sql.lower()
    assert params == (3,)


def test_run_report_returns_none_when_the_run_is_absent():
    from pipeline.report import run_report
    assert run_report(FakeCursor(rows=[]), 999) is None
