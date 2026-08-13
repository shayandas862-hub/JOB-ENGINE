"""census_queries — curated, secret-free reads over the census for the MCP skin.

list_software_companies is the founder's "software company lot": every census
card whose Pass-1 industry codes overlap SOFTWARE_SIC, boards-found first so
the immediately fetchable ones surface. The column list is explicit and never
includes ats_token (the one census secret), same rule the queue reads pin.
"""
from __future__ import annotations

from tests.test_criteria import RoutingCursor

CARD = {"org_name_norm": "acme software ltd",
        "organisation_name": "Acme Software Ltd", "town_city": "London",
        "registry_status": "active", "industry_codes": ["62012"],
        "incorporated": None, "probe_outcome": "board_found",
        "ats_type": "greenhouse", "careers_url": "https://x",
        "local_jobs_seen": 4, "total_jobs_seen": 9}


def test_list_software_companies_narrows_to_software_and_hides_the_token():
    from discover.census_queries import list_software_companies
    cur = RoutingCursor([("from sponsor_census", [CARD])])
    out = list_software_companies(cur, 25)
    assert out == [CARD]
    sql, params = cur.executed[0]
    assert "industry_codes && %(sic)s::text[]" in sql
    assert "ats_token" not in sql                       # the census secret
    assert "limit %(n)s" in sql and params["n"] == 25
    from discover.classify import SOFTWARE_SIC
    assert set(params["sic"]) == set(SOFTWARE_SIC)
    # fetchable-first ordering: boards found, then most local jobs seen
    order = sql.rsplit("order by", 1)[1]
    assert "probe_outcome = 'board_found'" in order
    assert "local_jobs_seen" in order


def test_list_software_companies_can_filter_to_boards_only():
    from discover.census_queries import list_software_companies
    cur = RoutingCursor([("from sponsor_census", [CARD])])
    list_software_companies(cur, 10, with_boards_only=True)
    sql, _ = cur.executed[0]
    assert "and probe_outcome = 'board_found'" in sql


# ---- lens_coverage (Phase 8.5 / U4: the brief's honest doors line) ---------

def test_lens_coverage_counts_knocked_vs_total_for_the_codes():
    from discover.census_queries import lens_coverage
    cur = RoutingCursor([
        ("from sponsor_census", [{"knocked": 43, "total": 6261}])])
    out = lens_coverage(cur, ["87300", "87100"])
    assert out == {"knocked": 43, "total": 6261, "pct": 0.7}
    sql, params = cur.executed[0]
    low = sql.lower()
    # the same slice the Pass-2 picker sees: registry-matched, lens codes
    assert "registry_outcome = 'matched'" in low
    assert "industry_codes && %(codes)s::text[]" in low
    assert params["codes"] == ["87300", "87100"]


def test_lens_coverage_survives_an_empty_slice():
    from discover.census_queries import lens_coverage
    cur = RoutingCursor([
        ("from sponsor_census", [{"knocked": 0, "total": 0}])])
    assert lens_coverage(cur, ["99999"]) == {"knocked": 0, "total": 0,
                                             "pct": 0.0}


def test_lens_coverage_without_codes_is_none_and_free():
    from discover.census_queries import lens_coverage
    cur = RoutingCursor([])
    assert lens_coverage(cur, []) is None
    assert cur.executed == []


# ---- search_sponsors (Phase 8.5 / U3: the universal census search) ---------

SPONSOR_ROW = {"org_name_norm": "sunrise care ltd",
               "organisation_name": "Sunrise Care Ltd", "town_city": "Leeds",
               "registry_status": "active", "industry_codes": ["87300"],
               "industry_descriptions": [
                   "Residential care activities for the elderly and disabled"],
               "probe_outcome": "board_found", "careers_url": "https://x",
               "local_jobs_seen": 3, "total_jobs_seen": 5}


def test_search_sponsors_answers_the_leeds_acceptance_question():
    # THE acceptance from the phase card: "care-home sponsors in Leeds with
    # live boards" answers over the existing view — plain-English industry,
    # town, board status, receipts riding along (industry_descriptions).
    from discover.census_queries import search_sponsors
    cur = RoutingCursor([("from v_sponsor_industry", [SPONSOR_ROW])])
    out = search_sponsors(cur, industry_words="care homes", town="Leeds",
                          with_boards_only=True)
    assert out == [SPONSOR_ROW]
    sql, params = cur.executed[0]
    low = sql.lower()
    assert "from v_sponsor_industry" in low
    assert "industry_descriptions" in low
    assert "ats_token" not in low                       # the census secret
    assert "probe_outcome = 'board_found'" in low       # live boards only
    assert sorted(params["pats"]) == ["%care%", "%home%"]
    assert params["town"] == "%Leeds%"
    # fetchable-first ordering, same promise as the software list
    order = low.rsplit("order by", 1)[1]
    assert "board_found" in order and "local_jobs_seen" in order


def test_search_sponsors_filters_are_all_optional():
    from discover.census_queries import search_sponsors
    cur = RoutingCursor([("from v_sponsor_industry", [SPONSOR_ROW])])
    search_sponsors(cur)                                # a plain browse
    sql, params = cur.executed[0]
    low = sql.lower()
    assert "ilike" not in low                           # no word/town filter
    # no board FILTER — the boards-first ORDERING promise still stands
    assert "probe_outcome = 'board_found'" not in low.split("order by")[0]
    assert params["n"] == 25


def test_search_sponsors_with_only_stopwords_searches_unfiltered():
    # "of the" carries no tokens — treat as no industry filter rather than
    # matching nothing (the human said words, the machine found none usable).
    from discover.census_queries import search_sponsors
    cur = RoutingCursor([("from v_sponsor_industry", [])])
    search_sponsors(cur, industry_words="of the")
    sql, _ = cur.executed[0]
    assert "industry_descriptions" not in sql.lower().split("order by")[0] \
        or "ilike" not in sql.lower()
