"""Tests for src/cv/blocks — the cv_blocks loader (verified career facts).

Offline: a FakeCursor pins the query shape. One opt-in integration test
(RUN_DB_TESTS=1) seeds a scratch cv_blocks and proves the loader returns only
confirmed, owner-scoped blocks in stable order with skill_norms intact.
"""
from __future__ import annotations

import os

import pytest

from tests.conftest import FakeCursor


def _row(block_id=1, kind="role", title="Senior Data Analyst",
         organisation="Acme", date_range="2021-2023",
         fact_text="Led analytics for Acme, cutting reporting time 40%.",
         skill_norms=("sql", "python"), sort_hint=0):
    return {"block_id": block_id, "kind": kind, "title": title,
            "organisation": organisation, "date_range": date_range,
            "fact_text": fact_text, "skill_norms": list(skill_norms),
            "sort_hint": sort_hint}


def test_load_cv_blocks_is_owner_scoped_and_confirmed_by_default():
    from cv.blocks import load_cv_blocks
    cur = FakeCursor(rows=[_row()])

    blocks = load_cv_blocks(cur, "p-1")

    sql, params = cur.executed[0]
    low = sql.lower()
    assert "from cv_blocks" in low
    assert "owner_id = %s" in low
    assert "confirmed" in low                 # only verified facts by default
    assert "order by sort_hint" in low
    assert params[0] == "p-1"
    assert len(blocks) == 1


def test_cv_block_carries_the_fact_text_and_skill_evidence():
    from cv.blocks import CvBlock, load_cv_blocks
    cur = FakeCursor(rows=[_row(fact_text="Shipped X.", skill_norms=["sql", "etl"])])
    (b,) = load_cv_blocks(cur, "p-1")
    assert isinstance(b, CvBlock)
    assert b.kind == "role" and b.title == "Senior Data Analyst"
    assert b.fact_text == "Shipped X."        # the grounding source for later tasks
    assert b.skill_norms == ["sql", "etl"]


def test_load_cv_blocks_can_include_unconfirmed():
    from cv.blocks import load_cv_blocks
    cur = FakeCursor(rows=[])
    load_cv_blocks(cur, "p-1", confirmed_only=False)
    assert "confirmed" not in cur.executed[0][0].lower()


def test_load_cv_blocks_filters_by_kind():
    from cv.blocks import load_cv_blocks
    cur = FakeCursor(rows=[])
    load_cv_blocks(cur, "p-1", kinds=["role", "achievement"])
    sql, params = cur.executed[0]
    assert "kind = any(%s)" in sql.lower()
    assert ["role", "achievement"] in params


@pytest.mark.skipif(
    os.getenv("RUN_DB_TESTS") != "1",
    reason="DB integration tests are opt-in: RUN_DB_TESTS=1",
)
def test_load_cv_blocks_against_a_seeded_slice():
    from cv.blocks import load_cv_blocks
    from db.connection import get_conn

    schema = "tq_cvblocks_test"
    owner = "11111111-1111-4111-a111-111111111111"
    other = "22222222-2222-4222-a222-222222222222"
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f"drop schema if exists {schema} cascade")
            cur.execute(f"create schema {schema}")
            cur.execute(f"set search_path to {schema}")
            # B-GAE-015: this table was hand-written and drifted the moment
            # migration 0049 added retired_at — LIKE cannot drift.
            cur.execute("create table cv_blocks "
                        "(like public.cv_blocks including all)")
            cur.execute(f"""
                insert into cv_blocks (owner_id, kind, title, fact_text, skill_norms, sort_hint, confirmed) values
                  ('{owner}','role','B','fact B','{{sql}}', 2, true),
                  ('{owner}','role','A','fact A','{{python,sql}}', 1, true),
                  ('{owner}','achievement','U','unconfirmed','{{}}', 0, false),
                  ('{other}','role','X','other owner','{{sql}}', 0, true);
            """)
            confirmed = load_cv_blocks(cur, owner)
            withall = load_cv_blocks(cur, owner, confirmed_only=False)
            cur.execute(f"drop schema {schema} cascade")
        conn.rollback()

    # only this owner's confirmed blocks, ordered by sort_hint
    assert [b.title for b in confirmed] == ["A", "B"]
    assert confirmed[0].skill_norms == ["python", "sql"]      # text[] round-trips as a list
    assert {b.title for b in withall} == {"A", "B", "U"}      # unconfirmed included on request


# ---- U8b: the cv_blocks writers (founder's ask 2026-08-10) ------------------

