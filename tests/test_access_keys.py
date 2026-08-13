"""Friend-tier access keys — the key store (Phase 9 task 1).

A key is a random secret shown ONCE at mint; the database keeps only its
SHA-256, so a database that leaks does not leak anybody's key. Resolution
answers exactly one question — whose data is this call for? — and answers
"nobody" for anything unknown, revoked, or blank.

Offline by default (fake cursors). The revocation and cross-owner proofs are
opt-in (RUN_DB_TESTS=1) and run against a scratch schema built from the real
migration DDL, then dropped: a revocation test that never revokes anything,
and an isolation test that never mints a second owner, prove nothing.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from tests.conftest import FakeCursor

OWNER_A = "11111111-1111-4111-a111-111111111111"
OWNER_B = "22222222-2222-4222-a222-222222222222"


# --- the key itself ------------------------------------------------------

def test_a_new_key_is_long_random_and_never_repeats():
    # KEY_BYTES is pinned, not just "long enough": >= 32 CHARACTERS would keep
    # passing if the entropy were quietly halved to 16 bytes, which is exactly
    # the change this test exists to stop.
    from auth.tokens import KEY_BYTES, new_key
    assert KEY_BYTES == 32, "256 bits is the contract; shrinking it needs a decision"
    keys = {new_key() for _ in range(50)}
    assert len(keys) == 50, "keys repeated — the source is not random"
    # urlsafe base64 of 32 bytes is 43 chars; anything shorter lost entropy
    assert all(len(k) >= 43 for k in keys), "a short key is a guessable key"


def test_hashing_is_stable_for_one_key_and_different_for_another():
    from auth.tokens import hash_key
    assert hash_key("abc") == hash_key("abc")
    assert hash_key("abc") != hash_key("abd")
    assert len(hash_key("abc")) == 64            # sha-256 hex


def test_the_database_never_sees_the_key_itself():
    # The one property everything else rests on. If the raw key reaches any
    # parameter, a database dump becomes a set of working keys.
    from auth.tokens import hash_key, mint_key
    cur = FakeCursor(rows=[{"key_id": 7}])
    minted = mint_key(cur, OWNER_A, label="friend-laptop")

    assert minted["key"] and minted["key_id"] == 7
    written = " ".join(f"{sql} {params}" for sql, params in cur.executed)
    assert minted["key"] not in written, "the raw key was written to the DB"
    assert hash_key(minted["key"]) in written, "the hash was not written"


# --- resolution ----------------------------------------------------------

def test_a_key_resolves_to_the_owner_it_was_minted_for():
    from auth.tokens import owner_for_key
    cur = FakeCursor(rows=[{"owner_id": OWNER_B}])
    assert owner_for_key(cur, "some-key") == OWNER_B


def test_a_key_nobody_holds_resolves_to_nobody():
    from auth.tokens import owner_for_key
    assert owner_for_key(FakeCursor(rows=[]), "not-a-key") is None


def test_a_blank_key_never_even_reaches_the_database():
    # A missing Authorization header must be refused by the door, not by a
    # query that could match an empty-string row.
    from auth.tokens import owner_for_key
    cur = FakeCursor(rows=[{"owner_id": OWNER_A}])
    assert owner_for_key(cur, "") is None
    assert owner_for_key(cur, None) is None
    assert cur.executed == [], "a blank key was sent to the database"


def test_resolution_looks_up_the_hash_and_excludes_revoked_keys():
    # Pins the two clauses the whole gate depends on. (The proof that
    # revocation actually bites is the DB test below — this only pins intent.)
    from auth.tokens import hash_key, owner_for_key
    cur = FakeCursor(rows=[{"owner_id": OWNER_A}])
    owner_for_key(cur, "k")
    sql, params = cur.executed[0]
    assert "revoked_at is null" in sql
    assert hash_key("k") in str(params)
    assert "k" not in (params or ()), "the raw key was sent as a parameter"


def test_revoking_a_key_is_a_stamp_never_a_delete():
    # Keep-all: the row stays, so "who held a key and when was it pulled"
    # survives the revocation.
    from auth.tokens import revoke_key
    cur = FakeCursor(rows=[{"key_id": 3, "revoked_at": "now"}])
    revoke_key(cur, 3)
    sql = cur.executed[0][0].lower()
    assert sql.startswith("update")
    assert "revoked_at" in sql
    assert "delete" not in sql


def test_listing_keys_never_returns_a_hash_or_a_key():
    # An operator listing keys (task 7's runbook) must not be handed material
    # that could be replayed, nor a hash to grind offline.
    # The cursor is deliberately poisoned with a digest column: a list that
    # simply passes its rows through fails here, which is the point.
    from auth.tokens import list_keys
    cur = FakeCursor(rows=[{"key_id": 1, "owner_id": OWNER_A,
                            "label": "friend-laptop", "created_at": "t",
                            "last_used_at": None, "revoked_at": None,
                            "token_sha256": "a" * 64}])
    rows = list_keys(cur)
    assert rows and all("token_sha256" not in r for r in rows)
    assert "token_sha256" not in cur.executed[0][0]


# --- the proofs that need a real database --------------------------------

DB_ONLY = pytest.mark.skipif(
    os.getenv("RUN_DB_TESTS") != "1",
    reason="DB integration tests are opt-in: RUN_DB_TESTS=1")

SCHEMA = "ak_keys_test"


@DB_ONLY
def test_a_key_resolves_to_its_own_owner_then_stops_dead_when_revoked():
    # Everything the offline tests can only assert about SQL text, proven by
    # doing it: two owners, two keys, each resolving to its own owner and
    # never the other's — then a revoke, and the same key resolving to
    # nobody. Runs in a scratch schema built from the real 0050 DDL and drops
    # it; production tables are never touched.
    from auth.tokens import mint_key, owner_for_key, revoke_key
    from db.connection import get_conn

    ddl = (Path(__file__).parents[1] / "db" / "migrations"
           / "0050_access_keys.sql").read_text()
    # search_path points at the scratch schema, so the schema qualifier goes;
    # columns, constraints and indexes are the real ones.
    ddl = ddl.replace("public.", "")

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f"drop schema if exists {SCHEMA} cascade")
            cur.execute(f"create schema {SCHEMA}")
            cur.execute(f"set search_path to {SCHEMA}")
            cur.execute("create table profiles "
                        "(like public.profiles including all)")
            cur.execute("insert into profiles (profile_id, name) values "
                        "(%s,'A'),(%s,'B')", (OWNER_A, OWNER_B))
            cur.execute(ddl)

            a = mint_key(cur, OWNER_A, label="owner-a-key")
            b = mint_key(cur, OWNER_B, label="owner-b-key")

            # each key knows its own owner, and only its own
            assert owner_for_key(cur, a["key"]) == OWNER_A
            assert owner_for_key(cur, b["key"]) == OWNER_B
            assert owner_for_key(cur, a["key"]) != OWNER_B

            # the key itself is nowhere in the table — only its digest
            cur.execute("select token_sha256 from access_keys")
            stored = [r["token_sha256"] for r in cur.fetchall()]
            assert a["key"] not in stored and b["key"] not in stored
            assert all(len(s) == 64 for s in stored)

            # a revoked key is dead, and its neighbour is untouched
            revoke_key(cur, a["key_id"])
            assert owner_for_key(cur, a["key"]) is None
            assert owner_for_key(cur, b["key"]) == OWNER_B

            # and the row survived the revocation (keep-all)
            cur.execute("select count(*) as n from access_keys")
            assert cur.fetchone()["n"] == 2

            cur.execute(f"drop schema {SCHEMA} cascade")
        conn.rollback()


@DB_ONLY
def test_the_key_column_refuses_anything_that_is_not_a_digest():
    # The check constraint is the structural guarantee that no code path —
    # not even a future one written in a hurry — can store a plaintext key.
    import psycopg
    from db.connection import get_conn

    ddl = (Path(__file__).parents[1] / "db" / "migrations"
           / "0050_access_keys.sql").read_text().replace("public.", "")
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f"drop schema if exists {SCHEMA}_chk cascade")
            cur.execute(f"create schema {SCHEMA}_chk")
            cur.execute(f"set search_path to {SCHEMA}_chk")
            cur.execute("create table profiles "
                        "(like public.profiles including all)")
            cur.execute("insert into profiles (profile_id, name) values (%s,'A')",
                        (OWNER_A,))
            cur.execute(ddl)
            with pytest.raises(psycopg.errors.CheckViolation):
                cur.execute("insert into access_keys (owner_id, token_sha256, "
                            "label) values (%s, 'a-plaintext-looking-key', 'x')",
                            (OWNER_A,))
        conn.rollback()


@DB_ONLY
def test_a_key_row_without_an_owner_fails_loudly():
    # No single-user DEFAULT here (the 0018 debt task 2 clears elsewhere): an
    # unstamped key must not quietly become the founder's.
    import psycopg
    from db.connection import get_conn

    ddl = (Path(__file__).parents[1] / "db" / "migrations"
           / "0050_access_keys.sql").read_text().replace("public.", "")
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f"drop schema if exists {SCHEMA}_own cascade")
            cur.execute(f"create schema {SCHEMA}_own")
            cur.execute(f"set search_path to {SCHEMA}_own")
            cur.execute("create table profiles "
                        "(like public.profiles including all)")
            cur.execute(ddl)
            with pytest.raises(psycopg.errors.NotNullViolation):
                cur.execute("insert into access_keys (token_sha256, label) "
                            "values (repeat('a',64), 'ownerless')")
        conn.rollback()
