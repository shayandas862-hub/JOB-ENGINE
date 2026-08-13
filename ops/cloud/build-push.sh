#!/usr/bin/env bash
# Build the linux/amd64 image (Cloud Run's architecture — this laptop is
# arm64, so buildx cross-builds) and push it to Artifact Registry, tagged
# with the git sha (immutable) and :latest (convenience).
set -euo pipefail
cd "$(dirname "$0")/../.."
source ops/cloud/env.sh

TAG="$(git rev-parse --short HEAD)"

gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet
docker buildx build --platform linux/amd64 \
  -t "${IMAGE}:${TAG}" -t "${IMAGE}:latest" --push .

echo "pushed ${IMAGE}:${TAG} (and :latest)"
