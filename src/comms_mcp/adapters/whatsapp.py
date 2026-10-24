"""WhatsApp adapter (v0.2) - proxies to the Node baileys sidecar (text only).

The sidecar (wa-sidecar/, Node) links the WhatsApp number as a companion
device; this module is a thin REST client: status / qr (pairing) / send.
Send is allowlist-gated (COMMS_WHATSAPP_ALLOW_NUMBERS, E.164). Inbound
arrives via POST /api/v1/inbound/wa (sidecar -> comms-mcp webhook).

Text-only scope, sidecar-bounded: the sidecar exposes /health, /qr and
/send only - no chat list, history, or group management. History for
WhatsApp = the local inbound store. Pairing state is surfaced through
status() so MCP clients never need the sidecar REST directly.

Nobody hand-starts the sidecar: start_sidecar() spawns it (npm install on
first run) as a backend-owned child process; stop_sidecar() kills it.
sidecar_state() reports the lifecycle phase for the Settings UI.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from ..config import get_settings

log = logging.getLogger("comms_mcp.whatsapp")

TIMEOUT_S = 15

# Lifecycle phases: idle -> installing -> starting -> running (-> idle),
# or -> failed with detail. Guarded by _sidecar_lock; the worker thread owns
# transitions after start, stop() owns the way back to idle.
_sidecar_lock = threading.Lock()
_sidecar: dict[str, Any] = {"phase": "idle", "detail": "", "pid": None}
_sidecar_proc: Any = None


def _sidecar_dir() -> Path:
    return Path(__file__).resolve().parent.parent.parent.parent / "wa-sidecar"


def sidecar_port() -> int:
    """Port from COMMS_WHATSAPP_SIDECAR_URL (default 11208)."""
    try:
        port = urlparse(get_settings().whatsapp_sidecar_url).port
        return port or 11208
    except Exception:
        return 11208


def sidecar_state() -> dict[str, Any]:
    with _sidecar_lock:
        return dict(_sidecar)


def _set_phase(phase: str, detail: str = "", pid: int | None = None) -> None:
    with _sidecar_lock:
        _sidecar["phase"] = phase
        _sidecar["detail"] = detail
        _sidecar["pid"] = pid


def _probe_running() -> bool:
    try:
        import urllib.request

        with urllib.request.urlopen(f"{_base()}/health", timeout=3) as r:
            return r.status == 200
    except Exception:
        return False


def start_sidecar() -> dict[str, Any]:
    """Spawn the sidecar in a background thread (idempotent while busy).

    Returns immediately: {"started": true, "phase": ...}. Poll
    sidecar_state() (or the channels endpoint) for installing/starting/
    running/failed. Never raises.
    """
    with _sidecar_lock:
        phase = _sidecar["phase"]
    if phase in ("installing", "starting"):
        return {"started": False, "phase": phase, "note": "already starting"}
    if phase == "running" or _probe_running():
        _set_phase("running", "already listening")
        return {"started": False, "phase": "running", "note": "already listening"}
    thread = threading.Thread(target=_run_sidecar, daemon=True, name="wa-sidecar-boot")
    thread.start()
    return {"started": True, "phase": "installing"}


def stop_sidecar() -> dict[str, Any]:
    """Terminate the backend-owned sidecar child (no-op when idle)."""
    global _sidecar_proc
    with _sidecar_lock:
        proc = _sidecar_proc
        _sidecar_proc = None
    if proc is None:
        _set_phase("idle", "not running")
        return {"stopped": False, "phase": "idle"}
    try:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:
            proc.kill()
    except Exception as exc:
        log.warning("sidecar stop failed: %s", exc)
    _set_phase("idle", "stopped by user")
    return {"stopped": True, "phase": "idle"}


def _run_sidecar() -> None:
    global _sidecar_proc
    node = shutil.which("node")
    if not node:
        _set_phase(
            "failed",
            "node not found — install Node.js LTS (https://nodejs.org), then Start again",
        )
        return
    workdir = _sidecar_dir()
    if not (workdir / "package.json").is_file():
        _set_phase("failed", f"wa-sidecar missing at {workdir}")
        return
    _set_phase("installing", "npm install (first run only)")
    if not (workdir / "node_modules").is_dir():
        try:
            install = subprocess.run(
                ["npm", "install", "--no-audit", "--no-fund"],
                cwd=str(workdir),
                capture_output=True,
                text=True,
                timeout=600,
            )
        except Exception as exc:
            _set_phase("failed", f"npm install crashed: {exc}")
            return
        if install.returncode != 0:
            tail = (install.stderr or install.stdout or "")[-500:]
            _set_phase("failed", f"npm install failed: {tail}")
            return
    _set_phase("starting", "booting baileys, waiting for /health")
    settings = get_settings()
    # Inherit the full parent env (Node on Windows needs SYSTEMROOT etc.)
    # and override only the sidecar keys.
    env = dict(os.environ)
    env.update(
        {
            "WA_PORT": str(sidecar_port()),
            "COMMS_INBOUND_WEBHOOK": f"http://127.0.0.1:{settings.port}/api/v1/inbound/wa",
            "COMMS_INBOUND_SECRET": settings.inbound_secret,
        }
    )
    try:
        proc = subprocess.Popen(
            [node, "index.js"],
            cwd=str(workdir),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as exc:
        _set_phase("failed", f"spawn failed: {exc}")
        return
    with _sidecar_lock:
        _sidecar_proc = proc
        _sidecar["pid"] = proc.pid
    for _ in range(40):
        if proc.poll() is not None:
            _set_phase(
                "failed",
                f"sidecar exited during boot (code {proc.returncode}) — see wa-sidecar logs",
            )
            with _sidecar_lock:
                _sidecar_proc = None
            return
        if _probe_running():
            _set_phase(
                "running",
                f"listening (pid {proc.pid}) — pair from Settings",
                pid=proc.pid,
            )
            return
        time.sleep(3)
    _set_phase("failed", "boot timed out waiting for /health")


def _base() -> str:
    return get_settings().whatsapp_sidecar_url.rstrip("/")


def _configured() -> bool:
    return bool(get_settings().whatsapp_sidecar_url)


def allow_numbers() -> list[str]:
    return [n.strip() for n in get_settings().whatsapp_allow_numbers.split(",") if n.strip()]


async def status() -> dict[str, Any]:
    if not _configured():
        return {
            "success": False,
            "configured": False,
            "error": "COMMS_WHATSAPP_SIDECAR_URL not set",
        }
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
            r = await client.get(f"{_base()}/health")
            r.raise_for_status()
            data = r.json()
        out: dict[str, Any] = {"success": True, "configured": True, **data}
        if not data.get("connected"):
            pair = await pairing_info()
            if pair.get("success"):
                out["qr"] = pair.get("qr")
                out["pairing_code"] = pair.get("pairing_code")
                out["pairing_hint"] = (
                    "Scan the QR with WhatsApp on the phone (Linked devices), "
                    "or use the pairing code, then call status again."
                )
        return out
    except Exception as exc:
        return {"success": False, "configured": True, "error": str(exc)}


async def pairing_info() -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
            r = await client.get(f"{_base()}/qr")
            r.raise_for_status()
            data = r.json()
        return {"success": True, "qr": data.get("qr"), "pairing_code": data.get("pairing_code")}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


async def send_message(to_number: str, text: str) -> dict[str, Any]:
    if not _configured():
        return {"success": False, "error": "COMMS_WHATSAPP_SIDECAR_URL not set"}
    allow = allow_numbers()
    if allow and to_number not in allow:
        return {
            "success": False,
            "error": f"number {to_number} not in allowlist",
            "allowlist": allow,
        }
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
            r = await client.post(f"{_base()}/send", json={"to": to_number, "text": text})
            if r.status_code == 503:
                return {"success": False, "error": r.json().get("error", "sidecar not connected")}
            r.raise_for_status()
            return {"success": True, **r.json()}
    except Exception as exc:
        return {"success": False, "error": str(exc)}
