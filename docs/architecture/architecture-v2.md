# Architecture v2 — Goal A Engine: From Tool to System

**Status:** Confirmed 2026-07-10 (founder-approved in session) · **Revised 2026-07-11:** Phase 7.5 (The Census Sweep) inserted between Phases 7 and 8 by founder direction; the country-agnostic machine principle added to Section 1.
**Supersedes:** the implicit v1 architecture (Phases 1–6 engine, CLI-only, fixed company list)
**Companion documents:** `../handoffs/` — the per-phase relay files that carry each phase's handoff into the next session (`phase-9-relay-*.md` and the session prompts). *Corrected 2026-08-10: this line named `../handoffs/architecture-handoff.md`, a single rolling handoff that stopped being written after Phase 4 and no longer exists. Per-phase relay files replaced it. `../../PROJECT-MEMORY.md` was also listed here and is likewise retired — it carried the project ref and was removed at the flip.*

---

# SECTION 1 — SYSTEM DESIGN

## What We Are Building

A sponsor-aware job-search system that hunts UK job listings matching a person's criteria, tracks how every listing changes over time, generates a tailored ATS-friendly CV for each role worth applying to, files everything in Notion, and nudges the person's phone when an application is ready to go. It runs by itself every day. All the work is done by deterministic code; Claude connects through an MCP server as the reasoning layer that directs the code's tools. It is built single-user-first (the founder), but every piece of personal data lives in the database — never in the code — so switching it on for other people later is a configuration change, not a rebuild.

**The machine principle (added 2026-07-11):** this is a job-search **and data-analysis machine**, not a UK program. The UK sponsor register is its first dataset, not its identity. The same portability rule that keeps personal data out of the code keeps country assumptions out of the new layers: census tables and columns carry country-neutral names (`registry_*`, `industry_codes`, `local_jobs_seen`, a `country` column), the national-registry client is a swappable per-country plug-in behind one import, and the board-probing layer is already global (Greenhouse/Lever/Ashby/Workable are worldwide platforms). Swap the register data and the registry plug-in and the machine works for another country; full generalisation of the UK-specific visa/salary rules is Phase 9 work.

**Governing principle: code first, MCP second.** Every capability must work as a plain function/CLI command with no Claude in the loop. The MCP server adds zero logic — it is the same functions with tool names on them. If the MCP server dies, cron still fetches, the queue still ranks, nudges still fire. Claude adds judgment, never plumbing. AI is used at exactly three caged spots (JD reading, skill-synonym mapping, CV wording), each with a working no-AI fallback.

## Tech Stack

**Language & engine:** Python 3.13 — extending the existing `goal-a-engine` codebase.
**Why:** The 2026-07-10 audit showed the existing engine is clean, tested, and well-shaped. You don't throw away a good foundation; you build on it.

**Database:** Supabase Postgres (existing "GOAL A" project).
**Why:** All data — 141,956 licensed sponsors, listings, skills, criteria — already lives here, and it comes with built-in user accounts and per-user data walls (RLS) for the day third parties join.

**MCP server:** FastMCP (official Python MCP framework), two modes — stdio locally with Claude now, hosted streamable-HTTP later.
**Why:** Standard way to give Claude tools, same language as the engine, and the same server file works locally and hosted without rewriting.

**AI:** Gemini Flash-Lite, in exactly three caged spots — reading job descriptions (exists), mapping messy skill names (exists), wording the tailored CV (new). Everything else is plain code; every AI spot keeps a no-AI fallback.
**Why:** "AI only where necessary" made physical: three small, testable, swappable AI touchpoints in an otherwise deterministic machine — cheap to run and honest to demo.

**Job discovery sources:** the sponsor register (already in DB), the four existing ATS adapters (Greenhouse/Lever/Ashby/Workable) plus a new Workday adapter, and two legitimate UK job-search APIs (Adzuna and Reed).
**Why:** The sponsor register is the unfair advantage no job site has — it turns "search jobs" into "search jobs at companies that can actually sponsor you." The APIs add breadth legally; no scraping of sites that forbid it.

**Company enrichment (the census):** the national company registry's official API — Companies House for the UK (free) — wired as a swappable per-country registry plug-in.
**Why:** The register gives only a name and a town. The registry adds what each company *is* — official industry codes, active/dissolved status, incorporation age — which is what turns 142k anonymous names into an analyzable dataset. Deterministic name-matching with ambiguity recorded, never guessed; country-neutral column names keep the machine portable.

**CV rendering:** python-docx producing a clean single-column .docx from a template.
**Why:** ATS software reads simple Word files most reliably. Code fills the structure with facts from the database; AI only phrases the wording — the CV can never invent experience.

**Notion:** the official Notion API, called by the engine with its own integration token.
**Why:** Code-first means the pipeline files applications into the Notion tracker by itself on schedule — it doesn't need Claude to be awake to do paperwork.

**Notifications:** ntfy — free push-notification service with a phone app.
**Why:** One line of code sends a push, no account or fees, and it swaps out trivially for email or Telegram later.

**Hosting:** Google Cloud Run — a scheduled Job for the daily pipeline, a small always-on service for the hosted MCP and public status page.
**Why:** Exactly what the build brief's "Job Engine, Live" project specifies; costs pennies at this scale and scales automatically if others join.

**Authentication (future third parties):** Supabase Auth + a bearer token per user for the hosted MCP.
**Why:** Built into the database already in use. Not switched on for single-user mode; the schema is simply built ready for it.

**Licence:** MIT — see Licence & Legal Foundations.

## How The System Connects

Every morning, a scheduler wakes the pipeline. The pipeline loads the profile's criteria from the database — target roles, salary floor, locations, kill-words — never from code. It fetches every classified company's job board (with retries, so one network blip no longer loses a company), plus fresh results from the Adzuna and Reed APIs filtered by those criteria. Every posting is checked against history: new listing → recorded with a first-seen date. Seen before → a fingerprint of the description is compared; if it changed, the event is logged with exactly when and what. Vanished → marked closed. Each API-discovered posting is cross-checked against the sponsor register, so everything entering the queue carries a sponsorship signal.

