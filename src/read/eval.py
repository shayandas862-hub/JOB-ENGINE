"""Grounding eval for extracted skills — a free, deterministic quality gate.

A skill is "grounded" if its normalised name appears verbatim in the job
description it was extracted from. Ungrounded skills are either canonicalisations
(JD says "ML", Gemini wrote "Machine Learning") or — rarely — hallucinations.
This eval can't tell those apart on its own; it surfaces the ungrounded set so a
human (or the GA-004 synonym map) can judge. It never blocks extraction; it
reports after the fact.
"""
from __future__ import annotations

from dataclasses import dataclass, field


def check_grounding(skill_norm: str, jd_text: str | None) -> bool:
    """True if the (lowercased) skill name appears verbatim in the JD text."""
    if not skill_norm or not jd_text:
        return False
    return skill_norm.lower() in jd_text.lower()


@dataclass
class EvalReport:
    total: int = 0
    grounded: int = 0
    ungrounded: int = 0
    pct: float = 100.0  # % grounded; 100 for an empty set (nothing wrong)
    by_name: dict[str, int] = field(default_factory=dict)   # ungrounded skill_asked -> count
    samples: list[dict] = field(default_factory=list)       # ungrounded rows (skill_asked, role_id)


def evaluate(rows: list[dict]) -> EvalReport:
    """Score [{skill_asked, skill_norm, jd_full, role_id}] for grounding."""
    rep = EvalReport(total=len(rows))
    for r in rows:
        if check_grounding(r.get("skill_norm", ""), r.get("jd_full")):
            rep.grounded += 1
        else:
            rep.ungrounded += 1
            name = r.get("skill_asked") or r.get("skill_norm") or "?"
            rep.by_name[name] = rep.by_name.get(name, 0) + 1
            rep.samples.append({"skill_asked": name, "role_id": r.get("role_id")})
    rep.pct = round(100 * rep.grounded / rep.total, 1) if rep.total else 100.0
    return rep
