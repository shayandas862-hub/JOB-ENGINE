"""Tests for deadline extraction (stated) and the advisory apply-by estimate."""
from __future__ import annotations

from datetime import date

from history.deadline import choose_deadline, estimate_apply_by, extract_stated_deadline


# ---- stated deadlines: parsed only when the JD really states one ----

def test_extracts_common_uk_date_formats():
    assert extract_stated_deadline(
        "Closing date: 31 July 2026.") == date(2026, 7, 31)
    assert extract_stated_deadline(
        "Apply by 07/08/2026 at the latest.") == date(2026, 8, 7)   # UK day-first
    assert extract_stated_deadline(
        "Application deadline: 2026-08-15.") == date(2026, 8, 15)
    assert extract_stated_deadline(
        "Applications close on 1st August 2026.") == date(2026, 8, 1)


def test_only_deadline_phrases_trigger_extraction():
    # A date without a deadline phrase is NOT a deadline (start dates, events).
    assert extract_stated_deadline("The role starts on 1 September 2026.") is None
    assert extract_stated_deadline("Founded in 2019, we ship fast.") is None
    assert extract_stated_deadline("") is None
    assert extract_stated_deadline(None) is None


# ---- advisory estimate: first_seen + the profile's window, always labelled ----

def test_estimate_is_first_seen_plus_window():
    assert estimate_apply_by(date(2026, 7, 10), 21) == date(2026, 7, 31)


def test_choose_prefers_stated_over_estimate():
    d, source = choose_deadline("Closing date: 31 July 2026.",
                                first_seen=date(2026, 7, 1), window_days=21)
    assert (d, source) == (date(2026, 7, 31), "stated")


def test_choose_falls_back_to_labelled_estimate():
    d, source = choose_deadline("No deadline mentioned here.",
                                first_seen=date(2026, 7, 10), window_days=14)
    assert (d, source) == (date(2026, 7, 24), "estimated")
