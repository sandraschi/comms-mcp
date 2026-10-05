# comms-mcp — Agent Guide

Unified fleet comms gateway. Telegram Bot API v0.1 behind `comms_ops`
portmanteau (send/read_recent/list_threads/status/help). Allowlist-gated
send, sanitized inbound, 7-day retention, SQLite outbox.

## Quick ref

```powershell
uv run python -m comms_mcp        # stdio; MCP_PORT=11205 -> HTTP daemon
just serve | lint | fix | test | types
```

Ports: backend 11205 (reserved 11205/11204 per WEBAPP_PORTS.md).

## Rules

- Send is allowlist-gated — never bypass `chat_allowlist()`.
- Inbound text is untrusted: always `sanitize.sanitize_inbound()` before use.
- Outbound goes through the outbox (enqueue -> mark_sent/failed).
- Token only via `.env` (`COMMS_TELEGRAM_BOT_TOKEN`) — never hardcode.
- Adapters: one module per channel in `adapters/`, registered in `comms_ops`.

## HTTP daemon + stdio proxy

- Daemon port **11205** (`MCP_PORT`/`PORT` env; `MCP_HOST` default 127.0.0.1).
  NSSM service name: `comms-mcp` (sidecar: `comms-mcp-wa` on :11208).
- The daemon owns `data/comms.db` (override `COMMS_DB_PATH`, absolute for NSSM).
- Stdio instances probe `COMMS_DAEMON_URL` (default
  `http://127.0.0.1:<MCP_PORT or 11205>/health`) and `FastMCP.as_proxy()` the
  daemon's `/mcp` when reachable — no double-daemon.
- Bounce orderly: `POST /api/shutdown` (or `comms_shutdown(confirm=True)`),
  then `Restart-Service`; never kill the child process.
- NSSM env pins `USERPROFILE` + absolute `COMMS_DB_PATH` (split-brain guard).

## Files

- `src/comms_mcp/adapters/telegram.py` — Bot API (httpx)
- `src/comms_mcp/outbox/sqlite.py` — outbox + inbound store, TTL purge
- `src/comms_mcp/mcp/tools/comms.py` — the portmanteau
- `src/comms_mcp/sanitize.py` — inbound sanitization (email-mcp pattern)
