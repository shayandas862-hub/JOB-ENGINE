"""Tests for src/discover/onboarding — the auto-onboarding pipeline.

Offline by default: classify_company is monkeypatched (no HTTP) and a FakeCursor
pins the writes. One opt-in integration test (RUN_DB_TESTS=1) runs the real SQL
against a seeded scratch schema and proves idempotency end to end.
"""
from __future__ import annotations

import json
import os

import pytest

from tests.conftest import FakeCursor


def candidate(sponsor_id=10, name="Acme AI Ltd", norm_name="acme ai ltd",
              town="London"):
    from discover.register import SponsorCandidate
    return SponsorCandidate(sponsor_id, name, norm_name, town, None, "A", "Skilled Worker")


def stub_classify(monkeypatch, classification):
    from discover import onboarding
    monkeypatch.setattr(onboarding, "classify_company",
                        lambda name, session=None: classification)


def greenhouse(name="Acme AI Ltd", token="acme", n=12):
    from fetch.ats import ATS_GREENHOUSE, Classification
    return Classification(name, ATS_GREENHOUSE, token,
                          f"https://boards.greenhouse.io/{token}", n)


def no_board(name="Beta Data Ltd"):
    from fetch.ats import ATS_UNKNOWN, Classification
    return Classification(name, ATS_UNKNOWN, None, None, None)


# ---- board hit: joins the fetch list ---------------------------------------

def test_classified_candidate_joins_the_fetch_list(monkeypatch):
    from discover import onboarding
    stub_classify(monkeypatch, greenhouse())
    cur = FakeCursor(rows=[{"company_id": 501}])

    r = onboarding.onboard_candidate(cur, "p-1", candidate())

    assert r.outcome == "onboarded" and r.company_id == 501
    assert r.ats_type == "greenhouse" and r.ats_token == "acme"
    ins_sql, ins_params = cur.executed[0]
    low = ins_sql.lower()
    assert "insert into target_companies" in low
    # the columns the fetch list selects on (scripts/fetch_jobs.py) are set
    assert "ats_type" in low and "ats_token" in low
    assert "greenhouse" in ins_params and "acme" in ins_params
    assert 10 in ins_params                       # sponsor_id linked to the register
    assert "register-only" in ins_params          # sponsor_confidence vocab
    assert "p-1" in ins_params                     # owner-scoped


def test_onboarded_write_is_audited(monkeypatch):
    from discover import onboarding
    stub_classify(monkeypatch, greenhouse())
    cur = FakeCursor(rows=[{"company_id": 501}])
    onboarding.onboard_candidate(cur, "p-1", candidate())
    audit_sql, audit_params = cur.executed[1]
    assert "insert into mcp_audit" in audit_sql.lower()
    assert audit_params[0] == onboarding.AUDIT_TOOL


# ---- no board: becomes a review flag ---------------------------------------

def test_unclassifiable_candidate_becomes_a_review_flag(monkeypatch):
    from discover import onboarding
    stub_classify(monkeypatch, no_board())
    cur = FakeCursor(rows=[{"review_id": 77, "kind": "company_onboard",
                            "ref": "beta data ltd", "status": "open"}])

    r = onboarding.onboard_candidate(cur, "p-1", candidate(11, "Beta Data Ltd", "beta data ltd", "Leeds"))

    assert r.outcome == "flagged" and r.review_id == 77 and r.company_id is None
    flag_sql, flag_params = cur.executed[0]
    assert "insert into review_items" in flag_sql.lower()
    assert onboarding.ONBOARD_FLAG_KIND in flag_params      # 'company_onboard'
    assert "beta data ltd" in flag_params                   # ref = org_name_norm
    assert "insert into mcp_audit" in cur.executed[1][0].lower()


def test_flag_evidence_carries_probe_details_for_claude(monkeypatch):
    from discover import onboarding
    stub_classify(monkeypatch, no_board())
    cur = FakeCursor(rows=[{"review_id": 77}])
    onboarding.onboard_candidate(cur, "p-1", candidate(11, "Beta Data Ltd", "beta data ltd", "Leeds"))
    evidence = json.loads(cur.executed[0][1][3])           # 4th bound param = evidence JSON
    assert evidence["company_name"] == "Beta Data Ltd"
    assert evidence["sponsor_id"] == 11
    assert evidence["org_name_norm"] == "beta data ltd"
    assert evidence["tokens_tried"]                         # a non-empty probe trail


