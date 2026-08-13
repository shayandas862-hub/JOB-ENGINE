#!/usr/bin/env bash
# Load the six engine secrets from the local .env into Google Secret Manager.
# Values flow .env -> stdin -> Secret Manager: never a CLI argument, never
# echoed, never traced. Re-running is free: a new version is added only when
# the value actually changed.
set -euo pipefail
cd "$(dirname "$0")/../.."
source ops/cloud/env.sh

[ -f .env ] || { echo ".env not found at repo root" >&2; exit 1; }

for name in ${SECRETS}; do
  value="$(grep -E "^${name}=" .env | head -1 | cut -d= -f2-)"
  if [ -z "${value}" ]; then
    echo "SKIP ${name}: empty or missing in .env" >&2
    continue
  fi
  if ! gcloud secrets describe "${name}" --project "${PROJECT_ID}" >/dev/null 2>&1; then
    printf '%s' "${value}" | gcloud secrets create "${name}" \
      --project "${PROJECT_ID}" --replication-policy=user-managed \
      --locations="${REGION}" --data-file=- --quiet
    echo "created ${name}"
  else
    current="$(gcloud secrets versions access latest --secret "${name}" \
      --project "${PROJECT_ID}" 2>/dev/null || true)"
    if [ "${current}" = "${value}" ]; then
      echo "unchanged ${name}"
    else
      printf '%s' "${value}" | gcloud secrets versions add "${name}" \
        --project "${PROJECT_ID}" --data-file=- --quiet
      echo "updated ${name} (new version)"
    fi
  fi
done

echo "-- secrets now in Secret Manager:"
gcloud secrets list --project "${PROJECT_ID}" --format="value(name)"
