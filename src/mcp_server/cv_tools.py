"""The CV tools (task 0 / U8 + U8b) — thin skins over cv.serve_all/cv.blocks.

serve_cv hands the client AI the job + EVERY confirmed fact + the versioned
cv-v1 prompt (server-side DATA — a client can never override it); submit_cv
returns the written CV through the deterministic truth gate, and the ENGINE
renders and saves the .docx. The U8b writer quartet is the fact base's own
door: add_cv_block DRAFTS (a client proposes, only the owner confirms),
list/confirm/retire complete the loop — retire is a stamp, never a delete.
AI decides relevance; code decides truth; the owner decides facts.
"""
from __future__ import annotations

from fastmcp import FastMCP

from audit import record as _audit
from cv.amend import amend_cv_block as _amend_block
from cv.blocks import add_cv_block as _add_block
from cv.blocks import confirm_cv_block as _confirm_block
from cv.blocks import list_cv_blocks as _list_blocks
from cv.blocks import retire_cv_block as _retire_block
from cv.mirror import build_mirror as _mirror
from cv.serve_all import accept_cv as _accept
from cv.serve_all import serve_cv as _serve
from mcp_server.annotations import READ, writes
from mcp_server.contract import envelope_schema, with_next

# M4 typed results (0013 §6): outcome is the one always-present key — the
# rest is outcome-dependent and stays additive.
_SERVE_RESULT = {
    "type": "object",
    "properties": {"outcome": {"type": "string"},
                   "prompt_version": {"type": "string"},
                   "prompt": {"type": "string"},
                   "required_shape": {"type": "object"},
                   "job": {"type": "object"},
                   "blocks": {"type": "array"},
                   "skill_hint": {"type": "array"}},
    "required": ["outcome"],
    "additionalProperties": True,
}
_SUBMIT_RESULT = {
    "type": "object",
    "properties": {"outcome": {"type": "string"},
                   "cv_path": {"type": "string"},
                   "used": {"type": "integer"},
                   "fallbacks": {"type": "integer"},
                   "rejected_block_ids": {"type": "array"}},
    "required": ["outcome"],
    "additionalProperties": True,
}
from mcp_server.identity import current_owner as _owner
from mcp_server.session import scoped_conn as get_conn


