# Cloud setup — what exists and how to drive it

Phase 8 task 2. The daily pipeline runs as a **Cloud Run Job** in project
`goal-a-engine` (region `europe-west2`, London), fired by **Cloud Scheduler**
at **06:30 Europe/London** — before the founder's apply hour. Secrets live in
**Google Secret Manager** (six, listed in `env.sh`; the nudge topic is data in
the `profiles` table, not a secret; the retired/deferred keys are deliberately
absent and a test bans them from this folder).

## Order of operations (first time, and after any change)

1. Founder, once per laptop: `gcloud auth login`
2. `ops/cloud/push-secrets.sh` — local `.env` → Secret Manager (re-run safe:
   new version only when a value changed)
3. `ops/cloud/build-push.sh` — amd64 image → Artifact Registry (needs Docker
   Desktop running; tags: git sha + latest)
4. `ops/cloud/setup.sh [tag]` — APIs, registry, identities, job, schedule
   (idempotent; default tag `latest`)
5. Fire one by hand and watch it:
   `gcloud run jobs execute goal-a-daily --region europe-west2 --wait`

## Where to look

- Runs + per-stage stderr: Cloud Console → Cloud Run → Jobs → `goal-a-daily`
  → Logs. The same stage summaries land in the `pipeline_runs` table.
- Schedule: Cloud Console → Cloud Scheduler → `goal-a-daily-morning`
  (change cadence in `env.sh` and re-run `setup.sh`).
- Spend: Billing → Reports. Expected shape: pennies — the job fits Cloud
  Run's monthly free tier; Scheduler's first three jobs are free; six secrets
  sit at the Secret Manager free-tier edge.

## Design notes

- The job runs the image's **default door** (`run`, the daily pipeline) — no
  command/args overrides, so the container contract stays in one place
  (Dockerfile + tests/test_docker.py).
- Identities are least-privilege: `goal-a-runner` may only read the six
  secrets; `goal-a-invoker` may only fire the job. No service-account keys
  are ever exported — Scheduler authenticates with OAuth as the invoker.
- `--max-retries=1`: stages tolerate a rerun (locks, drips, upserts), and a
  failed run must nudge, not loop.
- The weekly register refresh needs no extra schedule: it self-skips inside
  the daily run (`--if-stale 7`).
- launchd (`ops/launchd/`, never loaded) **retired 2026-08-09** in Stage C6,
  with the founder watching. Its gate — a confirmed clean unattended cloud
  run — was satisfied by run 5, which the scheduler woke by itself at
  18:45:00 UTC as `goal-a-invoker` (14/14 stages, nudge delivered). It was
  verified absent from `launchctl` and `~/Library/LaunchAgents` before removal.
