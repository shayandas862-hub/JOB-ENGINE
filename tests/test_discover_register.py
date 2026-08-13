"""Tests for src/discover/register — the licensed-sponsor register walk.

Offline by default: a routing fake cursor serves a seeded register slice and
records the SQL so we can assert the filters. One opt-in integration test
(RUN_DB_TESTS=1) runs the real query against a seeded scratch schema.
"""
from __future__ import annotations

import os

import pytest


class RoutingCursor:
    """Fake cursor answering each query from a routing table by substring."""

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


SPONSOR_ROWS = [
    {"sponsor_id": 10, "organisation_name": "Acme AI Ltd", "org_name_norm": "acme ai ltd",
     "town_city": "London", "county": None, "rating": "A", "route": "Skilled Worker"},
    {"sponsor_id": 11, "organisation_name": "Beta Data Ltd", "org_name_norm": "beta data ltd",
     "town_city": "Manchester", "county": None, "rating": "A", "route": "Skilled Worker"},
]


def make_cursor(sponsor_rows=None, known_targets=None, hints=None):
    return RoutingCursor([
        ("from target_companies", known_targets or []),
        ("from my_constraints", hints or []),
        ("from licensed_sponsors", SPONSOR_ROWS if sponsor_rows is None else sponsor_rows),
        ("from profiles", [{"profile_id": "p-1"}]),
    ])


def register_query(cur):
    """The (sql, params) pair for the licensed_sponsors read."""
    return next((s, p) for s, p in cur.executed if "from licensed_sponsors" in s)


# ---- register filtering -----------------------------------------------------

def test_find_candidate_sponsors_filters_to_a_rated_skilled_worker():
    from discover.register import find_candidate_sponsors
    cur = make_cursor()
    out = find_candidate_sponsors(cur, "p-1")
    sql, params = register_query(cur)
    assert "is_skilled_worker = true" in sql
    assert "ls.rating = %(rating)s" in sql
    assert params["rating"] == "A"
    assert [c.sponsor_id for c in out] == [10, 11]


def test_excludes_companies_already_targeted_by_id_and_by_normalised_name():
    from discover.register import find_candidate_sponsors
    known = [
        {"sponsor_id": 99, "company_name": "Gamma Corp"},
        {"sponsor_id": None, "company_name": "Beta  Data   Ltd"},   # matched via norm()
    ]
    cur = make_cursor(known_targets=known)
    find_candidate_sponsors(cur, "p-1")
    sql, params = register_query(cur)
    assert "ls.id <> all(%(known_ids)s)" in sql
    assert "ls.org_name_norm <> all(%(known_norms)s)" in sql
    assert 99 in params["known_ids"]
    assert "beta data ltd" in params["known_norms"]     # collapsed + lowered by norm()


def test_no_known_targets_means_no_exclusion_clause():
    from discover.register import find_candidate_sponsors
    cur = make_cursor(known_targets=[])
    find_candidate_sponsors(cur, "p-1")
    sql, _ = register_query(cur)
    assert "known_ids" not in sql and "known_norms" not in sql


def test_region_and_industry_hints_add_ilike_filters():
    from discover.register import find_candidate_sponsors
    cur = make_cursor()
    find_candidate_sponsors(cur, "p-1", region_patterns=["%London%"],
                            industry_patterns=["%software%", "%data%"])
    sql, params = register_query(cur)
    assert "ls.town_city ilike any(%(region)s)" in sql
    assert "ls.county ilike any(%(region)s)" in sql
    assert "ls.organisation_name ilike any(%(industry)s)" in sql
    assert params["region"] == ["%London%"]
    assert params["industry"] == ["%software%", "%data%"]


def test_no_hints_means_no_region_or_industry_clause():
    from discover.register import find_candidate_sponsors
    cur = make_cursor()
    find_candidate_sponsors(cur, "p-1")
    sql, _ = register_query(cur)
    assert "ilike any" not in sql


def test_limit_adds_a_bound_and_binds_the_value():
    from discover.register import find_candidate_sponsors
    cur = make_cursor()
    find_candidate_sponsors(cur, "p-1", limit=25)
    sql, params = register_query(cur)
    assert "limit %(limit)s" in sql
    assert params["limit"] == 25


def test_candidate_carries_every_register_column():
    from discover.register import SponsorCandidate, find_candidate_sponsors
    cur = make_cursor(sponsor_rows=[SPONSOR_ROWS[0]])
    (c,) = find_candidate_sponsors(cur, "p-1")
    assert isinstance(c, SponsorCandidate)
    assert (c.sponsor_id, c.organisation_name, c.org_name_norm, c.town_city,
            c.county, c.rating, c.route) == (
        10, "Acme AI Ltd", "acme ai ltd", "London", None, "A", "Skilled Worker")


