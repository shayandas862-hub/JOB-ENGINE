# 0012 — Road to fully built: Phase 8 → 8.5 → 9

- **Status:** ✅ Route delivered — Phases 8, 8.5 and 9 all shipped. **Four security debts stay open by decision** (§5, dispositions dated 2026-08-12)
- **Created:** 2026-08-09 · **Last updated:** 2026-08-09
- **Depends on / blocked by:** nothing to start Stage C. Phase 8.5 task 0 is blocked on the founder seeding `cv_blocks` (0 rows — his facts, his session).
- **Owner / last touched by:** Claude session 2026-08-09 (the audit-remediation night)
- **Relates to:** 0005 (Phase 8 staging), 0010 (walkthrough findings → 8.5), 0011 (saved watches, slots after 8.5)

## Goal

One ordered route from "the pipeline runs unattended" to "a second person can
use this safely." Written after the machine nudged the founder by itself for
the first time (2026-08-09 19:45), so every claim below is measured, not
assumed.

---

## 0 · Measured state (2026-08-09 20:00 BST)

| Thing | Value |
|---|---|
| Unattended cloud runs proven | **1** (run 5, cron-triggered, 14/14 stages, nudge delivered) |
| Suite | 647 (637 pass / 10 skip) repo · 624/23 container · exit 0 both |
| Migrations | through 0042 · **next free 0043** |
| MCP tools | 29 · **4 broken inside a container** (Stage C) |
| Cloud Run services | **0** — no MCP, no status page |
| Reading tray | 150 staged · **0 ever read by any AI** · 1,083 stageable but 0 matched tonight |
| `cv_blocks` | **0 rows** — blocks 8.5 task 0 |
| RLS | on, all 23 tables · **0 policies** · engine bypasses as owner role |
| **Applications sent** | **0** ← the only number that matters |

---

## 1 · Working principles (do not break what works)

1. **The 06:30 lane is sacred.** Nothing may stale or block the morning queue.
   Any change touching `scripts/run.py` or its stages gets a manual
   `gcloud run jobs execute … --wait` before a scheduled run meets it.
2. **Test before code.** Red first. A test that passes for the wrong reason is
   worse than no test — see the `.venv` assertions that hid a container-fatal bug.
3. **A check must fail LOUDLY and differently from "all clear."** Standing rule
   from 2026-08-09: never swallow stderr in a watcher; never report an
   instrument's silence as a finding without a second source.
4. **Rebuild → manual execute → only then let cron meet it.**
5. **Every ⛔ founder gate is a hard stop.** Cloud URLs, the push, the flip.
6. Only touch files for the current task. Note the rest here.

---

## 2 · PHASE 8 — remaining

### Stage C — audit fixes ⟨unblocked; do first; ~1 sitting⟩

- [ ] **C1** `python_executable()` into `src/pipeline/trigger.py`; `census_tools.py` imports it. Fixes `FileNotFoundError` in 3 tools. Rewrite the `.venv` assertions in `test_trigger.py` + `test_mcp_census_tools.py` — they pass for the wrong reason today.
- [ ] **C2** Split `run_pipeline`: `preview_pipeline()` sync (dry-run, seconds) · `start_pipeline()` detached. Kills the guaranteed 504 once hosted.
- [ ] **C3** `headers={"Title": title.encode("utf-8")}` — fix verified live 2026-08-09. Regression test with a non-ASCII title.
- [ ] **C4** `notify_failure` shouts on stderr when it cannot send (Cloud Logging catches what ntfy cannot).
- [ ] **C5** Rebuild → push → manual execute → verify. *(Needs Docker Desktop.)*
- [ ] **C6** Retire `ops/launchd/com.goala.engine.daily.plist` — ⛔ gate **satisfied** 2026-08-09 (task 2 required a confirmed clean cloud run). Do it with the founder watching.

**Done when:** green in repo *and* container · new image executed by hand · plist gone.

### Task 3 — Hosted MCP ⛔ ⟨blocked by Stage C⟩

- [ ] **3a** `MCP_TOKEN` — high entropy, `env.sh`, Secret Manager. **Note:** `test_the_secret_allowlist_is_exactly_the_six` pins the count at six. A seventh secret is a deliberate contract change; update the test *and* its name.
- [ ] **3b** First Cloud Run **service** this project has ever deployed: `mcp` door, `min-instances 0`, own least-privilege SA, `MCP_TOKEN` mounted. New section in `setup.sh`.
- [ ] **3c** ⛔ founder gate before any service URL exists, even token-gated.

