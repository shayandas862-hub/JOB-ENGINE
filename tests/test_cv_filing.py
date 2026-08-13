"""Tests for src/cv/filing — generate a CV, save it, file/refresh the Notion card,
and sync 'Applied' back. Notion is a fake client; the CV is written to a tmp dir;
no Gemini key so phrasing is the verbatim-fact fallback.
"""
from __future__ import annotations

import pytest

OWNER_A = "11111111-1111-4111-a111-111111111111"


class RoutingCursor:
    def __init__(self, cv_blocks=None, skills=None, profile=None):
        self._cv, self._skills, self._profile = cv_blocks or [], skills or [], profile
        self.executed = []
        self._pending = []

    def execute(self, sql, params=None):
        s = " ".join(sql.split()).lower()
        self.executed.append((s, params))
        if "from cv_blocks" in s:
            self._pending = list(self._cv)
        elif "from role_skills" in s:
            self._pending = list(self._skills)
        elif "from profiles" in s:
            self._pending = [self._profile] if self._profile else []
        elif "update role_listings" in s:
            self._pending = [{"role_title": "AI Engineer"}]
        else:
            self._pending = []

    def fetchall(self):
        return list(self._pending)

    def fetchone(self):
        return self._pending[0] if self._pending else None


class FakeNotion:
    """Minimal Notion client: no existing card, records create/update/query."""

    def __init__(self, existing=None, applied=None):
        self.existing, self.applied = existing, applied or []
        self.created, self.updated, self.queries = [], [], []

    def query_database(self, database_id, *, query_filter=None):
        self.queries.append(query_filter)
        if query_filter and query_filter.get("property") == "Status":
            return {"results": [{"id": f"p{r}", "properties": {"Role ID": {"number": r}}}
                                for r in self.applied]}
        return {"results": [{"id": self.existing}] if self.existing else []}

    def create_page(self, database_id, properties):
        self.created.append(properties)
        return {"id": "page-new"}

    def update_page(self, page_id, properties):
        self.updated.append((page_id, properties))
        return {"id": page_id}


def _settings():
    from config import Settings
    return Settings(database_url="x", gemini_api_key="", notion_token="ntn",
                    notion_database_id="db-1")


BLOCKS = [{"block_id": 1, "kind": "role", "title": "Analyst", "organisation": "Acme",
           "date_range": "2021-2023", "fact_text": "Led analytics, cutting time 40%.",
           "skill_norms": ["sql"], "sort_hint": 0}]
LISTING = {"role_id": 917, "role_title": "AI Engineer", "company_name": "Acme AI Ltd",
           "role_url": "https://x/1", "deadline": "2026-08-01", "salary_wall": "clears",
           "sponsor_signal": "register-only", "sponsor_confidence": "register-only"}


def test_build_application_maps_a_queue_listing():
    from cv.filing import build_application
    app = build_application(LISTING, cv_url="https://f/cv-917.docx", queue_rank=2)
    assert app.role_id == 917 and app.job_title == "AI Engineer"
    assert app.company == "Acme AI Ltd" and app.queue_rank == 2
    assert app.deadline == "2026-08-01" and app.cv_url.endswith("cv-917.docx")
    assert "register-only" in app.sponsor_evidence and "clears" in app.sponsor_evidence


def test_file_application_generates_saves_and_files(tmp_path):
    from cv.filing import file_application
    cur = RoutingCursor(cv_blocks=BLOCKS, skills=[{"skill_norm": "sql"}],
                        profile={"name": "Shayan", "contact_email": "s@x.com"})
    notion = FakeNotion()

    out = file_application(cur, "p-1", LISTING, settings=_settings(), client=notion,
                          cv_dir=tmp_path, cv_url_base="https://files")

    assert out["role_id"] == 917 and out["created"] is True and out["page_id"] == "page-new"
    assert (tmp_path / "cv-917.docx").exists()                    # the .docx was saved
    assert len(notion.created) == 1                               # one card filed
    assert notion.created[0]["Role ID"]["number"] == 917
    assert notion.created[0]["CV"]["files"][0]["external"]["url"].endswith("cv-917.docx")


def test_file_application_updates_an_existing_card(tmp_path):
    from cv.filing import file_application
    cur = RoutingCursor(cv_blocks=BLOCKS, skills=[], profile={"name": "S", "contact_email": ""})
    notion = FakeNotion(existing="page-old")
    out = file_application(cur, "p-1", LISTING, settings=_settings(), client=notion, cv_dir=tmp_path)
    assert out["created"] is False and out["page_id"] == "page-old"
    assert notion.updated and not notion.created                  # idempotent: updated, not duplicated


def test_sync_applied_marks_each_applied_listing():
    from cv.filing import sync_applied
    cur = RoutingCursor()
    notion = FakeNotion(applied=[917, 42])
    synced = sync_applied(cur, OWNER_A, notion, "db-1")
    assert set(synced) == {917, 42}
    marks = [p for s, p in cur.executed if "update role_listings" in s]
    assert len(marks) == 2                                        # one mark_applied per card


# ---- the daily filing stage ------------------------------------------------

