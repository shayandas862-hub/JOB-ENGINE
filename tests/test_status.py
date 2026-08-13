"""The public status page (Phase 8 task 4) — no auth, person-free.

This is the ONLY surface in the system anyone can read without a token, so the
tests here are mostly about what must NOT appear. Complexity-hiding matches the
dashboard: the package reads only v_status / v_status_stages (pinned), and the
views are the privacy boundary. Cloud Run shaped: 0.0.0.0 + $PORT, which is the
deliberate opposite of the dashboard's pinned 127.0.0.1 — the difference is the
whole point, so both are pinned.
"""
from __future__ import annotations

import pathlib

from status.page import render_status
from status.queries import fetch_stages, fetch_status
from status.server import BIND_HOST, respond

from tests.conftest import ScriptedCursor

STATUS_ROW = {
    "last_run_at": "2026-08-09 20:15:43+00", "last_run_status": "ok",
    "last_run_stages": 14, "last_run_stages_ok": 14, "last_run_seconds": 782,
    "runs_completed": 6, "listings_tracked": 12495, "listings_open": 12041,
    "companies_tracked": 885, "companies_with_boards": 82,
    "census_organisations": 128222, "census_boards": 314,
    "register_rows": 144041, "register_age_days": 0, "ads_collected": 104761,
}
STAGES = [
    {"stage_order": 1, "stage": "register", "ok": True, "duration_s": 1.0},
    {"stage_order": 2, "stage": "discover", "ok": True, "duration_s": 694.3},
    {"stage_order": 3, "stage": "nudge", "ok": True, "duration_s": 0.7},
]


def _render(row=None, stages=None):
    return render_status(row if row is not None else STATUS_ROW,
                         stages if stages is not None else STAGES,
                         generated_at="2026-08-09 21:40 UTC")


# ---------------------------------------------------------- the privacy wall

# Column names that would mean the privacy boundary has been crossed. The
# engine is full of them; this page must know none of them.
FORBIDDEN = (
    "applications_total", "applications_today", "applied_date",
    "application_status", "owner_id", "notification_channel",
    "salary_text", "salary_wall", "wall_basis", "going_rate",
    "ats_token", "DASHBOARD_TOKEN", "MCP_TOKEN", "jd_full",
    "role_title", "company_name", "role_url",
)


def test_the_status_package_never_names_a_personal_column():
    # A public page cannot leak what it cannot name. Checked against SOURCE,
    # so it fails when someone writes the query, not when a user is harmed.
    pkg = pathlib.Path(__file__).resolve().parents[1] / "src" / "status"
    offenders = []
    for path in sorted(pkg.rglob("*.py")):
        text = path.read_text()
        for name in FORBIDDEN:
            if name in text:
                offenders.append(f"{path.name}: {name}")
    assert offenders == [], f"personal columns named in the public page: {offenders}"


def test_a_smuggled_personal_field_is_never_rendered():
    # Defence in depth: even if a future view widened by accident, the page
    # renders only the keys it knows, never "whatever the row happens to hold".
    row = dict(STATUS_ROW, applications_total=7, owner_id="p-1",
               salary_text="£95,000", notification_channel="ntfy:secret-topic")
    html = _render(row)
    for leak in ("£95,000", "secret-topic", "p-1"):
        assert leak not in html, f"leaked {leak!r}"


def test_stage_rows_render_health_but_never_summary_prose():
    # Stage summaries carry company names and "nudged 64 listing(s)" — the
    # owner's activity, not machine health. The view drops them; if one ever
    # arrives anyway, the page must still not print it.
    stages = [dict(STAGES[0], summary="nudged 64 listing(s) — Anthropic, Palantir")]
    html = _render(stages=stages)
    assert "register" in html
    assert "nudged" not in html and "Anthropic" not in html


# --------------------------------------------------------------- the content

def test_page_answers_is_the_machine_alive():
    html = _render()
    assert "ok" in html.lower()
    assert "14" in html                      # 14 of 14 stages
    assert "2026-08-09" in html              # when it last ran


def test_page_shows_every_stage_with_its_outcome():
    html = _render()
    for stage in ("register", "discover", "nudge"):
        assert stage in html


def test_a_failed_stage_is_shown_as_failed_not_hidden():
    # A status page that only ever looks green is worthless.
    stages = [dict(STAGES[0], ok=False)]
    html = _render(dict(STATUS_ROW, last_run_status="failed",
                        last_run_stages_ok=13), stages)
    assert "failed" in html.lower()


def test_every_number_carries_its_label_no_naked_counts():
    # House rule 5: no naked numbers. Each headline figure says what it counts.
    html = _render()
    for number, label in (("144,041", "sponsor"), ("128,222", "organisation"),
                          ("104,761", "advert"), ("12,495", "listing")):
        assert number in html, f"{number} missing"
        assert label in html.lower(), f"{label} missing for {number}"


def test_big_numbers_are_thousands_separated():
    assert "144,041" in _render() and "144041" not in _render()


def test_an_empty_database_renders_an_honest_page_not_a_crash():
    html = render_status({}, [], generated_at="now")
    assert "no run" in html.lower() or "never" in html.lower()


# ------------------------------------------------------------- the mechanics

def test_page_is_self_contained_no_scripts_no_external_assets():
    html = _render()
    assert "<script" not in html.lower()
    for marker in ("http://", "//cdn", "src=", "@import"):
        assert marker not in html.lower().replace("https://goal-a", ""), marker


def test_every_dynamic_value_is_escaped():
    html = _render(dict(STATUS_ROW, last_run_status="<img src=x onerror=1>"))
    assert "<img" not in html
    assert "&lt;img" in html


def test_pin_status_reads_only_the_curated_views():
    # Complexity-hiding, same contract as the dashboard: the views decide, the
    # page renders. A raw table here would bypass the privacy boundary.
    src = (pathlib.Path(__file__).resolve().parents[1]
           / "src" / "status" / "queries.py").read_text()
    assert "v_status" in src
    for table in ("role_listings", "target_companies", "licensed_sponsors",
                  "sponsor_census", "aggregator_ads", "pipeline_runs",
                  "profiles"):
        assert table not in src, f"reads the raw table {table}"


def test_queries_select_from_the_two_views():
    cur = ScriptedCursor([("from v_status_stages", [[*STAGES]]),
                          ("from v_status", [[STATUS_ROW]])])
    assert fetch_status(cur)["register_rows"] == 144041
    assert len(fetch_stages(cur)) == 3
    assert "order by stage_order" in cur.executed[-1][0]


def test_status_serves_the_page_with_no_token_at_all():
    # Public by design: this is the one surface with no auth. If it ever starts
    # refusing anonymous readers, the point of the page has been lost.
    status, html = respond(loader=lambda: (STATUS_ROW, STAGES))
    assert status == 200
    assert "144,041" in html


def test_db_failure_renders_a_calm_line_never_a_traceback():
    def boom():
        raise RuntimeError("connection refused to db.example.supabase.co")
    status, html = respond(loader=boom)
    assert status == 503
    assert "Traceback" not in html and "supabase" not in html.lower()
    assert "unavailable" in html.lower() or "unreachable" in html.lower()


def test_pin_the_status_page_binds_all_interfaces_for_cloud_run():
    # The deliberate opposite of the dashboard's 127.0.0.1: inside a container
    # the process must accept traffic from the platform. There is no token to
    # protect here — the view is what makes this safe to expose.
    assert BIND_HOST == "0.0.0.0"
    src = (pathlib.Path(__file__).resolve().parents[1]
           / "src" / "status" / "server.py").read_text()
    assert "PORT" in src                      # Cloud Run injects it
