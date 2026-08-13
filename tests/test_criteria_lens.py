"""Tests for src/criteria/lens.py — plain words → ranked SIC candidates (U2).

The translator is deterministic code: token search over sic_codes
descriptions, ranked by tokens matched then sponsor count. Choosing from the
candidates is the client AI's job; writing the choice stays with
set_promotion_rule. Fully offline — RoutingCursor serves the rows.
"""
from __future__ import annotations

from tests.test_criteria import RoutingCursor

# What the live table holds for the care-home shape of query (measured
# 2026-08-10): no SIC description contains the literal phrase "care homes",
# so token matching is what makes the translator work at all.
SIC_ROWS = [
    {"code": "87300",
     "description": "Residential care activities for the elderly and disabled"},
    {"code": "86102", "description": "Medical nursing home activities"},
    {"code": "88100",
     "description": "Home care services for the elderly and disabled"},
    {"code": "01621", "description": "Farm animal boarding and care"},
]
SPONSOR_COUNTS = [
    {"code": "87300", "sponsors": 3911},
    {"code": "86102", "sponsors": 210},
    {"code": "88100", "sponsors": 1500},
    {"code": "01621", "sponsors": 3},
]


def make_cursor(sic_rows=None, counts=None):
    return RoutingCursor([
        ("from sic_codes", SIC_ROWS if sic_rows is None else sic_rows),
        ("from sponsor_census", SPONSOR_COUNTS if counts is None else counts),
    ])


def test_two_token_matches_outrank_bigger_single_token_codes():
    # "care homes" → tokens [care, home]. 88100 matches both and must lead,
    # even though 87300 (care only) has more sponsors.
    from criteria.lens import find_industry_codes
    got = find_industry_codes(make_cursor(), "care homes")
    assert [r["code"] for r in got[:2]] == ["88100", "87300"]
    # the receipt names the OWNER'S words, not internal stems
    assert got[0]["matched"] == ["care", "homes"]


def test_single_token_ties_break_by_sponsor_count_then_code():
    from criteria.lens import find_industry_codes
    got = find_industry_codes(make_cursor(), "care homes")
    # After 88100 (2 tokens): 87300 (care, 3911) > 86102 (home, 210) > 01621 (care, 3)
    assert [r["code"] for r in got] == ["88100", "87300", "86102", "01621"]


def test_every_candidate_carries_code_description_sponsors_and_matched():
    # No naked numbers: the AI/human picks from evidence, so every row says
    # which tokens hit and how many sponsors carry the code.
    from criteria.lens import find_industry_codes
    for row in find_industry_codes(make_cursor(), "care homes"):
        assert set(row) == {"code", "description", "sponsors", "matched"}
        assert isinstance(row["sponsors"], int) and row["matched"]


def test_codes_absent_from_the_census_count_zero_sponsors():
    from criteria.lens import find_industry_codes
    got = find_industry_codes(make_cursor(counts=[]), "care homes")
    assert all(r["sponsors"] == 0 for r in got)


def test_plurals_match_their_singular_descriptions():
    # "restaurants" must match "... restaurants ..." AND a singular
    # description; the stem is a shared prefix, not a dictionary.
    from criteria.lens import find_industry_codes
    rows = [{"code": "56101", "description": "Licensed restaurants"},
            {"code": "56102", "description": "Unlicensed restaurant"}]
    got = find_industry_codes(make_cursor(sic_rows=rows), "restaurants")
    assert {r["code"] for r in got} == {"56101", "56102"}


def test_ies_plurals_match_both_forms():
    from criteria.lens import find_industry_codes
    rows = [{"code": "66110", "description": "Administration of financial markets activity"},
            {"code": "66190", "description": "Other financial activities"}]
    got = find_industry_codes(make_cursor(sic_rows=rows), "financial activities")
    assert {r["code"] for r in got} == {"66110", "66190"}


def test_stopwords_alone_return_nothing_and_touch_no_table():
    from criteria.lens import find_industry_codes
    cur = make_cursor()
    assert find_industry_codes(cur, "of the and for") == []
    assert cur.executed == []
    assert find_industry_codes(cur, "   ") == []


def test_no_match_returns_empty_without_counting_sponsors():
    from criteria.lens import find_industry_codes
    cur = make_cursor(sic_rows=[])
    assert find_industry_codes(cur, "zzzz") == []
    assert not any("sponsor_census" in sql for sql, _ in cur.executed)


def test_words_travel_as_parameters_never_in_the_sql_text():
    # Injection guard: the user's words reach SQL only as bound parameters.
    from criteria.lens import find_industry_codes
    cur = make_cursor(sic_rows=[])
    hostile = "x%'; drop table sic_codes;--"
    find_industry_codes(cur, hostile)
    for sql, _params in cur.executed:
        assert "drop table" not in sql.lower()


def test_limit_caps_the_ranked_list():
    from criteria.lens import find_industry_codes
    got = find_industry_codes(make_cursor(), "care homes", limit=2)
    assert len(got) == 2
    assert got[0]["code"] == "88100"
