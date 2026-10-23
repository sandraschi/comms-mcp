"""Backend channel-status aggregation tests (Settings Channels section).

channel_statuses() must report all four channels even when adapters throw,
and must never leak tokens or QR payloads.
"""

import pytest

from comms_mcp import server
from comms_mcp.adapters import slack, teams, telegram, whatsapp


async def _boom():
    raise RuntimeError("probe exploded")


def _boom_sync():
    raise RuntimeError("probe exploded")


@pytest.mark.asyncio
async def test_channels_all_report_on_total_failure(monkeypatch):
    monkeypatch.setattr(telegram, "get_me", _boom)
    monkeypatch.setattr(whatsapp, "status", _boom)
    monkeypatch.setattr(slack, "status", _boom)
    monkeypatch.setattr(teams, "auth_status", _boom_sync)
    channels = await server.channel_statuses()
    assert [c["id"] for c in channels] == ["telegram", "whatsapp", "slack", "teams"]
    assert all(c["configured"] is False for c in channels)


@pytest.mark.asyncio
async def test_channels_no_secrets_leak(monkeypatch):
    import json

    async def fake_tg():
        return {"ok": True, "result": {"username": "testbot"}}

    async def fake_wa():
        return {
            "success": True,
            "connected": False,
            "qr": "SECRET-QR-PAYLOAD",
            "pairing_code": "123-456",
        }

    async def fake_slack():
        return {
            "success": True,
            "team": {"name": "T"},
            "bot": {"name": "b"},
        }

    monkeypatch.setattr(telegram, "get_me", fake_tg)
    monkeypatch.setattr(whatsapp, "status", fake_wa)
    monkeypatch.setattr(slack, "status", fake_slack)
    channels = await server.channel_statuses()
    blob = json.dumps(channels)
    assert "SECRET-QR-PAYLOAD" not in blob
    assert "123-456" not in blob
    wa = next(c for c in channels if c["id"] == "whatsapp")
    assert wa["pairing_needed"] is True
