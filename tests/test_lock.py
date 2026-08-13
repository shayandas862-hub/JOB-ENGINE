"""The run lock: two pipeline runs must never overlap."""
from __future__ import annotations


def test_second_acquire_fails_while_first_holds(tmp_path):
    from pipeline.lock import acquire_lock
    path = tmp_path / "run.lock"
    first = acquire_lock(path)
    assert first is not None
    assert acquire_lock(path) is None          # held -> refused
    first.close()                              # released -> available again
    again = acquire_lock(path)
    assert again is not None
    again.close()
