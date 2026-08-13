"""Apply-by dates: stated when the JD says so, otherwise a labelled estimate.

Stated deadlines are extracted only when a deadline PHRASE introduces a date —
a bare date in a JD is usually a start date or company trivia, not a deadline.
Everything here is advisory; deadlines never filter the queue.
"""
from __future__ import annotations

import re
from datetime import date, timedelta

_MONTHS = {m: i + 1 for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july",
     "august", "september", "october", "november", "december"])}

# "closing date", "apply by", "deadline", "applications close" + nearby date
_PHRASE = r"(?:closing date|apply by|application deadline|deadline|applications? close[sd]?(?: on)?)"

_DATE_PATTERNS = [
    # 31 July 2026 / 1st August 2026
    re.compile(_PHRASE + r"\D{0,12}?(\d{1,2})(?:st|nd|rd|th)?\s+([a-z]+)\s+(\d{4})", re.I),
    # 07/08/2026 (UK day-first)
    re.compile(_PHRASE + r"\D{0,12}?(\d{1,2})/(\d{1,2})/(\d{4})", re.I),
    # 2026-08-15
    re.compile(_PHRASE + r"\D{0,12}?(\d{4})-(\d{2})-(\d{2})", re.I),
]


def extract_stated_deadline(jd_text: str | None) -> date | None:
    """A deadline the JD explicitly states, or None. Never inferred."""
    if not jd_text:
        return None
    for i, rx in enumerate(_DATE_PATTERNS):
        m = rx.search(jd_text)
        if not m:
            continue
        try:
            if i == 0:  # day month-name year
                month = _MONTHS.get(m.group(2).lower())
                if not month:
                    continue
                return date(int(m.group(3)), month, int(m.group(1)))
            if i == 1:  # dd/mm/yyyy (UK day-first)
                return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            continue    # impossible date in text -> not a usable deadline
    return None


def estimate_apply_by(first_seen: date, window_days: int) -> date:
    """Advisory apply-by: the profile's window after the listing appeared."""
    return first_seen + timedelta(days=window_days)


def choose_deadline(jd_text, first_seen: date, window_days: int) -> tuple[date, str]:
    """(deadline, source): stated wins; otherwise a labelled estimate."""
    stated = extract_stated_deadline(jd_text)
    if stated:
        return stated, "stated"
    return estimate_apply_by(first_seen, window_days), "estimated"
