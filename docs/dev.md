# Dev setup

## Prerequisites
- Python 3.11+ (tested on 3.13)
- A Supabase project with the reference tables loaded (set its ref in your `.env` `DATABASE_URL`).

## Setup
```bash
cd goal-a-engine
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"          # deps are declared (pinned) in pyproject.toml
# or, for the exact locked versions: pip install -r requirements.lock
cp .env.example .env
```
Then edit `.env`:
- `DATABASE_URL` — the Supabase connection string (never commit `.env`). It is
  the only required value; every other key is optional and its absence degrades
  cleanly (absent sources are skipped, the census runs probe-only).
- `GEMINI_API_KEY` — **leave it blank.** The engine makes no AI calls at all:
  Gemini was retired to zero on 2026-08-03 and the deterministic keyword
  extractor reads job descriptions instead, with the *user's own* AI doing the
  proper reading over MCP behind a grounding gate. The variable and its code
  path still exist, and `scripts/extract_skills.py` still branches on the key
  being set, which is why this line says "blank" rather than "optional" — see
  `docs/bug-log.md` B-GAE-037. The cloud cannot reach it either way: `GEMINI`
  is banned by name from every cloud script and is not one of the eight
  secrets the deployment mounts.

## Run tests
```bash
pytest
```

## The daily schedule (Cloud Scheduler → Cloud Run Job)
The pipeline runs itself once a day in the cloud — the laptop can be shut.
Cloud Scheduler `goal-a-daily-morning` (`30 6 * * *`, Europe/London) invokes
the Cloud Run Job `goal-a-daily` in `europe-west2` over OAuth as the
`goal-a-invoker` service account. A flock in `scripts/run.py` still guarantees
two runs never overlap. Setup scripts live in `ops/cloud/` (repo only — `ops/`
is deliberately kept out of the image).

```bash
gcloud run jobs executions list --job=goal-a-daily --region=europe-west2   # history
gcloud run jobs execute goal-a-daily --region=europe-west2 --wait          # run now
gcloud scheduler jobs list --location=europe-west2                         # the cron
```

The local launchd plist was **retired on 2026-08-09** (Stage C6) once the
scheduler was proven to wake the job unattended: run 5 fired at 18:45:00 UTC
as `goal-a-invoker`, 14/14 stages, and nudged from inside Cloud Run. It had
never been loaded.

Every run writes a per-stage report to the `pipeline_runs` table; failures
push a "Pipeline run FAILED" nudge, and shout on stderr (→ Cloud Logging) when
that push cannot be delivered — never silent. Two Cloud Monitoring policies
watch the infrastructure independently, because an in-app nudge cannot report
the database being unreachable.

## The MCP server (Phase 5+)
A FastMCP server (`src/mcp_server/`) exposes the engine to Claude over stdio, or
over HTTP when hosted. It is a **thin skin** — every tool wraps one tested engine
function and holds no logic. Killing it changes nothing about the daily loop (the
scheduled run path never imports `src/mcp_server`; a test proves it).

> **Counts live in one place.** This file names tools, stages and tables; it does
> not restate how many there are. The tool, migration and test counts are in the
> README's numbers table, which `tests/test_public_safety.py` measures against
> reality on every run. A number restated here would be checked by nothing, and
> that is exactly how this file went stale for a phase and a half (B-GAE-033).

Run it directly (serves over stdio, then waits for a client):
```bash
PYTHONPATH=src .venv/bin/python -m mcp_server.server
```

