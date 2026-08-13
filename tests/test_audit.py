"""Tests for src/audit — one mcp_audit row per action; arg/result summaries only."""
from __future__ import annotations

import json
from datetime import date

from tests.conftest import FakeCursor


def test_record_inserts_an_audit_row_with_tool_args_and_result():
    from audit import record
    cur = FakeCursor()

    record(cur, "mark_applied", {"role_id": 917}, {"applied": True})

    sql, params = cur.executed[0]
    assert "insert into mcp_audit" in sql.lower()
    assert params[0] == "mark_applied"
    assert json.loads(params[1]) == {"role_id": 917}
    assert json.loads(params[2]) == {"applied": True}


def test_record_handles_none_args_and_result():
    from audit import record
    cur = FakeCursor()
    record(cur, "send_test_nudge", None, None)
    params = cur.executed[0][1]
    assert params[0] == "send_test_nudge"
    assert params[1] is None and params[2] is None


def test_record_serialises_stray_non_json_values_without_raising():
    from audit import record
    cur = FakeCursor()
    record(cur, "x", {"when": date(2026, 7, 11)}, None)   # default=str keeps it safe
    assert "2026-07-11" in cur.executed[0][1][1]
