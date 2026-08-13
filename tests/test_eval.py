"""Tests for the extraction grounding eval (read.eval)."""
from __future__ import annotations

from read.eval import EvalReport, check_grounding, evaluate


def test_check_grounding_case_insensitive():
    assert check_grounding("python", "We build in Python daily.") is True
    assert check_grounding("kubernetes", "No container orchestration here.") is False
    assert check_grounding("power bi", "Dashboards in POWER BI.") is True


def test_check_grounding_empty_inputs():
    assert check_grounding("python", "") is False
    assert check_grounding("", "anything") is False


def _row(skill_asked, skill_norm, jd, role_id=1):
    return {"skill_asked": skill_asked, "skill_norm": skill_norm, "jd_full": jd, "role_id": role_id}


def test_evaluate_counts_and_percentage():
    rows = [
        _row("Python", "python", "Python and SQL.", 1),
        _row("SQL", "sql", "Python and SQL.", 1),
        _row("Kubernetes", "kubernetes", "Python and SQL.", 1),  # not present
    ]
    rep = evaluate(rows)
    assert isinstance(rep, EvalReport)
    assert rep.total == 3
    assert rep.grounded == 2
    assert rep.ungrounded == 1
    assert rep.pct == round(100 * 2 / 3, 1)


def test_evaluate_collects_ungrounded_by_name_and_samples():
    rows = [
        _row("Machine Learning", "machine learning", "We use ML.", 7),
        _row("Machine Learning", "machine learning", "Also ML here.", 8),
        _row("AWS", "aws", "Hosted on AWS.", 7),
    ]
    rep = evaluate(rows)
    assert rep.by_name["Machine Learning"] == 2
    assert "AWS" not in rep.by_name
    assert (7 in [s["role_id"] for s in rep.samples]) and (8 in [s["role_id"] for s in rep.samples])


def test_evaluate_empty_is_safe():
    rep = evaluate([])
    assert rep.total == 0 and rep.grounded == 0 and rep.pct == 100.0
