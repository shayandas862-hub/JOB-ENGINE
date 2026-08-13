"""Poisson rate estimation with a Jeffreys interval — the honest "0" .

`plans/0011` §2a: before a watch is saved it is replayed over stored history.
It caught k jobs across t nights, so the nightly rate is k/t — but a point
estimate alone lies in the one case that matters most. A watch that caught
nothing has k/t = 0, and "0 jobs per week" reads as *never*, when the truth
after four quiet nights is "nothing yet, and it could still be up to 0.6 a
night". The interval is what makes a quiet watch distinguishable from a dead
one.

Jeffreys rather than Wald: the Wald interval is [0, 0] at k=0, which is the
exact failure being avoided, and it can dip below zero for small k. With the
Jeffreys prior the posterior for the rate is Gamma(k + 1/2, t), and its
quantiles are the interval. At k=0 the lower bound is pinned to 0 by
convention (Brown, Cai & DasGupta) rather than reported as the 0.0005 the
posterior gives, because a positive lower bound on a rate nothing was ever
observed at is not a claim this project should make.

There is no scipy here and adding numpy to the image for one quantile would
be a poor trade, so the regularised incomplete gamma and its inverse are
implemented directly. Both are pinned in `tests/test_watch_poisson.py`
against published chi-square quantiles and against the one closed form that
exists (a = 1 is the exponential), because a special function nobody checked
is just a number generator.
"""
from __future__ import annotations

import math

#: Two-sided coverage of the reported interval.
CONFIDENCE = 0.95

_MAX_ITERATIONS = 300
_TOLERANCE = 1e-12


def regularised_gamma_p(a: float, x: float) -> float:
    """P(a, x) — the regularised lower incomplete gamma, in [0, 1].

    Series expansion below the transition point, continued fraction above it
    (Numerical Recipes' gser/gcf split at x = a + 1); each converges quickly
    exactly where the other stalls.
    """
    if a <= 0:
        raise ValueError(f"a must be positive; got {a}")
    if x < 0:
        raise ValueError(f"x must not be negative; got {x}")
    if x == 0:
        return 0.0
    if x < a + 1:
        # Series: P(a,x) = x^a e^-x / Γ(a+1) · Σ x^n / ((a+1)...(a+n))
        term = 1.0 / a
        total = term
        for n in range(1, _MAX_ITERATIONS):
            term *= x / (a + n)
            total += term
            if abs(term) < abs(total) * _TOLERANCE:
                break
        return min(1.0, total * math.exp(-x + a * math.log(x) - math.lgamma(a)))
    # Continued fraction for Q(a,x) = 1 - P(a,x), by the modified Lentz method.
    tiny = 1e-300
    b = x + 1.0 - a
    c = 1.0 / tiny
    d = 1.0 / b if b != 0 else 1.0 / tiny
    h = d
    for i in range(1, _MAX_ITERATIONS):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        if abs(d) < tiny:
            d = tiny
        c = b + an / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < _TOLERANCE:
            break
    q = math.exp(-x + a * math.log(x) - math.lgamma(a)) * h
    return max(0.0, min(1.0, 1.0 - q))


def gammaincinv(a: float, p: float) -> float:
    """x such that regularised_gamma_p(a, x) == p, for p in [0, 1).

    Bisection on a bracket grown by doubling. Deliberately not Newton: this
    is called a handful of times per watch, never in a loop over listings, so
    robustness is worth more than iterations — and a derivative-free method
    cannot diverge on the small-a shapes (a = 0.5 at k = 0) that matter most
    here.
    """
    if not 0.0 <= p < 1.0:
        raise ValueError(f"p must be in [0, 1); got {p}")
    if a <= 0:
        raise ValueError(f"a must be positive; got {a}")
    if p == 0.0:
        return 0.0
    low, high = 0.0, max(1.0, a)
    while regularised_gamma_p(a, high) < p:
        high *= 2.0
        if high > 1e12:                     # unreachable for any real input
            raise ValueError(f"cannot bracket the quantile for a={a}, p={p}")
    for _ in range(200):
        mid = (low + high) / 2.0
        if regularised_gamma_p(a, mid) < p:
            low = mid
        else:
            high = mid
        if high - low < _TOLERANCE * max(1.0, high):
            break
    return (low + high) / 2.0


def jeffreys_rate_interval(catches: int, nights: float,
                           confidence: float = CONFIDENCE
                           ) -> tuple[float, float, float]:
    """(low, rate, high) nightly rate for `catches` seen over `nights`.

    `rate` is the plain point estimate k/t — the number the owner is quoted —
    and the bounds are the Jeffreys posterior's quantiles. The point estimate
    is deliberately NOT the posterior mean: the mean would shift a watch that
    caught exactly 2 a night to 2.05 for reasons no owner can be told in one
    line, and the honesty this interval buys is in the bounds, not the middle.
    """
    if catches < 0:
        raise ValueError(f"catches cannot be negative; got {catches}")
    if nights <= 0:
        raise ValueError(
            f"nights must be positive — a rate over no time is not a "
            f"measurement; got {nights}")
    tail = (1.0 - confidence) / 2.0
    shape = catches + 0.5
    # Gamma(shape, rate=nights) quantile = gammaincinv(shape, p) / nights.
    low = 0.0 if catches == 0 else gammaincinv(shape, tail) / nights
    high = gammaincinv(shape, 1.0 - tail) / nights
    return low, catches / nights, high
