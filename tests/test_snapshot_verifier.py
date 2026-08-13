"""B-GAE-045 — can the snapshot verifier print CLEAN it has not earned?

`ops/flip/prepare-snapshot.sh` is the last thing between this repository and a
public force-push. It scans the exported tree for four leak shapes and prints
`SNAPSHOT CLEAN` when it finds none. Everything downstream — including the
founder's decision to push — rests on that verdict, and until this file nothing
checked the checker.

Two ways it could bless a snapshot it had not scanned:

1. `check()` ran grep under `|| true` with stderr sent to `/dev/null`. The
   `|| true` was genuinely needed (grep exits 1 when it finds nothing, which
   under `set -e` would kill the script mid-verification), but it cannot tell
   exit 1 "clean" from exit 2 "the scanner itself broke" — and `2>/dev/null`
   hid the complaint. A typo in a pattern therefore produced four `ok` lines
   and a CLEAN verdict over a tree nobody had actually scanned. That is the
   construction this project's own gotcha list forbids: *a broken check must
   not look like a clean result.*
2. A missing LICENSE printed `LICENSE present: NO` and set nothing, so the
   script carried on to `SNAPSHOT CLEAN`.

Testing this by reading the script's source would only prove it contains
certain words. So these tests BUILD A SANDBOX REPOSITORY, run the real script
inside it, and read what it actually decides — including with a deliberately
broken `grep` shimmed onto PATH. The sandbox is tiny, so this stays fast, and
it never touches the working repo.

Note on the planted leak below: the matching string is ASSEMBLED at runtime and
never appears as a literal here. Writing a real-shaped project ref into a
tracked file is the exact leak these checks exist to catch — and it has
happened to this project once already, in the test that was checking for it.
"""
from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import tempfile

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "ops" / "flip" / "prepare-snapshot.sh"

pytestmark = pytest.mark.skipif(
    not SCRIPT.is_file(),
    reason="repo-only contract: ops/ is not in the container image")


def _sandbox(tmp: str, *, licensed: bool = True, leak: str | None = None) -> pathlib.Path:
    """A miniature repo the real script can be run inside."""
    repo = pathlib.Path(tmp) / "repo"
    (repo / "ops" / "flip").mkdir(parents=True)
    shutil.copy2(SCRIPT, repo / "ops" / "flip" / SCRIPT.name)
    (repo / "ops" / "flip" / "public-ci.yml").write_text("name: ci\non: push\njobs: {}\n")
    (repo / "README.md").write_text("a sandbox, not the real repository\n")
    if licensed:
        (repo / "LICENSE").write_text("MIT\n")
    if leak is not None:
        (repo / "leaky.md").write_text(f"connection string: {leak}\n")

    run = lambda *a: subprocess.run(a, cwd=repo, capture_output=True, text=True)  # noqa: E731
    run("git", "init", "-q", "-b", "main")
    run("git", "add", "-A")
    run("git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "seed")
    return repo


def _run_prepare(repo: pathlib.Path, target: pathlib.Path,
                 *, path_prefix: str | None = None):
    env = dict(os.environ)
    if path_prefix:
        env["PATH"] = f"{path_prefix}:{env['PATH']}"
    return subprocess.run(
        [str(repo / "ops" / "flip" / SCRIPT.name), str(target)],
        capture_output=True, text=True, env=env)


def test_a_healthy_sandbox_still_verifies_clean():
    # The control, and it comes first deliberately. Every assertion below is
    # "the script refused"; all of them would pass if the sandbox were broken
    # in some way that made the script fail for an unrelated reason. This is
    # the one that proves a refusal means something.
    with tempfile.TemporaryDirectory() as tmp:
        repo = _sandbox(tmp)
        done = _run_prepare(repo, pathlib.Path(tmp) / "out")
        assert done.returncode == 0, f"the control run failed:\n{done.stdout}\n{done.stderr}"
        assert "SNAPSHOT CLEAN" in done.stdout


def test_a_snapshot_missing_its_licence_is_not_clean():
    with tempfile.TemporaryDirectory() as tmp:
        repo = _sandbox(tmp, licensed=False)
        done = _run_prepare(repo, pathlib.Path(tmp) / "out")
        assert done.returncode != 0, (
            "a snapshot with no LICENSE was declared publishable — the check "
            "printed its NO and set no failure (B-GAE-045)")
        assert "NOT CLEAN" in done.stdout + done.stderr


def test_a_scanner_that_breaks_fails_shut_instead_of_reporting_ok():
    # The heart of it. grep exits 2 when grep itself is unhappy (a bad pattern,
    # an unreadable flag). `|| true` flattened that into the same answer as
    # "found nothing", so the verdict was CLEAN over an unscanned tree.
    with tempfile.TemporaryDirectory() as tmp:
        repo = _sandbox(tmp)
        shim = pathlib.Path(tmp) / "shim"
        shim.mkdir()
        broken = shim / "grep"
        broken.write_text("#!/bin/sh\necho 'grep: broken invocation' >&2\nexit 2\n")
        broken.chmod(0o755)

        done = _run_prepare(repo, pathlib.Path(tmp) / "out", path_prefix=str(shim))
        assert done.returncode != 0, (
            "the verifier declared a snapshot CLEAN while its scanner was "
            "exiting 2 on every pattern — nothing was actually scanned "
            "(B-GAE-045). Only exit 0 and exit 1 are answers.")
        assert "ok   no Supabase project ref" not in done.stdout, (
            "a broken scanner still printed an `ok` line, which is the "
            "false-clean this test exists to forbid")


def test_the_scrub_patterns_actually_catch_a_planted_leak():
    # The other half of "nothing checks the checker": the four patterns had
    # never been tried against something they are supposed to find, so a
    # pattern that silently matched nothing would look exactly like a clean
    # snapshot forever. Assembled at runtime — see the module docstring.
    planted = "db." + ("z" * 20) + ".supabase" + ".co"
    with tempfile.TemporaryDirectory() as tmp:
        repo = _sandbox(tmp, leak=planted)
        done = _run_prepare(repo, pathlib.Path(tmp) / "out")
        assert done.returncode != 0, (
            "a file containing a project-ref-shaped string passed the scrub — "
            "the pattern no longer matches what it was written to catch")
        assert "FAIL no Supabase project ref" in done.stdout
