"""Tests for src/history/survival.py — evidence-based deadlines.

Pins: durations come from first-appeared -> first-closed pairs per listing;
families group by SOC code first, then coarse title buckets; a family below
MIN_SAMPLE never drives a deadline (flat-window fallback, honestly labelled
'estimated'); a stated deadline in the JD always wins; and a survival
deadline ships its receipts (family, n, median) — the machine citing its
own history, never a naked date.
"""
from __future__ import annotations

from datetime import date

from history.survival import (MIN_SAMPLE, build_curves, choose_with_survival,
                              role_family)

from tests.conftest import ScriptedCursor


# --- role_family -------------------------------------------------------------

def test_soc_code_is_the_family_when_known():
    assert role_family("Anything At All", "2134") == "soc:2134"


def test_title_buckets_are_coarse_and_ordered():
    assert role_family("Senior Data Engineer", None) == "title:data"
    assert role_family("Machine Learning Engineer", None) == "title:ml"
    assert role_family("Software Engineer (Platform)", None) == "title:software"
    assert role_family("Product Manager", None) == "title:product"
    assert role_family("Head Chef", None) == "title:other"


# --- build_curves ------------------------------------------------------------

def _rows(days, soc="2134", title="Software Engineer"):
    return [{"soc_code": soc, "role_title": title, "days_open": d}
            for d in days]


def test_curves_group_by_family_and_carry_sample_size():
    cur = ScriptedCursor([
        ("from listing_events", [
            _rows([5, 7, 9, 11, 13]) + _rows([30], soc=None, title="Chef")]),
    ])
    curves = build_curves(cur)
    assert curves["soc:2134"]["n"] == 5
    assert curves["soc:2134"]["p50"] == 9
    assert curves["title:other"]["n"] == 1


def test_pin_durations_pair_first_appeared_with_first_closed():
    from history import survival
    sql = " ".join(survival.DURATIONS_SQL.split()).lower()
    assert "event_type = 'appeared'" in sql
    assert "event_type = 'closed'" in sql
    assert "group by" in sql


# --- choose_with_survival ----------------------------------------------------

RICH = {"soc:2134": {"n": 9, "p25": 6.0, "p50": 9.0, "p75": 14.0}}
THIN = {"soc:2134": {"n": 2, "p25": 6.0, "p50": 9.0, "p75": 14.0}}
FIRST_SEEN = date(2026, 8, 1)


def test_stated_deadline_always_wins():
    jd = "Interviews rolling. Closing date 15 August 2026."
    d, source, receipts = choose_with_survival(
        jd, FIRST_SEEN, "Software Engineer", "2134", RICH, window_days=21)
    assert (d, source) == (date(2026, 8, 15), "stated")


def test_rich_history_gives_a_survival_deadline_with_receipts():
    d, source, receipts = choose_with_survival(
        None, FIRST_SEEN, "Software Engineer", "2134", RICH, window_days=21)
    assert source == "survival"
    assert d == date(2026, 8, 10)            # first_seen + round(median 9)
    assert receipts["family"] == "soc:2134"
    assert receipts["n"] == 9
    assert receipts["p50"] == 9.0


def test_thin_history_falls_back_to_the_flat_window_honestly():
    d, source, receipts = choose_with_survival(
        None, FIRST_SEEN, "Software Engineer", "2134", THIN, window_days=21)
    assert source == "estimated"
    assert d == date(2026, 8, 22)            # first_seen + 21
    assert receipts["n"] == 2                # the thinness is on the receipt


def test_no_history_at_all_is_also_an_estimate():
    d, source, receipts = choose_with_survival(
        None, FIRST_SEEN, "Head Chef", None, {}, window_days=21)
    assert source == "estimated"
    assert receipts["n"] == 0


def test_min_sample_is_pinned():
    assert MIN_SAMPLE == 5


def test_the_deadline_source_constraint_admits_every_chooser_source():
    # The chooser returns stated|survival|estimated; migration 0042 widens the
    # 0024 check (which predates survival) to admit all three. The first cloud
    # run failed on exactly this drift — this pins mirror and code together.
    from pathlib import Path

    sql = (Path(__file__).resolve().parents[1] / "db" / "migrations"
           / "0042_deadline_source_admits_survival.sql").read_text()
    for source in ("stated", "estimated", "survival"):
        assert f"'{source}'" in sql
    assert "role_listings_deadline_source_check" in sql