### Register it with Claude Code / Desktop
Copy the `mcpServers` block from `ops/claude-mcp-config.json` into your Claude
config, then restart Claude (the paths are absolute — update them if the repo moves):
- **Claude Desktop:** `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Claude Code:** an `.mcp.json` at a project root, or `claude mcp add`.

Then just ask, e.g. *"show my apply queue"*, *"why is #3 ranked above #4"*,
*"mark role 917 applied"*, *"tighten my salary floor to £45k"*.

### The tool set
Contract v2 (Phase 7.8): **every** tool result is `{result, next}` — the
payload plus one uniform `next` block (state · suggested next call · why) —
and every description reads What/When/Returns/Next, so any vendor's AI can
run the whole loop with zero client-side prompting.

**The loop** (Phase 7.8 — the agenda, the reading tray, the promotion rule):

| Tool | Does |
|---|---|
| `daily_brief` | the day's agenda: applications so far, queue top, tray depth, open reviews, last run, and the lens's door-knock coverage (the honest "N of M knocked" line while low) — start here |
| `get_reading_batch` | claim staged JDs + the engine's versioned extraction prompt + the exact JSON shape; each job labelled `match` or `near_miss` (U7) |
| `submit_reading` | return one job's extraction through the deterministic grounding gate; verified rows upgrade in place |
| `skip_reading` | pass on a served near-miss (U7) — stamped so it never re-stages; audited |
| `get_promotion_rule` | the owner's lens row (industry set, local-jobs floor, auto flag, Adzuna ads category) |
| `set_promotion_rule` | change the lens row (partial update, audited) — since U1 the codes also drive the Pass-2 probe pick and the ads category drives the sweep; a codes CHANGE knocks on demand (starts the owner-lens sweep detached, U4) |

**Read** — structured data only, never a secret:

| Tool | Does |
|---|---|
| `get_apply_queue` | the ranked queue (fit → sponsor → recency) |
| `get_job` | one listing's full record by `role_id` |
| `get_job_history` | a listing's appeared/changed/closed/reopened story |
| `get_skill_gaps` | skills roles want that you lack — the fit queue by default, or any `role_words` lens ("care assistant") since U3 |
| `get_run_report` | the latest daily run's report card (or one by id) |
| `get_criteria` | your active search criteria |
| `list_software_companies` | the census's software-company lot (Pass-1 industry codes), most fetchable first |
| `get_job_gap` | one listing's skills split into have / missing + coverage (the per-job gap) |

**Action** — each writes an `mcp_audit` row (arg/result summary, never a secret):

| Tool | Does |
|---|---|
| `mark_applied` | record that *you* applied (the engine never applies) |
| `snooze_listing` | stop nudging you about a listing |
| `set_criteria` | adjust salary floor / wall thresholds |
| `add_target_company` | track a new company |
| `promote_company` | copy a census company's board onto the fetch list (the census→pipeline bridge) |
| `discover_company` | probe a company by name; a found board joins the fetch list with its register verdict |
| `classify_from_url` | onboard from a careers/board URL when the name-probe missed |
| `generate_cv` | re-tailor + re-file a listing's CV (truth-gated), optional emphasis |
| `serve_cv` | the serve-all CV hand-over (U8): the job + EVERY confirmed fact block + `skill_hint` + the versioned `cv-v1` prompt — the client AI selects relevance itself |
| `submit_cv` | return the written CV through the truth gate (bullet↔fact tracing; unknowns dropped); the ENGINE renders + saves the ATS-safe .docx; audited |
| `add_cv_block` | propose ONE career fact as a DRAFT (U8b) — always `confirmed=false`; a client proposes, only the owner confirms; audited |
| `list_cv_blocks` | the whole fact base, drafts included (retired never appears) — for showing the owner what awaits approval |
| `confirm_cv_block` | record the OWNER'S approval — the draft becomes a servable fact; audited |
| `retire_cv_block` | stamp a fact retired (keep-all: never a delete) — it stops serving everywhere; audited |
| `preview_pipeline` | preview what a run would nudge — dry run, waits (seconds) |
| `start_pipeline` | start a real run now, detached; returns a log path, not a returncode |
| `send_test_nudge` | test your notification channel |

**Review** (`resolve_review_flag` also audits):

| Tool | Does |
|---|---|
| `list_review_flags` | ambiguities the engine couldn't decide (seeded from low-confidence synonyms) |
| `resolve_review_flag` | record a decision, or dismiss |

**Census** (Phase 7.5+ — the two starters audit; the two statuses are pure reads):

| Tool | Does |
|---|---|
| `run_sweep` | start a census probe batch **detached** (`owner_lens` + `workers` = Pass 2 narrowed to the owner's rule codes, in parallel; logs to `ops/sweep-logs/`) |
| `sweep_status` | the census scoreboard: carded / boards / jobs / registry matches / remaining — plus today's API budget per source, yours and the world's |
| `run_classification` | start a Pass-1 registry-classification batch **detached** (logs to `ops/classify-logs/`) |
| `classify_status` | the Pass-1 scoreboard: classified / outcomes / software companies / remaining |

**Lens** (Phase 8.5 / U2+U3 — a user's words become rows and answers, never code edits; `add_skill` audits):

| Tool | Does |
|---|---|
| `find_industry_codes` | plain words ("care homes") → ranked SIC candidates with sponsor counts + matched words; write the confirmed codes with `set_promotion_rule` |
| `add_skill` | record one owner-scoped skill (upsert by normalised name) with `evidence` + `learned_at` — the learning-curve model's day-one data |
| `search_sponsors` | ALL sponsors by plain-English industry / town / board status over `v_sponsor_industry` — receipts = the industry descriptions that matched |
| `search_hiring` | "who is hiring \<role words> and can sponsor?" — live tracked listings first, then census sightings; the matching title is the receipt |

**Onboarding** (Phase 9 task 4 — a new owner reaches their first nudge by conversation; the writes audit):

| Tool | Does |
|---|---|
| `get_intake_interview` | the served, versioned `intake-v1` interview + the fact base's current state — the engine owns the questions, whatever AI the user brings |
| `create_profile` | operator-only until sign-in (task 6): creates the new owner's row through the one sanctioned re-scope; friend keys are refused; the key is minted out of band |
| `set_notification_channel` | the caller sets their OWN ntfy topic — stored, never echoed back, audited as "changed", never as the value |
| `set_notion_token_ref` | stores the NAME of the caller's Notion credential (token-shaped values are refused); read by nobody until per-owner filing lands |

**Self-serve keys** (Phase 9 task 6 — signed-in owners only; a minted key can never mint another):

| Tool | Does |
|---|---|
| `issue_my_key` | mints a key for the CALLER'S OWN profile (no owner argument exists); shown once, stored as a digest, audited as "issued" and never as the value |
| `revoke_my_key` | revokes one of the caller's own keys; another owner's key id answers exactly as an unknown one, so it cannot be used to discover key ids |

## Run the pipeline
```bash
.venv/bin/python scripts/run.py                                  # the full daily loop (register -> discover -> ... -> nudge)
PYTHONPATH=src .venv/bin/python scripts/build_synonyms.py        # canonicalise new skill names
PYTHONPATH=src .venv/bin/python scripts/eval_extraction.py       # grounding eval
PYTHONPATH=src .venv/bin/python scripts/jobqueue.py              # view the ranked queue
```
All scripts except `run.py` need `PYTHONPATH=src`.

Stage order (Phase 8.5): register (weekly, self-skipping) → classify →
discover → fetch → read → synonyms → **merge** (matched ads join the queue) →
**jd_drip** (U5: Reed full JDs for ad-only rows, shared 950/day cap) →
**promote** (the owner's rule promotes census cards) → salary → deadlines
(survival curves; flat window where history is thin) → eval →
**stage_reading** (sieve-3 tray) → file → nudge.

**Phase 9 task 3 split that order in two, without moving any of it.** The
first eight stages are **world work** and run ONCE a night whatever the owner
count: the register, the census, the ads and the boards are shared data and a
second owner costs nothing there. The last seven — promote, salary, deadlines,
eval, stage_reading, file, nudge — are the **personal pass** and run once per
owner, each with their own rule, apply window, tray, board and channel. Each
personal stage takes `--owner <profile_id>`; none of them may discover an
owner for itself, which is what B-GAE-027 and B-GAE-028 were.

Owners come from `pipeline.owners`: sorted by `profile_id`, then sharded by
Cloud Run's `CLOUD_RUN_TASK_INDEX` / `CLOUD_RUN_TASK_COUNT` (defaulting to
0 of 1, so today's single-task job is every owner, serially, exactly as
before). Raising the job's `taskCount` fans the same code out with no edit.

## API budgets (Phase 9 task 5)

Three external APIs cost quota — `adzuna`, `reed`, `companies_house` — and
every call to them is counted twice: against the **world cap** (the provider's
shared day) and, when the run belongs to somebody, against that owner's
**daily budget**. So one key holder can never eat the shared quota, and the
nightly world half — which passes no owner — spends only the world's.

The gate is in the HTTP client, not in the tools. There are exactly two
functions that reach these APIs (`discover.aggregators._get_json` and
`discover.companies_house._get_json`), and both charge `budget.gate` before
each attempt. A call is metered by **where it points**: a new helper aimed at
`REED_BASE` is metered automatically, and a board feed (Greenhouse, Lever,
Ashby, Workable, Workday) is free because it points somewhere else.

| Table | Holds |
|---|---|
| `api_budget_caps` | `world_daily` / `owner_daily` per source. Editable without a deploy. A source with **no row** has no budget — the gate fails closed. |
| `api_quota_ledger` | the world counter, `(source, day)`. Unchanged since 0036; the sweep and drip no longer write it directly. |
| `api_owner_spend` | one owner's calls, `(owner_id, source, day)`. |

Through the MCP door all three are **read-only** — an owner sees their own
spend rows and nobody else's, and a forged write raises 42501 (migration 0060
revokes the privilege as well as narrowing the policy; a policy alone would
make the refusal silent). The engine writes them on its own connection.

Who pays travels as `GOAL_A_BUDGET_OWNER` in the environment, because the
spend usually happens two processes away (a tool spawns `run.py`, which spawns
`jd_drip.py`). Unset = the nightly world half, which owes nobody.

A refusal is never an item error. `run_drip`, `run_classify` and `run_slice`
each catch `BudgetExhausted` **above** their per-item `except Exception` and
stop with receipts — otherwise one exhausted day becomes 200 "broken jobs" or
2,000 fabricated census errors. The message says what it means: `budget spent
— resets at midnight UTC`, with spent/cap for the scope that refused.

```bash
# what is left today, without leaving the shell
PYTHONPATH=src .venv/bin/python -c "
from budget.ledger import SOURCES, remaining
from db.connection import get_conn
with get_conn() as c, c.cursor() as cur:
    [print(remaining(cur, s)) for s in SOURCES]"
