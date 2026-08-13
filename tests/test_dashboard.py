"""Tests for src/dashboard/ — the read-only Today page (tabbed + paginated).

The big pin: complexity-hiding. The dashboard package may read ONLY the
three curated views (v_today / v_scorecard / v_health) — never a raw table;
the page renders what the views decided and adds no logic of its own.
The page is one lane at a time: a tab bar (Ready / Needs / Reading tray /
Company watch) whose counts come from the scorecard, and a pager (20/page)
whose links carry the query prefix. Local + token-protected: 127.0.0.1 bind
pinned, constant-time token check, DB failure renders a calm one-liner.
"""
from __future__ import annotations

import pathlib

from dashboard.page import render_page
from dashboard.queries import fetch_health, fetch_scorecard, fetch_today
from dashboard.server import BIND_HOST, check_token, respond

from tests.conftest import ScriptedCursor


def _today_row(**kw):
    base = {"role_id": 1, "company_name": "Acme AI Ltd",
            "role_title": "Solutions Engineer", "location": "London",
            "salary_text": "£70k–£90k", "salary_wall": "clears",
            "wall_basis": "going_rate:2134", "sponsor_signal": "role-confirmed",
            "fit_rank": "High", "role_url": "https://boards.example/1",
            "deadline": "2026-08-10", "deadline_source": "survival",
            "age_days": 3, "source": "greenhouse", "read_quality": "ai",
            "in_reading_tray": False, "has_jd": True, "has_reading": True,
            "bucket": "ready", "needs_what": None}
    base.update(kw)
    return base


SCORECARD = {
    "applications_total": 4, "applications_today": 1,
    "queue_rows": 12, "ready_rows": 7, "needs_rows": 5,
    "read_ai": 3, "read_keywords": 6, "read_unlabelled": 2,
    "unread_with_jd": 1, "staged_now": 9, "claimed_now": 2,
    "reviews_open": 2, "companies_tracked": 40, "companies_with_boards": 21,
    "ads_merged": 5800, "ads_awaiting_merge": 0,
    "last_run_at": "2026-08-02 06:10", "last_run_status": "ok",
    "register_rows": 126342, "register_age_days": 30,
}

HEALTH = [{"company_id": 5, "company_name": "Acme AI Ltd", "has_board": True,
           "ats_type": "greenhouse", "feed_status": "error",
           "last_fetched_at": "2026-08-01 06:00", "open_roles": 4,
           "applied_roles": 1, "last_listing_change": "2026-08-01 06:00"}]


# --- lanes and the tab bar ---------------------------------------------------

def test_tab_bar_names_every_lane_with_its_count():
    html = render_page([], SCORECARD, [], generated_at="now")
    for label in ("Ready to apply (7)", "Needs something (5)",
                  "Reading tray (9)", "Company watch (40)"):
        assert label in html, label


def test_active_tab_is_marked_and_links_carry_the_prefix():
    html = render_page([], SCORECARD, [], generated_at="now",
                       tab="needs", qs="/?token=t&")
    assert "aria-current='page'" in html
    assert "&amp;tab=needs" in html          # prefix escaped into every link
    assert "&amp;tab=companies" in html


def test_ready_lane_rows_carry_their_receipts_as_chips():
    html = render_page([_today_row()], SCORECARD, [], generated_at="now",
                       tab="ready")
    assert "Solutions Engineer" in html and "class='chip" in html
    for receipt in ("role-confirmed", "clears", "going_rate:2134", "survival",
                    "read ai"):
        assert receipt in html, receipt


def test_lane_shows_only_its_own_rows():
    rows = [_today_row(),
            _today_row(role_id=2, role_title="Backstage Role", bucket="needs",
                       needs_what="salary below the visa wall")]
    ready_html = render_page(rows, SCORECARD, [], generated_at="now",
                             tab="ready")
    assert "Solutions Engineer" in ready_html
    assert "Backstage Role" not in ready_html
    needs_html = render_page(rows, SCORECARD, [], generated_at="now",
                             tab="needs")
    assert "Backstage Role" in needs_html
    assert "salary below the visa wall" in needs_html


def test_tray_lane_filters_to_staged_rows():
    rows = [_today_row(role_id=1, in_reading_tray=True,
                       role_title="Staged Role"),
            _today_row(role_id=2, role_title="Unstaged Role")]
    html = render_page(rows, SCORECARD, [], generated_at="now", tab="tray")
    assert "Staged Role" in html and "Unstaged Role" not in html


