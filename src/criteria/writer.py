"""Write a profile's criteria: numeric thresholds, target companies, skills.

The read side lives in loader.py; these are the owner-scoped writes the MCP
action tools call. Kinds are whitelisted so a caller can never write an
arbitrary or secret-ish constraint row.
"""
from __future__ import annotations

import datetime

from normalise.text import norm

# The three singleton numeric constraints the queue's salary wall reads
# (kinds mirror criteria.loader). A partial unique index keeps them one-per-owner.
NUMERIC_KINDS = frozenset({
    "salary_floor",
    "salary_threshold_standard",
    "salary_threshold_new_entrant",
})


def set_numeric_criterion(cur, owner_id: str, kind: str, value: float) -> None:
    """Upsert one owner-scoped numeric constraint. Update in place, insert if the
    owner has no such row yet. Rejects any kind outside the whitelist."""
    if kind not in NUMERIC_KINDS:
        raise ValueError(f"not a settable numeric criterion: {kind!r}")
    cur.execute(
        "update my_constraints set numeric_value=%s where kind=%s and owner_id=%s",
        (value, kind, owner_id))
    if cur.rowcount == 0:
        cur.execute(
            "insert into my_constraints (kind, numeric_value, owner_id) "
            "values (%s,%s,%s)",
            (kind, value, owner_id))


def add_target_company(cur, owner_id: str, company_name: str,
                       careers_url: str | None = None) -> int:
    """Register a new target company for the owner (status defaults to
    not_started; the classifier probes it later). Returns the new company_id."""
    cur.execute(
        "insert into target_companies (company_name, careers_url, owner_id) "
        "values (%s,%s,%s) returning company_id",
        (company_name, careers_url, owner_id))
    return cur.fetchone()["company_id"]


def add_skill(cur, owner_id: str, skill: str, *, level: str | None = None,
              evidence: str | None = None,
              learned_at: datetime.date | str | None = None,
              category: str | None = None,
              source: str | None = None) -> dict:
    """Upsert one owner-scoped skill, keyed on the normalised name (U2).

    learned_at + evidence are the learning-curve model's day-one data.
    Update-then-insert like set_numeric_criterion: on update, fields the
    caller left out keep their stored values and the row reactivates
    (re-adding a retired skill revives it). Returns {skill, skill_norm,
    outcome added|updated}.
    """
    skill_norm = norm(skill)
    if not skill_norm:
        raise ValueError("skill must not be blank")
    if isinstance(learned_at, str):
        learned_at = datetime.date.fromisoformat(learned_at)  # raises ValueError

    cur.execute(
        "update my_skills set skill=%s, level=coalesce(%s, level), "
        "evidence=coalesce(%s, evidence), "
        "learned_at=coalesce(%s, learned_at), "
        "category=coalesce(%s, category), source=coalesce(%s, source), "
        "status='active', updated_at=now() "
        "where owner_id=%s and skill_norm=%s",
        (skill.strip(), level, evidence, learned_at, category, source,
         owner_id, skill_norm))
    outcome = "updated"
    if cur.rowcount == 0:
        # skill_norm is NOT written: it is GENERATED ALWAYS on my_skills
        # (since 0001), so naming it here is rejected outright and every new
        # skill failed to save — B-GAE-013. norm() still computes it for the
        # update's WHERE clause and for the returned value, and the database's
        # expression is the same one, which the DB test asserts rather than
        # assumes. Same rule as licensed_sponsors: insert raw facts only.
        cur.execute(
            "insert into my_skills (skill, level, evidence, "
            "learned_at, category, source, owner_id) "
            "values (%s,%s,%s,%s,%s,%s,%s)",
            (skill.strip(), level, evidence, learned_at,
             category, source, owner_id))
        outcome = "added"
    return {"skill": skill.strip(), "skill_norm": skill_norm,
            "outcome": outcome}
