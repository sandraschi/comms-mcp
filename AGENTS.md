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

## Files

- `src/comms_mcp/adapters/telegram.py` — Bot API (httpx)
- `src/comms_mcp/outbox/sqlite.py` — outbox + inbound store, TTL purge
- `src/comms_mcp/mcp/tools/comms.py` — the portmanteau
- `src/comms_mcp/sanitize.py` — inbound sanitization (email-mcp pattern)
