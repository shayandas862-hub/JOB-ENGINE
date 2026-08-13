"""Onboarding tools (Phase 9 task 4) — a new owner reaches their first
nudge by conversation alone.

get_intake_interview serves the versioned intake-v2 prompt that builds a
new owner's fact base (0013 §6 M1 — before it, fact-base quality depended
on which AI the user happened to bring). record_experience is where that
interview writes: one life experience becomes a career fact AND the skills
it evidences, joined (M7). create_profile mints the row
everything per-owner hangs off — operator-only until sign-in lands
(task 6), because whoever can create identities decides who the machine
answers to, and today that is the founder alone.
"""
from __future__ import annotations

from uuid import uuid4

from fastmcp import FastMCP
from fastmcp.server.dependencies import get_access_token as _token

from audit import record as _audit
from criteria.experience import record_experience as _record
from criteria.profiles import insert_profile
from criteria.profiles import set_notification_channel as _set_channel
from criteria.profiles import set_notion_token_ref as _set_ref
from cv.intake import get_interview
from mcp_server.annotations import READ, writes
from mcp_server.contract import with_next
from mcp_server.identity import current_owner as _owner
from mcp_server.session import adopt_owner
from mcp_server.session import scoped_conn as get_conn


def _operator() -> bool:
    """May this caller create profiles? The founder's bootstrap token or
    the local stdio door (no token at all) — never a minted friend key.
    Task 6 swaps this gate for sign-in identity; until then, minting
    identities stays with the person who answers for the machine."""
    token = _token()
    return token is None or "bootstrap" in (token.scopes or [])


