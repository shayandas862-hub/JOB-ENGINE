#!/usr/bin/env bash
# Build the PUBLIC snapshot locally, and verify it before anyone can see it.
#
# Phase 8 task 7. This does NOT publish anything and does not touch the working
# repo: it exports the current tree into a fresh directory with ONE commit and
# no history at all, then runs the checks that matter on the result.
#
# Why a squash and never a mirror: the Supabase project ref is in this repo's
# history (3 commits, 5 files). `git push --mirror` would publish it forever,
# and rewriting history in the working repo would break every commit id cited
# across the decision log, the progress log and the phase cards. The private
# repo keeps the real history; the public one starts clean at one commit.
#
# Usage: prepare-snapshot.sh [target-dir]     (default: ../goal-a-engine-public)
set -euo pipefail
cd "$(dirname "$0")/../.."
SRC="$(pwd)"
TARGET="${1:-${SRC}/../goal-a-engine-public}"

[ -e "${TARGET}" ] && { echo "target already exists: ${TARGET}" >&2; exit 1; }

echo "== exporting the tracked tree (no .git, no ignored files) =="
mkdir -p "${TARGET}"
git archive HEAD | tar -x -C "${TARGET}"

echo "== the scrub list =="
# Working notes and phase machinery: useful to the build, noise or leakage in
# public. PROJECT-MEMORY.md is a retired runbook that carried the project ref.
# claude-md-archive: every phase's INTERNAL operating instructions (gates,
# rhythms, security-debt lists). Public content is public BY DECISION, never
# by omission — the decision/progress/bug logs are the deliberate public
# story; the archives were never given that decision. Founder call 2026-08-11.
for path in PROJECT-MEMORY.md CLAUDE.md docs/handoffs docs/claude-md-archive; do
  if [ -e "${TARGET}/${path}" ]; then rm -rf "${TARGET:?}/${path}"; echo "  removed ${path}"; fi
done

echo "== the ONE public workflow =="
# B-GAE-035. The snapshot used to ship .github/workflows/ci.yml verbatim, and
# GitHub runs whatever workflow a pushed repository carries — including two
# jobs that authenticate to Google Cloud with credentials that deliberately do
# not exist in public. Every public run failed by construction. The scrub
# checked what the snapshot CONTAINED and never asked what GitHub would DO.
#
# So the workflow directory is emptied and replaced with an allowlist of the
# two lanes that need no credential. Emptying first is what makes it an
# allowlist: a workflow added to the private repo tomorrow does not ride along.
rm -rf "${TARGET:?}/.github/workflows"
mkdir -p "${TARGET}/.github/workflows"
cp "${SRC}/ops/flip/public-ci.yml" "${TARGET}/.github/workflows/ci.yml"
echo "  installed ops/flip/public-ci.yml as .github/workflows/ci.yml"

echo "== one commit, no history =="
cd "${TARGET}"
git init -q -b main
git add -A
git -c user.name="Shayan Das" -c user.email="noreply@users.noreply.github.com" \
    commit -q -m "Goal A Engine — a sponsor-aware UK job-search machine

Squashed public snapshot. The private repository keeps the full build history:
every decision, every measured test count, and the mistakes, are in
docs/decision-log.md and docs/progress-log.md."

echo
echo "== VERIFY: nothing secret survived =="
fail=0
check() {   # check <label> <pattern>
  local hits status n
  # grep's exit status is the whole answer here, so it is CAPTURED rather than
  # flattened. Only two values are answers:
  #     0 = found something   1 = found nothing
  # Anything else (2 and up) means the SCANNER broke — a bad pattern, an
  # unreadable flag — and a broken scanner must never be reported as a clean
  # result. It used to be: `|| true` mapped exit 2 onto the same outcome as
  # "found nothing" and `2>/dev/null` hid grep's complaint, so a typo in a
  # pattern printed four `ok` lines and a CLEAN verdict over a tree that had
  # not been scanned at all (B-GAE-045). The `|| true` was there for a real
  # reason — exit 1 under `set -e` killed the script mid-verification — but
  # the cure treated every failure as success.
  #
  # stderr is deliberately NOT silenced: if grep has something to say about
  # why it failed, that is exactly the sentence someone needs to read.
  #
  # Exclude this script: its own patterns are literal strings inside it, so it
  # matches itself and reports a leak that does not exist. Every other file is
  # scanned, including the rest of ops/.
  set +e
  hits="$(grep -rIl --exclude-dir=.git --exclude="$(basename "$0")" -e "$2" .)"
  status=$?
  set -e
  if [ "${status}" -gt 1 ]; then
    echo "  FAIL ${1}: the scanner itself failed (grep exit ${status}) — this" \
         "snapshot has NOT been checked for it"
    fail=1
    return
  fi
  # Counted without grep on purpose: having just decided grep may be broken,
  # asking it how many lines it produced would be trusting the same tool again.
  if [ -z "${hits}" ]; then n=0; else n="$(printf '%s\n' "${hits}" | wc -l | tr -d ' ')"; fi
  if [ "$n" != "0" ]; then echo "  FAIL ${1}: ${n} file(s)"; fail=1;
  else echo "  ok   ${1}"; fi
}
# By SHAPE, never by value: writing the actual ref here would put it in a
# tracked file, which is the very leak this check exists to catch — and it did,
# on the first run of tests/test_public_safety.py. Matching the host pattern
# also works for a future project, which a hardcoded value never would.
check "no Supabase project ref"      "db\.[a-z]\{20\}\.supabase\.co"
check "no .env"                      "^DATABASE_URL=postgresql://postgres:[^[]"
check "no ntfy topic"                "ntfy\.sh/[0-9a-f]\{24,\}"
check "no apply shortlist"           "Apply-Ready Shortlist"
echo "  history depth: $(git rev-list --count HEAD) commit(s)  (must be 1)"
[ "$(git rev-list --count HEAD)" = "1" ] || { echo "  FAIL: history is not squashed"; fail=1; }
if [ -f LICENSE ]; then
  echo "  LICENSE present: yes"
else
  # Used to print NO and set nothing, so a snapshot with no licence still
  # ended SNAPSHOT CLEAN (B-GAE-045). A public repository with no licence
  # grants no rights to anyone reading it — that is a publishing failure, not
  # a remark, and it fails like every other check here.
  echo "  FAIL LICENSE present: NO"; fail=1
fi

echo
if [ "${fail}" = "0" ]; then
  echo "SNAPSHOT CLEAN -> ${TARGET}"
  echo "Nothing has been published. To publish, the founder creates an EMPTY"
  echo "public repo and pushes this directory once:"
  echo "    git remote add origin <new-public-repo-url> && git push -u origin main"
else
  echo "SNAPSHOT NOT CLEAN — do not publish. Fix the failures above." >&2
  exit 1
fi
