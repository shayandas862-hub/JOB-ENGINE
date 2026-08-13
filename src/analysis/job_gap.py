"""One listing's skill gap: what it asks vs what the owner has.

v_skill_gap answers the aggregate question ("what should I learn overall");
this answers the per-job one: for THIS role, which asked skills does the
owner already hold (my_skills, current statuses only), which are missing,
and how covered are they — the data a gap-closing agent (or a CV emphasis
choice) reasons over. Pure read, curated columns, no secrets to leak.
"""
from __future__ import annotations


def fetch_job_gap(cur, owner_id, role_id: int) -> dict | None:
    """Have/missing split + coverage for one of this owner's listings, or None.

    Two questions, two owner filters (Phase 9 task 1b). The listing must be
    theirs — reached through target_companies, since role_listings carries no
    owner — and "i_have_it" must mean THEY have it, not that anybody does.
    The owner condition belongs in the LEFT JOIN's ON clause: moved to the
    WHERE it would discard every unmatched row and report perfect coverage.
    """
    cur.execute(
        "select r.role_id, r.role_title, c.company_name "
        "from role_listings r "
        "join target_companies c on c.company_id = r.company_id "
        "where r.role_id = %s and c.owner_id = %s",
        (role_id, owner_id))
    job = cur.fetchone()
    if job is None:
        return None

    cur.execute(
        "select rs.skill_asked, rs.skill_norm, rs.skill_type, "
        "(ms.skill_norm is not null) as i_have_it, ms.level as my_level "
        "from role_skills rs "
        "left join my_skills ms on ms.skill_norm = rs.skill_norm "
        "and ms.status in ('active', 'in_progress') "
        "and ms.owner_id = %s "
        "where rs.role_id = %s "
        "order by rs.skill_type, rs.skill_asked",
        (owner_id, role_id))
    skills = cur.fetchall()

    have = [s for s in skills if s["i_have_it"]]
    missing = [s for s in skills if not s["i_have_it"]]
    coverage = round(len(have) / len(skills), 2) if skills else None
    return {"role_id": job["role_id"], "role_title": job["role_title"],
            "company_name": job["company_name"],
            "skills_have": have, "skills_missing": missing,
            "have_count": len(have), "missing_count": len(missing),
            "coverage": coverage}
