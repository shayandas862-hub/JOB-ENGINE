"""Contract-v2 loop tools — the agenda, the reading tray, the promotion rule.

The loop a user's own AI runs on its own schedule: daily_brief hands it the
agenda, get_reading_batch serves staged JDs with the server-side prompt,
submit_reading returns each reading through the deterministic grounding
gate, and the rule pair reads/writes what the machine promotes nightly.
Thin skins over src/brief, src/reading and src/discover/promote_rule —
zero engine logic lives here.
"""
from __future__ import annotations

from fastmcp import FastMCP

from audit import record as _audit
from brief import assemble_brief
from discover.promote_rule import load_rule, save_rule
from mcp_server.annotations import READ, writes
from mcp_server.contract import envelope_schema, with_next

# M4 typed results (0013 §6): the stable core a client may validate;
# additive by design — new fields never break a validating client.
_BRIEF_RESULT = {
    "type": "object",
    "properties": {"applications": {"type": "object"},
                   "queue_top": {"type": "array"},
                   "to_read": {"type": "integer"},
                   "reviews_open": {"type": "array"},
                   "last_run": {"type": ["object", "null"]}},
    "required": ["applications", "queue_top", "to_read", "reviews_open"],
    "additionalProperties": True,
}
_BATCH_RESULT = {
    "type": "object",
    "properties": {"prompt_version": {"type": "string"},
                   "prompt": {"type": "string"},
                   "required_shape": {"type": "object"},
                   "claim_minutes": {"type": "integer"},
                   "jobs": {"type": "array"},
                   "staged_total": {"type": "integer"}},
    "required": ["prompt_version", "prompt", "required_shape", "jobs"],
    "additionalProperties": True,
}
_READING_RESULT = {
    "type": "object",
    "properties": {"outcome": {"type": "string"}},
    "required": ["outcome"],
    "additionalProperties": True,
}
from mcp_server.identity import current_owner as _owner
from mcp_server.session import scoped_conn as get_conn
from reading.accept import accept_reading
from reading.serve import get_batch
from reading.stage import skip_reading as _skip

# U4 knock-on-demand: a fresh lens starts at ~0.7% door coverage, so a codes
# change starts the owner-lens sweep immediately instead of waiting for
# someone to run it. Modest batch, polite parallelism.
KNOCK_BATCH = 2000
KNOCK_WORKERS = 4


def _spawn_knock(owner=None) -> str:
    """Start the owner-lens door-knock DETACHED; returns the log path. The
    sweep lock makes a double-start exit instantly (visible in the log).

    Knocking is done FOR this owner and on their lens, so it is charged to
    them (task 5) as well as to the shared quota."""
    from mcp_server.census_tools import LOG_DIR, _spawn_detached
    return _spawn_detached(LOG_DIR, "knock", "sweep.py",
                           ["--batch", str(KNOCK_BATCH), "--owner-lens",
                            "--workers", str(KNOCK_WORKERS)], owner=owner)


