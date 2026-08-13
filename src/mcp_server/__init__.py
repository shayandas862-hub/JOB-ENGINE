"""FastMCP server package — a thin skin over the deterministic engine.

Every tool is a typed wrapper around ONE existing engine function or query; zero
business logic lives here. New behaviour goes into ``src/`` (tested), then a tool
calls it. Killing this server changes nothing about the daily pipeline — the
scheduled run.py path never imports this package.

Named ``mcp_server`` (not ``mcp``) on purpose: with ``PYTHONPATH=src`` a local
package named ``mcp`` shadows the installed ``mcp`` SDK that fastmcp imports
internally, which breaks the server at import time (verified). The founder
approved this deviation from the CLAUDE.md's ``src/mcp/`` naming in the Phase 5
build session; it is recorded in docs/decision-log.md at phase completion.
"""