New listings flow through the reading stage — Gemini extracts skills, salary text, sponsorship hints, and occupation type, with the grounding check catching hallucinations — then skill names are canonicalised, salaries parsed, and the queue view re-ranks everything: fit first, sponsor confidence second, freshness third, with the salary wall judged against the correct per-occupation going rate.

For each listing that clears every gate, the CV maker assembles the facts — master career blocks from the database on one side, the job's extracted demands on the other — has AI phrase the overlap into tailored bullet wording, verifies no invented claims survived, renders the .docx, and files a card in the Notion application tracker: job details, deadline estimate, sponsor evidence, CV attached, status "ready to apply." Then the phone buzzes: "N roles ready. CVs and links in Notion." The human applies — the system never submits anything.

Alongside the daily loop, a slower machine grinds: **the census sweep**. Night after night it takes the next batch (default 2,000) of the ~110k register organisations that have no census card yet, probes each one for a job board, copies any live jobs once — titles, locations, real links, no AI reading, titles keyword-matched against the owner's roles — and asks the national registry what the company is. Every organisation ends up with a card; a crash resumes exactly where it stopped; the sweep writes only to its own two tables, so the daily loop never feels it. Promoting a census discovery into daily tracking stays a deliberate act through the existing onboarding tools.

Claude sits on top through the MCP server: show the queue, explain a ranking, pull a job's change history, resolve flagged ambiguities ("two companies named Apex — which one?"), onboard a new target company (probing its careers site; if probing fails, Claude finds the careers URL itself and hands it back to the classifier), adjust criteria, regenerate a CV with different emphasis, start a census batch or read the census scoreboard. Claude reasons; the engine does. If Claude never connects, the daily loop still runs whole.

Third parties later: their own profile row, criteria, Notion token, and notification channel — same engine, same tools, data walled off by row-level security.

## Folder Structure

```
/goal-a-engine
├── LICENSE                           — MIT, Copyright (c) 2026 Shayan Das
├── /.claude/
│   ├── settings.json                 — Claude Code config, checked into git
│   ├── settings.local.json           — local overrides, gitignored
│   └── /skills/
│       ├── /builder-md/              — generates per-phase CLAUDE.md
│       └── /repo-analyst/            — end-of-phase codebase audit
└── /docs/
    ├── PRD.md                        — the confirmed product requirements
    ├── VISION.md                     — the vision log (what/why + every change; V-GAE IDs)
    ├── id-registry.json              — record-ID registry (high-water marks per kind)
    ├── CONTEXT.md                    — living glossary (created lazily)
    ├── architecture-decisions.md     — architectural decision log
    ├── decision-log.md               — phase-level decision log
    ├── dev.md                        — local developer runbook
    ├── /architecture/
    │   └── architecture-v2.md        — this document
    ├── /handoffs/                    — per-phase handoff + end-of-phase audit reports
    └── /specs/                       — UI specs (status page, Notion layout)
```

Source tree — existing modules stay, new ones each get one clear job:

```
├── /src
│   ├── config.py         — loads settings from .env, nothing personal in it
│   ├── /db               — database connection handling (exists)
│   ├── /criteria         — NEW: loads a profile's criteria and master CV facts from the DB
│   ├── /fetch            — ATS classifying and fetching (exists) + workday.py
│   ├── /discover         — NEW: sponsor-register walk, Adzuna/Reed clients, company onboarding;
│   │                       Phase 7.5 adds the census sweep (sweep.py + census_store.py) and the
│   │                       per-country registry plug-in (companies_house.py for the UK)
│   ├── /persist          — NEW: the write rules (dedupe upsert, job-rot, no-clobber) moved out of scripts and tested
│   ├── /history          — NEW: listing fingerprints, change events, deadline estimates
│   ├── /read             — AI spot #1: JD reading + keyword fallback + grounding eval (exists)
│   ├── /normalise        — AI spot #2: skill canonicalisation + the ONE shared text normaliser
│   ├── /analysis         — salary parsing (exists, dead code removed)
│   ├── /cv               — NEW: AI spot #3 — fact assembly, tailored wording, .docx rendering, truth check
│   ├── /notion           — NEW: files application cards into the Notion tracker
│   ├── /notify           — NEW: sends the phone nudges
│   └── /mcp_server       — NEW: the FastMCP server — thin tool wrappers only, zero logic
│                           (named mcp_server, never mcp: a local `mcp` package would shadow the SDK)
├── /scripts              — thin command-line runners (exists, stays thin)
├── /db/migrations        — full SQL history, including a new baseline of the pre-existing tables
└── /tests                — one suite per module, plus queue-ranking tests against a real test database
```

**Module rule:** every folder and file has a single clear job. No `utils`, `helpers`, `misc`, `common`, or `shared`. Name things by what they do. The end-of-phase Repo Analyst audit checks against exactly this standard.

## Security Foundations

- **The rotation gate stays law:** no hosted deployment, no public repo, no live third-party token until the original Supabase and Gemini credentials are confirmed rotated, with a dated note in the decision log.
- **Nothing personal or secret in code — ever.** Criteria, career facts, tokens: database or environment variables only. This is also what makes the third-party provision real.
- **Every database query stays parameterized** (audit confirmed 22/22 as of 2026-07-10; the standard holds for all new code), and every table keeps row-level security on.
- **The hosted MCP and status page ship with a bearer token, rate limits, and a hard monthly spend cap** — a public endpoint with a paid AI behind it never runs uncapped.
- **The engine never submits an application.** Even the apply-assist agent stops at a filled form; a human presses submit. A security boundary, not a preference.

## Performance Foundations

- Database writes go in batches, not one row at a time (audit counted ~3,600 single-row round trips per run); batching cuts minutes to seconds and matters once daily runs are unattended.
- Every outbound call (job boards, APIs, Gemini) gets timeouts plus retry-with-backoff, and each company commits independently — one failure costs one company, one run, nothing more.
- AI is never re-charged for work already done: every read, synonym, and CV records completion in the database (fixes the "zero-skill roles re-billed forever" leak).
- Beyond that: not a concern at this stage — revisit before opening to third parties.

## Licence & Legal Foundations

