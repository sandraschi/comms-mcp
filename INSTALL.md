# Installing comms-mcp

comms-mcp runs as an MCP server (stdio) and, optionally, an HTTP daemon with a web
console. Pick the install path that fits you. Nobody needs all of them.

## Prerequisites

Install these only if you don't already have them. On Windows, all installs go
through [winget](https://learn.microsoft.com/en-us/windows/package-manager/winget/).

| Tool | Needed for | Install |
|---|---|---|
| Claude Desktop | Using the server in Claude | [claude.ai/download](https://claude.ai/download) |
| Git | Options B/C/D | `winget install Git.Git` |
| uv | Options C/D (and the script path) | `winget install astral-sh.uv` |
| Node.js | Option B only (mcpb CLI) | `winget install OpenJS.NodeJS` |
| Ollama | Optional local AI chat in the console | `winget install Ollama.Ollama` |

> After a winget install, **close and reopen your terminal** - the new PATH is not
> picked up in place.

## Easiest path - the one-click script

On Windows 10/11 this installs uv if needed, syncs dependencies, starts the server
and opens the console:

```powershell
git clone https://github.com/sandraschi/comms-mcp
cd comms-mcp
.\start.bat
```

- `.\start.bat -Check` - diagnose the machine, install nothing.
- `.\start.bat -Yes -NoStart` - install only, no prompts (good for agents).
- `.\stop.bat` - stop the server. `.\start.bat -Stop` does the same.

No terminal at all? See Option A.

## Option A - Drag and Drop (Recommended)

1. Go to [Releases](https://github.com/sandraschi/comms-mcp/releases/latest).
2. Download `comms-mcp-v*.mcpb`.
3. Open Claude Desktop and drag the file onto the window
   (*or* Settings -> MCP Servers -> Install from file).

No Python, uv, git or Node required. Requires a published release; if there is no
release yet, use the script path or Option C.

## Option B - mcpb CLI

```bash
# Requires Node.js (see Prerequisites)
npx @anthropic-ai/mcpb install https://github.com/sandraschi/comms-mcp
```

Note: mcpb is an npm package - **never** `uvx mcpb`, which does not exist.

## Option C - Manual Configuration

1. Clone and install:

   ```powershell
   git clone https://github.com/sandraschi/comms-mcp
   cd comms-mcp
   uv sync
   copy .env.example .env
   ```

2. Add it to your MCP client. Claude Desktop config:
   `%APPDATA%\Claude\claude_desktop_config.json`

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

3. Configure at least one channel in `.env` (see [docs/ONBOARDING.md](docs/ONBOARDING.md)):
   a Telegram bot token + chat allowlist is the fastest.
4. Restart the client.

Config file locations:
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`

## Option D - Developer Mode

For contributing or running from source with the test suite:

```powershell
git clone https://github.com/sandraschi/comms-mcp
cd comms-mcp
just bootstrap     # uv sync --extra dev + pre-commit + bun install
just serve         # stdio; MCP_PORT=11205 for the HTTP daemon
just ci            # ruff + pyright + pytest + biome + tsc
```

See [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md).

## AI / LLM features

The web console includes a Chat page and an LLM Settings page. Both work with
**either** local or cloud inference - you are not required to have a GPU:

- **Local (free):** install [Ollama](https://ollama.com) (`winget install Ollama.Ollama`)
  or LM Studio, pull a small model, and the console detects it automatically
  (`GET /api/llm/providers`). No key required.
- **Cloud:** open the console's Settings page and add a provider key
  (OpenAI-compatible or Anthropic). Keys are stored server-side and proxied -
  they are never sent to the browser or kept in `localStorage`.

Models are never bundled. The messaging gateway itself needs no LLM at all; this
section only matters if you use the console's chat.

## Verify Installation

In your MCP client, ask:

> "Run comms_ops with operation=status."

You should see each channel's configuration state. If you set up Telegram, run
`comms_ops(operation="read_recent")` after messaging your bot once.

## What is NOT required globally

Python and pip for the backend - uv fetches Python. Node and bun are needed only
to build or develop the console (`web_sota/dist`, which is gitignored); the MCP
server works without a built console.

## Globally required

- **uv** (auto-installed by `start.ps1` via winget) - backend.
- **bun** (`winget install Oven-sh.Bun`) - only for console work:
  `cd web_sota; bun install; bun run build`. Node stays installed because Vite runs
  on Node; bun replaces npm as the package manager and runner.

## Troubleshooting

Common issues and fixes live in [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md).
The most frequent one: a send is refused because the recipient is not on the
channel's allowlist - add it to the matching `COMMS_*` variable in `.env` and
restart. Logs: `logs\start.log`, `logs\backend.log`.
