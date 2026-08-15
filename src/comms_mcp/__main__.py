"""Entry point - dual transport: MCP_PORT env -> HTTP daemon, else stdio.

Per SOTA_REQUIREMENTS.md section 2.3: stateless adapters can run stdio;
with a persistent outbox/inbound store the HTTP daemon owns the DB.
"""

from __future__ import annotations

import os


def main() -> None:
    port = os.environ.get("MCP_PORT") or os.environ.get("PORT")
    if port:
        import uvicorn

        from comms_mcp.server import app

        host = os.environ.get("MCP_HOST", "127.0.0.1")
        uvicorn.run(app, host=host, port=int(port), log_level="warning")
        return

    from comms_mcp.server import mcp

    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
