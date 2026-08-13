"""B-GAE-043 — nothing from somebody's laptop may ride a `COPY` into a layer.

The Dockerfile copies by a named allowlist rather than `COPY .`, and its
comment says why: "a tree copy could smuggle local state or credentials into a
layer". `.dockerignore` is the belt to that brace. It was not holding.

Docker ignore patterns anchor at the **context root**. `__pycache__/` therefore
matched a top-level `__pycache__` and nothing else — never `tests/__pycache__`,
never `src/reading/__pycache__`. So `COPY src/ scripts/ tests/ db/` carried 246
`.pyc` files out of the author's working copy and into the image, each with an
absolute macOS home path baked into it, while the Dockerfile's comment claimed
a protection the file did not deliver. CI images were clean by luck alone: a
fresh runner checkout has no caches, so the lane that runs most often could
never see it. Only images built on the laptop were affected — which includes
`ops/cloud/build-push.sh`, and so plausibly the deployed one.

The invariant below is deliberately not "no .pyc exists". Running pytest
creates bytecode as it imports, so that test would be red the moment it ran,
everywhere, forever. The real property is narrower and exactly matches the
defect: **every compiled file in this tree was compiled FROM this tree.** A
`.pyc` records the absolute path of its source, so foreign bytecode announces
itself no matter who copied it in or how. On a laptop the caches are local and
this passes; in a correctly built image the only caches are the ones the test
run just made, and they point at `/app`; in a smuggling image the paths point
somewhere else and this fails by name.
"""
from __future__ import annotations

import importlib.util
import marshal
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
DOCKERFILE = ROOT / "Dockerfile"
DOCKERIGNORE = ROOT / ".dockerignore"

# A .pyc is a fixed-size header (magic, flags, mtime, size) then a marshalled
# code object. 16 bytes on every version this project runs; computed from the
# magic rather than hardcoded so a Python upgrade cannot silently misread it.
_HEADER = len(importlib.util.MAGIC_NUMBER) + 12

# Classes that occur at ANY depth, so the flat form is always a blind spot.
# Not every entry in .dockerignore: `docs/`, `plans/`, `ops/` and `data/` are
# top-level by design and flat is right for them.
AT_ANY_DEPTH = ("__pycache__", "*.pyc", ".pytest_cache", ".DS_Store", ".env")


def _copied_trees() -> list[str]:
    """The directories the Dockerfile actually copies, read from the Dockerfile."""
    return [d.rstrip("/") for line in DOCKERFILE.read_text().splitlines()
            if line.startswith("COPY ")
            for d in line.split()[1:-1] if d.endswith("/")]


def test_the_dockerignore_excludes_every_at_any_depth_class_recursively():
    # The cause, guarded directly: a pattern written flat cannot match a nested
    # path, and every entry below names something that appears nested in this
    # repo today. `**/x` is the only form that works, and the bug's own
    # prediction was that the NEXT flat entry would repeat it.
    text = DOCKERIGNORE.read_text()
    listed = {line.strip() for line in text.splitlines()
              if line.strip() and not line.startswith("#")}
    missing = [cls for cls in AT_ANY_DEPTH if f"**/{cls}" not in listed]
    assert missing == [], (
        f"these classes occur at any depth but .dockerignore only excludes them "
        f"at the context root: {missing}. Docker anchors patterns at the root, "
        f"so the flat form ships every nested copy (B-GAE-043). Write `**/{missing[0]}`."
    )


def test_the_dockerfile_still_copies_by_allowlist_not_by_tree():
    # The control for the test above: excluding nested caches matters only
    # while the copy is an allowlist of source trees. `COPY . .` would make
    # .dockerignore the ONLY protection, which is the arrangement that just
    # proved unreliable.
    body = DOCKERFILE.read_text()
    assert not re.search(r"^COPY \.[\s/]", body, re.M), (
        "the Dockerfile now copies the whole tree — .dockerignore becomes the "
        "only thing between the build context and a layer")
    assert _copied_trees(), "no COPY of a directory found — the parser has broken"


def test_no_bytecode_in_this_tree_was_compiled_somewhere_else():
    """The one that runs inside the container and means something there.

    Passes on a developer's machine (their caches are theirs), passes in a
    correctly built image (the only caches are the ones this run created, and
    they point at /app), fails in an image carrying somebody's working copy.
    """
    foreign: list[str] = []
    for tree in _copied_trees():
        for pyc in (ROOT / tree).rglob("*.pyc"):
            try:
                code = marshal.loads(pyc.read_bytes()[_HEADER:])
            except Exception:                      # noqa: BLE001 — unreadable
                continue                           # is not evidence either way
            source = getattr(code, "co_filename", "")
            if source and not source.startswith(str(ROOT)):
                foreign.append(source)

    assert foreign == [], (
        f"{len(foreign)} compiled file(s) in this tree were compiled somewhere "
        f"else — e.g. {foreign[0]!r}. In an image that means a working copy was "
        "smuggled past .dockerignore into a layer, paths and all (B-GAE-043)."
    )