def test_add_cv_block_writes_a_DRAFT_never_a_confirmed_fact():
    # A client AI proposes; only the owner confirms — the reading tray's
    # "propose, don't decide", applied to the fact base.
    from cv.blocks import add_cv_block
    from tests.conftest import FakeCursor
    cur = FakeCursor(rows=[{"block_id": 44}])
    out = add_cv_block(cur, "owner-1", kind="achievement",
                       fact_text="Shipped the rota tool to 40 staff.",
                       title="Rota tool", organisation="Meadow House",
                       date_range="2025", skill_norms=["python"],
                       source="user-ai")
    assert out == {"block_id": 44, "confirmed": False}
    sql, params = cur.executed[0]
    low = sql.lower()
    assert "insert into cv_blocks" in low and "owner_id" in low
    assert "confirmed" not in low.split("values")[0] or "false" in low
    assert "Shipped the rota tool to 40 staff." in params
    assert "owner-1" in params


def test_add_cv_block_rejects_junk_kinds_and_blank_facts():
    import pytest
    from cv.blocks import add_cv_block
    from tests.conftest import FakeCursor
    with pytest.raises(ValueError):
        add_cv_block(FakeCursor(), "owner-1", kind="poem", fact_text="x")
    with pytest.raises(ValueError):
        add_cv_block(FakeCursor(), "owner-1", kind="role", fact_text="   ")


def test_confirm_and_retire_are_owner_scoped_stamps():
    from cv.blocks import confirm_cv_block, retire_cv_block
    from tests.conftest import FakeCursor
    cur = FakeCursor(rowcount=1)
    assert confirm_cv_block(cur, "owner-1", 44) == {"block_id": 44,
                                                    "outcome": "confirmed"}
    sql, params = cur.executed[0]
    assert "confirmed = true" in sql.lower()
    assert "owner_id" in sql.lower() and "owner-1" in params

    cur2 = FakeCursor(rowcount=1)
    assert retire_cv_block(cur2, "owner-1", 44)["outcome"] == "retired"
    low2 = cur2.executed[0][0].lower()
    assert "retired_at = now()" in low2          # a stamp, never a delete
    assert "delete" not in low2

    missing = FakeCursor(rowcount=0)
    assert confirm_cv_block(missing, "owner-1", 99)["outcome"] == "not_found"


def test_load_cv_blocks_never_serves_a_retired_fact():
    from cv.blocks import load_cv_blocks
    cur = FakeCursor(rows=[])
    load_cv_blocks(cur, "owner-1")
    assert "retired_at is null" in cur.executed[0][0].lower()


@pytest.mark.skipif(
    os.getenv("RUN_DB_TESTS") != "1",
    reason="DB integration tests are opt-in: RUN_DB_TESTS=1",
)
def test_add_cv_block_actually_lands_a_row_in_a_real_cv_blocks():
    # B-GAE-014: the offline test above asserts the SQL string against a fake
    # cursor, which has no column types — so add_cv_block could fail on EVERY
    # insert and still pass. This one runs the real function against a real
    # copy of the real table, which is the only shape that catches it.
    from cv.blocks import add_cv_block
    from db.connection import get_conn

    schema = "add_cv_block_probe"
    owner = "11111111-1111-4111-a111-111111111111"
    with get_conn() as conn:
        try:
            with conn.cursor() as cur:
                cur.execute(f"drop schema if exists {schema} cascade")
                cur.execute(f"create schema {schema}")
                cur.execute(f"set search_path to {schema}")
                cur.execute("create table cv_blocks "
                            "(like public.cv_blocks including all)")

                added = add_cv_block(cur, owner, kind="achievement",
                                     fact_text="Shipped the rota tool.",
                                     skill_norms=["python", "sql"],
                                     source="user-ai")
                assert added["confirmed"] is False

                cur.execute("select skill_norms, confirmed from cv_blocks")
                rows = cur.fetchall()
                assert len(rows) == 1, "add_cv_block wrote nothing"
                assert rows[0]["skill_norms"] == ["python", "sql"]
                assert rows[0]["confirmed"] is False

                # the no-skills path stores the empty array, never null
                add_cv_block(cur, owner, kind="role", fact_text="A role.")
                cur.execute("select skill_norms from cv_blocks "
                            "order by block_id desc limit 1")
                assert cur.fetchone()["skill_norms"] == []
        finally:
            conn.rollback()
            with conn.cursor() as cur:
                cur.execute(f"drop schema if exists {schema} cascade")
            conn.rollback()
