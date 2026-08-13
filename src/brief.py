"""Assemble the daily agenda — the numbers behind the daily_brief tool.

Applications first (the number this whole machine exists to move), then what
wants doing: today's queue top, the reading-tray depth, open review flags,
the last run's report card, and the lens's door-knock coverage (U4: a fresh
lens must hear honestly how many of its industry's doors have been knocked).
Pure reads over existing views and tables; owner-scoped throughout.
"""
from __future__ import annotations

from applyqueue import fetch_queue
from discover.census_queries import lens_coverage
from discover.promote_rule import load_rule
from pipeline.report import latest_run

APPLICATIONS_SQL = """
select count(*) filter (where r.application_status = 'applied') as applied_total,
       count(*) filter (where r.applied_date = current_date)    as applied_today
  from role_listings r
  join target_companies c on c.company_id = r.company_id
 where c.owner_id = %s
"""

TO_READ_SQL = """
select count(*) as n
  from role_listings r
  join target_companies c on c.company_id = r.company_id
 where c.owner_id = %s and r.staged_at is not null
"""

# World flags (owner_id null) plus this owner's own — the same scope
# list_review_flags serves, so the brief's count matches what they can act on.
REVIEWS_SQL = """
select kind, count(*) as n from review_items
 where status = 'open' and (owner_id is null or owner_id = %s)
 group by kind order by kind
"""


def assemble_brief(cur, owner_id) -> dict:
    """The whole agenda in one read: applications, queue top, tray, reviews,
    last run. Empty engine -> honest zeros, never an error."""
    cur.execute(APPLICATIONS_SQL, (owner_id,))
    apps = cur.fetchone() or {}
    queue = fetch_queue(cur, owner_id, 5)
    cur.execute(TO_READ_SQL, (owner_id,))
    tray = cur.fetchone() or {}
    cur.execute(REVIEWS_SQL, (owner_id,))
    reviews = cur.fetchall()
    rule = load_rule(cur, owner_id)
    coverage = lens_coverage(cur, (rule or {}).get("industry_codes") or [])
    return {
        "applications": {"total": apps.get("applied_total") or 0,
                         "today": apps.get("applied_today") or 0},
        "queue_top": queue,
        "to_read": tray.get("n") or 0,
        "reviews_open": reviews,
        "last_run": latest_run(cur),
        "lens_coverage": coverage,
    }
