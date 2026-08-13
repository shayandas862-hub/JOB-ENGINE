"""Skills you are closest to closing — ranked by effort, with receipts.

Phase 9.5 task 4. The brief asked for this over `my_skills.learned_at`, on
the stated basis that the column had been "collecting since 2026-08-10" with
"weeks of data". Measured before building: **22 skills, 0 with learned_at**,
every row written 2026-06-28, none added since ([[B-GAE-046]]). Ranking on
that column would have produced an empty list forever, from code that runs
cleanly and reviews as correct.

So the ranking is built on what the data does support, which turns out to be
the better question anyway. "Closest to closing" is a statement about
EFFORT, and recency is only one proxy for it. The real ladder, cheapest
first:

  prove it   — the owner HAS the skill and roles ask for it, but no confirmed
               fact evidences it, so a CV cannot claim it. Closing this costs
               one sentence. Measured on the founder's base: 9 of these.
  finish it  — already in progress, and roles are asking.
  learn it   — in demand, not held at all. Months, not minutes.

`learned_at` is not silently ignored: the basis reports how many rows carry
it, so its absence is visible in every answer rather than invisible in an
empty one, and the recency dimension joins the ranking when that number is
no longer zero.
"""
from __future__ import annotations

import os

import pytest

from tests.conftest import ScriptedCursor

DB_ONLY = pytest.mark.skipif(
    os.getenv("RUN_DB_TESTS") != "1",
    reason="DB integration tests are opt-in: RUN_DB_TESTS=1")

OWNER = "11111111-1111-1111-1111-111111111111"


def _cursor(demand=(), held=(), proven=()):
    return ScriptedCursor([
        ("v_skill_demand", [list(demand)]),
        ("from my_skills", [list(held)]),
        ("from cv_blocks", [list(proven)]),
    ])


def _d(norm, skill, n):
    return {"skill_norm": norm, "skill": skill, "demand": n}


def _h(norm, skill, status="active", learned_at=None):
    return {"skill_norm": norm, "skill": skill, "status": status,
            "level": None, "learned_at": learned_at}


def test_a_held_skill_with_no_fact_behind_it_is_the_cheapest_thing_to_close():
    from analysis.curve import closest_to_closing

    cur = _cursor(demand=[_d("python", "Python", 40)],
                  held=[_h("python", "Python")], proven=[])
    row = closest_to_closing(cur, OWNER)["ranking"][0]

    assert row["skill"] == "Python"
    assert row["tier"] == "prove it"
    assert row["demand"] == 40
    assert "no confirmed fact" in row["why"]


def test_a_held_skill_that_a_fact_proves_is_already_closed_and_drops_out():
    from analysis.curve import closest_to_closing

    cur = _cursor(demand=[_d("python", "Python", 40)],
                  held=[_h("python", "Python")],
                  proven=[{"skill_norm": "python"}])
    result = closest_to_closing(cur, OWNER)

    assert result["ranking"] == []
    assert result["basis"]["already_closed"] == 1


def test_a_skill_in_progress_is_ranked_to_finish_not_to_prove():
    # It is not held yet, so "write the fact that proves it" would be asking
    # the owner to evidence something they are still learning — which the
    # truth gate would refuse and the interview forbids.
    from analysis.curve import closest_to_closing

    cur = _cursor(demand=[_d("rust", "Rust", 12)],
                  held=[_h("rust", "Rust", status="in_progress")])
    row = closest_to_closing(cur, OWNER)["ranking"][0]

    assert row["tier"] == "finish it"


def test_a_skill_not_held_at_all_is_the_furthest_from_closing():
    from analysis.curve import closest_to_closing

    cur = _cursor(demand=[_d("kubernetes", "Kubernetes", 55)], held=[])
    row = closest_to_closing(cur, OWNER)["ranking"][0]

    assert row["tier"] == "learn it"
    assert row["demand"] == 55


def test_cheaper_tiers_outrank_higher_demand():
    # The whole point of the ordering. A skill 55 roles ask for that would
    # take months to learn is NOT closer to closing than one 3 roles ask for
    # that needs a sentence, and sorting on demand alone would say it is.
    from analysis.curve import closest_to_closing

    cur = _cursor(
        demand=[_d("kubernetes", "Kubernetes", 55), _d("sql", "SQL", 3)],
        held=[_h("sql", "SQL")])
    ranking = closest_to_closing(cur, OWNER)["ranking"]

    assert [r["skill"] for r in ranking] == ["SQL", "Kubernetes"]
    assert [r["tier"] for r in ranking] == ["prove it", "learn it"]


def test_within_a_tier_the_most_asked_for_skill_comes_first():
    from analysis.curve import closest_to_closing

    cur = _cursor(demand=[_d("a", "A", 5), _d("b", "B", 30)],
                  held=[_h("a", "A"), _h("b", "B")])
    ranking = closest_to_closing(cur, OWNER)["ranking"]

    assert [r["skill"] for r in ranking] == ["B", "A"]


def test_a_dormant_skill_is_not_treated_as_held():
    # It must rank as "learn it", not as one sentence away — the owner has
    # said they no longer have it.
    from analysis.curve import closest_to_closing

    cur = _cursor(demand=[_d("cobol", "COBOL", 2)],
                  held=[_h("cobol", "COBOL", status="dormant")])
    ranking = closest_to_closing(cur, OWNER)["ranking"]

    assert ranking[0]["tier"] == "learn it"


