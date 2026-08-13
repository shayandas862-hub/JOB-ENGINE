"""The yield estimate's arithmetic — checked against values computed elsewhere.

`plans/0011` §2a asks for a Poisson rate with a Jeffreys interval, so that a
watch which caught nothing reads "0, but could be up to X" rather than a fake
hard zero. There is no scipy in this project (and adding numpy to the image
for one quantile would be a poor trade), so the incomplete gamma and its
inverse are implemented here — which means they have to be checked against
numbers this file did not produce.

The anchors below are standard published values:

* `gammaincinv(1, p) == -ln(1-p)` exactly, because P(1,x) = 1 - e^(-x). This
  is the one closed form available and it pins the inverse without reference
  to any table.
* chi-square quantiles from any statistical table, via
  `chi2.ppf(p, v) == 2 * gammaincinv(v/2, p)`:
      chi2.ppf(0.975, 1)  = 5.02389    chi2.ppf(0.025, 11) = 3.81575
      chi2.ppf(0.975, 11) = 21.92005   chi2.ppf(0.500, 2)  = 1.38629
"""
from __future__ import annotations

import math

import pytest

from watch.poisson import jeffreys_rate_interval, regularised_gamma_p, gammaincinv


# --- the special function, before anything is built on it ------------------

@pytest.mark.parametrize("p", [0.001, 0.025, 0.1, 0.5, 0.9, 0.975, 0.999])
def test_the_inverse_matches_the_one_closed_form_that_exists(p):
    # a = 1 is the exponential distribution: P(1, x) = 1 - e^(-x).
    assert gammaincinv(1.0, p) == pytest.approx(-math.log(1 - p), rel=1e-9)


@pytest.mark.parametrize("a,x", [(0.5, 0.3), (1.0, 2.0), (5.5, 4.0),
                                 (12.0, 12.0), (0.5, 8.0)])
def test_the_inverse_really_inverts_the_forward_function(a, x):
    # The property that matters and needs no table at all.
    assert gammaincinv(a, regularised_gamma_p(a, x)) == pytest.approx(x, rel=1e-7)


@pytest.mark.parametrize("p,df,expected", [
    (0.975, 1, 5.02389), (0.025, 11, 3.81575),
    (0.975, 11, 21.92005), (0.500, 2, 1.38629),
])
def test_it_reproduces_published_chi_square_quantiles(p, df, expected):
    assert 2 * gammaincinv(df / 2, p) == pytest.approx(expected, rel=1e-5)


def test_the_forward_function_is_a_probability_and_moves_the_right_way():
    assert regularised_gamma_p(3.0, 0.0) == 0.0
    assert regularised_gamma_p(3.0, 1e6) == pytest.approx(1.0, abs=1e-12)
    rising = [regularised_gamma_p(3.0, x) for x in (0.5, 1, 2, 4, 8, 16)]
    assert rising == sorted(rising)


# --- the estimate the owner actually sees ----------------------------------

def test_catching_nothing_reports_zero_with_an_honest_ceiling():
    # § 2a's whole reason for existing: 0 catches must not read as "never".
    low, rate, high = jeffreys_rate_interval(0, 1.0)
    assert (low, rate) == (0.0, 0.0)
    # Gamma(0.5, 1) upper 97.5% = chi2.ppf(0.975, 1) / 2 = 2.51194
    assert high == pytest.approx(2.51194, rel=1e-4)
    assert high > 0, "a zero-catch watch must still admit it could catch some"


def test_a_real_sample_brackets_its_own_point_estimate():
    # k=5 over t=10 nights: Gamma(5.5, 10), interval
    # [chi2.ppf(.025,11)/20, chi2.ppf(.975,11)/20] = [0.19079, 1.09600]
    low, rate, high = jeffreys_rate_interval(5, 10.0)
    assert rate == pytest.approx(0.5)
    assert low == pytest.approx(0.19079, rel=1e-4)
    assert high == pytest.approx(1.09600, rel=1e-4)
    assert low < rate < high


def test_the_interval_tightens_as_evidence_accumulates():
    # The property that makes the interval worth showing at all: the same
    # rate seen for longer says the same thing more confidently.
    narrow = jeffreys_rate_interval(50, 100.0)
    wide = jeffreys_rate_interval(5, 10.0)
    assert (narrow[2] - narrow[0]) < (wide[2] - wide[0])
    assert narrow[1] == pytest.approx(wide[1]), "same rate, different evidence"


def test_exposure_must_be_real_time():
    # Dividing by zero nights would produce an infinite rate presented as a
    # measurement, which is worse than refusing.
    for bad in (0.0, -1.0):
        with pytest.raises(ValueError):
            jeffreys_rate_interval(3, bad)
    with pytest.raises(ValueError):
        jeffreys_rate_interval(-1, 10.0)


def test_a_weekly_rate_is_just_the_nightly_rate_scaled():
    # The surface quotes jobs/week; the estimator works in nights. Stated as
    # a test because a factor of 7 applied twice is the kind of error that
    # looks plausible on a dashboard forever.
    _, rate, _ = jeffreys_rate_interval(14, 60.0)
    assert rate * 7 == pytest.approx(14 / 60 * 7)
