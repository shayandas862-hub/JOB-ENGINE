"""Access keys — mint, resolve, revoke (Phase 9 task 1).

A key is 256 bits of randomness handed over ONCE. The database keeps only its
SHA-256, so a leaked dump is a set of digests rather than a set of working
keys; the 0050 check constraint makes storing anything else impossible. No
KDF here on purpose — a random 256-bit key is not a password and cannot be
guessed, so bcrypt/argon would buy nothing and cost a hash on every request.

Resolution answers one question: whose data is this call for? It answers None
for anything unknown, revoked or blank — never a default, never a guess. That
"never a guess" is the whole point of the task: the old door stamped every
request "founder", which is a guess that happened to be right while there was
one user.
"""
from __future__ import annotations

import hashlib
import secrets

KEY_BYTES = 32                      # 256 bits, urlsafe-encoded to ~43 chars

# What an operator may see about a key. token_sha256 is deliberately absent:
# an operator listing keys must not be handed a digest to grind offline.
_PUBLIC_COLUMNS = ("key_id, owner_id::text as owner_id, label, created_at, "
                   "last_used_at, revoked_at")


def new_key() -> str:
    """A fresh key. Shown once, at mint, and never recoverable afterwards."""
    return secrets.token_urlsafe(KEY_BYTES)


def hash_key(key: str) -> str:
    """The digest stored in place of the key."""
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def mint_key(cur, owner_id: str, *, label: str) -> dict:
    """Mint a key for one owner. Returns {key_id, key, label} — `key` is the
    only time the secret exists outside the holder's hands."""
    key = new_key()
    cur.execute(
        "insert into access_keys (owner_id, token_sha256, label) "
        "values (%s,%s,%s) returning key_id",
        (owner_id, hash_key(key), label))
    return {"key_id": cur.fetchone()["key_id"], "key": key, "label": label}


def owner_for_key(cur, key: str | None) -> str | None:
    """The owner a presented key belongs to, or None.

    A blank key never reaches the database — a missing Authorization header
    must be refused by the door, not by a query that could match an
    empty-string row. The lookup stamps last_used_at in the same statement,
    so the operator signal costs no extra round trip.
    """
    if not key:
        return None
    cur.execute(
        "update access_keys set last_used_at = now() "
        "where token_sha256 = %s and revoked_at is null "
        "returning owner_id::text as owner_id",
        (hash_key(key),))
    row = cur.fetchone()
    return row["owner_id"] if row else None


def revoke_key(cur, key_id: int) -> dict:
    """Stamp a key revoked. Keep-all: the row stays, so the record of who
    held it and when it was pulled survives. Revoking twice is a no-op."""
    cur.execute(
        "update access_keys set revoked_at = now() "
        "where key_id = %s and revoked_at is null "
        f"returning {_PUBLIC_COLUMNS}",
        (key_id,))
    row = cur.fetchone()
    return {"key_id": key_id, "outcome": "revoked" if row else "not_live"}


def revoke_key_for_owner(cur, key_id: int, owner_id: str) -> dict:
    """Revoke a key the caller actually owns (Phase 9 task 6).

    The owner is in the WHERE clause, not in a check before it: a self-serve
    tool takes a key_id from whoever is calling, and "look it up, compare, then
    update" is two statements with a gap in the middle. Under the app role RLS
    would hide another owner's row anyway — this does not lean on that, because
    a caller on a different connection would inherit a tool that trusts its
    argument.

    "Not yours", "no such key" and "already revoked" all answer `not_live`, on
    purpose: a distinct answer for the first would turn this into a way to find
    out which key ids exist.
    """
    cur.execute(
        "update access_keys set revoked_at = now() "
        "where key_id = %s and owner_id = %s and revoked_at is null "
        f"returning {_PUBLIC_COLUMNS}",
        (key_id, owner_id))
    row = cur.fetchone()
    return {"key_id": key_id, "outcome": "revoked" if row else "not_live"}


def list_keys(cur, owner_id: str | None = None) -> list[dict]:
    """Every key, or one owner's, newest first — never a digest."""
    if owner_id:
        cur.execute(f"select {_PUBLIC_COLUMNS} from access_keys "
                    "where owner_id = %s order by created_at desc", (owner_id,))
    else:
        cur.execute(f"select {_PUBLIC_COLUMNS} from access_keys "
                    "order by created_at desc")
    return [{k: v for k, v in row.items() if k != "token_sha256"}
            for row in cur.fetchall()]