def test_reflagging_the_same_company_is_a_no_op(monkeypatch):
    from discover import onboarding
    stub_classify(monkeypatch, no_board())
    cur = FakeCursor(rows=[])                               # not-exists guard -> nothing returned
    r = onboarding.onboard_candidate(cur, "p-1", candidate(11, "Beta Data Ltd", "beta data ltd"))
    assert r.outcome == "already_flagged" and r.review_id is None
    assert len(cur.executed) == 1                           # only the skipped insert; no audit
    assert "insert into review_items" in cur.executed[0][0].lower()


# ---- batch ------------------------------------------------------------------

def test_batch_onboards_each_candidate(monkeypatch):
    from discover import onboarding
    stub_classify(monkeypatch, greenhouse(token="tok", n=3))
    cur = FakeCursor(rows=[{"company_id": 900}])
    out = onboarding.onboard_candidates(
        cur, "p-1", [candidate(1, "One Ltd", "one ltd"), candidate(2, "Two Ltd", "two ltd")])
    assert [r.outcome for r in out] == ["onboarded", "onboarded"]
    assert all(r.company_id == 900 for r in out)


# ---- opt-in integration: real SQL, real idempotency ------------------------

@pytest.mark.skipif(
    os.getenv("RUN_DB_TESTS") != "1",
    reason="DB integration tests are opt-in: RUN_DB_TESTS=1",
)
def test_onboarding_writes_real_rows_and_is_idempotent(monkeypatch):
    from db.connection import get_conn
    from discover import onboarding

    schema = "tq_onboard_test"
    owner = "11111111-1111-4111-a111-111111111111"
    board = candidate(1, "Board Co", "board co", "London")
    dark = candidate(2, "Dark Co", "dark co", "Leeds")

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f"drop schema if exists {schema} cascade")
            cur.execute(f"create schema {schema}")
            cur.execute(f"set search_path to {schema}")
            # B-GAE-020: these three were hand-written column lists, and
            # review_items drifted the moment migration 0056 added owner_id —
            # src/review.py wrote the column and the scratch table had no such
            # column, so the test died on UndefinedColumn while the live table
            # was perfectly correct. LIKE cannot drift, which is the whole of
            # the B-GAE-015 shape. All three are converted, not just the one
            # that broke: target_companies was missing eight real columns and
            # was the same bug waiting for the next migration.
            #
            # The owner_id / sponsor_id foreign keys are deliberately NOT
            # re-added (LIKE does not copy them): this scratch schema holds no
            # profiles or licensed_sponsors table, and these tests use a
            # synthetic owner on purpose.
            cur.execute("""
                create table target_companies
                  (like public.target_companies including all);
                create table review_items
                  (like public.review_items including all);
                create table mcp_audit
                  (like public.mcp_audit including all);
            """)
            stub_classify(monkeypatch, greenhouse("Board Co", "boardco", 7))
            r1 = onboarding.onboard_candidate(cur, owner, board)
            stub_classify(monkeypatch, no_board("Dark Co"))
            r2 = onboarding.onboard_candidate(cur, owner, dark)
            r3 = onboarding.onboard_candidate(cur, owner, dark)   # idempotent

            cur.execute("select company_name, ats_type, ats_token, web_checked, "
                        "sponsor_confidence from target_companies")
            companies = cur.fetchall()
            cur.execute("select kind, ref, status from review_items")
            flags = cur.fetchall()
            cur.execute("select count(*) n from mcp_audit")
            audits = cur.fetchone()["n"]
            cur.execute(f"drop schema {schema} cascade")
        conn.rollback()

    assert (r1.outcome, r2.outcome, r3.outcome) == ("onboarded", "flagged", "already_flagged")
    assert len(companies) == 1
    c = companies[0]
    assert c["ats_type"] == "greenhouse" and c["ats_token"] == "boardco"
    assert c["web_checked"] is True and c["sponsor_confidence"] == "register-only"
    assert len(flags) == 1 and flags[0]["kind"] == "company_onboard" and flags[0]["ref"] == "dark co"
    assert audits == 2                                       # onboard + first flag; no-op not audited
