"""B-GAE-035 — what GitHub will DO with the workflow the snapshot ships.

The snapshot ritual has always verified the snapshot's *content*: nothing
secret survives, the suite is green inside it, the history is one commit. It
never asked what GitHub would **run**. So the public repository received
`.github/workflows/ci.yml` verbatim — image and deploy jobs that authenticate
to Google Cloud with WIF credentials that deliberately do not exist there — and
failed both public runs by construction. A portfolio built to demonstrate CI
discipline greeted every visitor with a red X.

The rule these tests hold shut is an **allowlist**: the snapshot ships exactly
two jobs, the two that need no credential. A job added to the private workflow
later stays out by default rather than riding along until someone notices.

Repo-only, like tests/test_public_safety.py: the image carries no `.git` and no
git binary, so there is nothing here to assert inside the container.
"""
from __future__ import annotations

import pathlib
import re
import subprocess
import tempfile

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "ops" / "flip" / "public-ci.yml"
PRIVATE = ROOT / ".github" / "workflows" / "ci.yml"
PROOF = ROOT / ".github" / "workflows" / "public-ci-proof.yml"
SCRIPT = ROOT / "ops" / "flip" / "prepare-snapshot.sh"

pytestmark = pytest.mark.skipif(
    not (ROOT / ".git").exists(),
    reason="repo-only contract: no git index in the container image")

# The snapshot runs this same suite, and inside it `.github/workflows/ci.yml`
# IS the public workflow — so the tests that need the PRIVATE side (the
# scanner's control, the proof copy, the build itself) have nothing to compare
# against there, and the control would invert into a false pass. `private_only`
# is defined once, in conftest, because test_cloud_setup.py needs the same
# answer and two copies of one predicate is how a mirror starts drifting.
# The content guards below run in BOTH repos, so the public repository carries
# a working guard rather than a wholly skipped file.
from tests.conftest import private_only   # noqa: E402  (after the paths above)

# The two lanes that can run anywhere, because neither reads a credential:
# the offline suite, and the database lane whose Postgres is created empty on
# the runner and destroyed with it.
PUBLIC_JOBS = {"test", "database"}

# Matched against the raw text, not the parsed tree — a credential can hide in
# a `run:` block, a comment or an action input, and all three are text.
FORBIDDEN = {
    "a GitHub secret": "secrets.",
    "a WIF provider": "workload_identity_provider",
    "an OIDC token permission": "id-token",
    "the Google auth action": "google-github-actions",
    "a service account": "service_account",
    "a gcloud call": "gcloud ",
    "an Artifact Registry host": "pkg.dev",
    "a registry push": "docker push",
}


def _offences(text: str) -> list[str]:
    return [label for label, needle in FORBIDDEN.items() if needle in text]


def test_the_public_workflow_exists_where_the_snapshot_script_owns_it():
    # It lives with the ritual that installs it, not in .github/ — a second
    # file there would be a second workflow the private repo runs.
    assert PUBLIC.is_file(), f"the public workflow is missing: {PUBLIC}"


def test_the_public_workflow_runs_only_the_two_secret_free_jobs():
    # An ALLOWLIST, deliberately. A blocklist of today's private jobs would
    # pass the day a new credentialled job is added to ci.yml.
    jobs = set(yaml.safe_load(PUBLIC.read_text())["jobs"])
    assert jobs == PUBLIC_JOBS, (
        f"the public workflow's jobs are {sorted(jobs)}; only "
        f"{sorted(PUBLIC_JOBS)} may ship")


def test_the_public_workflow_names_no_secret_no_wif_and_no_deploy():
    assert _offences(PUBLIC.read_text()) == []


@private_only
def test_the_scanner_still_bites_the_workflow_that_actually_deploys():
    # The control, as its own test rather than a line inside the one above: a
    # scanner that has quietly stopped matching passes the public file for the
    # wrong reason, and this project's most persistent defect is exactly that
    # (B-GAE-004, B-GAE-008). The private workflow authenticates to Google
    # Cloud and pushes images, so it MUST trip every kind of needle here.
    assert _offences(PRIVATE.read_text()), (
        "the scanner found nothing in the workflow that deploys to Google "
        "Cloud — the scanner is broken, not the workflow")


def test_no_public_job_waits_on_a_job_that_was_left_behind():
    # `needs: [test, image]` with `image` removed is a workflow that can never
    # run — a red X of a different colour.
    spec = yaml.safe_load(PUBLIC.read_text())
    for name, job in spec["jobs"].items():
        needs = job.get("needs", [])
        needs = [needs] if isinstance(needs, str) else needs
        missing = [n for n in needs if n not in spec["jobs"]]
        assert missing == [], f"job {name!r} needs absent job(s): {missing}"


def test_the_public_workflow_asks_for_no_write_permission():
    spec = yaml.safe_load(PUBLIC.read_text())
    assert spec.get("permissions") == {"contents": "read"}, (
        "the public workflow must ask for read and nothing else: "
        f"{spec.get('permissions')!r}")