- **Project licence:** MIT.
- **Why:** This repo's second job is proving skill to hiring managers — MIT lets any engineer legally clone and run the showcase. It also permits future commercial use if the third-party version becomes a product.
- A `LICENSE` file at the repo root from Phase 1, "Copyright (c) 2026 Shayan Das", mirrored in `pyproject.toml`, referenced in the README.
- **Dependency landmines:** none present — five permissive dependencies plus psycopg (LGPL-3.0), fine as a pip-installed library; standing rule: never copy its source into the repo. New dependencies (FastMCP, python-docx, Notion SDK) are all permissive.
- Server-side product run by the founder — no NOTICES file needed. The public repo flip publishes a **fresh, squashed repository** (product-named, scrubbed of the project ref and leak narrative in old commits); the current repo stays private history.

---

# SECTION 2 — PHASE CARDS

Phases are ordered strictly by dependency. Pacing against the build brief: Phases 1–4 are the core-sprint material; Phases 5–7 the following week; Phase 8 lands "Job Engine, Live" by the 26 Jul milestone. Phases 9–10 are post-milestone options that must never displace applications — D-053 stands: build only while applying in parallel.

**Insertion (2026-07-11):** Phase 7.5 — The Census Sweep — was inserted between Phases 7 and 8 by founder direction: a rolling data-analysis layer over the whole register ("the actual analysis begins"), built before the system goes live. It reuses Phase 6's prober and fetchers wholesale and does not move the Phase 8 milestone's content.

**Insertion (2026-08-03):** Phase 8.5 — Universal Product Layer — inserted between Phases 8 and 9 by founder direction after the product walkthrough: the founder-first conveniences become universal, data-driven tools BEFORE multi-user plumbing, so Phase 9's security work lands on finished product surfaces. Sourced from plans/0010-walkthrough-findings.md.

**The phase relay (founder's working protocol, 2026-08-03):** one phase = one Claude Code chat. Every phase ends with the same five steps (decision log → progress log → archive CLAUDE.md → write the next phase's CLAUDE.md from its card here → hand the founder a short copy-paste prompt for the next chat). Everything feeds forward through the files, never through chat memory: decisions to `docs/decision-log.md`, vision-level shifts (what the product is / why it exists) to `docs/VISION.md`, shipped work to `docs/progress-log.md`, open items to `plans/`, the next phase to `CLAUDE.md`; record IDs come from `docs/id-registry.json`, never retyped into a phase card. A new chat needs nothing but the repo.

---

## PHASE 1 — FOUNDATION RESET & HARDENING

**What this phase builds:**
Turns the existing engine from "works when hand-run" into a core that can be trusted unattended. Fixes the live data bug, adds resilience everywhere, clears the audit's criticals, and resets the repo's paperwork (licence, honest docs, pinned dependencies).

**Depends on:** Nothing — this is the foundation. One human prerequisite: the founder rotates the initial Supabase password, secret key, and Gemini key, and confirms it. No commit or live API call before that confirmation.

**Tasks — in order:**
1. Record the rotation confirmation with date in `docs/decision-log.md`; verify the new Gemini key works with one live call.
2. Add `LICENSE` (MIT, real copyright line), licence + author metadata in `pyproject.toml`, licence section in README; commit the pending `.gitignore` line for PROJECT-MEMORY.md and add `.env.*` patterns (with `!.env.example` re-include).
3. Create the `/docs` structure; write `docs/PRD.md` from the confirmed vision; retire the stale CLAUDE.md content into an honest status doc (only GA-001-closure, the per-SOC salary wall, and GA-011 remain open from the old plan).
4. Fix `is_uk()` test-first: pinning tests for "Cambridge, MA", "Reading, PA", "London, Ontario, Canada" must fail, then harden the matcher; re-run over stored listings to purge false UK rows.
5. Add retry-with-backoff to all job-board fetches and all Gemini calls; test with simulated 429/503 responses.
6. Change the fetch run to commit per company, and make an empty feed mark the company "empty" without closing its listings until two consecutive empty runs; tests first.
7. Make synonym building persist each batch as it returns, surviving a mid-run failure; test first.
8. Fix the read-once guard: record extraction completion on the listing itself (e.g. `extracted_at`) so zero-skill roles are never re-billed; test first.
9. Create `src/persist` — move the dedupe upsert, job-rot, and no-clobber write rules out of scripts into tested modules; scripts become thin runners.
10. Create the single shared text normaliser in `src/normalise`; delete the two duplicate copies; delete the dead salary `classify()` function, its constants, and the dead `GENERAL_SALARY_THRESHOLD` env hook; add a golden-value test pinning the dedupe fingerprint.
11. Move dependencies into `pyproject.toml` with version pins and a lock file; batch all row-by-row database writes with `executemany`; add a unique rule on the constraints table so a duplicate threshold row can't break the queue.

**Done looks like:**
- Full test suite green, including new tests for every rule that previously lived untested in scripts.
- A deliberately unplugged-network test run loses at most one company and completes.
- "Cambridge, MA" cannot enter the database; existing false rows are gone.
- LICENSE visible at repo root; a fresh `pip install` reproduces the exact environment.

**Complexity:** Moderate

**Specialist Requirements:** None — Claude Code can handle all tasks in this phase with the CLAUDE.md instructions.

---

## PHASE 2 — CRITERIA, PROFILE & THE CORRECT SALARY WALL

**What this phase builds:**
All personal data moves into the database under a profile, making the engine person-agnostic (the third-party provision). The salary wall finally judges against the correct per-occupation going rate.

**Depends on:** Phase 1.

**Tasks — in order:**
1. Migration: `profiles` table (id, name, contact, notification channel, Notion token reference); one row for the founder; every personal table (`my_skills`, `my_constraints`, `target_roles`, target companies) gains an `owner_id` linked to it. Views become owner-aware.
2. Create `src/criteria`: one module that loads a profile's full criteria set; every script and pipeline stage reads criteria through it — grep proves no personal value remains hardcoded.
3. Seed the per-occupation going-rates table from the occupation data already in the database (verified against gov.uk figures); write the row-count and spot-check evidence into the decision log.
4. Populate each listing's occupation code from the AI reader's occupation hint; link it to the going-rates table.
5. Rebuild the queue's salary wall to compare against the listing's own occupation going rate, falling back to the profile's flat threshold when no occupation is known; remains advisory, never a filter.
6. Add queue-ranking tests against a disposable test database: load migrations, insert crafted listings, assert ranking order, sponsor precedence, wall verdicts, and UK guard.
7. Resolve the redundant `clears_wall`/`soc_tier` columns (drop them; the view computes).

