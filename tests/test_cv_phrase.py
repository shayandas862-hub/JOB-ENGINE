"""Tests for src/cv/phrase — AI spot #3: Gemini rephrases verified facts only.

No live API calls — the client is mocked. The cage: the instruction forbids
adding anything, and the fallback (no key, or any API failure, or a missing
bullet) is the un-rephrased fact. The truth gate (Task 4) is the enforcement;
here we prove the phrasing wiring, the block↔bullet mapping, and every fallback.
"""
from __future__ import annotations

import json


class FakeResponse:
    def __init__(self, text):
        self.text = text


class FakeClient:
    def __init__(self, text, boom=False):
        self._text, self._boom = text, boom
        self.calls = []

        class _Models:
            def __init__(self, outer):
                self._outer = outer

            def generate_content(self, *, model, contents, config):
                self._outer.calls.append({"model": model, "contents": contents})
                if self._outer._boom:
                    raise RuntimeError("api down")
                return FakeResponse(self._outer._text)

        self.models = _Models(self)


def block(block_id, fact, skills=("sql",), kind="role"):
    from cv.blocks import CvBlock
    return CvBlock(block_id=block_id, kind=kind, title=f"B{block_id}", organisation="Org",
                   date_range="2020-2023", fact_text=fact, skill_norms=list(skills), sort_hint=0)


def _reply(pairs):
    return json.dumps([{"block_id": bid, "bullet": text} for bid, text in pairs])


# ---- happy path -------------------------------------------------------------

def test_phrase_maps_bullets_back_to_their_blocks():
    from cv.phrase import phrase_blocks
    blocks = [block(1, "Led analytics at Acme."), block(2, "Built ETL pipelines.")]
    client = FakeClient(_reply([(1, "Led analytics at Acme, improving reporting."),
                                (2, "Built resilient ETL pipelines.")]))

    out = phrase_blocks(blocks, listing_title="Data Engineer", listing_skills={"sql"},
                        client=client)

    assert [p.block_id for p in out] == [1, 2]
    assert out[0].bullet == "Led analytics at Acme, improving reporting."
    assert out[0].source_fact == "Led analytics at Acme."   # source kept for the truth gate
    assert client.calls and "add nothing" in client.calls[0]["contents"].lower()


# ---- fallbacks (the cage's safety net) -------------------------------------

def test_no_key_and_no_client_falls_back_to_unrephrased_facts():
    from cv.phrase import phrase_blocks
    blocks = [block(1, "Led analytics at Acme.")]
    out = phrase_blocks(blocks)                       # no client, no api_key
    assert out[0].bullet == "Led analytics at Acme." == out[0].source_fact


def test_api_failure_falls_back_to_unrephrased_facts():
    from cv.phrase import phrase_blocks
    blocks = [block(1, "Led analytics."), block(2, "Built ETL.")]
    out = phrase_blocks(blocks, client=FakeClient("", boom=True))
    assert [p.bullet for p in out] == ["Led analytics.", "Built ETL."]


def test_a_block_missing_from_the_reply_falls_back_to_its_fact():
    from cv.phrase import phrase_blocks
    blocks = [block(1, "Fact one."), block(2, "Fact two.")]
    client = FakeClient(_reply([(1, "Rephrased one.")]))    # block 2 omitted by the model
    out = phrase_blocks(blocks, client=client)
    assert out[0].bullet == "Rephrased one."
    assert out[1].bullet == "Fact two."               # untouched fact, not dropped


def test_a_blank_bullet_falls_back_to_the_fact():
    from cv.phrase import phrase_blocks
    blocks = [block(1, "Fact one.")]
    out = phrase_blocks(blocks, client=FakeClient(_reply([(1, "   ")])))
    assert out[0].bullet == "Fact one."


def test_empty_block_list_returns_empty_without_calling_the_model():
    from cv.phrase import phrase_blocks
    client = FakeClient(_reply([]))
    assert phrase_blocks([], client=client) == []
    assert client.calls == []
