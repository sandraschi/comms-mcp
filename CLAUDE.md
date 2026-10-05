# CLAUDE.md — comms-mcp

Unified fleet comms gateway (Telegram / WhatsApp / Slack / Teams) behind the
`comms_ops` portmanteau. Allowlist-gated send, sanitized inbound, 7-day
retention, SQLite outbox. Backend :11205, console :11204, wa-sidecar :11208.

## Entry points

- `uv run python -m comms_mcp` — stdio; `MCP_PORT=11205` → HTTP daemon
- `just serve | test | lint | fix | fmt | types | ci | bootstrap | mcpb-pack`
- Console: `web_sota/` (`npm run dev`, proxied to :11205 in dev, served from
  `:11205` root via `web_sota/dist` in daemon mode)
- NSSM: `scripts/install-services.ps1` (elevated) — `comms-mcp` + `comms-mcp-wa`

## Standards that bite here

- `TOOL_DESIGN_STANDARDS.md` §4.2 dialogic returns (`success` + `message`),
  §7.1 error handling (`_error_response` + `logger.exception`), §9 MCP
  annotation hints — not custom keys.
- `STARLETTE_NO_PYDANTIC_STANDARD.md` — the `/mcp` mount pattern
  (`http_app(path="/")` + `mount("/mcp")`, bare-path rewrite middleware,
  composed `mcp_http.lifespan(app)`); verify with a real
  `fastmcp.Client("http://127.0.0.1:PORT/mcp")`, never in-process ASGI.
- Fleet ruff: `T20` (no `print` in server code) enforced; per-file-ignores for
  CLI/build/test paths only.

## Key files

- `src/comms_mcp/server.py` — FastAPI + `/mcp` mount + REST
- `src/comms_mcp/__main__.py` — dual transport + stdio→daemon probe/proxy
- `src/comms_mcp/mcp/tools/comms.py` — the portmanteau; `admin.py` — shutdown
- `src/comms_mcp/adapters/*.py` — one module per channel (allowlist + sanitize)
- `src/comms_mcp/outbox/sqlite.py` — outbox + inbound store, TTL purge
- `skills/comms/SKILL.md` — agent domain skill (also `GET /api/skills`)
- `docs/ONBOARDING.md` — per-channel setup; `docs/TROUBLESHOOTING.md` — fixes
