"""Tests for src/applyqueue — the read-side queries that surface the ranked
apply queue, its skill gaps, and a single job's record.

These are the engine functions the MCP read tools wrap. All offline: a
FakeCursor records the SQL and serves canned rows, so we pin the query shape
(right view/table, right filter, right params) and confirm no secret column is
ever selected.

Phase 9 task 1b: every one of these now takes the owner it is answering for.
The owner is a REQUIRED positional argument, not a default — a default is how
the second user quietly reads the first user's queue. These offline tests pin
the shape; the proof that another owner is actually REFUSED is the two-owner
database test in tests/test_owner_scoping.py, because SQL text is not evidence.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pytest

from tests.conftest import FakeCursor

OWNER_A = "11111111-1111-4111-a111-111111111111"


def test_fetch_queue_selects_curated_columns_from_the_view_with_a_limit():
    from applyqueue import fetch_queue
    rows = [{"role_id": 917, "company_name": "Acme", "fit_rank": "High",
             "sponsor_signal": "role-confirmed", "salary_wall": "clears",
             "wall_basis": "going_rate:2134", "role_title": "AI Engineer",
             "salary_max": Decimal("54700"), "last_changed_at": datetime(2026, 7, 10, 9, 0),
             "deadline": date(2026, 7, 19)}]
    cur = FakeCursor(rows=rows)

    out = fetch_queue(cur, OWNER_A, limit=5)

    assert out == rows                      # rows pass straight through
    sql, params = cur.executed[0]
    low = sql.lower()
    assert "from v_apply_queue" in low      # wraps the ranked view, not raw tables
    assert "where owner_id = %s" in low     # one owner's queue, never everyone's
    assert "limit %s" in low
    assert "select *" not in low            # curated columns, never *
    for col in ("role_id", "sponsor_signal", "salary_wall", "wall_basis", "fit_rank"):
        assert col in low                   # the columns needed to explain a ranking
    assert params == (OWNER_A, 5)


def test_fetch_queue_defaults_to_a_sensible_limit():
    from applyqueue import fetch_queue
    cur = FakeCursor(rows=[])
    fetch_queue(cur, OWNER_A)
    assert cur.executed[0][1] == (OWNER_A, 20)


def test_fetch_skill_gaps_returns_only_missing_skills_ranked_by_demand():
    from applyqueue import fetch_skill_gaps
    rows = [{"skill": "Kubernetes", "skill_type": "tool", "demand": 12, "my_level": None}]
    cur = FakeCursor(rows=rows)

    out = fetch_skill_gaps(cur, OWNER_A, limit=10)

    assert out == rows
    sql, params = cur.executed[0]
    low = sql.lower()
    assert "from v_skill_gap" in low
    assert "owner_id = %s" in low           # 0051 gave the view an owner; use it
    assert "i_have_it = false" in low       # gaps only — skills I already have are excluded
    assert "order by demand desc" in low    # most-wanted first
    assert params == (OWNER_A, 10)


def test_fetch_job_returns_one_row_by_id_and_never_selects_a_secret():
    from applyqueue import fetch_job
    rows = [{"role_id": 917, "company_name": "Acme", "role_title": "AI Engineer",
             "role_url": "https://x/y", "salary_max": Decimal("54700"),
             "jd_full": "…", "role_status": "open", "application_status": "not_applied"}]
    cur = FakeCursor(rows=rows)

    out = fetch_job(cur, OWNER_A, 917)

    assert out == rows[0]
    sql, params = cur.executed[0]
    low = sql.lower()
    assert "from role_listings" in low
    assert "r.role_id = %s" in low
    assert "c.owner_id = %s" in low         # the seam: role_listings has no owner of its own
    assert "select *" not in low
    assert "ats_token" not in low           # the ATS secret lives on target_companies — never selected
    assert params == (917, OWNER_A)


def test_fetch_job_returns_none_when_the_role_does_not_exist():
    from applyqueue import fetch_job
    assert fetch_job(FakeCursor(rows=[]), OWNER_A, 999) is None


# ---- apply-queue actions (Phase 5: mark_applied / snooze_listing tools) ----

def test_mark_applied_stamps_status_and_date_and_returns_the_title():
    from applyqueue import mark_applied
    cur = FakeCursor(rows=[{"role_title": "AI Engineer"}])

    title = mark_applied(cur, OWNER_A, 917)

    assert title == "AI Engineer"
    sql, params = cur.executed[0]
    low = sql.lower()
    assert "update role_listings" in low
    assert "application_status='applied'" in low.replace(" ", "")
    assert "applied_date=current_date" in low.replace(" ", "")
    assert "target_companies" in low        # the write reaches the owner the same way the read does
    assert "c.owner_id = %s" in low
    assert params == (917, OWNER_A)


def test_mark_applied_returns_none_for_an_unknown_role():
    from applyqueue import mark_applied
    assert mark_applied(FakeCursor(rows=[]), OWNER_A, 999) is None


def test_snooze_listing_suppresses_future_nudges_and_returns_the_title():
    from applyqueue import snooze_listing
    cur = FakeCursor(rows=[{"role_title": "AI Engineer"}])

    title = snooze_listing(cur, OWNER_A, 917)

    assert title == "AI Engineer"
    sql, params = cur.executed[0]
    low = sql.lower()
    assert "update role_listings" in low
    assert "nudged_at = now()" in low       # reuse the existing never-re-nudge stamp
    assert "c.owner_id = %s" in low
    assert params == (917, OWNER_A)


def test_snooze_listing_returns_none_for_an_unknown_role():
    from applyqueue import snooze_listing
    assert snooze_listing(FakeCursor(rows=[]), OWNER_A, 999) is None


# ---- the owner is required, not defaulted --------------------------------

@pytest.mark.parametrize("name,old_call", [
    ("fetch_queue", {"limit": 5}),
    ("fetch_skill_gaps", {"limit": 10}),
    ("fetch_job", {"role_id": 917}),
    ("mark_applied", {"role_id": 917}),
    ("snooze_listing", {"role_id": 917}),
])
def test_no_query_here_can_be_called_the_old_ownerless_way(name, old_call):
    # The whole point of task 1b. A default owner would make every call site
    # silently correct for user one and silently wrong for user two, with
    # nothing failing. So each function is called EXACTLY as Phase 8.5 called
    # it — cursor plus its own argument, no owner — and that must now be a
    # TypeError. Keyword arguments, deliberately: passing 917 positionally
    # would bind it to owner_id and prove nothing. This assertion fails
    # against the pre-1b source, which is what makes it a guard rather than a
    # description.
    import applyqueue
    fn = getattr(applyqueue, name)
    with pytest.raises(TypeError):
        fn(FakeCursor(rows=[]), **old_call)
