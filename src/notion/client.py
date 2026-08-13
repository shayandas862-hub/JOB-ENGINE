"""A thin Notion REST client — just the calls the tracker needs.

Auth is a Bearer integration token plus the required Notion-Version header. The
token lives only in the request header; no method ever returns it. Methods raise
on a non-2xx response (requests.HTTPError) so the caller can isolate a Notion
outage the way the pipeline isolates any stage failure.
"""
from __future__ import annotations

import requests

NOTION_BASE = "https://api.notion.com/v1"
# Pinned, widely-supported version. The 2025-09-03 "data sources" model is a
# later upgrade (decision-log); this stays on the stable database/page endpoints.
NOTION_VERSION = "2022-06-28"
TIMEOUT = 20


class NotionClient:
    def __init__(self, token: str, *, version: str = NOTION_VERSION,
                 session: requests.Session | None = None, base: str = NOTION_BASE):
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Notion-Version": version,
            "Content-Type": "application/json",
        }
        self._session = session or requests.Session()
        self._base = base

    def _request(self, method: str, path: str, body: dict | None = None) -> dict:
        resp = self._session.request(method, f"{self._base}{path}",
                                     headers=self._headers, json=body, timeout=TIMEOUT)
        resp.raise_for_status()
        return resp.json()

    def query_database(self, database_id: str, *, query_filter: dict | None = None) -> dict:
        body = {"filter": query_filter} if query_filter else {}
        return self._request("POST", f"/databases/{database_id}/query", body)

    def create_page(self, database_id: str, properties: dict) -> dict:
        return self._request("POST", "/pages",
                             {"parent": {"database_id": database_id}, "properties": properties})

    def update_page(self, page_id: str, properties: dict) -> dict:
        return self._request("PATCH", f"/pages/{page_id}", {"properties": properties})

    def create_database(self, parent_page_id: str, title: str, properties: dict) -> dict:
        return self._request("POST", "/databases", {
            "parent": {"type": "page_id", "page_id": parent_page_id},
            "title": [{"text": {"content": title}}],
            "properties": properties,
        })
