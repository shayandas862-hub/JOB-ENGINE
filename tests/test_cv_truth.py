"""Tests for src/cv/truth — the truth gate. Every shipped bullet must trace to its
source fact, or it falls back to the verbatim fact. Built on the read.eval
grounding approach (verbatim containment). Invented numbers or wholesale invention
fail; benign rephrasing survives.
"""
from __future__ import annotations


def phrased(bullet, source_fact, block_id=1):
    from cv.phrase import PhrasedBlock
    return PhrasedBlock(block_id=block_id, kind="role", title="B", organisation="Acme",
                        date_range="2020-2023", source_fact=source_fact, bullet=bullet)


SRC = "Led analytics at Acme, cutting reporting time 40%."


# ---- trace_bullet -----------------------------------------------------------

def test_verbatim_fact_traces_to_itself():
    from cv.truth import trace_bullet
    assert trace_bullet(SRC, SRC) is True


def test_light_rephrase_that_keeps_the_facts_traces():
    from cv.truth import trace_bullet
    assert trace_bullet("Cut Acme reporting time 40% by leading analytics.", SRC)


def test_invented_number_fails_the_gate():
    from cv.truth import trace_bullet
    assert trace_bullet("Cut Acme reporting time 60% by leading analytics.", SRC) is False


def test_invented_entities_fail_the_gate():
    from cv.truth import trace_bullet
    # 'Google' and 'TensorFlow' appear nowhere in the source fact
    assert trace_bullet("Led analytics at Google using TensorFlow and Kubernetes.", SRC) is False


def test_empty_bullet_never_traces():
    from cv.truth import trace_bullet
    assert trace_bullet("", SRC) is False
    assert trace_bullet("   ", SRC) is False


def test_salary_number_formatting_is_tolerated():
    from cv.truth import trace_bullet
    src = "Managed a budget of £70,000 across the team."
    assert trace_bullet("Managed a £70,000 team budget.", src)


# ---- gate_phrased (per-bullet fallback) ------------------------------------

def test_gate_keeps_traceable_bullets_and_falls_back_untraceable_ones():
    from cv.truth import gate_phrased
    good = phrased("Cut Acme reporting time 40% by leading analytics.", SRC, block_id=1)
    bad = phrased("Grew revenue 300% at Meta.", "Supported the analytics team at Acme.", block_id=2)

    gated = gate_phrased([good, bad])

    assert gated[0].bullet == good.bullet                 # traceable -> kept as phrased
    assert gated[1].bullet == bad.source_fact            # untraceable -> verbatim fact
    assert gated[1].bullet != bad.bullet


def test_gate_never_changes_the_source_fact():
    from cv.truth import gate_phrased
    bad = phrased("Invented lie with numbers 999.", "True fact about work.", block_id=3)
    (g,) = gate_phrased([bad])
    assert g.source_fact == "True fact about work."      # provenance is preserved
    assert g.bullet == "True fact about work."
