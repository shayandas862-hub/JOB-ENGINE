"""Central configuration: loads secrets from .env and validates them on demand.

Secrets never live in code. Validation is lazy (only when a secret is actually
needed) so that tests and offline tooling can import this module without a .env.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the project root (parent of src/), regardless of CWD.
_ENV_PATH = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(_ENV_PATH if _ENV_PATH.exists() else None)


@dataclass(frozen=True)
class Settings:
    database_url: str
    gemini_api_key: str
    # Aggregator keys (Phase 6). Blank = that source is simply skipped, the same
    # way a blank Gemini key falls back — discovery degrades, it never crashes.
    adzuna_app_id: str = ""
    adzuna_app_key: str = ""
    reed_api_key: str = ""
    # Notion filing (Phase 7). Token blank = filing is skipped; the database id
    # names the pre-created Applications tracker, the parent page is for creating it.
    notion_token: str = ""
    notion_database_id: str = ""
    notion_parent_page_id: str = ""
    # National company registry (Phase 7.5; UK plug-in = Companies House).
    # Blank = the census sweep runs probe-only and registry enrichment is skipped.
    companies_house_api_key: str = ""

    @property
    def adzuna_ready(self) -> bool:
        return bool(self.adzuna_app_id and self.adzuna_app_key)

    @property
    def reed_ready(self) -> bool:
        return bool(self.reed_api_key)

    @property
    def notion_ready(self) -> bool:
        return bool(self.notion_token and self.notion_database_id)

    @property
    def ch_ready(self) -> bool:
        return bool(self.companies_house_api_key)


def get_settings(require_gemini: bool = False) -> Settings:
    """Return validated settings. Raises a clear error if a required secret is missing."""
    database_url = os.getenv("DATABASE_URL", "").strip()
    gemini_api_key = os.getenv("GEMINI_API_KEY", "").strip()

    if not database_url:
        raise RuntimeError(
            "DATABASE_URL is not set. Copy .env.example to .env and fill it in."
        )
    if require_gemini and not gemini_api_key:
        raise RuntimeError(
            "GEMINI_API_KEY is not set (needed for reading job descriptions)."
        )
    return Settings(
        database_url=database_url,
        gemini_api_key=gemini_api_key,
        adzuna_app_id=os.getenv("ADZUNA_APP_ID", "").strip(),
        adzuna_app_key=os.getenv("ADZUNA_APP_KEY", "").strip(),
        reed_api_key=os.getenv("REED_API_KEY", "").strip(),
        notion_token=os.getenv("NOTION_TOKEN", "").strip(),
        notion_database_id=os.getenv("NOTION_DATABASE_ID", "").strip(),
        notion_parent_page_id=os.getenv("NOTION_PARENT_PAGE_ID", "").strip(),
        companies_house_api_key=os.getenv("COMPANIES_HOUSE_API_KEY", "").strip(),
    )
