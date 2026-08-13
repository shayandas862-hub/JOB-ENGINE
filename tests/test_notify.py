"""Tests for the ntfy push client — a nudge failure must never sink a run."""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
import responses

from notify.push import send_push

# profiles.profile_id is a uuid COLUMN, so psycopg hands back a uuid.UUID —
# faking it as a str is what let B-GAE-007 through review. The fake returns
# the real type.
OWNER_A = uuid.UUID("11111111-1111-4111-a111-111111111111")


def profile_row(channel):
    """A profiles row as the database returns it: both columns, real types."""
    return {"profile_id": OWNER_A, "notification_channel": channel}


@responses.activate
def test_sends_to_the_channel_topic_with_title():
    responses.add(responses.POST, "https://ntfy.sh/goala-secret-topic", status=200)
    ok = send_push("ntfy:goala-secret-topic", "3 roles ready", "Top: AI Engineer at X")
    assert ok is True
    req = responses.calls[0].request
    assert req.headers["Title"] == b"3 roles ready"   # utf-8 encoded by us, not http.client
    assert b"AI Engineer" in req.body


def test_missing_or_unknown_channel_skips_without_http():
    assert send_push(None, "t", "b") is False
    assert send_push("", "t", "b") is False
    assert send_push("email:x@y.z", "t", "b") is False   # only ntfy supported today
    assert send_push("ntfy:", "t", "b") is False


@responses.activate
def test_http_failure_returns_false_never_raises():
    responses.add(responses.POST, "https://ntfy.sh/goala-secret-topic", status=500)
    assert send_push("ntfy:goala-secret-topic", "t", "b") is False


class Latin1Session:
    """Mimics the one step `responses` skips: http.client.putheader encodes a
    str header value as latin-1 when it goes on the wire. That is where the
    live UnicodeEncodeError came from, so a test that never encodes cannot
    catch this bug — it passes against the broken code.
    """

    def __init__(self):
        self.headers = None

    def post(self, url, data=None, headers=None, timeout=None):
        self.headers = headers
        for value in (headers or {}).values():
            if isinstance(value, str):
                value.encode("latin-1")     # raises exactly as the wire does
        return SimpleNamespace(status_code=200)


def test_a_non_ascii_title_sends_instead_of_crashing():
    # Found live 2026-08-09. UnicodeEncodeError is NOT a
    # requests.RequestException, so it escaped the except entirely and took the
    # caller down. send_test's own em-dash title therefore always crashed.
    session = Latin1Session()
    title = "Société Générale —— Ünicode Ltd"

    ok = send_push("ntfy:goala-secret-topic", title, "body", session=session)

    assert ok is True                                    # not a crash, not False
    assert session.headers["Title"] == title.encode("utf-8")   # we encode, not http.client


@responses.activate
def test_an_ascii_title_is_unchanged_on_the_wire():
    responses.add(responses.POST, "https://ntfy.sh/goala-secret-topic", status=200)
    assert send_push("ntfy:goala-secret-topic", "64 roles ready", "b") is True
    sent = responses.calls[0].request.headers["Title"]
    assert (sent.decode("utf-8") if isinstance(sent, bytes) else sent) == "64 roles ready"


def test_notify_failure_pushes_the_failing_stage_names(monkeypatch):
    from notify import push
    from tests.test_criteria import RoutingCursor
    sent = []
    monkeypatch.setattr(push, "send_push",
                        lambda ch, t, b: sent.append((ch, t, b)) or True)
    cur = RoutingCursor([("from profiles", [profile_row("ntfy:x")])])
    push.notify_failure(cur, ["read", "eval"])
    assert len(sent) == 1
    ch, title, body = sent[0]
    assert ch == "ntfy:x"
    assert "failed" in title.lower()
    assert "read" in body and "eval" in body


def test_notify_failure_without_channel_shouts_instead_of_going_quiet(monkeypatch, capsys):
    # Was a silent no-op: an unset channel logged nothing and moved on, so a
    # broken run looked exactly like a clean one. It records the calls rather
    # than raising, because notify_failure now swallows exceptions by design —
    # a throwing guard here would be swallowed too and pass for the wrong reason.
    from notify import push
    from tests.test_criteria import RoutingCursor
    sent = []
    monkeypatch.setattr(push, "send_push", lambda ch, t, b: sent.append(ch) or True)
    cur = RoutingCursor([("from profiles", [profile_row(None)])])

    assert push.notify_failure(cur, ["read"]) is False   # must not raise
    assert sent == []                                    # must not send
    err = capsys.readouterr().err
    assert "read" in err and "UNDELIVERED" in err        # loud, and unlike "all clear"


