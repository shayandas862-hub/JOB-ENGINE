"""Plan and record listing events for one company's fetch."""
from __future__ import annotations

import json
from dataclasses import dataclass

from history.fingerprint import diff_fields, fingerprint


@dataclass(frozen=True)
class PlannedEvent:
    role_id: int | None      # None for 'appeared' until the upsert assigns one
    dedupe_key: str
    event_type: str          # appeared | changed | reopened (closed comes from job-rot)
    changes: dict | None
    reset_read: bool         # description changed -> this listing gets re-read


def plan_events(company_name, existing_by_key: dict, keyed_jobs) -> list[PlannedEvent]:
    """Compare fetched jobs against the stored rows and plan events.

    existing_by_key: dedupe_key -> row (role_id, role_status, content_fingerprint,
    role_title, location, salary_text, jd_full). keyed_jobs: (dedupe_key, Job).
    Unchanged listings plan nothing — re-runs on unchanged data are silent.
    """
    events: list[PlannedEvent] = []
    for key, job in keyed_jobs:
        old = existing_by_key.get(key)
        if old is None:
            events.append(PlannedEvent(None, key, "appeared", None, False))
            continue
        new_fp = fingerprint(job.title, job.location, job.salary_text, job.jd_text)
        changed = new_fp != old["content_fingerprint"]
        diff = diff_fields(
            {"title": old["role_title"], "location": old["location"],
             "salary_text": old["salary_text"], "jd_text": old["jd_full"]},
            {"title": job.title, "location": job.location,
             "salary_text": job.salary_text, "jd_text": job.jd_text},
        ) if changed else {}
        reset = "description" in diff
        if old["role_status"] == "closed":
            # One event tells the story: it came back (with its diff, if any).
            events.append(PlannedEvent(old["role_id"], key, "reopened",
                                       diff or None, reset))
        elif changed and diff:
            events.append(PlannedEvent(old["role_id"], key, "changed", diff, reset))
    return events


def record_events(cur, events: list[PlannedEvent], run_id: int | None,
                  company_id: int) -> int:
    """Insert planned events; resolve role_ids for fresh 'appeared' rows first.
    Runs inside the caller's per-company transaction. Returns rows written.

    company_id is REQUIRED, not optional: dedupe_key is unique per company
    since 0058, so an unscoped lookup can now match several owners' listings
    for one key and this map would attach an event to whichever row came back
    first — another owner's (B-GAE-018). A default would have made every
    existing caller keep the old, wrong behaviour silently.
    """
    if not events:
        return 0
    pending = [e for e in events if e.role_id is None]
    ids: dict[str, int] = {}
    if pending:
        cur.execute(
            "select dedupe_key, role_id from role_listings "
            "where company_id = %s and dedupe_key = any(%s)",
            (company_id, [e.dedupe_key for e in pending]))
        ids = {r["dedupe_key"]: r["role_id"] for r in cur.fetchall()}
    rows = []
    for e in events:
        role_id = e.role_id if e.role_id is not None else ids.get(e.dedupe_key)
        if role_id is None:
            continue   # upsert failed for this key; nothing to attach the event to
        rows.append((role_id, e.event_type,
                     json.dumps(e.changes) if e.changes else None, run_id))
    if rows:
        cur.executemany(
            "insert into listing_events (role_id, event_type, changes, run_id) "
            "values (%s,%s,%s,%s)",
            rows)
    return len(rows)


def record_closed(cur, role_ids: list[int], run_id: int | None) -> int:
    """Log 'closed' events for listings job-rot just closed."""
    if not role_ids:
        return 0
    cur.executemany(
        "insert into listing_events (role_id, event_type, changes, run_id) "
        "values (%s,%s,%s,%s)",
        [(rid, "closed", None, run_id) for rid in role_ids])
    return len(role_ids)


def reset_reads(cur, events: list[PlannedEvent]) -> int:
    """Description changed -> that listing (only) gets re-read by the AI."""
    ids = [e.role_id for e in events if e.reset_read and e.role_id is not None]
    if not ids:
        return 0
    cur.execute(
        "update role_listings set extracted_at = null where role_id = any(%s)",
        (ids,))
    return len(ids)


def history_for_role(cur, owner_id, role_id: int, limit: int = 50) -> list[dict]:
    """One of this owner's listings' life story, most recent first (read-only).

    The longest walk to an owner in the codebase: neither listing_events nor
    role_listings holds one, so the join runs event -> listing -> company.
    Without it a bare role_id was enough to read another owner's salary
    changes, closures and reopenings (Phase 9 task 1b).
    """
    cur.execute(
        "select e.event_id, e.event_type, e.occurred_at, e.changes, e.run_id "
        "from listing_events e "
        "join role_listings r on r.role_id = e.role_id "
        "join target_companies c on c.company_id = r.company_id "
        "where e.role_id = %s and c.owner_id = %s "
        "order by e.occurred_at desc limit %s",
        (role_id, owner_id, limit))
    return cur.fetchall()
