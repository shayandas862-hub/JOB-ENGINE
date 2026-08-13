#!/usr/bin/env bash
# Workload Identity Federation for CI (Phase 8 task 5b), idempotent.
#
# Lets GitHub Actions deploy WITHOUT a service-account key. GitHub mints a
# short-lived OIDC token for a workflow run; Google trades it for a
# minutes-long access token, and only if the token says it came from THIS
# repository. ops/cloud/NOTES.md forbids exported keys, and this is why: a
# leaked JSON key is a permanent credential with no expiry and no origin.
#
# The attribute CONDITION is the security control. Without it, any repository
# on GitHub could present a valid token and be accepted — the pool trusts the
# issuer, not the author. Everything else here is least privilege.
#
# Run once, as the founder. Usage: setup-wif.sh
set -euo pipefail
cd "$(dirname "$0")/../.."
source ops/cloud/env.sh

gcloud config set project "${PROJECT_ID}" --quiet
PROJECT_NUMBER="$(gcloud projects describe "${PROJECT_ID}" --format='value(projectNumber)')"

echo "== APIs =="
gcloud services enable iamcredentials.googleapis.com sts.googleapis.com --quiet

echo "== the deployer identity =="
gcloud iam service-accounts describe "${DEPLOYER_EMAIL}" >/dev/null 2>&1 || \
  gcloud iam service-accounts create "${DEPLOYER_SA}" \
    --display-name "Goal A CI deployer (no key, WIF only)"

# A just-created service account is not immediately usable as an IAM MEMBER —
# the binding fails with "does not exist" for a few seconds. Seen live on the
# first run of this script. Wait for it rather than leave a re-run-to-fix step.
retry() {   # retry <attempts> <command...>
  local attempts="$1"; shift
  local i
  for (( i = 1; i <= attempts; i++ )); do
    if "$@" >/dev/null 2>&1; then return 0; fi
    echo "    ...propagating, retry ${i}/${attempts}"
    sleep 5
  done
  echo "  FAILED after ${attempts} attempts: $*" >&2
  return 1
}
retry 12 gcloud iam service-accounts describe "${DEPLOYER_EMAIL}"

echo "== what CI may do: push an image, roll a revision, act as the runtimes =="
# Deliberately NOT owner/editor, and deliberately no secretAccessor: CI names
# the secrets a service mounts, it never needs to READ one.
for role in roles/run.developer roles/artifactregistry.writer; do
  gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member "serviceAccount:${DEPLOYER_EMAIL}" --role "${role}" \
    --condition=None --quiet >/dev/null
  echo "  granted ${role}"
done
# Deploying a service that RUNS AS another identity requires acting as it —
# granted per service account, never project-wide.
for sa in "${RUNNER_EMAIL}" "${MCP_EMAIL}" "${STATUS_EMAIL}"; do
  retry 12 gcloud iam service-accounts add-iam-policy-binding "${sa}" \
    --member "serviceAccount:${DEPLOYER_EMAIL}" \
    --role roles/iam.serviceAccountUser --quiet
  echo "  may act as ${sa}"
done

echo "== the identity pool =="
gcloud iam workload-identity-pools describe "${WIF_POOL}" --location=global >/dev/null 2>&1 || \
  gcloud iam workload-identity-pools create "${WIF_POOL}" --location=global \
    --display-name "GitHub Actions"

echo "== the provider, restricted to one repository =="
if ! gcloud iam workload-identity-pools providers describe "${WIF_PROVIDER}" \
      --location=global --workload-identity-pool="${WIF_POOL}" >/dev/null 2>&1; then
  gcloud iam workload-identity-pools providers create-oidc "${WIF_PROVIDER}" \
    --location=global --workload-identity-pool="${WIF_POOL}" \
    --display-name "GitHub OIDC" \
    --issuer-uri="https://token.actions.githubusercontent.com" \
    --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.repository_owner=assertion.repository_owner" \
    --attribute-condition="assertion.repository=='${GITHUB_REPO}'"
else
  gcloud iam workload-identity-pools providers update-oidc "${WIF_PROVIDER}" \
    --location=global --workload-identity-pool="${WIF_POOL}" \
    --attribute-condition="assertion.repository=='${GITHUB_REPO}'"
fi

echo "== only THIS repository may impersonate the deployer =="
POOL_ID="projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${WIF_POOL}"
gcloud iam service-accounts add-iam-policy-binding "${DEPLOYER_EMAIL}" \
  --member "principalSet://iam.googleapis.com/${POOL_ID}/attribute.repository/${GITHUB_REPO}" \
  --role roles/iam.workloadIdentityUser --quiet >/dev/null

echo
echo "done. Put these two in the workflow (neither is a secret):"
echo "  workload_identity_provider: ${POOL_ID}/providers/${WIF_PROVIDER}"
echo "  service_account:            ${DEPLOYER_EMAIL}"
