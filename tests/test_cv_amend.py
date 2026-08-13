"""M6, the amend path — one audited step, still a stamp chain.

Phase 9.5 task 2. Correcting a fact has always been possible: retire the old
block, add a new one. Two calls, correct by keep-all, and clumsy in exactly
the place clumsiness costs most — a client AI walking an owner through a
correction can do the first half, fail, and leave the fact base with a
retired block and no replacement. The owner's CV silently loses a line.

`amend_cv_block` does both halves in one call against one cursor, so they
land together or not at all. What it must NOT do is become an UPDATE. The
fact base's whole value is that `fact_text` is the exact wording every CV
bullet is traced against; mutating it in place would rewrite history, and the
audit trail would show a fact that had always said the new thing. So the old
row keeps its text and gains its retirement stamp, the new row is a fresh
DRAFT (an amendment is a proposal like any other — only the owner confirms),
and the two are linked so the chain can be walked.
"""
from __future__ import annotations

import os

import pytest

from tests.conftest import ScriptedCursor

DB_ONLY = pytest.mark.skipif(
    os.getenv("RUN_DB_TESTS") != "1",
    reason="DB integration tests are opt-in: RUN_DB_TESTS=1")

OWNER = "11111111-1111-1111-1111-111111111111"
OTHER = "22222222-2222-2222-2222-222222222222"


def _cursor(*, found=True, new_id=99):
    """Routes the amend path's three statements."""
    old = [{"block_id": 7, "kind": "achievement", "title": "Analyst",
            "organisation": "Acme", "date_range": "2022-2024",
            "fact_text": "Cut waste 12%.", "skill_norms": ["sql"],
            "sort_hint": 3}] if found else []
    return ScriptedCursor([
        ("select", [old]),
        ("insert into cv_blocks", [[{"block_id": new_id}]]),
        ("update cv_blocks", [[]]),
    ])


def test_an_amendment_retires_the_old_block_and_drafts_the_new_one():
    from cv.amend import amend_cv_block

    cur = _cursor()
    result = amend_cv_block(cur, OWNER, 7, fact_text="Cut waste 12.4%.")

    assert result["outcome"] == "amended"
    assert result["retired_block_id"] == 7
    assert result["block_id"] == 99
    assert result["confirmed"] is False, \
        "an amendment is a proposal — only the owner confirms it"


def test_the_old_wording_is_never_rewritten_only_stamped():
    # The property the whole fact base rests on. If an amendment could edit
    # fact_text in place, every CV bullet ever traced against the old wording
    # would now trace against words the owner never approved, and the audit
    # trail would show a fact that had always said the new thing.
    from cv.amend import amend_cv_block

    cur = _cursor()
    amend_cv_block(cur, OWNER, 7, fact_text="Cut waste 12.4%.")

    updates = [(sql, params) for sql, params in cur.executed
               if sql.lower().startswith("update")]
    assert len(updates) == 1, f"expected one stamp, got {updates}"
    sql, _ = updates[0]
    assert "retired_at = now()" in sql
    assert "fact_text" not in sql, \
        "the amendment rewrote the old block's words instead of stamping it"


def test_the_new_block_carries_the_old_ones_fields_unless_told_otherwise():
    # An amendment usually changes one thing. Making the client resend title,
    # organisation, dates and skills to correct a typo is how fields get
    # silently dropped — the caller omits one and the fact quietly loses it.
    from cv.amend import amend_cv_block

    cur = _cursor()
    amend_cv_block(cur, OWNER, 7, fact_text="Cut waste 12.4%.")

    insert = next(params for sql, params in cur.executed
                  if "insert into cv_blocks" in sql.lower())
    assert "Cut waste 12.4%." in insert
    assert "Analyst" in insert and "Acme" in insert and "2022-2024" in insert
    assert ["sql"] in insert, "the inherited skill_norms were dropped"


def test_an_explicit_field_overrides_the_inherited_one():
    from cv.amend import amend_cv_block

    cur = _cursor()
    amend_cv_block(cur, OWNER, 7, fact_text="Cut waste 12.4%.",
                   organisation="Acme Ltd", skill_norms=["sql", "excel"])

    insert = next(params for sql, params in cur.executed
                  if "insert into cv_blocks" in sql.lower())
    assert "Acme Ltd" in insert and "Acme" not in insert
    assert ["sql", "excel"] in insert


