# Plans — goal-a-engine

A lightweight, log-only record of plans and to-dos for this project.
**This folder does not execute anything.** It captures intent so any session
(or Shayan) can see what's planned, what's done, and what's blocked — then tick
things off as they land.

> Live census/run status and cross-session context live in `../PROJECT-MEMORY.md`,
> not here. This folder is only for *plans* (things we intend to do).

---

## How this works (read before writing — multiple sessions share this folder)

**One file per plan.** Each plan is its own file: `NNNN-slug.md` (e.g.
`0001-cv-autopilot.md`). This is deliberate — different sessions edit different
files, so no two sessions ever clobber the same file.

- **To add a plan:** create a new file with the next free `NNNN`. Copy the
  template below. Do **not** edit other plan files to add yours.
- **To update a plan:** edit **only that plan's file**.
- **To tick a task off:** change its `- [ ]` to `- [x]` and add a dated note.
  When every task is done, set the file's `Status:` to `✅ Done` and fill in
  `Completed:`.
- **Never delete a finished plan** — flip it to `✅ Done` and leave it for history.
- **Always stamp your change** with the date and a short who/what note, so the
  next session knows who did what and when. Dates absolute (YYYY-MM-DD).
- Keep the **index table below** in sync when you add or complete a plan (it's a
  convenience view; the plan files are the source of truth).

## Status legend
- 🔲 **Todo** — agreed, not started
- 🚧 **In progress** — partially done
- ⏸️ **Blocked / Deferred** — waiting on something (say what)
- ✅ **Done** — every task complete (kept for history)

## Plan template
```
# NNNN — <title>

- **Status:** 🔲 Todo
- **Created:** YYYY-MM-DD  ·  **Last updated:** YYYY-MM-DD
- **Depends on / blocked by:** <thing, or "nothing">
- **Owner / last touched by:** <session note, e.g. "Claude session 2026-07-14">

## Goal
<one or two lines>

## Tasks
- [ ] first task
- [ ] second task

## Notes / log
- YYYY-MM-DD — <what changed / decisions>
```

---

## Index (keep in sync)

| # | Plan | Status |
|---|------|--------|
| 0001 | [CV Autopilot (Phase 7.6)](0001-cv-autopilot.md) | ✅ Superseded by the serve-all CV (Phase 8.5 task 0) |
| 0002 | [SIC industry → engine integration](0002-sic-industry-engine-integration.md) | ✅ Delivered (128,222 classified, 0 errors; codes are the owner's lens since 8.5) |
| 0003 | [Census Pass 2 (job-board probe)](0003-census-pass2.md) | ✅ Done (run complete 2026-07-22 — 260 boards · 5,144 jobs · 0 errors) |
| 0004 | [Notion leaves the engine](0004-notion-out-of-engine.md) | ⏸️ Deferred with a NAMED trigger — the first second owner who wants a board (ref stored in Phase 9 task 4, read by nothing) |
| 0005 | [Phase 8 — Going Live](0005-phase-8-going-live.md) | ✅ Done (2026-08-10) |
| 0006 | [Scheduling & automation (cron map)](0006-scheduling-and-automation.md) | ✅ Largely delivered (Cloud Scheduler live since Phase 8); the Notion routine follows 0004 |
| 0007 | [Job-coverage deltas (aggregators, dedupe, non-UK, multi-board)](0007-coverage-deltas.md) | 🚧 In progress — **items 2, 3, 4 still open**. Phase 9.5 did NOT build them: the item's own rule is "sequence by what live users actually hit" and `profiles` is still 1. **Trigger: the first thing a real user hits, or user #2.** |
| 0008 | [Third-party product (friend's profile, pathways, email nudges)](0008-third-party-product.md) | 🔲 Todo (plan only per founder; build order inside) |
| 0009 | [Public product: market position, differentiation, build gap](0009-public-product-position.md) | 🔲 Todo (analysis only; BUILD/CHANGE/FINISH tables inside) |
| 0010 | [Walkthrough findings: noted gaps + refinements](0010-walkthrough-findings.md) | 🚧 In progress — **it had no Status line until 2026-08-12**; item 16 (learning curve) is item 4 of plan 0014, item 15 superseded by 0011 |
| 0011 | [Named saved watches: full design](0011-saved-watches-design.md) | 🧠 Design complete, **trigger FIRED, still NOT BUILT** — Phase 9.5 ran out of room and chose not to half-build a stage change. Design unchanged and still correct. **It is the next thing to build**; note that it touches the per-owner pass, so the sacred 06:30 lane rule applies. |
| 0012 | [Road to fully built: Phase 8 → 8.5 → 9](0012-road-to-fully-built.md) | ✅ Route delivered — **§8 carries the S-1…S-8 dispositions (4 closed, 4 open by decision, each with a trigger)** |
| 0013 | [Universal user: the full spec for "one lens → any lens"](0013-universal-user-spec.md) | ✅ Built — U1–U8 (8.5) + §6 M1–M4 (Phase 9); **only M5 remains, note-only by its own instruction** |
| 0014 | [Phase 9.5: the Translator Layer](0014-phase-9p5-translator-layer.md) | 🟡 **MOSTLY DELIVERED 2026-08-12** — the mirror, M6, M7, the learning curve, the salary-gate fix, M5 confirmed note-only and the retention decision surfaced, plus task 0's five audit repairs. **Items 5 (saved watches) and 8 (coverage) NOT built**, both carried with triggers. Three items changed shape because measuring came first. |

_Updated 2026-08-12 (evening, Phase 9.5 close): 0014 re-marked item by item, 0011 and 0007 re-marked as still-open with explicit triggers rather than left implying they were done. The honest headline of this sweep: **two of the ten items in 0014 were not built, and three of the eight that were changed shape once their premises were measured** — one plan's "cheap option" had already shipped and already failed, one plan's data did not exist, and one plan's option list was two-thirds worthless. Nothing survives on memory alone; both unbuilt items are named in the next phase's card._

_Previous folder update: 2026-08-12 (Phase 9 close, carry-forward sweep — the anti-orphan step). Every plan walked end to end and re-marked against what actually shipped: 0001 superseded, 0002/0005/0006 delivered, 0004 and 0011 given NAMED triggers instead of open-ended deferral, 0012 gained §8 with a verdict for every one of S-1…S-8, 0013's M-gaps closed except the note-only M5, 0007's three coverage items carried forward by name — and two findings the sweep existed to catch: **plan 0010 had no Status line at all** (so no sweep could ever report it open) and **plan 0014 was missing from this index entirely** (created 2026-08-10, never listed). Both fixed. Every still-open item is named in the Phase 9.5 CLAUDE.md; nothing survives on memory alone.)_
