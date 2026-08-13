"""B-GAE-048 — the stranger gate moves out of a dashboard and into the code.

The finding: "the stranger tier is switched OFF" was held by the Google
provider being disabled, while EMAIL sign-up stood open on the same project.
Google was never the gate. The property that decides it is *can a member of
the public obtain a Supabase-signed JWT for this project*, and email sign-up
answers yes. The door then verified that token correctly — it genuinely is
this project's token — and `owner_for_auth_user` created a profile on sight.

So the rule lived somewhere no test could see it. Nothing in this suite went
red on the day email sign-up was switched on, and nothing would have.

This file is that missing guard. The contract it holds:

* **CREATION is gated; RESOLUTION is not.** An already-known identity always
  resolves, gate open or shut — otherwise closing the gate would lock out
  every existing owner, which is a far worse failure than the one being
  fixed and exactly the kind of over-correction that gets reverted in a hurry.
* **The default is SHUT.** A missing or malformed setting means closed. A
  gate that opens when its configuration is absent is not a gate, and the
  deployed service sets no such variable today.
"""
from __future__ import annotations

import pytest

from auth.signin import RegistrationClosed, owner_for_auth_user, self_serve_open
from tests.conftest import ScriptedCursor

KNOWN_SUB = "google-oauth2|already-here"
NEW_SUB = "email|stranger-off-the-internet"
EXISTING_OWNER = "11111111-1111-1111-1111-111111111111"


def _cursor(*, found: bool) -> ScriptedCursor:
    """A cursor whose profile lookup either finds an owner or does not."""
    return ScriptedCursor([
        ("from profiles", [[{"profile_id": EXISTING_OWNER}] if found else []]),
    ])


# --- the switch itself -----------------------------------------------------

def test_the_gate_is_shut_when_nothing_is_configured(monkeypatch):
    # The property that matters most. The deployed service sets no such
    # variable, so "absent" is the state that is actually live tonight.
    monkeypatch.delenv("SELF_SERVE_SIGNUP", raising=False)
    assert self_serve_open({}) is False
    assert self_serve_open() is False


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on", " 1 "])
def test_the_gate_opens_only_on_a_deliberate_yes(value):
    assert self_serve_open({"SELF_SERVE_SIGNUP": value}) is True


@pytest.mark.parametrize("value", ["", "0", "false", "no", "off", "maybe",
                                   "  ", "2", "disabled", "null", "None"])
def test_anything_that_is_not_a_yes_leaves_the_gate_shut(value):
    # Deliberately an allowlist, not a blocklist: an unrecognised value is a
    # typo in a deployment, and a typo must fail SHUT. "2" and "None" are here
    # because both are the kind of thing a hurried edit produces, and a
    # truthiness check would have opened the door on both.
    assert self_serve_open({"SELF_SERVE_SIGNUP": value}) is False


# --- resolution: never gated ----------------------------------------------

def test_an_existing_owner_still_gets_in_while_the_gate_is_shut():
    # The half that must NOT change. Closing the door on strangers cannot
    # close it on the people already inside.
    cur = _cursor(found=True)
    owner, created = owner_for_auth_user(cur, KNOWN_SUB, email="a@b.c",
                                         env={})
    assert (owner, created) == (EXISTING_OWNER, False)


def test_resolving_a_known_owner_writes_nothing_at_all():
    # A read path that inserts is how a "harmless" lookup becomes a write.
    cur = _cursor(found=True)
    owner_for_auth_user(cur, KNOWN_SUB, email="a@b.c", env={})
    assert not any("insert" in sql.lower() for sql, _ in cur.executed), \
        f"the lookup wrote something: {cur.executed}"


# --- creation: gated -------------------------------------------------------

def test_a_stranger_is_refused_when_the_gate_is_shut():
    cur = _cursor(found=False)
    with pytest.raises(RegistrationClosed):
        owner_for_auth_user(cur, NEW_SUB, email="stranger@example.invalid",
                            env={})


def test_a_refused_stranger_leaves_no_row_and_no_savepoint_behind():
    # The refusal must happen BEFORE any write is attempted. A gate that
    # inserts and then rolls back still burns a sequence value and still
    # touches the table it was meant to protect.
    cur = _cursor(found=False)
    with pytest.raises(RegistrationClosed):
        owner_for_auth_user(cur, NEW_SUB, email="stranger@example.invalid",
                            env={})
    wrote = [sql for sql, _ in cur.executed
             if any(word in sql.lower()
                    for word in ("insert", "savepoint"))]
    assert wrote == [], f"the refusal still touched the database: {wrote}"


def test_a_stranger_is_admitted_when_the_founder_opens_the_gate():
    # The tier is BUILT, and this proves the switch turns it on rather than
    # the feature having been deleted — the failure mode where a gate is
    # "closed" because the thing behind it no longer works at all.
    cur = ScriptedCursor([
        ("from profiles", [[], [{"profile_id": EXISTING_OWNER}]]),
        ("insert into profiles", [[{"profile_id": "new"}]]),
    ])
    owner, created = owner_for_auth_user(
        cur, NEW_SUB, email="welcome@example.invalid",
        env={"SELF_SERVE_SIGNUP": "1"})
    assert created is True
    assert owner and owner != EXISTING_OWNER
    assert any("insert into profiles" in sql.lower() for sql, _ in cur.executed)


def test_the_refusal_names_the_setting_that_would_change_it():
    # An operator reading this in a log must be able to act on it. A bare
    # "forbidden" sends them into the auth provider's dashboard, which is
    # precisely the wrong place — that is the whole point of B-GAE-048.
    cur = _cursor(found=False)
    with pytest.raises(RegistrationClosed) as caught:
        owner_for_auth_user(cur, NEW_SUB, env={})
    assert "SELF_SERVE_SIGNUP" in str(caught.value)
