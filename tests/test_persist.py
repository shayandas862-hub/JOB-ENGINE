"""Tests for src/persist — the write rules that decide what the pipeline may
touch in the database. Pure functions; no DB needed."""
from __future__ import annotations

from persist.fetch_rules import fetch_outcome


# ---- two-empty-runs safety (audit: a glitchy feed returning [] must not
# mass-close a company's real listings on the first empty run) ----

def test_company_with_uk_jobs_is_ok_and_rot_eligible():
    assert fetch_outcome(job_count=3, previous_feed_status="ok") == ("ok", True)
    assert fetch_outcome(job_count=1, previous_feed_status="empty") == ("ok", True)


def test_first_empty_run_marks_empty_but_protects_listings():
    assert fetch_outcome(job_count=0, previous_feed_status="ok") == ("empty", False)
    assert fetch_outcome(job_count=0, previous_feed_status=None) == ("empty", False)
    assert fetch_outcome(job_count=0, previous_feed_status="error") == ("empty", False)


def test_second_consecutive_empty_run_allows_job_rot():
    assert fetch_outcome(job_count=0, previous_feed_status="empty") == ("empty", True)


# ---- read-once + no-clobber (audit: zero-skill roles were re-billed forever;
# a keyword re-run must never erase Gemini-derived values) ----

from tests.conftest import FakeCursor


class Reading:
    """Duck-typed stand-in for read.gemini.JDReading."""

    def __init__(self, skills=(), salary_text=None, sponsor_hint=None, soc_hint=None):
        self.skills = list(skills)
        self.salary_text = salary_text
        self.sponsor_hint = sponsor_hint
        self.soc_hint = soc_hint


def test_unread_selection_keys_on_extracted_at_not_skill_rows():
    from persist.extract_rules import UNREAD_ROLES_SQL
    sql = " ".join(UNREAD_ROLES_SQL.split()).lower()
    assert "extracted_at is null" in sql
    assert "role_skills" not in sql          # the old leaky guard is gone


def test_zero_skill_reading_still_marks_role_extracted():
    from persist.extract_rules import persist_reading
    cur = FakeCursor()
    n = persist_reading(cur, 42, Reading())
    assert n == 0
    assert len(cur.executed) == 1            # no skill inserts, but one update
    sql, params = cur.executed[0]
    assert "extracted_at" in sql and "now()" in sql
    assert params[-1] == 42


def test_persist_reading_coalesces_new_value_first_and_batch_inserts_skills():
    from persist.extract_rules import persist_reading
    cur = FakeCursor()
    n = persist_reading(cur, 7, Reading(
        skills=[("PostgreSQL", "data"), ("Python", "programming")],
        salary_text="£80k", sponsor_hint="sponsors"))
    assert n == 2
    # skills go in ONE batched executemany, not row-by-row round trips
    assert len(cur.executed_many) == 1
    insert_sql, insert_rows = cur.executed_many[0]
    assert "role_skills" in insert_sql
    assert insert_rows == [(7, "PostgreSQL", "postgresql", "data"),
                           (7, "Python", "python", "programming")]
    update_sql, update_params = cur.executed[0]
    # COALESCE(new, old): the fresh value must be the FIRST argument
    assert "salary_text = coalesce(%s, salary_text)" in update_sql
    # (salary, sponsor, raw hint, resolved code, quality, provenance, role_id)
    # — no resolver and no labels here, so those are None (0039: unlabelled
    # callers leave the existing labels alone)
    assert update_params == ("£80k", "sponsors", None, None, None, None, 7)


def test_persist_reading_stores_raw_hint_but_only_resolved_codes():
    from persist.extract_rules import persist_reading
    cur = FakeCursor()
    reading = Reading(soc_hint="Software developers")
    persist_reading(cur, 9, reading, soc_resolver=lambda hint: "2134")
    sql, params = cur.executed[0]
    assert "soc_hint = coalesce(%s, soc_hint)" in sql
    assert "soc_code = coalesce(%s, soc_code)" in sql
    assert params == (None, None, "Software developers", "2134", None, None, 9)


