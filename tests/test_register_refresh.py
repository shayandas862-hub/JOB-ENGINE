"""Tests for src/discover/register_refresh.py — the weekly register diff.

Closes the 2026-08-02 gap: the sponsor register was loaded once, by hand,
and never re-downloaded. Pins: the diff unit is (org_name_norm, route);
additions insert (keep-all grows) and stamp a census card; removals are
STAMPED licence_removed_at, never deleted; a re-licensed org gets its stamp
cleared; every refresh writes one bookkeeping row; and the staleness check
makes the refresh self-scheduling inside the daily loop.
"""
from __future__ import annotations

from discover.register_refresh import (find_csv_url, parse_register_csv,
                                       refresh, refresh_is_due)

from tests.conftest import ScriptedCursor

CSV = """Organisation Name,Town/City,County,Type & Rating,Route
Acme AI Ltd,London,,Worker (A rating),Skilled Worker
Acme AI Ltd,London,,Worker (A rating),Global Business Mobility: Senior or Specialist Worker
"Commas, Brackets & Co",Leeds,West Yorkshire,Temporary Worker (B rating),Creative Worker
Fresh Sponsor Ltd,Bristol,,Worker (A rating),Skilled Worker
"""


def test_parse_derives_norm_rating_and_skilled_flag():
    rows = parse_register_csv(CSV)
    assert len(rows) == 4
    first = rows[0]
    assert first["organisation_name"] == "Acme AI Ltd"
    assert first["org_name_norm"] == "acme ai ltd"
    assert first["rating"] == "A"
    assert first["is_skilled_worker"] is True
    assert rows[1]["is_skilled_worker"] is False       # GBM route
    assert rows[2]["rating"] == "B"
    assert rows[2]["organisation_name"] == "Commas, Brackets & Co"


def test_find_csv_url_absolutises_the_first_csv_link():
    html = ('<a href="/media/abc/2026-08-01_Worker_and_Temporary_Worker.csv">'
            "Download</a>")
    url = find_csv_url(html)
    assert url == ("https://assets.publishing.service.gov.uk/media/abc/"
                   "2026-08-01_Worker_and_Temporary_Worker.csv")


def test_find_csv_url_none_when_absent():
    assert find_csv_url("<p>no downloads today</p>") is None


def _db_rows():
    return [
        # stays licensed
        {"id": 1, "org_name_norm": "acme ai ltd", "route": "Skilled Worker",
         "licence_removed_at": None},
        {"id": 2, "org_name_norm": "acme ai ltd",
         "route": "Global Business Mobility: Senior or Specialist Worker",
         "licence_removed_at": None},
        # vanishes from the CSV -> stamped removed
        {"id": 3, "org_name_norm": "gone plc", "route": "Skilled Worker",
         "licence_removed_at": None},
        # already stamped removed -> not re-stamped
        {"id": 4, "org_name_norm": "long gone ltd", "route": "Skilled Worker",
         "licence_removed_at": "2026-07-01"},
        # was removed, is back in the CSV -> stamp cleared
        {"id": 5, "org_name_norm": "commas, brackets & co",
         "route": "Creative Worker", "licence_removed_at": "2026-07-01"},
    ]


def _refresh(cur):
    return refresh(cur, parse_register_csv(CSV),
                   source_file="2026-08-01_Worker_and_Temporary_Worker.csv")


def test_refresh_diffs_by_org_and_route():
    cur = ScriptedCursor([
        ("select id, org_name_norm, route", [_db_rows()]),
    ])
    counts = _refresh(cur)
    assert counts == {"csv_rows": 4, "added": 1, "removed": 1,
                      "re_licensed": 1, "orgs_carded": 1}

    inserts = [(s, p) for s, p in cur.executed
               if "insert into licensed_sponsors" in s]
    assert len(inserts) == 1
    assert inserts[0][1][0][0] == "Fresh Sponsor Ltd"    # the one new pair

    census = [(s, p) for s, p in cur.executed if "insert into sponsor_census" in s]
    assert len(census) == 1 and census[0][1][0] == "fresh sponsor ltd"

    removals = [(s, p) for s, p in cur.executed
                if "set licence_removed_at = now()" in s]
    assert len(removals) == 1 and removals[0][1] == ([3],)

    cleared = [(s, p) for s, p in cur.executed
               if "set licence_removed_at = null" in s]
    assert len(cleared) == 1 and cleared[0][1] == ([5],)

    books = [(s, p) for s, p in cur.executed
             if "insert into register_refreshes" in s]
    assert len(books) == 1

    audits = [(s, p) for s, p in cur.executed if "insert into mcp_audit" in s]
    assert len(audits) == 1 and "register.refresh" in str(audits[0][1])


def test_refresh_never_deletes_register_rows():
    import inspect

    from discover import register_refresh
    assert "delete from" not in inspect.getsource(register_refresh).lower()


def test_staleness_check_drives_the_weekly_self_schedule():
    fresh = ScriptedCursor([
        ("from register_refreshes", [[{"days_since": 2}]])])
    assert refresh_is_due(fresh, days=7) is False
    stale = ScriptedCursor([
        ("from register_refreshes", [[{"days_since": 9}]])])
    assert refresh_is_due(stale, days=7) is True
    never = ScriptedCursor([
        ("from register_refreshes", [[{"days_since": None}]])])
    assert refresh_is_due(never, days=7) is True


def test_daily_loop_stage_order_matches_the_phase_contract():
    import pathlib
    src = (pathlib.Path(__file__).resolve().parents[1] / "scripts"
           / "run.py").read_text()
    # classify sits between them: the refresh's newcomers get their industry
    # code the same night, before discovery leans on it. jd_drip (U5) sits
    # right after merge so tonight's freshly merged ad rows can gain their
    # full JD, then salary/deadlines/stage_reading enrich them the same run
    # — a DELIBERATE stage-order change (Phase 8.5 task 5).
    order = ["register", "classify", "discover", "fetch", "read", "synonyms",
             "merge", "jd_drip", "promote", "salary", "deadlines", "eval",
             "stage_reading", "file"]
    positions = [src.index(f'("{name}"') for name in order]
    assert positions == sorted(positions), "stage order drifted from the contract"
