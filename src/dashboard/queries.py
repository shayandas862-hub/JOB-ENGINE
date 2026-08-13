"""The dashboard's entire read surface — four selects over four views.

Nothing else in this package touches SQL, and nothing here touches a table:
the views decide, the page renders. Adding a fact to the page means adding
it to a VIEW first (migration), never widening these selects to raw tables.
Lanes and pages are WHERE/LIMIT/OFFSET over the same views — the totals a
pager needs come from v_scorecard, and the sponsors browse (whose totals
change with its filters) rides them on each row via count(*) over(), so no
extra counting queries exist.
"""
from __future__ import annotations

PAGE_SIZE = 20


def fetch_today(cur, bucket: str | None = None, tray_only: bool = False,
                limit: int = PAGE_SIZE, offset: int = 0) -> list[dict]:
    """One lane of queue rows, receipts included; soonest deadline first."""
    where, params = [], []
    if bucket:
        where.append("bucket = %s")
        params.append(bucket)
    if tray_only:
        where.append("in_reading_tray")
    clause = f"where {' and '.join(where)} " if where else ""
    cur.execute(
        "select * from v_today " + clause +
        "order by deadline asc nulls last, age_days asc "
        "limit %s offset %s", (*params, limit, offset))
    return cur.fetchall()


def fetch_scorecard(cur) -> dict:
    """The honesty panel's one row of labelled counts (also the pager totals)."""
    cur.execute("select * from v_scorecard")
    return cur.fetchone() or {}


def fetch_owner_mirror(cur) -> list[dict]:
    """The mirror card's rows: one per owner, what the machine understands.

    Ordered by the number it exists to surface — how many recorded skills have
    no confirmed fact behind them — so the owner with the most unprovable
    claims is read first. That is the one whose CV will quietly be thinnest
    than they expect.
    """
    cur.execute("select * from v_owner_mirror "
                "order by skills_unevidenced desc, name asc")
    return cur.fetchall()


def fetch_health(cur, limit: int = PAGE_SIZE, offset: int = 0) -> list[dict]:
    """Company watch rows, problems first (error, then empty, then quiet)."""
    cur.execute(
        "select * from v_health "
        "order by case feed_status when 'error' then 0 when 'empty' then 1 "
        "else 2 end, last_fetched_at asc nulls last limit %s offset %s",
        (limit, offset))
    return cur.fetchall()


def fetch_sponsors(cur, industry: str | None = None, town: str | None = None,
                   limit: int = PAGE_SIZE, offset: int = 0) -> list[dict]:
    """Sponsors browse rows (U6): plain-substring filters over the view's
    plain-English industry descriptions and town; boards first, then most
    local jobs seen. The filtered pager total rides on every row as
    total_rows (count(*) over())."""
    where, params = [], []
    if industry and industry.strip():
        where.append("array_to_string(industry_descriptions, ' ') ilike %s")
        params.append(f"%{industry.strip()}%")
    if town and town.strip():
        where.append("town_city ilike %s")
        params.append(f"%{town.strip()}%")
    clause = f"where {' and '.join(where)} " if where else ""
    cur.execute(
        "select *, count(*) over() as total_rows from v_sponsor_browse "
        + clause +
        "order by (probe_outcome = 'board_found') desc nulls last, "
        "local_jobs_seen desc nulls last, organisation_name "
        "limit %s offset %s", (*params, limit, offset))
    return cur.fetchall()
