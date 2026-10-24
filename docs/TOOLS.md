# Tools

## comms_ops — unified comms portmanteau (v0.8.0, text only)

| operation | channels | Description |
|---|---|---|
| `send` | all | Send text; Telegram `thread_ts`=reply_to + `parse_mode`=HTML; Slack/Teams `thread_ts`=thread reply |
| `read_recent` | all | Telegram polls getUpdates (offset-persisted); Signal polls receive; Slack/Teams live history when `chat_id` given (Teams: chat id or `team/{id}/channel/{id}`), else stored inbound |
| `list_threads` | all | Telegram: allowlist enriched with chat titles; Slack: live channels; Teams: live chats + teams-with-channels; WhatsApp/Signal: allowlist |
| `status` | all | Bot identity + pairing state (WhatsApp QR when disconnected; Signal link state) |
| `auth` | teams | Teams OAuth device-code flow |
| `history` | slack/teams | Live channel/chat history, `limit` 1-100 |
| `search` | slack | Live `search.messages` |
| `react` | slack | `reactions.add` |
| `edit` | telegram/slack/teams | Edit sent text (`thread_ts` = message id/ts) |
| `delete` | telegram/slack/teams | Delete message (`thread_ts` = message id/ts) |
| `help` | all | Per-channel setup steps |

## Parameters

- `channel` — literal `telegram` / `whatsapp` / `slack` / `teams` / `signal`
- `chat_id` — recipient chat id (send/history) / channel id (slack history/react/edit/delete) / E.164 (whatsapp/signal)
- `text` — message body (send/edit)
- `limit` — max messages (history/search/read_recent, default 20)
- `thread_ts` — reply target / message id: Slack ts, Telegram message_id, Teams message id
- `query` — search query (search)
- `emoji` — emoji name, colons optional (react)
- `parse_mode` — Telegram formatting: `HTML` or omitted

## REST (HTTP daemon mode, MCP_PORT=11205)

- `GET /health` — status + stats
- `GET /api/capabilities` — server/channels/tools/endpoints
- `GET /api/skills` — skill listing (skill-first agents)
- `GET /api/v1/outbox?status=&limit=` — delivery log
- `POST /api/v1/outbox/retry` — resend failed rows (`{"id"?}`), old rows → `retried`
- `GET /api/v1/inbound?chat_id=&limit=` — recent inbound
- `POST /api/shutdown` — orderly exit (NSSM-safe bounce)
- `/mcp` — MCP streamable HTTP (`comms_ops`, `comms_shutdown`, `comms_show_status`)

## Admin

- `comms_shutdown(confirm=True)` — orderly daemon exit after 500 ms
- `comms_show_status()` — Prefab card (`app=True`): bot identity, allowlist size, outbox counts

## Telegram (v0.1 + v0.6 text fatten: replies, HTML, edit/delete, offset-persisted poll)
- `send` supports `thread_ts` (reply_to message id) + `parse_mode="HTML"`
- `edit`/`delete` map to editMessageText/deleteMessage (`thread_ts` = message id)
- `list_threads` enriches the allowlist with live chat titles (best effort)
- `read_recent` polls getUpdates with a persisted offset (no re-ingest); handles message + edited_message + channel_post

## WhatsApp (v0.2, via Node baileys sidecar - text only, sidecar-bounded)
- `comms_ops` gains `channel="whatsapp"`: send (E.164, allowlist COMMS_WHATSAPP_ALLOW_NUMBERS), status (pairing QR via sidecar), list_threads (allowlist)
- Pair once: status surfaces QR + pairing_code + hint when disconnected (no direct sidecar calls needed); or GET :11208/qr, scan with the phone (Linked devices)
- Inbound: sidecar POSTs to /api/v1/inbound/wa - sanitized + stored with TTL
- Limits: sidecar exposes /health, /qr, /send only - no chat list or history; history = local inbound store

## Slack (v0.3 socket + v0.5 history/search/react, official SDK)
- `comms_ops` `channel="slack"`: send (allowlist COMMS_SLACK_CHANNEL_IDS, optional `thread_ts`), status (auth_test), list_threads (live channels), read_recent (live history when `chat_id` given), history / search / react
- No sidecar: Socket Mode client runs in the server process (needs xapp-* + xoxb-* tokens); inbound sanitized + stored
- Setup: create app (socket mode, scopes channels:history, channels:read, chat:write, reactions:write, search:read), set tokens, invite bot to channels, add channels to allowlist

## Teams (v0.4 Graph + v0.6 text fatten: live chats/history/replies/edit/delete)
- `comms_ops(operation="auth"|"send"|"history"|"edit"|"delete", channel="teams")`: send (allowlist COMMS_TEAMS_RECIPIENTS, optional `thread_ts` replyTo), status (Graph /me), list_threads (live chats + teams-with-channels), history/read_recent (live chat OR channel messages — `team/{teamId}/channel/{channelId}` or bare `@thread.tacv2` id), auth (device flow)
- Channel reads/sends need ChannelMessage.Read.All (usually admin-consented); the 403 names it
- Reuses email-mcp's Azure app registration (COMMS_GRAPH_CLIENT_ID); no Bot Framework / bot registration
- Auth: `comms_ops(operation="auth", channel="teams")` -> enter the code at microsoft.com/devicelogin -> call auth again to confirm
- Allowlist format: `steve=stephanschipal@hotmail.com` (email) or `channel=19:xxxx` (existing chat id); send resolves the target to a Teams chat and posts /chats/{id}/messages
- Note: Graph chat APIs need an organizational (work/school) identity; consumer accounts have limited /chats support

## Signal (v0.7 Docker bridge - text only, unofficial, dedicated number!)
- `comms_ops` `channel="signal"`: send (E.164, allowlist COMMS_SIGNAL_RECIPIENTS), status (link state), read_recent (polls receive), list_threads (allowlist)
- No history op (bridge has no server-side history); edit/delete/search/react unsupported
- Pair once: Settings → Channels → Signal → Start bridge (Docker, auto-pulls), Show link QR (scan with phone) or register dedicated number by SMS/voice + verify
- Limits: community bridge (bbernhard/signal-cli-rest-api) — upstream Signal changes can break it; never automate a personal primary number
