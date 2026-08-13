# 0001 — CV Autopilot (Phase 7.6)

- **Status:** ✅ Superseded (by the serve-all CV, Phase 8.5 task 0 — kept for history)
- **Created:** 2026-07-14  ·  **Last updated:** 2026-07-14
- **Depends on / blocked by:** `cv_blocks` is empty — needs Shayan to fill `docs/cv-intake-template.md` (his master fact-bank)
- **Owner / last touched by:** Claude session 2026-07-14

## Goal
Every role that reaches the apply list automatically gets a **tailored, ATS-safe
CV** attached to its Notion card. Same true facts in → a different CV per role
(Anthropic ≠ Google), all inside the existing truth gate (no invented claims).
Manual trigger first for testing; automatic path built behind a switch.

## Context (important)
Much of this **already exists** (Phase 7, green + tested): assemble → phrase →
truth-gate → ATS `.docx` render, plus the `generate_cv` MCP tool. This plan is an
**extension, not a rebuild.** `my_skills` (22) and `role_skills` (8k) are already
populated; only `cv_blocks` (the CV content) is empty — that's the one blocker.

## Decisions locked (2026-07-14)
- **Trigger = apply-list membership.** Anything in the apply list should carry a
  tailored CV. End state automatic; **manual first for testing, with the auto
  path provisioned** behind a switch.
- **Content:** Shayan provides a master fact-bank (see `docs/cv-intake-template.md`);
  engine tailors per role by selecting/phrasing — it never fabricates.
- **Delivery:** attach the `.docx` to the role's Notion card (via Claude's Notion
  connector — keeps Notion out of the engine, per plan 0004).

## Tasks
- [ ] **Seed loader** — `scripts/seed_cv_blocks.py`: load Shayan's fact-bank into
      `cv_blocks` as unconfirmed drafts; he confirms. (test-first) — BLOCKER
- [ ] **Apply-list trigger** — `CV_AUTOPILOT = manual | auto` switch; manual makes
      a CV for one role on command, auto (off by default) covers apply-list roles
- [ ] **Sharper per-role tailoring** — push JD/role_skills harder into selection +
      phrasing so two roles differ meaningfully, still inside the truth gate
- [ ] **Claude skill `cv-to-notion`** — pick apply-list role → `generate_cv` →
      attach `.docx` to the Notion card → set status
- [ ] Fold in **Notion-out-of-engine** (plan 0004) at the filing stage

## Notes / log
- 2026-07-14 — Plan captured. Intake template written to `docs/cv-intake-template.md`.
  Not started — waiting on Shayan's CV content. Cost note: auto-CV for *all*
  apply-list roles = one Gemini call each → scope to top/new roles at auto time
  (ties to Phase 8 spend cap).
- 2026-08-12 — **Phase 9 close, carry-forward sweep: SUPERSEDED, and the block is long gone.** The founder seeded `cv_blocks` 22/22 confirmed on 2026-08-10, which unblocked this plan and then made it unnecessary in the same afternoon: Phase 8.5 task 0 shipped the serve-all CV (`serve_cv` hands the client AI EVERY confirmed fact block; `submit_cv` returns it through the truth gate and the ENGINE renders the .docx), and Phase 8.5's U8b added the writer quartet so a fact enters by conversation. Nothing in this file is still owed. Marked here rather than deleted — a finished plan is history, never a tidy-up.
