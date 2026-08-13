"""Gemini Flash-Lite JD reader (GA-003) — AI extraction with a keyword fallback.

Reads one job description and returns only what is *explicitly present*: skills,
salary text, a sponsorship hint and a SOC occupation hint. A strict JSON schema
plus an "extract, never infer" instruction keep the output disciplined. When no
API key is configured the keyword extractor in `read.extract` is used instead,
so the pipeline runs end-to-end with or without Gemini.

All output is provisional until the founder confirms it. Tests mock the client;
no live calls are made in the test suite.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field

from google import genai
from google.genai import types

from config import get_settings

# Gemini Flash-Lite — cheap, high-recall reader. Change here if the id moves.
# (gemini-2.0-flash-lite was retired by Google; 2.5-flash-lite is the current pin.)
MODEL = "gemini-2.5-flash-lite"

SKILL_CATEGORIES = ["programming", "data", "cloud", "ml", "bi", "solutions", "other"]
SPONSOR_VALUES = ["sponsors", "no_sponsor", "unknown"]


@dataclass(frozen=True)
class JDReading:
    """One job description, read once. `skills` is [(name, category)]."""

    skills: list[tuple[str, str]] = field(default_factory=list)
    salary_text: str | None = None
    sponsor_hint: str | None = None  # 'sponsors' | 'no_sponsor' | None
    soc_hint: str | None = None      # closest UK SOC occupation name, or None


_RESPONSE_SCHEMA = types.Schema(
    type=types.Type.OBJECT,
    required=["skills", "salary_text", "sponsor_hint", "soc_hint"],
    properties={
        "skills": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(
                type=types.Type.OBJECT,
                required=["name", "category"],
                properties={
                    "name": types.Schema(type=types.Type.STRING),
                    "category": types.Schema(type=types.Type.STRING, enum=SKILL_CATEGORIES),
                },
            ),
        ),
        "salary_text": types.Schema(type=types.Type.STRING, nullable=True),
        "sponsor_hint": types.Schema(type=types.Type.STRING, enum=SPONSOR_VALUES, nullable=True),
        "soc_hint": types.Schema(type=types.Type.STRING, nullable=True),
    },
)

_INSTRUCTION = (
    "You are reading ONE UK job description. Extract ONLY what is explicitly "
    "stated; never infer, guess, or pad. Return JSON that matches the schema.\n"
    f"- skills: concrete technical/professional skills named in the text, each tagged with a "
    f"category from {SKILL_CATEGORIES}. Use each skill's common, canonical name "
    "(e.g. 'PostgreSQL' not 'postgres', 'Generative AI' not 'gen ai').\n"
    "- salary_text: the pay/compensation exactly as written (e.g. '£70,000 - £90,000'), "
    "or null if no salary is stated.\n"
    "- sponsor_hint: 'sponsors' if it offers UK visa sponsorship; 'no_sponsor' if it says you "
    "must already hold the right to work / no sponsorship is offered; otherwise 'unknown'.\n"
    "- soc_hint: the closest UK SOC occupation name if it is obvious from the role, else null.\n"
)


def get_client(api_key: str | None = None) -> genai.Client:
    """Build a Gemini client. Falls back to the configured GEMINI_API_KEY."""
    key = api_key or get_settings(require_gemini=True).gemini_api_key
    # http_options.timeout is milliseconds — without it a hung call blocks forever.
    return genai.Client(api_key=key, http_options=types.HttpOptions(timeout=60_000))


# ---- retry on transient API errors (shared by both AI spots) ----

GEMINI_TRIES = 3
_sleep = time.sleep  # module-level so tests can stub the backoff

# Markers of transient failures in google-genai error messages/codes.
_TRANSIENT_CODES = {429, 500, 502, 503, 504}
_TRANSIENT_MARKERS = ("429", "500", "502", "503", "504", "RESOURCE_EXHAUSTED",
                      "UNAVAILABLE", "DEADLINE_EXCEEDED", "overloaded")


def _is_transient(err: Exception) -> bool:
    code = getattr(err, "code", None) or getattr(err, "status_code", None)
    if isinstance(code, int):
        return code in _TRANSIENT_CODES
    msg = str(err)
    return any(m in msg for m in _TRANSIENT_MARKERS)


def generate_with_retry(client, *, model, contents, config):
    """client.models.generate_content with exponential backoff on transient errors."""
    for attempt in range(GEMINI_TRIES):
        try:
            return client.models.generate_content(
                model=model, contents=contents, config=config)
        except Exception as err:
            if attempt == GEMINI_TRIES - 1 or not _is_transient(err):
                raise
            _sleep(2 ** attempt)


def read_jd(text: str | None, *, client: genai.Client | None = None, model: str = MODEL) -> JDReading:
    """Read one JD via Gemini and return a JDReading. Empty text skips the API."""
    if not text or not text.strip():
        return JDReading()
    client = client or get_client()
    resp = generate_with_retry(
        client,
        model=model,
        contents=_INSTRUCTION + "\n\nJOB DESCRIPTION:\n" + text,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=_RESPONSE_SCHEMA,
            temperature=0,
        ),
    )
    return parse_reading(resp.text)


def read_jd_or_fallback(
    text: str | None,
    *,
    api_key: str | None,
    client: genai.Client | None = None,
    model: str = MODEL,
) -> JDReading:
    """Gemini when a key is present, else the keyword extractor (skills only)."""
    if api_key:
        return read_jd(text, client=client, model=model)
    from analysis.salary import salary_text_from
    from read.extract import extract_skills

    return JDReading(skills=extract_skills(text), salary_text=salary_text_from(text))


# Models sometimes emit the literal word for "absent" instead of JSON null.
_JUNK = {"", "null", "none", "n/a", "na", "unknown", "n.a."}


def _clean(v) -> str | None:
    """Return a trimmed string, or None for blanks and literal junk words."""
    if not isinstance(v, str):
        return None
    s = v.strip()
    return None if s.lower() in _JUNK else s


def parse_reading(raw: str | None) -> JDReading:
    """Parse the model's JSON string into a JDReading, normalising blanks to None."""
    if not raw:
        return JDReading()
    data = json.loads(raw)

    skills: list[tuple[str, str]] = []
    for s in data.get("skills") or []:
        name = (s.get("name") or "").strip()
        category = (s.get("category") or "other").strip() or "other"
        if name:
            skills.append((name, category))

    # sponsor_hint must be one of the two real values; anything else -> None.
    sponsor = data.get("sponsor_hint")
    sponsor = sponsor if sponsor in ("sponsors", "no_sponsor") else None

    return JDReading(
        skills=skills,
        salary_text=_clean(data.get("salary_text")),
        sponsor_hint=sponsor,
        soc_hint=_clean(data.get("soc_hint")),
    )
