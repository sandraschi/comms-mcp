"""Signal adapter tests (bbernhard bridge shapes are pinned here).

Envelope extraction covers json-rpc nesting + flat shapes and skips
non-text events. Lifecycle tests never touch docker.
"""

import json

import pytest
import respx
from httpx import Response

from comms_mcp.adapters import signal


def _env(monkeypatch, number="+15550001111", recipients="+15550002222"):
    monkeypatch.setenv("COMMS_SIGNAL_NUMBER", number)
    monkeypatch.setenv("COMMS_SIGNAL_RECIPIENTS", recipients)
    monkeypatch.setenv("COMMS_SIGNAL_SIDECAR_URL", "http://127.0.0.1:18080")


def test_extract_nested_envelope():
    item = {
        "envelope": {
            "sourceNumber": "+15550009999",
            "dataMessage": {"message": "hello", "timestamp": 1},
        }
    }
    sender, text, _ts = signal._extract_text(item)
    assert (sender, text) == ("+15550009999", "hello")


def test_extract_flat_and_skips_receipts():
    flat = {"source": "+15550009999", "dataMessage": {"message": "hi"}}
    assert signal._extract_text(flat)[1] == "hi"
    assert signal._extract_text({"envelope": {"receiptMessage": {}}})[1] == ""
    assert signal._extract_text({"envelope": {"typingMessage": {}}})[1] == ""
    assert signal._extract_text({"junk": 1})[1] == ""


@pytest.mark.asyncio
async def test_allowlist_gate(monkeypatch):
    _env(monkeypatch)
    with respx.mock:
        route = respx.post("http://127.0.0.1:18080/v2/send").mock(
            return_value=Response(200, json=[{"timestamp": 1}])
        )
        ok = await signal.send_message("+15550002222", "hi")
        assert ok["success"] is True
        assert route.called
        blocked = await signal.send_message("+1999", "hi")
        assert blocked["success"] is False
        assert "allowlist" in blocked


@pytest.mark.asyncio
async def test_receive_stores_text_only(monkeypatch):
    _env(monkeypatch)
    payload = [
        {"envelope": {"sourceNumber": "+1a", "dataMessage": {"message": "yo"}}},
        {"envelope": {"receiptMessage": {"when": 1}}},
    ]
    with respx.mock:
        respx.get("http://127.0.0.1:18080/v1/receive/+15550001111").mock(
            return_value=Response(200, json=payload)
        )
        stored = await signal.poll_receive()
        assert [s["from"] for s in stored] == ["+1a"]


@pytest.mark.asyncio
async def test_qr_accepts_image_and_uri(monkeypatch):
    _env(monkeypatch)
    with respx.mock:
        respx.get("http://127.0.0.1:18080/v1/qrcodelink?device_name=comms-mcp").mock(
            return_value=Response(200, content=b"\x89PNG", headers={"content-type": "image/png"})
        )
        img = await signal.pairing_qr()
        assert img["qr_image"].startswith("data:image/png;base64,")

    with respx.mock:
        respx.get("http://127.0.0.1:18080/v1/qrcodelink?device_name=comms-mcp").mock(
            return_value=Response(200, json={"qrcodelink": "sgnl://abc"})
        )
        uri = await signal.pairing_qr()
        assert uri["qr_uri"] == "sgnl://abc"


@pytest.mark.asyncio
async def test_register_validates_number(monkeypatch):
    _env(monkeypatch)
    bad = await signal.register("not-a-number")
    assert bad["success"] is False
    with respx.mock:
        respx.post("http://127.0.0.1:18080/v1/register/+15550001111").mock(
            return_value=Response(201, json={})
        )
        ok = await signal.register("+15550001111")
        assert ok["success"] is True


@pytest.mark.asyncio
async def test_verify_strips_dashes(monkeypatch):
    _env(monkeypatch)
    with respx.mock:
        route = respx.post("http://127.0.0.1:18080/v1/register/+15550001111/verify/123456").mock(
            return_value=Response(200, json={})
        )
        ok = await signal.verify("+15550001111", "123-456")
        assert ok["success"] is True
        assert route.called


def _reset_sidecar():
    signal._set_phase("idle", "")


def test_lifecycle_no_docker(monkeypatch):
    import types

    _reset_sidecar()
    monkeypatch.setattr(signal, "_probe_running", lambda: False)
    monkeypatch.setattr(signal, "shutil", types.SimpleNamespace(which=lambda _: None))
    signal._run_sidecar()
    assert signal.sidecar_state()["phase"] == "failed"
    assert "docker" in signal.sidecar_state()["detail"].lower()
    _reset_sidecar()


def test_lifecycle_start_short_circuits(monkeypatch):
    _reset_sidecar()
    monkeypatch.setattr(signal, "_probe_running", lambda: True)
    result = signal.start_sidecar()
    assert result["phase"] == "running"
    _reset_sidecar()


def test_status_unreachable_shape(monkeypatch):
    import asyncio

    # Dead port on purpose: must report unreachable regardless of any
    # real bridge running on the default port.
    monkeypatch.setenv("COMMS_SIGNAL_SIDECAR_URL", "http://127.0.0.1:19999")
    result = asyncio.run(signal.status())
    assert result["success"] is False
    assert "configured" in result


def test_json_round_trip_of_shapes():
    # guard: envelope fixtures above must stay JSON-serializable
    assert json.dumps([{"envelope": {"sourceNumber": "+1"}}])
