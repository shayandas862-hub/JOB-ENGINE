"""Integration tests for v_apply_queue — the product's ranking, wall, and guard.

Opt-in: they need a real Postgres (DATABASE_URL) and run only when
RUN_DB_TESTS=1. Everything happens inside a scratch schema built from the real
migration DDL (db/migrations/0022_per_soc_salary_wall.sql), then dropped —
production tables are never touched.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DB_TESTS") != "1",
    reason="DB integration tests are opt-in: RUN_DB_TESTS=1",
)

SCHEMA = "tq_queue_test"
OWNER = "11111111-1111-4111-a111-111111111111"

# Copies of the REAL tables, not minimal imitations of them. The hand-written
# version drifted from the schema exactly as B-GAE-015, 020 and 022 did — and
# five of the columns the views read did not exist in it at all, so the queue
# was being judged against a table shaped differently from production's. A LIKE
# cannot drift.
#
# LIKE does not copy FOREIGN KEYS, and none are re-added here on purpose: these
# views only ever JOIN, so no test depends on referential integrity, and adding
# FKs would force the seed to satisfy them in an order this fixture does not
# care about. Where an FK IS load-bearing it must be re-added by hand (see
# tests/test_census_store.py, where a ForeignKeyViolation is asserted).
REAL_TABLES = """
create table target_companies (like public.target_companies including all);
create table role_listings    (like public.role_listings including all);
create table my_constraints   (like public.my_constraints including all);
create table soc_going_rates  (like public.soc_going_rates including all);
create table listing_events   (like public.listing_events including all);
"""

# Every insert names its columns. The old seed used positional VALUES against
# the invented column order, which is what made the scaffold impossible to
# convert without rewriting it — a positional insert silently means something
# different the moment a column is added anywhere but the end.
#
# OVERRIDING SYSTEM VALUE where a real primary key is GENERATED ALWAYS AS
# IDENTITY: the assertions below are all "which role_id came back", so the ids
# have to be the stated ones rather than whatever the sequence hands out.
SEED = f"""
insert into target_companies
  (company_id, company_name, fit_rank, sponsor_confidence, lane, owner_id)
overriding system value values
  (1, 'HighFit Co',  'High', 'sponsors (verified)', 'lane-a', '{OWNER}'),
  (2, 'LowFit Ltd',  'Low',  'register-only',       'lane-b', '{OWNER}');
insert into my_constraints (kind, numeric_value, owner_id) values
  ('salary_threshold_standard',    41700, '{OWNER}'),
  ('salary_threshold_new_entrant', 30960, '{OWNER}');
insert into soc_going_rates (occupation_code, going_rate_annual)
values ('2134', 54700);
-- role_status is stated for every row because the REAL table has no default for
-- it. The old scaffold invented `role_status text default 'open'`, and that
-- invented default was the only reason these tests saw any rows: the view's
-- first condition is `r.role_status = 'open'`, so against the real table every
-- row arrived NULL and the queue came back empty. Production code always sets
-- it explicitly, and now so does this fixture.
insert into role_listings
  (role_id, company_id, role_title, location, salary_max, sponsors_this_role,
   soc_code, created_at, role_status)
overriding system value values
  (1, 1, 'AI Engineer',        'London, UK',    60000, null,         '2134', now() - interval '1 day', 'open'),
  (2, 1, 'AI Engineer',        'London, UK',    50000, null,         '2134', now() - interval '2 day', 'open'),
  (3, 1, 'AI Engineer',        'London, UK',    60000, null,         null,   now() - interval '3 day', 'open'),
  (4, 1, 'AI Engineer',        'London, UK',    null,  null,         null,   now() - interval '4 day', 'open'),
  (5, 1, 'AI Engineer',        'Cambridge, MA', 60000, null,         '2134', now() - interval '5 day', 'open'),
  (6, 1, 'AI Engineer',        'London, UK',    null,  'no_sponsor', null,   now() - interval '6 day', 'open'),
  (7, 2, 'ML Engineer',        'Remote - UK',   null,  'sponsors',   null,   now() - interval '7 day', 'open'),
  (8, 1, 'Head of Marketing',  'London, UK',    90000, null,         null,   now() - interval '8 day', 'open');
