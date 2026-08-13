"""Tests for src/brief.py — the daily agenda assembly (engine-side, no skin).

The brief is the number the phase exists to move (applications) plus what to
do next: today's queue top, the reading tray depth, open reviews, last run.
Pure reads; the MCP daily_brief tool is a skin over exactly this.
"""
from __future__ import annotations

from brief import assemble_brief

from tests.conftest import ScriptedCursor

OWNER = "00000000-0000-4000-a000-000000000001"


def _cursor():
    return ScriptedCursor([
        ("application_status = 'applied'",
         [[{"applied_total": 3, "applied_today": 1}]]),
        ("from v_apply_queue", [[{"role_id": 1, "company_name": "Acme",
                                  "fit_rank": "High"}]]),
        ("staged_at is not null", [[{"n": 14}]]),
        ("group by kind", [[{"kind": "promotion_review", "n": 2}]]),
        ("from pipeline_runs", [[{"run_id": 9, "status": "ok",
                                  "stages": []}]]),
    ])


def test_brief_carries_the_numbers_that_matter():
    brief = assemble_brief(_cursor(), OWNER)
    assert brief["applications"] == {"total": 3, "today": 1}
    assert brief["queue_top"][0]["company_name"] == "Acme"
    assert brief["to_read"] == 14
    assert brief["reviews_open"] == [{"kind": "promotion_review", "n": 2}]
    assert brief["last_run"]["run_id"] == 9


def test_brief_is_owner_scoped():
    cur = _cursor()
    assemble_brief(cur, OWNER)
    applied_sql, applied_params = [
        (s, p) for s, p in cur.executed
        if "application_status = 'applied'" in s][0]
    assert "owner_id" in applied_sql
    assert OWNER in applied_params


def test_brief_survives_an_empty_engine():
    cur = ScriptedCursor([("never-matches", [[]])])
    brief = assemble_brief(cur, OWNER)
    assert brief["applications"] == {"total": 0, "today": 0}
    assert brief["queue_top"] == []
    assert brief["to_read"] == 0
    assert brief["reviews_open"] == []
    assert brief["last_run"] is None


# ---- lens coverage in the brief (Phase 8.5 / U4) ---------------------------

def test_brief_carries_the_honest_doors_line_for_the_lens():
    # A fresh lens must hear "your industry's doors are still being knocked
    # — N of M done", so the coverage rides in the brief payload.
    cur = ScriptedCursor([
        ("application_status = 'applied'",
         [[{"applied_total": 0, "applied_today": 0}]]),
        ("from v_apply_queue", [[]]),
        ("staged_at is not null", [[{"n": 0}]]),
        ("group by kind", [[]]),
        ("from pipeline_runs", [[]]),
        ("from promotion_rules", [[{"industry_codes": ["87300"],
                                    "min_local_jobs": 1, "auto": True,
                                    "adzuna_category": None}]]),
        ("from sponsor_census", [[{"knocked": 43, "total": 6261}]]),
    ])
    brief = assemble_brief(cur, OWNER)
    assert brief["lens_coverage"] == {"knocked": 43, "total": 6261,
                                      "pct": 0.7}


def test_brief_lens_coverage_is_none_without_a_rule():
    brief = assemble_brief(_cursor(), OWNER)   # no promotion_rules route
    assert brief["lens_coverage"] is None
