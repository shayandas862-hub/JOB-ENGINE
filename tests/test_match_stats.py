"""Tests for src/match/stats.py — percentiles + smoothed confidence.

Pins: linear-interpolation percentiles (empty data returns None, never 0);
Laplace-smoothed rates that ALWAYS carry their sample size — a 2/2 and a
900/1000 must be distinguishable from their receipts alone.
"""
from __future__ import annotations

import pytest

from match.stats import percentile, smoothed_rate, summary


# --- percentile --------------------------------------------------------------

def test_single_value_is_every_percentile():
    assert percentile([42_000], 25) == 42_000
    assert percentile([42_000], 50) == 42_000
    assert percentile([42_000], 99) == 42_000


def test_median_interpolates_between_middle_pair():
    assert percentile([1, 3], 50) == pytest.approx(2.0)


def test_quartiles_use_linear_interpolation():
    values = [1, 2, 3, 4]
    assert percentile(values, 25) == pytest.approx(1.75)
    assert percentile(values, 50) == pytest.approx(2.5)
    assert percentile(values, 75) == pytest.approx(3.25)


def test_input_order_does_not_matter():
    assert percentile([4, 1, 3, 2], 50) == pytest.approx(2.5)


def test_p0_and_p100_are_min_and_max():
    values = [10, 20, 30]
    assert percentile(values, 0) == 10
    assert percentile(values, 100) == 30


def test_empty_data_has_no_percentile():
    assert percentile([], 50) is None


def test_percentile_out_of_range_rejected():
    with pytest.raises(ValueError):
        percentile([1], -1)
    with pytest.raises(ValueError):
        percentile([1], 101)


# --- summary -----------------------------------------------------------------

def test_summary_carries_sample_size_and_quartiles():
    s = summary([30_000, 40_000, 50_000, 60_000])
    assert s["n"] == 4
    assert s["p25"] == pytest.approx(37_500)
    assert s["p50"] == pytest.approx(45_000)
    assert s["p75"] == pytest.approx(52_500)


def test_empty_summary_is_honest_about_having_nothing():
    assert summary([]) == {"n": 0, "p25": None, "p50": None, "p75": None}


# --- smoothed_rate -----------------------------------------------------------

def test_zero_evidence_sits_at_the_prior_with_n_zero():
    r = smoothed_rate(0, 0)
    assert r["rate"] == pytest.approx(0.5)   # (0+1)/(0+2)
    assert r["n"] == 0
    assert r["raw_rate"] is None


def test_small_samples_shrink_toward_the_prior():
    r = smoothed_rate(2, 2)                  # raw 1.0
    assert r["raw_rate"] == pytest.approx(1.0)
    assert r["rate"] == pytest.approx(0.75)  # (2+1)/(2+2) — confidence tempered
    assert r["n"] == 2


def test_large_samples_converge_to_the_raw_rate():
    r = smoothed_rate(900, 1000)
    assert r["rate"] == pytest.approx(0.9, abs=0.001)
    assert r["n"] == 1000


def test_rate_is_recomputable_from_its_receipts():
    r = smoothed_rate(3, 4)
    assert r["rate"] == pytest.approx(
        (r["successes"] + r["prior_successes"]) / (r["n"] + r["prior_trials"]))


def test_custom_prior_is_respected_and_reported():
    r = smoothed_rate(0, 0, prior_successes=1, prior_trials=10)
    assert r["rate"] == pytest.approx(0.1)
    assert r["prior_successes"] == 1 and r["prior_trials"] == 10


def test_impossible_counts_rejected():
    with pytest.raises(ValueError):
        smoothed_rate(5, 4)                  # more successes than trials
    with pytest.raises(ValueError):
        smoothed_rate(-1, 4)
    with pytest.raises(ValueError):
        smoothed_rate(0, 0, prior_successes=0, prior_trials=0)   # 0/0
