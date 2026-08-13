# 0013 — Universal user: the full spec for "one lens → any lens"

- **Status:** ✅ Built — U1–U8 in Phase 8.5, §6 M1–M4 in Phase 9. **Only M5 remains, note-only by its own instruction**
- **Created:** 2026-08-10 · **Last updated:** 2026-08-10
- **Depends on / blocked by:** Phase 8 tasks 2–3 live (cloud job ✅, hosted MCP ⛔ founder gate). Nothing here blocks the 06:30 lane.
- **Owner / last touched by:** Claude session 2026-08-10 (the universality audit)
- **Relates to:** 0012 §3 (the Phase 8.5 checklist this expands), 0010 (items 3–8, 14, 17), 0011 (saved watches — after this), 0008 (third-party product)

## Goal

Answer, with evidence and a build list, the founder's question: *"is this wired
only for me, and how does anyone else use it for non-software jobs?"*

**Verdict from the audit (2026-08-10): the machine is universal in what it
COLLECTS and in how it DECIDES; it is personal only in what work has been RUN.**
Nothing needs redesigning. Five bricks are missing, and one backlog needs
running per new lens.

---

## 1 · The measured evidence (2026-08-10, live DB)

Door-knock coverage by industry — the whole argument in one table:

| Industry lens | Sponsors identified | Doors knocked | Boards found |
|---|---|---|---|
| Software (founder's lens) | 11,931 | **11,726 (98%)** | 256 |
| Care homes / social work | 6,261 | 43 (0.7%) | 2 |
| Restaurants / hotels | 10,295 | 31 (0.3%) | 0 |
| Retail / wholesale | 15,996 | 84 (0.5%) | 1 |
| Health / medical | 4,004 | 30 (0.7%) | 0 |
| Everything else | 50,151 | 767 (1.5%) | 30 |

Ads layer, already stored and lens-independent: **104,761 ads** — 2,249
care/support-worker titles · 3,235 driver/warehouse · 702 nursing · 633
chef/kitchen.

**Reading:** collection never filtered by industry (every sponsor is on the
register and carries its Companies House code; Reed sweeps all industries).
The 98%-vs-0.7% gap is **queue ORDER**, not capability — the knocker ran
software-first because that is the only lens that has ever existed.

## 2 · What is actually hardcoded (the complete list)

Audited 2026-08-10. Four spots, none of which decides anything *for a user*
(user decisions read rows: `promotion_rules`, `target_roles`, `my_skills`,
`my_constraints`):

1. `discover/classify.py::SOFTWARE_SIC` — a 10-code counting lens.
2. `discover/probe_pick.py` — **the real blocker**: Pass-2 hands out only
   registry-matched **software-SIC** cards, so door-knocking cannot serve
   another lens without a parameter.
3. `discover/sweep.py::TECH_NAME_PATTERN` — ORDERING only (explicitly never a
   filter); bootstrap scaffolding from before the census had industry codes.
4. Adzuna category pinned to `it-jobs` (a parameter, not baked in). Reed is
   already all-industry — that is the safety net for every non-software lens.

Plus one tool-level artefact: `list_software_companies` (founder-first
convenience; the universal version is task U3 below).

## 3 · The build list (all recommendations, ordered)

Each maps to a Phase 8.5 task in 0012 §3. **Test before code, as always.**

**U1 · Owner-lens sweep** *(0012 task 2 — the keystone)*
`probe_pick` takes the owner's rule codes instead of `SOFTWARE_SIC`;
`run_sweep`'s `software_only` flag becomes `owner_lens`. Adzuna category
becomes per-owner. `TECH_NAME_PATTERN` stays as ordering, or generalises to
"name looks like the owner's industry" — never a filter either way.
*Acceptance:* a care-home rule causes care-home cards to be picked and probed;
no code edit between the two lenses.

**U2 · Words→codes translator + skills-entry tool** *(0012 task 1)*
"care homes" → search `sic_codes` descriptions → matched codes written to
THEIR `promotion_rules` row. Skills tool writes owner-scoped `my_skills`.
**Requirement pinned from day one:** skills rows carry `learned_at` +
evidence text, so the learning-curve model (0010 item 16) has data the day it
is built. *Acceptance:* a lens is set by conversation alone; zero operator SQL.

**U3 · Universal read tools** *(0012 task 3)*
`search_sponsors` (any industry / town / board-status over
`v_sponsor_industry`), role-lens search, skills-gap search. Generalise, do not
duplicate, `list_software_companies`. *Acceptance:* "show me care-home
sponsors in Leeds with live boards" answers over the existing view.

**U4 · Knock-on-demand for a new lens** *(NEW — this plan's addition)*
A new user's slice has ~0.7% coverage on arrival. On lens creation, enqueue
their unknocked cards at the FRONT of the probe queue (a per-owner priority
flag or an on-demand batch), so their doors open within a night or two
instead of waiting behind 115,061 unknocked cards in global order.
**Expectation-setting is part of the build:** their first brief must say
honestly *"your industry's doors are still being knocked — N of M done"*,
because day-1 quality is ads-only and day-3 quality is ads + boards.
*Acceptance:* a fresh lens reaches >50% knocked on its own slice within 3
nightly runs, with the progress visible in the brief.

**U5 · Reed JD drip** *(0012 task 5)*
Ad-only jobs carry no description; industries that rarely rent the four
guessable boards (care, hospitality, retail) depend on ads almost entirely, so
**this is the primary description supply for most non-software users** —
higher value here than it is for the founder. Capped nightly stage, highest-
value ads first, ~950 free calls/day budget.

**U6 · Dashboard: Sponsors browse tab** *(0012 task 4)*
Industry-filterable sponsor browse (plain-English via `sic_codes`), fit column
in `v_today`, "new today" chip. Must extend the complexity-hiding pin (new
curated view + its own test) — the dashboard still reads ONLY curated views.

**U7 · Title-pattern tuning (the tray-starvation fix)** *(0012 §3 "also fix")*
Measured 2026-08-10: `stage_reading` staged **0 of 1,083** candidates because
sieve 2 filters on the owner's title patterns. Once the 150 waiting rows
drain, the tray starves. Any user with narrow patterns hits this — so the fix
belongs to the universal layer: widen/tune patterns, or serve a "near-miss"
tier that the client AI can accept or skip. Pairs with U5 (supply side).

**U8 · Serve-all CV** *(0012 task 0 — already decided 2026-08-03)*
The client AI receives EVERY confirmed `cv_block` and selects relevance
itself; the engine's skill match is a hint, never a filter; the truth gate is
the ceiling. Universal consequence: **store every true fact**, including
seemingly irrelevant history — breadth is a feature, because transferable
evidence is exactly what a literal matcher would have hidden.

**U8b · `cv_blocks` writer tools — ships WITH task 0** *(founder's ask
2026-08-10; the gap task 1 left)*
Task 1 built `add_skill` (the first `my_skills` writer) but nothing writes
`cv_blocks`, so "I finished a new project — add it to my CV facts" has no
door and every fact base must be seeded by an operator. That blocks user #2
harder than it blocks the founder. Ship alongside task 0:
`add_cv_block` (kind/title/organisation/date_range/fact_text/skill_norms,
owner-scoped, audited, **written `confirmed = false`**), `list_cv_blocks`
(both states, so a client can show drafts for approval), `confirm_cv_block`
and `retire_cv_block`. Rules that make it safe: **only the owner confirms** —
a client AI may draft but never self-confirm, mirroring the reading tray's
"propose, don't decide"; the CV path already reads confirmed-only, so an
unapproved draft can never reach a CV. Retire = a stamp, never a delete
(keep-all). Same shape as `add_skill`: `learned_at`-style provenance on
every write, receipts in the audit table.
*Acceptance:* a user adds a project by conversation, sees it as a draft,
confirms it, and it appears in the next served CV payload — zero operator SQL.

**Founder's fact base seeded 2026-08-10:** `cv_blocks` = **22 confirmed
rows** (2 education · 6 role · 8 achievement · 6 skill_evidence), loaded by
operator in the walkthrough session and verified through `cv.blocks.
load_cv_blocks`. Task 0's `cv_blocks`-count gate is therefore **OPEN**.

## 4 · Cross-cutting findings that affect every user (not just new ones)

1. **Review backlog is a brake.** 1,067 open review flags measured
   2026-08-10; promotion reported `cap_hit=True, promoted=0` on runs 7 and 8.
   Any user's discovery lane throttles behind this. Needs a decision path
   (bulk resolve / auto-rules / raise cap deliberately) — noted, not built.
2. **Coverage is thinner than "tracked" implies.** 885 companies tracked, but
   only **82 have a board being fetched**; the rest are boardless ad-entries.
   The brief/dashboard should say this honestly rather than implying 885 live
   feeds.
3. **`role_listings` has no `owner_id`.** Queue scoping works *indirectly*
   through `target_companies.owner_id`. Correct today (1 profile) but it is
   the seam to prove hard in Phase 9 alongside RLS policies (0 policies on 23
   tables today). **Hard gate before any stranger.**
4. **World work vs personal pass.** Confirmed shape: ONE container, ONE 06:30
   job for everyone — register/census/ads/boards run once; only match →
   promote → stage → brief → nudge loops per owner (seconds each). Phase 9
   task 3 implements the loop; nothing about it needs new infrastructure.
5. **Green ≠ productive.** Runs 7 and 8 reported all-stages-ok while merge,
   promote and staging did nothing. The report card measures execution, not
   progress. A "progress" signal (did anything actually move?) would make
   silent stalls visible — worth designing before user #2.

## 5 · Acceptance test for the whole layer

From the Phase 8.5 card, unchanged and now evidence-backed: **a care-home
lens, set up by conversation alone, produces a correct queue with receipts —
no code edit anywhere.** Add to it, from this plan: the same run must show
that user's door-knocking progressing on their own slice (U4), and their tray
must not starve (U5 + U7).

## 6 · The MCP door itself — five gaps for a stranger's AI (measured 2026-08-10 at 41 live tools; build home: Phase 9)

Found by the founder's CV session probing the door as a cold client would;
reviewed and re-measured at phase close. Nothing here changes engine
behaviour — all five are door-quality, and none blocked the 8.5 deploy.

- **M1 · `intake-v1` — the missing served prompt (the big one).** Reading has
  `extract-v1`, the CV has `cv-v1`; building a NEW user's fact base has
  nothing — whichever AI a user brings writes its own interview questions, so
  fact-base quality is unversioned and unknowable. Ship a served, versioned
  interview prompt on the same pattern: dates, numbers, named credits, honest
  tool levels, one fact per block, drafts only (the U8b writer quartet already
  enforces owner-confirms). *Acceptance: two different client AIs interviewing
  the same person produce comparably rich block sets.* **Home: Phase 9 task 4
  — it is the missing half of "a new user reaches their first nudge without
  operator involvement".**
- **M2 · Server `instructions` is None.** MCP has a server-level orientation
  slot; ours is empty, so a cold client gets no "start at daily_brief, the
  tray first". One paragraph in build_server. *Acceptance: a client that has
  never seen this engine runs the loop correctly from a standing start.*
- **M3 · Zero tool annotations on 41 tools.** MCP supports
  readOnlyHint/destructiveHint; ours are all None, so a client cannot tell
  `get_job` from `mark_applied` except by reading prose — blocks safe
  auto-approval of reads. Mechanical: one flag per tool.
- **M4 · Output schema is `{"type":"object","additionalProperties":true}` on
  all 41.** The shape lives only in the Returns: prose; a client cannot
  validate what it receives. Fix where it pays: typed returns on the loop
  tools first (daily_brief, get_reading_batch, submit_reading, serve_cv,
  submit_cv, get_apply_queue) — then STOP; full typing of 41 tools is churn
  the contract-v2 `next` block does not need.
- **M5 · `prompts`/`resources` primitives unused (`[]`).** Clients with a
  prompt picker see nothing from us. Lowest value of the five — list it,
  don't build it, until a real client wants it.

**Order: M1 first (it decides user #2's data quality forever), then M2+M3
(about an hour of mechanical work, red-first), M4 partial, M5 never until
pulled.** Phase 9's CLAUDE.md task 4 points here.

## Notes / log

- 2026-08-10 — §6 added at the founder's direction after his CV session's
  door audit: five MCP-door gaps (M1–M5) with homes assigned — M1 → Phase 9
  task 4 (`intake-v1`); M2/M3 → Phase 9 warm-up; M4 partial (loop tools);
  M5 note-only. No code touched; 8.5 deliberately shipped without them.
- 2026-08-10 — Written after the universality audit at the founder's request
  ("write all the recommendations for user universal in the plan for Phase
  8.5; do not change any code"). No code was touched. Expands 0012 §3 with
  measured evidence, adds U4 (knock-on-demand + honest day-1 expectations),
  U7 (tray starvation as a universal problem) and §4's five cross-cutting
  findings.
- 2026-08-12 — **Phase 9 close, carry-forward sweep: §6's M-gaps are closed except M5.** **M1** — the served `intake-v1` interview — shipped in Phase 9 task 4, so a new user's fact-base quality no longer depends on which AI they bring; its shape is test-pinned in lockstep with `cv.blocks.BLOCK_KINDS`. **M2 + M3** (server instructions and tool annotations) went in as the mechanical warm-up before task 1. **M4** typed the six loop tools' output envelopes and stopped there deliberately, with the boundary itself a test. **M5** (the `prompts`/`resources` MCP primitives) stays note-only, which is what this spec's own §6 instructed: build it when a real client's UI pulls for it, not before. That is a deliberate deferral, not an omission, and it is named as one in the Phase 9.5 CLAUDE.md. **§4's cross-cutting findings still apply.**
- 2026-08-12 — **§4 item 5 ("green ≠ productive") was homed in Phase 9 task 3
  and DID NOT SHIP — recorded here rather than left to be noticed again.**
  Task 3 split the night and folded the per-owner runs back into one report
  card, but the card still measures **execution, not progress**: a stage that
  moved nothing reports `ok` exactly like a stage that moved everything.
  Verified by reading `src/pipeline/report.py` and `src/pipeline/owners.py` at
  the phase close — no "did anything move?" signal exists in either. The
  finding that produced it is unchanged and now has more evidence, not less:
  `promote` has reported `cap_hit=True, promoted=0` for weeks while the review
  backlog sits full. **Carried into the Phase 9.5 CLAUDE.md by name.** This is
  exactly the orphan class the carry-forward step was added to catch — an item
  given a home in a phase, and the phase closing without it.
