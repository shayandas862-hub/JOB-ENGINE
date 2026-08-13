"""Curated reads over the census for humans and the MCP skin.

The census tables carry one secret-shaped column (ats_token); like the queue
reads, every column list here is explicit and never selects it. These are
pure reads — no writes, no audit.
"""
from __future__ import annotations

from criteria.lens import word_patterns
from discover.classify import SOFTWARE_SIC

# The universal search's column list: the view's plain-English industry
# receipts + the census card's board facts. Explicit, and never the token.
_SPONSOR_COLS = (
    "v.org_name_norm, v.organisation_name, v.town_city, v.registry_status, "
    "v.industry_codes, v.industry_descriptions, sc.probe_outcome, "
    "sc.careers_url, sc.local_jobs_seen, sc.total_jobs_seen"
)


def search_sponsors(cur, industry_words: str | None = None,
                    town: str | None = None, *,
                    with_boards_only: bool = False, limit: int = 25) -> list[dict]:
    """The universal census search (U3): any industry in plain words, any
    town, optional live-boards-only — over v_sponsor_industry, so every row
    carries its receipts (the official industry descriptions that matched).
    Words that carry no usable token mean no industry filter, not an empty
    answer. Same fetchable-first ordering as the software list it
    generalises."""
    where, params = [], {"n": limit}
    pats = word_patterns(industry_words or "")
    if pats:
        where.append("array_to_string(v.industry_descriptions, ' ') "
                     "ilike any (%(pats)s)")
        params["pats"] = pats
    if town and town.strip():
        where.append("v.town_city ilike %(town)s")
        params["town"] = f"%{town.strip()}%"
    if with_boards_only:
        where.append("sc.probe_outcome = 'board_found'")
    where_sql = ("where " + " and ".join(where) + " ") if where else ""
    cur.execute(
        f"select {_SPONSOR_COLS} from v_sponsor_industry v "
        "join sponsor_census sc using (org_name_norm) "
        f"{where_sql}"
        "order by (sc.probe_outcome = 'board_found') desc nulls last, "
        "sc.local_jobs_seen desc nulls last, v.organisation_name "
        "limit %(n)s",
        params)
    return cur.fetchall()

# Everything a founder needs to judge a census software company — no token.
_SOFTWARE_COLS = (
    "org_name_norm, organisation_name, town_city, registry_status, "
    "industry_codes, incorporated, probe_outcome, ats_type, careers_url, "
    "local_jobs_seen, total_jobs_seen"
)


def lens_coverage(cur, codes) -> dict | None:
    """Door-knock coverage of one lens (U4): of the registry-matched census
    cards carrying these codes — the same slice the Pass-2 picker sees — how
    many have been probed. The brief's honest expectation line for a fresh
    lens. None when the lens has no codes (nothing to measure)."""
    if not codes:
        return None
    cur.execute(
        "select count(*) filter (where probe_outcome is not null) as knocked, "
        "count(*) as total from sponsor_census "
        "where registry_outcome = 'matched' "
        "and industry_codes && %(codes)s::text[]",
        {"codes": list(codes)})
    row = cur.fetchone() or {}
    knocked, total = row.get("knocked") or 0, row.get("total") or 0
    pct = round(100.0 * knocked / total, 1) if total else 0.0
    return {"knocked": knocked, "total": total, "pct": pct}


def list_software_companies(cur, limit=50, *, with_boards_only=False) -> list[dict]:
    """The census's software-company lot, most fetchable first.

    Software = Pass-1 industry codes overlapping SOFTWARE_SIC. Boards-found
    cards lead (they can be promoted and fetched today), then the ones with
    the most local jobs seen, then name — deterministic paging.
    """
    board_filter = ("and probe_outcome = 'board_found' "
                    if with_boards_only else "")
    cur.execute(
        f"select {_SOFTWARE_COLS} from sponsor_census "
        "where industry_codes && %(sic)s::text[] "
        f"{board_filter}"
        "order by (probe_outcome = 'board_found') desc nulls last, "
        "local_jobs_seen desc nulls last, organisation_name "
        "limit %(n)s",
        {"n": limit, "sic": list(SOFTWARE_SIC)})
    return cur.fetchall()
