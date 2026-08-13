"""Tests for src/discover/merge.py — matched ads become queue listings.

Pins the blast radius (only register-matched ads can ever produce a
role_listings row; recruiter-matched and non-local ads are stamped and left
in the raw layer), the keep-all doctrine (the merge never removes an ad row —
its only aggregator_ads write is the three bookkeeping stamps), and the
prob.py dedupe boundary: an exact-title/same-town twin is absorbed as a
duplicate, a Senior-variant is a different job and gets its own row.
"""
from __future__ import annotations

import os
import uuid

import pytest

from datetime import date

from discover import merge
from discover.merge import SAME_JOB_DUPLICATE_P, merge_pending

from tests.conftest import ScriptedCursor


OWNER = "00000000-0000-4000-a000-000000000001"


def _ad(**kw):
    base = {
        "ad_id": 1, "source": "reed", "employer_name": "Monzo",
        "title": "Software Engineer", "location": "London", "is_local": True,
        "salary_min": 60_000, "salary_max": 80_000, "salary_text": "£60k-£80k",
        "posted_at": date(2026, 7, 20), "ad_url": "https://reed.example/1",
        "content_fingerprint": "fp-ad-1", "matched_org_norm": "monzo bank ltd",
        "sponsor_id": 77, "organisation_name": "Monzo Bank Ltd",
        "town_city": "London", "is_agency": False,
    }
    base.update(kw)
    return base


def _sql(cur, fragment):
    return [(s, p) for s, p in cur.executed if fragment in s.lower()]


def test_fresh_ad_creates_company_and_listing_and_stamps_the_ad():
    cur = ScriptedCursor([
        ("from aggregator_ads", [[_ad()]]),
        ("select company_id from target_companies", [[]]),
        ("insert into target_companies", [[{"company_id": 501}]]),
        ("select role_id, role_title", [[]]),
        ("insert into role_listings", [[{"role_id": 9001}]]),
    ])
    counts = merge_pending(cur, OWNER, limit=10)

    assert counts["merged"] == 1
    assert counts["companies_created"] == 1
    assert len(_sql(cur, "insert into target_companies")) == 1
    assert len(_sql(cur, "insert into role_listings")) == 1
    # the new row is history from birth
    events = _sql(cur, "insert into listing_events")
    assert len(events) == 1 and events[0][1][0] == 9001
    # company creation is an audited crossing
    audits = _sql(cur, "insert into mcp_audit")
    assert len(audits) == 1 and "discover.merge" in str(audits[0][1])
    # the ad is stamped merged with its listing
    stamps = _sql(cur, "update aggregator_ads")
    assert len(stamps) == 1
    assert stamps[0][1] == ("merged", 9001, 1)


def test_recruiter_matched_ad_is_stamped_and_stays_out_of_the_queue():
    cur = ScriptedCursor([
        ("from aggregator_ads", [[_ad(is_agency=True)]]),
    ])
    counts = merge_pending(cur, OWNER, limit=10)
    assert counts["skipped_recruiter"] == 1
    assert _sql(cur, "insert into role_listings") == []
    assert _sql(cur, "insert into target_companies") == []
    stamps = _sql(cur, "update aggregator_ads")
    assert stamps[0][1] == ("skipped_recruiter", None, 1)


def test_non_local_ad_is_stamped_and_stays_out_of_the_queue():
    cur = ScriptedCursor([
        ("from aggregator_ads", [[_ad(is_local=False)]]),
    ])
    counts = merge_pending(cur, OWNER, limit=10)
    assert counts["skipped_not_local"] == 1
    assert _sql(cur, "insert into role_listings") == []