**Done when:** 401 no-token · 401 wrong-token · 200 right-token · rate limit provably trips · **a client AI runs `daily_brief → get_reading_batch → submit_reading` from descriptions alone**, and the grounding gate is *seen* rejecting an ungrounded claim.

### Task 4 — Public status page ⛔

- [ ] **4a** Migration **0043** — person-free curated view (last run, per-stage health, listings tracked, companies covered, register age). Zero names, salaries, per-person application facts, tokens.
- [ ] **4b** `src/status/` — no auth, reads ONLY that view, pinned by its own test like the dashboard. *(The container already routes a `status` door at a module that does not exist — that door crashes today.)*
- [ ] **4c** Deploy as a second service, unauthenticated. ⛔ gate to make the URL public.

### Task 5b — CI deploy half ⛔

- [ ] Workload Identity Federation pool + provider + deployer SA (`run.developer`, `artifactregistry.writer`). **No SA key is ever exported** — `NOTES.md` forbids it.
- [ ] `google-github-actions/auth@v2` + deploy job on green main.

### Task 6 — Pre-flight security pass ⛔ *(mandatory)*

Run the `security-review` skill. Carry the register in §5 below. **Fix every CRITICAL before task 7.**

### Task 7 — The flip ⛔ *(his explicit word)*

- [ ] Fresh public repo from a **squashed, scrubbed** snapshot. **Never `git push --mirror`** — the Supabase project ref is in history (4 occurrences, old `.env.example`).
- [ ] Honest README — it is currently **materially false** (advertises 402 tests, 34 migrations, 24 tools, "caged AI with Gemini", "a hard spend cap"; reality: 647, 42, 29, no AI at all, cap retired).

### End of phase — the 5-step relay
Decision log · progress log · archive `CLAUDE.md` + README row · write Phase 8.5's `CLAUDE.md` · print the relay prompt. **Then stop.**

---

## 3 · PHASE 8.5 — Universal Product Layer (one lens → any lens)

**Acceptance test from the card:** a care-home lens set up **by conversation
alone**, producing a correct queue with receipts. No code edits anywhere.

- [ ] **0** CV by user-side AI — `cv-v1` served prompt → client AI writes → deterministic truth gate → **engine renders the .docx** (format is engine-owned). ⏸️ **Blocked: `cv_blocks` = 0 rows.** Founder's facts, founder's session.
- [ ] **1** Words→codes translator + skills-entry tool. *User words become rows, never code edits.*
- [ ] **2** Owner-lens sweep — retire the hardcoded software-only convenience; Adzuna category per-owner.
- [ ] **3** Universal read tools: `search_sponsors`, role lens, skills-gap.
- [ ] **4** Dashboard Sponsors browse tab + fit column + "new today".
- [ ] **5** Reed JD drip (~950 free calls/day) — descriptions for the tray regardless of lens.
- [ ] **6** End-to-end care-home lens proof.

> **Full universal-user spec: [0013](0013-universal-user-spec.md)** (2026-08-10
> audit) — measured coverage table (software 98% knocked vs care homes 0.7%),
> the complete hardcode list (`probe_pick`'s software-SIC pick is the real
> blocker), and U1–U8 mapped onto the tasks above. It adds **U4
> knock-on-demand** (a new lens must not queue behind 115k global cards, and
> the brief must say so honestly) and treats the tray-starvation fix as a
> universal problem, not a founder-only one.

**Also fix here (product, not cosmetic):** the tray staged **0 of 1,083**
tonight because sieve 2 filters on the owner's title patterns. Once the 150
waiting rows drain, **the tray starves.** Title patterns need a tuning pass, or
the flagship loop has nothing to serve. Task 5 (Reed drip) is the supply side of
the same problem.

---

## 4 · PHASE 9 — Third-party ready

Order per the architecture card: friend-tier keys → **RLS 24/24** → per-owner
pass → sign-in last (email off).

- [ ] **Per-user token → owner resolution.** `BearerVerifier` currently returns
      `client_id="founder"` hardcoded. The seam exists; Phase 9 fills it.
