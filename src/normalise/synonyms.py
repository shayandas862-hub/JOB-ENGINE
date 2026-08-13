"""Skill synonym canonicaliser (GA-004) — AI spot #2.

Gemini reads a batch of messy skill names once and maps each to a canonical
form, strongly preferring to match one of *my* skills when equivalent (so the
skill-gap stops counting "ai agents" as missing when I have "AI agent & pipeline
design"). Decisions are cached in the skill_synonyms table and reused forever.

A claimed my-skill match is trusted only if the canonical it returns is actually
one of my skills; otherwise it is downgraded and flagged 'low' for review.
Tests mock the client; no live calls in the suite.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from google.genai import types

from normalise.text import norm
from read.gemini import MODEL, generate_with_retry, get_client


@dataclass(frozen=True)
class SynonymRow:
    raw_norm: str
    canonical_label: str
    canonical_norm: str
    my_skill_match: bool
    confidence: str  # 'high' | 'low'


_SCHEMA = types.Schema(
    type=types.Type.OBJECT,
    required=["mappings"],
    properties={
        "mappings": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(
                type=types.Type.OBJECT,
                required=["raw", "canonical", "my_skill_match", "confidence"],
                properties={
                    "raw": types.Schema(type=types.Type.STRING),
                    "canonical": types.Schema(type=types.Type.STRING),
                    "my_skill_match": types.Schema(type=types.Type.BOOLEAN),
                    "confidence": types.Schema(type=types.Type.STRING, enum=["high", "low"]),
                },
            ),
        ),
    },
)


def _instruction(my_skill_labels: list[str]) -> str:
    skills = "\n".join(f"  - {s}" for s in my_skill_labels)
    return (
        "You are normalising messy job-skill names to canonical forms. For EACH raw "
        "skill name return one mapping object.\n"
        "MY SKILLS (canonical vocabulary — match against these first):\n" + skills + "\n\n"
        "Rules:\n"
        "- If the raw name is the SAME skill as one of MY SKILLS, set canonical to that EXACT "
        "my-skill label and my_skill_match=true (e.g. 'gen ai' -> 'Generative AI', "
        "'ai agents' -> 'AI agent & pipeline design').\n"
        "- Otherwise set my_skill_match=false and canonical to a clean, conventional name "
        "(fix casing/abbreviations: 'postgres' -> 'PostgreSQL', 'k8s' -> 'Kubernetes').\n"
        "- confidence: 'high' if certain, 'low' if unsure (a human will review 'low').\n"
        "- Never invent a my-skill that is not in the list above.\n"
    )


def parse_mappings(raw: str | None, my_skill_labels: list[str]) -> list[SynonymRow]:
    """Parse the model JSON into SynonymRows, validating my-skill claims."""
    if not raw:
        return []
    my_norms = {norm(s): s for s in my_skill_labels}
    rows: list[SynonymRow] = []
    for m in (json.loads(raw).get("mappings") or []):
        raw_name = (m.get("raw") or "").strip()
        canonical = (m.get("canonical") or "").strip()
        if not raw_name or not canonical:
            continue
        confidence = "low" if m.get("confidence") == "low" else "high"
        claimed = bool(m.get("my_skill_match"))
        canon_norm = norm(canonical)
        # Trust a my-skill match only if the canonical really is one of my skills.
        if claimed and canon_norm in my_norms:
            my_match = True
            canonical = my_norms[canon_norm]  # snap to exact my-skill label
        elif claimed:
            my_match = False          # claimed but not real -> distrust
            confidence = "low"
        else:
            my_match = False
        rows.append(SynonymRow(
            raw_norm=norm(raw_name),
            canonical_label=canonical,
            canonical_norm=norm(canonical),
            my_skill_match=my_match,
            confidence=confidence,
        ))
    return rows


def _read_batch(names, my_skill_labels, client, model) -> list[SynonymRow]:
    listing = "\n".join(f"  - {n}" for n in names)
    resp = generate_with_retry(
        client,
        model=model,
        contents=_instruction(my_skill_labels) + "\n\nRAW SKILL NAMES:\n" + listing,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=_SCHEMA,
            temperature=0,
        ),
    )
    return parse_mappings(resp.text, my_skill_labels)


def canonicalize(
    raw_names: list[str],
    my_skill_labels: list[str],
    *,
    client=None,
    model: str = MODEL,
    batch_size: int = 80,
) -> list[SynonymRow]:
    """Map every raw name to a canonical form, batching the model calls."""
    if not raw_names:
        return []
    client = client or get_client()
    out: list[SynonymRow] = []
    for i in range(0, len(raw_names), batch_size):
        out.extend(_read_batch(raw_names[i : i + batch_size], my_skill_labels, client, model))
    return out


def canonicalize_batches(
    raw_names: list[str],
    my_skill_labels: list[str],
    *,
    persist,
    client=None,
    model: str = MODEL,
    batch_size: int = 80,
) -> tuple[int, int]:
    """Canonicalise in batches, handing each batch to `persist` as it returns.

    A batch that still fails after retries is skipped — batches already
    persisted are never lost, and later batches still run (each Gemini batch
    is paid for once; a mid-run failure must not discard paid work).
    Returns (batches_ok, batches_failed).
    """
    if not raw_names:
        return (0, 0)
    client = client or get_client()
    ok = failed = 0
    for i in range(0, len(raw_names), batch_size):
        names = raw_names[i : i + batch_size]
        try:
            rows = _read_batch(names, my_skill_labels, client, model)
        except Exception:
            failed += 1
            continue
        persist(rows)
        ok += 1
    return (ok, failed)
