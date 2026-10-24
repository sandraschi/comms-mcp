# Changelog — comms-mcp

## v0.8.0 — gap fills (auto-resurrect, outbox retry, Teams channels)

- **Sidecar auto-resurrect on boot** (`COMMS_SIDECAR_AUTOSTART`, default on):
  adopt-if-alive always; auto-start WhatsApp when its allowlist is non-empty,
  Signal when its number is set._missing runtimes surface as failed phases.
- **Outbox retry**: failed rows keep `thread_ts`/`parse_mode` (schema
  migration), `POST /api/v1/outbox/retry` resends (new attempt row) and marks
  the old row `retried`; Outbox page has a Retry failed button.
- **Teams team/channel messages**: `team/{teamId}/channel/{channelId}` and
  bare `@thread.tacv2` addresses work for send/history/read_recent/edit/delete;
  `list_threads` also returns teams with channels. Needs
  ChannelMessage.Read.All (often admin-consented) for reads.
- **QR freshness**: pairing endpoints return `fetched_at`; Settings shows
  code age (codes rotate ~60s).
- **NSSM script**: passes `COMMS_INBOUND_SECRET` to the wa sidecar
  (was missing → 401 on inbound with a secret set); documents backend vs
  NSSM ownership and the Docker-managed Signal bridge.

## v0.7.0 — Signal lane (unofficial bridge, dedicated number!)

- 5th channel via bbernhard/signal-cli-rest-api (Docker-managed sidecar).
- Send (allowlist), poll-receive, link-QR, register/verify, Settings card,
  Help tab, docs guardrails. No history API — read_recent polls.

## v0.6.0 — text-only fatten (Telegram/Teams/WhatsApp)

- Telegram replies/HTML/edit/delete/getChat + offset-persisted polling.
- Teams live chats/history/replies/edit/delete. WhatsApp pairing in status.
- `edit`/`delete` ops.

## v0.5.0 — Slack depth

- Slack history/search/react/thread replies, live channel list.
