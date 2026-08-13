"""How many bugs are held shut by a sentence someone has to remember — pinned,
so it can only go down.

`docs/bug-log.md` already ends with the finding that matters most about it:
"Category 3 is now the largest and it is growing faster than category 1 is
shrinking." Guards that are documents rather than code are this project's most
common unclosed shape, and the log names them honestly. What it could not do was
stop the number rising — the count lived in a prose paragraph that had to be
recounted by hand, and it had already gone stale twice ("five of twelve" and
"five of sixteen" in a log of twenty-six entries).

So this is a ratchet on that count. It does not judge whether a guard is good
enough; it counts the entries whose Guard field **says out loud** that nothing
mechanical prevents a repeat, and refuses to let that number grow. Closing one
means either writing the test the entry asks for, or admitting a new one — and
the second is now a deliberate act with a number attached rather than a quiet
drift.

The honest weakness, stated because this file is about honesty: it matches
PHRASES. Someone could rephrase an admission and duck it, which would show up
here as the count falling without any test being written. That is why the
phrase list is explicit and small rather than clever, and why
`test_the_admission_scan_still_recognises_the_known_guardless_entries` pins
specific ids — a rephrase that drops B-GAE-001 out of the set fails there
instead of silently improving the score.

Repo-only, like `tests/test_bug_log.py`: the docs tree is not in the container.
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

# Phrases in which an entry admits, in its own words, that nothing executable
# stands between the bug and a repeat. Every one of these is lifted from a real
# Guard field in the log — none is hypothetical.
#
#   "no test enforces"        · 001, 005, 022
#   "documentation line only" · 001
#   "standing question in"    · 004  (a rule in CLAUDE.md, not code)
#   "standing rule in"        · 005
#   "if someone runs it"      · 006  (get_advisors is real, but only if run)
#   "none —"                  · 010
#   "none that is automatic"  · 012
#   "nothing checks"          · 012
#   "nothing automatic"       · 015, 025
#   "the only thing preventing" · 015
#   "nothing stops"           · 019
#   "no ci lane runs it"      · 019
#   "nothing generic"         · 022
#   "only a human"            · 024
#   "nothing guards"          · 037  (added 2026-08-12, see below)
#   "weaker guard than a test" · 022, 036  (added 2026-08-12, see below)
#
# The last two were added at the Phase 9 close, and the reason is the honest
# weakness this file's own docstring names: the scan matches PHRASES, and two
# entries written that same afternoon (036 and 037) admitted an unguarded half
# in wording it did not know — so they ducked the ratchet without anyone
# intending to duck it. The wording was not the problem; the phrase list being
# shorter than the language people write in was. Both phrases below are lifted
# verbatim from real Guard fields, per the rule above.
ADMISSIONS = (
    "no test enforces",
    "no test fails",
    "nothing automatic",
    "nothing generic",
    "nothing stops",
    "nothing checks",
    "nothing guards",
    "no ci lane runs it",
    "documentation line only",
    "sentence in a document",
    "weaker guard than a test",
    "the only thing preventing",
    "none that is automatic",
    "if someone runs it",
    "none —",
    "standing rule in",
    "standing question in",
    "only a human",
)

# Measured 2026-08-11 at the infra sitting: 11 of 26 entries. MAY ONLY GO DOWN.
#
# Two of the eleven were added by that same sitting and are not a regression —
# B-GAE-024 and B-GAE-025 both say their guard cannot run in CI because it needs
# the live database credential, which is true and is the reason they say it. The
# other nine are the pre-existing backlog the log's closing section describes.
#
# RAISED to 12 on 2026-08-12 (task 6), deliberately and with the reason stated,
# which is the only way this number is allowed to move upward. B-GAE-034 — a
# discovery stage holding one transaction open across its network fetches, so a
# migration run at the same time is refused — genuinely cannot be caught by a
# test: it is a runtime interleaving of a stage and a migration, not a shape any
# scan can see. The entry says so, and says what to run to diagnose it instead.
# The honest alternative was to word it vaguely enough to duck this ratchet,
# which is the exact failure the ratchet exists to make visible.
# RAISED to 13 on 2026-08-12 at the Phase 9 close. Three moves, netting +1, and
# each is stated because a number that moves without a reason is the drift this
# ratchet exists to stop:
#   −1  B-GAE-010 LEAVES. Migration 0055 replaced the single-column unique key
#       with UNIQUE (owner_id, search_title), so a database constraint — a real
#       mechanism, not a sentence — now prevents it. Its id comes off
#       KNOWN_GUARDLESS in this same commit, exactly as the failure message
#       below instructs.
#   +2  B-GAE-036 and B-GAE-037 JOIN, both logged the same day. 036 has a test
#       for the wiring and nothing for "the suite is green inside the snapshot",
#       which is held by a ritual step in CLAUDE.md. 037's cloud half is
#       mechanised and its laptop half is not, deliberately: the obvious test
#       would be red on the founder's machine today, and closing a phase by
#       adding a failing test is how a suite starts being ignored.
#   ±0  B-GAE-034 was counted in the 12 above but never added to KNOWN_GUARDLESS
#       when that number was raised. Added now, so the two halves agree.
# B-GAE-033 deliberately did NOT join: its prose gap was closed with a real test
# (tests/test_dev_doc_paths.py) rather than an admission, which is the direction
# this ratchet is meant to push.
# RAISED to 19 on 2026-08-12 by the independent close audit, +6 in one move —
# large on purpose and stated per the rule above: the audit logged six defects
# (B-GAE-040..045) it found by mutation and by measuring the live database and
# the built image, and every one is OPEN with no mechanical guard yet. Wording
# them to duck this ratchet was the alternative, and it is the one this file
# exists to forbid. Each id comes off KNOWN_GUARDLESS in the commit that writes
# its real guard, exactly as the failure message below instructs.
# LOWERED to 18 on 2026-08-12, Phase 9.5 task 0. B-GAE-040 is closed with a
# real test rather than a sentence — `test_the_snapshot_signals_never_disagree`,
# unmarked so the predicate it checks cannot skip it — so its id comes off
# KNOWN_GUARDLESS below in this same commit. This is the direction this file
# exists to push, and the first time the number has gone down since it was
# raised by the close audit.
# LOWERED to 17 the same day. B-GAE-041 (committed test residue on the
# production database) is closed by tests/test_db_residue.py, which reads the
# probe names out of the test sources and asserts none of them survives on
# live — with two controls, because a residue scan that silently matches
# nothing looks exactly like a clean database.
# LOWERED to 16 the same day. B-GAE-042's guard now covers the class
# (equal-to-or-inside a scrubbed path) rather than the one instance that was
# found, and was checked in three directions so a widened matcher cannot
# quietly start swallowing legitimate links.
# LOWERED to 15 the same day. B-GAE-043 is closed by tests/test_image_hygiene.py,
# whose central test reads the source path recorded inside every .pyc in the
# copied trees — so foreign bytecode fails the container lane by name, in the
# one place the blind spot was previously invisible by construction.
# LOWERED to 14 the same day, closing the last of task 0. B-GAE-045's guard is
# tests/test_snapshot_verifier.py, which RUNS the verifier in a sandbox repo
# with a deliberately broken grep on PATH rather than reading its source — and
# also fires the scrub's four patterns at a planted leak, which nothing had
# ever done.
#
# Task 0 took this number from 19 to 14. Five of the close audit's six defects
# are closed with executing tests; B-GAE-044 remains, being a record-accuracy
# finding rather than something a test can hold.
# RAISED to 15 on 2026-08-13, deliberately, with the reason stated as this
# number's own rule demands. B-GAE-048 — email sign-up is enabled on the live
# Supabase project, so "the stranger tier is switched OFF" is held by the
# Google provider alone while a second, never-considered way to mint a token
# this door correctly trusts stands open — genuinely has no guard, and the
# honest reason is that the state it depends on IS NOT IN THIS REPOSITORY. It
# is a toggle in a hosted dashboard: no test in this suite can see it, nothing
# went red on the day it was switched on, and nothing goes red today. Wording
# the entry vaguely enough to duck this ratchet was the alternative, and it is
# the one this file exists to forbid.
#
# How it comes back DOWN is written into the entry's own Fix: move the gate out
# of the dashboard and into the code, so `auth.signin.owner_for_auth_user`
# refuses to CREATE a profile unless self-serve registration is explicitly
# enabled here. That is testable, and on the day it is written B-GAE-048 comes
# off KNOWN_GUARDLESS in the same commit.
# LOWERED to 14 the SAME DAY, because that is exactly what happened: the gate
# was written (tests/test_self_serve_registration_gate.py, plus two door cases
# in tests/test_signin_door.py) and B-GAE-048 comes off KNOWN_GUARDLESS below.
# This file caught the change itself — the entry stopped reading as guardless
# and `test_the_admission_scan_still_recognises_the_known_guardless_entries`
# went red demanding both edits together, which is the ratchet working rather
# than the ratchet being edited around.
# The entry itself stays OPEN, and that is not a contradiction: the repository
# is shut and the deployed revision is not, so the guard exists while the live
# exposure lasts until the service is redeployed.
# RAISED to 15 on 2026-08-13 for B-GAE-049, deliberately and with the reason.
# The pre-push ritual runs the offline lane and the snapshot lane, and BOTH
# skip every RUN_DB_TESTS test — so a change that breaks only database tests is
# blessed twice locally and fails first in the PUBLIC repository. Nothing
# mechanical prevents that: the public CI is the check, and it runs after
# publication by construction. The only thing between a DB-only regression and
# a red public repo is remembering to type RUN_DB_TESTS=1, which is precisely
# the kind of guard this file exists to name rather than flatter.
MAX_GUARDLESS_ENTRIES = 15

# Pinned individually as well as counted, so that a rephrasing cannot lower the
# score without anyone noticing. Removing one of these is a real event: it means
# a test now exists, and the id should come off this list in the same commit.
KNOWN_GUARDLESS = frozenset({
    "B-GAE-001", "B-GAE-004", "B-GAE-005", "B-GAE-006", "B-GAE-012",
    "B-GAE-015", "B-GAE-019", "B-GAE-022", "B-GAE-024", "B-GAE-025",
    "B-GAE-034", "B-GAE-036", "B-GAE-037", "B-GAE-044", "B-GAE-049",
})


def _entries() -> list[tuple[str, str]]:
    """(id, Guard field text) for every entry in the log."""
    text = BUG_LOG.read_text()
    found = list(ENTRY_RE.finditer(text))
    out = []
    for i, match in enumerate(found):
        end = found[i + 1].start() if i + 1 < len(found) else len(text)
        body = text[match.end():end]
        guard = re.search(r"- \*\*Guard:\*\*(.*?)(?=\n- \*\*|\Z)", body, re.S)
        out.append((match.group(1), " ".join(guard.group(1).split()) if guard else ""))
    return out


def guardless_entries() -> set[str]:
    """Entries whose Guard field admits nothing mechanical prevents a repeat."""
    return {
        bug_id for bug_id, guard in _entries()
        if any(phrase in guard.lower() for phrase in ADMISSIONS)
    }


def test_the_number_of_bugs_guarded_only_by_prose_never_grows():
    # The ratchet. A new entry admitting it has no real guard is allowed — the
    # log's whole value is that it says so — but it costs a deliberate edit to
    # this number, which is the point.
    guardless = guardless_entries()
    assert len(guardless) <= MAX_GUARDLESS_ENTRIES, (
        f"{len(guardless)} entries now admit they have no real guard, up from "
        f"the pinned {MAX_GUARDLESS_ENTRIES}: {sorted(guardless)}. Write the "
        "test the new entry asks for, or lower nothing and raise this number "
        "deliberately — but do not let it drift."
    )


def test_the_admission_scan_still_recognises_the_known_guardless_entries():
    # Without this, the ratchet above can be satisfied by breaking the scan or
    # by rewording an entry, and the count would fall while nothing improved.
    # This is the B-GAE-004 countermeasure applied to this test itself: the
    # assertion is about the named entries, not about a number that could reach
    # zero for the wrong reason.
    guardless = guardless_entries()
    stopped_matching = sorted(KNOWN_GUARDLESS - guardless)
    assert stopped_matching == [], (
        f"these entries no longer read as guardless: {stopped_matching}. If a "
        "real test was written, delete the id from KNOWN_GUARDLESS and lower "
        "MAX_GUARDLESS_ENTRIES in the same commit. If the wording merely "
        "changed, the admission is still true and the wording should say so."
    )


def test_every_entry_has_a_guard_field_at_all():
    # The scan reads one field. An entry missing it would be silently counted as
    # guarded — a false clean, which is worse than a false alarm.
    # tests/test_bug_log.py asserts the label is present; this asserts the label
    # has CONTENT, which is the part that would make this file lie.
    empty = sorted(bug_id for bug_id, guard in _entries() if not guard.strip())
    assert empty == [], f"these entries have an empty Guard field: {empty}"


def test_the_ratchet_is_measuring_the_whole_log():
    # A control. Every assertion above is about a subset; all of them pass if
    # the parser returns nothing at all.
    entries = _entries()
    assert len(entries) >= 26, (
        f"the parser found {len(entries)} entries; there were 26 when this was "
        "written, so it has probably broken rather than the log having shrunk"
    )
    guarded = {b for b, _ in entries} - guardless_entries()
    assert guarded, "no entry names a real guard — the scan is matching everything"
