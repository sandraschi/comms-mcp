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

## WhatsApp (v0.2, via Node baileys sidecar)
- \comms_ops\ gains channel=\"whatsapp\": send (E.164, allowlist COMMS_WHATSAPP_ALLOW_NUMBERS), status (pairing QR via sidecar), list_threads (allowlist)
- Pair once: start wa-sidecar (node wa-sidecar), GET :11032/qr, scan with the phone (Linked devices)
- Inbound: sidecar POSTs to /api/v1/inbound/wa - sanitized + stored with TTL

## Slack (v0.3, official SDK, Socket Mode)
- \comms_ops\ channel=\"slack\": send (channel allowlist COMMS_SLACK_CHANNEL_IDS), status (auth_test), list_threads, read_recent (real-time inbound)
- No sidecar: Socket Mode client runs in the server process (needs xapp-* + xoxb-* tokens); inbound sanitized + stored
- Setup: create app (socket mode, channels:history+chat:write), set tokens, invite bot to channels, add channels to allowlist
