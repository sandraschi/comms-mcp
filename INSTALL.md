# Install

Two commands (Windows 10/11, winget available):

```powershell
git clone https://github.com/sandraschi/comms-mcp
cd comms-mcp
.\start.bat
```

`start.bat` → `start.ps1` → `Require-Command` (uv via winget) → `uv sync` → import
smoke test → backend on :11205.

## Manual

1. Install uv: `winget install Astral.uv`
2. `uv sync` (creates .venv, downloads CPython if absent)
3. `copy .env.example .env` and set `COMMS_TELEGRAM_BOT_TOKEN` + `COMMS_TELEGRAM_CHAT_IDS`
4. `uv run python -m comms_mcp` (or set `MCP_PORT=11205` for the HTTP daemon)

## What is NOT required globally

Python, pip — nothing for the backend. uv handles Python; the server is pure
Python. Node and bun are needed to build/develop the web console: `web_sota/dist`
is **not shipped** (gitignored), so on a fresh clone run `cd web_sota; bun install;
bun run build` to serve the console from the backend. The MCP server itself works
without the console.

## Globally required

- `uv` (auto-installed by start.ps1 via winget) — backend.
- **bun** (`C:\Users\sandr\.bun\bin\bun.exe`, or `winget install Oven-sh.Bun`)
  — only for console work: `cd web_sota; bun install; bun run dev`. Node stays
  installed (Vite runs on Node); bun replaces npm as package manager + runner.
  See `mcp-central-docs/standards/BUN_STANDARDS.md`.
