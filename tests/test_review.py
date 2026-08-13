"""Tests for src/review — the review queue (ambiguities the code couldn't decide).

Offline: a FakeCursor pins the query shape. resolve only ever touches a still-open
flag (idempotent), and a dismissal is just a different terminal status.
"""
from __future__ import annotations

import json

from tests.conftest import FakeCursor

OWNER_A = "11111111-1111-4111-a111-111111111111"


def test_add_flag_inserts_and_returns_the_new_row():
    from review import add_flag
    cur = FakeCursor(rows=[{"review_id": 9, "kind": "company_onboard",
                            "ref": "acme ai ltd", "status": "open"}])

    out = add_flag(cur, "company_onboard", "acme ai ltd",
                   "Onboard 'Acme AI Ltd': no job board found.",
                   {"sponsor_id": 10})

    assert out["review_id"] == 9
    sql, params = cur.executed[0]
    low = sql.lower()
    assert "insert into review_items" in low
    assert "where not exists" in low                 # idempotent by (kind, ref)
    assert params[0] == "company_onboard" and params[1] == "acme ai ltd"
    assert json.loads(params[3]) == {"sponsor_id": 10}   # evidence stored as JSON


def test_add_flag_is_a_no_op_when_the_flag_already_exists():
    from review import add_flag
    cur = FakeCursor(rows=[])                          # not-exists guard -> no returning row
    assert add_flag(cur, "company_onboard", "acme ai ltd", "…") is None


def test_list_flags_reads_open_items_by_default():
    from review import list_flags
    rows = [{"review_id": 1, "kind": "skill_synonym", "ref": "k8s",
             "summary": "…", "evidence": {}, "status": "open",
             "created_at": "…", "resolved_at": None}]
    cur = FakeCursor(rows=rows)

    out = list_flags(cur, OWNER_A)

    assert out == rows
    sql, params = cur.executed[0]
    low = sql.lower()
    assert "from review_items" in low
    assert "status = %s" in low
    assert "order by created_at" in low
    assert params == ("open", OWNER_A, 50)


def test_list_flags_filters_by_status_and_limit():
    from review import list_flags
    cur = FakeCursor(rows=[])
    list_flags(cur, OWNER_A, status="resolved", limit=10)
    assert cur.executed[0][1] == ("resolved", OWNER_A, 10)


def test_resolve_flag_marks_resolved_and_records_the_decision():
    from review import resolve_flag
    cur = FakeCursor(rows=[{"review_id": 1, "kind": "skill_synonym", "status": "resolved"}])

    out = resolve_flag(cur, OWNER_A, 1,
                       resolution={"decision": "accept", "canonical": "Kubernetes"})

    assert out["status"] == "resolved"
    sql, params = cur.executed[0]
    assert "update review_items" in sql.lower()
    assert "status='open'" in sql.lower().replace(" ", "")   # only an open flag is touched
    assert params[0] == "resolved"
    assert json.loads(params[1]) == {"decision": "accept", "canonical": "Kubernetes"}
    assert params[2] == 1               # review_id
    assert params[-1] == OWNER_A        # …acted on as this owner


def test_resolve_flag_can_dismiss():
    from review import resolve_flag
    cur = FakeCursor(rows=[{"review_id": 2, "kind": "skill_synonym", "status": "dismissed"}])
    out = resolve_flag(cur, OWNER_A, 2, dismiss=True)
    assert out["status"] == "dismissed"
    assert cur.executed[0][1][0] == "dismissed"


def test_resolve_flag_with_no_decision_stores_null():
    from review import resolve_flag
    cur = FakeCursor(rows=[{"review_id": 3, "status": "resolved"}])
    resolve_flag(cur, OWNER_A, 3)
    assert cur.executed[0][1][1] is None            # resolution -> NULL, not "null"


def test_resolve_flag_returns_none_when_the_flag_is_not_open():
    from review import resolve_flag
    assert resolve_flag(FakeCursor(rows=[]), OWNER_A, 999) is None


# ---- owner scoping (B-GAE-017) -------------------------------------------

DB_ONLY = __import__("pytest").mark.skipif(
    __import__("os").getenv("RUN_DB_TESTS") != "1",
    reason="DB integration tests are opt-in: RUN_DB_TESTS=1")


