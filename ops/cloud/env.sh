#!/usr/bin/env bash
# One source of cloud names — every ops/cloud script sources this file.
# No secret VALUES here, ever: values live in the local .env and, in the
# cloud, in Google Secret Manager only.
set -euo pipefail

PROJECT_ID="goal-a-engine"
REGION="europe-west2"                        # London
AR_REPO="engine"                             # Artifact Registry repository
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPO}/goal-a-engine"

JOB_NAME="goal-a-daily"
JOB_TIMEOUT="5400"                           # 90 min: register+classify nights
SCHEDULER_NAME="goal-a-daily-morning"
SCHEDULE="30 6 * * *"                        # before the founder's apply hour
SCHEDULE_TZ="Europe/London"

MCP_SERVICE="goal-a-mcp"                     # task 3: the hosted MCP door
STATUS_SERVICE="goal-a-status"               # task 4: the PUBLIC status page

RUNNER_SA="goal-a-runner"                    # the job's runtime identity
INVOKER_SA="goal-a-invoker"                  # the scheduler's identity
MCP_SA="goal-a-mcp"                          # the MCP service's own identity
STATUS_SA="goal-a-status"                    # the status page's own identity
DEPLOYER_SA="goal-a-deployer"                # CI's identity (task 5b)
RUNNER_EMAIL="${RUNNER_SA}@${PROJECT_ID}.iam.gserviceaccount.com"
INVOKER_EMAIL="${INVOKER_SA}@${PROJECT_ID}.iam.gserviceaccount.com"
MCP_EMAIL="${MCP_SA}@${PROJECT_ID}.iam.gserviceaccount.com"
STATUS_EMAIL="${STATUS_SA}@${PROJECT_ID}.iam.gserviceaccount.com"
DEPLOYER_EMAIL="${DEPLOYER_SA}@${PROJECT_ID}.iam.gserviceaccount.com"

# Workload Identity Federation — CI authenticates with a short-lived OIDC token
# minted by GitHub, bound to ONE repository. No service-account key is ever
# exported (NOTES.md), because a key is a permanent credential and this is not.
WIF_POOL="github-pool"
WIF_PROVIDER="github-provider"
GITHUB_REPO="shayandas862-hub/GOAL-A"

# Every secret this project manages — what push-secrets.sh loads into Secret
# Manager. tests/test_cloud_setup.py pins this list and bans the
# retired/deferred key names from every file in this folder. The nudge topic is
# DB-side data, so it needs no secret here. Growing this list is a DELIBERATE
# contract change: the test carries the count in its NAME so an accidental
# ninth secret cannot slip in quietly.
#
# SUPABASE_URL joined in Phase 9 task 6 and is the one entry here that is NOT
# confidential — it is the project's public URL, and the MCP door derives the
# JWKS endpoint it verifies sign-in tokens against from it. It rides through
# Secret Manager because it carries the project REF, which never enters the
# public repository; this is the only path this project has for a value that
# must stay out of git. Setting it is what switches sign-in ON.
SECRETS="DATABASE_URL ADZUNA_APP_ID ADZUNA_APP_KEY REED_API_KEY COMPANIES_HOUSE_API_KEY DASHBOARD_TOKEN MCP_TOKEN SUPABASE_URL"

# Least privilege per surface: each runtime mounts only what it actually uses,
# so one door being reached never hands over the other's credentials.
# The daily job runs the pipeline and never serves MCP -> no MCP_TOKEN.
JOB_SECRETS="DATABASE_URL ADZUNA_APP_ID ADZUNA_APP_KEY REED_API_KEY COMPANIES_HOUSE_API_KEY DASHBOARD_TOKEN"
# The MCP service answers requests against the database and guards the door.
# It gets NO aggregator keys: its tools that spawn scripts are not durable in a
# Cloud Run service anyway (see src/pipeline/trigger.py start_pipeline), so a
# key it cannot reliably use is exposure without benefit.
# SUPABASE_URL is here and nowhere else: the MCP door is the ONLY surface that
# verifies sign-in tokens. The daily job and the status page have no identity
# to check and are not given one.
MCP_SECRETS="DATABASE_URL MCP_TOKEN SUPABASE_URL"
# The PUBLIC status page holds no token at all — there is nothing to guard, by
# design (migration 0043's views are the privacy boundary). It reads the
# database and nothing more, so it carries the fewest secrets of any surface.
STATUS_SECRETS="DATABASE_URL"
