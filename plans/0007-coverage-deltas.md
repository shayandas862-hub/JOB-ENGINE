# 0007 — Job-coverage deltas (aggregators, dedupe, non-UK, multi-board)

- **Status:** 🚧 In progress (1a, 1b, 5 done; **2–4 still open, carried to Phase 9.5 as item 8 of plan 0014**)
- **Created:** 2026-07-15  ·  **Last updated:** 2026-07-22
- **Depends on / blocked by:** #1 needs a founder decision (keep non-UK or not);
  #2/#3 need the Adzuna + Reed keys in `.env`; #4 waits for the census sweep to
  be idle. Several tasks touch hot files (`src/fetch/feeds.py`) — never edit
  those while a census/sweep run is live.
- **Owner / last touched by:** Claude session 2026-07-15 (census/vision session)

## Goal
Four small, verified gaps between the founder's "maximum coverage" intent and
today's code. Each was confirmed by reading the code on 2026-07-15 — none is
speculative. Together they make job coverage complete for the long tail of
sponsors and safe when aggregator sources switch on.

## Tasks
- [x] **1a. Flag, don't drop — census layer** — done 2026-07-20, before Pass 2:
      migration 0034 `census_jobs.is_local` (backfilled true for pre-0034 rows),
      `insert_census_jobs` labels every job (matchers never filter), `probe_org`
      stores ALL jobs locals-first under the 500 cap; RED-first, suite 402 green.
      Scope decided by founder 2026-07-16: keep ALL jobs, filter at query time.
- [x] **1b. Flag, don't drop — pipeline layer** — done 2026-07-22 22:22 BST:
      migration 0035 (`role_listings.is_local + source`, URL-domain backfill),
      `upsert_jobs` labels every job, `fetch_jobs.py` filter deleted,
      `workday.py` keeps non-UK postings shallow (no detail call) and keeps
      detail-relocated jobs, extractor picker narrowed to `is_local` (the cost
      cage). RED-first; suite 416.
- [ ] **Per-company aggregator queries** — Adzuna/Reed are wired for keyword
      discovery only; add "fetch this company's jobs by name" so promoted
      companies get aggregator coverage on top of their ATS board. Needs keys.
- [ ] **Cross-source dedupe + aggregator jobs as first-class listings** —
      `dedupe_key` includes the URL, so the same job via ATS + Adzuna would make
      two rows; needed BEFORE aggregator fetch goes live. ATS copy is canonical;
      aggregator copy merges. Also store aggregator jobs as `role_listings` rows
      (`source='adzuna'/'reed'`) so no-board sponsors (the register long tail)
      become fetchable at all — today their discovered jobs are thrown away.
- [ ] **Measure the one-board assumption** — `classify_company` stops at the
      first ATS hit; change the census probe to record ALL platform hits, then
      count sponsors with 0/1/2+ boards. Turns an industry assumption into our
      own data; decides whether multi-board fetch is ever worth building.
- [x] **Board-learning loop from ads** — first built 2026-07-22 as URL-following
      token harvest; **that mechanism was RETIRED 2026-07-27 after a live
      diagnostic proved it structurally impossible** (Adzuna's `/jobs/details`
      and `/jobs/land/ad` URLs resolve to themselves — the hand-off is
      client-side; Reed keeps applicants on reed.co.uk — so no ATS token is
      ever exposed: 3,458 links followed, 0 hints planted). **Replaced by
      hiring-first probing**: `pick_hiring_batch` (unprobed sponsors that ads
      prove are hiring — 433 of them with 5,029 live ads, because Pass 2 only
      covered the software-SIC lot) + injectable `picker=` on both runners +
      `scripts/sweep.py --hiring`. **Probe hint-first survives** (`probe_token`
      verifies a known board with one call before slug guessing) and is still
      useful for any hint arriving from elsewhere. Open refinements: ad-count
      ordering surfaces recruitment agencies (recruiter CRMs, not startup
      ATSs — 0 boards in the first 40), so order by software-SIC if precision
      is ever needed; widen the probe set beyond 4 platforms (Teamtailor,
      Recruitee, SmartRecruiters, Personio…); Reed detail-API `externalUrl`
      remains an option if per-job quota spend is ever justified.

