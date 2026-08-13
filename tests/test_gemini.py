"""Tests for the Gemini JD reader (GA-003). No live API calls — the client is mocked."""
from __future__ import annotations

import json

import pytest

from read.gemini import JDReading, parse_reading, read_jd, read_jd_or_fallback


class FakeResponse:
    def __init__(self, text):
        self.text = text


class FakeClient:
    """Stand-in for genai.Client — records the call and returns a canned response."""

    def __init__(self, text):
        self._text = text
        self.calls = []

        class _Models:
            def __init__(self, outer):
                self._outer = outer

            def generate_content(self, *, model, contents, config):
                self._outer.calls.append({"model": model, "contents": contents, "config": config})
                return FakeResponse(self._outer._text)

        self.models = _Models(self)


# ---------- parse_reading (pure) ----------

def test_parse_reading_full_payload():
    raw = json.dumps({
        "skills": [
            {"name": "PostgreSQL", "category": "data"},
            {"name": "Python", "category": "programming"},
        ],
        "salary_text": "£70,000 - £90,000",
        "sponsor_hint": "sponsors",
        "soc_hint": "Programmers and software development professionals",
    })
    r = parse_reading(raw)
    assert r.skills == [("PostgreSQL", "data"), ("Python", "programming")]
    assert r.salary_text == "£70,000 - £90,000"
    assert r.sponsor_hint == "sponsors"
    assert r.soc_hint == "Programmers and software development professionals"


def test_parse_reading_normalises_empty_and_unknown_to_none():
    raw = json.dumps({
        "skills": [{"name": "  ", "category": "ml"}, {"name": "RAG", "category": "ml"}],
        "salary_text": "   ",
        "sponsor_hint": "unknown",
        "soc_hint": None,
    })
    r = parse_reading(raw)
    assert r.skills == [("RAG", "ml")]      # blank-named skill dropped
    assert r.salary_text is None            # whitespace-only -> None
    assert r.sponsor_hint is None           # "unknown" -> None
    assert r.soc_hint is None


def test_parse_reading_empty_input_returns_empty():
    assert parse_reading(None) == JDReading()
    assert parse_reading("") == JDReading()


def test_parse_reading_drops_literal_junk_words():
    raw = json.dumps({
        "skills": [], "salary_text": "null", "sponsor_hint": "null", "soc_hint": "N/A",
    })
    r = parse_reading(raw)
    assert r.salary_text is None and r.sponsor_hint is None and r.soc_hint is None


# ---------- read_jd (mocked client) ----------

def test_read_jd_calls_client_and_parses():
    payload = json.dumps({
        "skills": [{"name": "AWS", "category": "cloud"}],
        "salary_text": None, "sponsor_hint": "no_sponsor", "soc_hint": None,
    })
    client = FakeClient(payload)
    r = read_jd("We need an AWS engineer. You must have the right to work in the UK.",
                client=client, model="test-model")
    assert r.skills == [("AWS", "cloud")]
    assert r.sponsor_hint == "no_sponsor"
    assert len(client.calls) == 1
    assert client.calls[0]["model"] == "test-model"
    assert "right to work" in client.calls[0]["contents"]


def test_read_jd_empty_text_skips_client():
    client = FakeClient("{}")
    r = read_jd("   ", client=client)
    assert r == JDReading()
    assert client.calls == []               # no API call for empty text


# ---------- read_jd_or_fallback (selection) ----------

def test_fallback_uses_keyword_extractor_when_no_key():
    # No key -> deterministic keyword extractor; no client needed.
    r = read_jd_or_fallback("We use Python and Kubernetes here.", api_key="")
    names = {n for n, _ in r.skills}
    assert "Python" in names and "Kubernetes" in names
    assert r.salary_text is None and r.sponsor_hint is None


def test_fallback_also_extracts_salary_text():
    # The reader is the single source of salary_text — even on the keyword path.
    r = read_jd_or_fallback("Python role. Salary £80,000.", api_key="")
    assert r.salary_text == "£80,000"


def test_fallback_uses_gemini_when_key_present():
    payload = json.dumps({
        "skills": [{"name": "LLMs", "category": "ml"}],
        "salary_text": "£100k", "sponsor_hint": "sponsors", "soc_hint": None,
    })
    client = FakeClient(payload)
    r = read_jd_or_fallback("Work on LLMs.", api_key="AIzaSyFAKE", client=client)
    assert r.skills == [("LLMs", "ml")]
    assert r.salary_text == "£100k"
    assert len(client.calls) == 1


# ---------- retry on transient API errors ----------

class FlakyClient:
    """Raises `error` for the first `fail_times` calls, then answers normally."""

    def __init__(self, text, fail_times, error):
        self._text = text
        self.calls = 0

        class _Models:
            def __init__(self, outer):
                self._outer = outer

            def generate_content(self, *, model, contents, config):
                self._outer.calls += 1
                if self._outer.calls <= fail_times:
                    raise error
                return FakeResponse(self._outer._text)

        self.models = _Models(self)


EMPTY_PAYLOAD = json.dumps(
    {"skills": [], "salary_text": None, "sponsor_hint": None, "soc_hint": None})


def test_read_jd_retries_transient_errors(monkeypatch):
    from read import gemini
    sleeps = []
    monkeypatch.setattr(gemini, "_sleep", lambda s: sleeps.append(s))
    client = FlakyClient(EMPTY_PAYLOAD, fail_times=2,
                         error=Exception("503 UNAVAILABLE: model overloaded"))
    r = read_jd("Some JD text.", client=client)
    assert r == JDReading()
    assert client.calls == 3            # two failures + one success
    assert sleeps == [1, 2]             # exponential backoff between tries


def test_read_jd_does_not_retry_non_transient_errors(monkeypatch):
    from read import gemini
    monkeypatch.setattr(gemini, "_sleep", lambda s: None)
    client = FlakyClient(EMPTY_PAYLOAD, fail_times=9,
                         error=ValueError("400 INVALID_ARGUMENT: bad request"))
    with pytest.raises(ValueError):
        read_jd("Some JD text.", client=client)
    assert client.calls == 1            # no retry on a non-transient error


def test_read_jd_raises_after_exhausting_retries(monkeypatch):
    from read import gemini
    monkeypatch.setattr(gemini, "_sleep", lambda s: None)
    client = FlakyClient(EMPTY_PAYLOAD, fail_times=9,
                         error=Exception("429 RESOURCE_EXHAUSTED: quota"))
    with pytest.raises(Exception, match="429"):
        read_jd("Some JD text.", client=client)
    assert client.calls == gemini.GEMINI_TRIES
