"""File a gated listing: generate its CV, save the .docx, upsert the Notion card.

Reuses the CV generator and the Notion tracker. The .docx is written to a local
CV directory; when a public base URL is configured the card links to it, so the
attachment lights up once the CVs are hosted (Phase 8). sync_applied is the
reverse path: cards a human marked 'Applied' in Notion are marked applied in the
engine on the next run.
"""
from __future__ import annotations

from pathlib import Path

from cv.generate import generate_cv, load_header, load_listing_skills
from notion.tracker import STATUS_TO_APPLY, Application, applied_role_ids, upsert_application

# Where rendered CVs are written (served from here once hosting lands, Phase 8).
DEFAULT_CV_DIR = Path(__file__).resolve().parents[2] / "ops" / "cvs"


def save_cv(docx: bytes, role_id: int, cv_dir) -> Path:
    directory = Path(cv_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"cv-{role_id}.docx"
    path.write_bytes(docx)
    return path


def _iso(deadline) -> str | None:
    if not deadline:
        return None
    return deadline.isoformat() if hasattr(deadline, "isoformat") else str(deadline)


def _sponsor_evidence(listing) -> str:
    wall = listing.get("salary_wall")
    parts = [listing.get("sponsor_signal"), listing.get("sponsor_confidence"),
             f"wall: {wall}" if wall else None]
    seen, out = set(), []
    for p in parts:                          # de-dupe (signal/confidence often coincide)
        if p and p not in seen:
            seen.add(p)
            out.append(p)
    return " · ".join(out)


def build_application(listing, *, cv_url=None, queue_rank=None,
                      status: str = STATUS_TO_APPLY) -> Application:
    """Map a queue listing (+ its CV link and rank) to a tracker Application."""
    return Application(
        role_id=listing["role_id"],
        job_title=listing.get("role_title") or "",
        company=listing.get("company_name") or "",
        status=status,
        listing_url=listing.get("role_url") or "",
        deadline=_iso(listing.get("deadline")),
        sponsor_evidence=_sponsor_evidence(listing),
        queue_rank=queue_rank,
        cv_url=cv_url,
    )


def file_application(cur, owner_id, listing, *, settings, client, cv_dir,
                     api_key: str | None = None, cv_url_base: str | None = None,
                     queue_rank=None, emphasis=()) -> dict:
    """Generate the CV, save it, and create/refresh the listing's Notion card."""
    role_id = listing["role_id"]
    skills = load_listing_skills(cur, role_id)
    header = load_header(cur, owner_id)
    build = generate_cv(cur, owner_id, job_title=listing.get("role_title") or "",
                        listing_skills=skills, header=header, emphasis=emphasis,
                        api_key=api_key or settings.gemini_api_key)
    path = save_cv(build.docx, role_id, cv_dir)
    cv_url = f"{cv_url_base.rstrip('/')}/cv-{role_id}.docx" if cv_url_base else None
    app = build_application(listing, cv_url=cv_url, queue_rank=queue_rank)
    result = upsert_application(client, settings.notion_database_id, app)
    return {"role_id": role_id, "page_id": result["page_id"], "created": result["created"],
            "cv_path": str(path), "used": build.used, "fallbacks": build.fallbacks}


def sync_applied(cur, owner_id, client, database_id: str) -> list[int]:
    """Mark applied every listing whose Notion card the human set to 'Applied'.

    Owner-scoped (Phase 9 task 1b): a Notion board belongs to one owner, so a
    card naming a role_id that is not theirs stamps nothing and is not counted.
    """
    from applyqueue import mark_applied

    synced: list[int] = []
    for role_id in applied_role_ids(client, database_id):
        if mark_applied(cur, owner_id, role_id) is not None:
            synced.append(role_id)
    return synced


def _notion_url(page_or_db_id: str | None) -> str | None:
    if not page_or_db_id:
        return None
    return f"https://www.notion.so/{page_or_db_id.replace('-', '')}"


def run_filing_stage(cur, settings, *, owner_id, cv_dir=None, client=None,
                     cv_url_base=None) -> dict:
    """Daily stage for ONE owner: sync 'Applied' back, then file a card per
    gate-passing listing.

    Files the same set the nudge will send (High fit + positive sponsor, un-nudged),
    ranked. Skipped cleanly when Notion isn't configured; one bad listing never
    sinks the stage. Returns a summary and the board URL for the nudge footer.

    `owner_id` is required (B-GAE-027): this used to resolve the first profile
    and select every owner's listings, so a second owner's roles would have
    been filed as cards on the first owner's board, with CVs built from the
    first owner's confirmed blocks.
    """
    from notify.nudges import ELIGIBLE_SQL, select_nudges

    if not settings.notion_ready:
        return {"skipped": True, "filed": 0, "synced": 0,
                "line": "filing: skipped — Notion not configured", "board_url": None}

    # There is exactly ONE Notion credential in the environment and it opens
    # exactly one person's board. Scoping the row selection stops this stage
    # mixing owners, but it cannot make a shared board private — so filing
    # runs only for the owner that credential belongs to, and refuses loudly
    # for anyone else rather than writing their cards somewhere they cannot
    # see them. Per-owner Notion (profiles.notion_token_ref, unused today) is
    # task 4's onboarding work; this is the honest half of the fix.
    from criteria.loader import default_profile_id

    if str(owner_id) != str(default_profile_id(cur)):
        return {"skipped": True, "filed": 0, "synced": 0,
                "line": "filing: skipped — the configured Notion board belongs "
                        "to another owner (per-owner Notion is task 4)",
                "board_url": None}

    if client is None:
        from notion.client import NotionClient
        client = NotionClient(settings.notion_token)
    owner = owner_id
    synced = sync_applied(cur, owner, client, settings.notion_database_id)

    cur.execute(ELIGIBLE_SQL, (owner,))
    picks = select_nudges(cur.fetchall())
    filed = 0
    for rank, listing in enumerate(picks, start=1):
        try:
            file_application(cur, owner, listing, settings=settings, client=client,
                             cv_dir=cv_dir or DEFAULT_CV_DIR, cv_url_base=cv_url_base,
                             queue_rank=rank)
            filed += 1
        except Exception:                    # a single bad listing is skipped, not fatal
            continue
    return {"skipped": False, "filed": filed, "synced": len(synced),
            "line": f"filing: {filed} card(s), {len(synced)} applied synced",
            "board_url": _notion_url(settings.notion_database_id)}


def regenerate_cv_card(cur, owner_id, role_id: int, *, emphasis=(), cv_dir=None) -> dict:
    """Re-tailor and re-file one listing's CV (the generate_cv MCP tool's logic)."""
    from applyqueue import fetch_job
    from config import get_settings

    settings = get_settings()
    if not settings.notion_ready:
        return {"role_id": role_id, "filed": False, "reason": "Notion not configured"}
    listing = fetch_job(cur, owner_id, role_id)
    if not listing:
        return {"role_id": role_id, "filed": False, "reason": "unknown role_id"}

    from notion.client import NotionClient
    out = file_application(cur, owner_id, listing, settings=settings,
                           client=NotionClient(settings.notion_token),
                           cv_dir=cv_dir or DEFAULT_CV_DIR, emphasis=emphasis)
    return {"role_id": role_id, "filed": True, "created": out["created"],
            "card_url": _notion_url(out.get("page_id")),
            "blocks_used": out["used"], "fallbacks": out["fallbacks"]}