def test_a_world_flag_carries_no_owner_and_an_owned_one_does():
    # NULL is the meaningful value here: it says "this ambiguity is about a
    # public fact". A promotion_review flag is the opposite — it is built from
    # one person's lens and must name them.
    from review import add_flag
    world = FakeCursor(rows=[{"review_id": 1}])
    add_flag(world, "sponsor_match", "acme ltd", "which sponsor?", {})
    assert None in world.executed[0][1]

    owned = FakeCursor(rows=[{"review_id": 2}])
    add_flag(owned, "promotion_review", "acme ltd", "promote?", {},
             owner_id=OWNER_A)
    assert OWNER_A in owned.executed[0][1]


def test_add_flag_dedupes_per_owner_not_globally():
    # Without the owner in the not-exists check, the first person to flag an
    # organisation silently suppresses everyone else's flag for it — the same
    # shape as B-GAE-018's global dedupe_key.
    from review import add_flag
    cur = FakeCursor(rows=[{"review_id": 3}])
    add_flag(cur, "promotion_review", "acme ltd", "promote?", {},
             owner_id=OWNER_A)
    sql, params = cur.executed[0]
    assert "owner_id is not distinct from %s" in sql.lower()
    assert params.count(OWNER_A) == 2      # once to insert, once to compare


def test_listing_flags_shows_world_flags_and_only_my_own_owned_ones():
    from review import list_flags
    cur = FakeCursor(rows=[])
    list_flags(cur, OWNER_A)
    sql, params = cur.executed[0]
    low = sql.lower()
    assert "owner_id is null or owner_id = %s" in low
    assert OWNER_A in params


def test_resolving_someone_elses_flag_is_not_possible():
    # The half that matters most: reading another owner's lens is bad,
    # dismissing their open flags is worse — it empties a queue they are
    # relying on and holds their capped budget shut.
    from review import resolve_flag
    cur = FakeCursor(rows=[])
    resolve_flag(cur, OWNER_A, 42)
    sql, params = cur.executed[0]
    low = sql.lower()
    assert "owner_id is null or owner_id = %s" in low
    assert OWNER_A in params


def test_the_review_functions_cannot_be_called_the_old_ownerless_way():
    import pytest
    from review import list_flags, resolve_flag
    with pytest.raises(TypeError):
        list_flags(FakeCursor(rows=[]), status="open")
    with pytest.raises(TypeError):
        resolve_flag(FakeCursor(rows=[]), review_id=42)


@DB_ONLY
def test_owner_b_cannot_read_or_dismiss_owner_as_promotion_flags():
    # Proven by attempting it against real column shapes, two owners seeded.
    from db.connection import get_conn
    from review import add_flag, list_flags, resolve_flag

    schema = "review_owner_probe"
    owner_b = "22222222-2222-4222-a222-222222222222"
    with get_conn() as conn:
        try:
            with conn.cursor() as cur:
                cur.execute(f"drop schema if exists {schema} cascade")
                cur.execute(f"create schema {schema}")
                cur.execute(f"set search_path to {schema}")
                cur.execute("create table profiles "
                            "(like public.profiles including all)")
                cur.execute("create table review_items "
                            "(like public.review_items including all)")
                cur.execute("insert into profiles (profile_id, name) values "
                            "(%s,'A'),(%s,'B')", (OWNER_A, owner_b))

                a_flag = add_flag(cur, "promotion_review", "acme ltd",
                                  "promote for A?", {"min_local_jobs": 3},
                                  owner_id=OWNER_A)
                add_flag(cur, "sponsor_match", "acme ltd", "which sponsor?",
                         {}, owner_id=None)
                # B flagging the SAME org must not be suppressed by A's flag
                b_flag = add_flag(cur, "promotion_review", "acme ltd",
                                  "promote for B?", {"min_local_jobs": 9},
                                  owner_id=owner_b)
                assert b_flag is not None, "A's flag suppressed B's"

                b_sees = {r["review_id"] for r in list_flags(cur, owner_b)}
                assert b_flag["review_id"] in b_sees
                assert a_flag["review_id"] not in b_sees, \
                    "owner B read owner A's lens-derived flag"
                # the world flag reaches both
                assert len(b_sees) == 2

                assert resolve_flag(cur, owner_b, a_flag["review_id"],
                                    dismiss=True) is None, \
                    "owner B dismissed owner A's flag"
                # …and A can still resolve their own: the pairing control
                assert resolve_flag(cur, OWNER_A, a_flag["review_id"],
                                    dismiss=True) is not None
        finally:
            conn.rollback()
            with conn.cursor() as cur:
                cur.execute(f"drop schema if exists {schema} cascade")
            conn.rollback()