def register(mcp: FastMCP) -> None:
    """Hang the CV tools on the server."""

    @mcp.tool(annotations=READ, output_schema=envelope_schema(_SERVE_RESULT))
    def serve_cv(role_id: int) -> dict:
        """What: everything needed to write one job's CV — the job (title,
        company, full JD), EVERY confirmed fact block (never filtered:
        transferable evidence is yours to spot), the engine's literal matches
        as skill_hint (a hint, never a limit), and the versioned cv-v1 prompt.
        When: the owner wants a tailored CV for a queue listing.
        Returns: {outcome, prompt_version, prompt, required_shape, job,
        blocks, skill_hint} — no_blocks means no facts are confirmed yet.
        Next: write the CV per the prompt, then submit_cv(role_id, cv)."""
        with get_conn() as conn, conn.cursor() as cur:
            result = _serve(cur, _owner(cur), role_id)
        if result["outcome"] == "served":
            return with_next(
                result, state=f"{len(result['blocks'])} fact blocks served",
                call="submit_cv",
                why="write the CV from the served facts and submit it")
        if result["outcome"] == "no_blocks":
            return with_next(result, state="no confirmed facts yet",
                             call="daily_brief",
                             why="the owner must confirm cv_blocks first")
        return with_next(result, state="unknown role_id",
                         call="get_apply_queue", why="pick a real listing")

    @mcp.tool(annotations=writes(),
              output_schema=envelope_schema(_SUBMIT_RESULT))
    def submit_cv(role_id: int, cv: dict,
                  client_label: str = "user-ai") -> dict:
        """What: submit the written CV for verification and rendering — every
        bullet is traced against its own block's fact_text (an untraceable
        bullet is replaced by the verbatim fact; unknown blocks are dropped
        and reported), then the ENGINE renders the ATS-safe .docx. Audited.
        When: after serve_cv, with the client-written selection.
        Returns: {outcome, cv_path, used, fallbacks, rejected_block_ids} —
        never the bytes.
        Next: mark_applied(role_id) once the human actually applies."""
        with get_conn() as conn, conn.cursor() as cur:
            result = _accept(cur, _owner(cur), role_id, cv)
            _audit(cur, "submit_cv",
                   {"role_id": role_id, "client_label": client_label,
                    "blocks_submitted": len((cv or {}).get("blocks") or [])},
                   {"outcome": result["outcome"],
                    "used": result.get("used"),
                    "fallbacks": result.get("fallbacks"),
                    "rejected": result.get("rejected_block_ids")})
        result.pop("docx", None)          # bytes never ride the wire
        if result["outcome"] == "rendered":
            return with_next(
                result,
                state=(f"rendered: {result['used']} bullets, "
                       f"{result['fallbacks']} fell back to the fact"),
                call="mark_applied",
                why="record it once the human actually applies")
        return with_next(result, state=result["outcome"], call="serve_cv",
                         why="re-serve the facts and try again")

    @mcp.tool(annotations=writes())
    def add_cv_block(kind: str, fact_text: str, title: str | None = None,
                     organisation: str | None = None,
                     date_range: str | None = None,
                     skill_norms: list[str] | None = None,
                     client_label: str = "user-ai") -> dict:
        """What: propose ONE new fact about the owner's life and work as a
        DRAFT — kind is role | achievement | skill_evidence | education;
        fact_text is the statement every CV bullet is traced against.
        Experience outside paid work often carries the strongest transferable
        evidence — record it on the same footing. Always unconfirmed: you
        propose, only the owner confirms. Audited.
        When: the owner tells you something true the fact base lacks.
        Returns: {block_id, confirmed: false}.
        Next: confirm_cv_block(block_id) once the OWNER approves the exact
        wording — never on your own judgement."""
        with get_conn() as conn, conn.cursor() as cur:
            result = _add_block(cur, _owner(cur), kind=kind,
                                fact_text=fact_text, title=title,
                                organisation=organisation,
                                date_range=date_range,
                                skill_norms=skill_norms, source="mcp")
            _audit(cur, "add_cv_block",
                   {"kind": kind, "client_label": client_label},
                   {"block_id": result["block_id"], "confirmed": False})
        return with_next(result, state="draft written",
                         call="confirm_cv_block",
                         why="the owner approves the wording, then confirm")

    @mcp.tool(annotations=READ)
    def list_cv_blocks() -> dict:
        """What: the owner's whole fact base, drafts included (confirmed rides
        on every row) so drafts can be shown for approval. Retired blocks
        never appear.
        When: reviewing the fact base, or showing the owner a draft.
        Returns: {blocks: [...]} with confirmed true/false per block.
        Next: confirm_cv_block for an approved draft, retire_cv_block for one
        the owner no longer wants served."""
        with get_conn() as conn, conn.cursor() as cur:
            rows = _list_blocks(cur, _owner(cur))
        drafts = sum(1 for r in rows if not r.get("confirmed"))
        return with_next({"blocks": rows},
                         state=f"{len(rows)} blocks, {drafts} draft(s)",
                         call="confirm_cv_block" if drafts else "serve_cv",
                         why="confirm approved drafts" if drafts
                         else "the fact base is all confirmed — write a CV")

    @mcp.tool(annotations=writes(idempotent=False))
    def amend_cv_block(block_id: int, fact_text: str,
                       kind: str | None = None, title: str | None = None,
                       organisation: str | None = None,
                       date_range: str | None = None,
                       skill_norms: list[str] | None = None,
                       client_label: str = "user-ai") -> dict:
        """What: correct a fact in ONE audited step — the old block is stamped
        retired (its wording is never rewritten) and a corrected DRAFT is
        written linked to it. Omitted fields are inherited, so a typo fix need
        only send fact_text.
        When: the owner says a recorded fact is wrong. Not for a NEW fact —
        that is add_cv_block.
        Returns: {outcome: amended|not_found, block_id, retired_block_id}.
        Next: confirm_cv_block — the correction is a draft until the owner
        approves it."""
        with get_conn() as conn, conn.cursor() as cur:
            result = _amend_block(
                cur, _owner(cur), block_id, fact_text=fact_text, kind=kind,
                title=title, organisation=organisation, date_range=date_range,
                skill_norms=skill_norms, source="mcp")
            _audit(cur, "amend_cv_block",
                   {"block_id": block_id, "client_label": client_label},
                   result)
        if result["outcome"] == "not_found":
            return with_next(result, state="no such block for this owner",
                             call="list_cv_blocks",
                             why="find the block_id to correct")
        return with_next(result, state="corrected draft written",
                         call="confirm_cv_block",
                         why="the owner approves the new wording, then confirm")

    @mcp.tool(annotations=READ)
    def describe_the_owner() -> dict:
        """What: the fact base read back as understanding — counts by kind,
        which skills a CV can PROVE (each citing the block that proves it),
        which it cannot, and how many are evidenced outside paid work.
        Nothing is stored: it is re-formed from the rows on every call.
        When: after intake, before a CV, or when the owner asks what the
        system has on them. Show them the unprovable list — the truth gate
        declines to put those in a CV.
        Returns: {facts, skills, provable, unprovable, coverage, headline}.
        Next: add_cv_block to give an unprovable skill its evidence."""
        with get_conn() as conn, conn.cursor() as cur:
            mirror = _mirror(cur, _owner(cur))
        missing = mirror["skills"]["unevidenced"]
        return with_next(
            mirror, state=mirror["headline"],
            call="add_cv_block" if missing else "serve_cv",
            why=f"{missing} skill(s) have no fact behind them — a CV cannot "
                "claim them" if missing
                else "every skill is evidenced — write a CV")

    @mcp.tool(annotations=writes(idempotent=True))
    def confirm_cv_block(block_id: int,
                         client_label: str = "user-ai") -> dict:
        """What: record the OWNER'S approval of a draft — the block becomes a
        fact the CV path may serve. Only call after the owner explicitly
        approved the exact wording. Audited.
        When: the owner said yes to a draft from add_cv_block.
        Returns: {block_id, outcome: confirmed|not_found}.
        Next: serve_cv to write a CV with the fact available."""
        with get_conn() as conn, conn.cursor() as cur:
            result = _confirm_block(cur, _owner(cur), block_id)
            _audit(cur, "confirm_cv_block",
                   {"block_id": block_id, "client_label": client_label},
                   {"outcome": result["outcome"]})
        return with_next(result, state=result["outcome"], call="serve_cv",
                         why="the confirmed fact now serves in every CV")

    @mcp.tool(annotations=writes(destructive=True, idempotent=True))
    def retire_cv_block(block_id: int,
                        client_label: str = "user-ai") -> dict:
        """What: stamp a fact retired on the owner's word — it stops serving
        (drafts and CVs alike) but the row is kept, as everything is. Audited.
        When: the owner no longer wants a fact on any CV.
        Returns: {block_id, outcome: retired|not_found}.
        Next: list_cv_blocks to see the remaining fact base."""
        with get_conn() as conn, conn.cursor() as cur:
            result = _retire_block(cur, _owner(cur), block_id)
            _audit(cur, "retire_cv_block",
                   {"block_id": block_id, "client_label": client_label},
                   {"outcome": result["outcome"]})
        return with_next(result, state=result["outcome"],
                         call="list_cv_blocks",
                         why="see the remaining fact base")