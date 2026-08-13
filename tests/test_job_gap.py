"""fetch_job_gap — one listing's skills split into have vs missing.

The aggregate v_skill_gap answers "what should I learn overall"; this answers
the founder's per-job question: for THIS role, which of its asked skills do I
already have (my_skills, active-ish), which am I missing, and how covered am
I — the data a gap-closing agent reasons over before a CV is generated.
"""
from __future__ import annotations

import pytest

from tests.test_criteria import RoutingCursor

OWNER_A = "11111111-1111-4111-a111-111111111111"

JOB = {"role_id": 42, "role_title": "AI Engineer", "company_name": "Acme"}
SKILLS = [
    {"skill_asked": "Python", "skill_norm": "python", "skill_type": "must",
     "i_have_it": True, "my_level": "strong"},
    {"skill_asked": "Kubernetes", "skill_norm": "kubernetes",
     "skill_type": "must", "i_have_it": False, "my_level": None},
    {"skill_asked": "RAG", "skill_norm": "rag", "skill_type": "nice",
     "i_have_it": False, "my_level": None},
]


def test_job_gap_unknown_role_returns_none():
    from analysis.job_gap import fetch_job_gap
    cur = RoutingCursor([("from role_listings", [])])
    assert fetch_job_gap(cur, OWNER_A, 999) is None


def test_job_gap_splits_have_and_missing_with_coverage():
    from analysis.job_gap import fetch_job_gap
    cur = RoutingCursor([
        ("from role_listings", [JOB]),
        ("from role_skills", SKILLS),
    ])
    out = fetch_job_gap(cur, OWNER_A, 42)
    assert out["role_id"] == 42 and out["company_name"] == "Acme"
    assert [s["skill_asked"] for s in out["skills_have"]] == ["Python"]
    assert [s["skill_asked"] for s in out["skills_missing"]] == ["Kubernetes", "RAG"]
    assert out["have_count"] == 1 and out["missing_count"] == 2
    assert out["coverage"] == round(1 / 3, 2)
    # the my_skills join only counts current skills, and reads never audit
    skills_sql = next(s for s, _ in cur.executed if "from role_skills" in s)
    assert "left join my_skills" in skills_sql
    assert "'active'" in skills_sql
    assert not any("mcp_audit" in s for s, _ in cur.executed)


def test_job_gap_asks_both_questions_about_one_owner_only():
    # Two separate leaks, both closed here (Phase 9 task 1b). The listing read
    # reaches its owner through target_companies — role_listings has no owner
    # column of its own — and the skills read must match MY skills, not
    # whoever else happens to hold that skill_norm. The owner belongs in the
    # LEFT JOIN's ON clause, never a WHERE: in a WHERE it would drop every
    # missing skill and report perfect coverage for everyone.
    from analysis.job_gap import fetch_job_gap
    cur = RoutingCursor([
        ("from role_listings", [JOB]),
        ("from role_skills", SKILLS),
    ])
    fetch_job_gap(cur, OWNER_A, 42)

    job_sql, job_params = next((s, p) for s, p in cur.executed
                               if "from role_listings" in s)
    assert "c.owner_id = %s" in job_sql
    assert job_params == (42, OWNER_A)

    skills_sql, skills_params = next((s, p) for s, p in cur.executed
                                     if "from role_skills" in s)
    on_clause = skills_sql.split("left join my_skills")[1].split("where")[0]
    assert "ms.owner_id = %s" in on_clause
    assert skills_params == (OWNER_A, 42)


def test_job_gap_cannot_be_called_the_old_ownerless_way():
    # Called exactly as Phase 8.5 called it. Fails against the pre-1b source.
    from analysis.job_gap import fetch_job_gap
    with pytest.raises(TypeError):
        fetch_job_gap(RoutingCursor([("from role_listings", [])]), role_id=42)


def test_job_gap_with_no_asked_skills_reports_empty_but_valid():
    from analysis.job_gap import fetch_job_gap
    cur = RoutingCursor([
        ("from role_listings", [JOB]),
        ("from role_skills", []),
    ])
    out = fetch_job_gap(cur, OWNER_A, 42)
    assert out["skills_have"] == [] and out["skills_missing"] == []
    assert out["coverage"] is None                    # nothing asked, no ratio