def test_read_receipt_tells_the_truth_for_pre_tracking_reads():
    # A row read before 0039 has a reading but no quality label: the receipt
    # must say 'unlabelled', never 'not yet' (it WAS read).
    read_html = render_page([_today_row(read_quality=None, has_reading=True)],
                            SCORECARD, [], generated_at="now", tab="ready")
    assert "read unlabelled" in read_html
    unread_html = render_page(
        [_today_row(role_id=3, read_quality=None, has_reading=False,
                    bucket="needs", needs_what="waiting for tonight's read")],
        SCORECARD, [], generated_at="now", tab="needs")
    assert "read not yet" in unread_html


# --- pagination --------------------------------------------------------------

def test_pager_shows_position_and_neighbour_links():
    busy = {**SCORECARD, "ready_rows": 45}
    html = render_page([], busy, [], generated_at="now",
                       tab="ready", page=2, qs="/?token=t&")
    assert "page 2 of 3" in html
    assert "rel='prev'" in html and "page=1" in html
    assert "rel='next'" in html and "page=3" in html


def test_pager_hides_dead_ends_and_single_pages():
    busy = {**SCORECARD, "ready_rows": 45}
    first = render_page([], busy, [], generated_at="now", tab="ready", page=1)
    assert "rel='prev'" not in first
    last = render_page([], busy, [], generated_at="now", tab="ready", page=3)
    assert "rel='next'" not in last
    single = render_page([], SCORECARD, [], generated_at="now", tab="ready")
    assert "page 1 of 1" not in single and "rel='next'" not in single


# --- the rest of the page ----------------------------------------------------

def test_timestamps_render_short_not_raw():
    from datetime import datetime, timezone
    stamp = datetime(2026, 7, 10, 21, 48, 52, 856615, tzinfo=timezone.utc)
    html = render_page([], {**SCORECARD, "last_run_at": stamp},
                       [{**HEALTH[0], "last_fetched_at": stamp}],
                       generated_at="now", tab="companies")
    assert "2026-07-10 21:48" in html
    assert "856615" not in html


def test_honesty_tiles_ride_every_tab_and_companies_tab_shows_health():
    for tab in ("ready", "needs", "tray", "companies"):
        html = render_page([], SCORECARD, HEALTH, generated_at="now", tab=tab)
        for fact in ("Applications", "Read quality", "Register", "126,342"):
            assert fact in html, (tab, fact)
    companies = render_page([], SCORECARD, HEALTH, generated_at="now",
                            tab="companies")
    assert "Acme AI Ltd" in companies and "error" in companies


def test_empty_lanes_render_honest_empty_states_not_blanks():
    empty_scorecard = {k: 0 for k in SCORECARD} | {
        "last_run_at": None, "last_run_status": None, "register_age_days": None}
    cases = {"ready": "Nothing ready yet",
             "needs": "Nothing waiting",
             "tray": "Nothing staged",
             "companies": "No companies tracked yet"}
    for tab, text in cases.items():
        html = render_page([], empty_scorecard, [], generated_at="now", tab=tab)
        assert text in html, tab


def test_unknown_tab_falls_back_to_ready():
    html = render_page([_today_row()], SCORECARD, [], generated_at="now",
                       tab="nonsense")
    assert "Solutions Engineer" in html


def test_every_dynamic_value_is_escaped():
    html = render_page(
        [_today_row(role_title="<script>alert(1)</script>",
                    company_name="Bad & Co")],
        SCORECARD, HEALTH, generated_at="now")
    assert "<script>alert(1)" not in html
    assert "&lt;script&gt;" in html
    assert "Bad &amp; Co" in html


def test_page_is_self_contained_no_scripts_no_external_assets():
    html = render_page([_today_row()], SCORECARD, HEALTH, generated_at="now")
    assert "<script" not in html
    assert "stylesheet" not in html          # all CSS inline
    assert "http-equiv" in html and "refresh" in html   # calm auto-refresh, no JS


# --- the complexity-hiding pin ----------------------------------------------

RAW_TABLES = ("role_listings", "target_companies", "aggregator_ads",
              "sponsor_census", "census_jobs", "listing_events",
              "licensed_sponsors", "review_items", "pipeline_runs",
              "role_skills", "my_skills", "my_constraints", "promotion_rules",
              # Added with the mirror card (Phase 9.5 task 1). The card reads
              # v_owner_mirror; the moment this list did not name the tables
              # under that view, the rule would have been enforced for the
              # tables someone happened to think of in 2026 and no others.
              "cv_blocks", "profiles")


def test_pin_dashboard_reads_only_the_curated_views():
    # Phase 8.5 / U6 extended the allowed set with v_sponsor_browse — the
    # Sponsors tab reads THAT view, never sponsor_census or the sic table.
    # Phase 9.5 task 1 adds v_owner_mirror for the mirror card.
    pkg = pathlib.Path(__file__).resolve().parents[1] / "src" / "dashboard"
    source = " ".join(p.read_text() for p in pkg.glob("*.py")).lower()
    for table in RAW_TABLES:
        assert table not in source, f"dashboard touches raw table {table}"
    for view in ("v_today", "v_scorecard", "v_health", "v_sponsor_browse",
                 "v_owner_mirror"):
        assert view in source


