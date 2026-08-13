"""Load a profile and its criteria; build the role-fit matcher from them."""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Criteria:
    profile_id: str
    name: str
    salary_floor: float | None
    threshold_standard: float | None
    threshold_new_entrant: float | None
    kill_keywords: list[str]
    role_patterns: list[str]   # search titles from target_roles


def default_profile_id(cur) -> str:
    """The sole/first profile's id — the owner writes hang off. Raises if none."""
    cur.execute("select profile_id from profiles order by created_at limit 1")
    row = cur.fetchone()
    if not row:
        raise RuntimeError("No profile found — create one in the profiles table first.")
    return row["profile_id"]


def load_criteria(cur, profile_id: str | None = None) -> Criteria:
    """Load one profile's full criteria set. Defaults to the sole/first profile."""
    if profile_id is None:
        cur.execute("select profile_id, name from profiles order by created_at limit 1")
    else:
        cur.execute("select profile_id, name from profiles where profile_id = %s",
                    (profile_id,))
    row = cur.fetchone()
    if not row:
        raise RuntimeError("No profile found — create one in the profiles table first.")
    pid, name = row["profile_id"], row["name"]

    cur.execute(
        "select kind, value, numeric_value from my_constraints where owner_id = %s",
        (pid,))
    numbers: dict[str, float] = {}
    kills: list[str] = []
    for c in cur.fetchall():
        if c["kind"] == "kill_keyword" and c["value"]:
            kills.append(c["value"])
        elif c["numeric_value"] is not None:
            numbers[c["kind"]] = c["numeric_value"]

    cur.execute(
        "select search_title from target_roles where owner_id = %s order by search_title",
        (pid,))
    patterns = [r["search_title"] for r in cur.fetchall() if r["search_title"]]

    return Criteria(
        profile_id=pid,
        name=name,
        salary_floor=numbers.get("salary_floor"),
        threshold_standard=numbers.get("salary_threshold_standard"),
        threshold_new_entrant=numbers.get("salary_threshold_new_entrant"),
        kill_keywords=kills,
        role_patterns=patterns,
    )


# Generic, deliberately non-personal samples so an offline --dry-run has a
# matcher without a database. Real runs always load target_roles instead.
SAMPLE_ROLE_PATTERNS = [
    "Software Engineer",
    "Machine Learning Engineer",
    "Data Engineer",
    "Solutions Engineer",
]


def build_role_matcher(patterns: list[str]):
    """Compile search titles into one case-insensitive substring matcher.

    Titles are treated as plain text; internal whitespace also matches hyphens
    ('Front End' == 'Front-End'). Returns a callable(title)->bool.
    """
    parts = [re.escape(p.strip()).replace(r"\ ", r"[\s\-]+")
             for p in patterns if p and p.strip()]
    if not parts:
        return lambda title: False
    rx = re.compile("|".join(parts), re.I)
    return lambda title: bool(title and rx.search(title))