# ---- hints loading (owner-scoped, from the DB never code) -------------------

def test_load_discovery_hints_wraps_owner_keywords_as_patterns():
    from discover.register import load_discovery_hints
    rows = [
        {"kind": "region_hint", "value": "London"},
        {"kind": "industry_hint", "value": "software"},
        {"kind": "industry_hint", "value": "data"},
    ]
    cur = RoutingCursor([("from my_constraints", rows)])
    region, industry = load_discovery_hints(cur, "p-1")
    assert region == ["%London%"]
    assert industry == ["%software%", "%data%"]
    assert cur.executed[0][1] == ("p-1",)               # owner-scoped read


def test_load_discovery_hints_returns_empty_lists_when_none_configured():
    from discover.register import load_discovery_hints
    cur = RoutingCursor([("from my_constraints", [])])
    assert load_discovery_hints(cur, "p-1") == ([], [])


# ---- the owner-scoped entry point ------------------------------------------

def test_find_candidates_for_profile_resolves_profile_and_scopes_by_owner():
    from discover.register import find_candidates_for_profile
    cur = make_cursor(hints=[{"kind": "industry_hint", "value": "software"}])
    out = find_candidates_for_profile(cur)              # profile resolved from profiles
    scoped = [p for s, p in cur.executed
              if "from target_companies" in s or "from my_constraints" in s]
    assert scoped and all(p == ("p-1",) for p in scoped)
    _, params = register_query(cur)
    assert params["industry"] == ["%software%"]
    assert [c.sponsor_id for c in out] == [10, 11]


# ---- opt-in integration: a real seeded register slice ----------------------

@pytest.mark.skipif(
    os.getenv("RUN_DB_TESTS") != "1",
    reason="DB integration tests are opt-in: RUN_DB_TESTS=1",
)
def test_register_walk_against_a_seeded_slice():
    from db.connection import get_conn
    from discover.register import find_candidate_sponsors

    schema = "tq_register_test"
    owner = "11111111-1111-4111-a111-111111111111"
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f"drop schema if exists {schema} cascade")
            cur.execute(f"create schema {schema}")
            cur.execute(f"set search_path to {schema}")
            # Real shapes, not invented ones. The old hand-written scaffold
            # declared rating, org_name_norm and is_skilled_worker as plain text
            # columns and inserted them directly — but all three are GENERATED
            # ALWAYS on the real table, and type_rating (which is what they are
            # generated FROM) did not exist in the scaffold at all. So this test
            # used to assert against a schema the database does not have, and
            # could never have caught a B-GAE-013-style write to a generated
            # column on this path. See B-GAE-026.
            cur.execute("""
                create table licensed_sponsors
                  (like public.licensed_sponsors including all);
                create table target_companies
                  (like public.target_companies including all);
            """)
            # Raw facts only — the database derives rating from type_rating
            # ('A (Premium)' -> 'A'), org_name_norm from organisation_name, and
            # is_skilled_worker from route. Inserting them would raise
            # GeneratedAlways, which is the whole of the CLAUDE.md gotcha.
            # OVERRIDING SYSTEM VALUE because id is GENERATED ALWAYS AS IDENTITY
            # on the real table — the old scaffold declared it a plain bigint, so
            # it silently accepted explicit ids. The assertions below are about
            # WHICH sponsors come back, so the ids have to be the stated ones.
            cur.execute(f"""
                insert into licensed_sponsors
                  (id, organisation_name, town_city, county, type_rating, route)
                overriding system value
                values
                  (1,'Acme AI Ltd','London',null,'Worker (A rating)','Skilled Worker'),
                  (2,'Beta Data Ltd','Leeds',null,'Worker (A rating)','Skilled Worker'),
                  (3,'Gamma Charity','York',null,'Worker (A rating)','Charity Worker'),
                  (4,'Delta B Ltd','Bath',null,'Worker (B rating)','Skilled Worker'),
                  (5,'Known Co','Hull',null,'Worker (A rating)','Skilled Worker');
                insert into target_companies
                  (company_id, company_name, sponsor_id, owner_id)
                overriding system value
                values (100,'Known Co',5,'{owner}');
            """)
            out = find_candidate_sponsors(cur, owner)
            cur.execute(f"drop schema {schema} cascade")
        conn.rollback()

    # A-rated Skilled Worker sponsors not already targeted, name-ordered.
    assert [c.sponsor_id for c in out] == [1, 2]
    assert all(c.rating == "A" and c.route == "Skilled Worker" for c in out)
