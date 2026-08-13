"""A verified sign-in becomes an owner of this engine (Phase 9 task 6).

The door verifies that a JWT is genuine — signature, issuer, audience, expiry.
That answers WHO SIGNED IN, in the identity provider's terms. It does not
answer whose queue, tray, CV and budget the request is for; that is this
engine's own question, and `profiles` has always been where it is answered.
This module is the join, and the only place the two ids meet.

Two rules hold it together:

* **The provider's subject is never our owner id.** `sub` is an opaque
  identifier minted by somebody else's system for their own reasons. It is
  recorded on the profile as the identity the owner came in from; the owner id
  stays ours, so nothing downstream depends on the provider's choices.
* **First sight creates exactly once.** Two first requests arriving together
  both read "no such user" and both insert. The unique index decides, not the
  read — so the loser rolls back to a savepoint and re-reads, and comes back
  with the winner's profile rather than an error or a second identity. Without
  the savepoint the failed insert would abort the whole transaction and the
  request would die on a race it should have absorbed.

Nothing here is secret and nothing here is trusted: this is only ever reached
after the door has verified the token, and `email`/`name` are the provider's
own claims about its user, written to that user's own row.

**The registration gate (B-GAE-048).** Verifying a token answers "is this
person real to the identity provider", never "may this person become an owner
of this engine". Those were treated as one question, and the second was
answered in a hosted dashboard instead: the stranger tier counted as OFF
because the Google provider was disabled — while EMAIL sign-up stood open on
the same project, minting tokens this door then verified perfectly correctly,
because they genuinely are this project's tokens.

So the gate lives here now, where a test can see it. CREATION is gated;
RESOLUTION never is — an owner who already exists always gets in, because
closing the door on strangers must not close it on the people already inside.
The default is SHUT: an absent or unrecognised setting means closed, since a
gate that opens when its configuration goes missing is not a gate.
"""
from __future__ import annotations

import os
from uuid import uuid4

import psycopg

from criteria.profiles import insert_profile

_LOOKUP = ("select profile_id::text as profile_id from profiles "
           "where auth_user_id = %s")

_SAVEPOINT = "first_sign_in"

#: The one setting that admits strangers. Absent on the deployed service.
SELF_SERVE_ENV = "SELF_SERVE_SIGNUP"

# An ALLOWLIST of yeses, not a truthiness check. "2", "None" and "disabled"
# are all truthy strings, and every one of them is what a hurried deployment
# edit looks like — each must fail shut rather than open the engine.
_YES = frozenset({"1", "true", "yes", "on"})


class RegistrationClosed(RuntimeError):
    """A verified stranger, refused because self-serve sign-up is off.

    Deliberately not the same thing as a bad token. The credential was
    genuine; the engine simply does not accept new owners right now, and an
    operator reading this in a log needs to be sent to the setting that
    changes it rather than into the identity provider's dashboard.
    """


def self_serve_open(env=None) -> bool:
    """May a verified stranger become a new owner? Default no."""
    source = os.environ if env is None else env
    return (source.get(SELF_SERVE_ENV) or "").strip().lower() in _YES


def _display_name(email: str | None, name: str | None) -> str:
    """What to call them until they say. Derived, never invented.

    Google hands Supabase a full name and it rides in the token's user
    metadata; when it is missing, the email's local part is the closest thing
    to a name we were actually given. The owner replaces it during intake.
    """
    if name and name.strip():
        return name.strip()
    if email and "@" in email:
        return email.split("@", 1)[0]
    return email.strip() if email else "New owner"


def owner_for_auth_user(cur, auth_user_id, *, email=None,
                        name=None, env=None) -> tuple[str, bool]:
    """The profile a verified identity belongs to — created on first sight,
    and only when self-serve registration is open.

    Returns ``(owner_id, created)``. `created` is for the caller's audit and
    log lines: a first sign-in is a real event, and a door that cannot tell it
    from a returning user cannot report one.

    Raises `RegistrationClosed` for an unknown identity while the gate is
    shut. The refusal happens BEFORE any write is attempted — a gate that
    inserts and then rolls back has still touched the table it exists to
    protect, and still burned a sequence value doing it.
    """
    cur.execute(_LOOKUP, (str(auth_user_id),))
    row = cur.fetchone()
    if row:
        return row["profile_id"], False

    if not self_serve_open(env):
        raise RegistrationClosed(
            "this engine is not accepting new owners: a verified sign-in is "
            "not by itself an invitation. Set "
            f"{SELF_SERVE_ENV}=1 on the MCP service to open self-serve "
            "registration, or have the operator create the profile and mint "
            "a key. (B-GAE-048: this gate is deliberately here and not in "
            "the auth provider's dashboard, where no test can see it.)")

    new_id = str(uuid4())
    cur.execute(f"savepoint {_SAVEPOINT}")
    try:
        insert_profile(cur, new_id, _display_name(email, name), email,
                       auth_user_id=str(auth_user_id))
    except psycopg.errors.UniqueViolation:
        # Somebody else's request created this identity between our read and
        # our insert. Theirs is the profile; ours never existed.
        cur.execute(f"rollback to savepoint {_SAVEPOINT}")
        cur.execute(_LOOKUP, (str(auth_user_id),))
        row = cur.fetchone()
        if row is None:
            raise                      # a different unique column, not a race
        return row["profile_id"], False
    cur.execute(f"release savepoint {_SAVEPOINT}")
    return new_id, True