- [ ] **RLS for real.** 23 tables have RLS on and **zero policies**; the engine
      bypasses entirely by connecting as the owner role. Multi-user requires
      either per-user connections or enforced policies. **Verify by *trying* a
      cross-user read and being refused** — not by reading the policy text.
- [ ] **Drop the `owner_id` DEFAULT** (single-user convenience, flagged since Phase 2).
- [ ] **Per-owner nightly pass** — see scale notes.
- [ ] Sign-in last.

---

## 5 · Security debt register (carried; owner = task 6 unless stated)

| # | Debt | Severity |
|---|---|---|
| S-1 | Supabase project ref in git history — **blocks any full-history public push** | HIGH at flip |
| S-2 | RLS on, 0 policies; engine bypasses as owner role | HIGH at multi-user (Phase 9) |
| S-3 | One static bearer token, `client_id="founder"` hardcoded | HIGH at multi-user |
| S-4 | ntfy topic is obscurity-only; digest carries company + role names | MEDIUM — self-hosted or token-gated topic |
| S-5 | `DASHBOARD_TOKEN` mounted into the daily Job, which never serves the dashboard | MEDIUM — remove |
| S-6 | Secrets mount `:latest`, no pinned version — a bad write propagates silently | LOW |
| S-7 | Default compute SA holds `roles/editor` (GCP default, unused) | LOW |
| S-8 | **MCP rate limiter is in-process** — at >1 Cloud Run instance, per-token limits become per-instance limits | LOW now, HIGH at scale |

---

## 6 · Scale notes — what actually breaks at N users

**The architecture's shape is right, and worth naming:** the expensive data is
**shared** (register 144k · census 128k · ads 105k · listings 12.5k), and the
per-user data is **tiny** (criteria, skills, rule, queue stamps). One census
serves every user. That is the correct economics and it does not need changing.

Where it breaks:

1. **The nightly job is `O(1)` for register/classify/discover/fetch and
   `O(users)` for match/promote/salary/deadlines/nudge.** The scaling axis is
   therefore per-owner fan-out, not more machines for the shared half. Cloud Run
   Jobs support `taskCount` — that is the lever, and the per-owner pass in Phase 9
   should be written with it in mind rather than as a serial loop.
2. **API quotas are per-account and shared across all users** (Adzuna, Reed,
   Companies House). This is a hard ceiling, not a soft one. At scale, discovery
   stays a shared cost (good) but rate limits become the binding constraint —
   the drip design in 8.5 task 5 is the right pattern to generalise.
3. **The MCP rate limiter lives in process memory** (S-8). Correct at one
   instance; wrong the moment Cloud Run scales out. Needs a shared store or a
   gateway-level limit before real concurrency.
4. **Zero AI cost to the operator by design** — each user brings their own AI
   over MCP. This is the single best scale decision in the system and must not
   be undone by "helpfully" adding an engine-side model.
5. **The 13-minute run is nowhere near the 90-minute timeout.** No pressure yet.
   Watch `discover` (690s tonight — the long pole, all external I/O).

---

## 7 · Definition of done — "fully built and verified"

Not "perfect." **Every claim backed by a measurement, and every check fails
loudly.** Seven criteria:

1. Seven consecutive unattended runs, nudge arriving each time
2. A real AI drains the tray end to end; grounding gate *seen* rejecting an ungrounded claim
3. A failure nobody caused produces **both** alerts (ntfy + email)
4. Care-home lens works by conversation alone (8.5 task 6)
5. A second user **cannot** read the first user's rows — proven by trying
6. `security-review` returns zero CRITICAL
7. **Applications sent > 0**

Only #7 matters to Goal A. The rest is scaffolding around moving it.