def test_every_row_ships_the_receipts_its_ranking_was_computed_from():
    # The house rule. A tier and a position are both claims, and neither can
    # be checked without the numbers behind them.
    from analysis.curve import closest_to_closing

    cur = _cursor(demand=[_d("python", "Python", 40)],
                  held=[_h("python", "Python", learned_at="2026-01-01")])
    row = closest_to_closing(cur, OWNER)["ranking"][0]

    for field in ("skill", "tier", "demand", "held", "proven", "why"):
        assert field in row, field
    assert row["held"] is True and row["proven"] is False


def test_the_basis_reports_how_much_recency_data_exists():
    # B-GAE-046. The brief said learned_at had been collecting for weeks; the
    # column was empty. An answer that silently ignored it would hide that
    # forever, so the count rides in every response — zero is a finding, not
    # a blank.
    from analysis.curve import closest_to_closing

    cur = _cursor(demand=[_d("a", "A", 1), _d("b", "B", 1)],
                  held=[_h("a", "A"), _h("b", "B", learned_at="2026-01-01")])
    basis = closest_to_closing(cur, OWNER)["basis"]

    assert basis["learned_at_known"] == 1
    assert basis["skills_held"] == 2
    assert basis["skills_in_demand"] == 2
    assert basis["ranks_on_recency"] is False, (
        "recency must stay out of the ranking until enough rows carry it — "
        "ordering on a column that is mostly NULL is not a ranking")


def test_the_ranking_is_capped_but_says_what_it_dropped():
    # 902 skills are in demand on the real base. A silent top-10 would read
    # as "these are the only ones", which is the no-silent-caps rule.
    from analysis.curve import closest_to_closing

    cur = _cursor(demand=[_d(f"s{i}", f"S{i}", i) for i in range(30)])
    result = closest_to_closing(cur, OWNER, limit=10)

    assert len(result["ranking"]) == 10
    assert result["basis"]["ranked"] == 10
    assert result["basis"]["not_shown"] == 20


def test_an_owner_with_nothing_recorded_gets_an_empty_ranking_not_an_error():
    from analysis.curve import closest_to_closing

    result = closest_to_closing(_cursor(), OWNER)
    assert result["ranking"] == []
    assert result["basis"]["skills_in_demand"] == 0


@DB_ONLY
def test_the_curve_runs_against_the_real_views_and_real_column_types():
    """The offline tests feed dicts; `v_skill_demand` is a real view over a
    real join and `skill_norms` is a real text[]. This proves the queries
    parse and the shapes line up (B-GAE-016's class).

    B-GAE-050: this test used to assert on whatever `my_skills` happened to
    contain — "the founder's own base" — which made it a measurement of the
    developer's laptop rather than of the query. It passed on live, where he
    holds 21 skills, and failed on any database built from the committed
    migration log plus `ops/ci/02-seed.sql`, which seeds `role_skills` (so
    demand exists) and no `my_skills` at all (so nothing is held). The CI lane
    builds exactly that database, which is why the first honest run of this
    lane went red on a test nobody had changed.

    So it now CREATES what it needs and rolls back. Same query, same real
    views, same real column types — but the arrangement is stated in the test
    instead of inherited from the environment, and the assertions can be about
    the answer rather than about a number that was true one afternoon.
    """
    from db.connection import get_conn
    from analysis.curve import closest_to_closing
    from criteria.writer import add_skill

    with get_conn() as conn:
        try:
            with conn.cursor() as cur:
                cur.execute("select profile_id from profiles "
                            "order by created_at limit 1")
                owner = str(cur.fetchone()["profile_id"])

                # A skill this owner HOLDS that listings ASK for, chosen from
                # real demand rather than invented, so the join under test has
                # something true to match on in either database.
                cur.execute("select skill_asked from role_skills "
                            "where skill_asked is not null limit 1")
                row = cur.fetchone()
                assert row, "no role_skills rows at all — the fixture is broken"
                in_demand = row["skill_asked"]
                add_skill(cur, owner, in_demand, source="test")

                result = closest_to_closing(cur, owner, limit=5)
                basis = result["basis"]

                assert basis["skills_in_demand"] > 0, \
                    "listings ask for skills, but the demand view returned none"
                assert basis["skills_held"] > 0, \
                    "a skill was just written for this owner and the query " \
                    "cannot see it — the join, not the data, is wrong"
                assert len(result["ranking"]) <= 5
                for entry in result["ranking"]:
                    assert entry["tier"] in ("prove it", "finish it", "learn it")
                    assert entry["demand"] >= 1
                # The point of the whole task: a skill the owner HAS, that
                # roles ASK for, that no confirmed fact proves, is one
                # sentence away from being usable on a CV. The row just
                # written is exactly that, so this is now a property of the
                # ranking rather than a count that was true on one afternoon.
                assert any(r["tier"] == "prove it" for r in result["ranking"]), \
                    "a held, in-demand, unevidenced skill did not rank as " \
                    "'prove it'"
        finally:
            conn.rollback()
