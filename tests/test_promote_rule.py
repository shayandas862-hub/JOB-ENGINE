"""Tests for src/discover/promote_rule.py — the promote button becomes a rule.

The census blast-radius wall survives (the sweep still never writes
target_companies — pinned in test_sweep/test_census_store); this module is
the AUDITED crossing, and its own pin here says the crossing stays single:
promote_rule may reach target_companies only through promote.promote_from_census.

Rule semantics pinned: a board_found card auto-promotes when ALL THREE hold —
industry code in the owner's set, a local census job matching the owner's
target_roles, and the local-jobs floor. Exactly one condition missing =
borderline -> a capped promotion_review flag. Two or more missing = silence.
"""
from __future__ import annotations

import pytest

from discover import promote_rule
from discover.promote_rule import PROMOTION_REVIEW_CAP, evaluate_rule

from tests.conftest import ScriptedCursor

OWNER = "00000000-0000-4000-a000-000000000001"

RULE_ROW = {"industry_codes": ["62012", "62020"], "min_local_jobs": 1,
            "auto": True}
ROLE_ROWS = [{"search_title": "Software Engineer"},
             {"search_title": "Data Engineer"}]


def _card(**kw):
    base = {"org_name_norm": "acme ai ltd", "organisation_name": "Acme AI Ltd",
            "industry_codes": ["62012"], "local_jobs_seen": 4}
    base.update(kw)
    return base


def _cursor(cards, *, jobs_per_org=None, open_flags=0, rule=RULE_ROW):
    return ScriptedCursor([
        ("from promotion_rules", [[rule]] if rule else [[]]),
        ("from target_roles", [[*ROLE_ROWS]]),
        ("from sponsor_census", [cards]),
        ("from census_jobs", jobs_per_org if jobs_per_org is not None
         else [[{"title": "Software Engineer"}]]),
        ("select count(*) as n from review_items where kind",
         [[{"n": open_flags}]]),
        ("insert into review_items", [[{"review_id": 1, "kind": "promotion_review",
                                        "ref": "acme ai ltd", "status": "open"}]]),
    ])


@pytest.fixture
def promoted(monkeypatch):
    calls = []

    def fake_promote(cur, owner_id, org_name_norm):
        calls.append(org_name_norm)
        return {"outcome": "promoted", "company_id": 900 + len(calls),
                "org_name_norm": org_name_norm}
    monkeypatch.setattr(promote_rule, "promote_from_census", fake_promote)
    return calls


def test_card_passing_all_three_conditions_auto_promotes(promoted):
    cur = _cursor([_card()])
    counts = evaluate_rule(cur, OWNER)
    assert counts["promoted"] == 1
    assert promoted == ["acme ai ltd"]
    assert counts["flagged"] == 0


def test_missing_title_evidence_is_borderline_and_flagged(promoted):
    cur = _cursor([_card()], jobs_per_org=[[{"title": "Quantity Surveyor"}]])
    counts = evaluate_rule(cur, OWNER)
    assert counts["promoted"] == 0
    assert counts["flagged"] == 1
    assert promoted == []
    flag_sql, flag_params = [
        (s, p) for s, p in cur.executed if "insert into review_items" in s][0]
    assert "promotion_review" in str(flag_params)
    assert "title" in str(flag_params)      # the evidence names what is missing


def test_wrong_industry_with_matching_titles_is_borderline(promoted):
    cur = _cursor([_card(industry_codes=["64191"])])   # a bank hiring engineers
    counts = evaluate_rule(cur, OWNER)
    assert counts["promoted"] == 0
    assert counts["flagged"] == 1


def test_two_conditions_missing_is_silence_not_noise(promoted):
    cur = _cursor([_card(industry_codes=["64191"])],
                  jobs_per_org=[[{"title": "Quantity Surveyor"}]])
    counts = evaluate_rule(cur, OWNER)
    assert counts["promoted"] == 0
    assert counts["flagged"] == 0
    assert counts["skipped"] == 1


def test_local_jobs_floor_gates_promotion(promoted):
    cur = _cursor([_card(local_jobs_seen=0)],
                  jobs_per_org=[[]],
                  rule={**RULE_ROW, "min_local_jobs": 1})
    counts = evaluate_rule(cur, OWNER)
    assert counts["promoted"] == 0
    assert counts["skipped"] == 1          # no local jobs -> no titles either


