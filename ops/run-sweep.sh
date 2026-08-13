#!/usr/bin/env bash
# Unattended Pass-2 census runner (software-lot job-board probe).
#
# Runs scripts/sweep.py --software-only in moderate batches until every software
# sponsor carries a probe outcome. Auto-restarts after a transient death
# (network blip, laptop wake) because per-org commits make every restart resume
# from the exact org. Fully Claude-independent: survives the app closing.
#
# Stops cleanly when:
#   * a batch picks 0 orgs (the software lot is fully probed — done), or
#   * the stop file `.sweep-stop` exists in the repo root (graceful founder
#     stop: `touch .sweep-stop` — takes effect after the current batch;
#     delete the file and re-launch this script to resume), or
#   * another sweep already holds the lock.
#
# To stop IMMEDIATELY by hand:  pkill -f run-sweep.sh; pkill -f scripts/sweep.py
# (per-org commit = no data lost; re-launch to resume where it stopped).
#
# Usage: ops/run-sweep.sh [BATCH] [WORKERS]   (defaults: BATCH=500, WORKERS=4)
set -u
cd "$(dirname "$0")/.." || exit 1

BATCH="${1:-500}"
WORKERS="${2:-4}"
mkdir -p ops/sweep-logs
LOG="ops/sweep-logs/sweep-$(date -u +%Y%m%dT%H%M%SZ).log"
echo "[wrapper] starting Pass-2 sweep runner · batch=$BATCH · workers=$WORKERS · log=$LOG"

while true; do
  if [ -e .sweep-stop ]; then
    echo "[wrapper] stop file present — stopping cleanly. Delete .sweep-stop and re-launch to resume." >> "$LOG"
    break
  fi

  PYTHONPATH=src .venv/bin/python scripts/sweep.py --software-only \
      --workers "$WORKERS" --batch "$BATCH" >> "$LOG" 2>&1
  tail_out="$(tail -n 25 "$LOG")"

  if grep -q "batch done: 0 picked" <<<"$tail_out"; then
    echo "[wrapper] software lot fully probed — nothing left. Done." >> "$LOG"
    break
  fi
  if grep -q "another sweep is in progress" <<<"$tail_out"; then
    echo "[wrapper] stopping: another sweep holds the lock." >> "$LOG"
    break
  fi
  sleep 2   # brief breather, then pick up the next batch
done
