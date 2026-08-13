"""AI spot #3 — Gemini rephrases verified facts into tailored CV bullets.

Caged like the other two AI spots: reuses the read.gemini client + retry, runs
at temperature 0 under a strict "rephrase the supplied facts only, add nothing"
instruction, and falls back to the un-rephrased fact whenever it can't do that
safely — no key, an API failure, or a block the model didn't return. Each result
keeps its source fact so the truth gate (Task 4) can verify the bullet against it;
the gate, not this module, is the real enforcement.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from google.genai import types

from read.gemini import MODEL, generate_with_retry, get_client


@dataclass(frozen=True)
class PhrasedBlock:
    block_id: int
    kind: str
    title: str | None
    organisation: str | None
    date_range: str | None
    source_fact: str          # verbatim cv_blocks.fact_text — the grounding source
    bullet: str               # the tailored line, or the source fact on any fallback


_INSTRUCTION = (
    "You are writing bullets for ONE person's CV, tailored to a target role. You "
    "are given verified career FACTS, one per block. Rephrase EACH fact into a "
    "single concise, ATS-friendly CV bullet. Absolute rules:\n"
    "- Use ONLY the information in that block's fact. Add nothing.\n"
    "- Invent no numbers, employers, dates, tools, or skills that are not in the fact.\n"
    "- Never merge information from other blocks.\n"
    "- Emphasise the parts most relevant to the target role, but never at the cost of truth.\n"
    "Return JSON matching the schema: exactly one {block_id, bullet} per input block."
)

_RESPONSE_SCHEMA = types.Schema(
    type=types.Type.ARRAY,
    items=types.Schema(
        type=types.Type.OBJECT,
        required=["block_id", "bullet"],
        properties={
            "block_id": types.Schema(type=types.Type.INTEGER),
            "bullet": types.Schema(type=types.Type.STRING),
        },
    ),
)


def _fallback(block, bullet=None) -> PhrasedBlock:
    """A phrased block whose bullet is just the verified fact (un-rephrased)."""
    text = bullet.strip() if bullet and bullet.strip() else block.fact_text
    return PhrasedBlock(block.block_id, block.kind, block.title, block.organisation,
                        block.date_range, block.fact_text, text)


def _parse_bullets(raw: str | None) -> dict[int, str]:
    if not raw:
        return {}
    out: dict[int, str] = {}
    for item in json.loads(raw) or []:
        try:
            out[int(item["block_id"])] = item.get("bullet") or ""
        except (KeyError, TypeError, ValueError):
            continue
    return out


def phrase_blocks(blocks, *, listing_title=None, listing_skills=None,
                  api_key: str | None = None, client=None, model: str = MODEL) -> list[PhrasedBlock]:
    """Rephrase each block's fact into a tailored bullet; fall back on any doubt."""
    blocks = list(blocks)
    if not blocks:
        return []
    if client is None and not api_key:
        return [_fallback(b) for b in blocks]        # no way to call the model

    try:
        client = client or get_client(api_key)
        payload = {
            "target_role": listing_title or "",
            "target_skills": sorted(listing_skills or []),
            "blocks": [{"block_id": b.block_id, "fact": b.fact_text} for b in blocks],
        }
        resp = generate_with_retry(
            client, model=model,
            contents=_INSTRUCTION + "\n\nINPUT:\n" + json.dumps(payload),
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=_RESPONSE_SCHEMA, temperature=0))
        bullets = _parse_bullets(resp.text)
    except Exception:
        return [_fallback(b) for b in blocks]        # any failure -> un-rephrased

    return [_fallback(b, bullets.get(b.block_id)) for b in blocks]
