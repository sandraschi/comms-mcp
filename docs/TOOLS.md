# Tools

## comms_ops — unified comms portmanteau

| operation | v0.1 | Description |
|---|---|---|
| `send` | telegram | Send text to an allowlisted chat; outbox-logged; returns outbox_id + telegram message_id |
| `read_recent` | telegram | Pull pending inbound (getUpdates polling), store sanitized, list recent |
| `list_threads` | telegram | The configured chat allowlist |
| `status` | telegram | Bot identity (getMe), configured flag, allowlist, outbox/inbound stats |
| `help` | telegram | Per-channel setup steps |

## Parameters

- `channel` — literal `telegram` (v0.1)
- `chat_id` — recipient chat id (send)
- `text` — message body (send)

## REST (HTTP daemon mode, MCP_PORT=11028)

- `GET /health` — status + stats
- `GET /api/v1/outbox?status=&limit=` — delivery log
- `GET /api/v1/inbound?chat_id=&limit=` — recent inbound
