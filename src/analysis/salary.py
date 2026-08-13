"""Salary: one place for stated-salary text and its numeric parse (deterministic, no API).

The single source of stated-salary *text* is salary_text_from() (used by the
keyword-fallback reader; Gemini supplies it directly when a key is set). parse_salary()
turns that text into a (min, max) range. The ADVISORY wall verdict lives in the
v_apply_queue SQL view — never in Python — so thresholds have exactly one home.
"""
from __future__ import annotations

import re

# £ followed by: comma-grouped (80,000) | 2-3 digits + k (80k, 80.5k) | 4-6 plain digits
_AMOUNT = re.compile(r"£\s?(\d{1,3}(?:,\d{3})+|\d{2,3}(?:\.\d+)?\s?k|\d{4,6})", re.I)

# A stated salary as written, e.g. "£80,000" or "£45,000 - £55,000".
_STATED = re.compile(r"£\s?\d[\d,]{3,}(?:\s?[-–]\s?£?\s?\d[\d,]{3,})?")


def salary_text_from(text: str | None) -> str | None:
    """The stated-salary text found in free text, or None. Single source of truth."""
    if not text:
        return None
    m = _STATED.search(text)
    return m.group(0) if m else None


def _to_int(token: str) -> int:
    t = token.lower().replace(" ", "").replace(",", "")
    if t.endswith("k"):
        return int(float(t[:-1]) * 1000)
    return int(float(t))


def parse_salary(text: str | None) -> tuple[int, int] | None:
    """Return (min, max) GBP found in text, or None. Filters implausible values."""
    if not text:
        return None
    vals = [_to_int(m.group(1)) for m in _AMOUNT.finditer(text)]
    vals = [v for v in vals if 15_000 <= v <= 500_000]
    if not vals:
        return None
    return min(vals), max(vals)
