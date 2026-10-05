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

    # Stdio (Claude Desktop): the HTTP daemon owns the SQLite store, so probe
    # it first and proxy when reachable (SOTA 2.3) — else serve stdio directly.
    from comms_mcp.server import mcp

    daemon = os.environ.get("COMMS_DAEMON_URL")
    if not daemon:
        probe_port = os.environ.get("MCP_PORT") or "11205"
        daemon = f"http://127.0.0.1:{probe_port}/mcp"
    try:
        import httpx

        base = daemon.removesuffix("/mcp")
        r = httpx.get(f"{base}/health", timeout=3)
        if r.status_code == 200:
            from fastmcp import FastMCP

            proxy = FastMCP.as_proxy(daemon)
            proxy.run(transport="stdio")
            return
    except Exception:
        pass
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