update role_listings set deadline = current_date + 10, deadline_source = 'estimated' where role_id = 1;
insert into listing_events (role_id, event_type, occurred_at) values
  (2, 'changed',  now() - interval '1 day'),
  (2, 'reopened', now() - interval '12 hour'),
  (2, 'appeared', now() - interval '2 day');
"""


@pytest.fixture(scope="module")
def queue_rows():
    from db.connection import get_conn

    ddl = (Path(__file__).parents[1] / "db" / "migrations"
           / "0025_queue_surfaces_history.sql").read_text()
    view_sql = ddl.split("BEGIN;")[1].split("COMMIT;")[0]

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f"drop schema if exists {SCHEMA} cascade")
            cur.execute(f"create schema {SCHEMA}")
            cur.execute(f"set search_path to {SCHEMA}")
            cur.execute(REAL_TABLES)
            cur.execute(SEED)
            cur.execute(view_sql)
            cur.execute("select * from v_apply_queue")
            rows = cur.fetchall()
            cur.execute(f"drop schema {SCHEMA} cascade")
        conn.rollback()  # scratch schema was dropped; nothing to keep
    return rows


def by_id(rows, role_id):
    return next(r for r in rows if r["role_id"] == role_id)


def test_uk_guard_excludes_foreign_city_and_fit_filter_excludes_wrong_titles(queue_rows):
    ids = {r["role_id"] for r in queue_rows}
    assert 5 not in ids                       # Cambridge, MA — UK guard
    assert 8 not in ids                       # Head of Marketing — fit filter
    assert ids == {1, 2, 3, 4, 6, 7}


def test_wall_judges_per_soc_when_code_known(queue_rows):
    r1 = by_id(queue_rows, 1)                 # £60k vs going rate £54.7k
    assert r1["salary_wall"] == "clears"
    assert r1["wall_basis"] == "going_rate:2134"
    r2 = by_id(queue_rows, 2)                 # £50k: under £54.7k but over 70% band
    assert r2["salary_wall"] == "clears_new_entrant"
    assert r2["wall_basis"] == "going_rate:2134"


def test_wall_falls_back_to_flat_threshold_without_a_code(queue_rows):
    r3 = by_id(queue_rows, 3)                 # £60k, no SOC -> flat £41.7k
    assert r3["salary_wall"] == "clears"
    assert r3["wall_basis"] == "flat_fallback"
    r4 = by_id(queue_rows, 4)                 # no salary stated
    assert r4["salary_wall"] == "unknown"
    assert r4["wall_basis"] == "no_salary"


def test_sponsor_signals_and_ranking_order(queue_rows):
    assert by_id(queue_rows, 6)["sponsor_signal"] == "role-excluded"
    assert by_id(queue_rows, 7)["sponsor_signal"] == "role-confirmed"
    order = [r["role_id"] for r in queue_rows]
    # High-fit company rows come before the low-fit company's...
    assert order.index(1) < order.index(7)
    # ...within High fit, the role-excluded hard negative sorts dead last
    high_fit = [r["role_id"] for r in queue_rows if r["company_name"] == "HighFit Co"]
    assert high_fit[-1] == 6
    # fresher listings first within the same fit+sponsor band
    assert order.index(1) < order.index(2) < order.index(3)


def test_owner_id_is_surfaced_for_multi_user_isolation(queue_rows):
    assert {str(r["owner_id"]) for r in queue_rows} == {OWNER}


def test_history_columns_tell_each_listings_story(queue_rows):
    r1 = by_id(queue_rows, 1)
    assert r1["age_days"] == 1
    assert r1["deadline"] is not None and r1["deadline_source"] == "estimated"
    r2 = by_id(queue_rows, 2)
    # last change = the most recent changed/reopened event, not 'appeared'
    assert r2["last_changed_at"] is not None
    r3 = by_id(queue_rows, 3)
    assert r3["last_changed_at"] is None          # never changed -> no noise
