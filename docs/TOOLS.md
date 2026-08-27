# Tools

## comms_ops — unified comms portmanteau

| operation | v0.1 | Description |
|---|---|---|
| `send` | telegram | Send text to an allowlisted chat; outbox-logged; returns outbox_id + telegram message_id |
| `read_recent` | telegram | Pull pending inbound (getUpdates polling), store sanitized, list recent |
| `list_threads` | telegram | The configured chat allowlist |
| `status` | telegram | Bot identity (getMe), configured flag, allowlist, outbox/inbound stats |
| `auth` | teams | Start/poll the Teams OAuth device-code flow (enter the code at microsoft.com/devicelogin) |
| `help` | telegram | Per-channel setup steps |

## Parameters

- `channel` — literal `telegram` / `whatsapp` / `slack` / `teams`
- `chat_id` — recipient chat id (send)
- `text` — message body (send)

## REST (HTTP daemon mode, MCP_PORT=11028)

- `GET /health` — status + stats
- `GET /api/v1/outbox?status=&limit=` — delivery log
- `GET /api/v1/inbound?chat_id=&limit=` — recent inbound

## WhatsApp (v0.2, via Node baileys sidecar)
- \comms_ops\ gains channel=\"whatsapp\": send (E.164, allowlist COMMS_WHATSAPP_ALLOW_NUMBERS), status (pairing QR via sidecar), list_threads (allowlist)
- Pair once: start wa-sidecar (node wa-sidecar), GET :10709/qr, scan with the phone (Linked devices)
- Inbound: sidecar POSTs to /api/v1/inbound/wa - sanitized + stored with TTL

## Slack (v0.3, official SDK, Socket Mode)
- \comms_ops\ channel=\"slack\": send (channel allowlist COMMS_SLACK_CHANNEL_IDS), status (auth_test), list_threads, read_recent (real-time inbound)
- No sidecar: Socket Mode client runs in the server process (needs xapp-* + xoxb-* tokens); inbound sanitized + stored
- Setup: create app (socket mode, channels:history+chat:write), set tokens, invite bot to channels, add channels to allowlist

## Teams (v0.4, Microsoft Graph - delegated device-code flow)
- channel=\"teams\": send (allowlist COMMS_TEAMS_RECIPIENTS), status (Graph /me), list_threads (allowlist), auth (device flow)
- Reuses email-mcp's Azure app registration (COMMS_GRAPH_CLIENT_ID); no Bot Framework / bot registration
- Auth: `comms_ops(operation="auth", channel="teams")` -> enter the code at microsoft.com/devicelogin -> call auth again to confirm
- Allowlist format: `steve=stephanschipal@hotmail.com` (email) or `channel=19:xxxx` (existing chat id); send resolves the target to a Teams chat and posts /chats/{id}/messages
- Note: Graph chat APIs need an organizational (work/school) identity; consumer accounts have limited /chats support

