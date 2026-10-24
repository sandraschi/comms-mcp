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


def test_strip_html_to_text():
    assert teams._strip_html("<p>Hello <b>world</b></p>") == "Hello world"
    assert teams._strip_html("plain") == "plain"


def test_channel_address_parsing():
    assert teams.is_channel_id("19:abc@thread.tacv2") is True
    assert teams.is_channel_id("19:abc123") is False
    assert teams.parse_channel_ref("team/T1/channel/19:c@thread.tacv2") == (
        "T1",
        "19:c@thread.tacv2",
    )
    assert teams.parse_channel_ref("19:c@thread.tacv2") == (None, "19:c@thread.tacv2")
    assert teams.parse_channel_ref("19:plainchat") == (None, None)
    assert teams.parse_channel_ref("team//channel/") == (None, None)


@pytest.mark.asyncio
async def test_channel_messages_and_send(monkeypatch):
    import comms_mcp.adapters.teams as teams_mod
    import comms_mcp.config as cfg_mod

    monkeypatch.setenv("COMMS_GRAPH_CLIENT_ID", "graph-app-id")
    teams_mod.get_settings = cfg_mod.get_settings
    teams_mod._access_token = lambda: "tok"

    import httpx

    async def fake_get(self, url, headers=None):
        class R:
            status_code = 200

            def raise_for_status(self):
                pass

            def json(self):
                if "/channels" in url and "messages" not in url:
                    return {"value": [{"id": "19:chan@thread.tacv2", "displayName": "General"}]}
                if "joinedTeams" in url:
                    return {"value": [{"id": "T1", "displayName": "Ops"}]}
                return {"value": [{"id": "m9", "body": {"content": "hello"}, "from": {}}]}

        return R()

    async def fake_post(self, url, json=None, headers=None):
        class R:
            def raise_for_status(self):
                pass

            def json(self):
                return {"id": "m10"}

        assert "channels" in url and "messages" in url
        return R()

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    listed = await teams_mod.list_teams_with_channels()
    assert listed["success"] is True
    assert listed["teams"][0]["channels"][0]["id"] == "19:chan@thread.tacv2"
    hist = await teams_mod.channel_messages("T1", "19:chan@thread.tacv2", limit=5)
    assert hist["success"] is True
    assert hist["messages"][0]["text"] == "hello"
    sent = await teams_mod.channel_send(None, "19:chan@thread.tacv2", "hi")
    assert sent["success"] is True
    assert sent["team_id"] == "T1"


@pytest.mark.asyncio
async def test_list_chats_live(monkeypatch):
    import comms_mcp.adapters.teams as teams_mod
    import comms_mcp.config as cfg_mod

    monkeypatch.setenv("COMMS_GRAPH_CLIENT_ID", "graph-app-id")
    teams_mod.get_settings = cfg_mod.get_settings
    teams_mod._access_token = lambda: "tok"

    import httpx

    async def fake_get(self, url, headers=None):
        class R:
            def raise_for_status(self):
                pass

            def json(self):
                return {"value": [{"id": "19:abc", "topic": "Ops", "chatType": "group"}]}

        return R()

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    result = await teams.list_chats()
    assert result["success"] is True
    assert result["chats"][0]["id"] == "19:abc"


@pytest.mark.asyncio
async def test_chat_messages_and_edit_delete(monkeypatch):
    import comms_mcp.adapters.teams as teams_mod
    import comms_mcp.config as cfg_mod

    monkeypatch.setenv("COMMS_GRAPH_CLIENT_ID", "graph-app-id")
    teams_mod.get_settings = cfg_mod.get_settings
    teams_mod._access_token = lambda: "tok"

    import httpx

    async def fake_get(self, url, headers=None):
        class R:
            def raise_for_status(self):
                pass

            def json(self):
                return {
                    "value": [
                        {
                            "id": "m1",
                            "body": {"content": "<p>hi</p>"},
                            "from": {"user": {"displayName": "Steve"}},
                            "createdDateTime": "2026-01-01T00:00:00Z",
                        }
                    ]
                }

        return R()

    async def fake_post(self, url, json=None, headers=None):
        class R:
            def raise_for_status(self):
                pass

            def json(self):
                return {"id": "m2"}

        assert "reply" in url or "messages" in url
        return R()

    async def fake_patch(self, url, json=None, headers=None):
        class R:
            def raise_for_status(self):
                pass

        return R()

    async def fake_delete(self, url, headers=None):
        class R:
            def raise_for_status(self):
                pass

        return R()

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    monkeypatch.setattr(httpx.AsyncClient, "patch", fake_patch)
    monkeypatch.setattr(httpx.AsyncClient, "delete", fake_delete)
    hist = await teams.chat_messages("19:abc", limit=5)
    assert hist["success"] is True
    assert hist["messages"][0]["text"] == "hi"
    edited = await teams.edit_message("19:abc", "m1", "fixed")
    assert edited["success"] is True
    deleted = await teams.delete_message("19:abc", "m1")
    assert deleted["success"] is True
