"""The mirror: what the system understands about a person, read back with receipts.

Phase 9.5 task 1. The product's turn from job board to translator — but the
engineering claim underneath it is narrow and testable: **nothing here is
stored**. The facts are stored; the understanding is re-formed on every read.
A stored summary drifts away from the rows it summarises, silently, and then
the machine is confidently telling someone about a person who has changed.
`test_the_mirror_writes_nothing_at_all` is that principle as a mechanism.

The other property worth naming is that the mirror must be willing to say
uncomfortable things. A read-back that only counts what it has is flattery;
the number that earns the feature is how much of what the owner claims the
machine **cannot prove** — because the CV truth gate will refuse exactly those
skills later, and the owner should hear it now rather than from an empty CV.
Measured on the founder's own fact base the day this was built: 21 live
skills, 4 evidenced, 17 not.
"""
from __future__ import annotations

import os
import pathlib

import pytest

from tests.conftest import ScriptedCursor

ROOT = pathlib.Path(__file__).resolve().parents[1]

DB_ONLY = pytest.mark.skipif(
    os.getenv("RUN_DB_TESTS") != "1",
    reason="DB integration tests are opt-in: RUN_DB_TESTS=1")

OWNER = "11111111-1111-1111-1111-111111111111"


def _cursor(blocks=None, skills=None) -> ScriptedCursor:
    """Route the mirror's two reads: cv_blocks, then my_skills."""
    return ScriptedCursor([
        ("from cv_blocks", [blocks or []]),
        ("from my_skills", [skills or []]),
    ])


def _block(**kw) -> dict:
    row = {"kind": "skill_evidence", "confirmed": True, "retired_at": None,
           "skill_norms": [], "organisation": None, "title": None,
           "block_id": 1, "fact_text": "a true sentence"}
    row.update(kw)
    return row


def _skill(**kw) -> dict:
    row = {"skill": "Python", "skill_norm": "python", "level": None,
           "evidence": None, "learned_at": None, "status": "active"}
    row.update(kw)
    return row


def test_the_mirror_counts_facts_by_kind_and_by_state():
    from cv.mirror import build_mirror

    cur = _cursor(blocks=[
        _block(block_id=1, kind="role", confirmed=True),
        _block(block_id=2, kind="role", confirmed=True),
        _block(block_id=3, kind="achievement", confirmed=False),
        _block(block_id=4, kind="education", confirmed=True, retired_at="2026-01-01"),
    ])
    mirror = build_mirror(cur, OWNER)

    facts = mirror["facts"]
    assert facts["confirmed"] == 2
    assert facts["drafts"] == 1
    assert facts["retired"] == 1
    # by_kind counts what SERVES — confirmed and live — because that is what a
    # CV can be built from. A retired education block is history, not a fact.
    assert facts["by_kind"] == {"role": 2}


def test_only_a_confirmed_live_block_can_evidence_a_skill():
    # The mirror must agree with the truth gate about what counts as proof. A
    # draft is a proposal nobody has approved, and a retired block has been
    # withdrawn; if either could evidence a skill, the mirror would promise a
    # CV line that generate.py would then refuse to write.
    from cv.mirror import build_mirror

    cur = _cursor(
        blocks=[
            _block(block_id=1, kind="achievement", confirmed=False,
                   skill_norms=["python"]),
            _block(block_id=2, kind="achievement", confirmed=True,
                   retired_at="2026-01-01", skill_norms=["sql"]),
            _block(block_id=3, kind="achievement", confirmed=True,
                   skill_norms=["docker"]),
        ],
        skills=[_skill(skill="Python", skill_norm="python"),
                _skill(skill="SQL", skill_norm="sql"),
                _skill(skill="Docker", skill_norm="docker")])
    mirror = build_mirror(cur, OWNER)

    assert mirror["skills"]["evidenced"] == 1
    assert [s["skill"] for s in mirror["provable"]] == ["Docker"]
    assert sorted(s["skill"] for s in mirror["unprovable"]) == ["Python", "SQL"]


def test_the_unprovable_skills_are_named_not_merely_counted():
    # The receipts rule, and the whole point of the surface: "17 unevidenced"
    # is a number someone can do nothing with. The names are what let the owner
    # go and add the missing fact.
    from cv.mirror import build_mirror

    cur = _cursor(
        blocks=[_block(block_id=1, confirmed=True, skill_norms=["python"])],
        skills=[_skill(skill="Python", skill_norm="python"),
                _skill(skill="Kubernetes", skill_norm="kubernetes")])
    mirror = build_mirror(cur, OWNER)

    assert mirror["skills"]["unevidenced"] == 1
    assert [s["skill"] for s in mirror["unprovable"]] == ["Kubernetes"]
    # And a provable skill cites the block that proves it, so the claim can be
    # followed to its source rather than believed.
    proof = mirror["provable"][0]
    assert proof["skill"] == "Python"
    assert proof["evidenced_by"] == [1]


