"""Signal adapter (v0.7) - bbernhard signal-cli-rest-api sidecar (text only).

Signal has NO official bot API, so everything here rides the unofficial
community bridge (Docker image bbernhard/signal-cli-rest-api). That is the
entire risk profile of this lane: upstream Signal changes can break the
bridge, and automation must run on a DEDICATED number — never a personal
primary, or a ban costs the account.

Two ways onto the network (both in the Settings UI, no terminal):
  1. Link as a secondary device: GET /v1/qrcodelink -> scan with the phone.
  2. Register a dedicated number: POST /v1/register + verify (SMS/voice).

Runtime: text send/receive only. Receive is polled (GET /v1/receive) on
read_recent — the bridge has no push webhook. Inbound is sanitized and
stored with the 7-day TTL like every other lane.
"""

from __future__ import annotations

import base64
import logging
import shutil
import subprocess
import threading
import time
from typing import Any
from urllib.parse import urlparse

import httpx

from ..config import get_settings
from ..outbox import sqlite as store
from ..sanitize import sanitize_inbound

log = logging.getLogger("comms_mcp.signal")

TIMEOUT_S = 20
CONTAINER_NAME = "comms-signal-sidecar"
IMAGE = "bbernhard/signal-cli-rest-api:latest"
VOLUME = "comms-signal-data"

_sidecar_lock = threading.Lock()
_sidecar: dict[str, Any] = {"phase": "idle", "detail": "", "pid": None}


def _base() -> str:
    return get_settings().signal_sidecar_url.rstrip("/")


def _number() -> str:
    return get_settings().signal_number.strip()


def allow_recipients() -> list[str]:
    return [n.strip() for n in get_settings().signal_recipients.split(",") if n.strip()]


def sidecar_port() -> int:
    try:
        port = urlparse(get_settings().signal_sidecar_url).port
        return port or 18080
    except Exception:
        return 18080


def sidecar_state() -> dict[str, Any]:
    with _sidecar_lock:
        return dict(_sidecar)


def _set_phase(phase: str, detail: str = "") -> None:
    with _sidecar_lock:
        _sidecar["phase"] = phase
        _sidecar["detail"] = detail


def _probe_running() -> bool:
    import urllib.request

    try:
        with urllib.request.urlopen(f"{_base()}/v1/health", timeout=3) as r:
            return r.status == 200
    except Exception:
        return False


async def status() -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
            r = await client.get(f"{_base()}/v1/about")
            r.raise_for_status()
            about = r.json()
    except Exception as exc:
        return {"success": False, "configured": False, "error": f"sidecar unreachable: {exc}"}
    number = _number()
    accounts: list[str] = []
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
            r = await client.get(f"{_base()}/v1/accounts")
            if r.status_code == 200:
                data = r.json()
                accounts = data if isinstance(data, list) else data.get("accounts", [])
    except Exception as exc:
        log.warning("signal accounts probe failed: %s", exc)
    linked = (not number) or (number in accounts) or (not accounts)
    return {
        "success": True,
        "configured": True,
        "versions": about.get("versions") if isinstance(about, dict) else None,
        "number": number or "(not set)",
        "accounts": accounts,
        "linked": bool(linked),
        "detail": (
            "sidecar up; number ready" if linked else f"{number} not linked — pair from Settings"
        ),
    }


def _extract_text(item: dict[str, Any]) -> tuple[str, str, str]:
    """Return (sender, text, timestamp) or empties for non-text events.

    Handles json-rpc envelope nesting (item['envelope']) and flat shapes;
    skips receipts, typing indicators, attachments, and stories.
    """
    env = item.get("envelope") if isinstance(item.get("envelope"), dict) else item
    if not isinstance(env, dict):
        return "", "", ""
    data = env.get("dataMessage")
    if not isinstance(data, dict):
        return "", "", ""
    text = str(data.get("message") or "")
    if not text.strip():
        return "", "", ""
    sender = str(env.get("sourceNumber") or env.get("source") or env.get("sourceUuid") or "?")
    ts = str(data.get("timestamp") or env.get("timestamp") or "")
    return sender, text, ts


async def poll_receive() -> list[dict[str, Any]]:
    """Long-poll-less fetch: GET /v1/receive, store new text messages."""
    number = _number()
    if not number:
        return []
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_S + 10) as client:
            r = await client.get(f"{_base()}/v1/receive/{number}")
            r.raise_for_status()
            items = r.json()
    except Exception as exc:
        log.warning("signal receive failed: %s", exc)
        return []
    if not isinstance(items, list):
        return []
    stored: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        sender, text, _ts = _extract_text(item)
        if not text:
            continue
        safe = sanitize_inbound(text)
        store.store_inbound("signal", sender, sender, safe)
        stored.append({"from": sender})
    return stored


