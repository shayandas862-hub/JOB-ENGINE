"""M7 — one life experience reaches BOTH the fact base and the gap model.

Phase 9.5 task 3. `add_cv_block` writes a fact; `add_skill` writes a skill;
nothing linked them, and `intake-v1` has instructed a client to call both
since Phase 9. The prompt option was therefore not hypothetical — it shipped,
and this is what it produced on the founder's own base, measured while
building task 1:

    21 live skills · 4 evidenced · 17 with no fact behind them
    6 role blocks evidencing 8 skill_norms — "teamwork", "call handling",
    "cinematography" — of which ZERO match any my_skills row

Two vocabularies, drifted completely apart. Not a normalisation bug (every
one of those norms is correctly normalised); the sessions that wrote the
career facts and the sessions that wrote the skills simply used different
words, because nothing required them to agree.

So the seam is a server-side write, and the property that matters is that the
two sides join **by construction**: the block's `skill_norms` are the values
`add_skill` returns, which come from the one normaliser whose equivalence to
the generated column is already DB-tested. There is no second normalisation
here and there must never be one.

The test that proves it did any good is the round trip: record an experience,
then ask the mirror, and the skill must come back PROVABLE.
"""
from __future__ import annotations

import os

import pytest

DB_ONLY = pytest.mark.skipif(
    os.getenv("RUN_DB_TESTS") != "1",
    reason="DB integration tests are opt-in: RUN_DB_TESTS=1")

OWNER = "11111111-1111-1111-1111-111111111111"


def test_the_block_and_the_skills_are_written_from_one_payload():
    from criteria.experience import record_experience

    calls = []

    def fake_add_skill(cur, owner_id, skill, **kw):
        calls.append(("skill", skill, kw))
        return {"skill": skill, "skill_norm": skill.lower(), "outcome": "added"}

    def fake_add_block(cur, owner_id, **kw):
        calls.append(("block", kw["fact_text"], kw))
        return {"block_id": 5, "confirmed": False}

    result = record_experience(
        None, OWNER, kind="achievement",
        fact_text="Built the nightly pipeline that runs unattended.",
        skills=[{"name": "Python", "evidence": "wrote the whole engine"},
                {"name": "SQL"}],
        add_skill=fake_add_skill, add_block=fake_add_block)

    assert result["block_id"] == 5
    assert result["confirmed"] is False
    assert [s["skill_norm"] for s in result["skills"]] == ["python", "sql"]
    assert [c[0] for c in calls] == ["skill", "skill", "block"], \
        "the skills must be written BEFORE the block that cites them"


def test_the_blocks_skill_norms_come_from_the_skill_writer_never_recomputed():
    # The whole seam. If this module normalised the names itself, it would be
    # a SECOND implementation of my_skills' generated column, and the day the
    # two disagreed the join would silently return nothing — which is exactly
    # the drift measured above, reintroduced by the fix for it.
    from criteria.experience import record_experience

    seen = {}

    def fake_add_skill(cur, owner_id, skill, **kw):
        # Deliberately unlike anything a caller could guess: if the block's
        # norms match THIS, they came from here.
        return {"skill": skill, "skill_norm": f"norm::{skill}", "outcome": "added"}

    def fake_add_block(cur, owner_id, **kw):
        seen.update(kw)
        return {"block_id": 1, "confirmed": False}

    record_experience(None, OWNER, kind="role", fact_text="Ran a team.",
                      skills=[{"name": "Leadership"}],
                      add_skill=fake_add_skill, add_block=fake_add_block)

    assert seen["skill_norms"] == ["norm::Leadership"]


def test_every_skill_field_the_curve_needs_is_carried_through():
    # learned_at and evidence are the learning-curve model's data (task 4). A
    # seam that dropped them would quietly make the curve unbuildable for
    # every skill recorded through it — the failure being an empty ranking
    # months later, with nothing pointing here.
    from criteria.experience import record_experience

    got = []

    def fake_add_skill(cur, owner_id, skill, **kw):
        got.append(kw)
        return {"skill": skill, "skill_norm": skill, "outcome": "added"}

    record_experience(None, OWNER, kind="skill_evidence", fact_text="A fact.",
                      skills=[{"name": "Rust", "level": "used daily",
                               "evidence": "shipped a parser",
                               "learned_at": "2026-01-15",
                               "category": "language"}],
                      add_skill=fake_add_skill,
                      add_block=lambda *a, **k: {"block_id": 1,
                                                 "confirmed": False})

    assert got[0]["level"] == "used daily"
    assert got[0]["evidence"] == "shipped a parser"
    assert got[0]["learned_at"] == "2026-01-15"
    assert got[0]["category"] == "language"


