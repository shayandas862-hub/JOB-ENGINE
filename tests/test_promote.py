"""promote_from_census — the census→pipeline bridge, founder-triggered only.

The census NEVER writes target_companies (blast-radius rule, sweep-side
pinned). Promotion is the deliberate, audited, one-org-at-a-time act that
copies a census card's board onto the fetch list so the daily pipeline starts
watching its jobs. Guards: unknown org, already tracked, no board to copy.
"""
from __future__ import annotations

from tests.test_criteria import RoutingCursor

BOARD_CARD = {"org_name_norm": "acme software ltd", "sponsor_id": 7,
              "organisation_name": "Acme Software Ltd", "town_city": "London",
              "probe_outcome": "board_found", "ats_type": "greenhouse",
              "ats_token": "acme", "careers_url": "https://boards.example/acme",
              "local_jobs_seen": 4}
NO_BOARD_CARD = dict(BOARD_CARD, probe_outcome="no_board", ats_type=None,
                     ats_token=None, careers_url=None)


def test_promote_unknown_org_reports_not_found():
    from discover.promote import promote_from_census
    cur = RoutingCursor([("from sponsor_census", [])])
    out = promote_from_census(cur, "owner-1", "ghost ltd")
    assert out["outcome"] == "not_found"
    assert not any("insert into target_companies" in s for s, _ in cur.executed)


def test_promote_already_tracked_org_is_a_no_op_with_the_company_id():
    from discover.promote import promote_from_census
    cur = RoutingCursor([
        ("from sponsor_census", [BOARD_CARD]),
        ("from target_companies", [{"company_id": 5}]),
    ])
    out = promote_from_census(cur, "owner-1", BOARD_CARD["org_name_norm"])
    assert out["outcome"] == "already_tracked" and out["company_id"] == 5
    assert not any("insert into target_companies" in s for s, _ in cur.executed)


def test_promote_without_a_board_returns_the_probe_evidence():
    from discover.promote import promote_from_census
    cur = RoutingCursor([
        ("from sponsor_census", [NO_BOARD_CARD]),
        ("from target_companies", []),
    ])
    out = promote_from_census(cur, "owner-1", NO_BOARD_CARD["org_name_norm"])
    assert out["outcome"] == "no_board"
    assert out["probe_outcome"] == "no_board"
    assert not any("insert into target_companies" in s for s, _ in cur.executed)


def test_promote_copies_the_census_board_onto_the_fetch_list_and_audits():
    from discover.promote import promote_from_census
    cur = RoutingCursor([
        ("from sponsor_census", [BOARD_CARD]),
        ("from target_companies", []),
        ("insert into target_companies", [{"company_id": 9}]),
    ])
    out = promote_from_census(cur, "owner-1", BOARD_CARD["org_name_norm"])
    assert out["outcome"] == "promoted" and out["company_id"] == 9
    assert out["ats_type"] == "greenhouse"
    insert = next((s, p) for s, p in cur.executed
                  if "insert into target_companies" in s)
    assert "register-only" in insert[1]              # sponsor confidence carried
    assert "acme" in insert[1]                       # the board token copied
    assert any("insert into mcp_audit" in s for s, _ in cur.executed)