def test_evidence_outside_paid_work_is_evidence_that_is_not_a_role():
    # The number the brief names, and it matters for exactly the people this
    # product is for: someone whose paid history is thin in this country can
    # still have provable skills, and a machine that only counted jobs would
    # tell them they have nothing.
    from cv.mirror import build_mirror

    cur = _cursor(
        blocks=[
            _block(block_id=1, kind="role", skill_norms=["sql"]),
            _block(block_id=2, kind="skill_evidence", skill_norms=["rust"]),
            _block(block_id=3, kind="education", skill_norms=["statistics"]),
        ],
        skills=[_skill(skill="SQL", skill_norm="sql"),
                _skill(skill="Rust", skill_norm="rust"),
                _skill(skill="Statistics", skill_norm="statistics")])
    mirror = build_mirror(cur, OWNER)

    assert mirror["skills"]["evidenced"] == 3
    assert mirror["skills"]["evidenced_outside_paid_work"] == 2
    outside = {s["skill"] for s in mirror["provable"] if s["outside_paid_work"]}
    assert outside == {"Rust", "Statistics"}


def test_a_skill_evidenced_both_ways_is_not_counted_as_outside_paid_work():
    # A skill proven by a job AND by a side project is proven by the job. The
    # "outside paid work" count exists to surface what would otherwise be
    # invisible, so double-counting it would inflate the very number that is
    # supposed to be the honest one.
    from cv.mirror import build_mirror

    cur = _cursor(
        blocks=[_block(block_id=1, kind="role", skill_norms=["sql"]),
                _block(block_id=2, kind="skill_evidence", skill_norms=["sql"])],
        skills=[_skill(skill="SQL", skill_norm="sql")])
    mirror = build_mirror(cur, OWNER)

    assert mirror["skills"]["evidenced"] == 1
    assert mirror["skills"]["evidenced_outside_paid_work"] == 0
    assert mirror["provable"][0]["evidenced_by"] == [1, 2]


def test_a_dormant_skill_is_not_counted_among_the_live_ones():
    # Matches every gap query in the codebase: status in ('active','in_progress').
    from cv.mirror import build_mirror

    cur = _cursor(skills=[_skill(skill="A", skill_norm="a", status="active"),
                          _skill(skill="B", skill_norm="b", status="in_progress"),
                          _skill(skill="C", skill_norm="c", status="dormant")])
    mirror = build_mirror(cur, OWNER)

    assert mirror["skills"]["live"] == 2
    assert mirror["skills"]["dormant"] == 1
    assert {s["skill"] for s in mirror["unprovable"]} == {"A", "B"}


def test_the_headline_states_the_three_numbers_it_is_made_of():
    from cv.mirror import build_mirror

    cur = _cursor(
        blocks=[_block(block_id=1, kind="skill_evidence", skill_norms=["rust"]),
                _block(block_id=2, kind="role")],
        skills=[_skill(skill="Rust", skill_norm="rust"),
                _skill(skill="Go", skill_norm="go")])
    mirror = build_mirror(cur, OWNER)

    assert mirror["headline"] == "2 facts · 2 skills · 1 evidenced outside paid work"


def test_an_empty_fact_base_reads_back_as_empty_rather_than_failing():
    # A brand-new owner calls this before anything exists. It must answer, and
    # the answer must not be a division by zero dressed up as understanding.
    from cv.mirror import build_mirror

    mirror = build_mirror(_cursor(), OWNER)

    assert mirror["facts"]["confirmed"] == 0
    assert mirror["skills"]["live"] == 0
    assert mirror["provable"] == [] and mirror["unprovable"] == []
    assert mirror["coverage"] is None, \
        "coverage over an empty skill set must be None, never a fake 0 or 100"
    assert "0 facts" in mirror["headline"]


def test_coverage_is_the_evidenced_share_and_ships_its_basis():
    from cv.mirror import build_mirror

    cur = _cursor(
        blocks=[_block(block_id=1, skill_norms=["a", "b"])],
        skills=[_skill(skill="A", skill_norm="a"), _skill(skill="B", skill_norm="b"),
                _skill(skill="C", skill_norm="c"), _skill(skill="D", skill_norm="d")])
    mirror = build_mirror(cur, OWNER)

    assert mirror["coverage"] == 0.5
    # Recomputable from its own siblings — the house receipts rule.
    assert mirror["skills"]["evidenced"] / mirror["skills"]["live"] == mirror["coverage"]


def test_the_mirror_writes_nothing_at_all():
    # "No stored opinion of the person" as a mechanism rather than an
    # intention. The facts are stored; the understanding is re-formed on every
    # read. A stored summary would drift away from the rows beneath it and the
    # machine would go on confidently describing someone who had changed.
    from cv.mirror import build_mirror

    cur = _cursor(
        blocks=[_block(block_id=1, skill_norms=["python"])],
        skills=[_skill()])
    build_mirror(cur, OWNER)

    written = [sql for sql, _ in cur.executed
               if any(verb in sql.lower().split()
                      for verb in ("insert", "update", "delete", "create", "drop"))]
    assert written == [], f"the mirror wrote to the database: {written}"


