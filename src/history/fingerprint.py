"""Content fingerprints and field-level diffs for listings."""
from __future__ import annotations

import hashlib

from normalise.text import norm


def _sha1(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()


def jd_hash(jd_text: str | None) -> str:
    return _sha1(jd_text or "")


def fingerprint(title, location, salary_text, jd_text) -> str:
    """Change detector over the fields that matter. NOT the identity —
    dedupe_key is; this changes whenever the listing's content does."""
    base = f"{norm(title)}|{norm(location)}|{(salary_text or '').strip()}|{jd_hash(jd_text)}"
    return _sha1(base)


def diff_fields(old: dict, new: dict) -> dict:
    """Field-level diff. Short fields carry old/new verbatim; the description
    carries lengths only (full JD bodies don't belong in an event log)."""
    changes: dict = {}
    for f in ("title", "location", "salary_text"):
        if (old.get(f) or None) != (new.get(f) or None):
            changes[f] = {"old": old.get(f), "new": new.get(f)}
    if jd_hash(old.get("jd_text")) != jd_hash(new.get("jd_text")):
        changes["description"] = {
            "old_len": len(old.get("jd_text") or ""),
            "new_len": len(new.get("jd_text") or ""),
        }
    return changes
