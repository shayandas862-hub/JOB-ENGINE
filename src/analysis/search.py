"""The U3 word searches: who is hiring, and what those jobs want.

search_hiring answers "who is hiring <role words> and can sponsor?" across
the two worlds already stored: tracked listings (live boards, apply-able
today) and census jobs (titles seen while door-knocking; every census org
is on the sponsor register by construction). skill_gaps_for_words answers
"what do <role words> jobs want that I lack" over stored role_skills.
Pure reads; the matching title itself is each row's receipt.
"""
from __future__ import annotations

from criteria.lens import word_patterns


def search_hiring(cur, role_words: str, town: str | None = None, *,
                  limit: int = 25) -> list[dict]:
    """Tracked matches first (a live board means apply-able today), then
    census sightings, capped to `limit` overall. Empty words = empty answer
    (a role search needs a role)."""
    pats = word_patterns(role_words)
    if not pats:
        return []
    params = {"pats": pats, "n": limit}
    tracked_town = census_town = ""
    if town and town.strip():
        params["town"] = f"%{town.strip()}%"
        tracked_town = "and r.location ilike %(town)s "
        census_town = "and cj.location ilike %(town)s "

    cur.execute(
        "select r.role_id, r.role_title as title, c.company_name, "
        "r.location, r.role_url, r.salary_text, 'tracked' as source "
        "from role_listings r join target_companies c using (company_id) "
        "where r.role_status = 'open' and r.role_title ilike any (%(pats)s) "
        f"{tracked_town}"
        "order by r.role_id desc limit %(n)s",
        params)
    hits = cur.fetchall()[:limit]

    if len(hits) < limit:
        params["n"] = limit - len(hits)
        cur.execute(
            "select cj.title, cj.company_name, cj.org_name_norm, "
            "cj.location, cj.url, cj.salary_text, 'census' as source "
            "from census_jobs cj "
            "where cj.title ilike any (%(pats)s) "
            f"{census_town}"
            "order by cj.seen_at desc, cj.census_job_id limit %(n)s",
            params)
        hits += cur.fetchall()[:limit - len(hits)]
    return hits


def skill_gaps_for_words(cur, owner_id: str, role_words: str, *,
                         limit: int = 20) -> list[dict]:
    """Demand-ranked skills asked by listings whose titles match the words,
    each marked i_have_it against the owner's active skills — the per-lens
    gap ("what do care jobs want that I lack")."""
    pats = word_patterns(role_words)
    if not pats:
        return []
    cur.execute(
        "select coalesce(ss.canonical_norm, rs.skill_norm) as skill_norm, "
        "max(coalesce(ss.canonical_label, rs.skill_asked)) as skill, "
        "max(rs.skill_type) as skill_type, "
        "count(distinct rs.role_id) as demand, "
        "bool_or(ms.skill_norm is not null) as i_have_it "
        "from role_skills rs "
        "join role_listings r on r.role_id = rs.role_id "
        "left join skill_synonyms ss on ss.raw_norm = rs.skill_norm "
        "left join my_skills ms on "
        "ms.skill_norm = coalesce(ss.canonical_norm, rs.skill_norm) "
        "and ms.owner_id = %(owner)s "
        "and ms.status in ('active', 'in_progress') "
        "where r.role_title ilike any (%(pats)s) "
        "group by coalesce(ss.canonical_norm, rs.skill_norm) "
        "order by demand desc, skill_norm limit %(n)s",
        {"pats": pats, "owner": owner_id, "n": limit})
    return cur.fetchall()
