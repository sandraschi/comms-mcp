# Changelog

## v0.4.0 (2026-10-05)

- assfix pass: score 0 -> SOTA-track (see docs/assess-reports/2026-10-05.md)
- MCP streamable HTTP mounted at `/mcp` (both `/mcp` + `/mcp/` answer via
  bare-path rewrite; lifespan composed per BUG-038) — registry promise kept
- Stdio probes the daemon and proxies when reachable (SOTA 2.3)
- `comms_shutdown` MCP tool + `POST /api/shutdown` (NSSM-safe bounce)
- `GET /api/capabilities`, `GET /api/skills`; `comms://status` resource,
  `comms_send_briefing` prompt, `skills/comms/SKILL.md` + provider
- Dialogic returns (`success` + `message`) on all ops; MCP hint annotations;
  `output_schema`; `_error_response` with traceback logging
- wa webhook shared secret (`COMMS_INBOUND_SECRET` + sidecar header)
- NSSM installer pins `USERPROFILE` + absolute `COMMS_DB_PATH` (split-brain)
- Console: hero + onboarding cue, Outbox search/sort/paginate/count, error
  states with retry, button types, contrast/font fixes, biome + tsc green
- CI (ruff/format/pyright/pytest + web biome:ci/typecheck), pre-commit +
  local biome hook, `.gitattributes` LF, coverage gate (fail-under 40)
- Docs: ONBOARDING / DEVELOPMENT / TROUBLESHOOTING / CLAUDE.md; synced
  glama.json, llms-full.txt, README; session-ctx injectors (Claude/Cursor/
  Windsurf/Copilot/OpenCode/Antigravity)

## v0.4.0-teams (shipped before 2026-10-05; exact date unknown, reconstructed)

- Teams adapter (Graph delegated device-code flow): auth/status/send,
  `name=email|19:chatId` allowlist, token store with refresh

## v0.3.0-slack (shipped before 2026-10-05; exact date unknown, reconstructed)

- Slack adapter (official SDK, Socket Mode + Web API): allowlist-gated send,
  auth_test status, real-time sanitized inbound (bot echo skipped)

## v0.2.0-whatsapp (shipped before 2026-10-05; exact date unknown, reconstructed)

- WhatsApp adapter via Node baileys sidecar (`wa-sidecar/`, :11208): status/QR
  pairing, E.164 allowlist send, inbound webhook with TTL

## v0.1.0 (2026-08-15)

- comms_ops portmanteau: send / read_recent / list_threads / status / help
- Telegram adapter (Bot API, httpx): allowlist-gated send, getUpdates polling
- Outbox (pending/sent/failed) + inbound store, 7-day retention TTL
- Inbound sanitization (zero-width/control stripping, injection neutralization)
- Dual transport (stdio / MCP_PORT HTTP daemon) + Starlette REST /health,
  /api/v1/outbox, /api/v1/inbound
- 6 unit tests; ruff/pyright clean