def test_persist_reading_never_writes_unresolved_hint_into_soc_code():
    from persist.extract_rules import persist_reading
    cur = FakeCursor()
    reading = Reading(soc_hint="Software Engineer")        # not an official title
    persist_reading(cur, 9, reading, soc_resolver=lambda hint: None)
    sql, params = cur.executed[0]
    # hint kept, code NULL
    assert params == (None, None, "Software Engineer", None, None, None, 9)


# ---- fetch-run writes: dedupe upsert, job-rot, run bookkeeping ----

class FakeJob:
    def __init__(self, title, location, url, jd_text="jd", salary_text=None,
                 source="greenhouse"):
        self.title, self.location, self.url = title, location, url
        self.jd_text, self.salary_text, self.source = jd_text, salary_text, source


def test_upsert_jobs_batches_rows_keyed_on_dedupe():
    from fetch.feeds import dedupe_key
    from history.fingerprint import fingerprint
    from persist.fetch_rules import upsert_jobs
    cur = FakeCursor()
    jobs = [FakeJob("Solutions Engineer", "London, UK", "https://x/1"),
            FakeJob("ML Engineer", "Remote - UK", "https://x/2")]
    n = upsert_jobs(cur, company_id=5, company_name="Anthropic", jobs=jobs, run_id=99)
    assert n == 2
    # one batched executemany, not one round trip per job
    assert len(cur.executed_many) == 1 and cur.executed == []
    sql, rows = cur.executed_many[0]
    assert "on conflict (company_id, dedupe_key)" in sql.lower()
    assert "content_fingerprint" in sql                    # history change detector rides along
    assert "is_local" in sql and "source" in sql           # keep-all labels ride along too
    assert len(rows) == 2
    assert rows[0][0] == 5                                 # company_id
    assert rows[0][6] == "greenhouse"                      # source label
    assert rows[0][7] is True                              # is_local (London)
    assert rows[0][-3] == fingerprint("Solutions Engineer", "London, UK", None, "jd")
    assert rows[0][-2] == dedupe_key("Anthropic", "Solutions Engineer", "https://x/1")
    assert rows[0][-1] == 99                               # run_id


def test_upsert_jobs_keeps_foreign_jobs_labelled_not_dropped():
    # Founder keep-all rule (2026-07-16): the pipeline layer stores every job
    # the feed returns; locality is a label, never a filter.
    from persist.fetch_rules import upsert_jobs
    cur = FakeCursor()
    jobs = [FakeJob("Platform Engineer", "Austin, TX, US", "https://x/3", source="lever")]
    assert upsert_jobs(cur, 5, "Anthropic", jobs, run_id=7) == 1
    _, rows = cur.executed_many[0]
    assert rows[0][6] == "lever"
    assert rows[0][7] is False                             # stored, labelled non-local


def test_upsert_jobs_empty_list_is_a_noop():
    from persist.fetch_rules import upsert_jobs
    cur = FakeCursor()
    assert upsert_jobs(cur, 5, "Anthropic", [], 99) == 0
    assert cur.executed_many == [] and cur.executed == []


def test_close_vanished_returns_the_closed_ids_for_event_recording():
    from persist.fetch_rules import close_vanished
    cur = FakeCursor(rows=[{"role_id": 10}, {"role_id": 11}, {"role_id": 12}])
    closed = close_vanished(cur, rot_ids=[1, 2], run_id=99)
    assert closed == [10, 11, 12]                          # ids, so 'closed' events can be logged
    sql, params = cur.executed[0]
    assert "role_status='closed'" in sql.replace(" = ", "=")
    assert "role_status <> 'closed'" in sql
    assert "returning role_id" in sql.lower()
    assert params == ([1, 2], 99)


def test_finish_run_records_counts_and_ok_status():
    from persist.fetch_rules import finish_run
    cur = FakeCursor()
    finish_run(cur, run_id=99, companies_attempted=39, roles_seen=750)
    sql, params = cur.executed[0]
    assert "fetch_runs" in sql and "status='ok'" in sql.replace(" = ", "=")
    assert params == (39, 750, 99)