**Done looks like:**
- The queue shows "clears wall" against the real going rate for the role's occupation (~£52–55k for IT roles, not flat £41,700).
- Deleting the founder's profile row and inserting a fictional person's profile runs the whole pipeline for them without touching code.
- View logic failures are now caught by tests, not discovered in production.

**Complexity:** Moderate

**Specialist Requirements:** None.

---

## PHASE 3 — JOB HISTORY & CHANGE TRACKING

**What this phase builds:**
The system's memory. Every listing gets a life story: when first seen, what changed and when, when it closed, and a best-estimate apply-by date.

**Depends on:** Phase 2.

**Tasks — in order:**
1. Migration: `listing_events` table (listing, event type: appeared/changed/closed/reopened, timestamp, what changed) plus a content fingerprint column on listings.
2. Create `src/history`: fingerprint each fetched listing; on change, store the event with a field-level diff (title, salary, description); tests with crafted before/after pairs.
3. Reopened-listing handling: a closed listing that reappears logs "reopened" rather than duplicating; test first.
4. Deadline estimation: extract explicit deadlines when stated; otherwise compute an advisory apply-by from posting age and the profile's urgency setting — always labelled as an estimate; tests for both paths.
5. Changed listings whose description changed get re-read by the AI (a change resets read-once for that listing only); test that unchanged listings are never re-billed.
6. Queue and CLI surface history: age, "changed 2 days ago", estimated apply-by.

**Done looks like:**
- Asking about any listing answers: seen when, changed what and when, closed when, apply by when.
- A listing whose salary was edited on the company's site shows that edit within one daily run.
- Re-runs on unchanged data produce zero new events and zero new AI spend.

**Complexity:** Moderate

**Specialist Requirements:** None.

---

## PHASE 4 — THE AUTOMATIC LOOP: SCHEDULER, RUN REPORTS & NUDGES

**What this phase builds:**
The system starts working without the founder. One daily scheduled run executes the entire pipeline — including the stages that were previously manual — and the phone gets a nudge when something is worth acting on.

**Depends on:** Phase 3.

**Tasks — in order:**
1. Extend the orchestrator to run all stages in order (fetch → history → read → synonyms → salary → grounding eval), recording a structured run report (per-stage counts, failures, cost) in a `runs` table; test the sequencing with stubbed stages.
2. Create `src/notify` with an ntfy client; profile stores the channel; test with a mocked endpoint.
3. Nudge policy in code, test-first: notify only for listings that newly entered the queue AND pass every hard gate (UK, sponsor signal, fit rank, wall-advisory attached); batch into one daily digest; never re-nudge the same listing.
4. Failure nudges: a run that dies or a grounding eval below threshold pings the founder with the reason — silence must never mean "nothing found" when it actually means "it broke."
5. Local scheduling: a launchd job running the daily pipeline, with a lock so overlapping runs can't collide; documented in `docs/dev.md`.
6. A `--dry-run` mode that reports what it would nudge, for safe testing.

**Done looks like:**
- Three untouched days; each morning the run executes and the phone shows either "N roles ready", nothing (genuinely nothing new), or "run failed: reason".
- The runs table shows three clean daily reports with per-stage numbers.

**Complexity:** Moderate

**Specialist Requirements:** None.

---

## PHASE 5 — THE MCP SERVER: CLAUDE BECOMES THE BRAIN

**What this phase builds:**
A FastMCP server exposing the engine as ~14 clean tools, so Claude can direct everything conversationally: inspect the queue, explain rankings, adjust criteria, trigger runs, resolve flagged ambiguities. Zero logic lives in the server — it is a skin.

**Depends on:** Phase 4 (the engine must be worth directing).

**Tasks — in order:**
1. Create `src/mcp/server.py` with FastMCP over stdio; tool registry pattern — each tool is a named wrapper around one existing engine function with typed inputs/outputs.
2. Read tools: `get_apply_queue`, `get_job`, `get_job_history`, `get_skill_gaps`, `get_run_report`, `get_criteria`.
3. Action tools: `set_criteria`, `add_target_company`, `mark_applied`, `snooze_listing`, `run_pipeline` (with dry-run flag), `send_test_nudge`.
4. Review tools: `list_review_flags`, `resolve_review_flag` — the queue of ambiguities code couldn't decide (built now, filled by Phase 6's discovery).
5. Every action tool writes an audit row (who/what/when) — provisional-until-confirmed extends to Claude's actions.
6. Test suite driving the server through a real MCP client harness: call every tool, assert schemas and effects.
7. Register the server with Claude Code/Desktop locally; document the setup in `docs/dev.md`.

**Done looks like:**
- In Claude: "show my queue, why is #3 above #4, mark #1 applied, tighten my salary floor to £45k" — the engine obeys through tool calls.
- Killing the MCP server changes nothing about the daily automatic loop.
- Every tool has a passing test through the MCP protocol itself.

**Complexity:** Moderate

**Specialist Requirements:**
- **Task:** MCP server design (tools, schemas, transport).
- **Why general Claude Code is not enough:** MCP has evolving protocol specifics (transports, schema conventions, auth patterns for the hosted mode) where stale training knowledge produces subtle incompatibilities.
- **Specialist needed:** the claude-api / MCP reference skill during build.
- **What it needs to do:** supply current FastMCP idioms and transport/auth patterns that the CLAUDE.md tasks then follow.

---

## PHASE 6 — THE DISCOVERY ENGINE: AUTOMATIC JOB SEARCH

**What this phase builds:**
The system starts finding jobs the founder never pointed it at: walking the sponsor register by criteria, probing discovered companies' job boards, reading Workday boards, and pulling matching roles from the Adzuna and Reed APIs — with ambiguous cases flagged for Claude to resolve rather than guessed.

