"""B-GAE-047 — a log or plan may not name a test file that is not in the repo.

The finding: `plans/0014` was committed describing
`tests/test_tool_description_budget.py` as "a ratchet that measures what every
client pays per turn and refuses to let it grow" — while that file had never
been committed at all, and the copy on disk was RED against a budget nobody had
measured. So the phase record asserted a live guard, the repository contained
none, and nothing anywhere disagreed. That is this project's most-repeated
shape (B-GAE-004): a claim about a guard, with no guard on the claim.

It matters most in `docs/bug-log.md`, whose entry format REQUIRES a named
guard — "Guards are named, not implied". An entry citing a test that does not
exist is the log flattering itself in exactly the way its own rules forbid, and
`tests/test_bug_log_guard_ratchet.py` cannot see it: that file reads the Guard
field for admissions of absence, so a confident citation of a missing file
reads to it as a guard that exists.

The cheapest real check is the one `tests/test_dev_doc_paths.py` already makes
for `docs/dev.md`: every path the prose names must EXIST. It deliberately does
NOT check that the cited test passes — the suite being green proves that, and a
test asserting other tests pass is a loop nobody can debug. It checks the one
rot that is mechanical and that actually happened: prose naming a file that is
not there.

Repo-only: neither `plans/` nor `docs/` is in the container image. Both ship in
the public snapshot, minus the two directories the scrub deletes.
"""
from __future__ import annotations

import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SEARCHED = ("plans", "docs")

pytestmark = pytest.mark.skipif(
    not (ROOT / "docs").is_dir() or not (ROOT / "plans").is_dir(),
    reason="repo-only contract: plans/ and docs/ are not in the container")

# A test file path, backticked or bare. Narrow on purpose: prose names plenty
# of things that are not files, and a greedy pattern makes a guard nobody
# trusts. Matches `tests/test_foo.py` and tests/test_foo.py alike.
PATH_RE = re.compile(r"`?(tests/[A-Za-z0-9_/-]+\.py)`?")


def _cited() -> dict[str, list[str]]:
    """{cited test path: [documents that name it]}."""
    found: dict[str, list[str]] = {}
    for directory in SEARCHED:
        for doc in sorted((ROOT / directory).rglob("*.md")):
            for path in PATH_RE.findall(doc.read_text()):
                found.setdefault(path, []).append(
                    str(doc.relative_to(ROOT)))
    return found


def test_every_test_file_the_logs_and_plans_name_actually_exists():
    cited = _cited()
    missing = sorted(p for p in cited if not (ROOT / p).is_file())
    assert missing == [], (
        "these documents name test files that are not in the repository: "
        + "; ".join(f"{p} (cited by {', '.join(sorted(set(cited[p])))})"
                    for p in missing)
        + ". Either the test was never committed — which is what B-GAE-047 "
          "was — or it moved and the prose still points at the old path.")


def test_the_scan_is_actually_reading_the_logs_and_plans():
    # The control. The assertion above passes trivially if the pattern stops
    # matching or the directories stop being read, and a count of zero would
    # read exactly like a clean result — B-GAE-004, the defect this project
    # repeats more than any other.
    #
    # Measured 2026-08-12: 38 distinct cited test paths in the private repo,
    # 34 in the public snapshot (which deletes docs/handoffs and
    # docs/claude-md-archive). The floor is set below both so this file does
    # not go red in the snapshot for a reason that is not a defect.
    cited = _cited()
    assert len(cited) >= 25, (
        f"the scan found only {len(cited)} cited test paths across "
        f"{'/, '.join(SEARCHED)}/; there were 38 in the repo and 34 in the "
        "snapshot when this was written, so the pattern has probably broken "
        "rather than the documents having emptied")
    # The anchor: the file whose absence was the bug.
    assert "tests/test_tool_description_budget.py" in cited, (
        "nothing cites the description budget ratchet any more — if item 7 "
        "was rewritten, re-point this anchor at a real citation rather than "
        "deleting the control")