def test_flag_cap_stops_new_flags_but_never_blocks_promotions(promoted):
    cur = _cursor(
        [_card(), _card(org_name_norm="other ltd",
                        organisation_name="Other Ltd",
                        industry_codes=["64191"])],
        jobs_per_org=[[{"title": "Software Engineer"}],
                      [{"title": "Software Engineer"}]],
        open_flags=PROMOTION_REVIEW_CAP)
    counts = evaluate_rule(cur, OWNER)
    assert counts["promoted"] == 1          # the pass still promotes
    assert counts["flagged"] == 0           # the cap held
    assert counts["cap_hit"] is True
    assert all("insert into review_items" not in s for s, _ in cur.executed)


def test_auto_off_means_nothing_happens(promoted):
    cur = _cursor([_card()], rule={**RULE_ROW, "auto": False})
    counts = evaluate_rule(cur, OWNER)
    assert counts == {"outcome": "auto_off"}
    assert promoted == []


def test_no_rule_row_means_nothing_happens(promoted):
    cur = _cursor([_card()], rule=None)
    counts = evaluate_rule(cur, OWNER)
    assert counts == {"outcome": "no_rule"}
    assert promoted == []


def test_already_tracked_is_counted_not_flagged(monkeypatch):
    monkeypatch.setattr(
        promote_rule, "promote_from_census",
        lambda cur, owner, org: {"outcome": "already_tracked",
                                 "company_id": 5, "org_name_norm": org})
    cur = _cursor([_card()])
    counts = evaluate_rule(cur, OWNER)
    assert counts["already_tracked"] == 1
    assert counts["promoted"] == 0


def test_save_rule_upserts_partially_and_audits():
    from discover.promote_rule import save_rule
    cur = ScriptedCursor([
        ("insert into promotion_rules", [[{
            "owner_id": OWNER, "industry_codes": ["62012"],
            "min_local_jobs": 3, "auto": True,
            "adzuna_category": "it-jobs"}]]),
    ])
    row = save_rule(cur, OWNER, min_local_jobs=3)
    assert row["min_local_jobs"] == 3
    upsert_sql, upsert_params = [
        (s, p) for s, p in cur.executed if "insert into promotion_rules" in s][0]
    assert "on conflict (owner_id) do update" in upsert_sql.lower()
    # partial update: untouched fields keep their stored values
    assert "coalesce" in upsert_sql.lower()
    audits = [(s, p) for s, p in cur.executed if "insert into mcp_audit" in s]
    assert len(audits) == 1 and "promote_rule.save" in str(audits[0][1])


def test_save_rule_carries_the_owner_ads_category():
    # U1: the Adzuna ads category is part of the owner's lens row — settable
    # by conversation, partial like every other field.
    from discover.promote_rule import save_rule
    cur = ScriptedCursor([
        ("insert into promotion_rules", [[{
            "owner_id": OWNER, "industry_codes": ["87300"],
            "min_local_jobs": 1, "auto": True,
            "adzuna_category": "social-work-jobs"}]]),
    ])
    row = save_rule(cur, OWNER, adzuna_category="social-work-jobs")
    assert row["adzuna_category"] == "social-work-jobs"
    upsert_sql, params = [
        (s, p) for s, p in cur.executed if "insert into promotion_rules" in s][0]
    assert "adzuna_category" in upsert_sql.lower()
    assert "social-work-jobs" in params


def test_load_rule_serves_the_ads_category():
    from discover.promote_rule import load_rule
    cur = ScriptedCursor([
        ("from promotion_rules", [[{
            "industry_codes": ["87300"], "min_local_jobs": 1, "auto": True,
            "adzuna_category": "social-work-jobs"}]]),
    ])
    rule = load_rule(cur, OWNER)
    assert rule["adzuna_category"] == "social-work-jobs"
    sql = cur.executed[0][0].lower()
    assert "adzuna_category" in sql


def test_pin_the_crossing_stays_single():
    # promote_rule reaches target_companies ONLY via promote_from_census —
    # the audited bridge built for the manual button.
    import inspect
    source = inspect.getsource(promote_rule).lower()
    assert "insert into target_companies" not in source
    assert "promote_from_census" in source