def test_board_twin_is_absorbed_as_a_duplicate_not_a_second_row():
    cur = ScriptedCursor([
        ("from aggregator_ads", [[_ad()]]),
        ("select company_id from target_companies", [[{"company_id": 501}]]),
        ("select role_id, role_title", [[{
            "role_id": 7, "role_title": "Software Engineer",
            "location": "London", "salary_min": 60_000, "salary_max": 80_000,
        }]]),
    ])
    counts = merge_pending(cur, OWNER, limit=10)
    assert counts["duplicate"] == 1
    assert _sql(cur, "insert into role_listings") == []
    stamps = _sql(cur, "update aggregator_ads")
    assert stamps[0][1] == ("duplicate", 7, 1)


def test_senior_variant_is_a_different_job_and_gets_its_own_row():
    cur = ScriptedCursor([
        ("from aggregator_ads", [[_ad()]]),
        ("select company_id from target_companies", [[{"company_id": 501}]]),
        ("select role_id, role_title", [[{
            "role_id": 7, "role_title": "Senior Software Engineer",
            "location": "London", "salary_min": 60_000, "salary_max": 80_000,
        }]]),
        ("insert into role_listings", [[{"role_id": 9002}]]),
    ])
    counts = merge_pending(cur, OWNER, limit=10)
    assert counts["merged"] == 1
    assert len(_sql(cur, "insert into role_listings")) == 1


def test_one_company_row_per_org_however_many_ads():
    ads = [_ad(), _ad(ad_id=2, title="Data Engineer",
                      content_fingerprint="fp-ad-2", ad_url="https://reed.example/2")]
    cur = ScriptedCursor([
        ("from aggregator_ads", [[ads[0], ads[1]]]),
        ("select company_id from target_companies", [[]]),
        ("insert into target_companies", [[{"company_id": 501}]]),
        ("select role_id, role_title", [[]]),
        ("insert into role_listings", [[{"role_id": 9001}], [{"role_id": 9002}]]),
    ])
    counts = merge_pending(cur, OWNER, limit=10)
    assert counts["merged"] == 2
    assert counts["companies_created"] == 1
    assert len(_sql(cur, "insert into target_companies")) == 1


def test_identical_ad_landing_twice_does_not_double_insert():
    # dedupe_key conflict: the insert returns no row; the existing listing
    # absorbs the ad as a duplicate instead.
    cur = ScriptedCursor([
        ("from aggregator_ads", [[_ad()]]),
        ("select company_id from target_companies", [[{"company_id": 501}]]),
        ("select role_id, role_title", [[]]),
        ("insert into role_listings", [[]]),
        ("and dedupe_key = %s", [[{"role_id": 42}]]),
    ])
    counts = merge_pending(cur, OWNER, limit=10)
    assert counts["duplicate"] == 1
    assert _sql(cur, "insert into listing_events") == []
    stamps = _sql(cur, "update aggregator_ads")
    assert stamps[0][1] == ("duplicate", 42, 1)


# --- the pins ----------------------------------------------------------------

def test_pin_merge_selects_only_register_matched_unmerged_ads():
    sql = " ".join(merge.PENDING_SQL.split()).lower()
    assert "matched_org_norm is not null" in sql
    assert "merged_at is null" in sql


def test_pin_merge_never_removes_ad_rows():
    import inspect
    source = inspect.getsource(merge).lower()
    assert "delete from" not in source
    stamp = " ".join(merge.STAMP_SQL.split()).lower()
    # the ONLY aggregator_ads write is the three bookkeeping stamps
    assert stamp.startswith("update aggregator_ads set merge_outcome")
    for content_column in ("employer", "title", "salary", "snippet", "url"):
        assert content_column not in stamp


def test_pin_duplicate_threshold_sits_between_exact_and_near_title():
    from match.prob import same_job_probability
    exact = same_job_probability(
        {"title": "Software Engineer", "location": "London",
         "salary_min": 60_000, "salary_max": 80_000},
        {"title": "Software Engineer", "location": "London",
         "salary_min": 60_000, "salary_max": 80_000})["p"]
    near = same_job_probability(
        {"title": "Software Engineer", "location": "London",
         "salary_min": 60_000, "salary_max": 80_000},
        {"title": "Senior Software Engineer", "location": "London",
         "salary_min": 60_000, "salary_max": 80_000})["p"]
    assert near < SAME_JOB_DUPLICATE_P < exact


