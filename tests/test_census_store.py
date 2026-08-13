"""The census store: every sweep write goes through here, and only here.

Offline: FakeCursor/RoutingCursor assert the exact SQL shapes (upsert by
org_name_norm, census_jobs dedupe via the shared dedupe_key, registry columns).
One opt-in DB test (RUN_DB_TESTS=1) proves the 0030 constraints against a
scratch schema. The sweep never touches target_companies or review_items —
that invariant is pinned in test_sweep.py; here we pin that the store's SQL
only ever names the two census tables.
"""
from __future__ import annotations

import os

import pytest

from tests.conftest import FakeCursor
from tests.test_criteria import RoutingCursor

ORG = {
    "org_name_norm": "acme ai ltd",
    "sponsor_id": 42,
    "organisation_name": "Acme AI Ltd",
    "town_city": "London",
    "is_skilled_worker": True,
    "rating": "A",
}


def _job(title, url, company="Acme AI Ltd", location="London, UK"):
    from fetch.feeds import Job
    return Job(company_name=company, source="greenhouse", external_id=url,
               title=title, location=location, url=url, jd_text="",
               salary_text=None)


# ---- upsert_probe -----------------------------------------------------------

def test_upsert_probe_board_found_writes_counts_and_stamps_probed_at():
    from discover.census_store import upsert_probe
    cur = FakeCursor()
    upsert_probe(cur, ORG, outcome="board_found", ats_type="greenhouse",
                 ats_token="acmeai", careers_url="https://boards.greenhouse.io/acmeai",
                 total_jobs_seen=5, local_jobs_seen=2)
    assert len(cur.executed) == 1
    sql, params = cur.executed[0]
    lowered = sql.lower()
    assert "insert into sponsor_census" in lowered
    assert "on conflict (org_name_norm) do update" in lowered
    assert "now()" in lowered                       # probed_at stamped in SQL
    assert "board_found" in params and "greenhouse" in params
    assert 5 in params and 2 in params and "acme ai ltd" in params


def test_upsert_probe_already_tracked_copies_ats_fields():
    from discover.census_store import upsert_probe
    cur = FakeCursor()
    upsert_probe(cur, ORG, outcome="already_tracked", ats_type="lever",
                 ats_token="acme", careers_url="https://jobs.lever.co/acme")
    _, params = cur.executed[0]
    assert "already_tracked" in params and "lever" in params and "acme" in params


def test_upsert_probe_error_records_the_message():
    from discover.census_store import upsert_probe
    cur = FakeCursor()
    upsert_probe(cur, ORG, outcome="error", probe_error="probe blew up")
    _, params = cur.executed[0]
    assert "error" in params and "probe blew up" in params


# ---- update_probe_fetch -----------------------------------------------------

def test_update_probe_fetch_sets_local_count():
    from discover.census_store import update_probe_fetch
    cur = FakeCursor()
    update_probe_fetch(cur, "acme ai ltd", local_jobs_seen=2)
    sql, params = cur.executed[0]
    lowered = sql.lower()
    assert "update sponsor_census" in lowered
    assert "local_jobs_seen" in lowered and "where org_name_norm" in lowered
    assert params == (2, None, "acme ai ltd")


def test_update_probe_fetch_can_note_a_fetch_error():
    from discover.census_store import update_probe_fetch
    cur = FakeCursor()
    update_probe_fetch(cur, "acme ai ltd", local_jobs_seen=None,
                       probe_error="fetch failed: 500")
    _, params = cur.executed[0]
    assert params == (None, "fetch failed: 500", "acme ai ltd")


# ---- insert_census_jobs -----------------------------------------------------

