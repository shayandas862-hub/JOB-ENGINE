"""B-GAE-033's second half — docs/dev.md's Layout must name paths that exist.

The entry's finding was that dev.md's prose is guarded by nothing, so it drifted
for a phase and a half: a `src/read/` described as a Gemini reader long after
the engine stopped calling AI, and eleven packages added since Phase 7.5 that
the Layout had never heard of. The counts were fixed by DELETING them (one place
owns a number, and it is measured by test). The prose cannot be deleted — it is
the file's job — so it gets the cheapest real guard available: every repository
path it names must exist.

This does not check that the description is true, and it is not pretended to.
It checks the one kind of rot that is mechanical: a directory renamed or a
module moved, leaving the map pointing at nothing.

Repo-only: the docs tree is not in the container image.
"""
from __future__ import annotations

import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
DEV = ROOT / "docs" / "dev.md"

pytestmark = pytest.mark.skipif(
    not DEV.exists(), reason="repo-only contract: docs/ is not in the image")

# Backticked paths under a real top-level directory. Trailing slash allowed
# (`src/cv/`), as is a bare package (`src/match/`). Deliberately narrow: prose
# mentions plenty of things that are not paths, and a greedy pattern would turn
# this guard into a nuisance nobody trusts.
PATH_RE = re.compile(r"`((?:src|scripts|db|ops|tests)/[A-Za-z0-9_./-]*)`")

# Named in dev.md as things that do NOT exist, on purpose.
EXPECTED_ABSENT = {
    "ops/sweep-logs/",     # created at runtime by the sweep, gitignored
    "ops/classify-logs/",  # same, by the classification pass
}


def _paths() -> list[str]:
    return [p for p in PATH_RE.findall(DEV.read_text())
            if p not in EXPECTED_ABSENT]


def test_every_repository_path_dev_md_names_still_exists():
    missing = sorted({p for p in _paths() if not (ROOT / p.rstrip("/")).exists()})
    assert missing == [], (
        f"docs/dev.md points at paths that are gone: {missing}. The map is "
        "wrong, not the code — fix the Layout section.")


def test_the_scan_actually_finds_the_layout_and_is_not_matching_nothing():
    # The control. Every assertion above passes trivially if the pattern stops
    # matching, which is this project's most-repeated defect (B-GAE-004): the
    # count going to zero would read exactly like a clean result.
    found = set(_paths())
    assert len(found) >= 15, (
        f"the scan found only {len(found)} paths in dev.md; it found 28 when "
        "written, so the pattern has probably broken rather than the file "
        "having emptied")
    # Two anchors that must be in any honest Layout of this repo.
    assert "src/mcp_server/" in found or "src/mcp_server" in found
    assert "db/migrations/" in found or "db/migrations" in found
