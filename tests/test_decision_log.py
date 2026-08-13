"""The decision log's shape — B-GAE-038.

`docs/bug-log.md` has had a shape test since the day it was created. The
decision log, which is older, larger and equally public, has had none — and it
cost exactly what an unchecked shape costs: writing the Task 5 entry above the
Task 4 entry **deleted Task 4's heading**, so seven of that task's decisions sat
under Task 5's title for a day and a half, in the file whose whole job is to say
why a thing was done and when.

The check that would have caught it is narrow on purpose. Entries written from
Phase 9 onward open with a `Built HH:MM–HH:MM` line, so a section containing
TWO such openers is a section that has swallowed another entry. It protects only
the entries that carry that opener — three today — and that limit is stated
rather than glossed: the older sections have no machine-recognisable opener and
this test cannot see them. Coverage grows as entries adopt the convention.

Repo-only: the docs tree is not in the container image.
"""
from __future__ import annotations

import json
import pathlib
import re
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
LOG = ROOT / "docs" / "decision-log.md"
REGISTRY = ROOT / "docs" / "id-registry.json"

pytestmark = pytest.mark.skipif(
    not LOG.exists(), reason="repo-only contract: docs/ is not in the image")

SECTION_RE = re.compile(r"^## (.+)$", re.M)
OPENER_RE = re.compile(r"^Built \d{1,2}:\d{2}", re.M)
ID_RE = re.compile(r"\bD-GAE-(\d{3})\b")


def _sections() -> list[tuple[str, str]]:
    """(heading, body) for every `## ` section, in file order."""
    text = LOG.read_text()
    found = list(SECTION_RE.finditer(text))
    out = []
    for i, match in enumerate(found):
        end = found[i + 1].start() if i + 1 < len(found) else len(text)
        out.append((match.group(1), text[match.end():end]))
    return out


def _swallowed(sections) -> list[str]:
    return [head for head, body in sections if len(OPENER_RE.findall(body)) > 1]


def test_no_section_has_swallowed_another_entrys_heading():
    # The B-GAE-038 guard. Two openers under one heading means an entry lost its
    # title — which reads, to anyone auditing later, as one task having made
    # another task's decisions.
    swallowed = _swallowed(_sections())
    assert swallowed == [], (
        "these sections contain more than one entry opener, so a `## ` heading "
        f"was destroyed beneath them: {swallowed}")


def test_the_opener_scan_can_actually_see_the_entries_it_guards():
    # The control. With no opener in the file the assertion above passes for
    # every possible log, which is this project's most-repeated defect shape
    # (B-GAE-004). Three entries carried the opener when this was written.
    total = len(OPENER_RE.findall(LOG.read_text()))
    assert total >= 3, (
        f"the scan found {total} entry openers; it found 3 when written, so the "
        "convention has been dropped or the pattern has broken — either way "
        "this file is no longer guarding anything")


def test_every_decision_id_is_cited_once_and_fits_the_registry():
    # Same rule as every other record here: ids are allocated on first sight,
    # never recycled, and the registry holds the high-water mark. A duplicate
    # means two decisions claim one identity and every citation is ambiguous.
    numbers = [int(n) for n in ID_RE.findall(LOG.read_text())]
    headings = [int(n) for n in
                ID_RE.findall("\n".join(h for h, _ in _sections()))]
    cited = [n for n in numbers if n not in headings]
    duplicates = sorted({n for n in cited if cited.count(n) > 1})
    assert duplicates == [], f"duplicate decision ids: {duplicates}"

    allocated = json.loads(REGISTRY.read_text())["allocated"]["decision"]
    highest = max(numbers, default=0)
    assert allocated >= highest, (
        f"registry allocated.decision is {allocated} but the log cites "
        f"D-GAE-{highest:03d} — bump the registry")


def test_the_decision_log_is_tracked_so_it_ships_and_stays_scanned():
    # It is one of the three logs the public snapshot deliberately carries, and
    # being tracked is also what puts it inside test_public_safety's scans for
    # the project ref, key shapes and connection-string passwords.
    if not (ROOT / ".git").exists():
        pytest.skip("no git index here")
    tracked = subprocess.run(["git", "ls-files", "docs/decision-log.md"],
                             cwd=ROOT, capture_output=True, text=True,
                             check=True).stdout.split()
    assert tracked == ["docs/decision-log.md"], "the decision log is not tracked"
