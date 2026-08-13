"""Tests for src/history — fingerprints, field-level diffs, and event planning."""
from __future__ import annotations

import pytest

from tests.conftest import FakeCursor

OWNER_A = "11111111-1111-4111-a111-111111111111"


class Job:
    def __init__(self, title, location, url="https://x/1", jd_text="jd", salary_text=None):
        self.title, self.location, self.url = title, location, url
        self.jd_text, self.salary_text = jd_text, salary_text


def row(role_id, status="open", title="AI Engineer", location="London, UK",
        salary_text=None, jd="jd", fp=None):
    from history.fingerprint import fingerprint
    return {
        "role_id": role_id, "role_status": status,
        "role_title": title, "location": location,
        "salary_text": salary_text, "jd_full": jd,
        "content_fingerprint": fp or fingerprint(title, location, salary_text, jd),
    }


# ---- fingerprint ----

def test_fingerprint_is_stable_and_content_sensitive():
    from history.fingerprint import fingerprint
    a = fingerprint("AI Engineer", "London, UK", None, "Build things.")
    b = fingerprint("  AI   Engineer ", "london, uk", None, "Build things.")
    c = fingerprint("AI Engineer", "London, UK", None, "Build OTHER things.")
    assert a == b            # normalisation-insensitive
    assert a != c            # description change changes it


# ---- field diffs ----

def test_diff_reports_changed_fields_with_old_and_new():
    from history.fingerprint import diff_fields
    old = {"title": "AI Engineer", "location": "London, UK",
           "salary_text": "£60,000", "jd_text": "Build things."}
    new = {"title": "Senior AI Engineer", "location": "London, UK",
           "salary_text": "£70,000", "jd_text": "Build things."}
    d = diff_fields(old, new)
    assert d["title"] == {"old": "AI Engineer", "new": "Senior AI Engineer"}
    assert d["salary_text"] == {"old": "£60,000", "new": "£70,000"}
    assert "location" not in d and "description" not in d


def test_diff_description_reports_lengths_not_full_text():
    from history.fingerprint import diff_fields
    old = {"title": "T", "location": "L", "salary_text": None, "jd_text": "short"}
    new = {"title": "T", "location": "L", "salary_text": None, "jd_text": "a much longer description"}
    d = diff_fields(old, new)
    assert d == {"description": {"old_len": 5, "new_len": 25}}


# ---- event planning ----

def plan(existing_rows, jobs):
    from fetch.feeds import dedupe_key
    from history.events import plan_events
    existing = {r["dedupe_key"]: r for r in existing_rows}
    keyed = [(dedupe_key("Co", j.title, j.url), j) for j in jobs]
    return plan_events("Co", existing, keyed)


def keyed_row(role_id, job, **kw):
    from fetch.feeds import dedupe_key
    r = row(role_id, title=job.title, location=job.location,
            jd=kw.pop("jd", job.jd_text), **kw)
    r["dedupe_key"] = dedupe_key("Co", job.title, job.url)
    return r


def test_new_listing_plans_appeared():
    events = plan([], [Job("AI Engineer", "London, UK")])
    assert len(events) == 1
    e = events[0]
    assert e.event_type == "appeared" and e.role_id is None and e.changes is None


def test_unchanged_listing_plans_nothing():
    j = Job("AI Engineer", "London, UK")
    events = plan([keyed_row(1, j)], [j])
    assert events == []


def test_content_change_plans_changed_with_diff():
    old_job = Job("AI Engineer", "London, UK", jd_text="old text")
    new_job = Job("AI Engineer", "London, UK", jd_text="new different text")
    events = plan([keyed_row(1, old_job)], [new_job])
    assert len(events) == 1
    e = events[0]
    assert e.event_type == "changed" and e.role_id == 1
    assert "description" in e.changes


def test_record_events_batch_inserts_and_resolves_new_role_ids():
    from history.events import PlannedEvent, record_events
    cur = FakeCursor(rows=[{"dedupe_key": "k-new", "role_id": 42}])
    events = [
        PlannedEvent(role_id=None, dedupe_key="k-new", event_type="appeared",
                     changes=None, reset_read=False),
        PlannedEvent(role_id=7, dedupe_key="k-old", event_type="changed",
                     changes={"title": {"old": "a", "new": "b"}}, reset_read=False),
    ]
    n = record_events(cur, events, run_id=99, company_id=5)
    assert n == 2
    # 0058/B-GAE-018: dedupe_key is unique per company, so resolving a key to
    # a role_id without naming the company can now match another owner's
    # listing and attach this owner's event to it.
    lookup = next(s for s, _ in cur.executed if "from role_listings" in s)
    assert "company_id = %s" in lookup, \
        "the dedupe_key -> role_id lookup is not scoped to one company"
    insert_sql, rows_ = cur.executed_many[0]
    assert "listing_events" in insert_sql
    assert [r[0] for r in rows_] == [42, 7]          # appeared got its real role_id
    assert rows_[0][1] == "appeared" and rows_[1][1] == "changed"
    assert all(r[-1] == 99 for r in rows_)


