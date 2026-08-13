"""End-to-end CV generation: verified facts in, a truthful tailored .docx out.

Ties the CV pieces together — load confirmed cv_blocks, select/order them for the
listing (assemble), rephrase the facts (phrase, caged Gemini), enforce the truth
gate, and render the ATS-safe .docx. With no Gemini key the phrasing falls back
to verbatim facts, so this runs end-to-end with or without AI. The reusable core
behind both the daily filing stage and the generate_cv MCP tool.
"""
from __future__ import annotations

from dataclasses import dataclass

from cv.assemble import assemble_cv
from cv.blocks import load_cv_blocks
from cv.phrase import phrase_blocks
from cv.render import CvHeader, render_cv
from cv.truth import gate_phrased


@dataclass(frozen=True)
class CvBuild:
    docx: bytes
    blocks: list           # the gated PhrasedBlocks that made the CV
    used: int              # how many blocks were rendered
    fallbacks: int         # how many bullets fell back to the verbatim fact


def load_listing_skills(cur, role_id: int) -> list[str]:
    """The normalised skills a listing asks for (role_skills.skill_norm)."""
    cur.execute(
        "select distinct skill_norm from role_skills "
        "where role_id = %s and skill_norm is not null",
        (role_id,))
    return [r["skill_norm"] for r in cur.fetchall() if r["skill_norm"]]


def load_header(cur, owner_id: str) -> CvHeader:
    """Build the CV header from the owner's profile."""
    cur.execute("select name, contact_email from profiles where profile_id = %s",
                (owner_id,))
    row = cur.fetchone() or {}
    return CvHeader(name=row.get("name") or "", contact=row.get("contact_email") or "")


def generate_cv(cur, owner_id: str, *, job_title: str, listing_skills, header: CvHeader,
                emphasis=(), api_key: str | None = None, client=None,
                max_blocks: int | None = None) -> CvBuild:
    """Assemble → phrase → truth-gate → render one tailored CV for a listing."""
    target = list(dict.fromkeys([*(listing_skills or ()), *(emphasis or ())]))
    blocks = load_cv_blocks(cur, owner_id)
    selected = assemble_cv(blocks, target, max_blocks=max_blocks)
    phrased = phrase_blocks(selected, listing_title=job_title, listing_skills=target,
                            api_key=api_key, client=client)
    gated = gate_phrased(phrased)
    docx = render_cv(header, gated)
    fallbacks = sum(1 for p in gated if p.bullet == p.source_fact)
    return CvBuild(docx=docx, blocks=gated, used=len(gated), fallbacks=fallbacks)
