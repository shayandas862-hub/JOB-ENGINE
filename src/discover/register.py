"""Walk the licensed-sponsor register for companies the owner hasn't targeted.

The register (``licensed_sponsors``) is the engine's unfair advantage: every
row is already a UK visa sponsor. This module surfaces A-rated Skilled Worker
sponsors that are *not yet* in the owner's ``target_companies`` — optionally
narrowed by region and industry keyword hints that live in the owner's
``my_constraints`` (kinds ``region_hint`` / ``industry_hint``), never in code.

The register carries no industry column, so an "industry hint" is matched as a
keyword against ``organisation_name``; a "region hint" against town/county.
"""
from __future__ import annotations

from dataclasses import dataclass

from normalise.text import norm


@dataclass(frozen=True)
class SponsorCandidate:
    """One licensed sponsor not yet on the owner's target list."""

    sponsor_id: int
    organisation_name: str
    org_name_norm: str
    town_city: str | None
    county: str | None
    rating: str | None
    route: str | None


def _like_patterns(values) -> list[str]:
    """Wrap raw keyword hints as case-insensitive ILIKE patterns; drop blanks."""
    out: list[str] = []
    for v in values or ():
        v = (v or "").strip()
        if v:
            out.append(f"%{v}%")
    return out


def load_discovery_hints(cur, owner_id: str) -> tuple[list[str], list[str]]:
    """Region + industry hints for one owner, read from ``my_constraints``.

    Kinds ``region_hint`` and ``industry_hint`` hold raw keywords (data, never
    code). Returns ``(region_patterns, industry_patterns)`` as ILIKE patterns;
    empty lists mean "no narrowing" — a UK-wide, all-industry register walk.
    """
    cur.execute(
        "select kind, value from my_constraints "
        "where owner_id = %s and kind in ('region_hint','industry_hint')",
        (owner_id,))
    region: list[str] = []
    industry: list[str] = []
    for r in cur.fetchall():
        if r["kind"] == "region_hint" and r["value"]:
            region.append(r["value"])
        elif r["kind"] == "industry_hint" and r["value"]:
            industry.append(r["value"])
    return _like_patterns(region), _like_patterns(industry)


def lookup_register_verdict(cur, name_norm: str) -> dict | None:
    """Exact-name register lookup: is this normalised name a licensed sponsor?

    Returns the register row (sponsor_id, name, town, rating, route,
    is_skilled_worker) or None. This is the deterministic verdict the by-name
    discovery path attaches so nothing enters the queue without one; the fuzzy,
    uncertain-match cross-check is Task 6.
    """
    cur.execute(
        "select id as sponsor_id, organisation_name, town_city, rating, route, "
        "is_skilled_worker from licensed_sponsors where org_name_norm = %s limit 1",
        (name_norm,))
    return cur.fetchone()


def load_known_sponsors(cur, owner_id: str) -> tuple[set[int], set[str]]:
    """The sponsors already on this owner's target list.

    Returns ``(sponsor_ids, name_norms)``. Names are run through the shared
    ``norm()`` so they compare against the register's ``org_name_norm``, which
    is produced by the same function — this catches companies added without a
    ``sponsor_id`` link.
    """
    cur.execute(
        "select sponsor_id, company_name from target_companies where owner_id = %s",
        (owner_id,))
    ids: set[int] = set()
    norms: set[str] = set()
    for r in cur.fetchall():
        if r["sponsor_id"] is not None:
            ids.add(r["sponsor_id"])
        if r["company_name"]:
            norms.add(norm(r["company_name"]))
    return ids, norms


def find_candidate_sponsors(
    cur,
    owner_id: str,
    *,
    region_patterns=(),
    industry_patterns=(),
    require_skilled_worker: bool = True,
    require_a_rating: bool = True,
    limit: int | None = None,
) -> list[SponsorCandidate]:
    """Register rows for ``owner_id`` that aren't yet target companies.

    Excludes any sponsor already linked to one of the owner's target companies
    — by ``sponsor_id`` or by matching normalised name. ``region_patterns``
    match town/county and ``industry_patterns`` match the organisation name;
    both are ILIKE patterns (see :func:`load_discovery_hints`). Every value is
    a bound parameter — only fixed clauses are toggled on or off.
    """
    known_ids, known_norms = load_known_sponsors(cur, owner_id)

    where: list[str] = []
    params: dict = {}
    if require_skilled_worker:
        where.append("ls.is_skilled_worker = true")
    if require_a_rating:
        where.append("ls.rating = %(rating)s")
        params["rating"] = "A"
    if known_ids:
        where.append("ls.id <> all(%(known_ids)s)")
        params["known_ids"] = list(known_ids)
    if known_norms:
        where.append("ls.org_name_norm <> all(%(known_norms)s)")
        params["known_norms"] = list(known_norms)
    region_patterns = list(region_patterns)
    if region_patterns:
        where.append(
            "(ls.town_city ilike any(%(region)s) or ls.county ilike any(%(region)s))")
        params["region"] = region_patterns
    industry_patterns = list(industry_patterns)
    if industry_patterns:
        where.append("ls.organisation_name ilike any(%(industry)s)")
        params["industry"] = industry_patterns

    sql = (
        "select ls.id as sponsor_id, ls.organisation_name, ls.org_name_norm, "
        "ls.town_city, ls.county, ls.rating, ls.route "
        "from licensed_sponsors ls "
        "where " + (" and ".join(where) if where else "true") +
        " order by ls.organisation_name")
    if limit is not None:
        sql += " limit %(limit)s"
        params["limit"] = limit

    cur.execute(sql, params)
    return [
        SponsorCandidate(
            sponsor_id=r["sponsor_id"],
            organisation_name=r["organisation_name"],
            org_name_norm=r["org_name_norm"],
            town_city=r["town_city"],
            county=r["county"],
            rating=r["rating"],
            route=r["route"],
        )
        for r in cur.fetchall()
    ]


def find_candidates_for_profile(
    cur, profile_id: str | None = None, *, limit: int | None = None,
) -> list[SponsorCandidate]:
    """Owner-scoped register walk: resolve the profile, load its hints, emit.

    Defaults to the sole/first profile. This is the entry point the discovery
    pipeline calls; the hints come from the DB, so no personal values live here.
    """
    from criteria.loader import default_profile_id

    if profile_id is None:
        profile_id = default_profile_id(cur)
    region_patterns, industry_patterns = load_discovery_hints(cur, profile_id)
    return find_candidate_sponsors(
        cur, profile_id,
        region_patterns=region_patterns,
        industry_patterns=industry_patterns,
        limit=limit,
    )
