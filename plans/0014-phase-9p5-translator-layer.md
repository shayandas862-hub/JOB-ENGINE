# 0014 — Phase 9.5: the Translator Layer (the second update, after the app goes live)

- **Status:** 🟡 **MOSTLY DELIVERED 2026-08-12** — task 0 (the five audit
  repairs) and items 1, 2, 3, 4, 6, 9, 10 shipped. **Items 5 (saved watches)
  and 8 (coverage) were NOT built** and carry forward with their triggers;
  see the per-item marks in §1 and the note dated 2026-08-12 (evening).
- **Created:** 2026-08-10 · **Last updated:** 2026-08-10
- **Depends on / blocked by:** Phase 9 complete (friend keys, RLS proven by refusal, per-owner pass, onboarding + intake-v1, budgets, Google sign-in, runbook, security-review zero criticals)
- **Owner / last touched by:** Claude session 2026-08-10 (the go-live planning night)
- **Relates to:** 0013 §6 (M-gaps — M1–M4 build in Phase 9; M5/M6/M7 land here), 0010 item 16 (learning curve), 0011 (saved watches), 0007 items 2–4 (coverage), 0004 (Notion disposition), 0001 (superseded — see §4)

## Goal

Turn the safe machine into the product the founder named: **a life-story →
deterministic-pattern translator**, not merely a smart job engine. Everything
here is user-experience and product depth; nothing here gates safety — that is
exactly why it waits until after live. Most items are text and rows, not
engineering.

**Why "Phase 9.5", not "Phase 10":** the architecture master plan's PHASE 10
card is already the Apply-Assist Agent (browser form-filler, deliberate
stretch finale). This layer slots between, per the project's insertion
convention (7.5 / 7.8 / 8.5 precedent). Do not renumber anything.

## 1 · The build list (ordered by product value)

