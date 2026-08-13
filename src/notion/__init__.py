"""Notion filing — the application tracker the engine writes to headlessly.

A direct REST client (client.py) and the Applications tracker logic (tracker.py):
one idempotent card per gated listing, carrying the job, its sponsor verdict, the
queue rank, the tailored CV and the listing link. This is deliberately NOT the
Claude Notion MCP — the daily loop files without Claude in the room.
"""
