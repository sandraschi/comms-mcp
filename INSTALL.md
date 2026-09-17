# Install

Two commands (Windows 10/11, winget available):

```powershell
git clone https://github.com/sandraschi/comms-mcp
cd comms-mcp
.\start.bat
```

`start.bat` → `start.ps1` → `Require-Command` (uv via winget) → `uv sync` → import
smoke test → backend on :10904.

## Manual

1. Install uv: `winget install Astral.uv`
2. `uv sync` (creates .venv, downloads CPython if absent)
3. `copy .env.example .env` and set `COMMS_TELEGRAM_BOT_TOKEN` + `COMMS_TELEGRAM_CHAT_IDS`
4. `uv run python -m comms_mcp` (or set `MCP_PORT=10904` for the HTTP daemon)

## What is NOT required globally

Python, pip, Node, npm — nothing. uv handles Python; the server is pure Python.

## Globally required

- `uv` (auto-installed by start.ps1 via winget) — nothing else.
