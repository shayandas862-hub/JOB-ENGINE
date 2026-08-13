"""The bug log's shape — docs/bug-log.md (founder's standing instruction,
2026-08-10).

The log's whole value is the field the other logs do not carry: **can this
bug come back, and where**. A "fixed" entry with no recurrence answer is the
one shape that would quietly turn this back into a changelog, so the format
is checked rather than trusted.

Repo-only: the container ships src/, scripts/, tests/ and db/, but the docs
tree is not something the image needs. Skips there, never fails.
"""
from __future__ import annotations

import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
BUG_LOG = ROOT / "docs" / "bug-log.md"

pytestmark = pytest.mark.skipif(
    not BUG_LOG.exists() and not (ROOT / "docs").is_dir(),
    reason="repo-only contract: the docs tree is not in the container image")

ENTRY_RE = re.compile(r"^### (B-GAE-(\d{3})) · (.+)$", re.M)
REQUIRED = ("**Phase:**", "**Found by:**", "**Cause:**", "**Guard:**",
            "**Could it return?**")


def _entries() -> list[tuple[str, int, str, str]]:
    """(id, number, headline, body) for every entry, in file order."""
    text = BUG_LOG.read_text()
    found = list(ENTRY_RE.finditer(text))
    out = []
    for i, m in enumerate(found):
        end = found[i + 1].start() if i + 1 < len(found) else len(text)
        out.append((m.group(1), int(m.group(2)), m.group(3),
                    text[m.end():end]))
    return out


def test_the_bug_log_exists_and_holds_entries():
    assert BUG_LOG.exists(), "docs/bug-log.md is a standing record — do not delete it"
    assert _entries(), "the bug log has no entries at all — the parser or the file is broken"


def test_every_entry_answers_whether_the_bug_can_come_back():
    # The field this log exists for. An entry that says how it was fixed but
    # not whether it will happen again is a changelog line, not a bug record.
    missing = []
    for bug_id, _, _, body in _entries():
        for label in REQUIRED:
            if label not in body:
                missing.append(f"{bug_id} missing {label}")
    assert missing == [], f"incomplete bug entries: {missing}"


def test_a_recurrence_answer_is_one_of_the_three_levels():
    # LOW/MEDIUM/HIGH, so the log can be read at a glance and counted. Prose
    # alone ("probably not") is not an answer anyone can act on.
    bad = []
    for bug_id, _, _, body in _entries():
        line = next((ln for ln in body.splitlines()
                     if "**Could it return?**" in ln), "")
        if not re.search(r"\b(LOW|MEDIUM|HIGH)\b", line):
            bad.append(bug_id)
    assert bad == [], f"no severity on the recurrence answer: {bad}"


def test_ids_are_unique_and_never_recycled():
    # Numbers are allocated on first sight and burned on removal — the same
    # rule as every other record in this project. A duplicate means two bugs
    # are claiming one identity, and every citation to it is now ambiguous.
    numbers = [n for _, n, _, _ in _entries()]
    duplicates = {n for n in numbers if numbers.count(n) > 1}
    assert not duplicates, f"duplicate bug ids: {sorted(duplicates)}"


def test_the_registry_covers_every_id_in_the_log():
    # docs/id-registry.json holds the high-water mark. If the log cites a
    # number above it, the next allocation will collide.
    import json
    registry = json.loads((ROOT / "docs" / "id-registry.json").read_text())
    allocated = registry.get("allocated", {}).get("bug")
    assert allocated is not None, "no 'bug' kind in docs/id-registry.json"
    highest = max((n for _, n, _, _ in _entries()), default=0)
    assert allocated >= highest, (
        f"registry allocated.bug is {allocated} but the log cites "
        f"B-GAE-{highest:03d} — bump the registry")


def test_the_log_is_tracked_so_it_ships_and_stays_scanned():
    # Two things ride on this file being tracked. It ships in the public
    # snapshot (the scrub removes CLAUDE.md, PROJECT-MEMORY.md and
    # docs/handoffs — not this file), and being tracked is also what puts it
    # inside test_public_safety's scans for the project ref, api-key shapes,
    # connection-string passwords and the ntfy topic. Untracking it would
    # silently cost both at once.
    #
    # Those scans are deliberately NOT repeated here. The first version of
    # this test re-implemented them with the project ref hardcoded as the
    # needle — so the duplicate check became the leak it was checking for the
    # moment the file was committed (B-GAE-009). Generalise, don't duplicate.
    import subprocess
    tracked = subprocess.run(["git", "ls-files", "docs/bug-log.md"],
                             cwd=ROOT, capture_output=True, text=True).stdout
    assert tracked.strip() == "docs/bug-log.md", \
        "docs/bug-log.md is untracked — it would stop shipping AND stop being scanned"
