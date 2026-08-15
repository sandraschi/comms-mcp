"""WhatsApp adapter (v0.2) - proxies to the Node baileys sidecar.

The sidecar (wa-sidecar/, Node) links the WhatsApp number as a companion
device; this module is a thin REST client: status / qr (pairing) / send.
Send is allowlist-gated (COMMS_WHATSAPP_ALLOW_NUMBERS, E.164). Inbound
arrives via POST /api/v1/inbound/wa (sidecar -> comms-mcp webhook).
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from ..config import get_settings

log = logging.getLogger("comms_mcp.whatsapp")

TIMEOUT_S = 15


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
        return {"success": True, "configured": True, **data}
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
