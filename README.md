# Goal A Engine

**A sponsor-aware UK job-search and data-analysis machine.** I built it to run my own
UK job search end-to-end: it takes the entire Home Office sponsor register, works out
which organisations are real, alive, and in software, finds their live careers boards,
extracts the skills each job asks for, matches every one against my own with receipts,
and produces a ranked apply queue — **the human always presses apply, the engine never does.**

It runs itself. A Cloud Run job wakes at 06:30 UK time, works for ~13 minutes, and pushes
the queue to my phone. The laptop can be shut.

**→ [Live status page](https://goal-a-status-fifuwqb3fq-nw.a.run.app)** — generated from the
running database, no login. That page *is* the proof this is not a demo.

Built person-agnostic and country-agnostic on purpose: swap the register dataset and the
national-registry plug-in, and the same machine runs for another person in another country.

## The numbers so far

Every figure below is read from the live database or measured in the repo — not estimated.

| What | Count |
|---|---|
| Sponsor licences tracked from the Home Office register | **144,041** |
| Sponsor organisations classified against Companies House (Pass 1 census) | **128,222 / 128,222 — 0 errors** |
| Software companies identified by official industry codes | **11,931** |
| Live careers boards discovered | **314** |
| Job adverts collected and kept (aggregator layer) | **104,761** |
| Job listings tracked in the pipeline | **13,049** |
| Tests (written red-first, offline by default) | **1163** |
| Database migrations, each one a design decision | **64** |
| MCP tools exposing the engine to an AI (thin skin, zero logic) | **51** |
| Job-board integrations (Greenhouse, Lever, Ashby, Workable, Workday + Adzuna/Reed APIs) | **7** |

The census ran for days on a laptop through sleep, crashes, and dropped connections —
per-organisation commits and self-restarting batches meant it never lost a row.

## How it works

```
Home Office sponsor register (144k licences)
        │
        ▼
Pass 1 — census classify ──── Companies House: real? alive? what industry?
        │                                   (rate-capped, resumable, per-org commit)
        ▼
Pass 2 — board probe ───────── which software sponsors have live careers boards,
        │                      and every job they list (labelled, never filtered)
        ▼
promote (rule-based) ───────── companies matching the owner's rule cross into the
        │                      tracked pipeline; borderline cases are flagged, capped
        ▼
daily loop ─ register → classify → discover → fetch → read → merge → JD drip →
        │    promote → salary wall → deadlines → rank → file → nudge   (15 stages)
        ▼
ranked apply queue ─────────── skills I have vs skills asked, per job, with receipts;
                               gap analysis for everything else. I press apply.
```

## Design principles

- **Code-first, MCP-second.** The deterministic engine does all the work and runs whole
  without any AI in the loop. The MCP server is a thin skin over tested functions — a
  test pins that no engine file even imports it.
- **The engine makes no AI calls at all.** It once used a caged LLM to read job
  descriptions; that was retired in favour of a deterministic keyword extractor plus an
  opt-in path where the *user's own* AI reads a job through a versioned, server-side
  prompt and a grounding gate rejects any claim not present in the text. Engine-side AI
  cost is zero, by design.
- **Every score ships its receipts.** No naked numbers anywhere — a rank, a salary
  verdict, or a deadline can always be traced to the facts that produced it.
- **Labels, not filters.** The census stores every job it sees and stamps labels
  (`is_local`, `title_match`); filtering happens at query time, so no decision is ever
  destroyed by storage.
- **Blast radius pinned by tests.** The census can only write its own two tables — a test
  fails if it ever touches the curated pipeline. Promotion across that wall is an
  audited action.
- **Everything resumable.** Per-row commits, advisory locks, self-restarting wrappers;
  any run can be killed at any moment and continue where it stopped.
- **A check must fail loudly, and differently from "all clear".** Learned the hard way:
  a monitor once reported the exact opposite of the truth because an error was swallowed.
  Silent success and silent breakage must never look alike.
- **The human presses apply.** Always.

## Running in the cloud

One image, four doors, chosen by the command word — `run` (the nightly pipeline),
`mcp` (the hosted tool server), `status` (the public page), `dashboard` (the private one).
Config comes from the environment only; no secret is baked into any layer.

| Surface | Who reaches it | Auth |
|---|---|---|
| Nightly job (Cloud Run Job + Scheduler) | nobody — it runs itself | service account |
| Hosted MCP | my own AI | bearer token, rate-limited |
| Status page | anyone | none, by design — it exposes only machine health |
| Today dashboard | me | token, bound to localhost |

The status page is safe to expose because a curated database view is the privacy
boundary, not the page: the code cannot name a personal column, and a test greps its
source to keep it that way.

CI runs the suite on every push, rebuilds the container and runs the suite *inside* it,
then deploys on green — authenticating with a short-lived OIDC token bound to this one
repository. No service-account key exists anywhere.

## How I work (for the curious reviewer)

This repo is built AI-assisted but engineering-led — the full trail is deliberately public:

- [`docs/VISION.md`](docs/VISION.md) — what the product *is* and *why it exists*, and the dated log of every change to that answer
- [`docs/decision-log.md`](docs/decision-log.md) — dated *why* for every non-obvious choice, including the ones that turned out wrong
- [`docs/progress-log.md`](docs/progress-log.md) — dated *what*, task by task, with measured test counts
- [`plans/`](plans/) — the running plan files: what's done, blocked, deliberately deferred
- [`docs/bug-log.md`](docs/bug-log.md) — every defect this build has hit: cause, fix, the named guard, and whether it can come back
- [`docs/architecture/architecture-v2.md`](docs/architecture/architecture-v2.md) — the master plan and phase cards

The per-phase build instructions are kept privately rather than published: they
are operating instructions, not a record, and what they decided is in the logs
above. Public content here is public by decision, never by omission.

## Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"            # or: pip install -r requirements.lock
cp .env.example .env               # fill in DATABASE_URL (+ optional keys)
PYTHONPATH=src python -m pytest    # the whole suite, offline by default
PYTHONPATH=src python scripts/run.py --dry-run
```

Every key is optional except the database: missing keys degrade cleanly (reading falls
back to keyword extraction, absent sources are skipped, the census runs probe-only).

## Status

Running unattended in Google Cloud: the scheduler wakes the job every morning, the hosted
MCP and the public status page are live, and CI deploys on green.

Honest about what it has not done yet: **it has not got me a job.** The queue fills every
night and the nudges arrive; the applications counter is the number that matters, and the
[status page](https://goal-a-status-fifuwqb3fq-nw.a.run.app) will show the machine's
health whether or not that number moves.

## License

MIT — see [LICENSE](LICENSE).
