"""Backend channel-status + config-write tests (Settings Channels section).

channel_statuses() must report all four channels even when adapters throw,
and must never leak tokens or QR payloads. apply_config() validates,
persists to .env, and applies live — rejecting anything outside the
allowlist.
"""

import json
import os

import pytest

from comms_mcp import server
from comms_mcp.adapters import signal, slack, teams, telegram, whatsapp


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
    monkeypatch.setattr(signal, "status", _boom)
    channels = await server.channel_statuses()
    assert [c["id"] for c in channels] == ["telegram", "whatsapp", "slack", "teams", "signal"]
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


def _use_tmp_env(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    monkeypatch.setattr(server, "_ENV_FILE_OVERRIDE", env_file)
    return env_file


def test_apply_config_rejects_unknown_key(tmp_path, monkeypatch):
    _use_tmp_env(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="not writable"):
        server.apply_config({"COMMS_EVIL": "1"})


def test_apply_config_validates_retention(tmp_path, monkeypatch):
    _use_tmp_env(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match=">= 1"):
        server.apply_config({"COMMS_RETENTION_DAYS": "0"})
    with pytest.raises(ValueError, match="integer"):
        server.apply_config({"COMMS_RETENTION_DAYS": "abc"})


def test_apply_config_accepts_signal_keys(tmp_path, monkeypatch):
    _use_tmp_env(tmp_path, monkeypatch)
    result = server.apply_config(
        {"COMMS_SIGNAL_NUMBER": "+15550001111", "COMMS_SIGNAL_RECIPIENTS": "+15550002222"}
    )
    assert result == {"applied": ["COMMS_SIGNAL_NUMBER", "COMMS_SIGNAL_RECIPIENTS"]}


@pytest.mark.asyncio
async def test_signal_route_rejects_bad_action():
    result = await server.api_signal_sidecar(_JsonRequest({"action": "dance"}))
    assert result.status_code == 400


def test_apply_config_round_trips_env_file_and_process(tmp_path, monkeypatch):
    env_file = _use_tmp_env(tmp_path, monkeypatch)
    env_file.write_text("# comment\nCOMMS_TELEGRAM_BOT_TOKEN=old\nUNRELATED=keep\n")
    try:
        result = server.apply_config(
            {"COMMS_TELEGRAM_BOT_TOKEN": "new-token", "COMMS_RETENTION_DAYS": "30"}
        )
        assert result == {"applied": ["COMMS_RETENTION_DAYS", "COMMS_TELEGRAM_BOT_TOKEN"]}
        text = env_file.read_text(encoding="utf-8")
        assert "# comment" in text
        assert "UNRELATED=keep" in text
        assert "COMMS_TELEGRAM_BOT_TOKEN=new-token" in text
        assert "COMMS_RETENTION_DAYS=30" in text
        assert os.environ.get("COMMS_TELEGRAM_BOT_TOKEN") == "new-token"
    finally:
        os.environ.pop("COMMS_TELEGRAM_BOT_TOKEN", None)
        os.environ.pop("COMMS_RETENTION_DAYS", None)


class _JsonRequest:
    def __init__(self, body):
        self._body = body

    async def json(self):
        return self._body


def _reset_sidecar():
    whatsapp._set_phase("idle", "")
    whatsapp._sidecar_proc = None


def test_sidecar_port_parsing(monkeypatch):
    monkeypatch.delenv("COMMS_WHATSAPP_SIDECAR_URL", raising=False)
    assert whatsapp.sidecar_port() == 11208
    monkeypatch.setenv("COMMS_WHATSAPP_SIDECAR_URL", "http://127.0.0.1:19999")
    assert whatsapp.sidecar_port() == 19999


def test_sidecar_start_short_circuits_when_listening(monkeypatch):
    _reset_sidecar()
    monkeypatch.setattr(whatsapp, "_probe_running", lambda: True)
    result = whatsapp.start_sidecar()
    assert result["phase"] == "running"
    _reset_sidecar()


def test_sidecar_start_fails_cleanly_without_node(monkeypatch):
    import types

    _reset_sidecar()
    monkeypatch.setattr(whatsapp, "_probe_running", lambda: False)
    monkeypatch.setattr(whatsapp, "shutil", types.SimpleNamespace(which=lambda _: None))
    # run synchronously to avoid thread races in test
    whatsapp._run_sidecar()
    state = whatsapp.sidecar_state()
    assert state["phase"] == "failed"
    assert "node" in state["detail"].lower()
    _reset_sidecar()


def test_sidecar_stop_idle_is_noop():
    _reset_sidecar()
    result = whatsapp.stop_sidecar()
    assert result == {"stopped": False, "phase": "idle"}


@pytest.mark.asyncio
async def test_sidecar_route_rejects_bad_action():
    result = await server.api_whatsapp_sidecar(_JsonRequest({"action": "dance"}))
    assert result.status_code == 400


@pytest.mark.asyncio
async def test_sidecar_route_start_delegates(monkeypatch):
    monkeypatch.setattr(whatsapp, "start_sidecar", lambda: {"started": False, "phase": "running"})
    result = await server.api_whatsapp_sidecar(_JsonRequest({"action": "start"}))
    assert result["success"] is True
    assert result["phase"] == "running"


@pytest.mark.asyncio
async def test_teams_auth_reset_needs_no_network():
    result = await server.api_teams_auth(_JsonRequest({"action": "reset"}))
    assert result["success"] is True
    assert result["status"] == "reset"


@pytest.mark.asyncio
async def test_teams_auth_rejects_bad_action():
    result = await server.api_teams_auth(_JsonRequest({"action": "dance"}))
    assert result.status_code == 400


@pytest.mark.asyncio
async def test_whatsapp_qr_never_returns_raw_qr(monkeypatch):
    async def fake_pairing():
        return {"success": True, "qr": "SECRET-QR", "pairing_code": "111-222"}

    monkeypatch.setattr(whatsapp, "pairing_info", fake_pairing)
    result = await server.api_whatsapp_qr()
    blob = json.dumps(result)
    assert "SECRET-QR" not in blob
    assert result["pairing_code"] == "111-222"
    assert result["qr_present"] is True
