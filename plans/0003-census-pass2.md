# 0003 — Census Pass 2 (job-board probe)

- **Status:** ✅ Done
- **Created:** 2026-07-14  ·  **Last updated:** 2026-07-22  ·  **Completed:** 2026-07-22 20:40 BST
- **Depends on / blocked by:** nothing technical — founder's word only. No keys, £0, no AI.
- **Owner / last touched by:** Claude session 2026-07-20 (census/vision session)

## Goal
After every register org is classified (Pass 1), probe the **software-only**
subset for live job boards. Founder's sequence: classify ALL first, THEN probe.

## Tasks
- [x] Change the picker to probe ONLY `probe_outcome IS NULL AND
      registry_outcome='matched' AND industry_codes && SOFTWARE_SIC` (software narrowing)
      — done 2026-07-13: new `src/discover/probe_pick.py` (hot-file-safe, additive);
      `scripts/sweep.py --software-only`
- [x] Add **parallelism** — done 2026-07-13: `run_software_sweep_parallel`, N workers,
      one connection each, per-org commit kept; `--workers N` /
      `run_sweep(software_only=true, workers=N)`
- [x] Add `run_classification` / promote-company MCP tools — done 2026-07-13:
      `run_classification` + `classify_status` + `promote_company` (+
      `list_software_companies`, `get_job_gap`); MCP 19→24
- [x] **RUN Pass 2** over the software lot once Pass 1 completes — done 2026-07-22
      20:40 BST (launched 2026-07-20 19:43 BST via detached `ops/run-sweep.sh`,
      batch 500 × 4 workers; self-stopped on "software lot fully probed")

## Notes / log
- 2026-07-22 — **RUN COMPLETE → plan ✅ Done.** Wrapper self-stopped 20:40 BST
  ("0 picked" → "software lot fully probed — nothing left. Done.", log
  `sweep-20260722T173825Z.log`). Final: **260 live boards** (259 register-matched
  + 1 not_found) · **5,144 census jobs** (1,196 UK · 288 title-matched · 253 orgs
  · 4 sources) · **0 errors** over three segments (07-20 launch, founder
  stop/resume 07-21, finish 07-22; survived a macOS TCC prompt and an internet
  outage via worker auto-restart). Next step lives outside this plan: founder
  promotion review → `promote_company`, then plan 0007 task 1b before the fetch run.
- 2026-07-20 — **Pass 1 finished** (126,342/126,342 · 11,726 software · 0 errors;
  wrapper self-stopped). The keep-all-jobs census change (plan 0007 task 1a,
  migration 0034) landed BEFORE Pass 2, so the first sweep already stores every
  job labelled is_local/title_match. Plan is now ready-to-run on the founder's word.
- 2026-07-14 — Deferred by design; do not start until Pass 1 is done. Live Pass 1
  status is tracked in `../PROJECT-MEMORY.md`, not here.
- 2026-07-14 — Ticked the three build tasks: they landed 2026-07-13 in commit
  `b8db398` (see `docs/vision-pipeline.md` + decision-log 2026-07-13), test-first,
  400-test suite green, census untouched. Only the actual RUN remains, so the
  plan stays ⏸️ until Pass 1 finishes.
