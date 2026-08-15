# Changelog

## v0.1.0 (2026-08-15)

- comms_ops portmanteau: send / read_recent / list_threads / status / help
- Telegram adapter (Bot API, httpx): allowlist-gated send, getUpdates polling
- Outbox (pending/sent/failed) + inbound store, 7-day retention TTL
- Inbound sanitization (zero-width/control stripping, injection neutralization)
- Dual transport (stdio / MCP_PORT HTTP daemon) + Starlette REST /health,
  /api/v1/outbox, /api/v1/inbound
- 6 unit tests; ruff/pyright clean
