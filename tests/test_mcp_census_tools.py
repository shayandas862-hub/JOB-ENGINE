"""The census MCP switches, driven through the real in-process client.

run_sweep must spawn the script DETACHED (a sweep takes hours; an MCP call
must return in milliseconds) with its output logged under ops/sweep-logs/,
and audit the start. sweep_status is a pure read: counts straight from
census_store, no audit (reads never audit). Neither ever returns a secret.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from fastmcp import Client

from pipeline.trigger import python_executable
from tests.conftest import FakeCursor, fake_conn
from tests.test_criteria import RoutingCursor

ROOT = Path(__file__).resolve().parents[1]


def _run(coro):
    return asyncio.run(coro)


OWNER = "own-1"


def _server(monkeypatch, cur=None, spawn=None):
    from mcp_server import census_tools
    from mcp_server.server import build_server
    if cur is not None:
        monkeypatch.setattr(census_tools, "get_conn", lambda: fake_conn(cur))
    if spawn is not None:
        monkeypatch.setattr(census_tools, "_spawn", spawn)
    # Owner resolution is proven in tests/test_mcp_identity.py; pinned here so
    # the budget owner these tools hand to a spawned run can be checked.
    monkeypatch.setattr(census_tools, "_owner", lambda cur: OWNER)
    monkeypatch.setattr(census_tools, "_remaining",
                        lambda cur, source, owner: {"source": source,
                                                    "owner_id": owner})
    return build_server()


def test_census_tools_are_registered(monkeypatch):
    mcp = _server(monkeypatch, FakeCursor())

    async def go():
        async with Client(mcp) as client:
            names = {t.name for t in await client.list_tools()}
            assert {"run_sweep", "sweep_status"} <= names
    _run(go())


def test_run_sweep_tool_spawns_detached_and_returns_immediately(monkeypatch, tmp_path):
    from mcp_server import census_tools
    monkeypatch.setattr(census_tools, "LOG_DIR", tmp_path / "sweep-logs")
    cur = FakeCursor()
    seen = {}
    mcp = _server(monkeypatch, cur,
                  spawn=lambda cmd, **kw: seen.update(cmd=cmd, **kw) or object())

    async def go():
        async with Client(mcp) as client:
            r = await client.call_tool("run_sweep", {"batch_size": 500})
            assert r.data["result"]["started"] is True and r.data["result"]["batch_size"] == 500
            assert "sweep-logs" in r.data["result"]["log_path"]
            assert seen["cmd"][0] == python_executable()          # resolved, not hardcoded
            assert seen["cmd"][1].endswith("scripts/sweep.py")   # the real entrypoint
            assert seen["cmd"][2:] == ["--batch", "500"]
            assert seen["start_new_session"] is True             # DETACHED
            assert seen["env"]["PYTHONPATH"] == "src"
            assert any("insert into mcp_audit" in e[0].lower() for e in cur.executed)
    _run(go())


def test_run_sweep_tool_respects_batch_size_arg(monkeypatch, tmp_path):
    from mcp_server import census_tools
    monkeypatch.setattr(census_tools, "LOG_DIR", tmp_path / "sweep-logs")
    seen = {}
    mcp = _server(monkeypatch, FakeCursor(),
                  spawn=lambda cmd, **kw: seen.update(cmd=cmd) or object())

    async def go():
        async with Client(mcp) as client:
            await client.call_tool("run_sweep", {"batch_size": 25})
            assert seen["cmd"][2:] == ["--batch", "25"]
    _run(go())


def test_sweep_status_returns_counts_without_audit(monkeypatch):
    cur = RoutingCursor([
        ("from licensed_sponsors", [{"total": 110}]),
        ("group by probe_outcome", [{"probe_outcome": "board_found", "n": 3}]),
        ("from census_jobs", [{"jobs": 42, "matches": 7}]),
        ("group by registry_outcome", [{"registry_outcome": "matched", "n": 2}]),
    ])
    mcp = _server(monkeypatch, cur)

    async def go():
        async with Client(mcp) as client:
            r = await client.call_tool("sweep_status", {})
            assert r.data["result"]["total_unique_orgs"] == 110
            assert r.data["result"]["boards_found"] == 3
            assert r.data["result"]["census_jobs"] == 42 and r.data["result"]["title_matches"] == 7
            assert r.data["result"]["registry_by_outcome"] == {"matched": 2}
            assert r.data["result"]["remaining"] == 107
            assert not any("mcp_audit" in s for s, _ in cur.executed)  # reads never audit
    _run(go())


def test_run_sweep_tool_passes_owner_lens_and_workers(monkeypatch, tmp_path):
    # U1: the flag is the owner's lens now (their rule codes pick the batch);
    # software_only is gone from the tool contract — a deliberate rename.
    from mcp_server import census_tools
    monkeypatch.setattr(census_tools, "LOG_DIR", tmp_path / "sweep-logs")
    seen = {}
    mcp = _server(monkeypatch, FakeCursor(),
                  spawn=lambda cmd, **kw: seen.update(cmd=cmd) or object())

    async def go():
        async with Client(mcp) as client:
            r = await client.call_tool(
                "run_sweep", {"batch_size": 200, "owner_lens": True,
                              "workers": 4})
            assert r.data["result"]["owner_lens"] is True and r.data["result"]["workers"] == 4
            assert seen["cmd"][2:] == ["--batch", "200", "--owner-lens",
                                       "--workers", "4"]
    _run(go())


def test_run_classification_tool_spawns_pass1_detached(monkeypatch, tmp_path):
    from mcp_server import census_tools
    monkeypatch.setattr(census_tools, "CLASSIFY_LOG_DIR",
                        tmp_path / "classify-logs")
    cur = FakeCursor()
    seen = {}
    mcp = _server(monkeypatch, cur,
                  spawn=lambda cmd, **kw: seen.update(cmd=cmd, **kw) or object())

    async def go():
        async with Client(mcp) as client:
            r = await client.call_tool("run_classification", {"batch_size": 5000})
            assert r.data["result"]["started"] is True and r.data["result"]["batch_size"] == 5000
            assert "classify-logs" in r.data["result"]["log_path"]
            assert seen["cmd"][0] == python_executable()          # resolved, not hardcoded
            assert seen["cmd"][1].endswith("scripts/classify_sponsors.py")
            assert seen["cmd"][2:] == ["--batch", "5000"]
            assert seen["start_new_session"] is True             # DETACHED
            assert seen["env"]["PYTHONPATH"] == "src"
            assert any("insert into mcp_audit" in e[0].lower()
                       for e in cur.executed)
    _run(go())


def test_classify_status_returns_pass1_scoreboard_without_audit(monkeypatch):
    cur = RoutingCursor([
        ("from licensed_sponsors", [{"total": 126342}]),
        ("group by registry_outcome", [{"registry_outcome": "matched", "n": 80},
                                       {"registry_outcome": "not_found", "n": 20}]),
        ("industry_codes &&", [{"n": 12}]),
    ])
    mcp = _server(monkeypatch, cur)

    async def go():
        async with Client(mcp) as client:
            r = await client.call_tool("classify_status", {})
            assert r.data["result"]["total_unique_orgs"] == 126342
            assert r.data["result"]["classified"] == 100
            assert r.data["result"]["software_companies"] == 12
            assert r.data["result"]["remaining"] == 126242
            assert not any("mcp_audit" in s for s, _ in cur.executed)
    _run(go())


def test_census_tools_never_return_a_secret(monkeypatch, tmp_path):
    from mcp_server import census_tools
    monkeypatch.setattr(census_tools, "LOG_DIR", tmp_path / "sweep-logs")
    monkeypatch.setenv("COMPANIES_HOUSE_API_KEY", "super-secret-ch-key")
    cur = FakeCursor()
    mcp = _server(monkeypatch, cur, spawn=lambda cmd, **kw: object())

    async def go():
        async with Client(mcp) as client:
            r = await client.call_tool("run_sweep", {"batch_size": 5})
            assert "super-secret-ch-key" not in str(r.data["result"])
            audit = next(e for e in cur.executed
                         if "insert into mcp_audit" in e[0].lower())
            assert "super-secret-ch-key" not in str(audit[1])
    _run(go())


# ---- who pays for a run somebody asked for (task 5) -------------------------

def test_a_user_triggered_sweep_carries_its_owner_into_the_spawned_run(
        monkeypatch, tmp_path):
    # The spend happens two processes away — the tool spawns sweep.py, which
    # makes the calls. Environment is what crosses that gap, so if this
    # variable is missing the run is charged to nobody and one key holder can
    # quietly drain the shared quota.
    from budget.gate import OWNER_ENV
    from mcp_server import census_tools
    monkeypatch.setattr(census_tools, "LOG_DIR", tmp_path / "sweep-logs")
    seen = {}
    mcp = _server(monkeypatch, FakeCursor(),
                  spawn=lambda cmd, **kw: seen.update(kw) or object())

    async def go():
        async with Client(mcp) as client:
            await client.call_tool("run_sweep", {"batch_size": 5})
            assert seen["env"][OWNER_ENV] == OWNER
    _run(go())


def test_a_user_triggered_classification_carries_its_owner_too(
        monkeypatch, tmp_path):
    from budget.gate import OWNER_ENV
    from mcp_server import census_tools
    monkeypatch.setattr(census_tools, "CLASSIFY_LOG_DIR", tmp_path / "c-logs")
    seen = {}
    mcp = _server(monkeypatch, FakeCursor(),
                  spawn=lambda cmd, **kw: seen.update(kw) or object())

    async def go():
        async with Client(mcp) as client:
            await client.call_tool("run_classification", {"batch_size": 5})
            assert seen["env"][OWNER_ENV] == OWNER
    _run(go())


def test_the_nightly_run_is_charged_to_nobody(monkeypatch, tmp_path):
    # The scheduler's own 06:30 run passes no owner, so the world half debits
    # the shared cap and no owner budget at all — the founder's night stays
    # exactly what it was.
    from budget.gate import OWNER_ENV
    from pipeline.trigger import start_pipeline
    seen = {}
    start_pipeline(spawn=lambda cmd, **kw: seen.update(kw) or object(),
                   log_dir=tmp_path)
    assert OWNER_ENV not in seen["env"]


def test_sweep_status_shows_what_is_left_of_every_source(monkeypatch):
    from budget.ledger import SOURCES
    cur = RoutingCursor([
        ("from licensed_sponsors", [{"total": 110}]),
        ("group by probe_outcome", [{"probe_outcome": "board_found", "n": 3}]),
        ("from census_jobs", [{"jobs": 42, "matches": 7}]),
        ("group by registry_outcome", [{"registry_outcome": "matched", "n": 2}]),
    ])
    mcp = _server(monkeypatch, cur)

    async def go():
        async with Client(mcp) as client:
            r = await client.call_tool("sweep_status", {})
            budget = r.data["result"]["budget"]
            assert set(budget) == set(SOURCES)
            assert budget["reed"]["owner_id"] == OWNER
    _run(go())
