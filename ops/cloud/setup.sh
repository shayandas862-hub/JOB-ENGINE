#!/usr/bin/env bash
# The cloud spine, idempotent: APIs -> registry -> identities -> secret
# access -> the daily Job -> the morning schedule. Safe to re-run; updates
# specs in place. Run AFTER the founder's gcloud login, push-secrets.sh and
# build-push.sh. Usage: setup.sh [image-tag]   (default: latest)
set -euo pipefail
cd "$(dirname "$0")/../.."
source ops/cloud/env.sh

TAG="${1:-latest}"

gcloud config set project "${PROJECT_ID}" --quiet

echo "== APIs =="
gcloud services enable run.googleapis.com cloudscheduler.googleapis.com \
  secretmanager.googleapis.com artifactregistry.googleapis.com --quiet

echo "== Artifact Registry =="
gcloud artifacts repositories describe "${AR_REPO}" --location "${REGION}" >/dev/null 2>&1 || \
gcloud artifacts repositories create "${AR_REPO}" --location "${REGION}" \
  --repository-format=docker --description="Goal A Engine images"

echo "== service accounts =="
gcloud iam service-accounts describe "${RUNNER_EMAIL}" >/dev/null 2>&1 || \
  gcloud iam service-accounts create "${RUNNER_SA}" --display-name "Goal A daily job runtime"
gcloud iam service-accounts describe "${INVOKER_EMAIL}" >/dev/null 2>&1 || \
  gcloud iam service-accounts create "${INVOKER_SA}" --display-name "Goal A scheduler invoker"

# "NAME NAME2" -> "NAME=NAME:latest,NAME2=NAME2:latest" for --set-secrets.
# Built from the env.sh lists so the names live in exactly one place.
secret_flags() {
  local out="" name
  for name in $1; do out="${out:+${out},}${name}=${name}:latest"; done
  printf '%s' "${out}"
}

# Each identity may read only the secrets its own surface mounts.
grant_secret_access() {   # $1 = member email, $2 = secret name list
  local name
  for name in $2; do
    gcloud secrets add-iam-policy-binding "${name}" \
      --member "serviceAccount:$1" \
      --role roles/secretmanager.secretAccessor --quiet >/dev/null
  done
}

echo "== secret access: each identity reads only its own surface's secrets =="
grant_secret_access "${RUNNER_EMAIL}" "${JOB_SECRETS}"

echo "== the daily job =="
# Every secret mounts as an env var of its own name; the image's default door
# IS `run`, so nothing overrides the entrypoint or its arguments — the
# contract stays with the Dockerfile (and with tests/test_docker.py).
JOB_VERB=create
gcloud run jobs describe "${JOB_NAME}" --region "${REGION}" >/dev/null 2>&1 && JOB_VERB=update
gcloud run jobs "${JOB_VERB}" "${JOB_NAME}" \
  --region "${REGION}" \
  --image "${IMAGE}:${TAG}" \
  --service-account "${RUNNER_EMAIL}" \
  --set-secrets "$(secret_flags "${JOB_SECRETS}")" \
  --memory 2Gi --cpu 1 \
  --task-timeout="${JOB_TIMEOUT}" \
  --max-retries=1

echo "== the hosted MCP service =="
# Task 3. The image's `mcp` door with MCP_TRANSPORT=http: token-gated and
# rate-limited in code (src/mcp_server/transport.py), which REFUSES to start
# without MCP_TOKEN — no token, no door.
#
# --allow-unauthenticated is deliberate and is not "no auth": Google IAM
# would demand an OAuth identity the founder's AI client cannot mint, which
# would lock out the only intended user. The bearer token IS the door, and
# the container will not serve without one. Rejected: IAM-authenticated, which
# no MCP client can satisfy today.
#
# --min-instances 0 means it costs nothing while idle and cold-starts on
# first call. Its own identity reads only MCP_SECRETS.
gcloud iam service-accounts describe "${MCP_EMAIL}" >/dev/null 2>&1 || \
  gcloud iam service-accounts create "${MCP_SA}" --display-name "Goal A hosted MCP"
grant_secret_access "${MCP_EMAIL}" "${MCP_SECRETS}"

gcloud run deploy "${MCP_SERVICE}" \
  --region "${REGION}" \
  --image "${IMAGE}:${TAG}" \
  --args mcp \
  --service-account "${MCP_EMAIL}" \
  --set-secrets "$(secret_flags "${MCP_SECRETS}")" \
  --set-env-vars "MCP_TRANSPORT=http" \
  --memory 1Gi --cpu 1 \
  --min-instances 0 --max-instances 2 \
  --allow-unauthenticated \
  --quiet

echo "== the public status page =="
# Task 4. The image's `status` door: read-only aggregates from the curated
# views of migration 0043, for anyone — a hiring manager, a stranger.
#
# --allow-unauthenticated here means what it says, and is NOT the same claim as
# the MCP section above. There the bearer token is the door; here there is
# genuinely nothing to guard, because the VIEWS are the privacy boundary —
# no personal column is even reachable, and the page accepts no input. It
# therefore carries the fewest secrets of any surface: the database, and no
# token of any kind.
gcloud iam service-accounts describe "${STATUS_EMAIL}" >/dev/null 2>&1 || \
  gcloud iam service-accounts create "${STATUS_SA}" --display-name "Goal A public status page"
grant_secret_access "${STATUS_EMAIL}" "${STATUS_SECRETS}"

gcloud run deploy "${STATUS_SERVICE}" \
  --region "${REGION}" \
  --image "${IMAGE}:${TAG}" \
  --args status \
  --service-account "${STATUS_EMAIL}" \
  --set-secrets "$(secret_flags "${STATUS_SECRETS}")" \
  --memory 512Mi --cpu 1 \
  --min-instances 0 --max-instances 3 \
  --allow-unauthenticated \
  --quiet

echo "== permission to fire the job =="
gcloud run jobs add-iam-policy-binding "${JOB_NAME}" --region "${REGION}" \
  --member "serviceAccount:${INVOKER_EMAIL}" --role roles/run.invoker --quiet >/dev/null

echo "== the morning schedule =="
RUN_URI="https://run.googleapis.com/v2/projects/${PROJECT_ID}/locations/${REGION}/jobs/${JOB_NAME}:run"
SCHED_VERB=create
gcloud scheduler jobs describe "${SCHEDULER_NAME}" --location "${REGION}" >/dev/null 2>&1 && SCHED_VERB=update
gcloud scheduler jobs "${SCHED_VERB}" http "${SCHEDULER_NAME}" \
  --location "${REGION}" \
  --schedule="${SCHEDULE}" \
  --time-zone="${SCHEDULE_TZ}" \
  --uri="${RUN_URI}" \
  --http-method POST \
  --oauth-service-account-email "${INVOKER_EMAIL}"

echo "done. fire one now:  gcloud run jobs execute ${JOB_NAME} --region ${REGION} --wait"
