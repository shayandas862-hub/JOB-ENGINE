import pytest
import responses

from fetch.ats import (
    ATS_GREENHOUSE,
    ATS_LEVER,
    ATS_UNKNOWN,
    candidate_tokens,
    classify_company,
)


@pytest.fixture(autouse=True)
def _no_backoff(monkeypatch):
    # Retries (added Phase 1 T5) really sleep; tests must never wait them out.
    from fetch import ats
    monkeypatch.setattr(ats, "_sleep", lambda s: None)


def test_candidate_tokens_multiword():
    toks = candidate_tokens("Thought Machine")
    assert "thoughtmachine" in toks
    assert "thought-machine" in toks


def test_candidate_tokens_strips_ai_suffix():
    toks = candidate_tokens("Stability AI")
    assert "stabilityai" in toks
    assert "stability" in toks


def test_candidate_tokens_strips_legal_suffixes():
    # Register names legally end Ltd/Limited/PLC; board slugs use the bare
    # brand — the census (Phase 7.5) probes register names, so the stripped
    # variant must be tried. Original guesses keep first position.
    toks = candidate_tokens("Synthesia Limited")
    assert toks[0] == "synthesialimited"
    assert "synthesia" in toks


def test_candidate_tokens_register_style_names():
    assert "revolut" in candidate_tokens("Revolut Ltd")
    toks = candidate_tokens("Wayve Technologies Ltd")
    assert "wayvetechnologies" in toks and "wayve-technologies" in toks


def test_candidate_tokens_without_suffix_are_unchanged():
    assert candidate_tokens("Thought Machine") == ["thoughtmachine", "thought-machine"]


@responses.activate
def test_classify_greenhouse_hit():
    responses.add(
        responses.GET,
        "https://boards-api.greenhouse.io/v1/boards/anthropic/jobs",
        json={"jobs": [{"id": 1}, {"id": 2}]},
        status=200,
    )
    c = classify_company("Anthropic")
    assert c.ats_type == ATS_GREENHOUSE
    assert c.ats_token == "anthropic"
    assert c.n_jobs == 2
    assert c.careers_url == "https://boards.greenhouse.io/anthropic"


@responses.activate
def test_classify_falls_through_to_lever():
    responses.add(
        responses.GET,
        "https://boards-api.greenhouse.io/v1/boards/palantir/jobs",
        status=404,
    )
    responses.add(
        responses.GET,
        "https://api.lever.co/v0/postings/palantir?mode=json",
        json=[{"id": "a"}, {"id": "b"}, {"id": "c"}],
        status=200,
    )
    c = classify_company("Palantir")
    assert c.ats_type == ATS_LEVER
    assert c.n_jobs == 3


@responses.activate
def test_classify_unknown_when_nothing_matches():
    # No mocks registered -> every probe gets a connection error -> unknown.
    c = classify_company("Some Custom Co")
    assert c.ats_type == ATS_UNKNOWN
    assert c.careers_url is None
    assert c.ats_token is None


@responses.activate
def test_zero_job_hit_is_rejected():
    # An empty board (0 jobs) is a non-hit: likely a collision or parked account.
    responses.add(
        responses.GET,
        "https://boards-api.greenhouse.io/v1/boards/wise/jobs",
        json={"jobs": []},
        status=200,
    )
    responses.add(
        responses.POST,
        "https://apply.workable.com/api/v3/accounts/wise/jobs",
        json={"results": []},
        status=200,
    )
    c = classify_company("Wise")
    assert c.ats_type == ATS_UNKNOWN


@responses.activate
def test_probe_retries_transient_429_then_succeeds(monkeypatch):
    from fetch import ats
    sleeps = []
    monkeypatch.setattr(ats, "_sleep", lambda s: sleeps.append(s))
    url = "https://boards-api.greenhouse.io/v1/boards/anthropic/jobs"
    responses.add(responses.GET, url, json={}, status=429)
    responses.add(responses.GET, url, json={"jobs": [{"id": 1}]}, status=200)
    import requests
    result = ats.probe_greenhouse("anthropic", requests.Session())
    assert result is not None and result.n_jobs == 1
    assert len(responses.calls) == 2 and sleeps == [1]