## Notes / log
- 2026-07-25 02:25 BST — **Both provider depth-walls now beaten** (decision-log
  same time): Reed's honest 10k error-wall (salary bands, 07-23) and Adzuna's
  silent ~5k clamp (bands generalised via `ensure_bands` + the `stale_limit`
  saturation guard in `run_slice`). Progress is measured in distinct rows
  banked, never pages walked. Suite 425.
- 2026-07-22 22:22 BST — **The aggregator machine is BUILT and smoke-proven**
  (progress-log + decision-log same time): migration 0036 raw layer, broad-sweep
  pagers (Reed full-inventory ~92,925 ads measured · Adzuna it-jobs ~44,562),
  quota-refusing resumable runner, register-match label pass, token harvest,
  `ops/run-aggregator.sh` detached wrapper. **Run gated on the founder's word.**
  Task 3's cross-source `content_fingerprint` already rides on every stored ad;
  what remains of task 3 is only the merge into `role_listings` — do it AFTER
  the first pass shows the real matched-ad shape. Task 2 stays demoted (broad
  sweep ≈30× cheaper; per-company reserved for promoted orgs).
- 2026-07-22 — **Aggregator-lane algorithm decided with the founder** (decision-log
  21:26 BST): **jobs-first** — broad category sweep (Reed = workhorse, ~1,000
  req/day × 100/page; Adzuna ~250/day × 50, quota confirmed at registration) →
  employer-name match against the register (the register IS the filter — no
  role-keyword map as fetch driver; keep-all rule) → ads stored as first-class
  listings (task 3 dedupe FIRST) → token harvesting (new task 5) → per-company
  queries (task 2) reserved for promoted orgs. Keyword-discovery wiring already
  works the day keys land; Adzuna/Reed lines in `.env` still empty.
- 2026-07-20 — Task 1a (census layer) built and committed locally, after Pass 1
  finished (2026-07-17 00:34 BST) and before Pass 2 launched; task 1 split into
  1a census (done) / 1b pipeline (open).
  **Final Pass-1 scoreboard: 126,342/126,342 classified · 11,726 software
  companies · 0 errors** (the figures in the 2026-07-15 note were interim).
- 2026-07-16 — **Founder decided task 1's open question: keep ALL jobs** ("I do
  not want it to return only one kind of jobs… I will filter that later — I want
  the full picture"). Scope = flag-don't-drop, everything stored with a UK label.
  Build it in the gap AFTER Pass 1 self-stops and BEFORE Pass 2 launches, so
  Pass 2's first sweep already stores the full picture (hot files are only safe
  to edit between runs). Founder also confirmed: title_match stays a label,
  never a filter.
- 2026-07-15 — Captured from founder questioning ("max coverage; both UK and
  non-UK; how do keyword results fit a company-keyed pipeline; prove one
  company = one board"). Keyword→company inversion already exists
  (`discover/daily.py` + `sponsor_match.py`) and is NOT part of this plan; these
  four are the true gaps. Pass 1 finished the same evening (78,919 matched /
  21,428 not_found / 195 ambiguous / 0 errors; software lot = 9,972 orgs).
- 2026-08-12 — **Phase 9 close, carry-forward sweep.** Items **2 (per-company probes), 3 (deeper merge) and 4 (multi-board employers)** are unchanged and still open — Phase 9 was security and multi-user work and touched none of them. They are carried into plan 0014 as item 8, sequenced by what live users actually hit rather than by list order. **The measurement that says why they matter, taken today: 894 companies tracked, of which only 91 carry a live board feed** — the coverage-honesty gap the briefs and the dashboard must keep being honest about. The knock-on-demand sweep and the Reed JD drip narrow it nightly; these three items narrow it structurally.
