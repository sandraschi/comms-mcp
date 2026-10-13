# AI_SETUP - install comms-mcp for a user

You are an AI agent (Claude Code, Cursor, Codex, Copilot, ...) asked to set up
comms-mcp on this PC. Follow these steps in order. Do not improvise outside them.
Windows 10/11 only for now.

comms-mcp is one MCP tool that sends and reads messages on Telegram, WhatsApp,
Slack and Teams, with a local web console on port 11205. It runs as an MCP server
(stdio for Claude Desktop / Cursor) and, optionally, an HTTP daemon.

## 1. Ground rules

- Tell the user in plain words what you are about to do before each step.
- Allowed without asking: cloning this repo, running `start.bat` with the flags
  below, which may install **uv** (`astral-sh.uv`) via winget.
- **Ask the user first** before installing a WhatsApp sidecar, before entering any
  channel token, and before changing any MCP client config.
- Do not run anything elevated, do not change system settings, do not disable
  security features. Do not expose the server beyond `127.0.0.1`.
- Never kill a process you did not start. If port 11205 is held by another program,
  stop and tell the user.
- A quiet step is not a hung step: the first `uv sync` can take 1-2 minutes. Use a
  long timeout; never kill it.
- If something fails, rerunning `start.bat` is safe. Never "fix" problems by
  editing this repo's source code.

## 2. Get the code

Pick a folder with the user (default: `%USERPROFILE%\comms-mcp`).

```powershell
git clone https://github.com/sandraschi/comms-mcp "$env:USERPROFILE\comms-mcp"
```

No git? Download and unpack the zip:

```powershell
Invoke-WebRequest https://github.com/sandraschi/comms-mcp/archive/refs/heads/main.zip -OutFile "$env:TEMP\comms-mcp.zip"
Expand-Archive "$env:TEMP\comms-mcp.zip" "$env:USERPROFILE" ; Rename-Item "$env:USERPROFILE\comms-mcp-main" comms-mcp
```

All commands below run in that folder.

## 3. Check (installs nothing)

```powershell
.\start.bat -Check -Json
```

Read `verdict` and the `checks` array:

| verdict | exit code | Do |
|---|---|---|
| `READY` | 0 | Go to step 5 |
| `READY WITH WARNINGS` | 2 | Read each `warn`, decide with step 4, continue |
| `BLOCKED: ...` | 1 | Stop. Tell the user the `detail` and `fix` of the `fail` item. Do not work around it |

`status: install` items are fine - step 5 installs them. If `running` is `true`,
comms-mcp is already up: skip to step 7.

A `env_file` warn means no `.env` yet: the server starts, but no channel can send
until the user configures one. That is expected on a fresh install.

## 4. Decide

| Situation (from the check) | Choice |
|---|---|
| `env_file` warn (no `.env`) | Copy `.env.example` to `.env`, then ask the user which **one** channel to set up first (see docs/ONBOARDING.md). Do not invent tokens |
| User wants the console | It is served on `http://127.0.0.1:11205/` once `web_sota/dist` exists; if `console` is `info`, ask before running `bun run build` in `web_sota` |
| User only wants their AI app to send messages | stdio connect is enough (step 7a) |
| WhatsApp requested | Explain the sidecar + QR pairing (docs/ONBOARDING.md); ask before starting it |
| Teams requested | Explain the device-code flow; reuse the fleet email-mcp Azure app id if present |

## 5. Install

```powershell
.\start.bat -Yes -NoStart
```

Run with a timeout of at least 10 minutes. Ends with `Install OK.` and exit code 0,
printing the fix next to any error. On failure: rerun once (it resumes); if it
fails again, go to step 8.

## 6. Start and verify

```powershell
.\start.bat -Yes -Detach -NoBrowser
```

Returns in about 10-30 s once healthy. Verify:

```powershell
Invoke-RestMethod http://127.0.0.1:11205/health   # expect status=ok, server=comms-mcp
```

Tell the user: console at `http://127.0.0.1:11205/`. Stop with `.\stop.bat` (or
`.\start.bat -Stop`). The server keeps running after you exit.

## 7. Connect the user's AI app

Ask which app, show the change, then apply it. Replace `C:\path\to\comms-mcp` with
the real folder.

**a) Stdio (recommended; the app starts the server itself):**

Claude Code:

```powershell
claude mcp add comms --scope user -- uv --directory "C:\path\to\comms-mcp" run python -m comms_mcp
```

Claude Desktop (`%APPDATA%\Claude\claude_desktop_config.json`) or Cursor
(`%USERPROFILE%\.cursor\mcp.json`), merged into the existing `mcpServers` object:

```json
{
  "mcpServers": {
    "comms": {
      "command": "uv",
      "args": ["--directory", "C:\\path\\to\\comms-mcp", "run", "python", "-m", "comms_mcp"],
      "env": { "PYTHONUNBUFFERED": "1" }
    }
  }
}
```

Claude Desktop must be restarted (fully quit from the tray) to pick it up. With no
`MCP_PORT` set, this runs stdio and proxies to the daemon when one is up.

**b) HTTP (only while the daemon from step 6 is running):** `http://127.0.0.1:11205/mcp`
(Claude Code: `claude mcp add --transport http comms http://127.0.0.1:11205/mcp`).

**c) Claude Desktop zero-setup alternative:** the `.mcpb` from
https://github.com/sandraschi/comms-mcp/releases/latest - the user drags it onto
Claude Desktop. Only available once a release is published.

**Verify:** in the app, ask: "Run comms_ops with operation=status." It should list
the channels and report which are configured.

## 8. Stop conditions and logs

Stop and hand back to the user, quoting the relevant lines, when:

- the check says `BLOCKED`,
- `start.bat` fails twice in a row,
- a step needs a channel token, the sidecar, or a config change the user has not
  approved.

Logs (one set per run, overwritten each run):

| File | Contains |
|---|---|
| `logs\start.log` | Everything `start.bat` printed |
| `logs\backend.log` / `logs\backend.log.err` | Server output |

Problems and fixes: [TROUBLESHOOTING.md](TROUBLESHOOTING.md). To report a bug, open
an issue at https://github.com/sandraschi/comms-mcp/issues and attach
`logs\start.log` and `logs\backend.log.err`.
