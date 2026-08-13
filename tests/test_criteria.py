"""Tests for src/criteria — the profile's criteria loaded from the DB, never code."""
from __future__ import annotations

import os

import pytest

_DB_ONLY = pytest.mark.skipif(
    os.getenv("RUN_DB_TESTS") != "1",
    reason="DB integration tests are opt-in: RUN_DB_TESTS=1")


class RoutingCursor:
    """Fake cursor that answers each query from a routing table by substring."""

    def __init__(self, routes):
        self.routes = routes            # list of (substring, rows)
        self.executed = []
        self._pending = []

    def execute(self, sql, params=None):
        squashed = " ".join(sql.split()).lower()
        self.executed.append((squashed, params))
        for marker, rows in self.routes:
            if marker in squashed:
                self._pending = list(rows)
                return
        self._pending = []

    def fetchall(self):
        return list(self._pending)

    def fetchone(self):
        return self._pending[0] if self._pending else None


PROFILE_ROW = {"profile_id": "p-1", "name": "Test Person"}
CONSTRAINT_ROWS = [
    {"kind": "salary_floor", "value": None, "numeric_value": 30000},
    {"kind": "salary_threshold_standard", "value": None, "numeric_value": 41700},
    {"kind": "salary_threshold_new_entrant", "value": None, "numeric_value": 30960},
    {"kind": "kill_keyword", "value": "audit", "numeric_value": None},
    {"kind": "kill_keyword", "value": "compliance", "numeric_value": None},
]
ROLE_ROWS = [
    {"search_title": "Solutions Engineer"},
    {"search_title": "Forward Deployed Engineer"},
]


def make_cursor():
    return RoutingCursor([
        ("from profiles", [PROFILE_ROW]),
        ("from my_constraints", CONSTRAINT_ROWS),
        ("from target_roles", ROLE_ROWS),
    ])


def test_load_criteria_builds_full_profile_view():
    from criteria.loader import load_criteria
    c = load_criteria(make_cursor())
    assert c.profile_id == "p-1" and c.name == "Test Person"
    assert c.salary_floor == 30000
    assert c.threshold_standard == 41700
    assert c.threshold_new_entrant == 30960
    assert c.kill_keywords == ["audit", "compliance"]
    assert c.role_patterns == ["Solutions Engineer", "Forward Deployed Engineer"]


def test_load_criteria_scopes_queries_to_the_owner():
    from criteria.loader import load_criteria
    cur = make_cursor()
    load_criteria(cur)
    owner_scoped = [sql for sql, _ in cur.executed if "owner_id" in sql]
    assert len(owner_scoped) >= 2      # constraints and roles filter by owner


def test_role_matcher_is_flexible_on_spacing_and_hyphens():
    from criteria.loader import build_role_matcher
    fits = build_role_matcher(["Solutions Engineer", "Forward Deployed Engineer"])
    assert fits("Senior Solutions Engineer, EMEA")
    assert fits("Forward-Deployed Engineer")       # hyphen == space
    assert fits("forward  deployed engineer")      # case/whitespace-insensitive
    assert not fits("Accountant")
    assert not fits("")
    assert not fits(None)


def test_sample_patterns_exist_for_offline_dry_runs():
    # Offline dry-run needs a matcher without a DB: generic samples, clearly
    # not personal data.
    from criteria.loader import SAMPLE_ROLE_PATTERNS, build_role_matcher
    assert len(SAMPLE_ROLE_PATTERNS) >= 3
    fits = build_role_matcher(SAMPLE_ROLE_PATTERNS)
    assert fits("Machine Learning Engineer")


# ---- criteria writes (Phase 5: set_criteria / add_target_company tools) ----

def test_default_profile_id_reads_the_first_profile():
    from criteria.loader import default_profile_id
    from tests.conftest import FakeCursor
    cur = FakeCursor(rows=[{"profile_id": "p-1"}])
    assert default_profile_id(cur) == "p-1"
    assert "from profiles" in cur.executed[0][0].lower()


def test_default_profile_id_raises_when_no_profile_exists():
    import pytest
    from criteria.loader import default_profile_id
    from tests.conftest import FakeCursor
    with pytest.raises(RuntimeError):
        default_profile_id(FakeCursor(rows=[]))


def test_set_numeric_criterion_updates_an_existing_constraint():
    from criteria.writer import set_numeric_criterion
    from tests.conftest import FakeCursor
    cur = FakeCursor(rowcount=1)                          # update hits a row
    set_numeric_criterion(cur, "p-1", "salary_floor", 45000)
    assert len(cur.executed) == 1                         # no insert needed
    sql, params = cur.executed[0]
    assert "update my_constraints" in sql.lower()
    assert params == (45000, "salary_floor", "p-1")       # owner-scoped write


def test_set_numeric_criterion_inserts_when_the_constraint_is_absent():
    from criteria.writer import set_numeric_criterion
    from tests.conftest import FakeCursor
    cur = FakeCursor(rowcount=0)                          # update hit nothing
    set_numeric_criterion(cur, "p-1", "salary_floor", 45000)
    assert len(cur.executed) == 2
    assert "insert into my_constraints" in cur.executed[1][0].lower()


def test_set_numeric_criterion_refuses_kinds_outside_the_whitelist():
    # Guards against a caller trying to write an arbitrary or secret-ish kind.
    import pytest
    from criteria.writer import set_numeric_criterion
    from tests.conftest import FakeCursor
    with pytest.raises(ValueError):
        set_numeric_criterion(FakeCursor(), "p-1", "notification_channel", 1)


