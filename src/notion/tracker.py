"""The Applications tracker — one idempotent Notion card per gated listing.

Each card carries the job, company, status, deadline estimate, sponsor evidence,
queue rank, the tailored CV (as a file link) and the listing URL. The engine's
role_id is stored in a hidden 'Role ID' number property and used as the upsert
key, so re-runs update the same card instead of duplicating it. The reverse read
(applied_role_ids) lets the loop sync 'Applied' back to the engine.
"""
from __future__ import annotations

from dataclasses import dataclass

TRACKER_TITLE = "Applications"
STATUS_TO_APPLY = "To apply"
STATUS_APPLIED = "Applied"
STATUS_SNOOZED = "Snoozed"
STATUS_OPTIONS = (STATUS_TO_APPLY, STATUS_APPLIED, STATUS_SNOOZED)


@dataclass(frozen=True)
class Application:
    role_id: int
    job_title: str
    company: str
    status: str
    listing_url: str
    deadline: str | None = None          # ISO date (estimate ok)
    sponsor_evidence: str = ""
    queue_rank: int | None = None
    cv_url: str | None = None            # link to the rendered .docx


def tracker_schema() -> dict:
    """The Notion database property schema for a fresh Applications tracker."""
    return {
        "Job": {"title": {}},
        "Company": {"rich_text": {}},
        "Status": {"select": {"options": [{"name": s} for s in STATUS_OPTIONS]}},
        "Deadline": {"date": {}},
        "Sponsor evidence": {"rich_text": {}},
        "Queue rank": {"number": {}},
        "CV": {"files": {}},
        "Listing": {"url": {}},
        "Role ID": {"number": {}},
    }


def _rich_text(text: str | None) -> dict:
    return {"rich_text": [{"text": {"content": text or ""}}]}


def application_properties(app: Application) -> dict:
    """Map an Application to Notion page properties (optional fields omitted)."""
    props = {
        "Job": {"title": [{"text": {"content": app.job_title}}]},
        "Company": _rich_text(app.company),
        "Status": {"select": {"name": app.status}},
        "Sponsor evidence": _rich_text(app.sponsor_evidence),
        "Listing": {"url": app.listing_url or None},
        "Role ID": {"number": app.role_id},
    }
    if app.deadline:
        props["Deadline"] = {"date": {"start": app.deadline}}
    if app.queue_rank is not None:
        props["Queue rank"] = {"number": app.queue_rank}
    if app.cv_url:
        props["CV"] = {"files": [{"type": "external", "name": "CV.docx",
                                  "external": {"url": app.cv_url}}]}
    return props


def find_application(client, database_id: str, role_id: int) -> str | None:
    """The page id of the card for this role_id, or None if there isn't one."""
    res = client.query_database(
        database_id, query_filter={"property": "Role ID", "number": {"equals": role_id}})
    results = res.get("results") or []
    return results[0]["id"] if results else None


def upsert_application(client, database_id: str, app: Application) -> dict:
    """Create the card, or update it in place if one already exists (idempotent)."""
    props = application_properties(app)
    page_id = find_application(client, database_id, app.role_id)
    if page_id:
        client.update_page(page_id, props)
        return {"page_id": page_id, "created": False, "role_id": app.role_id}
    res = client.create_page(database_id, props)
    return {"page_id": res.get("id"), "created": True, "role_id": app.role_id}


def applied_role_ids(client, database_id: str) -> list[int]:
    """role_ids of cards the human marked 'Applied' — the sync-back signal."""
    res = client.query_database(
        database_id, query_filter={"property": "Status", "select": {"equals": STATUS_APPLIED}})
    ids: list[int] = []
    for page in res.get("results") or []:
        number = ((page.get("properties") or {}).get("Role ID") or {}).get("number")
        if number is not None:
            ids.append(int(number))
    return ids
