# Plan 0010 — Walkthrough findings: noted gaps + refinements (2026-08-03)

- **Status:** 🚧 In progress — several items shipped in Phases 8.5 and 9; the rest carry into plan 0014 (added 2026-08-12: this file had no Status line at all, which is why nothing ever read it as open)
- **Last updated:** 2026-08-12

Source: the founder's step-by-step product walkthrough (2026-08-03 session).
Every suggestion spoken in that session is written here so it can be revisited
or rebuilt from this file alone. Rule of the list: **nothing here may block or
stale the apply lane**; items activate at their stated trigger, not before.
None of this changes Phase 8's task list (plans/0005) — items marked (P9) are
Phase 9 / third-party territory (plans/0008).

Status legend: ✅ shipped · 🔲 todo · 🧠 design-first (decide before building).

---

## Shipped during the walkthrough (recorded, not pending)

- ✅ **Daily classify top-up** (commit 5a59c4e, suite 592/0 fail, 3 new tests).
  Gap found by founder questioning: weekly register refresh created blank
  census cards for newcomers but classification only ran by hand. Now a
  `classify` stage (register → **classify** → discover, order pin updated
  deliberately) runs nightly: only never-asked cards, `--batch 2000` cap
  (~20 min worst case; seconds when census current), quiet exit-0 when the
  key is unset or nothing is left. Built by a delegated Opus agent in a
  worktree from a written spec; reviewed line-by-line + full suite before
  merge.

## A. Engine refinements (small, safe, no product change)

1. 🔲 **Retry stale registry errors.** Cards stamped `registry_outcome='error'`
   (e.g. a Companies House outage night) are never re-asked —
   `pick_classify_batch` picks only never-asked cards. Deliberate for
   ambiguous/not_found (re-asking wastes quota), wrong forever for transient
   errors. Build: inside the classify stage, also pick `error` cards with
   `registry_checked_at` older than ~30 days, capped (say 200/night).
   Trigger: when error-card count is worth the quota (check
   `classify_status` first).
2. 🔲 **run.py line-3 docstring is stale** — lists the old stage chain
   (missing register/classify/merge/promote/stage_reading). Cosmetic honesty
   fix next time the file is touched for real work.

## B. Universal-lens tools — the three ways humans search (P9-leaning)

The engine is person-agnostic by data, not code: a user's lens = DB rows
(promotion_rules.industry_codes + min_local_jobs, their target_roles,
my_skills, my_constraints), switched by MCP tool calls. What's missing is the
*universal* tool surface; today's tools are founder-first artifacts.

3. 🔲 **`search_sponsors` universal tool** — filter the census by any industry
   (SIC or plain-English via sic_codes), town, board status. The data layer
   exists (`v_sponsor_industry`, 0032); `list_software_companies` is the
   software-only convenience it generalises. Thin build; unlocks
   grocery/marketing/restaurant users and the "research tool" use.
4. 🔲 **Role-lens universal search** — "who is hiring <role words> and can
   sponsor?" over census_jobs + role_listings titles (synonyms applied),
   sponsor/salary gates on top. Exists for the tracked+ads world; the
   census-wide version is thin once (3) exists.
5. 🧠 **Skills-lens full tool (P9)** — "here are my skills → which roles,
   which companies, what gap, with receipts." Math core built
   (overlap×rarity + receipts); accuracy grows with reading volume — this
   lens is the moat and depends on the tray being drained routinely.

## C. Dashboard surfaces

6. 🔲 **Sponsors/Browse tab** — industry-filterable sponsor list. "The shelf
   is stocked, the shop window isn't": v_sponsor_industry exists; the tab
   must keep the complexity-hiding pin (add the view to the allowed set +
   extend the pin test — the dashboard still reads ONLY curated views).
