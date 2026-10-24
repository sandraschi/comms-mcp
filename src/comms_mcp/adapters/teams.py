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

Read is text-only: list_chats / chat_messages return plain text
(HTML bodies are stripped, no cards/files). Replies use replyToId.
Edits/deletes map to PATCH/DELETE on the chat message.

Channels: team/channel targets use the address form
"team/{teamId}/channel/{channelId}" (or a bare channel id, resolved by
scanning joined teams). Channel reads need ChannelMessage.Read.All
(often admin-consented); the 403 names the missing scope.

Caveat: Graph Teams chat APIs require an organizational (work/school)
identity; personal consumer accounts have limited /chats support. Configure a
target that has a Teams identity for reliable 1:1 chat.
"""

from __future__ import annotations

import asyncio
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
    token = await asyncio.to_thread(_access_token)
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


async def send_message(recipient: str, text: str, reply_to: str | None = None) -> dict[str, Any]:
    if not configured():
        return {"success": False, "error": "COMMS_GRAPH_CLIENT_ID not set"}
    allow = allow_list()
    if allow and recipient not in allow:
        return {
            "success": False,
            "error": f"recipient {recipient} not in allowlist",
            "allowlist": allow,
        }
    token = await asyncio.to_thread(_access_token)
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
            if reply_to:
                r = await client.post(
                    f"{_cfg().teams_graph_base}/chats/{quote(chat_id, safe='')}"
                    f"/messages/{quote(reply_to, safe='')}/replies",
                    json=payload,
                    headers={"Authorization": f"Bearer {token}"},
                )
            else:
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


def _strip_html(content: str) -> str:
    """Graph returns message bodies as HTML - reduce to plain text."""
    import html as _html
    import re as _re

    text = _re.sub(r"<[^>]+>", " ", content or "")
    text = _html.unescape(text)
    return _re.sub(r"\s+", " ", text).strip()


async def list_chats() -> dict[str, Any]:
    """Live chat list via GET /me/chats (text scope, members expanded)."""
    if not configured():
        return {"success": False, "configured": False, "error": "COMMS_GRAPH_CLIENT_ID not set"}
    token = await asyncio.to_thread(_access_token)
    if not token:
        return {
            "success": False,
            "configured": True,
            "needs_auth": True,
            "error": "not authorized - run comms_ops(operation='auth', channel='teams')",
        }
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
            r = await client.get(
                f"{_cfg().teams_graph_base}/me/chats?$expand=members&$top=50",
                headers={"Authorization": f"Bearer {token}"},
            )
            r.raise_for_status()
            chats = [
                {
                    "id": c.get("id"),
                    "topic": c.get("topic") or c.get("chatType"),
                    "chatType": c.get("chatType"),
                }
                for c in r.json().get("value", [])
            ]
        return {"success": True, "chats": chats, "allowlist": allow_list()}
    except Exception as exc:
        return {"success": False, "error": str(exc), "allowlist": allow_list()}


async def chat_messages(chat_id: str, limit: int = 20) -> dict[str, Any]:
    """Recent messages via GET /chats/{id}/messages (text only)."""
    if not configured():
        return {"success": False, "error": "COMMS_GRAPH_CLIENT_ID not set"}
    token = await asyncio.to_thread(_access_token)
    if not token:
        return {
            "success": False,
            "error": "not authorized - run comms_ops(operation='auth', channel='teams')",
        }
    try:
        n = max(1, min(int(limit), 100))
        async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
            r = await client.get(
                f"{_cfg().teams_graph_base}/chats/{quote(chat_id, safe='')}/messages?$top={n}",
                headers={"Authorization": f"Bearer {token}"},
            )
            r.raise_for_status()
            messages = [
                {
                    "id": m.get("id"),
                    "from": ((m.get("from") or {}).get("user") or {}).get("displayName"),
                    "text": _strip_html((m.get("body") or {}).get("content", ""))[:2000],
                    "createdDateTime": m.get("createdDateTime"),
                }
                for m in r.json().get("value", [])
            ]
        return {"success": True, "chat_id": chat_id, "messages": messages}
    except httpx.HTTPStatusError as exc:
        return {
            "success": False,
            "error": f"graph {exc.response.status_code}: {exc.response.text[:300]}",
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def is_channel_id(ref: str) -> bool:
    """Channel message ids live under @thread.tacv2; chat ids do not."""
    return "@thread.tacv2" in (ref or "")


def parse_channel_ref(ref: str) -> tuple[str | None, str | None]:
    """Split "team/{teamId}/channel/{channelId}" or a bare channel id.

    Returns (team_id, channel_id); team_id None means "resolve by scan".
    Returns (None, None) when ref is not a channel address at all.
    """
    text = (ref or "").strip()
    if text.startswith("team/") and "/channel/" in text:
        try:
            _, team_part = text.split("team/", 1)
            team_id, channel_id = team_part.split("/channel/", 1)
            if team_id and channel_id:
                return team_id, channel_id
        except ValueError:
            pass
        return None, None
    if is_channel_id(text):
        return None, text
    return None, None


async def _authed_token() -> str | None:
    return await asyncio.to_thread(_access_token)


async def list_teams() -> dict[str, Any]:
    """Joined teams via GET /me/joinedTeams (needs Team.ReadBasic.All)."""
    if not configured():
        return {"success": False, "configured": False, "error": "COMMS_GRAPH_CLIENT_ID not set"}
    token = await _authed_token()
    if not token:
        return {
            "success": False,
            "configured": True,
            "needs_auth": True,
            "error": "not authorized - run comms_ops(operation='auth', channel='teams')",
        }
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
            r = await client.get(
                f"{_cfg().teams_graph_base}/me/joinedTeams",
                headers={"Authorization": f"Bearer {token}"},
            )
            r.raise_for_status()
            teams = [
                {"id": t.get("id"), "displayName": t.get("displayName")}
                for t in r.json().get("value", [])
            ]
        return {"success": True, "teams": teams}
    except httpx.HTTPStatusError as exc:
        return {
            "success": False,
            "error": f"graph {exc.response.status_code}: {exc.response.text[:300]}",
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


async def team_channels(team_id: str) -> dict[str, Any]:
    """Channels of one team via GET /teams/{id}/channels."""
    if not configured():
        return {"success": False, "error": "COMMS_GRAPH_CLIENT_ID not set"}
    token = await _authed_token()
    if not token:
        return {
            "success": False,
            "error": "not authorized - run comms_ops(operation='auth', channel='teams')",
        }
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
            r = await client.get(
                f"{_cfg().teams_graph_base}/teams/{quote(team_id, safe='')}/channels",
                headers={"Authorization": f"Bearer {token}"},
            )
            r.raise_for_status()
            channels = [
                {"id": c.get("id"), "displayName": c.get("displayName")}
                for c in r.json().get("value", [])
            ]
        return {"success": True, "team_id": team_id, "channels": channels}
    except httpx.HTTPStatusError as exc:
        return {
            "success": False,
            "error": f"graph {exc.response.status_code}: {exc.response.text[:300]}",
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


async def list_teams_with_channels() -> dict[str, Any]:
    """Joined teams, each with its channel list (best effort per team)."""
    teams_res = await list_teams()
    if not teams_res.get("success"):
        return teams_res
    out: list[dict[str, Any]] = []
    for team in teams_res.get("teams", []):
        channels_res = await team_channels(str(team.get("id", "")))
        out.append(
            {
                "id": team.get("id"),
                "displayName": team.get("displayName"),
                "channels": channels_res.get("channels", []),
            }
        )
    return {"success": True, "teams": out}


async def _resolve_team_for_channel(token: str, channel_id: str) -> str | None:
    """Find the parent team of a bare channel id by scanning joined teams."""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
            r = await client.get(
                f"{_cfg().teams_graph_base}/me/joinedTeams?$select=id",
                headers={"Authorization": f"Bearer {token}"},
            )
            r.raise_for_status()
            team_ids = [t.get("id") for t in r.json().get("value", []) if t.get("id")]
        async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
            for team_id in team_ids:
                try:
                    r = await client.get(
                        f"{_cfg().teams_graph_base}/teams/{quote(str(team_id), safe='')}"
                        "/channels?$select=id",
                        headers={"Authorization": f"Bearer {token}"},
                    )
                    if r.status_code != 200:
                        continue
                    if any(c.get("id") == channel_id for c in r.json().get("value", [])):
                        return str(team_id)
                except Exception:
                    continue
    except Exception as exc:
        log.warning("teams channel-team scan failed: %s", exc)
    return None


def _map_channel_messages(data: Any, team_id: str, channel_id: str) -> dict[str, Any]:
    messages = [
        {
            "id": m.get("id"),
            "from": ((m.get("from") or {}).get("user") or {}).get("displayName"),
            "text": _strip_html((m.get("body") or {}).get("content", ""))[:2000],
            "createdDateTime": m.get("createdDateTime"),
        }
        for m in (data.get("value", []) if isinstance(data, dict) else [])
    ]
    return {
        "success": True,
        "team_id": team_id,
        "channel_id": channel_id,
        "messages": messages,
    }


async def channel_messages(team_id: str, channel_id: str, limit: int = 20) -> dict[str, Any]:
    """Recent channel messages (needs ChannelMessage.Read.All, text only)."""
    if not configured():
        return {"success": False, "error": "COMMS_GRAPH_CLIENT_ID not set"}
    token = await _authed_token()
    if not token:
        return {
            "success": False,
            "error": "not authorized - run comms_ops(operation='auth', channel='teams')",
        }
    try:
        n = max(1, min(int(limit), 100))
        async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
            r = await client.get(
                f"{_cfg().teams_graph_base}/teams/{quote(team_id, safe='')}"
                f"/channels/{quote(channel_id, safe='')}/messages?$top={n}",
                headers={"Authorization": f"Bearer {token}"},
            )
            r.raise_for_status()
            return _map_channel_messages(r.json(), team_id, channel_id)
    except httpx.HTTPStatusError as exc:
        return {
            "success": False,
            "error": f"graph {exc.response.status_code}: {exc.response.text[:300]}",
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


async def channel_send(
    team_id: str | None, channel_id: str, text: str, reply_to: str | None = None
) -> dict[str, Any]:
    """Post to a team channel (resolves the team by scan when omitted)."""
    if not configured():
        return {"success": False, "error": "COMMS_GRAPH_CLIENT_ID not set"}
    token = await _authed_token()
    if not token:
        return {
            "success": False,
            "error": "not authorized - run comms_ops(operation='auth', channel='teams')",
        }
    if not team_id:
        team_id = await _resolve_team_for_channel(token, channel_id)
    if not team_id:
        return {"success": False, "error": f"could not find the team for channel {channel_id}"}
    payload = {"body": {"contentType": "text", "content": text[:28000]}}
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
            if reply_to:
                r = await client.post(
                    f"{_cfg().teams_graph_base}/teams/{quote(team_id, safe='')}"
                    f"/channels/{quote(channel_id, safe='')}/messages/"
                    f"{quote(reply_to, safe='')}/replies",
                    json=payload,
                    headers={"Authorization": f"Bearer {token}"},
                )
            else:
                r = await client.post(
                    f"{_cfg().teams_graph_base}/teams/{quote(team_id, safe='')}"
                    f"/channels/{quote(channel_id, safe='')}/messages",
                    json=payload,
                    headers={"Authorization": f"Bearer {token}"},
                )
            r.raise_for_status()
            msg = r.json()
        return {
            "success": True,
            "team_id": team_id,
            "channel_id": channel_id,
            "message_id": msg.get("id"),
        }
    except httpx.HTTPStatusError as exc:
        return {
            "success": False,
            "error": f"graph {exc.response.status_code}: {exc.response.text[:300]}",
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


async def channel_edit(team_id: str, channel_id: str, message_id: str, text: str) -> dict[str, Any]:
    """Edit a channel message (PATCH body, text only)."""
    if not configured():
        return {"success": False, "error": "COMMS_GRAPH_CLIENT_ID not set"}
    token = await _authed_token()
    if not token:
        return {
            "success": False,
            "error": "not authorized - run comms_ops(operation='auth', channel='teams')",
        }
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
            r = await client.patch(
                f"{_cfg().teams_graph_base}/teams/{quote(team_id, safe='')}"
                f"/channels/{quote(channel_id, safe='')}/messages/{quote(message_id, safe='')}",
                json={"body": {"contentType": "text", "content": text[:28000]}},
                headers={"Authorization": f"Bearer {token}"},
            )
            r.raise_for_status()
            return {"success": True, "channel_id": channel_id, "message_id": message_id}
    except httpx.HTTPStatusError as exc:
        return {
            "success": False,
            "error": f"graph {exc.response.status_code}: {exc.response.text[:300]}",
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


async def channel_delete(team_id: str, channel_id: str, message_id: str) -> dict[str, Any]:
    """Soft-delete a channel message (DELETE)."""
    if not configured():
        return {"success": False, "error": "COMMS_GRAPH_CLIENT_ID not set"}
    token = await _authed_token()
    if not token:
        return {
            "success": False,
            "error": "not authorized - run comms_ops(operation='auth', channel='teams')",
        }
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
            r = await client.delete(
                f"{_cfg().teams_graph_base}/teams/{quote(team_id, safe='')}"
                f"/channels/{quote(channel_id, safe='')}/messages/{quote(message_id, safe='')}",
                headers={"Authorization": f"Bearer {token}"},
            )
            r.raise_for_status()
            return {"success": True, "channel_id": channel_id, "message_id": message_id}
    except httpx.HTTPStatusError as exc:
        return {
            "success": False,
            "error": f"graph {exc.response.status_code}: {exc.response.text[:300]}",
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


# ── address-form wrappers ("team/{t}/channel/{c}" or bare channel id) ──────
# The gateway routes on parse_channel_ref(); these resolve + delegate.


async def channel_history(ref: str, limit: int = 20) -> dict[str, Any]:
    """Read channel messages by address form (resolves team by scan)."""
    team_id, channel_id = parse_channel_ref(ref)
    if channel_id is None:
        return {"success": False, "error": f"not a channel address: {ref}"}
    if not team_id:
        token = await _authed_token()
        if not token:
            return {
                "success": False,
                "error": "not authorized - run comms_ops(operation='auth', channel='teams')",
            }
        team_id = await _resolve_team_for_channel(token, channel_id)
    if not team_id:
        return {"success": False, "error": f"could not find the team for channel {channel_id}"}
    return await channel_messages(team_id, channel_id, limit=limit)


async def channel_post(ref: str, text: str, reply_to: str | None = None) -> dict[str, Any]:
    """Post to a channel by address form (resolves team by scan)."""
    team_id, channel_id = parse_channel_ref(ref)
    if channel_id is None:
        return {"success": False, "error": f"not a channel address: {ref}"}
    return await channel_send(team_id, channel_id, text, reply_to=reply_to)


async def channel_edit_msg(ref: str, message_id: str, text: str) -> dict[str, Any]:
    """Edit a channel message by address form (team required)."""
    team_id, channel_id = parse_channel_ref(ref)
    if channel_id is None or not team_id:
        return {
            "success": False,
            "error": f"channel edit needs team/{{teamId}}/channel/{{channelId}}, got: {ref}",
        }
    return await channel_edit(team_id, channel_id, message_id, text)


async def channel_delete_msg(ref: str, message_id: str) -> dict[str, Any]:
    """Delete a channel message by address form (team required)."""
    team_id, channel_id = parse_channel_ref(ref)
    if channel_id is None or not team_id:
        return {
            "success": False,
            "error": f"channel delete needs team/{{teamId}}/channel/{{channelId}}, got: {ref}",
        }
    return await channel_delete(team_id, channel_id, message_id)


async def edit_message(chat_id: str, message_id: str, text: str) -> dict[str, Any]:
    """Edit a chat message (PATCH body, text only)."""
    if not configured():
        return {"success": False, "error": "COMMS_GRAPH_CLIENT_ID not set"}
    token = await asyncio.to_thread(_access_token)
    if not token:
        return {
            "success": False,
            "error": "not authorized - run comms_ops(operation='auth', channel='teams')",
        }
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
            r = await client.patch(
                f"{_cfg().teams_graph_base}/chats/{quote(chat_id, safe='')}"
                f"/messages/{quote(message_id, safe='')}",
                json={"body": {"contentType": "text", "content": text[:28000]}},
                headers={"Authorization": f"Bearer {token}"},
            )
            r.raise_for_status()
            return {"success": True, "chat_id": chat_id, "message_id": message_id}
    except httpx.HTTPStatusError as exc:
        return {
            "success": False,
            "error": f"graph {exc.response.status_code}: {exc.response.text[:300]}",
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


async def delete_message(chat_id: str, message_id: str) -> dict[str, Any]:
    """Soft-delete a chat message (DELETE)."""
    if not configured():
        return {"success": False, "error": "COMMS_GRAPH_CLIENT_ID not set"}
    token = await asyncio.to_thread(_access_token)
    if not token:
        return {
            "success": False,
            "error": "not authorized - run comms_ops(operation='auth', channel='teams')",
        }
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
            r = await client.delete(
                f"{_cfg().teams_graph_base}/chats/{quote(chat_id, safe='')}"
                f"/messages/{quote(message_id, safe='')}",
                headers={"Authorization": f"Bearer {token}"},
            )
            r.raise_for_status()
            return {"success": True, "chat_id": chat_id, "message_id": message_id}
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
