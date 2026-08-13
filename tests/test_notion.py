"""Tests for src/notion — the application-tracker client, against a mocked API.

The engine files to Notion headless (direct REST, not the Claude MCP). We prove
the auth headers, the property mapping, idempotent upsert (query -> update, or
create when absent), and the 'Applied' sync-back read. No live calls — every
Notion endpoint is mocked with `responses`.
"""
from __future__ import annotations

import json

import requests
import responses

QUERY = "https://api.notion.com/v1/databases/db-1/query"
PAGES = "https://api.notion.com/v1/pages"


def _client():
    from notion.client import NotionClient
    return NotionClient("ntn_secret", session=requests.Session())


def _app(role_id=917, **over):
    from notion.tracker import Application
    base = dict(role_id=role_id, job_title="AI Engineer", company="Acme AI Ltd",
                status="To apply", listing_url="https://boards.greenhouse.io/acme/jobs/1",
                deadline="2026-08-01", sponsor_evidence="register-only (A-rated)",
                queue_rank=3, cv_url="https://files/cv-917.docx")
    base.update(over)
    return Application(**base)


# ---- client ----------------------------------------------------------------

@responses.activate
def test_client_sends_bearer_token_and_version_header():
    responses.add(responses.POST, QUERY, json={"results": []}, status=200)
    _client().query_database("db-1")
    req = responses.calls[0].request
    assert req.headers["Authorization"] == "Bearer ntn_secret"
    assert req.headers["Notion-Version"]                 # a version is always sent


# ---- property mapping ------------------------------------------------------

def test_application_properties_map_to_notion_shapes():
    from notion.tracker import application_properties
    props = application_properties(_app())
    assert props["Job"]["title"][0]["text"]["content"] == "AI Engineer"
    assert props["Company"]["rich_text"][0]["text"]["content"] == "Acme AI Ltd"
    assert props["Status"]["select"]["name"] == "To apply"
    assert props["Role ID"]["number"] == 917            # the idempotency key
    assert props["Deadline"]["date"]["start"] == "2026-08-01"
    assert props["Queue rank"]["number"] == 3
    assert props["Listing"]["url"].startswith("https://")
    assert props["CV"]["files"][0]["external"]["url"] == "https://files/cv-917.docx"


def test_optional_fields_are_omitted_when_absent():
    from notion.tracker import application_properties
    props = application_properties(_app(deadline=None, queue_rank=None, cv_url=None))
    assert "Deadline" not in props and "Queue rank" not in props and "CV" not in props
    assert "Job" in props and "Role ID" in props        # the required ones stay


# ---- idempotent upsert -----------------------------------------------------

@responses.activate
def test_upsert_creates_a_card_when_none_exists():
    responses.add(responses.POST, QUERY, json={"results": []}, status=200)   # not found
    responses.add(responses.POST, PAGES, json={"id": "page-new"}, status=200)
    from notion.tracker import upsert_application

    out = upsert_application(_client(), "db-1", _app())

    assert out == {"page_id": "page-new", "created": True, "role_id": 917}
    create_body = json.loads(responses.calls[1].request.body)
    assert create_body["parent"]["database_id"] == "db-1"
    assert create_body["properties"]["Role ID"]["number"] == 917


@responses.activate
def test_upsert_updates_the_existing_card_and_never_duplicates():
    responses.add(responses.POST, QUERY,
                  json={"results": [{"id": "page-existing"}]}, status=200)   # found
    responses.add(responses.PATCH, "https://api.notion.com/v1/pages/page-existing",
                  json={"id": "page-existing"}, status=200)
    from notion.tracker import upsert_application

    out = upsert_application(_client(), "db-1", _app())

    assert out == {"page_id": "page-existing", "created": False, "role_id": 917}
    # exactly one query + one PATCH, and NO create POST to /pages
    assert not any(c.request.url == PAGES for c in responses.calls)
    assert responses.calls[0].request.url == QUERY


@responses.activate
def test_query_uses_a_role_id_filter():
    responses.add(responses.POST, QUERY, json={"results": []}, status=200)
    from notion.tracker import find_application
    find_application(_client(), "db-1", 917)
    body = json.loads(responses.calls[0].request.body)
    assert body["filter"] == {"property": "Role ID", "number": {"equals": 917}}


# ---- 'Applied' sync-back ----------------------------------------------------

@responses.activate
def test_applied_role_ids_reads_cards_marked_applied():
    responses.add(responses.POST, QUERY, json={"results": [
        {"id": "p1", "properties": {"Role ID": {"number": 917}}},
        {"id": "p2", "properties": {"Role ID": {"number": 42}}},
    ]}, status=200)
    from notion.tracker import applied_role_ids

    ids = applied_role_ids(_client(), "db-1")

    assert set(ids) == {917, 42}
    body = json.loads(responses.calls[0].request.body)
    assert body["filter"] == {"property": "Status", "select": {"equals": "Applied"}}


# ---- database schema (for one-time creation) -------------------------------

def test_tracker_schema_declares_every_tracked_property():
    from notion.tracker import tracker_schema
    schema = tracker_schema()
    assert "title" in schema["Job"]                     # the title property
    for name in ("Company", "Status", "Deadline", "Sponsor evidence",
                 "Queue rank", "CV", "Listing", "Role ID"):
        assert name in schema
