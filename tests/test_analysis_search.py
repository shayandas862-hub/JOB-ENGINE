"""src/analysis/search.py — the U3 role-lens and skills-gap searches.

search_hiring answers "who is hiring <role words> and can sponsor?" across
the two worlds the machine already holds: tracked listings (live boards,
apply-able today) and census jobs (seen while door-knocking; every census
org is on the sponsor register by construction). skill_gaps_for_words
answers "what do <role words> jobs want that I lack" over stored
role_skills. Fully offline — RoutingCursor serves the rows.
"""
from __future__ import annotations

from tests.test_criteria import RoutingCursor

TRACKED = {"role_id": 917, "title": "Care Assistant", "company_name": "Sunrise Care",
           "location": "Leeds", "role_url": "https://x/1", "salary_text": None,
           "source": "tracked"}
CENSUS = {"title": "Care Assistant (Nights)", "company_name": "Meadow House",
          "org_name_norm": "meadow house ltd", "location": "Leeds",
          "url": "https://x/2", "salary_text": "£24k", "source": "census"}


def _cursor(tracked_rows, census_rows):
    return RoutingCursor([
        ("from role_listings", tracked_rows),
        ("from census_jobs", census_rows),
    ])


def test_search_hiring_merges_tracked_first_then_census():
    from analysis.search import search_hiring
    cur = _cursor([TRACKED], [CENSUS])
    out = search_hiring(cur, "care assistant")
    assert [r["source"] for r in out] == ["tracked", "census"]
    tracked_sql, tracked_params = [
        (s, p) for s, p in cur.executed if "from role_listings" in s.lower()][0]
    low = tracked_sql.lower()
    assert "role_status = 'open'" in low                # live listings only
    assert "ats_token" not in low
    assert sorted(tracked_params["pats"]) == ["%assistant%", "%care%"]
    census_sql, _ = [
        (s, p) for s, p in cur.executed if "from census_jobs" in s.lower()][0]
    assert "title ilike any" in census_sql.lower()


def test_search_hiring_scopes_by_town_when_given():
    from analysis.search import search_hiring
    cur = _cursor([], [])
    search_hiring(cur, "care assistant", town="Leeds")
    for _sql, params in cur.executed:
        assert params["town"] == "%Leeds%"


def test_search_hiring_without_usable_words_is_empty_and_free():
    from analysis.search import search_hiring
    cur = _cursor([], [])
    assert search_hiring(cur, "  of the  ") == []
    assert cur.executed == []


def test_search_hiring_respects_the_overall_limit():
    from analysis.search import search_hiring
    tracked = [dict(TRACKED, role_id=i) for i in range(4)]
    census = [dict(CENSUS, title=f"Care {i}") for i in range(4)]
    out = search_hiring(_cursor(tracked, census), "care", limit=5)
    assert len(out) == 5
    assert [r["source"] for r in out] == ["tracked"] * 4 + ["census"]


def test_skill_gaps_for_words_ranks_demand_and_marks_what_i_lack():
    from analysis.search import skill_gaps_for_words
    rows = [{"skill": "Care Planning", "skill_type": "domain", "demand": 9,
             "i_have_it": False},
            {"skill": "First Aid", "skill_type": "cert", "demand": 4,
             "i_have_it": True}]
    cur = RoutingCursor([("from role_skills", rows)])
    out = skill_gaps_for_words(cur, "owner-1", "care assistant")
    assert out == rows
    sql, params = cur.executed[0]
    low = sql.lower()
    assert "join role_listings" in low                  # the words pick the roles
    assert "my_skills" in low and "owner_id" in low     # owner-scoped have/lack
    assert "order by" in low and "demand" in low.rsplit("order by", 1)[1]
    assert sorted(params["pats"]) == ["%assistant%", "%care%"]
    assert params["owner"] == "owner-1"


def test_skill_gaps_for_words_without_usable_words_is_empty_and_free():
    from analysis.search import skill_gaps_for_words
    cur = RoutingCursor([])
    assert skill_gaps_for_words(cur, "owner-1", "the of") == []
    assert cur.executed == []
