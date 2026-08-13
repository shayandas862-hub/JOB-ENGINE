"""Phase 8 task 1 — the container contract.

One image, four doors (run | mcp | status | dashboard), config from the
environment ONLY. These tests pin the shape of the Dockerfile, the entrypoint
router, and the no-venv interpreter fallback in scripts/run.py — all offline,
no Docker daemon needed. The build itself is proven live (suite green inside
the container, `run --dry-run` with env-injected secrets).
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = ROOT / "Dockerfile"
ENTRYPOINT = ROOT / "docker-entrypoint.sh"
DOCKERIGNORE = ROOT / ".dockerignore"


def load_run_script():
    spec = importlib.util.spec_from_file_location(
        "run_script", ROOT / "scripts" / "run.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------- Dockerfile

def test_dockerfile_builds_slim_313_from_the_lock():
    text = DOCKERFILE.read_text()
    assert text.splitlines()[0].startswith("#")  # says what it is
    assert "FROM python:3.13-slim" in text
    assert "requirements.lock" in text
    assert "pip install --no-cache-dir -r requirements.lock" in text


def test_dockerfile_sets_pythonpath_to_src():
    text = DOCKERFILE.read_text()
    assert "PYTHONPATH=/app/src" in text


def test_dockerfile_copies_an_allowlist_never_the_tree():
    # `COPY . .` (or any ADD) could smuggle .env / local state into a layer.
    # Sources must be named, and none may be dotfiles beyond the entrypoint.
    for line in DOCKERFILE.read_text().splitlines():
        words = line.split()
        if not words or words[0] not in ("COPY", "ADD"):
            continue
        assert words[0] == "COPY", f"ADD is banned: {line!r}"
        sources = [w for w in words[1:-1] if not w.startswith("--")]
        for src in sources:
            assert src != "." and not src.startswith("./"), \
                f"blanket tree copy: {line!r}"
            assert ".env" not in src, f".env must never enter a layer: {line!r}"


def test_dockerfile_names_no_secret():
    # Config is injected at runtime (docker -e / Secret Manager) — a secret
    # name appearing in the Dockerfile means a value could be baked with it.
    text = DOCKERFILE.read_text()
    for needle in ("DATABASE_URL", "GEMINI", "ADZUNA", "REED_", "NOTION",
                   "TOKEN", "API_KEY", "COMPANIES_HOUSE"):
        assert needle not in text, f"secret name in Dockerfile: {needle}"


def test_dockerfile_runs_as_nonroot_behind_the_entrypoint():
    text = DOCKERFILE.read_text()
    assert 'ENTRYPOINT ["/app/docker-entrypoint.sh"]' in text
    assert 'CMD ["run"]' in text          # the image's default door
    assert "\nUSER app\n" in text         # never root at runtime


def test_dockerignore_blocks_env_venv_git_but_keeps_the_lock():
    lines = [ln.strip() for ln in DOCKERIGNORE.read_text().splitlines()]
    for required in (".env", ".env.*", ".venv/", ".git/"):
        assert required in lines, f".dockerignore must list {required}"
    assert "*.lock" not in lines            # would drop requirements.lock
    assert "requirements.lock" not in lines


# ---------------------------------------------------------- entrypoint router

def _route(*args: str) -> subprocess.CompletedProcess:
    """Run the entrypoint with `python` shimmed to an echo stub.

    The router execs `python …`; with the stub first on PATH the process
    prints the exact command line it would have become, so the test drives
    the real case statement, not a grep of its text.
    """
    shim = ROOT / "tests" / "fixtures" / "python_shim"
    return subprocess.run(
        ["/bin/sh", str(ENTRYPOINT), *args],
        cwd=ROOT, capture_output=True, text=True,
        env={**os.environ, "PATH": f"{shim}:{os.environ['PATH']}"},
    )


def test_entrypoint_is_executable():
    assert ENTRYPOINT.exists()
    assert os.access(ENTRYPOINT, os.X_OK)


def test_entrypoint_routes_all_four_doors_and_passes_args_through():
    assert _route("run", "--dry-run").stdout.strip() == \
        "python scripts/run.py --dry-run"
    assert _route("mcp").stdout.strip() == "python -m mcp_server.server"
    assert _route("status").stdout.strip() == "python -m status.server"
    assert _route("dashboard", "--port", "9000").stdout.strip() == \
        "python scripts/run_dashboard.py --port 9000"


def test_entrypoint_defaults_to_the_daily_run():
    # Cloud Run Job invokes the image bare: no args must mean `run`.
    assert _route().stdout.strip() == "python scripts/run.py"


def test_entrypoint_rejects_an_unknown_door():
    proc = _route("shell")
    assert proc.returncode == 2
    assert "usage:" in proc.stderr
    assert "shell" in proc.stderr


# ------------------------------------------------- run.py without a repo venv

def test_stage_interpreter_prefers_the_repo_venv(tmp_path):
    venv_py = tmp_path / ".venv" / "bin" / "python"
    venv_py.parent.mkdir(parents=True)
    venv_py.write_text("")
    run = load_run_script()
    assert run._python(tmp_path) == str(venv_py)


def test_stage_interpreter_falls_back_to_the_running_one(tmp_path):
    # The container has no .venv — stages must reuse the image interpreter.
    run = load_run_script()
    assert run._python(tmp_path) == sys.executable