**Rough size:** Stage C 1 sitting · rest of Phase 8 3–4 · Phase 8.5 3–4 (+ the
founder's `cv_blocks` session) · Phase 9 3–5. **≈10–14 sittings.** ~14 weeks to
mid-November.

## Notes / log

- 2026-08-09 — Created after the audit-remediation night. Phase 8 tasks 1–2 ✅
  proven live: the scheduler woke the job by itself at 18:45:00 UTC, run 5 ok
  14/14 stages, 64 listings nudged to the founder's phone from inside Cloud Run.
  Stage C is unblocked (its "wait for the first unattended run" gate expired
  when that run passed). Founder seeding `cv_blocks` in a parallel session.

---

## 8 · Disposition of the security-debt register (Phase 9 close, 2026-08-12)

Every S in §5 gets a verdict here rather than a silence. Four are closed by
work; four stay open, and each of those is now a **decision with a trigger**,
which is the difference between an accepted risk and a forgotten one.

| # | Debt | Verdict (2026-08-12) |
|---|---|---|
| S-1 | Project ref in git history | **Closed by design, permanently.** The public repo is a squashed one-commit export, never a mirror, so history never reaches it — and `test_no_supabase_project_ref_in_tracked_files` matches by SHAPE, so it bites for a future project too. The ref stays in the private history and that is the accepted, stated cost. |
| S-2 | RLS on, 0 policies, engine bypasses as owner | **CLOSED (task 2a + 2b).** Measured at the close: **30 policies across 30 tables, RLS on all 30.** The MCP door runs as `goal_a_app`, which cannot bypass RLS, and the proof removed the application's own filter so the refusal is the database's. |
| S-3 | One static token, `client_id="founder"` hardcoded | **CLOSED (task 1).** Every tool resolves its owner from the verified credential; `default_profile_id` is demoted to the stdio/local fallback. Task 6 added the JWT path behind it. |
| S-4 | ntfy topic is obscurity-only | **OPEN — accepted, with a trigger.** The topic is a 32-hex secret living only in `profiles.notification_channel`, never printed, never committed, and pinned out of the repo by test. What it protects is a digest carrying company and role names — real but low-value, and per-owner since task 3. **Trigger to fix: the first owner who is not the founder receiving real nudges.** The fix is a token-gated or self-hosted topic, and it is per-owner already, so it is a config change rather than a rebuild. |
| S-5 | `DASHBOARD_TOKEN` mounted into the daily Job, which never serves the dashboard | **OPEN — and it is the cheapest one here.** Verified still true: `JOB_SECRETS` in `ops/cloud/env.sh` carries it and the job never opens that door. Removing it is deleting one word, then a redeploy. Left undone this phase only because the phase's rule was to touch files for the current task; **it is named in the next phase's carry-forward for exactly that reason.** |
| S-6 | Secrets mount `:latest`, no pinned version | **OPEN — accepted deliberately.** `secret_flags` builds `NAME=NAME:latest` for all three surfaces. Pinning versions would make a rotation a two-step deploy, and the failure it guards against (a bad secret write propagating silently) has never happened here. **Trigger to reconsider: the first secret rotation that goes wrong, or any surface serving strangers** — task 6 is built but switched OFF, so that day has not arrived. |
| S-7 | Default compute SA holds `roles/editor` | **OPEN — unverified this phase, and said so.** It needs `gcloud` against the live project, which this close did not run. The deployer identity IS least-privileged and tested (`run.developer`, `artifactregistry.writer`, `serviceAccountUser`, and a test asserting it holds neither `owner` nor `editor` nor `secretAccessor`); the GCP-default compute SA is a separate identity that nothing here uses. **Next action: one `gcloud projects get-iam-policy` read, then remove the binding if the default SA is genuinely unused.** |
| S-8 | MCP rate limiter is in-process | **OPEN — accepted 2026-08-12 with the trigger written down (D-GAE-061's neighbour), and the trigger has NOT fired.** The limiter runs against `--max-instances 2`, so the effective limit is already **twice** what it says — a live 2× overshoot, not a hypothetical. The stated trigger was "task 6, the moment sign-in makes the key-holder set open-ended, **or** any change that raises `--max-instances`". Task 6 built sign-in and **left it switched off at the founder's gate**, so the key-holder set is still a handful of founder-minted keys and the trigger genuinely has not fired. **It fires the day the Google provider is enabled** — which `docs/runbook.md` §7 documents as a founder click-path, so the two must be done together. What actually protects the shared money meanwhile is the per-owner budget ledger built in task 5: DB-backed, and therefore correct across any number of containers. |

**The pattern worth naming:** the four that closed were closed by *code*; the
four that remain are all *configuration*, and three of the four are one edit
each. That is a good position to be in and a bad one to forget about, which is
why every row above carries a trigger rather than a wish.
