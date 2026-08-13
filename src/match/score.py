"""Overlap × rarity role scoring — the score AND its receipts.

The score is the rarity-weighted share of a role's required skills that the
owner holds: matching the one rare skill a role really hinges on beats
matching three commodity ones. Receipts make it recomputable anywhere:
score == weight_matched / weight_total, matched + missing partition the
requirement set, and missing is sorted heaviest-first — it doubles as the
"what would close the gap" list.
"""
from __future__ import annotations

import math

from normalise.text import norm


def rarity_weight(roles_with_skill: int, total_roles: int) -> float:
    """IDF-shaped weight: 1 + ln((total+1)/(demand+1)).

    A skill every role demands carries no ranking information (weight 1.0);
    the rarer the skill, the heavier it weighs. An empty corpus has no
    opinion — everything weighs the baseline 1.0.
    """
    if total_roles < 0 or roles_with_skill < 0 or roles_with_skill > total_roles:
        raise ValueError(
            f"impossible counts: {roles_with_skill} roles with skill "
            f"of {total_roles} total")
    return 1.0 + math.log((total_roles + 1) / (roles_with_skill + 1))


def score_role(role_skills: list[dict], my_skills) -> dict:
    """Score one role's requirements against the owner's skills.

    ``role_skills``: [{"skill": str, "weight": float}] (weights from
    :func:`rarity_weight`); ``my_skills``: iterable of skill names. Matching
    uses the shared norm() on both sides; receipts echo the input strings.
    Duplicate requirements collapse to their heaviest weight.

    Returns {"score", "matched", "missing", "weight_matched", "weight_total"};
    score is None when there is nothing scorable (no requirements, or all
    zero-weight) — never a fake 0.
    """
    heaviest: dict[str, dict] = {}   # skill_norm -> {"skill": input echo, "weight": float}
    for req in role_skills:
        weight = float(req["weight"])
        if weight < 0:
            raise ValueError(f"negative weight for skill {req['skill']!r}")
        key = norm(req["skill"])
        if key not in heaviest or weight > heaviest[key]["weight"]:
            heaviest[key] = {"skill": req["skill"], "weight": weight}

    owned = {norm(s) for s in my_skills}
    matched = [entry for key, entry in heaviest.items() if key in owned]
    missing = [entry for key, entry in heaviest.items() if key not in owned]

    def gap_order(entry: dict):
        return (-entry["weight"], norm(entry["skill"]))
    matched.sort(key=gap_order)
    missing.sort(key=gap_order)

    weight_matched = sum(e["weight"] for e in matched)
    weight_total = weight_matched + sum(e["weight"] for e in missing)
    return {
        "score": (weight_matched / weight_total) if weight_total > 0 else None,
        "matched": matched,
        "missing": missing,
        "weight_matched": weight_matched,
        "weight_total": weight_total,
    }