class StageCursor:
    def __init__(self, eligible, profile_id="p-1"):
        self.eligible, self.profile_id, self.executed, self._p = eligible, profile_id, [], []

    def execute(self, sql, params=None):
        s = " ".join(sql.split()).lower()
        self.executed.append((s, params))
        self._p = list(self.eligible) if "from v_apply_queue" in s else (
            [{"profile_id": self.profile_id}] if "from profiles" in s else [])

    def fetchall(self):
        return list(self._p)

    def fetchone(self):
        return self._p[0] if self._p else None


def _eligible(role_id, fit="High", signal="register-only"):
    return {"role_id": role_id, "fit_rank": fit, "sponsor_signal": signal, "role_title": "R",
            "company_name": "C", "role_url": "u", "salary_wall": "clears",
            "deadline": None, "deadline_source": None}


def test_run_filing_stage_files_eligible_ranked_and_syncs(monkeypatch):
    from cv import filing
    monkeypatch.setattr(filing, "sync_applied", lambda cur, owner, c, db: [99])
    filed = []
    monkeypatch.setattr(filing, "file_application",
                        lambda cur, owner, listing, **k: filed.append((listing["role_id"], k["queue_rank"]))
                        or {"page_id": "p", "created": True})
    cur = StageCursor([_eligible(1), _eligible(2, fit="Low", signal="weak"), _eligible(3)])

    out = filing.run_filing_stage(cur, _settings(), owner_id="p-1",
                                  cv_dir="/tmp/x", client=object())

    assert out["filed"] == 2 and out["synced"] == 1              # only the two High+positive
    assert filed == [(1, 1), (3, 2)]                             # ranked in queue order
    assert "notion.so" in out["board_url"]


def test_run_filing_stage_skips_cleanly_without_notion():
    from config import Settings
    from cv.filing import run_filing_stage
    out = run_filing_stage(StageCursor([]), Settings(database_url="x", gemini_api_key=""),
                           owner_id="p-1", cv_dir="/tmp/x")
    assert out["skipped"] is True and out["filed"] == 0


def test_filing_refuses_to_write_another_owners_cards_to_the_configured_board(monkeypatch):
    # The half of B-GAE-027 that scoping alone cannot fix. There is ONE Notion
    # credential in the environment and it opens ONE person's board, so a
    # second owner's cards would land somewhere they can never read them —
    # on the first owner's board, with the first owner's CVs attached. Until
    # per-owner Notion exists (task 4, profiles.notion_token_ref) the honest
    # behaviour is to refuse and say why, not to file into the wrong place.
    from cv import filing
    monkeypatch.setattr(filing, "sync_applied",
                        lambda *a: pytest.fail("synced another owner's board"))
    monkeypatch.setattr(filing, "file_application",
                        lambda *a, **k: pytest.fail("filed another owner's card"))

    out = filing.run_filing_stage(StageCursor([_eligible(1)], profile_id="p-1"),
                                  _settings(), owner_id="p-2",
                                  cv_dir="/tmp/x", client=object())

    assert out["skipped"] is True and out["filed"] == 0
    assert "another owner" in out["line"]
    assert out["board_url"] is None      # and no footer link to it either


def test_run_filing_stage_isolates_a_bad_listing(monkeypatch):
    from cv import filing
    monkeypatch.setattr(filing, "sync_applied", lambda *a: [])

    def boom(cur, owner, listing, **k):
        if listing["role_id"] == 1:
            raise RuntimeError("gemini down")
        return {"page_id": "p", "created": True}
    monkeypatch.setattr(filing, "file_application", boom)
    out = filing.run_filing_stage(StageCursor([_eligible(1), _eligible(3)]),
                                  _settings(), owner_id="p-1", cv_dir="/tmp/x",
                                  client=object())
    assert out["filed"] == 1                                     # role 3 filed; role 1 skipped


# ---- the generate_cv MCP tool's logic --------------------------------------

def test_regenerate_cv_card_refiles_with_emphasis(monkeypatch):
    from cv import filing
    monkeypatch.setattr("config.get_settings", lambda *a, **k: _settings())
    monkeypatch.setattr("applyqueue.fetch_job",
                        lambda cur, owner, rid: {"role_id": rid, "role_title": "AI Engineer",
                                          "company_name": "C", "role_url": "u", "deadline": None})
    seen = {}
    monkeypatch.setattr(filing, "file_application",
                        lambda cur, owner, listing, **k: seen.update(emphasis=k.get("emphasis"))
                        or {"page_id": "abc-def", "created": False, "used": 3, "fallbacks": 1})

    out = filing.regenerate_cv_card(None, "p-1", 917, emphasis=["ml"])

    assert out["filed"] is True and out["blocks_used"] == 3 and out["created"] is False
    assert out["card_url"] == "https://www.notion.so/abcdef"
    assert seen["emphasis"] == ["ml"]                           # the re-tailor hint reached generation


def test_regenerate_cv_card_reports_unknown_role(monkeypatch):
    from cv import filing
    monkeypatch.setattr("config.get_settings", lambda *a, **k: _settings())
    monkeypatch.setattr("applyqueue.fetch_job", lambda cur, owner, rid: None)
    out = filing.regenerate_cv_card(None, "p-1", 999)
    assert out["filed"] is False and "unknown" in out["reason"]