def test_insert_census_jobs_uses_shared_dedupe_key_and_conflict_do_nothing():
    from discover.census_store import insert_census_jobs
    from fetch.feeds import dedupe_key
    cur = FakeCursor()
    jobs = [_job("Senior Solutions Engineer", "https://a/1"),
            _job("Accountant", "https://a/2")]
    stored, matched = insert_census_jobs(
        cur, "acme ai ltd", jobs, lambda title: "engineer" in title.lower(),
        lambda location: True)
    assert (stored, matched) == (2, 1)
    assert len(cur.executed_many) == 1
    sql, rows = cur.executed_many[0]
    lowered = sql.lower()
    assert "insert into census_jobs" in lowered
    assert "on conflict (dedupe_key) do nothing" in lowered
    assert "is_local" in lowered
    assert rows[0][0] == "acme ai ltd"                       # org_name_norm first
    expected_key = dedupe_key("Acme AI Ltd", "Senior Solutions Engineer", "https://a/1")
    assert expected_key in rows[0]                           # the SHARED fingerprint
    assert rows[0][7] is True and rows[1][7] is False        # title_match per row
    assert rows[0][8] is True and rows[1][8] is True         # is_local per row


def test_insert_census_jobs_keeps_foreign_jobs_labelled_not_dropped():
    """Founder rule (2026-07-16): storage never filters by country. is_local is
    a label from the caller's matcher; foreign rows land exactly like local ones."""
    from discover.census_store import insert_census_jobs
    cur = FakeCursor()
    jobs = [_job("Platform Engineer", "https://a/uk"),
            _job("Platform Engineer II", "https://a/us",
                 location="Austin, TX, US")]
    stored, _ = insert_census_jobs(cur, "acme ai ltd", jobs, lambda t: False,
                                   lambda loc: "UK" in str(loc))
    assert stored == 2                                       # both rows land
    _, rows = cur.executed_many[0]
    assert rows[0][8] is True and rows[1][8] is False        # labelled, not dropped


def test_insert_census_jobs_with_no_jobs_touches_nothing():
    from discover.census_store import insert_census_jobs
    cur = FakeCursor()
    assert insert_census_jobs(cur, "acme ai ltd", [], lambda t: True,
                              lambda loc: True) == (0, 0)
    assert cur.executed == [] and cur.executed_many == []


# ---- record_registry_result -------------------------------------------------

def test_record_registry_result_matched_writes_registry_columns():
    from discover.census_store import record_registry_result
    cur = FakeCursor()
    record_registry_result(cur, "acme ai ltd", "matched", number="09876543",
                           status="active", company_type="ltd",
                           industry_codes=["62012", "62020"],
                           incorporated="2015-03-01")
    sql, params = cur.executed[0]
    lowered = sql.lower()
    assert "update sponsor_census" in lowered
    for col in ("registry_checked_at", "registry_outcome", "registry_number",
                "registry_status", "registry_type", "industry_codes",
                "incorporated", "registry_error"):
        assert col in lowered
    assert "matched" in params and "09876543" in params
    assert ["62012", "62020"] in params


def test_record_registry_result_never_touches_probe_columns():
    from discover.census_store import record_registry_result
    cur = FakeCursor()
    record_registry_result(cur, "acme ai ltd", "error", error="profile 404")
    sql, params = cur.executed[0]
    assert "probe" not in sql.lower()            # registry writer stays in its lane
    assert "profile 404" in params


# ---- census_status_counts ---------------------------------------------------

def test_census_status_counts_reports_totals_by_outcome():
    from discover.census_store import census_status_counts
    cur = RoutingCursor([
        ("from licensed_sponsors", [{"total": 110}]),
        ("group by probe_outcome", [{"probe_outcome": "board_found", "n": 3},
                                    {"probe_outcome": "no_board", "n": 5}]),
        ("from census_jobs", [{"jobs": 42, "matches": 7}]),
        ("group by registry_outcome", [{"registry_outcome": "matched", "n": 4}]),
    ])
    out = census_status_counts(cur)
    assert out == {
        "total_unique_orgs": 110,
        "probed": 8,
        "by_outcome": {"board_found": 3, "no_board": 5},
        "boards_found": 3,
        "census_jobs": 42,
        "title_matches": 7,
        "registry_by_outcome": {"matched": 4},
        "remaining": 102,
    }


def test_ensure_census_card_inserts_a_bare_card_idempotently():
    from discover.census_store import ensure_census_card
    cur = FakeCursor()
    ensure_census_card(cur, ORG)
    sql, params = cur.executed[0]
    lowered = sql.lower()
    assert "insert into sponsor_census" in lowered
    assert "on conflict (org_name_norm) do nothing" in lowered
    assert "probe_outcome" not in lowered          # a bare card: no probe verdict yet
    assert "acme ai ltd" in params and 42 in params


