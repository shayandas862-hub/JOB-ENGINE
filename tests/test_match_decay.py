"""Tests for src/match/decay.py — half-life freshness weight.

Pins the exact curve (0.5 ** (age/half_life)) so a freshness number on any
surface can be recomputed from age + half-life alone.
"""
from __future__ import annotations

import pytest

from match.decay import freshness


def test_brand_new_is_fully_fresh():
    assert freshness(0, 14) == pytest.approx(1.0)


def test_one_half_life_halves():
    assert freshness(14, 14) == pytest.approx(0.5)


def test_two_half_lives_quarter():
    assert freshness(28, 14) == pytest.approx(0.25)


def test_fractional_ages_interpolate_smoothly():
    assert freshness(7, 14) == pytest.approx(0.5 ** 0.5)


def test_freshness_is_monotonically_decreasing():
    values = [freshness(d, 14) for d in (0, 1, 5, 20, 100)]
    assert values == sorted(values, reverse=True)


def test_future_dates_clamp_to_fully_fresh():
    # Clock drift can make age negative; a job cannot be fresher than fresh.
    assert freshness(-3, 14) == pytest.approx(1.0)


def test_half_life_must_be_positive():
    with pytest.raises(ValueError):
        freshness(5, 0)
    with pytest.raises(ValueError):
        freshness(5, -14)
