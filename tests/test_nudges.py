"""Tests for the nudge policy: hard gates, one daily digest, never re-nudge."""
from __future__ import annotations

import uuid

import pytest

from tests.test_criteria import RoutingCursor

OWNER_A = uuid.UUID("11111111-1111-4111-a111-111111111111")
OWNER_B = uuid.UUID("22222222-2222-4222-a222-222222222222")


def qrow(role_id, fit="High", signal="role-confirmed", title="AI Engineer",
         company="Co", wall="unknown", deadline=None, deadline_source=None):
    return {"role_id": role_id, "fit_rank": fit, "sponsor_signal": signal,
            "role_title": title, "company_name": company, "salary_wall": wall,
            "role_url": f"https://x/{role_id}", "deadline": deadline,
            "deadline_source": deadline_source}


# ---- gates ----

def test_gates_high_fit_and_positive_sponsor_signals_only():
    from notify.nudges import select_nudges
    rows = [
        qrow(1, fit="High", signal="role-confirmed"),      # in
        qrow(2, fit="High", signal="company-confirmed"),   # in
        qrow(3, fit="High", signal="register-only"),       # in
        qrow(4, fit="Med",  signal="role-confirmed"),      # out: fit
        qrow(5, fit="High", signal="role-excluded"),       # out: hard negative
        qrow(6, fit="High", signal="weak"),                # out: no sponsor evidence
    ]
    assert [r["role_id"] for r in select_nudges(rows)] == [1, 2, 3]


# ---- digest ----

def test_digest_is_one_message_capped_with_overflow_count():
    from notify.nudges import digest
    rows = [qrow(i, title=f"Role {i}", company=f"Co{i}") for i in range(1, 8)]
    title, body = digest(rows, limit=5)
    assert title == "7 roles ready to apply"
    assert body.count("\n") == 5                     # 5 lines + overflow note share
    assert "+2 more in the queue" in body
    assert "Co1" in body and "Role 1" in body


# ---- the stage ----

def make_cursor(eligible_rows, channel="ntfy:topic-x"):
    # One profiles route serves both queries the stage now makes: the owner
    # lookup (default_profile_id) and the channel lookup for that owner. The
    # id is a real uuid.UUID because the column is a uuid and psycopg returns
    # one — the fake-it-as-a-string habit is what hid B-GAE-007.
    return RoutingCursor([
        ("from v_apply_queue", eligible_rows),
        ("from profiles", [{"profile_id": OWNER_A,
                            "notification_channel": channel}]),
    ])


def test_load_channel_reads_one_named_profile_not_whichever_is_first():
    # It used to be `order by created_at limit 1` — the founder's row, for
    # every caller. Any second profile's nudges would have gone to his phone.
    from notify.nudges import load_channel
    cur = RoutingCursor([("from profiles",
                          [{"notification_channel": "ntfy:topic-x"}])])

    assert load_channel(cur, OWNER_B) == "ntfy:topic-x"

    sql, params = cur.executed[0]
    assert "where profile_id = %s" in sql
    assert "order by created_at" not in sql
    assert params == (OWNER_B,)


def test_load_channel_cannot_be_called_the_old_ownerless_way():
    # Called exactly as Phase 8.5 called it. Fails against the pre-1b source.
    from notify.nudges import load_channel
    with pytest.raises(TypeError):
        load_channel(RoutingCursor([("from profiles", [])]))


def test_the_nightly_stage_nudges_the_owner_it_was_given_and_only_them():
    # Task 1b made the stage RESOLVE its owner instead of assuming one, and
    # left a note that task 3 would replace that resolution with a per-owner
    # loop. This is that change: the owner is now an argument, so the stage
    # cannot pick one at all — which is B-GAE-027's fix.
    from notify.nudges import nudge_stage
    sent = []
    cur = make_cursor([qrow(1)])

    nudge_stage(cur, send=lambda ch, t, b: sent.append(ch) or True,
                owner_id=OWNER_A)

    assert sent == ["ntfy:topic-x"]
    channel_calls = [(s, p) for s, p in cur.executed
                     if "notification_channel" in s]
    assert len(channel_calls) == 1
    assert channel_calls[0][1] == (OWNER_A,)      # given, not discovered
    # …and the queue it built the digest from was scoped to that owner too.
    queue_calls = [(s, p) for s, p in cur.executed if "v_apply_queue" in s]
    assert queue_calls and queue_calls[0][1] == (OWNER_A,)


def test_nudge_stage_sends_once_and_stamps_only_after_success():
    from notify.nudges import nudge_stage
    sent = []
    cur = make_cursor([qrow(1), qrow(2)])
    out = nudge_stage(cur, send=lambda ch, t, b: sent.append((ch, t, b)) or True,
                      owner_id=OWNER_A)
    assert "2" in out
    assert len(sent) == 1 and sent[0][0] == "ntfy:topic-x"
    stamp_sql = [s for s, p in cur.executed if "nudged_at" in s and "update" in s]
    assert len(stamp_sql) == 1


def test_nudge_stage_nothing_new_is_quiet_success():
    from notify.nudges import nudge_stage
    cur = make_cursor([])
    out = nudge_stage(cur, send=lambda *a: pytest.fail("must not send"),
                      owner_id=OWNER_A)
    assert "nothing" in out.lower()


def test_push_failure_raises_so_the_run_is_marked_failed():
    from notify.nudges import nudge_stage
    cur = make_cursor([qrow(1)])
    with pytest.raises(RuntimeError):
        nudge_stage(cur, send=lambda *a: False, owner_id=OWNER_A)
    # and the listing is NOT stamped — it will be retried next run
    assert not [s for s, p in cur.executed if "nudged_at" in s and "update" in s]


def test_no_channel_is_a_visible_note_not_a_crash():
    from notify.nudges import nudge_stage
    cur = make_cursor([qrow(1)], channel=None)
    out = nudge_stage(cur, send=lambda *a: pytest.fail("must not send"),
                      owner_id=OWNER_A)
    assert "channel" in out.lower()


def test_dry_run_previews_without_sending_or_stamping():
    from notify.nudges import nudge_stage
    cur = make_cursor([qrow(1), qrow(2)])
    out = nudge_stage(cur, send=None, owner_id=OWNER_A, dry_run=True)
    assert "DRY RUN" in out and "2" in out
    assert not [s for s, p in cur.executed if "update" in s]
