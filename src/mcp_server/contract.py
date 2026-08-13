"""Contract v2's uniform envelope — one shape for every tool result.

Every tool returns {"result": <payload>, "next": {"state", "call", "why"}}:
what came back, where the machine stands, the one suggested next call (None
when the loop is done), and why — so any vendor's AI runs the whole loop
with zero client-side prompting. Built here and nowhere else.
"""
from __future__ import annotations


def with_next(payload, *, state: str, call: str | None, why: str) -> dict:
    """Wrap a tool payload in the uniform contract-v2 envelope."""
    return {"result": payload,
            "next": {"state": state, "call": call, "why": why}}


# M4 (0013 §6): the six loop tools declare their shape so a client can
# validate what it receives; every other tool keeps prose ON PURPOSE —
# type where it pays, then stop. The next block is the contract itself.
NEXT_SCHEMA = {
    "type": "object",
    "properties": {"state": {"type": "string"},
                   "call": {"type": ["string", "null"]},
                   "why": {"type": "string"}},
    "required": ["state", "call", "why"],
    "additionalProperties": False,
}


def envelope_schema(result_schema: dict) -> dict:
    """The typed envelope: result's stable core + the pinned next block.

    result schemas stay additive (additionalProperties true, required =
    the always-present core) so a field added tomorrow does not break a
    validating client today.
    """
    return {"type": "object",
            "properties": {"result": result_schema, "next": NEXT_SCHEMA},
            "required": ["result", "next"],
            "additionalProperties": False}
