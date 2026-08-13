"""Who a caller is — access keys today, Supabase JWTs in task 6.

Engine-side and transport-free on purpose: this package answers "which owner
does this secret belong to?" over the database and nothing else. The door
that presents the secret lives in the MCP skin; this package never imports
it, so the same answers serve the hosted door, a script, or a future
sign-in flow without change.
"""
