#!/usr/bin/env bash
# Unattended aggregator drip runner (broad ad sweep + register match).
# Fully Claude-independent, like run-sweep.sh. Board learning is a separate
# free run: `scripts/sweep.py --hiring` (link-following retired 2026-07-27).
#
# Start:            nohup ops/run-aggregator.sh >/dev/null 2>&1 & disown
# Graceful stop:    touch .aggregator-stop      (takes effect within ~10s)
#                   delete the file and re-launch to resume — zero loss,
#                   per-page commits mean the cursor resumes exactly.
# Immediate stop:   pkill -f run-aggregator.sh; pkill -f scripts/agg_sweep.py
#
# Quota-bound by design: on "quota exhausted" it sleeps 30 min and retries —
# past midnight the ledger resets and the drip simply continues, day after
# day, until every slice reports pass complete. No caffeinate needed: if the
# laptop sleeps, the drip pauses harmlessly and resumes on wake.
#
# Usage: ops/run-aggregator.sh [PAGES_PER_SLICE_PER_CYCLE]   (default 40)
set -u
cd "$(dirname "$0")/.." || exit 1

PAGES="${1:-40}"
mkdir -p ops/aggregator-logs
LOG="ops/aggregator-logs/agg-$(date -u +%Y%m%dT%H%M%SZ).log"
echo "[wrapper] starting aggregator drip · pages/slice/cycle=$PAGES · log=$LOG"

while true; do
  if [ -e .aggregator-stop ]; then
    echo "[wrapper] stop file present — stopping cleanly. Delete .aggregator-stop and re-launch to resume." >> "$LOG"
    break
  fi

  PYTHONPATH=src .venv/bin/python scripts/agg_sweep.py --pages "$PAGES" >> "$LOG" 2>&1
  tail_out="$(tail -n 15 "$LOG")"

  if grep -q "outcome: pass complete (all slices)" <<<"$tail_out"; then
    echo "[wrapper] every slice complete — the pass is done. Re-launch for a fresh pass." >> "$LOG"
    break
  fi
  if grep -q "another aggregator sweep is in progress" <<<"$tail_out"; then
    echo "[wrapper] stopping: another aggregator run holds the lock." >> "$LOG"
    break
  fi
  if grep -q "outcome: quota exhausted" <<<"$tail_out"; then
    echo "[wrapper] daily quota spent — sleeping 30 min (ledger resets at midnight)." >> "$LOG"
    for _ in $(seq 1 180); do
      [ -e .aggregator-stop ] && break
      sleep 10
    done
  elif grep -q "outcome: source error" <<<"$tail_out"; then
    echo "[wrapper] source error — sleeping 60s before retrying." >> "$LOG"
    for _ in $(seq 1 6); do
      [ -e .aggregator-stop ] && break
      sleep 10
    done
  else
    sleep 2   # brief breather, then the next page budget
  fi
done