def test_classify_status_counts_reports_software_and_remaining():
    from discover.census_store import classify_status_counts
    cur = RoutingCursor([
        ("from licensed_sponsors", [{"total": 126000}]),
        ("group by registry_outcome", [{"registry_outcome": "matched", "n": 40},
                                       {"registry_outcome": "not_found", "n": 10}]),
        ("industry_codes &&", [{"n": 12}]),
    ])
    out = classify_status_counts(cur, {"62012", "62020"})
    assert out == {
        "total_unique_orgs": 126000,
        "classified": 50,
        "by_outcome": {"matched": 40, "not_found": 10},
        "software_companies": 12,
        "remaining": 125950,
    }


def test_census_store_sql_only_names_census_tables():
    """Blast-radius, store edition: no store write can name the daily tables."""
    import inspect

    from discover import census_store
    source = inspect.getsource(census_store).lower()
    assert "target_companies" not in source
    assert "review_items" not in source


# ---- opt-in integration: the 0030 constraints against a scratch schema ------

@pytest.mark.skipif(
    os.getenv("RUN_DB_TESTS") != "1",
    reason="DB integration tests are opt-in: RUN_DB_TESTS=1",
)
def test_census_tables_constrain_and_dedupe():
    import psycopg

    from db.connection import get_conn
    from discover.census_store import (insert_census_jobs, update_probe_fetch,
                                       upsert_probe)

    schema = "tq_census_test"
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f"drop schema if exists {schema} cascade")
            cur.execute(f"create schema {schema}")
            cur.execute(f"set search_path to {schema}")
            # B-GAE-019/B-GAE-015: both tables were hand-written column lists,
            # and census_jobs drifted when Phase 8.5 added is_local — so this
            # test would have died on UndefinedColumn even after the signature
            # below was corrected. LIKE cannot drift. The CHECK constraints
            # this test asserts come across with INCLUDING ALL; the foreign key
            # does not, so it is re-added by hand to keep the FK assertion
            # below meaningful.
            cur.execute("""
                create table sponsor_census
                  (like public.sponsor_census including all);
                create table census_jobs
                  (like public.census_jobs including all);
                alter table census_jobs
                  add foreign key (org_name_norm)
                  references sponsor_census (org_name_norm) on delete cascade;
            """)
            # upsert is idempotent by org: a re-probe updates, never duplicates
            upsert_probe(cur, ORG, outcome="board_found", ats_type="greenhouse",
                         ats_token="acmeai", careers_url="https://x",
                         total_jobs_seen=5)
            update_probe_fetch(cur, ORG["org_name_norm"], local_jobs_seen=2)
            upsert_probe(cur, ORG, outcome="error", probe_error="second pass")
            cur.execute("select count(*) as n, max(probe_outcome) as o from sponsor_census")
            row = cur.fetchone()
            assert (row["n"], row["o"]) == (1, "error")
            # same job twice -> one row (shared dedupe_key)
            jobs = [_job("Engineer", "https://a/1"), _job("Engineer", "https://a/1")]
            # B-GAE-019: this call kept insert_census_jobs' pre-8.5 shape and
            # died on TypeError before touching a row — red since 8.5 task 2,
            # unseen because CI runs offline only. local_matcher is required.
            insert_census_jobs(cur, ORG["org_name_norm"], jobs,
                               lambda title: True, lambda location: True)
            cur.execute("select count(*) as n from census_jobs")
            assert cur.fetchone()["n"] == 1
            # a bogus outcome is rejected by the CHECK constraint
            with pytest.raises(psycopg.errors.CheckViolation):
                with conn.transaction():
                    cur.execute("insert into sponsor_census (org_name_norm, probe_outcome) "
                                "values ('bogus org', 'not_an_outcome')")
            # a job without its census parent is rejected by the FK
            with pytest.raises(psycopg.errors.ForeignKeyViolation):
                with conn.transaction():
                    cur.execute("insert into census_jobs (org_name_norm, dedupe_key) "
                                "values ('nobody', 'k1')")
            cur.execute(f"drop schema {schema} cascade")
        conn.rollback()
