"""The owner's industry lens: plain words → ranked SIC-code candidates (U2).

Deterministic translation, no AI: tokenise the owner's words, search
sic_codes descriptions, rank by tokens matched then by how many census
sponsors carry the code. Choosing from the candidates is the client AI's
job (with the owner), and writing the choice stays with the existing
promotion-rule writer — this module never writes.
"""
from __future__ import annotations

from normalise.text import norm

# Glue words only — a token this common says nothing about an industry.
_STOPWORDS = frozenset({
    "a", "an", "and", "for", "in", "of", "or", "the", "to", "with",
})


def _stem(token: str) -> str:
    """A shared-prefix stem, not a dictionary: 'homes'→'home' matches both
    forms as a substring; 'activities'→'activit' matches activity AND
    activities. Never applied to short or -ss words."""
    if len(token) > 4 and token.endswith("ies"):
        return token[:-3]
    if len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def _tokens(words: str) -> list[str]:
    seen: list[str] = []
    for tok in norm(words).split():
        if tok not in _STOPWORDS and tok not in seen:
            seen.append(tok)
    return seen


def word_patterns(words: str) -> list[str]:
    """ILIKE patterns for each meaningful word, prefix-stemmed — the shared
    tokenisation every universal-layer word search uses (U2/U3). Empty when
    the words carry no usable token."""
    return [f"%{_stem(t)}%" for t in _tokens(words or "")]


def find_industry_codes(cur, words: str, limit: int = 12) -> list[dict]:
    """Rank SIC codes for the owner's words: tokens matched desc, census
    sponsor count desc, code. Every row carries its receipts — the matched
    tokens and the sponsor count — so the picker sees why it is offered."""
    tokens = _tokens(words)
    if not tokens:
        return []
    stems = {t: _stem(t) for t in tokens}

    cur.execute(
        "select code, description from sic_codes "
        "where description ilike any (%(pats)s)",
        {"pats": [f"%{s}%" for s in stems.values()]})
    rows = cur.fetchall()
    if not rows:
        return []

    sponsors = _sponsor_counts(cur, [r["code"] for r in rows])
    ranked = []
    for r in rows:
        desc = norm(r["description"])
        matched = [t for t, s in stems.items() if s in desc]
        ranked.append({"code": r["code"], "description": r["description"],
                       "sponsors": sponsors.get(r["code"], 0),
                       "matched": matched})
    ranked.sort(key=lambda r: (-len(r["matched"]), -r["sponsors"], r["code"]))
    return ranked[:limit]


def _sponsor_counts(cur, codes: list[str]) -> dict[str, int]:
    """How many census sponsors carry each candidate code."""
    cur.execute(
        "select u.code, count(*) as sponsors "
        "from sponsor_census sc, unnest(sc.industry_codes) as u(code) "
        "where u.code = any (%(codes)s) group by u.code",
        {"codes": codes})
    return {r["code"]: r["sponsors"] for r in cur.fetchall()}