def test_a_plain_string_is_accepted_as_a_skill_with_no_detail():
    # The interview will often have a name and nothing else. Refusing it would
    # push the client back to calling add_skill separately, which is the
    # behaviour this exists to end.
    from criteria.experience import record_experience

    result = record_experience(
        None, OWNER, kind="achievement", fact_text="A fact.",
        skills=["Docker"],
        add_skill=lambda cur, o, s, **kw: {"skill": s, "skill_norm": s.lower(),
                                           "outcome": "added"},
        add_block=lambda *a, **k: {"block_id": 1, "confirmed": False})

    assert result["skills"][0]["skill_norm"] == "docker"


def test_an_experience_with_no_skills_is_still_a_fact():
    # Education and plain history evidence nothing in particular. This must
    # not become a reason to skip recording the fact.
    from criteria.experience import record_experience

    seen = {}
    result = record_experience(
        None, OWNER, kind="education", fact_text="MSc, 2019.", skills=[],
        add_skill=lambda *a, **k: pytest.fail("no skill should be written"),
        add_block=lambda cur, o, **kw: seen.update(kw) or {"block_id": 2,
                                                           "confirmed": False})

    assert result["block_id"] == 2 and result["skills"] == []
    assert seen["skill_norms"] == []


def test_a_blank_fact_is_refused_before_any_skill_is_written():
    # Skills-first ordering has one hazard: a payload that fails validation
    # after the skills land leaves them orphaned, claimed with no fact behind
    # them — manufacturing the exact state task 1 exists to complain about.
    from criteria.experience import record_experience

    with pytest.raises(ValueError):
        record_experience(None, OWNER, kind="role", fact_text="  ",
                          skills=[{"name": "Python"}],
                          add_skill=lambda *a, **k: pytest.fail(
                              "a skill was written for a fact that was refused"),
                          add_block=lambda *a, **k: None)


def test_an_unknown_kind_is_refused_before_any_skill_is_written():
    from criteria.experience import record_experience

    with pytest.raises(ValueError):
        record_experience(None, OWNER, kind="anecdote", fact_text="A fact.",
                          skills=[{"name": "Python"}],
                          add_skill=lambda *a, **k: pytest.fail(
                              "a skill was written for a fact that was refused"),
                          add_block=lambda *a, **k: None)


def test_a_skill_with_no_name_is_refused_rather_than_written_blank():
    from criteria.experience import record_experience

    with pytest.raises(ValueError):
        record_experience(None, OWNER, kind="role", fact_text="A fact.",
                          skills=[{"level": "expert"}],
                          add_skill=lambda *a, **k: pytest.fail("unreachable"),
                          add_block=lambda *a, **k: None)


@DB_ONLY
def test_the_seam_closes_the_gap_the_mirror_reports():
    """The round trip, and the only test that proves this was worth building.

    Write one experience the new way; confirm the fact; ask the mirror. The
    skill must come back PROVABLE — which is precisely what does not happen
    for 17 of the founder's 21 real skills, recorded the old way.
    """
    from db.connection import get_conn
    from criteria.experience import record_experience
    from criteria.writer import add_skill
    from cv.blocks import add_cv_block, confirm_cv_block
    from cv.mirror import build_mirror

    schema = "experience_seam_probe"
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
                            "values (%s,'Seam Probe')", (OWNER,))

                # The OLD way, which is what produced the drift: two separate
                # calls whose vocabularies nobody reconciled.
                add_skill(cur, OWNER, "Prompt Engineering")
                old = add_cv_block(cur, OWNER, kind="achievement",
                                   fact_text="Wrote the interview prompt.",
                                   skill_norms=["prompt design"])
                confirm_cv_block(cur, OWNER, old["block_id"])

                # The NEW way: one payload, both writes, joined by construction.
                new = record_experience(
                    cur, OWNER, kind="skill_evidence",
                    fact_text="Built the nightly pipeline that runs unattended.",
                    skills=[{"name": "Python", "evidence": "the whole engine",
                             "learned_at": "2026-01-15"}])
                confirm_cv_block(cur, OWNER, new["block_id"])

                mirror = build_mirror(cur, OWNER)
                provable = {s["skill"] for s in mirror["provable"]}
                unprovable = {s["skill"] for s in mirror["unprovable"]}

                assert provable == {"Python"}, (
                    "the seam did not join: a skill written through it must be "
                    f"provable, got {provable}")
                assert unprovable == {"Prompt Engineering"}, (
                    "the separately-written skill should still be unprovable — "
                    "otherwise this test is not comparing the two paths")

                # And the curve's data survived the trip (task 4 depends on it).
                cur.execute("select learned_at, evidence from my_skills "
                            "where skill_norm = 'python'")
                row = cur.fetchone()
                assert row["learned_at"].isoformat() == "2026-01-15"
                assert row["evidence"] == "the whole engine"
        finally:
            conn.rollback()
            with conn.cursor() as cur:
                cur.execute(f"drop schema if exists {schema} cascade")
            conn.commit()       # B-GAE-041: a rolled-back drop is not a drop