def register(mcp: FastMCP) -> None:
    """Hang the onboarding tools on the server."""

    @mcp.tool(annotations=writes())
    def create_profile(name: str, contact_email: str | None = None) -> dict:
        """What: create a NEW owner profile — the row every per-owner surface
        (lens, queue, tray, CV, nudges) hangs off. Operator-only until sign-in
        lands: a friend key is refused. Takes NO secrets; the channel and
        Notion ref have their own setters. Audited.
        When: the founder is onboarding a new person by conversation.
        Returns: {profile_id, name}, or {refused, reason}.
        Next: the operator mints their key out of band (docs/runbook.md),
        then their own AI starts at get_intake_interview."""
        if not _operator():
            return with_next(
                {"refused": True,
                 "reason": "only the operator may create profiles until "
                           "sign-in lands (task 6)"},
                state="refused — operator only",
                call="daily_brief",
                why="ask the founder to onboard you; your key already "
                    "serves your own data")
        with get_conn() as conn, conn.cursor() as cur:
            operator_id = _owner(cur)
            new_id = str(uuid4())
            # WITH CHECK (profile_id = app_owner()): the row can only be
            # written AS the owner it belongs to — adopt, insert, return.
            adopt_owner(cur, new_id)
            row = insert_profile(cur, new_id, name, contact_email)
            adopt_owner(cur, operator_id)   # the audit row is the operator's
            _audit(cur, "create_profile", {"name": name},
                   {"profile_id": new_id})
        return with_next(
            row,
            state="profile created",
            call="get_intake_interview",
            why="mint their key out of band with the operator mint script "
                "(docs/runbook.md), then their own AI starts here")

    @mcp.tool(annotations=writes(idempotent=True))
    def set_notification_channel(channel: str) -> dict:
        """What: point the caller's OWN nudges at their own phone — the ntfy
        topic their daily digest goes to. The value is a secret (the topic IS
        the capability to reach that phone): stored, NEVER echoed back, and
        the audit row records that a change happened, not the value.
        When: onboarding, or the owner switched phones/topics.
        Returns: {updated} — never the value.
        Next: send_test_nudge to prove the phone actually buzzes."""
        with get_conn() as conn, conn.cursor() as cur:
            updated = _set_channel(cur, _owner(cur), channel)
            _audit(cur, "set_notification_channel", {"changed": True},
                   {"updated": updated})
        if not updated:
            return with_next({"updated": False},
                             state="no profile row to update",
                             call="daily_brief",
                             why="the caller's profile was not found")
        return with_next({"updated": True}, state="channel set",
                         call="send_test_nudge",
                         why="prove the phone buzzes before relying on it")

    @mcp.tool(annotations=writes(idempotent=True))
    def set_notion_token_ref(ref: str) -> dict:
        """What: store the NAME of the caller's Notion credential (a Secret
        Manager-style reference) on their own profile — never the token
        itself; values that look like real tokens (ntn_, secret_) are
        refused. Audited.
        When: onboarding a user who wants their own applications board.
        Returns: {updated, notion_token_ref} or {refused, reason}.
        Next: daily_brief — onboarding continues there."""
        if ref.startswith(("ntn_", "secret_")):
            return with_next(
                {"refused": True,
                 "reason": "that looks like a real Notion token — store a "
                           "reference to where the secret lives, never the "
                           "secret itself"},
                state="refused — raw token", call="daily_brief",
                why="create a named secret and pass its reference instead")
        with get_conn() as conn, conn.cursor() as cur:
            updated = _set_ref(cur, _owner(cur), ref)
            _audit(cur, "set_notion_token_ref", {"ref": ref},
                   {"updated": updated})
        return with_next(
            {"updated": updated, "notion_token_ref": ref} if updated
            else {"updated": False},
            state="reference stored" if updated else "no profile row",
            call="daily_brief",
            why="continue onboarding from the agenda")

    @mcp.tool(annotations=writes(idempotent=False))
    def record_experience(kind: str, fact_text: str,
                          skills: list[dict] | None = None,
                          title: str | None = None,
                          organisation: str | None = None,
                          date_range: str | None = None,
                          client_label: str = "user-ai") -> dict:
        """What: record ONE life experience as a fact AND the skills it
        evidences, in one call that links them — the fact is a DRAFT, as
        always. Use this instead of add_cv_block + add_skill: called
        separately the two drift apart and the skill ends up claimed with no
        fact behind it.
        When: the intake interview, or whenever the owner describes something
        they did. Skills are [{name, level?, evidence?, learned_at?,
        category?}] — a bare name is fine.
        Returns: {block_id, confirmed: false, skills: [...]}.
        Next: list_cv_blocks to show the wording, then confirm_cv_block."""
        with get_conn() as conn, conn.cursor() as cur:
            result = _record(cur, _owner(cur), kind=kind, fact_text=fact_text,
                             skills=skills or [], title=title,
                             organisation=organisation, date_range=date_range,
                             source="mcp")
            _audit(cur, "record_experience",
                   {"kind": kind, "skills": len(result["skills"]),
                    "client_label": client_label},
                   {"block_id": result["block_id"]})
        return with_next(
            result, state=f"draft written with {len(result['skills'])} skill(s)",
            call="confirm_cv_block",
            why="the owner approves the wording, then confirm")

    @mcp.tool(annotations=READ)
    def get_intake_interview() -> dict:
        """What: the served, versioned interview (intake-v2) for building the
        owner's fact base — the prompt, the shape every fact must take, the
        coverage checklist, and the fact base's state. The engine owns this
        prompt; never substitute your own questions.
        When: a new owner has no facts yet, or wants a top-up.
        Returns: {prompt_version, prompt, required_shape, coverage,
        fact_base: {blocks, confirmed, drafts}}.
        Next: interview per the prompt and record each experience with
        record_experience; list_cv_blocks shows drafts for approval."""
        with get_conn() as conn, conn.cursor() as cur:
            result = get_interview(cur, _owner(cur))
        fb = result["fact_base"]
        if fb["drafts"]:
            return with_next(
                result,
                state=(f"{fb['blocks']} facts, {fb['drafts']} awaiting "
                       "the owner's approval"),
                call="list_cv_blocks",
                why="show the owner the drafts; they approve, you confirm")
        return with_next(
            result,
            state=("fact base is empty — fresh intake" if not fb["blocks"]
                   else f"{fb['confirmed']} confirmed facts"),
            call="add_cv_block",
            why="interview the owner and record each fact as a draft")