# --- the mirror card (Phase 9.5 task 1) -------------------------------------

MIRROR_ROW = {"owner_id": "o-1", "name": "A Person", "facts_confirmed": 38,
              "facts_drafts": 2, "facts_retired": 1, "fact_kinds": 4,
              "skills_live": 21, "skills_evidenced": 4,
              "skills_unevidenced": 17, "evidenced_outside_paid_work": 4}


def test_fetch_owner_mirror_reads_the_view_and_leads_with_the_unprovable():
    from dashboard.queries import fetch_owner_mirror

    cur = ScriptedCursor([("from v_owner_mirror", [[MIRROR_ROW]])])
    assert fetch_owner_mirror(cur)[0]["skills_unevidenced"] == 17
    sql, _ = cur.executed[0]
    assert "from v_owner_mirror" in sql
    assert "order by skills_unevidenced desc" in sql, (
        "the card exists to surface unprovable claims — ordering by anything "
        "else buries the owner who most needs to see it")


def test_the_mirror_card_shows_what_a_cv_cannot_claim_with_its_basis():
    html = render_page([], SCORECARD, [], [], mirror=[MIRROR_ROW])

    assert "What the system understands about you" in html
    # The three numbers, each with its receipt beside it.
    assert "38" in html and "4 of 21" in html
    assert "17" in html and "no confirmed fact behind them" in html
    assert "19%" in html, "the evidenced share must ride with the count"
    assert "4 evidenced outside paid work" in html
    assert "2 draft(s) awaiting your word" in html
    # And it must say out loud that it is not a stored opinion.
    assert "stored opinion" in html


def test_the_mirror_card_says_so_when_every_skill_is_evidenced():
    row = {**MIRROR_ROW, "skills_unevidenced": 0, "skills_evidenced": 21}
    html = render_page([], SCORECARD, [], [], mirror=[row])
    assert "every recorded skill is evidenced" in html


def test_an_owner_with_nothing_recorded_renders_a_dash_not_a_fake_zero():
    # 0% would read as a verdict on someone the machine has simply not met.
    empty = {**MIRROR_ROW, "skills_live": 0, "skills_evidenced": 0,
             "skills_unevidenced": 0, "evidenced_outside_paid_work": 0,
             "facts_confirmed": 0}
    html = render_page([], SCORECARD, [], [], mirror=[empty])
    # Scoped to the card: the stylesheet is full of `100%`, so a bare
    # substring check over the whole page would pass for the wrong reason —
    # and this file's own rule is that a check must fail for its own reason.
    card = html.split("understands about you")[1].split("</section>")[0]
    assert "0%" not in card
    assert "no skills recorded yet" in card


def test_the_page_still_renders_when_the_mirror_has_no_rows():
    # The card is additive: an older deployment, or a database where the view
    # has not been applied yet, must not take the whole dashboard down.
    html = render_page([], SCORECARD, [], [], mirror=[])
    assert "Honesty panel" in html
    assert "What the system understands about you" not in html


def test_queries_select_from_the_views_with_lane_filters_and_paging():
    cur = ScriptedCursor([
        ("from v_today", [[_today_row()]]),
        ("from v_scorecard", [[SCORECARD]]),
        ("from v_health", [[*HEALTH]]),
    ])
    assert fetch_today(cur, bucket="ready", limit=20, offset=40)[0]["role_id"] == 1
    sql, params = cur.executed[0]
    assert "bucket = %s" in sql and params == ("ready", 20, 40)

    fetch_today(cur, tray_only=True)
    sql, _ = cur.executed[1]
    assert "in_reading_tray" in sql

    assert fetch_scorecard(cur)["queue_rows"] == 12
    fetch_health(cur, limit=20, offset=20)
    sql, params = cur.executed[-1]
    assert "from v_health" in sql and params[-2:] == (20, 20)


# --- token + serving ---------------------------------------------------------

def test_token_check_is_strict_and_none_safe():
    assert check_token("s3cret", "s3cret") is True
    assert check_token("wrong", "s3cret") is False
    assert check_token(None, "s3cret") is False
    assert check_token("", "s3cret") is False
    assert check_token("anything", "") is False   # no token configured = no access


def test_respond_serves_the_page_only_with_the_right_token():
    ok, body = respond("s3cret", "s3cret",
                       loader=lambda tab, page, industry, town:
                       ([], SCORECARD, [], [], []))
    assert ok == 200 and "Today" in body
    denied, body = respond("nope", "s3cret",
                           loader=lambda tab, page, industry, town:
                           ([], SCORECARD, [], [], []))
    assert denied == 403 and "token" in body.lower()