**Depends on:** Phase 5 (Claude resolves discovery's ambiguities through the review tools).

**Tasks — in order:**
1. Create `src/discover/register.py`: walk the licensed-sponsors table filtered by profile criteria (region, industry hints), emit candidate companies not yet targeted; test with a seeded register slice.
2. Auto-onboarding pipeline: candidate → existing job-board prober → classified companies join the fetch list automatically; unclassifiable ones become review flags with the probe evidence attached; test both paths.
3. `discover_company` MCP tool: name any company; code probes; on failure the tool returns evidence so Claude can hunt the careers URL and hand it back to `classify_from_url`.
4. Workday adapter in `src/fetch/workday.py` against the recorded response shapes of 3 real target companies' boards, mocked in tests; feeds the standard pipeline.
5. `src/discover/aggregators.py`: Adzuna and Reed API clients (free keys), querying by profile criteria; results normalised into the standard job shape; test with recorded fixtures.
6. Sponsor cross-check: aggregator-discovered employers matched against the register (exact + normalised name); uncertain matches become review flags, never silent guesses; test the matcher with tricky name pairs.
7. Discovery runs join the daily schedule with per-source caps and per-source run-report lines.

**Done looks like:**
- The morning digest includes roles from companies never listed, each with a sponsor-register verdict attached.
- Naming any company in Claude either onboards it live or shows exactly why it can't be fetched.
- Workday roles from at least 3 previously-invisible target companies flow through reading, ranking, and history like any other listing.

**Complexity:** Complex

**Specialist Requirements:**
- **Task:** Workday adapter and aggregator integrations.
- **Why general Claude Code is not enough:** third-party API response shapes and quirks (Workday's tenant-specific endpoints, Adzuna/Reed auth and rate rules) need live verification against current documentation, not assumptions.
- **Specialist needed:** an API-integration research pass (web-enabled) before implementation.
- **What it needs to do:** capture real, current response samples and endpoint contracts for the CLAUDE.md tasks to code against.

---

## PHASE 7 — CV MAKER & NOTION FILING

**What this phase builds:**
For every listing that clears the gates, a tailored ATS-friendly CV is generated from verified career facts and filed with the job's full details into a Notion application tracker. The nudge now carries a Notion link: everything needed to apply, one tap away.

**Depends on:** Phase 4 (the loop) — runs after Phase 6 lands.

**Tasks — in order:**
1. Migration: `cv_blocks` table under the profile — verified career facts (roles, achievements, skills evidence, education) as structured blocks; loaded from the founder's current CV, human-confirmed.
2. Create `src/cv/assemble.py`: pure code selects and orders relevant blocks for a listing by matching its extracted skills against block evidence; deterministic, tested.
3. AI spot #3, caged like the others: Gemini phrases the selected blocks into tailored bullets under an "only rephrase supplied facts, add nothing" instruction; fallback = un-rephrased blocks; tests with mocked responses.
4. Truth gate, test-first: every claim in the output must trace to a source block (reusing the grounding-eval approach); any untraceable sentence fails the CV and falls back.
5. `src/cv/render.py`: single-column ATS-safe .docx via python-docx; golden-file test.
6. Create `src/notion`: application tracker database (Job, Company, Status, Deadline estimate, Sponsor evidence, Queue rank, CV file, Listing link); one card per gated listing; idempotent updates; test against a mocked API.
7. Wire into the daily loop: gate-passing listings get CV + Notion card before the nudge; nudge text includes the Notion link. `generate_cv(listing, emphasis)` becomes an MCP tool so Claude can re-tailor on request.

**Done looks like:**
- Morning nudge → Notion card → attached tailored CV whose every line is true → job link. Apply in minutes.
- Two different roles produce visibly different CVs from the same fact base, with zero invented claims (spot-check plus truth-gate evidence).
- Marking a card "Applied" in Notion syncs back to the engine on the next run.

**Complexity:** Complex

**Specialist Requirements:**
- **Task:** CV document generation.
- **Why general Claude Code is not enough:** .docx internals and ATS-safe formatting have library-specific pitfalls.
- **Specialist needed:** the docx skill during rendering tasks.
- **What it needs to do:** produce the template and rendering patterns the tasks code against.

---

## PHASE 7.5 — THE CENSUS SWEEP: THE REGISTER BECOMES A DATASET (inserted 2026-07-11)

**What this phase builds:**
Peace of mind, as data. A resumable nightly batch machine that works through every one of the ~110k unique organisations on the sponsor register (~142k rows, deduped by normalised name) and writes each a census card: does it have a discoverable job board, what jobs does it post (titles, locations, **real links**), and what kind of company it is — official industry codes, active/dissolved status, age — from the national company registry (Companies House for the UK, wired as a swappable per-country plug-in). Gemini is never called by the sweep; job titles are keyword-matched against the owner's role patterns. The daily loop is untouched: the sweep writes ONLY to its own two tables (`sponsor_census`, `census_jobs`) — never `target_companies` (the fetch stage would start fetching every board it finds) and never `review_items` (~100k no-board flags would drown review). Promotion census→tracked stays a deliberate act via the existing onboarding tools.

**Depends on:** Phase 6 (reuses its prober, fetchers, matcher and norm wholesale). Inserted before Phase 8 by founder direction — the analysis layer should exist and be filling before the system goes live.

**Tasks — in order:**
1. Migration 0030 — `sponsor_census` (one row per unique org: the cursor + probe findings + registry findings, country-neutral column names, `country` default 'uk') and `census_jobs` (lightweight job rows, unique shared dedupe key, no JD body) — applied via Supabase MCP, mirrored to `db/migrations/`, RLS on, advisors checked; plus `src/discover/census_store.py`: every census SQL write and the status counts, tested against cursor fakes with one opt-in DB test.
2. `pick_batch` + `load_tracked_orgs` in `src/discover/sweep.py`: the next-N picker (groups register rows by `org_name_norm`, skilled-worker/A-rated first, `NOT EXISTS` anti-join against `sponsor_census`, `--retry-errors` variant) and the tracked-org map (normalised names plus register-linked names, so already-tracked orgs get marked `already_tracked` without re-probing and the remaining count converges).
3. `probe_org` + `run_sweep`: classify (existing prober) → on a board, fetch ONCE → local-filter (behind a `_is_local` seam) → store census jobs capped per org; fetch failure keeps `board_found` with the error noted; per-org error isolation and per-org commit (exact crash-resume, transactions stay milliseconds-short); polite pacing via a swappable sleep; sequential with one shared HTTP session — no threading. Pin test: the sweep never writes `target_companies` or `review_items`.
4. The registry plug-in `src/discover/companies_house.py` + `COMPANIES_HOUSE_API_KEY` config (`ch_ready` property, Reed-style Basic auth): search → deterministic name match (exact norm; unique legal-suffix-stripped; single-active-candidate disambiguation; otherwise ambiguous/not-found recorded, never guessed) → profile → industry codes; 0.6 s pacing under the 600-per-5-minute limit with the standard 429 backoff. The sweep imports it as `registry` — the one-line country seam.
5. `scripts/sweep.py` thin runner: `--batch` (default 2000) / `--pause` / `--retry-errors` / `--probe-only`; its own `.sweep.lock` (sweep and daily pipeline coexist; two sweeps cannot); `[sweep]` progress lines and a totals summary; per-item errors never fail the run.
6. MCP census tools in `src/mcp_server/census_tools.py`: `run_sweep(batch_size)` spawning the script **detached** with a log under `ops/sweep-logs/` (a multi-hour sweep must never block a chat call) and read-only `sweep_status()` (counts by outcome, boards, jobs, matches, remaining); registered alongside the existing registrars; toolset contract 17 → 19.
7. Docs + live smoke: dated decision-log and progress-log entries; `docs/dev.md` tool count corrected to 19 with the missing tool rows and a "run the census sweep" section; a 25-org live run verifying outcome mix, real links, resumability, the lock, and that `target_companies`/`review_items` counts did not move.

**Done looks like:**
- `sweep_status` answers "N of ~110k censused · X boards found · Y jobs recorded · Z registry-matched" and the number climbs every night it runs (default pace ≈ 2,000/night ≈ full coverage in ~2 months).
- Any register organisation can be looked up: its card says board or no board with evidence, its jobs with real links, its industry code, active or dissolved.
- The daily pipeline's tables and runtime are provably unchanged; all pre-existing tests still green.
- Swapping countries later = new register data + one new registry plug-in module; nothing else changes shape.

**Complexity:** Moderate

**Specialist Requirements:** None — the Companies House response contract is verified against the live developer documentation during Task 4 (the same in-session web verification used for Phase 6's adapters), with the confirmation date noted in the module header.

---

## PHASE 7.8 — THE PRODUCT CORE: ONE QUEUE, RULES, MATH & THE DASHBOARD (inserted 2026-08-02)

**What this phase builds:**
The two halves become one machine. Every job the system knows — career-page listings, census doors, and the 9,196 sponsor-matched aggregator ads — flows through the three sieves (register → profile facts → deep read) into ONE ranked queue; census promotion becomes a per-owner RULE evaluated nightly instead of a manual button; the deep read becomes a staged work-queue that any user's own AI drains over MCP (server-side versioned prompts, deterministic grounding verification at the submission boundary — the engine itself runs NO new AI); a small pure math core makes every number explainable (overlap × rarity scoring with receipts, smoothed confidence with sample sizes, name/job match probability, freshness decay, survival-curve deadlines); and a read-only dashboard shows only what matters — Today: ready-to-apply vs needs-something, plus the honesty panel. The founder keeps applying from the queue every morning throughout the build.

**Depends on:** Phases 1–7.5 plus the July insertions (keep-all 0035, aggregator machine 0036, completed collection pass). Inserted before Phase 8 by founder direction (2026-08-02): the cloud should lift a finished product core, and the sieve-3 architecture (user-side AI) must exist before a hosted MCP means anything.

**Tasks — in order:**
1. **Math core** — `src/match/score.py` (skill-overlap × rarity weighting; returns the score AND its receipts: matched, missing, weights), `src/match/stats.py` (percentile salary summaries; Laplace-smoothed confidence that always carries its sample size), `src/match/decay.py` (half-life freshness weight). Pure functions, no DB, no AI, no network; exhaustive unit tests first.
2. **Match probability** — `src/match/prob.py`: employer-name match probability (evidence combination: exact norm, suffix-stripped, town, industry agreement) and same-job probability across sources (fingerprint exact + near-title/town/salary). Tests on the tricky-name pairs already in the decision log (Monzo/Thought Machine class). Orders the uncertain pile; powers the merge.
3. **Wire 2 — the merge** — `src/discover/merge.py` + migration 0037 (merge bookkeeping columns on `aggregator_ads`; nothing destructive — the ads layer stays keep-all): register-matched + local + direct-employer ads become `role_listings` rows (`source` set, shallow until a JD is known), deduplicated against existing listings via `prob.py` so a board listing is never duplicated; per-batch commit; joins the daily loop after discovery. Blast-radius pin: the merge writes `role_listings` only for register-matched ads.
4. **Rule-based promotion** — `src/discover/promote_rule.py` + migration 0038 (`promotion_rules`: one row per owner — industry-code set, uses the owner's `target_roles` for titles, minimum local jobs, auto flag): nightly evaluation auto-promotes census `board_found` cards that pass the owner's rule (reuses `promote.py`: audited, board copied, register-only confidence); borderline cases → a capped `promotion_review` flag; manual `promote_company` stays as the override. The census blast-radius wall survives — the rule IS the audited crossing; the pin test is updated consciously. Founder's rule is seeded from his current criteria.
5. **Sieve-3 staged reading** — `src/reading/` + migration 0039 (read quality `keywords|ai`, staged/claimed timestamps, provenance): `stage.py` (sieve-1/2 survivors with a JD and no AI read), `serve.py` (batches + the versioned server-side extraction prompt + required JSON shape), `accept.py` (deterministic grounding verification reusing `read.eval` — every claimed skill/number must appear in the stored JD text; rejects recorded, rows upgraded in place; idempotent; owner-scoped). The existing keyword fallback stays the engine's own default so the daily run never waits on AI.
6. **MCP contract v2** — `daily_brief` (the agenda tool), `get_reading_batch`/`submit_reading`, `get_promotion_rule`/`set_promotion_rule`; EVERY tool result gains a uniform `next` block (state, suggested next call, why) so any vendor's AI can run the loop with zero client-side prompting; all tool descriptions rewritten to the what/when/returns/what-next contract; exact-toolset pin test updated. The MCP stays a skin — zero logic.
7. **Survival deadlines** — `src/history/survival.py`: per role-family open-duration curves from `listing_events` (appeared→closed pairs); estimated deadlines become evidence-based ("roles like this fill in ~N days", `deadline_source='survival'`), flat-window fallback where history is thin; wired into the deadline stage.
8. **The dashboard** — `src/dashboard/` + read-only views (0040: `v_today`, `v_scorecard`, `v_health`): a small, framework-light, token-protected local web page — Today screen (ready-to-apply vs needs-something, each row with its receipts), the honesty panel (coverage, last-checked, read-quality mix), company watch. Complexity-hiding pinned by test: the page can read ONLY the curated views, never raw tables; no personal data beyond the owner's own rows. Runs by command; Phase 8's container carries it to the cloud unchanged.
9. **Heartbeat glue + register refresh** — the daily loop gains its new stages in order (discover → fetch → keyword-read → merge → rule-promotion → salary → deadlines → eval → stage-reading → file → nudge); NEW `scripts/refresh_register.py` (weekly re-download of the sponsor register, diff → licence-added/removed recorded, census cards stamped — closes the "register never re-downloaded" gap found 2026-08-02); docs + logs + a live smoke proving one queue with all three sources visible and the founder's rule promoting nightly.

**Done looks like:**
- One queue holds jobs from career pages AND matched ads; every row shows its score WITH receipts — what matched, what's missing, what would close the gap.
- Census companies promote themselves nightly through the founder's rule; only genuinely unclear cases wait in a short review list; no promote button pressed by a human.
- With zero AI connected the daily run completes end-to-end (keyword reads, honestly labelled); when the founder's AI connects over MCP, `daily_brief` hands it the agenda, the reading tray drains, and rows upgrade in place — with the grounding gate provably rejecting ungrounded claims.
- Deadlines cite the machine's own history ("data roles at fintechs fill in ~9 days"), not a flat guess.
- The founder opens one page and sees ready-to-apply / needs-something / machine health — and nothing else; the no-raw-tables rule is pinned by test.
- The register refreshes itself weekly; all pre-existing tests stay green.

**Complexity:** Complex

**Specialist Requirements:**
- **Task:** 8 (the dashboard).
- **Why general Claude Code is not enough:** the screen's whole value is information design — what to hide, what to surface, how state reads at a glance; that needs design judgement, not just working code.
- **Specialist needed:** the ui-designer skill (already available to this workspace).
- **What it needs to do:** produce the Today-screen layout and visual system (built on the 2026-08-02 explainer artifact's design language) that Claude Code then implements against the curated views.

---

## PHASE 8 — GOING LIVE: CLOUD RUN, STATUS PAGE & THE PUBLIC FLIP

**What this phase builds:**
The system leaves the laptop: daily pipeline as a scheduled Cloud Run Job, hosted MCP behind a token, a public status page proving it's alive, and the portfolio repo published clean. The build brief's "Job Engine, Live" milestone.

**Depends on:** Phase 7 (and the inserted Phase 7.5 — the census sweep should be running before the flip; its nightly batch becomes a second scheduled Cloud Run Job in this phase's Task 2 pattern). Also the inserted Phase 7.8 — the cloud lifts a finished product core (one queue, rules, staged reading, dashboard), not a half-wired machine.

**Tasks — in order:**
1. Containerize (Dockerfile + config from environment only); the container runs pipeline, MCP server, or status page by command.
2. Cloud Run Job + Cloud Scheduler for the daily run; secrets in Google Secret Manager; local scheduler retired; failure nudges confirmed working from the cloud.
3. Hosted MCP: FastMCP's HTTP transport on a Cloud Run service behind a bearer token; rate limits enforced and tested. (Spend cap retired with Gemini 2026-08-03 — the engine pays for no AI; the cap returns if a paid spot ever does.)
4. Public status page (no auth): last run time, listings tracked, companies covered, per-stage health — read-only, revealing no personal data.
5. CI: GitHub Actions running the full suite on every push; deploy on green main.
6. Pre-flip security pass: scrub project ref and leak narrative from all docs; verify rotation note; run the security review.
7. The flip: fresh product-named public repo from a squashed, scrubbed snapshot (LICENSE, honest README with architecture diagram and demo GIF); private repo stays as working history.

**Done looks like:**
- The pipeline runs daily with the laptop shut; nudges still arrive.
- Anyone can view the status page; only the founder can use the MCP or see personal data.
- A public repo a hiring manager can clone and run with their own keys — with a live URL to prove it. Portfolio milestone met.

**Complexity:** Complex

**Specialist Requirements:**
- **Task:** Pre-flip security pass.
- **Why general Claude Code is not enough:** publishing + a public endpoint with paid AI behind it warrants an adversarial security review, not self-review.
- **Specialist needed:** the security-review skill.
- **What it needs to do:** verify no secret/personal leakage, auth on every private surface, caps and rate limits enforced, before anything goes public.

---

## PHASE 8.5 — UNIVERSAL PRODUCT LAYER: ONE LENS → ANY LENS (INSERTED 2026-08-03)

**What this phase builds:**
The founder-first conveniences become universal, data-driven tools: a user's words become rows (never code edits), any industry works the way software already does, and the dashboard learns to browse the whole sponsor world. This is the onboarding spine for any non-software user, sourced from the founder's walkthrough findings (plans/0010, items 3–8, 10, 14).

**Depends on:** Phase 8 (the hosted MCP is where these tools meet users; the dashboard ships hosted too).

**Tasks — in order:**
0. **CV by user-side AI (founder direction 2026-08-03 — FIRST task of this phase).** The CV becomes the reading tray's twin: a versioned server-side prompt (`cv-v1`, ATS-safe rules baked in, client can never override it) serves the job + **ALL of the owner's confirmed cv_blocks** → the connected AI (Cowork automation or any MCP client) selects what is relevant and writes structured CV content → `submit_cv` passes the deterministic truth gate (every claim grounded in stored facts — reuses the existing CV gate) → the ENGINE renders the final ATS-safe .docx itself (format is engine-owned, never client-owned). **Serve-all, never pre-filter (founder correction 2026-08-03):** the engine's skill matching is literal and would silently hide transferable evidence the AI could have used, and a hidden fact is unknowable to the client; assemble.py's relevance match degrades to an optional HINT ("these blocks share skill words with this job"), never a filter. AI decides relevance; code decides truth. (Gemini already fully retired 2026-08-03 — the key is never set anywhere; until this task lands, CV assembly uses the plain-facts fallback: truth-gated, no AI, plainer wording.) Depends on cv_blocks being seeded (the founder's facts session).
1. Words→codes translator: user words ("care homes") → `sic_codes` description search → matched codes written into THEIR promotion rule; plus the missing skills-entry tool (owner-scoped `my_skills` writes). Principle pinned: user words never edit code — they become rows.
2. Owner-lens sweep: `run_sweep` + aggregator stages read the owner's rule codes (retire the hardcoded software-only convenience); Adzuna category becomes per-owner.
3. Universal read tools: `search_sponsors` (any industry/town/board-status over `v_sponsor_industry`), role-lens search, skills-gap search — generalised from the software-only conveniences.
4. Dashboard: Sponsors browse tab (new curated view + complexity-pin extension), fit-score column in `v_today`, "new today" chip.
5. Reed job-detail drip: a capped nightly stage fetching full JDs for the highest-value ad-only jobs (~950 free calls/day budget) — descriptions for the reading tray regardless of lens.
6. End-to-end lens proof: a care-home test lens set up by conversation alone (via MCP tools) produces a correct queue with receipts — no code edits anywhere.

**Done looks like:**
- A non-software lens works end-to-end by talking: words → rows → nightly run → morning queue with receipts.
- The dashboard browses all 128k sponsors by plain-English industry.
- Ad-only jobs gain full descriptions through the drip; the tray serves them like board jobs.

**Complexity:** Medium

**Specialist Requirements:**
- **Task:** Sponsors browse tab layout.
- **Specialist needed:** ui-designer skill, only if the tab outgrows the existing Railway-DNA components.

---

## PHASE 9 — THIRD-PARTY READY (WHEN THE FOUNDER CHOOSES)

**What this phase builds:**
The provision becomes real: other people sign up, define their criteria, connect their own Notion and notifications, and run their own job search on the hosted system. Optional — activate after Goal A allows.

**Depends on:** Phases 8 + 8.5 (multi-user plumbing lands on finished product surfaces).

**Tasks — in order:**
1. Friend tier FIRST — founder-minted per-user keys, no sign-in system: the hosted server resolves every call to its owner (token→owner_id); tests proving cross-user isolation (user B can never read user A's rows).
2. Row-level-security policies on ALL tables (4 of 24 done as of 2026-08-03) — the database itself checks the owner stamp on every row; adversarially tested.
3. Per-owner nightly pass: world work runs once (register, census, ads); the personal pass (match, promote, stage, brief, nudge) loops per owner, each with their own notification channel.
4. Onboarding flow via MCP tools (`create_profile`, guided criteria setup over the Phase 8.5 translator, own Notion token, own notification channel) — a new user reaches their first nudge without operator involvement.
5. Per-user AI budgets and per-source caps so one user can't spend everyone's quota.
6. Stranger tier LAST — sign-in switched on: Supabase Auth, username+password shape with email confirmation OFF (decision 2026-08-03; free plan covers 50k monthly users); self-serve key issue + one-click revoke.
7. Operator docs: `docs/runbook.md` — adding users, rotating tokens, reading run reports, incident basics.

**Done looks like:**
- A test user with different criteria onboards end-to-end and gets their own correct, isolated nudges and CVs.
- Isolation proven by tests, budgets enforced.

**Complexity:** Complex

**Specialist Requirements:**
- **Task:** Multi-user isolation.
- **Why general Claude Code is not enough:** row-level-security policy mistakes fail silently and leak data across users.
- **Specialist needed:** security-review skill against the RLS policies and MCP auth path.
- **What it needs to do:** adversarially attempt cross-user access and verify every path is walled.

---

## PHASE 10 — APPLY-ASSIST AGENT (STRETCH)

**What this phase builds:**
The last mile: a browser-driving agent that opens an application, fills every field from the profile and the tailored CV, uploads the file — and stops. The human reviews and presses submit. The hard boundary (never auto-submit) is enforced in code, not by promise.

**Depends on:** Phase 7 (CVs). Deliberately last: highest risk, lowest necessity.

**Tasks — in order:**
1. Per-system form maps for the three most common application forms in the queue (Greenhouse first), from real form structures.
2. Browser automation (Playwright) filling mapped fields from profile + CV data, screenshotting each step; hard stop before any submit control — enforced and tested (the agent cannot click elements matching submit patterns).
3. Unmapped-field handling: agent pauses and asks (via Claude/MCP) rather than guessing.
4. `prepare_application(listing)` MCP tool: launches the fill, returns screenshots and the handoff point; audit row per run.
5. A terms-of-service check per ATS domain recorded in the decision log — automation runs only where permitted; a domain that forbids it gets a "manual apply" label in Notion instead.

**Done looks like:**
- For a real Greenhouse posting: one command → filled form with CV attached → screenshots → the human presses submit.
- The submit-block test proves the agent physically cannot complete a submission.

**Complexity:** Complex

**Specialist Requirements:**
- **Task:** Browser automation.
- **Why general Claude Code is not enough:** live form-filling against real sites needs interactive verification and judgment about dynamic pages.
- **Specialist needed:** browser/computer-use tooling driven interactively, plus ToS verification per target.
- **What it needs to do:** validate each form map against the real site and capture the evidence trail before the map is trusted.