1. ✅ **DELIVERED 2026-08-12.** **The mirror** — "here is what the system understands about you": a
   read-back surface (MCP tool + dashboard card) over confirmed cv_blocks +
   my_skills, with receipts — *"34 facts · 19 skills · 6 evidenced outside
   paid work"*. The moment the product stops feeling like a job board.
   Deliberately built AFTER watching real users onboard in Phase 9.
   *No stored opinion of the person — the facts are stored, understanding is
   re-formed on each read (a stored summary drifts; facts don't).*
2. ✅ **DELIVERED 2026-08-12.** **M6 — the amend path.** Today a fact edit = retire + re-add (two calls,
   correct by keep-all, clumsy for clients). Ship an `amend_cv_block`
   convenience that does retire-old + draft-new-linked in one audited step —
   still a stamp chain, never an in-place mutation.
3. ✅ **DELIVERED 2026-08-12** (server-side convenience, not the prompt — the prompt option had already shipped in Phase 9 and was measured to have failed). **M7 — the skills double-write seam.** One life experience should reach
   BOTH the CV fact base and the gap model. Today `add_cv_block` and
   `add_skill` are separate calls nothing links. Either the intake-v1 prompt
   instructs both calls explicitly (cheap, Phase 9 can carry the sentence) or
   a server-side convenience writes both from one payload (here).
4. ✅ **DELIVERED 2026-08-12, on a different basis than briefed** — `learned_at` was measured EMPTY (0 of 22 rows, B-GAE-046), so the ranking is over demand × held × proven in three effort tiers. **Learning-curve model** (0010 item 16). `my_skills.learned_at` + evidence
   has been collecting since 8.5 task 1 (2026-08-10). With weeks of data:
   "skills you're closest to closing" ranking, receipts riding. Rows-first;
   no engine AI.
5. ⛔ **NOT BUILT — carried forward.** The design below is unchanged and still correct; it was not started, rather than started and abandoned. Reason: it is the largest item in this list (ten dimensions, a starvation forecast, nightly evaluation inside the per-owner pass, plus brief and dashboard surfaces) and the session chose to finish tasks 6, 9 and 10 and close the phase properly instead of leaving a half-built stage behind. **Trigger: unchanged — it is next.** Note for whoever builds it: it touches the per-owner pass in `scripts/run.py`, so the sacred 06:30 lane rule applies (rebuild → `gcloud run jobs execute goal-a-daily --region europe-west2 --wait` → verify 15/15 → only then may the cron meet it). **Saved watches** (plan 0011 — design already written; its trigger
   "slots after 8.5" has fired). Per-owner watch rows over sponsors/roles,
   evaluated in the per-owner pass, surfacing in brief + dashboard.
6. ✅ **DELIVERED 2026-08-12.** Both halves: the gate reads `clean_html`-stripped text (63 of 212 ranges in HTML adverts were ungroundable before), and a rejected salary now HOLDS the listing for a retry. `extract-v1 → v2`. **HTML-split salary gate fix** (the 2026-08-10 drainer finding, parked
   from a worktree chip — full detail): board-fetched JDs (Ashby, e.g.
   Algolia roles 7090/7116) retain raw HTML, so a rendered range
   "£77,500 — £90,000" is stored as `<span>£77,500</span><span
   class="divider">&mdash;</span><span>£90,000 GBP</span>` — not a contiguous
   substring, so the verbatim gate correctly refuses it; AND a gate-rejected
   FIELD cannot be retried because the first `submit_reading` un-stages the
   row. Mitigation already live: the nightly deterministic salary parser
   independently banked both Algolia ranges — nothing was lost. Fix
   directions (red-first): gate salary against `clean_html`-stripped text
   (there is ONE stripper — alias it, never a second), and/or allow a
   rejected-field-only resubmit while the claim is held. Do NOT weaken the
   verbatim principle for skills. A served-text change may warrant
   `extract-v2` — check how the prompt version is pinned first.
7. ✅ **DELIVERED 2026-08-12** — trimmed 23,087 → **20,151** characters across all 51 tools (−12.7%) while the toolset GREW by four, and pinned by a ratchet at the measured number. See the note below: the first attempt at this item was itself a bug ([[B-GAE-047]]). **Description-trim pass.** The 41-tool descriptions cost every client
   ~6.8k tokens per turn (measured). Tighten wording tool-by-tool with the
   pinned-count tests updated deliberately — the rent goes DOWN while M3
   annotations go in (M2/M3 themselves build in Phase 9's warm-up).
8. ⛔ **NOT BUILT — carried forward**, for the same reason as item 5 and with less regret: this item's own text says "sequence by what live users actually hit", and with `profiles` = 1 there is still no live-user signal to sequence by. **Trigger: the first thing a real user actually hits, or user #2.** **Coverage items** (0007 items 2/3/4): per-company probes, deeper merge,
   multi-board employers. Value-adds; sequence by what live users actually hit.
9. ✅ **CONFIRMED note-only 2026-08-12** — restated as a decision (D-GAE-094) rather than left to decay into an oversight; trigger unchanged and still unmet. **M5** — `prompts`/`resources` MCP primitives: STILL note-only. Build only
   when a real client's UI pulls for it.
10. ✅ **DECISION SURFACED 2026-08-12, not taken — it is the founder's** (D-GAE-095). Measured 323/500 MB, `profiles` = 1: neither trigger fired, and two of the three options below are now known to free almost nothing today. **The database retention decision** (at the latest here; earlier if the
    meter says so). Measured 2026-08-10: DB 316/500MB free tier, drip adds
    ~30MB/month; `aggregator_ads` = 127MB of world data. Options, in order:
    prune ads long-closed at never-sponsor employers (the one class no user
    path touches); trim heavy JD text on closed roles keeping extracted
    facts; or Supabase Pro $25/mo (8GB) — the correct answer if users exist.
    **Keep-all is an OWNER-data principle; whether world data shares it is a
    founder decision to be logged, not assumed.** Trigger: ~450MB or user #2,
    whichever first.

## 2 · Cost posture (measured 2026-08-10, carried as context)

Engine AI £0 forever · Cloud Run ~13% of free tier · Artifact Registry
cleanup policy SET (keep newest 10 — was 95% full, self-maintains now) ·
GitHub Actions inside free tier (doc-only filter absorbs prose pushes) ·
the ONE ticking meter is the database (item 10). Everything in this phase is
strings and rows: zero new engine AI cost, zero new cloud services.

## 3 · Acceptance for the layer

A new user onboards by telling their life story; the system reads back what
it understood, with receipts; one story feeds CV + gaps + curve; a rejected
salary is recoverable; watches watch; and the founder's bill is still
pennies unless users made it Pro-plan money.

## 4 · Disposition of older plans (the carry-forward sweep's first pass)

- 0001 CV Autopilot — **superseded** by serve-all CV (8.5 task 0): the
  "blocked awaiting CV content" block died when cv_blocks seeded 22/22.
  Mark ✅-superseded at next touch.
- 0002 SIC integration / 0006 scheduling — **largely delivered** (census
  classify + Cloud Scheduler); mark delivered-with-notes at next touch.
- 0004 Notion — still deferred; disposition decided when a live user asks
  for filing (their token, task 4 of Phase 9 carries the ref).
- 0013 §4.5 green≠productive — **homed in Phase 9 task 3** (per-owner run
  report must say what MOVED); not this plan's item.

## Notes / log

- 2026-08-10 — Created at the founder's direction after the go-live planning
  review ("ship safety next, ship soul second"). Adopts every orphan the
  phase-boundary audit surfaced (the CV session found the leak; measurement
  confirmed 10 plan files unnamed by Phase 9). Step 5.5 (carry-forward sweep)
  added to the phase relay the same night so this list is the LAST one that
  had to be rescued by memory.
- 2026-08-12 — **Phase 9 closed, so this plan's dependency is satisfied and it becomes the next phase's source.** Delivered by Phase 9 from this plan's blocked-by list: friend keys, RLS proven by refusal (30 policies over 30 tables), the per-owner nightly pass, onboarding + `intake-v1`, per-owner budgets, the runbook. **Two qualifications, stated rather than glossed:** (1) Google sign-in is BUILT and switched OFF at the founder's gate — the provider is not enabled and the project answers the connector's discovery endpoint with 404, so "sign-in done" means the door verifies tokens, not that strangers can walk in; (2) the security-review pass ran adversarially against tasks 2 and 6 and its findings are closed (0055, 0056, 0061), but **zero criticals** is a claim about the reviews that were run, not a certificate. Item 10 (the database retention decision) keeps its trigger: ~450MB or user #2, whichever comes first — still user #1 today, measured `profiles` = 1.

- 2026-08-12 (evening) — **Phase 9.5 built against this plan. Eight of the ten
  items are closed; two are not, and the two are named here rather than left
  to be rediscovered.** Delivered: the mirror (item 1), M6 (2), M7 (3), the
  learning curve (4), the salary gate (6), M5 confirmed note-only (9), the
  retention decision surfaced with its measured basis (10), plus task 0's five
  close-audit repairs. **Three items did not survive contact with the data,
  and that is the useful part of this note:**
  - Item 3 offered "prompt instructs both calls" as the cheap option. It was
    not an option: it had already shipped in Phase 9 and had already failed —
    6 role blocks evidencing "teamwork", "call handling", "cinematography",
    none matching any `my_skills` row, every norm correctly normalised. The
    server-side write was the only one that could make two writes agree.
  - Item 4's premise was false. `learned_at` had 0 of 22 rows populated, and
    the column was two days old, not weeks ([[B-GAE-046]]). Ranking on it
    would have returned an empty list forever from code that reviews as
    correct. Rebuilt on effort tiers instead.
  - Item 10's option list survived, but two of its three options were measured
    to be worth almost nothing today: trimming closed-role JD text frees 6 MB,
    and the never-sponsor ad prune has **zero** candidates because no ad is
    older than 60 days. Only Supabase Pro moves the needle, and no trigger has
    fired.
  **Not built: items 5 and 8.** Item 5 (saved watches) was not started rather
  than half-started; it is the largest thing in this list and it changes a
  stage, so beginning it late would have left the 06:30 lane in an unproven
  state — the one outcome the phase rules forbid. Item 8 (coverage) is
  explicitly "sequence by what live users actually hit", and `profiles` is
  still 1, so there is nothing to sequence by. Both carry into the next
  phase's card with their triggers.
  Item 7 (description trim) is marked partly delivered: the enduring piece is
  `tests/test_tool_description_budget.py`, a ratchet that measures what every
  client pays per turn and refuses to let it grow — the number had never been
  enforceable before, which is why it drifted upward for four phases.

- 2026-08-12 (later, after the quota reset) — **Item 7 is now DELIVERED, and
  the paragraph directly above it was wrong when it was written.** Stated here
  rather than edited away, because the gap between the two is the finding:
  when that sweep ran, `tests/test_tool_description_budget.py` had never been
  committed (`git log --all` on the path returns empty) and the copy on disk
  was RED — asserting a 19,000-character budget against a measured 22,766. So
  a committed plan described a live ratchet that the repository did not
  contain and that did not pass. Logged as [[B-GAE-047]] and closed with
  `tests/test_plan_cited_tests_exist.py`, which now fails when any `tests/…py`
  path named in `plans/` or `docs/` is missing from the repo — 38 such
  citations exist, and exactly one was a lie.
  **What actually landed on resuming:** every description trimmed tool by tool
  to 20,151 characters (−2,936, −12.7%) with the four-label contract and the
  wording pins intact; the budget pinned at the MEASURED number rather than a
  hoped-for one; the 51-tool count test untouched, since no tool was added or
  removed. The trim stopped where it did on purpose — what remains is signal a
  client needs to choose correctly (that a minted key is shown once, that the
  budget resets at midnight UTC, that `held_for_retry` keeps the claim), and
  cutting further would have met the budget by deleting meaning, which is the
  failure `test_no_description_was_gutted_to_meet_the_budget` exists to catch.