def test_amending_a_block_that_is_not_yours_changes_nothing():
    # Paired with the success case above, per the house rule: a one-sided
    # isolation test cannot tell "refused" from "nothing there".
    from cv.amend import amend_cv_block

    cur = _cursor(found=False)
    result = amend_cv_block(cur, OTHER, 7, fact_text="Not mine to edit.")

    assert result["outcome"] == "not_found"
    assert result.get("block_id") is None
    writes = [sql for sql, _ in cur.executed
              if sql.lower().startswith(("insert", "update"))]
    assert writes == [], f"a refused amendment still wrote: {writes}"


def test_the_lookup_is_scoped_to_the_owner_and_ignores_retired_blocks():
    from cv.amend import amend_cv_block

    cur = _cursor()
    amend_cv_block(cur, OWNER, 7, fact_text="x")

    sql, params = cur.executed[0]
    assert "owner_id = %s" in sql and "retired_at is null" in sql
    assert params == (7, OWNER)


def test_a_blank_amendment_is_refused_before_anything_is_stamped():
    # The dangerous ordering is retire-then-validate: the old fact is gone and
    # the replacement never lands. Validation happens first, and the refusal
    # is an exception rather than an outcome because it is a caller bug, not a
    # state of the world — matching add_cv_block.
    from cv.amend import amend_cv_block

    cur = _cursor()
    with pytest.raises(ValueError):
        amend_cv_block(cur, OWNER, 7, fact_text="   ")
    assert cur.executed == [], "a rejected amendment touched the database"


@DB_ONLY
def test_the_amend_path_leaves_a_walkable_chain_on_real_tables():
    """B-GAE-016's family: cv.blocks writes have never met a real table, and
    this adds a writer to it. `skill_norms` is a real text[] and `amended_from`
    is a real self-FK — neither behaves like a dict key."""
    from db.connection import get_conn
    from cv.amend import amend_cv_block
    from cv.blocks import add_cv_block, confirm_cv_block, load_cv_blocks

    schema = "cv_amend_probe"
    with get_conn() as conn:
        try:
            with conn.cursor() as cur:
                cur.execute(f"drop schema if exists {schema} cascade")
                cur.execute(f"create schema {schema}")
                cur.execute(f"set search_path to {schema}, public")
                for table in ("profiles", "cv_blocks"):
                    cur.execute(f"create table {table} "
                                f"(like public.{table} including all)")
                cur.execute("insert into profiles (profile_id, name) "
                            "values (%s,'Amend Probe')", (OWNER,))

                first = add_cv_block(cur, OWNER, kind="achievement",
                                     fact_text="Cut waste 12%.",
                                     organisation="Acme", skill_norms=["sql"])
                confirm_cv_block(cur, OWNER, first["block_id"])

                result = amend_cv_block(cur, OWNER, first["block_id"],
                                        fact_text="Cut waste 12.4%.")
                assert result["outcome"] == "amended"

                # The old row: words intact, stamped, no longer serving.
                cur.execute("select fact_text, retired_at, confirmed "
                            "from cv_blocks where block_id = %s",
                            (first["block_id"],))
                old = cur.fetchone()
                assert old["fact_text"] == "Cut waste 12%.", \
                    "the original wording was rewritten"
                assert old["retired_at"] is not None
                assert old["confirmed"] is True, \
                    "history says this WAS a confirmed fact; unconfirming it " \
                    "would rewrite that too"

                # The new row: a draft, linked back, fields inherited.
                cur.execute("select fact_text, confirmed, amended_from, "
                            "organisation, skill_norms from cv_blocks "
                            "where block_id = %s", (result["block_id"],))
                new = cur.fetchone()
                assert new["fact_text"] == "Cut waste 12.4%."
                assert new["confirmed"] is False
                assert new["amended_from"] == first["block_id"]
                assert new["organisation"] == "Acme"
                assert list(new["skill_norms"]) == ["sql"]

                # And the CV path sees neither until the owner confirms.
                assert load_cv_blocks(cur, OWNER) == []
                confirm_cv_block(cur, OWNER, result["block_id"])
                serving = load_cv_blocks(cur, OWNER)
                assert [b.fact_text for b in serving] == ["Cut waste 12.4%."]
        finally:
            conn.rollback()
            with conn.cursor() as cur:
                cur.execute(f"drop schema if exists {schema} cascade")
            conn.commit()       # B-GAE-041: a rolled-back drop is not a drop
