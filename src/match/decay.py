"""Half-life freshness weight.

One curve, pinned: 0.5 ** (age_days / half_life_days). A listing at one
half-life counts half as much as a fresh one. Callers choose the half-life
per use; any freshness number is recomputable from age + half-life alone.
"""
from __future__ import annotations


def freshness(age_days: float, half_life_days: float) -> float:
    """Freshness in (0, 1]; 1.0 at age 0, halving every half-life.

    Negative ages (clock drift) clamp to fully fresh.
    """
    if half_life_days <= 0:
        raise ValueError(f"half-life must be positive, got {half_life_days}")
    if age_days < 0:
        return 1.0
    return 0.5 ** (age_days / half_life_days)