@private_only
def test_the_private_proof_copy_runs_the_same_jobs_and_only_by_hand():
    # A workflow that has never run cannot be trusted to go green on its first
    # public run, and a first-run failure would land a day-one red on a fresh
    # snapshot in front of exactly the audience the refresh is for. So the
    # private repo keeps a dispatch-only copy and runs it once before shipping.
    #
    # Two files that must say the same thing is precisely the shape that rotted
    # in B-GAE-025 (a mirror that stopped describing what it mirrored), so the
    # equality is a test rather than an intention. `jobs` is compared parsed:
    # what GitHub executes, not how it is commented.
    proof = yaml.safe_load(PROOF.read_text())
    public = yaml.safe_load(PUBLIC.read_text())
    assert proof["jobs"] == public["jobs"], (
        "the proof copy no longer runs what the snapshot would ship — proving "
        "it proves nothing")
    assert proof["permissions"] == public["permissions"]
    # PyYAML reads a bare `on:` key as the boolean True (the Norway problem),
    # which is why this is spelled `True` and not "on".
    assert proof[True] == {"workflow_dispatch": None} or \
        proof[True] == "workflow_dispatch", (
            f"the proof copy must run only by hand: {proof[True]!r}")


def test_the_readme_never_links_to_a_path_the_snapshot_deletes():
    # B-GAE-039, the same mirror class as this file's own bug. The README ships
    # verbatim and is the first thing a visitor reads, but the snapshot removes
    # four paths on the way out — so a link to one of them is a 404 that exists
    # ONLY in public, where nobody who could fix it is looking.
    #
    # The scrub list is read out of the script rather than copied here: two
    # copies of one list is how the private and public repos got out of step in
    # the first place. Runs in both checkouts — in the snapshot the paths really
    # are gone, so the assertion is if anything more direct there.
    script = SCRIPT.read_text()
    match = re.search(r"^for path in (.+); do$", script, re.M)
    assert match, "prepare-snapshot.sh no longer has a readable scrub list"
    scrubbed = match.group(1).split()
    assert len(scrubbed) >= 3, f"the scrub list parsed as {scrubbed} — suspicious"

    readme = (ROOT / "README.md").read_text()
    links = re.findall(r"\]\((?!https?:)([^)#]+)\)", readme)
    # B-GAE-042: "equal to, or INSIDE" — not just equal. The original compared
    # exact equality against the four scrubbed paths, so `docs/handoffs` was
    # caught and `docs/handoffs/phase-9p5-relay-2026-08-12.md` sailed through,
    # though both 404 identically in public. B-GAE-039's actual instance was a
    # link to the directory itself and the guard was written to that instance
    # rather than to its class — the B-GAE-004 shape, again. Citing a handoff
    # or an archived phase file by its full path is the NATURAL way to write
    # the link, which made the uncovered half the likelier one.
    dead = sorted({link for link in links
                   for gone in (g.strip("/") for g in scrubbed)
                   if link.strip("/") == gone or link.strip("/").startswith(gone + "/")})
    assert dead == [], (
        f"README links to {dead}, which the snapshot deletes (the path itself "
        "or something inside it) — the public repo would show a broken link")


def test_the_snapshot_signals_never_disagree():
    # B-GAE-040, and deliberately NOT `private_only` — a test that can be
    # skipped by the predicate it is checking is the bug, not the guard.
    #
    # `_is_snapshot()` reads two independent signals. In a real snapshot both
    # are true; in the private repo both are false; in the container neither
    # applies. There is exactly one way to get them to disagree, and it is the
    # accident this exists for: copying the public workflow over the private
    # one, which is a documented near-miss (B-GAE-036) with a live motive —
    # killing a red X in public. That copy moves signal one and cannot move
    # signal two, and before this test the whole suite went green over it.
    #
    # So: if this checkout carries the public workflow, it must also have been
    # scrubbed. Passing in both real repos and failing loudly in a corrupted
    # one is the entire specification.
    from tests.conftest import scrub_marker_is_gone, workflow_matches_the_public_one

    if workflow_matches_the_public_one() and not scrub_marker_is_gone():
        raise AssertionError(
            "this checkout carries the PUBLIC workflow but has NOT been "
            "scrubbed — so it is a private repo whose deploy workflow has been "
            "overwritten by ops/flip/public-ci.yml. Every private_only guard "
            "has just stood down, CI no longer deploys, and the suite would "
            "otherwise be green. Restore it: git checkout .github/workflows/ci.yml"
        )


def test_the_two_snapshot_signals_are_read_from_the_real_scrub_list():
    # The second signal is only independent while the scrub really does delete
    # that file. If the list is edited and the marker is not, `_is_snapshot()`
    # silently returns False in the actual snapshot — every private_only test
    # would run in public and fail there, which is B-GAE-035 arriving again by
    # a new road. The list is read from the script, never copied.
    from tests.conftest import _SCRUBBED_MARKER

    match = re.search(r"^for path in (.+); do$", SCRIPT.read_text(), re.M)
    assert match, "prepare-snapshot.sh no longer has a readable scrub list"
    scrubbed = match.group(1).split()
    marker = _SCRUBBED_MARKER.name
    assert marker in scrubbed, (
        f"conftest treats {marker!r} as proof a checkout was scrubbed, but the "
        f"scrub list is {scrubbed} and no longer removes it")


@private_only
def test_the_snapshot_ships_the_public_workflow_and_nothing_else():
    # The one assertion that proves the WIRING rather than the file: build a
    # real snapshot and read what .github/workflows actually contains. Reading
    # the script's source instead would prove only that it mentions the path.
    with tempfile.TemporaryDirectory() as tmp:
        target = pathlib.Path(tmp) / "snapshot"
        done = subprocess.run([str(SCRIPT), str(target)],
                              capture_output=True, text=True)
        assert done.returncode == 0, (
            f"prepare-snapshot.sh failed:\n{done.stdout}\n{done.stderr}")

        shipped = sorted(p.name for p in (target / ".github" / "workflows").iterdir())
        assert shipped == ["ci.yml"], f"snapshot workflows: {shipped}"
        assert (target / ".github" / "workflows" / "ci.yml").read_text() \
            == PUBLIC.read_text()