def test_record_closed_events_batch():
    from history.events import record_closed
    cur = FakeCursor()
    n = record_closed(cur, [10, 11], run_id=99)
    assert n == 2
    sql, rows_ = cur.executed_many[0]
    assert "listing_events" in sql
    assert rows_ == [(10, "closed", None, 99), (11, "closed", None, 99)]
    assert record_closed(FakeCursor(), [], run_id=99) == 0


# ---- reopened listings (Task 3) ----

def test_closed_listing_seen_again_plans_reopened_not_duplicate():
    j = Job("AI Engineer", "London, UK")
    events = plan([keyed_row(1, j, status="closed")], [j])
    assert len(events) == 1                       # one event, no duplicate row logic
    e = events[0]
    assert e.event_type == "reopened" and e.role_id == 1
    assert e.changes is None                      # came back unchanged


def test_closed_listing_back_with_changes_is_one_reopened_event_with_diff():
    old_job = Job("AI Engineer", "London, UK", jd_text="old text")
    new_job = Job("AI Engineer", "London, UK", jd_text="brand new text")
    events = plan([keyed_row(1, old_job, status="closed")], [new_job])
    assert [e.event_type for e in events] == ["reopened"]   # never reopened+changed pair
    assert "description" in events[0].changes
    assert events[0].reset_read is True           # description changed -> re-read


# ---- change-triggered re-reads (Task 5): only a DESCRIPTION change re-bills ----

def test_salary_change_never_resets_the_read():
    old_job = Job("AI Engineer", "London, UK", jd_text="same text", salary_text="£60,000")
    new_job = Job("AI Engineer", "London, UK", jd_text="same text", salary_text="£70,000")
    events = plan([keyed_row(1, old_job, salary_text="£60,000")], [new_job])
    assert len(events) == 1 and events[0].event_type == "changed"
    assert "salary_text" in events[0].changes
    assert events[0].reset_read is False          # no new description -> no new AI spend


def test_retitled_job_is_a_new_identity_not_a_change():
    # dedupe_key includes the title: a retitle = new listing appears, old one
    # rot-closes later. Pinned so nobody "fixes" this into silent renames.
    old_job = Job("AI Engineer", "London, UK", jd_text="same text")
    new_job = Job("Senior AI Engineer", "London, UK", jd_text="same text")
    events = plan([keyed_row(1, old_job)], [new_job])
    assert [e.event_type for e in events] == ["appeared"]


def test_description_change_resets_only_that_listing():
    changed_old = Job("AI Engineer", "London, UK", url="https://x/1", jd_text="old")
    changed_new = Job("AI Engineer", "London, UK", url="https://x/1", jd_text="completely new")
    untouched = Job("ML Engineer", "London, UK", url="https://x/2", jd_text="stable")
    events = plan(
        [keyed_row(1, changed_old), keyed_row(2, untouched)],
        [changed_new, untouched])
    assert [(e.role_id, e.reset_read) for e in events] == [(1, True)]

    from history.events import reset_reads
    cur = FakeCursor()
    assert reset_reads(cur, events) == 1
    sql, params = cur.executed[0]
    assert "extracted_at = null" in sql and params == ([1],)


def test_unchanged_listings_produce_no_reset_and_no_events():
    j = Job("AI Engineer", "London, UK")
    events = plan([keyed_row(1, j)], [j])
    from history.events import reset_reads
    cur = FakeCursor()
    assert events == [] and reset_reads(cur, events) == 0
    assert cur.executed == []                     # zero SQL: re-runs are free


# ---- reading a listing's story (Phase 5: the MCP get_job_history tool) ----

def test_history_for_role_reads_its_events_newest_first_with_a_limit():
    from history.events import history_for_role
    rows = [{"event_id": 5, "event_type": "changed", "occurred_at": "2026-07-10T09:00:00",
             "changes": {"salary_text": {"old": "£50k", "new": "£55k"}}, "run_id": 3}]
    cur = FakeCursor(rows=rows)

    out = history_for_role(cur, OWNER_A, 917, limit=50)

    assert out == rows                             # rows pass straight through
    sql, params = cur.executed[0]
    low = sql.lower()
    assert "from listing_events" in low
    assert "e.role_id = %s" in low
    assert "order by e.occurred_at desc" in low    # the life story, most recent first
    assert params == (917, OWNER_A, 50)


def test_history_for_role_reaches_its_owner_through_the_company_join():
    # listing_events has no owner column and neither does role_listings, so
    # this is the longest walk to an owner in the codebase: event -> listing
    # -> company -> owner. Without it, a listing id is enough to read another
    # owner's salary changes and closure dates.
    from history.events import history_for_role
    cur = FakeCursor(rows=[])

    history_for_role(cur, OWNER_A, 917)

    sql, params = cur.executed[0]
    low = sql.lower()
    assert "join role_listings" in low
    assert "join target_companies" in low
    assert "c.owner_id = %s" in low
    assert params == (917, OWNER_A, 50)


def test_history_for_role_cannot_be_called_the_old_ownerless_way():
    # Called exactly as Phase 8.5 called it. Fails against the pre-1b source.
    from history.events import history_for_role
    with pytest.raises(TypeError):
        history_for_role(FakeCursor(rows=[]), role_id=917)
