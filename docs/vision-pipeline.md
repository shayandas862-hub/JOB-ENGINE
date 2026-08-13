# The Founder's Pipeline Vision — mapped onto the machine

*Written 2026-07-13, during the Pass-1 census run. This is the founder's
end-to-end flow in his own sequence, with exactly where each step lives in
the engine, what was added to close the gaps, and what remains deliberately
Claude-side. One file does one thing throughout — the vision runs as a chain
of small, individually-tested parts, each also exposed as an MCP tool so any
combination can be driven from Claude.*

## The flow, step by step

| # | Founder's step | Where it lives | Status |
|---|---|---|---|
| 1 | **Census the whole register** — every sponsor company, software or not, gets its official industry type recorded | Pass 1: `scripts/classify_sponsors.py` → Companies House → `sponsor_census.industry_codes` (`run_classification` / `classify_status` from Claude) | ✅ running now (~62%+) |
| 2 | **Take the software-company lot first** | Pass 2 picker: `discover/probe_pick.py` — only registry-matched + software-SIC + never-probed cards, active first | ✅ built, waits for Pass 1 |
| 3 | **Fetch all their jobs from the 4 job boards** | The existing probe (`discover/sweep.py::probe_org`): Greenhouse / Lever / Ashby / Workable detection + one-shot job copy into `census_jobs` (+ Workday & aggregators in daily discovery). Run it software-first with `scripts/sweep.py --software-only [--workers N]` or `run_sweep(software_only=true, workers=N)` | ✅ machinery existed; software-first + parallel added |
| 4 | **Filter to MY profile — primary / secondary / tertiary** | Criteria + tiering that already exist: `target_roles` title patterns (what counts as my kind of job), `fit_rank` High/Med/Low + `lane` on companies, per-role `sponsor_signal`, the salary wall, `v_apply_queue` ranking. The census marks `title_match` per job with the same matcher | ✅ existed (this IS the tiering — names differ) |
| 5 | **Understand what fits my skills** | JD reader (caged Gemini + keyword fallback) → `role_skills`; `my_skills` (yours, 22 rows); aggregate gap `v_skill_gap`; per-job gap `analysis/job_gap.py` (`get_job_gap`) | ✅ existed; per-job gap added |
| 6 | **A match goes to Notion (with a tailored CV)** | Filing stage + CV maker (assemble → phrase → truth-gate → ATS render). Notion delivery moves Claude-side per the 2026-07-12 decision; CV content needs `cv_blocks` seeded (`docs/cv-intake-template.md`) | ⚠️ engine ready; **blocked on your fact bank** |
| 7 | **A non-match: an agent figures out how to close the gap** | Deliberately NOT engine logic (AI only at caged spots). The data: `get_job_gap` (what's missing) + `get_skill_gaps` (what's most demanded). The reasoning: Claude, via a skill, deciding learn/emphasise/skip | ✅ data tools ready; skill is Claude-side |
| 8 | **Everything driveable from Claude in any combination** | 24 MCP tools (was 19): + `run_classification`, `classify_status`, `list_software_companies`, `promote_company`, `get_job_gap`; `run_sweep` gained `software_only`/`workers` | ✅ done |

## The one concept the vision needed that didn't exist: the bridge
The census is deliberately walled off (blast-radius rule: it never writes the
daily pipeline's tables). Your flow needs census findings to BECOME pipeline
work, so the bridge is explicit and founder-triggered:

```
census (sponsor_census + census_jobs)          the daily pipeline
  list_software_companies  ──pick──▶  promote_company  ──▶  target_companies
                                                             └▶ next run fetches its jobs
                                                                → read → skills → wall → queue
                                                                → get_job_gap / generate_cv → Notion
```

Promotion copies the board straight off the census card (no re-probe), links
the register row, carries the `register-only` sponsor verdict, and audits.
The wall stays: nothing crosses it automatically.

## Order of operations (the founder's sequence, as runbook)
1. **Now:** let Pass 1 finish (`classify_status` to watch).
2. **Then:** `run_sweep(software_only=true, workers=4)` batches until the
   software lot is probed (`sweep_status` to watch).
3. **Then:** `list_software_companies(with_boards_only=true)` → review →
   `promote_company` the ones you want watched.
4. **Daily loop / `run_pipeline`** picks them up: fetch → read → skills →
   salary wall → queue → nudge.
5. Per queued role: `get_job_gap` → match? `generate_cv` (once `cv_blocks`
   is seeded) and file; gap? Claude reasons about closing it.

## Still open (carried forward honestly)
- **`cv_blocks` is empty** — the CV maker produces nothing real until the
  fact bank in `docs/cv-intake-template.md` is filled and seeded. Biggest
  single unlock in the whole flow.
- **Notion-out-of-the-engine** refactor (2026-07-12 decision) — engine keeps
  filing to its DB; Claude mirrors to Notion. Not actioned yet.
- **Auto-CV on queue entry** (the founder wants it automatic eventually) —
  provision exists (`generate_cv` per role); the automatic trigger stays off
  until he flips it, per his "manual first to test" instruction.
