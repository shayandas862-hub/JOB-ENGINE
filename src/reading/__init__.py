"""Sieve-3: the staged reading tray (Phase 7.8).

The engine never reads JDs with its own AI here — it stages sieve-1/2
survivors (stage), serves them with a versioned server-side extraction
prompt (serve), and deterministically verifies whatever a user's AI submits
back (accept). The engine's keyword fallback remains the default reader, so
the daily run never waits on any of this.
"""