def test_respond_normalises_tab_and_page_before_loading():
    seen = {}

    def loader(tab, page, industry, town):
        seen["tab"], seen["page"] = tab, page
        return [], SCORECARD, [], [], []

    respond("s3cret", "s3cret", tab="tray", page=3, loader=loader)
    assert seen == {"tab": "tray", "page": 3}
    respond("s3cret", "s3cret", tab="bogus", page="0", loader=loader)
    assert seen == {"tab": "ready", "page": 1}


def test_respond_threads_the_sponsor_filters_to_the_loader():
    seen = {}

    def loader(tab, page, industry, town):
        seen.update(tab=tab, industry=industry, town=town)
        return [], SCORECARD, [], [], []

    respond("s3cret", "s3cret", tab="sponsors", industry="care homes",
            town="Leeds", loader=loader)
    assert seen == {"tab": "sponsors", "industry": "care homes",
                    "town": "Leeds"}


def test_db_failure_renders_a_calm_line_never_a_traceback():
    def boom(tab, page, industry, town):
        raise RuntimeError("connection refused at 10.0.0.1 password=hunter2")
    status, body = respond("s3cret", "s3cret", loader=boom)
    assert status == 500
    assert "unreachable" in body.lower()
    assert "hunter2" not in body and "Traceback" not in body


def test_pin_the_dashboard_binds_local_only():
    assert BIND_HOST == "127.0.0.1"


# --- Phase 8.5 / U6: the Sponsors browse tab + fit + new-today ---------------

SPONSOR_ROWS = [
    {"org_name_norm": "sunrise care ltd", "organisation_name": "Sunrise Care Ltd",
     "town_city": "Leeds", "registry_status": "active",
     "industry_descriptions": ["Residential care activities for the elderly"],
     "probe_outcome": "board_found", "careers_url": "https://sunrise/careers",
     "local_jobs_seen": 3, "total_jobs_seen": 5, "total_rows": 61},
]


def test_fetch_sponsors_filters_and_pages_over_the_browse_view():
    from dashboard.queries import fetch_sponsors
    cur = ScriptedCursor([("from v_sponsor_browse", [[*SPONSOR_ROWS]])])
    rows = fetch_sponsors(cur, industry="care", town="Leeds",
                          limit=20, offset=20)
    assert rows[0]["organisation_name"] == "Sunrise Care Ltd"
    sql, params = cur.executed[0]
    low = sql.lower()
    assert "from v_sponsor_browse" in low
    assert "count(*) over()" in low            # filtered pager total, one query
    assert "industry_descriptions" in low and "ilike" in low
    assert "town_city ilike" in low
    assert "%care%" in params and "%Leeds%" in params
    assert params[-2:] == (20, 20)
    order = low.rsplit("order by", 1)[1]
    assert "board_found" in order and "local_jobs_seen" in order


def test_fetch_sponsors_without_filters_is_a_plain_browse():
    from dashboard.queries import fetch_sponsors
    cur = ScriptedCursor([("from v_sponsor_browse", [[*SPONSOR_ROWS]])])
    fetch_sponsors(cur)
    sql, params = cur.executed[0]
    assert "ilike" not in sql.lower()
    assert params == (20, 0)


def test_sponsors_tab_renders_table_filters_and_count():
    s = dict(SCORECARD, sponsors_total=98638)
    html = render_page([], s, [], SPONSOR_ROWS, generated_at="now",
                       tab="sponsors", industry="care", town="Leeds")
    assert "Sponsors (98,638)" in html                  # tab bar count
    assert "Sunrise Care Ltd" in html
    assert "Residential care activities for the elderly" in html
    assert "board_found" in html or "board found" in html
    # the zero-JS filter form: GET inputs that echo the current filters
    assert "<form" in html and "name='industry'" in html
    assert "value='care'" in html and "value='Leeds'" in html
    assert "name='tab'" in html                         # stays on the tab
    # filtered pager total comes from the window column, not the scorecard
    assert "of 4" in html                               # ceil(61/20) pages


def test_queue_rows_render_fit_and_new_today_chips():
    row = _today_row(skill_have=3, skill_asked=7, is_new_today=True)
    s = dict(SCORECARD, new_today=4, sponsors_total=0)
    html = render_page([row], s, [], [], generated_at="now", tab="ready")
    assert "skills 3/7" in html
    assert "new today" in html
    assert "4 new today" in html                        # the header chip


def test_rows_without_readings_hide_the_skills_chip():
    row = _today_row(skill_have=0, skill_asked=0, is_new_today=False)
    html = render_page([row], dict(SCORECARD, new_today=0, sponsors_total=0),
                       [], [], generated_at="now", tab="ready")
    assert "skills 0/0" not in html
