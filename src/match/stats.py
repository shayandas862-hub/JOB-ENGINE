"""Percentiles and smoothed confidence — numbers that carry their sample size.

percentile/summary answer "what do salaries like this look like" honestly:
empty data returns None, never 0. smoothed_rate is the Laplace rule of
succession — small samples shrink toward the prior instead of shouting 100%,
and the receipts (successes, n, prior) always ride along so 2/2 and 900/1000
can never masquerade as the same fact.
"""
from __future__ import annotations


def percentile(values, p: float) -> float | None:
    """Linear-interpolation percentile (p in [0, 100]); None on empty data."""
    if not 0 <= p <= 100:
        raise ValueError(f"percentile must be 0..100, got {p}")
    data = sorted(values)
    if not data:
        return None
    rank = (p / 100) * (len(data) - 1)
    lo = int(rank)
    frac = rank - lo
    if frac == 0:
        return float(data[lo])
    return float(data[lo]) + frac * (float(data[lo + 1]) - float(data[lo]))


def summary(values) -> dict:
    """Quartile summary that always carries its sample size.

    {"n", "p25", "p50", "p75"} — percentile values are None when n == 0.
    """
    data = list(values)
    return {
        "n": len(data),
        "p25": percentile(data, 25),
        "p50": percentile(data, 50),
        "p75": percentile(data, 75),
    }


def smoothed_rate(successes: int, trials: int, *,
                  prior_successes: float = 1.0,
                  prior_trials: float = 2.0) -> dict:
    """Laplace-smoothed success rate with its receipts.

    rate = (successes + prior_successes) / (trials + prior_trials). The
    default prior (1 of 2) pulls tiny samples toward 0.5; large samples
    converge to the raw rate. raw_rate is None when there are no trials.
    """
    if successes < 0 or trials < 0 or successes > trials:
        raise ValueError(f"impossible counts: {successes}/{trials}")
    if prior_successes < 0 or prior_trials < prior_successes:
        raise ValueError(
            f"impossible prior: {prior_successes}/{prior_trials}")
    if trials + prior_trials == 0:
        raise ValueError("no evidence and no prior — rate undefined")
    return {
        "rate": (successes + prior_successes) / (trials + prior_trials),
        "raw_rate": (successes / trials) if trials else None,
        "successes": successes,
        "n": trials,
        "prior_successes": prior_successes,
        "prior_trials": prior_trials,
    }