```

One owner's failed stage is recorded against that owner and the night carries
on — for the rest of their own pass, and for everybody else's.
`pipeline_runs.stages` still holds exactly **one array element per stage
name**, because `v_status_stages` counts those elements and the public status
page renders the count as "15 of 15"; per-owner detail rides as an added
`owners` field on the existing object, and those entries are **numbered, not
named** — no profile_id ever reaches that world-readable table. The seq →
owner map is printed to the run's own stderr, which is operator-only.

```bash
PYTHONPATH=src .venv/bin/python scripts/merge_ads.py             # merge matched aggregator ads into role_listings
PYTHONPATH=src .venv/bin/python scripts/promote_by_rule.py       # one nightly promotion-rule pass
PYTHONPATH=src .venv/bin/python scripts/stage_reading.py         # stage sieve-1/2 survivors for a user's AI
PYTHONPATH=src .venv/bin/python scripts/refresh_register.py      # re-download + diff the sponsor register now
PYTHONPATH=src .venv/bin/python scripts/run_dashboard.py         # the read-only Today page (needs DASHBOARD_TOKEN in .env)
```
The dashboard serves http://127.0.0.1:8377/?token=<DASHBOARD_TOKEN> — the
Today screen (ready vs needs-something with receipts), the honesty panel,
company watch, and the Sponsors tab. It reads only curated views —
`v_today`, `v_scorecard`, `v_health`, `v_sponsor_browse` — and never a raw
table. Pinned by `tests/test_dashboard.py`, which is where the allowed set is
defined; extending it is a deliberate edit there.

## Run the census sweep (Phase 7.5)
The sweep cards every register organisation, batch by batch — resumable,
Gemini-free, and walled off from the daily pipeline (it writes only
`sponsor_census` + `census_jobs`; promotion to tracking stays manual).
```bash
PYTHONPATH=src .venv/bin/python scripts/sweep.py                 # one nightly batch (default 2000 orgs, ~3-4h)
PYTHONPATH=src .venv/bin/python scripts/sweep.py --batch 25      # a small test batch
PYTHONPATH=src .venv/bin/python scripts/sweep.py --retry-errors  # re-card previously errored orgs
PYTHONPATH=src .venv/bin/python scripts/sweep.py --probe-only    # skip registry enrichment
```
- Its own lock (`.sweep.lock`): a sweep and the daily pipeline can coexist; two
  sweeps cannot. Per-org commits mean a crash resumes exactly where it stopped.
- `COMPANIES_HOUSE_API_KEY` in `.env` (free) switches on registry enrichment —
  official industry codes, active/dissolved, incorporation date per org.
  Blank = probe-only, automatically.
- From Claude: the `run_sweep` tool starts a batch detached (log under
  `ops/sweep-logs/`); `sweep_status` shows the scoreboard.

### Pass 2 — software-first probing (after Pass 1 classification)
The founder's sequence: classify ALL orgs first, THEN probe — software lot first.
```bash
PYTHONPATH=src .venv/bin/python scripts/sweep.py --software-only              # sequential
PYTHONPATH=src .venv/bin/python scripts/sweep.py --software-only --workers 4 # parallel (own conn per worker)
```
- Picks ONLY cards with `probe_outcome IS NULL AND registry_outcome='matched'
  AND industry_codes && SOFTWARE_SIC`, active companies first. No registry
  calls (Pass 1 already did that). Per-org commit kept in both modes.
- From Claude: `run_sweep(software_only=true, workers=4)`; Pass-1 runs via
  `run_classification` (detached, logs under `ops/classify-logs/`) with
  `classify_status` as its scoreboard.
- The bridge into the daily pipeline: `list_software_companies` → pick →
  `promote_company` (copies the census board onto `target_companies`; the
  next `start_pipeline`/daily run fetches its jobs) → `get_job_gap`/`generate_cv`
  per listing.

## Where the state of the build is written down
The build follows **Architecture v2** — `architecture/architecture-v2.md` (the
phase cards, including the founder-directed 7.5 / 7.8 / 8.5 insertions).

This file used to carry a "Status (honest)" paragraph restating the phase, the
test count, the migration number and the tool count. Every one of them was wrong
by Phase 9, because nothing checked them (B-GAE-033). The section is deleted
rather than corrected: it duplicated records that already own those facts, and a
duplicate with no guard is a liability, not a service.

| Question | The file that owns the answer |
|---|---|
| What shipped, when, with measured numbers | `docs/progress-log.md` |
| Why a choice was made, and what was rejected | `docs/decision-log.md` |
| What broke, why, and whether it can return | `docs/bug-log.md` |
| Tests, migrations, tools — the current counts | `README.md`'s numbers table (measured by test) |
| Next free id for any record kind | `docs/id-registry.json` |
| What is planned, deferred or superseded | `plans/` (index in `plans/README.md`) |

## Layout
- `src/config.py` — loads settings from `.env`, validates on demand.
- `src/db/connection.py` — direct Postgres (psycopg) connection to Supabase.
- `src/fetch/` — ATS classification + job fetchers (Greenhouse/Lever/Ashby/Workable
  + Workday via `workday.py`); `jd_drip.py` pulls full Reed descriptions for
  ad-only rows.
- `src/discover/` — register walk, aggregators, onboarding, merge and rule
  promotion; the census sweep (`sweep.py`, `census_store.py`) and the
  per-country registry plug-in (`companies_house.py`).
- `src/read/` — the **deterministic keyword extractor** (`extract.py`) that the
  pipeline actually uses, plus the grounding eval (`eval.py`). `gemini.py` is the
  retired AI reader: still present, reachable only if `GEMINI_API_KEY` is set,
  and set nowhere the engine runs.
- `src/reading/` — the tray: what gets staged for a user's AI (`stage.py`), what
  is served to it (`serve.py`), and the grounding gate every answer comes back
  through (`accept.py`).
- `src/normalise/` — `text.py` (the one normaliser) and `synonyms.py`, the skill
  synonym map. Its AI path shares `read/gemini.py`'s client and is dormant for
  the same reason; low-confidence mappings become review flags either way.
- `src/analysis/` — salary text parsing and search. The ranked apply queue lives
  in **SQL views** (`v_apply_queue`, `v_skill_gap` — see `db/migrations/`) with
  `scripts/jobqueue.py` as the CLI over them; the salary wall judges against
  per-SOC going rates (Phase 2).
- `src/match/` — the fit maths: score, probability, decay, stats.
- `src/cv/` — the fact base (`blocks.py`), the serve-all hand-over
  (`serve_all.py`), the truth gate (`truth.py`), rendering and filing.
- `src/criteria/` — the owner's profile, skills, lens and target roles.
- `src/auth/` — sign-in: a verified identity mapped to a profile (Phase 9 task 6).
- `src/budget/` — the per-source caps and the two-scope spend ledger.
- `src/pipeline/` — the run orchestrator, the per-owner fan-out (`owners.py`) and
  the run report.
- `src/mcp_server/` — the skin: transport, identity, session scoping, and the
  tool modules. No engine file may name it (an invariant test scans for the
  string).
- `src/status/`, `src/dashboard/` — the two read-only pages, each pinned to
  curated views by its own test.
- `db/migrations/` — the SQL record of every schema change, applied via Supabase
  MCP and mirrored here. `ops/ci/` builds a blank database from it.

## Database access during build
Schema changes are applied via the Supabase MCP (`apply_migration`) and mirrored into
`db/migrations/` as a record. The runtime engine connects directly via psycopg using `DATABASE_URL`.
