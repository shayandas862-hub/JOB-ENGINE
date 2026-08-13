"""Serve the read-only Today page locally (token-protected, 127.0.0.1).

    python scripts/run_dashboard.py [--port 8377]

Needs DASHBOARD_TOKEN in .env; open /?token=<value>. Read-only by
construction — the page reads the three curated views and nothing else.
"""
from __future__ import annotations

import argparse

from config import get_settings
from dashboard.server import DEFAULT_PORT, serve


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = ap.parse_args()
    get_settings()          # loads .env so DASHBOARD_TOKEN reaches the env
    serve(port=args.port)


if __name__ == "__main__":
    main()
