"""The serve-all CV path (U8): every confirmed fact out, truth gated back.

The founder's call (2026-08-10 serve-all correction): the client AI receives
EVERY confirmed cv_block and selects relevance itself — literal skill
matching hides transferable evidence, and a filtered fact is unknowable to
the client. The engine's skill match survives only as an optional HINT
(skill_hint). The truth gate remains the ceiling — select freely, invent
never: every submitted bullet is verified against ITS block's fact_text and
an untraceable bullet is replaced by the verbatim fact. The ENGINE renders
the .docx (single-column, ATS-safe) — format is engine-owned; the client
writes content, never layout.
"""
from __future__ import annotations

from applyqueue import fetch_job
from cv.blocks import load_cv_blocks
from cv.filing import DEFAULT_CV_DIR, save_cv
from cv.generate import load_header, load_listing_skills
from cv.phrase import PhrasedBlock
from cv.render import render_cv
from cv.truth import trace_bullet

CV_PROMPT_VERSION = "cv-v1"

CV_PROMPT = (
    "You are writing ONE person's CV for ONE job, from their verified career "
    "facts (blocks). Select the blocks most relevant to the job yourself — "
    "freely, including transferable evidence; skill_hint lists the engine's "
    "literal matches and is a hint, never a limit. Write one concise, "
    "ATS-friendly bullet per selected block. Absolute rules (the engine "
    "verifies every bullet against that block's fact_text and replaces an "
    "untraceable bullet with the verbatim fact):\n"
    "- Use ONLY that block's fact_text. Add nothing; merge nothing across "
    "blocks.\n"
    "- Invent no numbers, employers, dates, tools, or skills.\n"
    "- Emphasise what the job asks for, never at the cost of truth.\n"
    "The engine owns the layout and renders the .docx itself — submit "
    "content only, via submit_cv(role_id, cv) in the required shape."
)

REQUIRED_SHAPE = {
    "blocks": [{"block_id": "int — a served block's id",
                "bullet": "string grounded in THAT block's fact_text"}],
}


def serve_cv(cur, owner_id: str, role_id: int) -> dict:
    """The whole hand-over: the job, EVERY confirmed block, the hint."""
    job = fetch_job(cur, owner_id, role_id)
    if job is None:
        return {"outcome": "not_found", "role_id": role_id}
    blocks = load_cv_blocks(cur, owner_id)
    if not blocks:
        return {"outcome": "no_blocks", "role_id": role_id}
    listing_skills = set(load_listing_skills(cur, role_id))
    block_skills = {s for b in blocks for s in b.skill_norms}
    return {
        "outcome": "served",
        "prompt_version": CV_PROMPT_VERSION,
        "prompt": CV_PROMPT,
        "required_shape": REQUIRED_SHAPE,
        "job": {"role_id": job["role_id"],
                "role_title": job.get("role_title"),
                "company_name": job.get("company_name"),
                "jd_full": job.get("jd_full")},
        "blocks": [{"block_id": b.block_id, "kind": b.kind, "title": b.title,
                    "organisation": b.organisation,
                    "date_range": b.date_range, "fact_text": b.fact_text,
                    "skill_norms": b.skill_norms} for b in blocks],
        "skill_hint": sorted(listing_skills & block_skills),
    }


def _validate(submission) -> tuple[list[tuple[int, str]] | None, str | None]:
    """Shape check: {'blocks': [{block_id int, bullet non-empty str}, ...]}."""
    if not isinstance(submission, dict) or \
            not isinstance(submission.get("blocks"), list) or \
            not submission["blocks"]:
        return None, "cv must be {'blocks': [{block_id, bullet}, ...]}"
    wanted: list[tuple[int, str]] = []
    for i, b in enumerate(submission["blocks"]):
        if not isinstance(b, dict) or not isinstance(b.get("block_id"), int) \
                or not isinstance(b.get("bullet"), str) or not b["bullet"].strip():
            return None, f"blocks[{i}] needs an int block_id and a non-empty bullet"
        wanted.append((b["block_id"], b["bullet"].strip()))
    return wanted, None


def accept_cv(cur, owner_id: str, role_id: int, submission, *,
              cv_dir=None) -> dict:
    """Gate the client's selection and render the .docx — the engine's half.

    Unknown/unconfirmed block ids are dropped and reported (never invented);
    each bullet is traced against its own fact_text, the verbatim fact
    replacing anything untraceable. Rendering and saving are engine-owned.
    """
    job = fetch_job(cur, owner_id, role_id)
    if job is None:
        return {"outcome": "not_found", "role_id": role_id}
    wanted, error = _validate(submission)
    if error:
        return {"outcome": "invalid", "role_id": role_id, "error": error}
    by_id = {b.block_id: b for b in load_cv_blocks(cur, owner_id)}
    if not by_id:
        return {"outcome": "no_blocks", "role_id": role_id}

    rejected = [bid for bid, _ in wanted if bid not in by_id]
    phrased: list[PhrasedBlock] = []
    for bid, bullet in wanted:
        block = by_id.get(bid)
        if block is None:
            continue
        ok = trace_bullet(bullet, block.fact_text)
        phrased.append(PhrasedBlock(
            block_id=block.block_id, kind=block.kind, title=block.title,
            organisation=block.organisation, date_range=block.date_range,
            source_fact=block.fact_text,
            bullet=bullet if ok else block.fact_text))
    if not phrased:
        return {"outcome": "invalid", "role_id": role_id,
                "error": "no submitted block_id matches a confirmed block",
                "rejected_block_ids": rejected}

    docx = render_cv(load_header(cur, owner_id), phrased)
    path = save_cv(docx, role_id, cv_dir or DEFAULT_CV_DIR)
    fallbacks = sum(1 for p in phrased if p.bullet == p.source_fact)
    return {"outcome": "rendered", "role_id": role_id, "docx": docx,
            "cv_path": str(path), "used": len(phrased),
            "fallbacks": fallbacks, "rejected_block_ids": rejected}
