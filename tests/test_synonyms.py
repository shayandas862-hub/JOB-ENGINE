"""Tests for the skill synonym canonicaliser (normalise.synonyms). Client is mocked."""
from __future__ import annotations

import json

from normalise.synonyms import SynonymRow, canonicalize, norm, parse_mappings


class FakeResponse:
    def __init__(self, text):
        self.text = text


class FakeClient:
    def __init__(self, text):
        self._text = text
        self.calls = []

        class _Models:
            def __init__(self, outer):
                self._outer = outer

            def generate_content(self, *, model, contents, config):
                self._outer.calls.append({"model": model, "contents": contents})
                return FakeResponse(self._outer._text)

        self.models = _Models(self)


MY_SKILLS = ["Generative AI", "AI agent & pipeline design", "Python"]


def test_norm_lowercases_and_collapses_space():
    assert norm("  Power   BI ") == "power bi"


def test_parse_mappings_builds_rows_and_norms_canonical():
    raw = json.dumps({"mappings": [
        {"raw": "gen ai", "canonical": "Generative AI", "my_skill_match": True, "confidence": "high"},
        {"raw": "ai agents", "canonical": "AI agent & pipeline design", "my_skill_match": True, "confidence": "low"},
        {"raw": "postgres", "canonical": "PostgreSQL", "my_skill_match": False, "confidence": "high"},
    ]})
    rows = parse_mappings(raw, MY_SKILLS)
    by_raw = {r.raw_norm: r for r in rows}
    assert by_raw["gen ai"].canonical_norm == "generative ai"     # matches my_skills norm
    assert by_raw["gen ai"].my_skill_match is True
    assert by_raw["ai agents"].canonical_norm == "ai agent & pipeline design"
    assert by_raw["ai agents"].confidence == "low"                # flagged for review
    assert by_raw["postgres"].canonical_label == "PostgreSQL"
    assert by_raw["postgres"].my_skill_match is False


def test_parse_mappings_forces_low_confidence_when_claimed_match_not_in_my_skills():
    # Model says my_skill_match but the canonical isn't actually one of my skills -> distrust.
    raw = json.dumps({"mappings": [
        {"raw": "ml ops", "canonical": "Made Up Skill", "my_skill_match": True, "confidence": "high"},
    ]})
    rows = parse_mappings(raw, MY_SKILLS)
    assert rows[0].my_skill_match is False
    assert rows[0].confidence == "low"


def test_canonicalize_calls_client_per_batch():
    payload = json.dumps({"mappings": [
        {"raw": "gen ai", "canonical": "Generative AI", "my_skill_match": True, "confidence": "high"},
    ]})
    client = FakeClient(payload)
    rows = canonicalize(["gen ai"], MY_SKILLS, client=client, model="m", batch_size=50)
    assert len(client.calls) == 1
    assert rows[0].canonical_norm == "generative ai"


def test_canonicalize_batches_split_calls():
    payload = json.dumps({"mappings": []})
    client = FakeClient(payload)
    canonicalize(["a", "b", "c", "d", "e"], MY_SKILLS, client=client, model="m", batch_size=2)
    assert len(client.calls) == 3  # 2 + 2 + 1


def test_canonicalize_survives_transient_api_error(monkeypatch):
    # Retries come from the shared helper in read.gemini.
    from read import gemini
    monkeypatch.setattr(gemini, "_sleep", lambda s: None)
    payload = json.dumps({"mappings": [
        {"raw": "postgres", "canonical": "PostgreSQL",
         "my_skill_match": False, "confidence": "high"},
    ]})

    class Flaky:
        def __init__(self):
            self.calls = 0
            outer = self

            class _M:
                def generate_content(self, *, model, contents, config):
                    outer.calls += 1
                    if outer.calls == 1:
                        raise Exception("503 UNAVAILABLE: try again")
                    return FakeResponse(payload)

            self.models = _M()

    flaky = Flaky()
    rows = canonicalize(["postgres"], MY_SKILLS, client=flaky)
    assert [r.canonical_label for r in rows] == ["PostgreSQL"]
    assert flaky.calls == 2


# ---- per-batch persistence (a failed batch must not discard paid batches) ----

def _payload_for(name):
    return json.dumps({"mappings": [
        {"raw": name, "canonical": name.title(),
         "my_skill_match": False, "confidence": "high"},
    ]})


class PerBatchFlaky:
    """Answers per call from a script of payloads; 'BOOM' raises a hard error."""

    def __init__(self, script):
        self.script = list(script)
        outer = self

        class _M:
            def generate_content(self, *, model, contents, config):
                step = outer.script.pop(0)
                if step == "BOOM":
                    raise ValueError("400 INVALID_ARGUMENT: malformed")
                return FakeResponse(step)

        self.models = _M()


def test_canonicalize_batches_persists_each_batch_and_survives_one_failure():
    from normalise.synonyms import canonicalize_batches
    persisted = []
    client = PerBatchFlaky([_payload_for("aws"), "BOOM", _payload_for("gcp")])
    ok, failed = canonicalize_batches(
        ["aws", "azure", "gcp"], MY_SKILLS,
        client=client, batch_size=1, persist=persisted.append)
    assert ok == 2 and failed == 1
    # batches 1 and 3 survived batch 2's failure and were persisted in order
    assert [[r.raw_norm for r in batch] for batch in persisted] == [["aws"], ["gcp"]]


def test_canonicalize_batches_empty_input_is_a_noop():
    from normalise.synonyms import canonicalize_batches
    persisted = []
    ok, failed = canonicalize_batches([], MY_SKILLS, client=None, persist=persisted.append)
    assert (ok, failed) == (0, 0) and persisted == []


def test_no_key_skips_cleanly_and_never_touches_the_db(monkeypatch, capsys):
    # Engine-side AI is retired (2026-08-03): with no key the stage must exit 0
    # and do nothing — synonym mapping is user-side now (plan 0010 item 17);
    # existing mappings persist. A hard exit here failed the first cloud run.
    import importlib.util
    from pathlib import Path

    from config import Settings

    spec = importlib.util.spec_from_file_location(
        "build_synonyms_script",
        Path(__file__).resolve().parents[1] / "scripts" / "build_synonyms.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    monkeypatch.setattr(mod, "get_settings",
                        lambda **kw: Settings(database_url="x", gemini_api_key=""))

    def boom():
        raise AssertionError("get_conn must not be called when skipping")
    monkeypatch.setattr(mod, "get_conn", boom)

    mod.main()          # returns, no SystemExit — the run must carry on

    err = capsys.readouterr().err
    assert "skip" in err.lower()
    assert "user-side" in err.lower()