async def send_message(to_number: str, text: str) -> dict[str, Any]:
    number = _number()
    if not number:
        return {"success": False, "error": "COMMS_SIGNAL_NUMBER not set"}
    allow = allow_recipients()
    if allow and to_number not in allow:
        return {
            "success": False,
            "error": f"number {to_number} not in allowlist",
            "allowlist": allow,
        }
    body = sanitize_inbound(text)
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
            r = await client.post(
                f"{_base()}/v2/send",
                json={"number": number, "recipients": [to_number], "message": body[:4000]},
            )
            r.raise_for_status()
            return {"success": True, "result": r.json()}
    except httpx.HTTPStatusError as exc:
        return {
            "success": False,
            "error": f"signal {exc.response.status_code}: {exc.response.text[:300]}",
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


async def pairing_qr(device_name: str = "comms-mcp") -> dict[str, Any]:
    """Link-as-device QR. Returns qr_image (data URL) and/or qr_uri (sgnl://).

    Shape-agnostic: the bridge has returned PNG bytes, JSON blobs, and raw
    URI text across versions — accept all three.
    """
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
            r = await client.get(f"{_base()}/v1/qrcodelink?device-name={device_name}")
            if r.status_code != 200:
                return {"success": False, "error": f"qrcodelink HTTP {r.status_code}"}
            ctype = r.headers.get("content-type", "")
            if ctype.startswith("image/"):
                b64 = base64.b64encode(r.content).decode("ascii")
                return {"success": True, "qr_image": f"data:{ctype.split(';')[0]};base64,{b64}"}
            try:
                data = r.json()
            except Exception:
                data = None
            if isinstance(data, dict):
                for key in ("qrcodelink", "uri", "link", "image", "data", "qr"):
                    val = data.get(key)
                    if isinstance(val, str) and val:
                        if val.startswith("data:image"):
                            return {"success": True, "qr_image": val}
                        if val.startswith("sgnl://"):
                            return {"success": True, "qr_uri": val}
            text = r.text.strip().strip('"')
            if text.startswith("sgnl://"):
                return {"success": True, "qr_uri": text}
            # Fallback: raw endpoint returns the plain URI.
            r2 = await client.get(f"{_base()}/v1/qrcodelink/raw?device-name={device_name}")
            if r2.status_code == 200 and r2.text.strip().startswith("sgnl://"):
                return {"success": True, "qr_uri": r2.text.strip()}
            return {"success": False, "error": "unrecognized qrcodelink shape"}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


async def register(number: str, voice: bool = False) -> dict[str, Any]:
    if not number.strip().startswith("+"):
        return {"success": False, "error": "number must be E.164 (+...)"}
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
            r = await client.post(
                f"{_base()}/v1/register/{number.strip()}",
                json={"use_voice": bool(voice)},
            )
            if r.status_code in (200, 201):
                return {"success": True, "message": "code sent — verify from Settings"}
            return {"success": False, "error": f"register HTTP {r.status_code}: {r.text[:300]}"}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


async def verify(number: str, token: str, pin: str = "") -> dict[str, Any]:
    token = token.strip().replace("-", "").replace(" ", "")
    if not token:
        return {"success": False, "error": "token required"}
    payload: dict[str, Any] = {}
    if pin.strip():
        payload["pin"] = pin.strip()
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
            r = await client.post(
                f"{_base()}/v1/register/{number.strip()}/verify/{token}", json=payload
            )
            if r.status_code in (200, 201):
                return {"success": True, "message": "number verified"}
            return {"success": False, "error": f"verify HTTP {r.status_code}: {r.text[:300]}"}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def start_sidecar() -> dict[str, Any]:
    """Run the bridge container (idempotent). Returns immediately-ish.

    Pulls bbernhard/signal-cli-rest-api on first run (slow), then starts the
    container with a persistent data volume. Poll sidecar_state().
    """
    with _sidecar_lock:
        phase = _sidecar["phase"]
    if phase in ("installing", "starting"):
        return {"started": False, "phase": phase, "note": "already starting"}
    if phase == "running" or _probe_running():
        _set_phase("running", "already listening")
        return {"started": False, "phase": "running", "note": "already listening"}
    thread = threading.Thread(target=_run_sidecar, daemon=True, name="signal-sidecar-boot")
    thread.start()
    return {"started": True, "phase": "installing"}


def stop_sidecar() -> dict[str, Any]:
    try:
        subprocess.run(
            ["docker", "stop", CONTAINER_NAME],
            capture_output=True,
            text=True,
            timeout=60,
        )
        subprocess.run(
            ["docker", "rm", CONTAINER_NAME],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except Exception as exc:
        return {"started": False, "phase": "idle", "note": f"stop failed: {exc}", "stopped": False}
    _set_phase("idle", "stopped by user")
    return {"stopped": True, "phase": "idle"}


def _run_sidecar() -> None:
    if not shutil.which("docker"):
        _set_phase("failed", "docker not found — install Docker Desktop, then Start again")
        return
    _set_phase("installing", "pulling signal-cli-rest-api image (first run, may take minutes)")
    try:
        pull = subprocess.run(
            ["docker", "pull", IMAGE],
            capture_output=True,
            text=True,
            timeout=1200,
        )
    except Exception as exc:
        _set_phase("failed", f"docker pull crashed: {exc}")
        return
    if pull.returncode != 0:
        tail = (pull.stderr or pull.stdout or "")[-500:]
        _set_phase("failed", f"docker pull failed: {tail}")
        return
    _set_phase("starting", "creating container, waiting for /v1/health")
    port = sidecar_port()
    try:
        subprocess.run(["docker", "rm", "-f", CONTAINER_NAME], capture_output=True, timeout=60)
        run = subprocess.run(
            [
                "docker",
                "run",
                "-d",
                "--name",
                CONTAINER_NAME,
                "--restart",
                "unless-stopped",
                "-p",
                f"127.0.0.1:{port}:8080",
                "-v",
                f"{VOLUME}:/home/.local/share/signal-cli",
                IMAGE,
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except Exception as exc:
        _set_phase("failed", f"docker run crashed: {exc}")
        return
    if run.returncode != 0:
        tail = (run.stderr or run.stdout or "")[-500:]
        _set_phase("failed", f"docker run failed: {tail}")
        return
    for _ in range(40):
        if _probe_running():
            _set_phase("running", "listening — link or register from Settings")
            return
        time.sleep(3)
    _set_phase("failed", "boot timed out waiting for /v1/health")