# --- B-GAE-018: two owners, one advert -------------------------------------

DB_ONLY = pytest.mark.skipif(
    os.getenv("RUN_DB_TESTS") != "1",
    reason="DB integration tests are opt-in: RUN_DB_TESTS=1")

OWNER_B_MERGE = uuid.UUID("cccccccc-cccc-4ccc-accc-cccccccccccc")


@DB_ONLY
def test_two_owners_merging_the_same_advert_each_get_their_own_listing():
    """B-GAE-018. The aggregator feed is shared, so two owners whose lenses
    overlap see the SAME advert — the normal case for a sponsor-aware engine,
    not the edge one.

    Each owner has their own target_companies row for the org (task 1b), so
    both produce the same dedupe_key(company_name, title, url) with a
    different company_id. While the unique index was on dedupe_key ALONE, the
    second owner's insert hit `do nothing`, fell through to the fallback
    lookup and was handed the FIRST owner's role_id — so they silently never
    received the job, and their ad pointed at another tenant's row.

    No fake can catch this: a FakeCursor has no unique index, which is why
    every existing merge test above passed throughout.
    """
    from db.connection import get_conn
    from discover.merge import _insert_listing

    org = "B-GAE-018 Probe Ltd"
    ad = _ad()
    with get_conn() as conn:
        try:
            with conn.cursor() as cur:
                cur.execute("select profile_id from profiles "
                            "order by created_at limit 1")
                owner_a = cur.fetchone()["profile_id"]
                cur.execute("insert into profiles (profile_id, name) "
                            "values (%s, 'merge probe B')", (OWNER_B_MERGE,))
                ids = []
                for owner in (owner_a, OWNER_B_MERGE):
                    cur.execute(
                        "insert into target_companies (company_name, owner_id, "
                        "sponsor_confidence) values (%s,%s,'sponsors') "
                        "returning company_id", (org, owner))
                    ids.append(cur.fetchone()["company_id"])

                first = _insert_listing(cur, ids[0], org, ad)
                second = _insert_listing(cur, ids[1], org, ad)

                cur.execute("select company_id from role_listings "
                            "where role_id = any(%s)",
                            ([first[0], second[0]],))
                owning = sorted(r["company_id"] for r in cur.fetchall())

            assert first[0] != second[0], (
                "the second owner was handed the first owner's role_id — "
                "they never receive this job at all")
            assert first[1] == "merged" and second[1] == "merged", (
                f"outcomes were {first[1]!r}/{second[1]!r}; the second owner's "
                "advert was recorded as a duplicate of somebody else's row")
            assert owning == sorted(ids), \
                "each listing must belong to its own owner's company row"
        finally:
            conn.rollback()


@DB_ONLY
def test_one_owner_still_cannot_hold_the_same_advert_twice():
    """The other half: scoping the key per company must not stop deduping
    WITHIN a company, which is the whole reason the key exists."""
    from db.connection import get_conn
    from discover.merge import _insert_listing

    org = "B-GAE-018 Probe Solo Ltd"
    ad = _ad()
    with get_conn() as conn:
        try:
            with conn.cursor() as cur:
                cur.execute("select profile_id from profiles "
                            "order by created_at limit 1")
                owner = cur.fetchone()["profile_id"]
                cur.execute(
                    "insert into target_companies (company_name, owner_id, "
                    "sponsor_confidence) values (%s,%s,'sponsors') "
                    "returning company_id", (org, owner))
                company_id = cur.fetchone()["company_id"]

                first = _insert_listing(cur, company_id, org, ad)
                again = _insert_listing(cur, company_id, org, ad)

            assert again[0] == first[0] and again[1] == "duplicate", (
                "the same advert landed twice for one owner — the dedupe key "
                "no longer dedupes")
        finally:
            conn.rollback()