def register(mcp: FastMCP) -> None:
    """Hang the five contract-v2 loop tools on the server."""

    @mcp.tool(annotations=READ, output_schema=envelope_schema(_BRIEF_RESULT))
    def daily_brief() -> dict:
        """What: the day's agenda — applications so far, the top of the apply
        queue, JDs waiting in the reading tray, open review flags, the last
        run, and lens_coverage (industry doors knocked so far — relay it
        honestly while it is low: day-1 quality is ads-only).
        When: start every session here; it decides what to do next.
        Returns: {applications, queue_top, to_read, reviews_open, last_run,
        lens_coverage}.
        Next: whatever `next` suggests — tray, then reviews, then the queue."""
        with get_conn() as conn, conn.cursor() as cur:
            brief = assemble_brief(cur, _owner(cur))
        reviews = sum(r["n"] for r in brief["reviews_open"])
        if brief["to_read"] > 0:
            call, why = "get_reading_batch", (
                f"{brief['to_read']} staged JDs want a proper read")
        elif reviews > 0:
            call, why = "list_review_flags", (
                f"{reviews} open flags wait for a decision")
        else:
            call, why = "get_apply_queue", (
                "nothing staged or flagged — apply from the queue")
        state = (f"{brief['applications']['total']} applications so far, "
                 f"{brief['to_read']} to read, {reviews} to review")
        doors = brief.get("lens_coverage")
        if doors and doors["total"] and doors["pct"] < 50:
            state += (f" · your industry's doors are still being knocked — "
                      f"{doors['knocked']}/{doors['total']} done")
        return with_next(brief, state=state, call=call, why=why)

    @mcp.tool(annotations=writes(),
              output_schema=envelope_schema(_BATCH_RESULT))
    def get_reading_batch(limit: int = 10) -> dict:
        """What: claim a batch from the reading tray — staged JDs plus the
        engine's versioned extraction prompt and the JSON shape to return.
        staged_tier is 'match' (title patterns hit — always read it) or
        'near_miss' (read if plausibly relevant, else skip_reading it).
        When: daily_brief says there is something to read.
        Returns: {prompt_version, prompt, required_shape, claim_minutes,
        jobs: [{role_id, role_title, jd_full, staged_tier}], staged_total}.
        Next: submit_reading per job (or skip_reading); unclaimed batches
        re-serve after claim_minutes."""
        with get_conn() as conn, conn.cursor() as cur:
            batch = get_batch(cur, _owner(cur), limit=limit)
        n = len(batch["jobs"])
        if n:
            return with_next(
                batch, state=f"{n} JDs claimed, {batch['staged_total']} staged in all",
                call="submit_reading",
                why="extract per the served prompt; ungrounded claims are dropped")
        return with_next(batch, state="tray empty", call="daily_brief",
                         why="nothing staged — check the agenda")

    @mcp.tool(annotations=writes(idempotent=True),
              output_schema=envelope_schema(_READING_RESULT))
    def submit_reading(role_id: int, reading: dict,
                       client_label: str = "user-ai") -> dict:
        """What: submit one job's extraction for verification — every claimed
        skill must appear verbatim in the stored JD, the salary verbatim in
        its READABLE text (tags stripped, so an HTML-split range still
        grounds). What fails is dropped and recorded.
        When: after reading a job from get_reading_batch.
        Returns: {outcome: accepted|held_for_retry|invalid|not_staged|
        not_found, skills_accepted, rejected_skills, salary_rejected}.
        held_for_retry means only the salary failed: the listing STAYS in your
        tray — fix that one field and resubmit, or send salary_text null.
        Next: the rest of the batch, then get_reading_batch until dry."""
        with get_conn() as conn, conn.cursor() as cur:
            result = accept_reading(cur, _owner(cur), role_id, reading,
                                    provenance=client_label)
            _audit(cur, "submit_reading",
                   {"role_id": role_id, "client_label": client_label},
                   {"outcome": result["outcome"],
                    "skills_accepted": result.get("skills_accepted"),
                    "rejected": result.get("rejected_skills")})
        state = result["outcome"]
        if result["outcome"] == "accepted":
            state = (f"accepted {result['skills_accepted']} skills, "
                     f"rejected {len(result['rejected_skills'])}")
        return with_next(result, state=state, call="get_reading_batch",
                         why="keep draining the tray until it is dry")

    @mcp.tool(annotations=writes(idempotent=True))
    def skip_reading(role_id: int, client_label: str = "user-ai") -> dict:
        """What: pass on a served near-miss you judged irrelevant. The skip is
        STAMPED so the row never re-stages; the row itself is kept. Audited.
        When: a 'near_miss' job from get_reading_batch is clearly not worth
        the owner's reading time.
        Returns: {outcome: skipped|not_staged|not_found, role_id}.
        Next: get_reading_batch to keep draining the tray."""
        with get_conn() as conn, conn.cursor() as cur:
            result = _skip(cur, _owner(cur), role_id)
            _audit(cur, "skip_reading",
                   {"role_id": role_id, "client_label": client_label},
                   {"outcome": result["outcome"]})
        return with_next(result, state=result["outcome"],
                         call="get_reading_batch",
                         why="keep draining the tray until it is dry")

    @mcp.tool(annotations=READ)
    def get_promotion_rule() -> dict:
        """What: the owner's lens row — industry codes, minimum local jobs,
        auto flag, Adzuna ads category. This one row drives nightly promotion,
        what the Pass-2 probe picks, and which ads category the sweep walks.
        When: to check or explain what the machine promotes by itself.
        Returns: {industry_codes, min_local_jobs, auto, adzuna_category}, or
        null if no rule exists yet.
        Next: set_promotion_rule to change it."""
        with get_conn() as conn, conn.cursor() as cur:
            rule = load_rule(cur, _owner(cur))
        state = "no rule set" if rule is None else (
            f"{len(rule['industry_codes'] or [])} industry codes, "
            f"floor {rule['min_local_jobs']}, auto "
            + ("on" if rule["auto"] else "off"))
        return with_next(rule, state=state, call="set_promotion_rule",
                         why="adjust what the machine promotes nightly")

    @mcp.tool(annotations=writes(idempotent=True, open_world=True))
    def set_promotion_rule(industry_codes: list[str] | None = None,
                           min_local_jobs: int | None = None,
                           auto: bool | None = None,
                           adzuna_category: str | None = None) -> dict:
        """What: change the owner's lens row; only the fields you pass change.
        adzuna_category drives the ads sweep ('all' = whole inventory).
        Changing the codes starts the owner-lens door-knock immediately, so a
        fresh lens does not wait at 0.7% coverage. Audited.
        When: after find_industry_codes confirms codes with the owner, or the
        nightly promotions are too loose or too tight.
        Returns: the stored rule plus knock ({started, log_path}, else null).
        Next: sweep_status to watch the doors open."""
        with get_conn() as conn, conn.cursor() as cur:
            owner = _owner(cur)
            before = load_rule(cur, owner)
            row = save_rule(cur, owner, industry_codes=industry_codes,
                            min_local_jobs=min_local_jobs, auto=auto,
                            adzuna_category=adzuna_category)
        stored = {k: row[k] for k in ("industry_codes", "min_local_jobs",
                                      "auto", "adzuna_category")}
        old_codes = set((before or {}).get("industry_codes") or [])
        stored["knock"] = None
        if industry_codes is not None and set(stored["industry_codes"] or []) != old_codes:
            stored["knock"] = {"started": True,
                               "log_path": _spawn_knock(owner)}
        state = (f"rule stored: floor {stored['min_local_jobs']}, auto "
                 + ("on" if stored["auto"] else "off"))
        if stored["knock"]:
            return with_next(
                stored, state=state + " · door-knock started for the new lens",
                call="sweep_status",
                why="watch your industry's doors being knocked")
        return with_next(
            stored, state=state, call="get_promotion_rule",
            why="verify the stored rule reads back as intended")