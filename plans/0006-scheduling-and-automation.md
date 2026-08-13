# 0006 — Scheduling & automation (cron map)

- **Status:** ✅ Largely delivered (Cloud Scheduler live since Phase 8; see the 2026-08-12 entry)
- **Created:** 2026-07-14  ·  **Last updated:** 2026-07-14
- **Depends on / blocked by:** founder go to build; the Cloud-Scheduler items belong to Phase 8 (plan 0005); the Notion routine follows plan 0004
- **Owner / last touched by:** Claude session 2026-07-14 (census/vision session)

## Goal
Some parts of the pipeline age daily and deserve automatic runs; others are
once-and-done. This plan is the agreed map of **what runs on a schedule, when,
and why** — and what must never be automated. Nothing here executes; it is the
blueprint for when the founder says build.

## The cadence map (agreed 2026-07-14)

| What | When | Why |
|---|---|---|
| Daily pipeline (`scripts/run.py`) | daily ~08:00 | listings appear/close daily; morning nudge digest; run-lock prevents overlap |
| Census sweep batch (`scripts/sweep.py`) | nightly ~02:00 | rolling census; software-first after Pass 1; separate lock, no clash with daily run |
| Notion mirror (Claude-side routine, per plan 0004) | daily after the pipeline run, or on demand | DB is 24/7 truth; Notion is the human mirror |
| Register refresh + classify top-up | weekly | Home Office register updates most working days; both pickers self-select only NEW orgs, so top-ups are minutes |
| Error-retry sweep (`--retry-errors`) | weekly, small batch (optional) | re-card transient network failures |
| SOC going-rates reseed | ~yearly, manual | only when the government updates rates |

**Runs-until-done (self-terminating, no cron needed):** Pass 1 classification
(the `run-classify.sh` wrapper stops itself at "0 classified"); the one-time
Pass 2 software-lot probe (collapses into the nightly rolling sweep after).

**Once, never again:** migrations; initial register load; launchd/Scheduler/MCP
config setup; profiles + criteria (event-driven adjustments only).

**Founder-only, event-driven (never on a clock):** `cv_blocks` facts,
`my_skills`, `promote_company`, flipping CV-autopilot to auto.

**Never automated, by principle:** applying to jobs (human presses apply),
pushing/publishing (Phase 8 gates), key rotation.

## Tasks (in build order, when the founder says go)
- [ ] Load the existing daily launchd plist (`ops/launchd/com.goala.engine.daily.plist`)
      — one founder command; laptop-era only, retired at Phase 8
- [ ] Add a nightly census-sweep schedule (laptop era: a second launchd plist;
      cloud era: Cloud Scheduler — don't over-invest locally)
- [ ] **Build the register-refresh script** (Home Office CSV → `licensed_sponsors`)
      — the ONE missing piece; nothing exists for this today (verified 2026-07-14)
- [ ] Weekly classify top-up batch chained AFTER the refresh (order matters:
      refresh first, then classify the new orgs)
- [ ] Weekly `--retry-errors` small batch (optional; decide if worth a slot)
- [ ] Claude-side scheduled routine: mirror the apply queue to Notion daily
      (after plan 0004 lands — uses Claude's connector, not an engine cron)
- [ ] At Phase 8: fold every schedule above into Cloud Scheduler + Cloud Run Jobs
      and retire launchd (this task belongs to plan 0005, Task 2 — cross-ref)

## Notes / log
- 2026-07-14 — Plan captured from the founder's ask ("list what deserves a run
  and when, what is done once — do not build"). Verified: no register-ingest
  script exists; the daily plist exists but was never loaded (founder hold);
  the Pass-1 wrapper self-terminates. Full reasoning in the session transcript;
  cadences chosen to keep the daily run and nightly sweep off each other's locks.
- 2026-08-12 — **Phase 9 close, carry-forward sweep: the cron map is BUILT.** Cloud Scheduler `goal-a-daily-morning` fires `30 6 * * *` Europe/London as the `goal-a-invoker` service account and has been waking the job unattended since 2026-08-09; the local launchd plist was retired the same day. The 15-stage order is pinned by test, `pipeline_runs` records a per-stage report every night, and two Cloud Monitoring policies watch the infrastructure independently. **Still open from this plan:** the Notion routine, which follows plan 0004's trigger and no other.
