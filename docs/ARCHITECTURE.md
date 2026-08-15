# Architecture

```
Agent (MCP client)
    |
comms_ops portmanteau (FastMCP)
    |                              adapters/telegram.py (Bot API, httpx)
    |--- send ---------> allowlist check -> outbox(sqlite) -> sendMessage
    |--- read_recent --> getUpdates(poll) -> sanitize_inbound -> inbound(sqlite, 7d TTL)
    |--- status -------> getMe + allowlist + stats
    |
Starlette REST (:11028, daemon mode)   outbox/inbound = data/comms.db (WAL)
```

- Dual transport: stdio (default) or HTTP daemon when `MCP_PORT` set
  (SOTA_REQUIREMENTS 2.3 - the daemon owns the store; stdio proxies).
- Channel adapters are additive: new channel = new `adapters/<ch>.py` +
  a `comms_ops` dispatch arm (Signal/WhatsApp/Slack in v0.2/v0.3).
- Retention: `purge_expired()` runs at daemon startup and is available via
  `status` metrics; bodies expire at `received_at + COMMS_RETENTION_DAYS`.
