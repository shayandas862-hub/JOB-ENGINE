"""Tests for src/discover/agg_store — the aggregator raw keep-all layer.

Pure fake-cursor tests: every ad is stored labelled (matched or not), refresh
never clobbers match/harvest labels, and the quota ledger + resume cursor do
their bookkeeping with upsert math.
"""
from __future__ import annotations

from datetime import date

from tests.conftest import FakeCursor

AD = {
    "source": "adzuna", "external_id": "123",
    "employer_name": "Sky UK Ltd", "title": "AI Engineer",
    "location": "London, UK", "salary_min": 60000, "salary_max": 80000,
    "salary_text": "£60,000 - £80,000", "posted_at": "2026-07-20",
    "ad_url": "https://www.adzuna.co.uk/land/ad/123", "snippet": "Do AI.",
}
FOREIGN_AD = {
    "source": "reed", "external_id": "987",
    "employer_name": "Acme Corp", "title": "Platform Engineer",
    "location": "New York, NY, US", "salary_min": None, "salary_max": None,
    "salary_text": None, "posted_at": None,
    "ad_url": "https://www.reed.co.uk/jobs/987", "snippet": "",
}
TOWN_AD = {
    "source": "reed", "external_id": "988",
    "employer_name": "Basingstoke Soft Ltd", "title": "Dev",
    "location": "Basingstoke", "salary_min": None, "salary_max": None,
    "salary_text": None, "posted_at": None,
    "ad_url": "https://www.reed.co.uk/jobs/988", "snippet": "",
}


def test_ad_keys_are_deterministic_and_fingerprint_is_cross_source():
    from discover.agg_store import ad_dedupe_key, ad_fingerprint
    assert ad_dedupe_key("adzuna", "123") == ad_dedupe_key("adzuna", "123")
    assert ad_dedupe_key("adzuna", "123") != ad_dedupe_key("reed", "123")
    # the SAME job seen via two sources shares one content fingerprint
    a = ad_fingerprint("Sky UK Ltd", "AI Engineer", "London, UK")
    b = ad_fingerprint("Sky UK Ltd.", "AI  Engineer", "london, uk")
    assert a == b


def test_insert_ads_stores_everything_labelled_and_preserves_match_labels():
    from discover.agg_store import insert_ads
    cur = FakeCursor()
    assert insert_ads(cur, [AD, FOREIGN_AD, TOWN_AD]) == 3
    assert len(cur.executed_many) == 1
    sql, rows = cur.executed_many[0]
    low = sql.lower()
    assert "insert into aggregator_ads" in low
    assert "on conflict (dedupe_key) do update" in low
    # a refresh must NEVER clobber the label passes
    update_clause = low.split("do update", 1)[1]
    assert "matched_org_norm" not in update_clause
    assert "harvest_checked_at" not in update_clause
    assert len(rows) == 3
    assert rows[0][3] == "sky uk ltd"            # employer_norm via shared norm()
    assert rows[0][6] is True                    # is_local: London
    assert rows[1][6] is False                   # keep-all: foreign stored, labelled
    # country-scoped sources (Adzuna /gb, Reed UK): a bare UK town with no
    # foreign marker is local — the API's own country scope decides.
    assert rows[2][6] is True


def test_insert_ads_empty_is_a_noop():
    from discover.agg_store import insert_ads
    cur = FakeCursor()
    assert insert_ads(cur, []) == 0
    assert cur.executed_many == []


def test_quota_spent_reads_the_shared_ledger():
    # The write half lives in budget.ledger since task 5 (one writer, at the
    # HTTP choke point); what agg_store still owns is this read, which the
    # sweep uses for its own per-slice cap.
    from discover.agg_store import quota_spent

    assert quota_spent(FakeCursor(rows=[{"calls": 7}]), "reed", date(2026, 7, 22)) == 7
    assert quota_spent(FakeCursor(rows=[]), "reed", date(2026, 7, 22)) == 0


def test_cursor_save_upserts_and_load_returns_row_or_none():
    from discover.agg_store import load_cursor, save_cursor
    cur = FakeCursor()
    save_cursor(cur, "reed|kw=|loc=", "reed", {"keywords": None},
                next_page=4, total_reported=39000, ads_seen_inc=100,
                pass_complete=False)
    sql, params = cur.executed[0]
    low = sql.lower()
    assert "on conflict (slice_key) do update" in low
    assert "aggregator_cursor.ads_seen +" in low  # running total, never reset
    assert load_cursor(FakeCursor(rows=[]), "nope") is None
    row = {"next_page": 4, "pass_complete": False, "ads_seen": 300}
    assert load_cursor(FakeCursor(rows=[row]), "reed|kw=|loc=") == row