def test_add_target_company_inserts_owner_scoped_and_returns_the_id():
    from criteria.writer import add_target_company
    from tests.conftest import FakeCursor
    cur = FakeCursor(rows=[{"company_id": 123}])
    cid = add_target_company(cur, "p-1", "Acme AI", careers_url="https://acme/careers")
    assert cid == 123
    sql, params = cur.executed[0]
    low = sql.lower()
    assert "insert into target_companies" in low
    assert "owner_id" in low
    assert "Acme AI" in params and "p-1" in params and "https://acme/careers" in params


def test_add_target_company_defaults_the_careers_url_to_null():
    from criteria.writer import add_target_company
    from tests.conftest import FakeCursor
    cur = FakeCursor(rows=[{"company_id": 5}])
    add_target_company(cur, "p-1", "Beta Corp")
    assert None in cur.executed[0][1]


# ---- add_skill (Phase 8.5 / U2: the skills-entry write) ----

def test_add_skill_inserts_with_norm_evidence_and_learned_at():
    # The first writer of my_skills. learned_at + evidence are pinned from
    # day one — the future learning-curve model's data starts here.
    from criteria.writer import add_skill
    from tests.conftest import FakeCursor
    cur = FakeCursor(rowcount=0)                          # update hit nothing
    out = add_skill(cur, "p-1", "  Care   Planning ", level="working",
                    evidence="2 years writing care plans at Meadow House",
                    learned_at="2024-03-01", category="care")
    assert out["outcome"] == "added"
    assert out["skill_norm"] == "care planning"           # the ONE normaliser
    assert len(cur.executed) == 2
    sql, params = cur.executed[1]
    low = sql.lower()
    assert "insert into my_skills" in low and "owner_id" in low
    assert "learned_at" in low and "evidence" in low
    # The RAW skill is written and the database normalises it (skill_norm is
    # GENERATED ALWAYS). This assertion used to require "care planning" among
    # the parameters, which is precisely what B-GAE-013 was: it pinned the
    # broken INSERT in place and read as coverage.
    assert "Care   Planning" in params and "p-1" in params
    import datetime
    assert datetime.date(2024, 3, 1) in params


def test_add_skill_updates_in_place_and_reactivates():
    from criteria.writer import add_skill
    from tests.conftest import FakeCursor
    cur = FakeCursor(rowcount=1)                          # update hits a row
    out = add_skill(cur, "p-1", "Care Planning", evidence="newer evidence")
    assert out["outcome"] == "updated"
    assert len(cur.executed) == 1                         # no insert
    sql, params = cur.executed[0]
    low = sql.lower()
    assert "update my_skills" in low
    assert "status" in low                                # re-adding revives it
    assert "coalesce" in low                              # absent fields keep old values
    assert "care planning" in params and "p-1" in params


def test_add_skill_rejects_blank_names_and_bad_dates():
    import pytest
    from criteria.writer import add_skill
    from tests.conftest import FakeCursor
    with pytest.raises(ValueError):
        add_skill(FakeCursor(), "p-1", "   ")
    with pytest.raises(ValueError):
        add_skill(FakeCursor(), "p-1", "Python", learned_at="last spring")


def test_add_skill_leaves_the_generated_column_to_the_database():
    # my_skills.skill_norm has been GENERATED ALWAYS since migration 0001, so
    # naming it in an INSERT is rejected outright. Every test above uses a
    # FakeCursor, which records SQL without caring what the column is — which
    # is exactly why this survived (B-GAE-013).
    from criteria.writer import add_skill
    from tests.conftest import FakeCursor
    cur = FakeCursor(rowcount=0)

    add_skill(cur, "p-1", "Care Planning")

    insert_sql = cur.executed[1][0].lower()
    assert "insert into my_skills" in insert_sql
    assert "skill_norm" not in insert_sql, \
        "skill_norm is GENERATED ALWAYS — the database computes it, not us"


@_DB_ONLY
def test_add_skill_actually_lands_a_row_in_a_real_my_skills():
    # The offline tests could not have caught B-GAE-013 and no rewrite of them
    # would: a fake cursor has no generated columns. So this one runs the real
    # function against a real copy of the real table.
    from criteria.writer import add_skill
    from db.connection import get_conn

    schema = "add_skill_probe"
    owner = "11111111-1111-4111-a111-111111111111"
    with get_conn() as conn:
        try:
            with conn.cursor() as cur:
                cur.execute(f"drop schema if exists {schema} cascade")
                cur.execute(f"create schema {schema}")
                cur.execute(f"set search_path to {schema}")
                cur.execute("create table my_skills "
                            "(like public.my_skills including all)")

                added = add_skill(cur, owner, "  Care   Planning ",
                                  level="working", evidence="2 years",
                                  learned_at="2024-03-01")
                assert added["outcome"] == "added"

                cur.execute("select skill, skill_norm, level, owner_id "
                            "from my_skills")
                rows = cur.fetchall()
                assert len(rows) == 1, "add_skill wrote nothing"
                # the database's own normalisation agrees with norm()
                assert rows[0]["skill_norm"] == added["skill_norm"]
                assert rows[0]["skill_norm"] == "care planning"

                # and the second call updates rather than duplicating
                again = add_skill(cur, owner, "Care Planning", level="strong")
                assert again["outcome"] == "updated"
                cur.execute("select count(*) as n from my_skills")
                assert cur.fetchone()["n"] == 1
        finally:
            conn.rollback()
            with conn.cursor() as cur:
                cur.execute(f"drop schema if exists {schema} cascade")
            conn.rollback()
