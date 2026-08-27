"""Tests for the Teams adapter (v0.4, Graph) - allowlist, status, auth, send."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

os.environ.setdefault("COMMS_TEAMS_RECIPIENTS", "steve=stephanschipal@hotmail.com,19:abc123")

from comms_mcp.adapters import teams  # noqa: E402
from comms_mcp.outbox import sqlite as store  # noqa: E402

_DB = Path(tempfile.mkdtemp(prefix="comms-teams-test-")) / "comms.db"


@pytest.fixture(autouse=True)
def _fresh_env(tmp_path):
    os.environ["COMMS_DB_PATH"] = str(_DB)
    os.environ["COMMS_TEAMS_TOKEN_FILE"] = str(tmp_path / "teams_oauth.json")
    for suffix in ("", "-wal", "-shm"):
        p = Path(str(_DB) + suffix)
        if p.exists():
            p.unlink()
    store._conn(_DB).close()


def test_allow_list_parse():
    assert teams.allow_list() == ["steve", "19:abc123"]


@pytest.mark.asyncio
async def test_status_unconfigured(monkeypatch):
    monkeypatch.setenv("COMMS_GRAPH_CLIENT_ID", "")
    import comms_mcp.adapters.teams as teams_mod
    import comms_mcp.config as cfg_mod

    teams_mod.get_settings = cfg_mod.get_settings
    result = await teams.status()
    assert result["success"] is False
    assert result["configured"] is False


@pytest.mark.asyncio
async def test_send_allowlist_blocked(monkeypatch):
    monkeypatch.setenv("COMMS_GRAPH_CLIENT_ID", "graph-app-id")
    import comms_mcp.adapters.teams as teams_mod
    import comms_mcp.config as cfg_mod

    teams_mod.get_settings = cfg_mod.get_settings
    result = await teams.send_message("not-in-allowlist", "hi")
    assert result["success"] is False
    assert "allowlist" in result


@pytest.mark.asyncio
async def test_send_not_authorized(monkeypatch):
    monkeypatch.setenv("COMMS_GRAPH_CLIENT_ID", "graph-app-id")
    import comms_mcp.adapters.teams as teams_mod
    import comms_mcp.config as cfg_mod

    teams_mod.get_settings = cfg_mod.get_settings
    result = await teams.send_message("steve", "hi")
    assert result["success"] is False
    assert "not authorized" in result.get("error", "")


def test_auth_status_unconfigured():
    assert teams.auth_status()["success"] is False