def test_notify_failure_shouts_when_the_push_is_refused(monkeypatch, capsys):
    # ntfy reachable but refusing: the run still failed and someone must learn
    # of it. Cloud Logging catches what ntfy could not deliver.
    from notify import push
    from tests.test_criteria import RoutingCursor
    monkeypatch.setattr(push, "send_push", lambda ch, t, b: False)
    cur = RoutingCursor([("from profiles", [profile_row("ntfy:x")])])

    assert push.notify_failure(cur, ["read", "eval"]) is False
    err = capsys.readouterr().err
    assert "read, eval" in err and "UNDELIVERED" in err


def test_notify_failure_never_raises_even_when_the_alert_path_itself_breaks(
        monkeypatch, capsys):
    # It runs BEFORE finish_run — an exception escaping here loses the run
    # report too, so the whole run would go unrecorded AND unreported.
    from notify import push
    from tests.test_criteria import RoutingCursor
    monkeypatch.setattr(push, "send_push",
                        lambda *a: (_ for _ in ()).throw(RuntimeError("ntfy exploded")))
    cur = RoutingCursor([("from profiles", [profile_row("ntfy:x")])])

    assert push.notify_failure(cur, ["read"]) is False
    err = capsys.readouterr().err
    assert "ntfy exploded" in err and "UNDELIVERED" in err


def test_notify_failure_says_nothing_extra_when_the_push_succeeds(monkeypatch, capsys):
    # The shout must mean something: silence on success is what makes it signal.
    from notify import push
    from tests.test_criteria import RoutingCursor
    monkeypatch.setattr(push, "send_push", lambda ch, t, b: True)
    cur = RoutingCursor([("from profiles", [profile_row("ntfy:x")])])

    assert push.notify_failure(cur, ["read"]) is True
    assert "UNDELIVERED" not in capsys.readouterr().err


# ---- test nudge (Phase 5: the send_test_nudge tool) ----

def test_send_test_reports_sent_without_ever_returning_the_channel(monkeypatch):
    from notify import push
    from tests.conftest import FakeCursor
    monkeypatch.setattr(push, "send_push", lambda ch, t, b: True)
    cur = FakeCursor(rows=[profile_row("ntfy:secret-topic")])

    out = push.send_test(cur, OWNER_A)

    assert out == {"channel_configured": True, "sent": True}
    assert "secret-topic" not in str(out)       # the channel/topic is a secret — never returned


def test_send_test_without_a_channel_does_not_send(monkeypatch):
    from notify import push
    from tests.conftest import FakeCursor
    monkeypatch.setattr(push, "send_push",
                        lambda *a: (_ for _ in ()).throw(AssertionError("no send")))
    cur = FakeCursor(rows=[profile_row(None)])
    assert push.send_test(cur, OWNER_A) == {"channel_configured": False, "sent": False}


def test_send_test_pushes_to_the_calling_owners_channel_and_no_one_elses(monkeypatch):
    # The sharpest hole task 1a left open: send_test_nudge reached
    # load_channel, which read the FIRST profile's channel regardless of who
    # called. A friend's key would therefore fire a push at the founder's
    # phone — the one unscoped call with an effect outside the database.
    from notify import push
    from tests.conftest import FakeCursor
    monkeypatch.setattr(push, "send_push", lambda ch, t, b: True)
    other = uuid.UUID("22222222-2222-4222-a222-222222222222")
    cur = FakeCursor(rows=[profile_row("ntfy:x")])

    push.send_test(cur, other)

    sql, params = cur.executed[0]
    assert "where profile_id = %s" in sql.lower()   # asked for one profile, by id
    assert params == (other,)                       # and it was the CALLER's


def test_send_test_cannot_be_called_the_old_ownerless_way():
    # Called exactly as Phase 8.5 called it. Fails against the pre-1b source.
    from notify import push
    from tests.conftest import FakeCursor
    with pytest.raises(TypeError):
        push.send_test(FakeCursor(rows=[profile_row("ntfy:x")]))
