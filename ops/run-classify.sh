#!/usr/bin/env bash
# Unattended Pass-1 classification runner.
#
# Runs scripts/classify_sponsors.py back-to-back in moderate batches until the
# whole register carries an industry code. Auto-restarts after a transient death
# (network blip, laptop wake) because per-company commits make every restart
# resume from the exact company. Stops cleanly when a batch classifies 0 (done),
# when the Companies House key is missing, or when another run holds the lock.
#
# To stop by hand: pkill -f classify_sponsors  (per-company commit = no data lost;
# just re-launch this script to resume from where it left off).
#
# Usage: ops/run-classify.sh [BATCH]   (BATCH default 5000)
set -u
cd "$(dirname "$0")/.." || exit 1

BATCH="${1:-5000}"
LOG="ops/classify-logs/classify-$(date -u +%Y%m%dT%H%M%SZ).log"
echo "[wrapper] starting classification runner · batch=$BATCH · log=$LOG"

while true; do
  PYTHONPATH=src .venv/bin/python scripts/classify_sponsors.py --batch "$BATCH" >> "$LOG" 2>&1
  tail_out="$(tail -n 25 "$LOG")"

  if grep -q "batch done: 0 classified" <<<"$tail_out"; then
    echo "[wrapper] register fully classified — nothing left. Done." >> "$LOG"
    break
  fi
  if grep -q "COMPANIES_HOUSE_API_KEY is not set" <<<"$tail_out"; then
    echo "[wrapper] stopping: Companies House key missing." >> "$LOG"
    break
  fi
  if grep -q "another classification run is in progress" <<<"$tail_out"; then
    echo "[wrapper] stopping: another run holds the lock." >> "$LOG"
    break
  fi
  sleep 2   # brief breather, then pick up the next batch
done
