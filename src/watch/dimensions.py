"""The ten dimensions a watch may be made of, and the gate that admits them.

`plans/0011` §1 fixed this space by filtering every stored fact through four
admission gates rather than by choosing favourites, and §5 refuses a free-text
query language: combinations of these ten, nothing else.

The gate below is where that refusal becomes real. Two properties matter more
than the individual rules:

* **An unknown key is REFUSED, never ignored.** A dropped filter leaves a
  watch that catches far more than the owner asked for, and every catch still
  carries correct-looking receipts — a wrong answer that cannot be seen.
* **A meaningless value is refused too.** `freshness_days: 0` and
  `role_words: ""` are the two ends of the same failure: a watch that can
  never catch anything, and one that catches everything. Both read to the
  owner as a broken machine rather than as a nonsense filter.

Values are normalised on the way in (case, whitespace) because the overlap
maths compares catch sets across watches: two spellings of one company would
otherwise produce two watches with a Jaccard of 1.0 and an advisory to merge
rows that were never different.
"""
from __future__ import annotations

from normalise.text import norm

#: The whole space. Ordered as `plans/0011` §1 tabulates them.
DIMENSIONS = (
    "company",          # 1 · one company or a set, by normalised name
    "industry_codes",   # 2 · plain words become SIC codes before they land here
    "role_words",       # 3 · synonym-expanded titles
    "location",         # 4 · town or region text
    "salary_floor",     # 5 · the visa wall ALWAYS applies on top of this
    "source",           # 6 · company board / ad site / either
    "rating",           # 7 · A-rated sponsors only, or any
    "freshness_days",   # 8 · first seen within N days
    "fit_floor",        # 9 · match score at or above a threshold
    "deadline_days",    # 10 · closes within N days
)

SOURCES = ("board", "ads", "either")
RATINGS = ("A", "any")

# Beyond the stored history a freshness window is a lie: the replay can only
# count what the database has watched. 365 is generous against a machine that
# started keeping listing_events in Phase 4.
MAX_FRESHNESS_DAYS = 365
MAX_DEADLINE_DAYS = 365


class InvalidWatch(ValueError):
    """A watch that would be nonsense, refused at the door with the reason."""


def _text(value, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidWatch(
            f"{field} must be non-empty text; got {value!r}. An empty "
            "value here matches every listing, which is not a watch.")
    return " ".join(value.split()).strip().lower()


def _name_set(value, field: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise InvalidWatch(
            f"{field} must be a non-empty list; got {value!r}. A bare string "
            "is a common slip — pass [\"monzo\"], not \"monzo\".")
    return [norm(v) if field == "company" else _text(v, field) for v in value]


def _whole(value, field: str, *, low: int, high: int) -> int:
    # bool is an int in Python and True would sail through every range check
    # below as 1, so it is excluded by type before the range is looked at.
    if isinstance(value, bool) or not isinstance(value, int):
        raise InvalidWatch(f"{field} must be a whole number; got {value!r}")
    if not low <= value <= high:
        raise InvalidWatch(
            f"{field} must be between {low} and {high}; got {value}")
    return value


def _money(value, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InvalidWatch(
            f"{field} must be a number, not text; got {value!r}")
    if value < 0:
        raise InvalidWatch(f"{field} cannot be negative; got {value}")
    return float(value)


def _fraction(value, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InvalidWatch(f"{field} must be a number; got {value!r}")
    if not 0.0 <= value <= 1.0:
        raise InvalidWatch(
            f"{field} is a score between 0 and 1; got {value}")
    return float(value)


def _one_of(value, field: str, allowed: tuple[str, ...]) -> str:
    if value not in allowed:
        raise InvalidWatch(
            f"{field} must be one of {list(allowed)}; got {value!r}")
    return value


#: dimension -> the function that admits and normalises its value.
_CHECKS = {
    "company": lambda v: _name_set(v, "company"),
    "industry_codes": lambda v: _name_set(v, "industry_codes"),
    "role_words": lambda v: _text(v, "role_words"),
    "location": lambda v: _text(v, "location"),
    "salary_floor": lambda v: _money(v, "salary_floor"),
    "source": lambda v: _one_of(v, "source", SOURCES),
    "rating": lambda v: _one_of(v, "rating", RATINGS),
    "freshness_days": lambda v: _whole(v, "freshness_days", low=1,
                                       high=MAX_FRESHNESS_DAYS),
    "fit_floor": lambda v: _fraction(v, "fit_floor"),
    "deadline_days": lambda v: _whole(v, "deadline_days", low=1,
                                      high=MAX_DEADLINE_DAYS),
}


def validate_filters(filters) -> dict:
    """The admitted, normalised filter set — or InvalidWatch saying why not.

    Refuses: anything that is not an object, an object with no dimensions at
    all (that is the whole job market, nightly), and any key outside the ten.
    The last one is the important refusal: it is what stops a watch quietly
    growing a filter the evaluator does not implement.
    """
    if not isinstance(filters, dict):
        raise InvalidWatch(
            f"a watch's filters must be an object; got {type(filters).__name__}")
    unknown = sorted(set(filters) - set(DIMENSIONS))
    if unknown:
        raise InvalidWatch(
            f"unknown watch dimension(s): {unknown}. A watch is built from "
            f"{list(DIMENSIONS)} and nothing else — the salary wall and the "
            "other always-on protections are deliberately not switchable.")
    if not filters:
        raise InvalidWatch(
            "a watch needs at least one dimension; an empty watch is every "
            "listing in the database, every night")
    return {name: _CHECKS[name](value) for name, value in filters.items()}