7. 🔲 **Per-row fit score in v_today** once AI reads flow (score+receipts are
   already computed by src/match/; the view just doesn't carry them yet).
8. 🔲 **"New today (N)" chip/filter** on the queue tabs.
9. 🧠 **Product buttons (mark applied / snooze) on the dashboard** — a
   *conscious* relaxation of the read-only pin (token-gated POST). The MCP
   tools already do both; decide deliberately whether the glass gains hands.

## D. Data-coverage builds (where JDs and missing doors come from)

10. 🔲 **Reed job-detail drip.** 5,549 merged ads carry no job description →
    invisible to the skills engine. Reed's detail endpoint returns one ad's
    full JD per call (~950 free calls/day budget). Build as a capped nightly
    drip stage (like the quota drip), highest-value ads first — the £50k+
    matched slice (~1,362 ads) clears in ~1.5 days. Deliberately deferred in
    July; build when ad-JDs are wanted in the tray.
11. 🧠 **Reader-supplies-JD path.** Dashboard wording ("or a reader supplies
    one") is ahead of the code: stage.py stages only rows with non-empty
    jd_full. Trust design required before building: if the same reader
    supplies BOTH the JD and the claims, the grounding gate loses its
    independence. Options: engine fetch-verifies the URL server-side, or
    reader-supplied JDs become a labelled lower-trust tier. Build
    deliberately, never casually.
12. 🔲 **More ATS adapters** (SmartRecruiters, Teamtailor, Personio,
    Recruitee, …). Same-shaped modules as the door-knock four. Choose by
    observed density: count apply-link hosts across stored ads first, then
    build the top one or two — not alphabetically.
13. 🔲 **Workday address intake.** Corporate doors are unguessable; the
    adapter exists but must be handed addresses. Consider a small assisted
    list (top sponsor corporates + their myworkdayjobs addresses) fed through
    the existing verified onboarding.
14. 🔲 **Onboarding words→codes translator + owner-lens sweep.** The founder's
    care-home walkthrough (2026-08-03): a user says "care homes" → look the
    words up in sic_codes descriptions → write the matched codes into THEIR
    promotion rule → done; and `run_sweep`/aggregator stages should read the
    owner's rule codes instead of the hardcoded SOFTWARE_SIC convenience
    (software_only flag becomes "owner_lens"). Principle to preserve: user
    words never edit code — they become rows. Adzuna's IT-category pin
    becomes a per-owner category while at it. This is the onboarding spine
    for any non-software user (P9-leaning, but the sweep parameter is thin
    and safe now).
15. 🔲 **Named saved watches (multi-lens per owner).** Founder's spec
    (2026-08-03): a user keeps SEVERAL standing watches, each a named filter
    combo — (company), (role anywhere), (role + location), (location +
    salary), any mix — each evaluated by the nightly run, each feeding its
    own labelled line in the morning nudge. Today each owner has exactly one
    lens (one criteria set + one rule); this generalises to N watch rows per
    owner (a `watches` table: owner_id, name, filters jsonb, notify flag).
    The engine's matching already does every individual filter — this is
    rows + a loop, not new machinery. Company-tracking ("tell me when they
    post") and role-tracking ("tell me who advertises this") already exist
    via target_companies + the core loop; this item is only the
    any-combination generalisation. Cadence stays nightly (honest "as soon
    as" = next morning); faster per-watch cadence is a scheduler decision
    later. Builds naturally after item 14's owner-lens work (P8.5/P9 seam).
16. 🧠 **Skill-gap closure trajectory (the learning curve).** Founder's spec
    (2026-08-03): users tell their AI what they've learned/built ("finished
    the NVQ", "shipped a Django project") → written as TIMESTAMPED,
    evidence-carrying rows via the skills-entry tool → the maths turns the
    history into a curve. The model, all deterministic with receipts:
    gap(t) = the match core's gap recomputed at each point in time;
    **closure rate = the discrete derivative** Δgap/Δweek ("you're closing
    3% a week"); **the decomposition** Δgap = (user learning) + (market
    drift) — because demand moves too, a gap can widen while the user
    improves, and the two terms must be shown separately or the number
    lies; **cumulative learning = the integral** of learning events over
    time (the effort account); **honest forecast** = time-to-close at the
    current trailing rate (linear trend, MIN_SAMPLE-style floor, never a
    promise). PREREQUISITE BAKED IN NOW: the skills-entry tool (P8.5 task 1)
    must carry `learned_at` timestamps + evidence text from its FIRST
    version, so the curve has data the day the model builds. Build slot:
    after 8.5 task 1; the model itself is P9-adjacent.
17. 🔲 **Synonym mapping goes user-side (Gemini's third job).** Found during
    the Gemini retirement (2026-08-03): normalise/synonyms.py was AI spot
    #3 — batch-mapping messy skill names ("ReactJS"/"React.js" → "React")
    into the synonyms table. Retirement consequence: existing mappings
    persist forever (keep-all), but NEW variants stop being auto-merged;
    matching falls back to exact-norm names. Fix, tray-pattern: a small
    served-prompt tool (get_synonym_batch / submit_synonyms) so the user's
    AI canonicalises pending unknown skill names; deterministic gate =
    proposed canonical must be an existing skill name or flagged for
    review. Small brick, slots beside P8.5 task 0/1.

---

_Written 2026-08-03 during the walkthrough; owner of every trigger: the
founder. Revisit at Phase 8 close (status page + hosted MCP change what B/C
items are worth) and at any "drain the tray" burst (changes D-10's urgency)._

## Notes / log

- 2026-08-12 — **Phase 9 close, carry-forward sweep.** This file had **no `Status:`
  line**, so no sweep could ever report it as open — found and fixed here.
  Shipped from it since it was written: the classify top-up, the near-miss tray
  tier (item on the starving tray), the honest coverage line in the brief, and
  the queue view's hidden founder title regex. **Item 16 (the learning-curve
  model)** is item 4 of plan 0014 and its data has been collecting since
  2026-08-10 — `my_skills.learned_at` + evidence, pinned from day one for
  exactly this. **Item 15** was superseded by plan 0011 (saved watches), whose
  trigger has now fired. Everything else stays as written, with its own stated
  trigger; **nothing here may block or stale the apply lane**, which remains
  this file's governing rule.
