#!/bin/sh
# One image, four doors (Phase 8 task 1). The first word picks the process;
# everything after it passes straight through to that process.
#
#   run        the daily pipeline           (scripts/run.py, accepts --dry-run)
#   mcp        the MCP server               (the skin; transport per its config)
#   status     the public status page       (src/status/ — lands in task 4)
#   dashboard  the founder's Today page     (scripts/run_dashboard.py)
set -eu

door="${1:-run}"
if [ "$#" -gt 0 ]; then shift; fi

case "$door" in
  run)       exec python scripts/run.py "$@" ;;
  mcp)       exec python -m mcp_server.server "$@" ;;
  status)    exec python -m status.server "$@" ;;
  dashboard) exec python scripts/run_dashboard.py "$@" ;;
  *)
    echo "usage: {run|mcp|status|dashboard} [args...]" >&2
    echo "unknown command: $door" >&2
    exit 2
    ;;
esac