def test_both_reads_are_scoped_to_the_owner():
    # Every read in this project carries its owner. A mirror that forgot would
    # read someone else's life back to the wrong person — and RLS would be the
    # only thing between that and a very bad afternoon.
    from cv.mirror import build_mirror

    cur = _cursor()
    build_mirror(cur, OWNER)

    assert len(cur.executed) == 2, f"expected two reads, got {len(cur.executed)}"
    for sql, params in cur.executed:
        assert "owner_id = %s" in sql, f"unscoped read: {sql}"
        assert params == (OWNER,)


@DB_ONLY
def test_the_mirror_reads_a_real_fact_base_with_real_column_types():
    """B-GAE-016's class: the offline tests above use dicts, which have no
    column types, no generated columns and no array handling. `skill_norms` is
    a real `text[]` and `skill_norm` is GENERATED — neither behaves like a dict
    key. So the whole fold runs once against real tables."""
    from db.connection import get_conn
    from cv.mirror import build_mirror

    schema = "cv_mirror_probe"
    with get_conn() as conn:
        try:
            with conn.cursor() as cur:
                cur.execute(f"drop schema if exists {schema} cascade")
                cur.execute(f"create schema {schema}")
                cur.execute(f"set search_path to {schema}, public")
                for table in ("profiles", "cv_blocks", "my_skills"):
                    cur.execute(f"create table {table} "
                                f"(like public.{table} including all)")
                cur.execute("insert into profiles (profile_id, name) "
                            "values (%s,'Mirror Probe')", (OWNER,))

                cur.execute(
                    "insert into cv_blocks (owner_id, kind, fact_text, "
                    "skill_norms, confirmed) values "
                    "(%s,'role','Ran the thing for two years.','{sql}'::text[],true),"
                    "(%s,'skill_evidence','Built the other thing.','{rust}'::text[],true),"
                    "(%s,'achievement','A draft nobody approved.','{go}'::text[],false)",
                    (OWNER, OWNER, OWNER))
                # skill_norm is GENERATED ALWAYS — inserting raw facts only.
                cur.execute(
                    "insert into my_skills (owner_id, skill, status) values "
                    "(%s,'SQL','active'),(%s,'Rust','active'),(%s,'Go','active')",
                    (OWNER, OWNER, OWNER))

                mirror = build_mirror(cur, OWNER)

                assert mirror["facts"]["confirmed"] == 2
                assert mirror["facts"]["drafts"] == 1
                assert mirror["facts"]["by_kind"] == {"role": 1, "skill_evidence": 1}
                assert mirror["skills"]["live"] == 3
                assert mirror["skills"]["evidenced"] == 2
                assert mirror["skills"]["evidenced_outside_paid_work"] == 1
                # Go is only on the unapproved draft, so it stays unprovable —
                # the property the offline test asserts, now against a real
                # text[] column and a real generated skill_norm.
                assert [s["skill"] for s in mirror["unprovable"]] == ["Go"]
                assert mirror["coverage"] == pytest.approx(2 / 3)

                # --- and the view must say the same thing about the same rows.
                #
                # `v_owner_mirror` re-implements this fold in SQL because the
                # dashboard may read nothing but curated views. Two
                # implementations of one idea is precisely the shape that
                # rotted in B-GAE-025, where a mirror stopped describing what
                # it mirrored and nobody noticed for weeks. So they are held
                # together here, against the same probe rows, rather than by
                # anyone remembering to update both.
                # The SHIPPED migration SQL, run against the probe tables —
                # not a hand-copied version of it, which would be a third
                # implementation to keep in step. The body names its tables
                # unqualified, so with the probe schema first on search_path
                # they resolve to the probe's copies.
                sql = (ROOT / "db" / "migrations"
                       / "0063_owner_mirror_view.sql").read_text()
                cur.execute(sql.replace("CREATE VIEW public.v_owner_mirror",
                                        "CREATE VIEW v_owner_mirror")
                               .replace("BEGIN;", "").replace("COMMIT;", ""))
                cur.execute("select * from v_owner_mirror where owner_id = %s",
                            (OWNER,))
                view = cur.fetchone()
                assert view is not None, \
                    "an owner with a fact base has no row in v_owner_mirror"
                assert view["facts_confirmed"] == mirror["facts"]["confirmed"]
                assert view["facts_drafts"] == mirror["facts"]["drafts"]
                assert view["facts_retired"] == mirror["facts"]["retired"]
                assert view["fact_kinds"] == len(mirror["facts"]["by_kind"])
                assert view["skills_live"] == mirror["skills"]["live"]
                assert view["skills_evidenced"] == mirror["skills"]["evidenced"]
                assert view["skills_unevidenced"] == mirror["skills"]["unevidenced"]
                assert view["evidenced_outside_paid_work"] == \
                    mirror["skills"]["evidenced_outside_paid_work"]
        finally:
            conn.rollback()
            with conn.cursor() as cur:
                cur.execute(f"drop schema if exists {schema} cascade")
            conn.commit()       # B-GAE-041: a rolled-back drop is not a drop
