"""The status page's entire read surface — two selects over two views.

Nothing else in this package touches SQL and nothing here touches a table.
The views (migration 0043) decide what a stranger may see; this module only
fetches it. Pinned by test: naming a raw table here would step around the
privacy boundary rather than through it.
"""
from __future__ import annotations


def fetch_status(cur) -> dict:
    """The one row of person-free headline aggregates."""
    cur.execute("select * from v_status")
    return cur.fetchone() or {}


def fetch_stages(cur) -> list[dict]:
    """Per-stage health of the latest finished run, in run order."""
    cur.execute("select * from v_status_stages order by stage_order")
    return cur.fetchall()
