"""SOC occupation resolution — deterministic name→code matching, never a guess.

The AI reader's soc_hint is an occupation NAME ("closest UK SOC occupation
name"). This module resolves names to official SOC 2020 codes using only the
reference data in skilled_worker_occupations (job_type + the official
related_job_titles list). A hint that matches nothing — or matches more than
one code — resolves to None and is left for human/Claude review.
"""
from __future__ import annotations

from normalise.text import norm

_AMBIGUOUS = object()   # sentinel: two codes claimed the same name


def _name_key(name: str | None) -> str:
    return norm(name).rstrip(".") if name else ""


def build_occupation_index(rows) -> dict[str, str]:
    """Index of name-key -> occupation_code from reference rows.

    Rows need occupation_code, job_type, related_job_titles (newline-separated).
    A name claimed by two different codes is dropped entirely (never guess).
    Codes index to themselves so a bare "2134" hint passes through.
    """
    index: dict[str, object] = {}
    for r in rows:
        code = (r["occupation_code"] or "").strip()
        if not code:
            continue
        names = [code, r.get("job_type") or ""]
        names += (r.get("related_job_titles") or "").splitlines()
        for name in names:
            key = _name_key(name)
            if not key:
                continue
            if key in index and index[key] != code:
                index[key] = _AMBIGUOUS
            else:
                index[key] = code
    return {k: v for k, v in index.items() if v is not _AMBIGUOUS}


def load_occupation_index(cur) -> dict[str, str]:
    cur.execute(
        "select occupation_code, job_type, related_job_titles "
        "from skilled_worker_occupations")
    return build_occupation_index(cur.fetchall())


def make_resolver(index: dict[str, str]):
    """Callable(hint) -> occupation_code | None."""
    return lambda hint: index.get(_name_key(hint)) or None
