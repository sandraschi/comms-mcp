"""Teams adapter (v0.4) - Microsoft Graph, delegated device-code flow.

Sends chat messages as the signed-in user through the Graph API using the
same Azure app registration as email-mcp's EMAIL_MCP_OAUTH_CLIENT_ID (no Bot
Framework / bot-registration rigmarole). Auth is the OAuth2 device-code flow:

    1. comms_ops(operation="auth", channel="teams")
    2. enter the returned code at microsoft.com/devicelogin
    3. call comms_ops(operation="auth", channel="teams") again to poll/confirm

The token needs the delegated Chat.ReadWrite scope. Send is allowlist-gated
(COMMS_TEAMS_RECIPIENTS: name=email or name=19:chatId). The token store lives
at COMMS_TEAMS_TOKEN_FILE (default data/teams_oauth.json), not committed.

Caveat: Graph Teams chat APIs require an organizational (work/school)
identity; personal consumer accounts have limited /chats support. Configure a
target that has a Teams identity for reliable 1:1 chat.
"""

from __future__ import annotations

import base64
import json
import logging
import time
from typing import Any
from urllib.parse import quote

import httpx

from ..config import get_settings

log = logging.getLogger("comms_mcp.teams")

AUTHORITY = "https://login.microsoftonline.com/common/oauth2/v2.0"
DEVICE_CODE_URL = f"{AUTHORITY}/devicecode"
TOKEN_URL = f"{AUTHORITY}/token"
SCOPE = "openid profile email https://graph.microsoft.com/Chat.ReadWrite offline_access"

TIMEOUT_S = 20

_pending_flow: dict[str, Any] | None = None


def _cfg():
    return get_settings()


def configured() -> bool:
    return bool(_cfg().graph_client_id)


def client_id() -> str:
    return _cfg().graph_client_id


def allow_list() -> list[str]:
    return list(_cfg_recipients().keys())


def _cfg_recipients() -> dict[str, str]:
    from ..config import teams_allowlist

    return teams_allowlist()


# ── token store ───────────────────────────────────────────────────────────


def _token_path() -> Any:
    return _cfg().teams_token_file


def _load() -> dict[str, Any]:
    p = _token_path()
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception as exc:
            log.warning("teams token store unreadable: %s", exc)
    return {}


def _save(data: dict[str, Any]) -> None:
    p = _token_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _access_token() -> str | None:
    data = _load()
    if not data:
        return None
    if time.time() < float(data.get("expires_at", 0)) - 120:
        return str(data["access_token"])
    rt = data.get("refresh_token")
    cid = client_id()
    if not rt or not cid:
        return None
    try:
        r = httpx.post(
            TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "client_id": cid,
                "refresh_token": rt,
                "scope": SCOPE,
            },
            timeout=TIMEOUT_S,
        )
        r.raise_for_status()
        tok = r.json()
        data["access_token"] = tok["access_token"]
        if tok.get("refresh_token"):
            data["refresh_token"] = tok["refresh_token"]
        data["expires_at"] = time.time() + int(tok.get("expires_in", 3600))
        _save(data)
        return str(tok["access_token"])
    except Exception as exc:
        log.warning("teams token refresh failed: %s", exc)
        return None


# ── device-code auth ───────────────────────────────────────────────────────


def auth_status() -> dict[str, Any]:
    """Start a device flow if none is pending, otherwise poll the pending one."""
    global _pending_flow
    cid = client_id()
    if not cid:
        return {"success": False, "error": "COMMS_GRAPH_CLIENT_ID not configured"}
    if _pending_flow and _pending_flow["expires_at"] > time.time():
        return _poll(_pending_flow)
    try:
        r = httpx.post(DEVICE_CODE_URL, data={"client_id": cid, "scope": SCOPE}, timeout=TIMEOUT_S)
        r.raise_for_status()
        d = r.json()
    except Exception as exc:
        return {"success": False, "error": f"device code request failed: {exc}"}
    _pending_flow = {
        "device_code": d["device_code"],
        "user_code": d["user_code"],
        "verification_uri": d.get("verification_uri", "https://microsoft.com/devicelogin"),
        "expires_at": time.time() + int(d.get("expires_in", 900)),
        "interval": int(d.get("interval", 5)),
    }
    return {
        "success": True,
        "needs_auth": True,
        "user_code": d["user_code"],
        "verification_uri": _pending_flow["verification_uri"],
        "message": (
            f"Go to {_pending_flow['verification_uri']} and enter code {d['user_code']}, "
            "then call comms_ops(operation='auth', channel='teams') again to confirm."
        ),
    }


def _poll(flow: dict[str, Any]) -> dict[str, Any]:
    global _pending_flow
    try:
        r = httpx.post(
            TOKEN_URL,
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "client_id": client_id(),
                "device_code": flow["device_code"],
                "scope": SCOPE,
            },
            timeout=TIMEOUT_S,
        )
    except Exception as exc:
        return {"success": False, "status": "error", "error": f"poll failed: {exc}"}
    if r.status_code == 400:
        err = r.json().get("error")
        if err == "authorization_pending":
            return {
                "success": True,
                "status": "pending",
                "message": "Waiting for you to enter the code.",
            }
        if err in ("authorization_declined", "expired_token", "bad_verification_code"):
            _pending_flow = None
            return {"success": False, "status": "error", "error": err}
        return {"success": False, "status": "error", "error": err}
    r.raise_for_status()
    d = r.json()
    account = _account_from_id_token(d.get("id_token", "")) or _account_from_id_token(
        d.get("access_token", "")
    )
    _save(
        {
            "account": account or "unknown",
            "access_token": d["access_token"],
            "refresh_token": d.get("refresh_token", ""),
            "expires_at": time.time() + int(d.get("expires_in", 3600)),
        }
    )
    _pending_flow = None
    log.info("teams oauth authorized as %s", account)
    return {"success": True, "status": "authorized", "account": account}


