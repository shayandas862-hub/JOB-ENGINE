#!/usr/bin/env bash
# Build the whole schema on a blank Postgres, in the order the database grew:
#
#   00-bootstrap.sql   what vanilla Postgres lacks (extensions)
#   01-genesis.sql     the eight tables Phase 1 made before db/migrations/ existed
#   db/migrations/*.sql  every migration, in filename order, none skipped
#
# Used by the CI database lane (.github/workflows/ci.yml) and runnable by hand
# against any throwaway Postgres:
#
#   DATABASE_URL=postgresql://postgres:example-not-a-secret@localhost:5432/goal_a ./ops/ci/apply-schema.sh
#
# It fails on the FIRST error, loudly, naming the file — a half-applied schema
# must never look like a working one. ON_ERROR_STOP is what makes psql do that;
# without it psql reports errors and exits 0, which is exactly the "silence
# where there should be noise" shape this project keeps getting bitten by
# (B-GAE-005).
set -euo pipefail

: "${DATABASE_URL:?DATABASE_URL is not set}"

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo="$(cd "$here/../.." && pwd)"

apply() {
  local file="$1"
  if ! psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -q -f "$file"; then
    echo "FAILED applying: ${file#$repo/}" >&2
    echo "The migration log is mirrored so that it can be replayed. If a" >&2
    echo "migration genuinely cannot apply to a blank Postgres, that is a" >&2
    echo "finding to report — never delete or skip one to make this green." >&2
    exit 1
  fi
}

echo "== bootstrap =="
apply "$here/00-bootstrap.sql"

echo "== genesis (pre-0001 schema) =="
apply "$here/01-genesis.sql"

echo "== migrations =="
count=0
for f in "$repo"/db/migrations/*.sql; do
  apply "$f"
  count=$((count + 1))
  printf '  ok %s\n' "$(basename "$f")"
done
echo "== applied $count migrations =="

# The isolation tests pair every refusal with the same read succeeding for the
# owner, so they need rows to be refused. Skipped with SKIP_SEED=1 when the
# point is to inspect the bare schema.
if [ "${SKIP_SEED:-0}" != "1" ]; then
  echo "== seed (fixture rows, all invented) =="
  apply "$here/02-seed.sql"
fi
