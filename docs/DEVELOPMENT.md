# Development — comms-mcp

## Layout

```
src/comms_mcp/
  server.py          FastAPI app (REST) + MCP streamable-HTTP mount at /mcp
  __main__.py        dual transport: MCP_PORT set -> uvicorn daemon, else stdio
                     (stdio probes the daemon /health and proxies when up)
  registry.py        the single FastMCP("comms-mcp") instance
  config.py          pydantic-settings, env prefix COMMS_
  sanitize.py        inbound sanitization (zero-width/control strip + injection wrap)
  adapters/          telegram.py whatsapp.py slack.py teams.py (one module/channel)
  outbox/sqlite.py   outbox (pending/sent/failed) + inbound (7-day TTL), WAL
  mcp/tools/         comms.py (comms_ops portmanteau) admin.py (comms_shutdown)
skills/comms/SKILL.md  agent-facing domain skill (also served via GET /api/skills)
web_sota/            React + Vite + Tailwind console (ports 11204 dev / 11205 serve)
wa-sidecar/          Node baileys sidecar (:11208) -> webhook /api/v1/inbound/wa
scripts/install-services.ps1  NSSM installer (comms-mcp + comms-mcp-wa)
```

## Commands

```powershell
just serve    # stdio; MCP_PORT=11205 -> HTTP daemon
just test     # pytest
just lint     # ruff check
just fmt      # ruff format (write)
just fix      # ruff check --fix + format
just types    # pyright src/
just ci       # gates-green: lint + format --check + types + tests (+ web typecheck)
just bootstrap  # uv sync --extra dev + pre-commit install + web npm ci
```

## Backend endpoints

`GET /health` (also `/api/health`) · `GET /api/capabilities` ·
`GET /api/skills` · `GET /api/v1/outbox|inbound|status` · `POST /api/v1/send` ·
`POST /api/v1/inbound/wa` (X-Comms-Secret when COMMS_INBOUND_SECRET is set) ·
`POST /api/shutdown` (200 now, os._exit after 500 ms — NSSM-safe bounce).

MCP streamable HTTP is mounted at `/mcp` (both `/mcp` and `/mcp/` answer —
Starlette Mount only matches `/mcp/*`, so a rewrite middleware covers the bare
path). Mount with `mcp.http_app(path="/", transport="streamable-http")` and
compose the parent lifespan as `async with mcp_http.lifespan(app)` (BUG-038);
verify with a real `fastmcp.Client("http://127.0.0.1:PORT/mcp")` calling
`list_tools()` — in-process ASGI transport never runs lifespan and proves nothing.

## Adding a channel

1. New `src/comms_mcp/adapters/<ch>.py` with `configured()`, `status()`,
   `send_message()`, allowlist reader; sanitize all inbound via
   `sanitize.sanitize_inbound()` before `store.store_inbound()`.
2. Add a dispatch arm in `comms_ops` for status/list_threads/send (+ auth if the
   channel needs pairing/device flow).
3. Env vars under `COMMS_` + rows in `.env.example`, `docs/CONFIGURATION.md`,
   `docs/ONBOARDING.md`, `llms-full.txt`; extend `comms_ops` docstring examples.
4. Tests in `tests/test_<ch>.py` (allowlist gate, status shape, inbound store).
5. Register ports in `mcp-central-docs/operations/WEBAPP_PORTS.md` if the channel
   needs a new one.

## Conventions

- Send is allowlist-gated — never bypass the adapter allowlist check.
- Inbound text is untrusted — always sanitize before store or display.
- Tool returns are dialogic: `{"success", "message", ...}` (keep `"error"` too).
- Tool annotations use MCP hints (`readOnlyHint`, …), not custom keys.
- No `print()` in server code (`logger`), no bare `except:`, ruff `T20` enforced.