def _account_from_id_token(id_token: str) -> str:
    try:
        payload_b64 = id_token.split(".")[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload_b64))
        for key in ("preferred_username", "email", "upn"):
            if claims.get(key):
                return str(claims[key])
    except Exception:
        pass
    return ""


# ── status / send ──────────────────────────────────────────────────────────


async def status() -> dict[str, Any]:
    if not configured():
        return {"success": False, "configured": False, "error": "COMMS_GRAPH_CLIENT_ID not set"}
    token = _access_token()
    if not token:
        return {
            "success": False,
            "configured": True,
            "needs_auth": True,
            "error": "not authorized - run comms_ops(operation='auth', channel='teams')",
            "allowlist": allow_list(),
        }
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
            r = await client.get(
                f"{_cfg().teams_graph_base}/me",
                headers={"Authorization": f"Bearer {token}"},
            )
            r.raise_for_status()
            me = r.json()
        return {
            "success": True,
            "configured": True,
            "account": me.get("userPrincipalName") or me.get("mail") or me.get("displayName"),
            "allowlist": allow_list(),
        }
    except Exception as exc:
        return {"success": False, "configured": True, "error": str(exc)}


async def send_message(recipient: str, text: str) -> dict[str, Any]:
    if not configured():
        return {"success": False, "error": "COMMS_GRAPH_CLIENT_ID not set"}
    allow = allow_list()
    if allow and recipient not in allow:
        return {
            "success": False,
            "error": f"recipient {recipient} not in allowlist",
            "allowlist": allow,
        }
    token = _access_token()
    if not token:
        return {
            "success": False,
            "error": "not authorized - run comms_ops(operation='auth', channel='teams')",
        }
    target = _cfg_recipients().get(recipient, recipient)
    chat_id = await _resolve_chat_id(token, target)
    if not chat_id:
        return {"success": False, "error": f"could not resolve a Teams chat for {target}"}
    payload = {"body": {"contentType": "text", "content": text[:28000]}}
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
            r = await client.post(
                f"{_cfg().teams_graph_base}/chats/{quote(chat_id, safe='')}/messages",
                json=payload,
                headers={"Authorization": f"Bearer {token}"},
            )
            r.raise_for_status()
            msg = r.json()
        return {"success": True, "chat_id": chat_id, "message_id": msg.get("id")}
    except httpx.HTTPStatusError as exc:
        return {
            "success": False,
            "error": f"graph {exc.response.status_code}: {exc.response.text[:300]}",
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


async def _resolve_chat_id(token: str, target: str) -> str | None:
    """Resolve a recipient (chat id, user id, or email) to a Teams chat id."""
    if target.startswith("19:"):
        return target
    user_id = await _resolve_user_id(token, target)
    if user_id:
        created = await _create_one_on_one(token, user_id)
        if created:
            return created
        found = await _find_existing_chat(token, user_id)
        if found:
            return found
    return None


async def _resolve_user_id(token: str, target: str) -> str | None:
    # Already a user id (UUID)?
    if len(target) == 36 and target.count("-") == 4:
        return target
    # Resolve email / UPN -> user
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
            r = await client.get(
                f"{_cfg().teams_graph_base}/users/{quote(target, safe='')}",
                headers={"Authorization": f"Bearer {token}"},
            )
            if r.status_code == 200:
                return r.json().get("id")
    except Exception as exc:
        log.warning("teams user resolve failed: %s", exc)
    return None


async def _create_one_on_one(token: str, user_id: str) -> str | None:
    body = {
        "chatType": "oneOnOne",
        "members": [
            {
                "@odata.type": "#microsoft.graph.aadUserConversationMember",
                "roles": ["owner"],
                "user@odata.bind": f"https://graph.microsoft.com/v1.0/users('{user_id}')",
            }
        ],
    }
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
            r = await client.post(
                f"{_cfg().teams_graph_base}/chats",
                json=body,
                headers={"Authorization": f"Bearer {token}"},
            )
            if r.status_code in (200, 201):
                return r.json().get("id")
            log.warning("teams 1:1 chat create status %s: %s", r.status_code, r.text[:200])
    except Exception as exc:
        log.warning("teams 1:1 chat create failed: %s", exc)
    return None


async def _find_existing_chat(token: str, user_id: str) -> str | None:
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
            r = await client.get(
                f"{_cfg().teams_graph_base}/me/chats?$expand=members&$top=50",
                headers={"Authorization": f"Bearer {token}"},
            )
            r.raise_for_status()
            for chat in r.json().get("value", []):
                for member in chat.get("members", []):
                    if str(member.get("id", "")).lower() == user_id.lower():
                        return chat.get("id")
    except Exception as exc:
        log.warning("teams chat scan failed: %s", exc)
    return None
