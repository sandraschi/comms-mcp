"""Admin tools - graceful shutdown for NSSM/launcher restarts."""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Annotated, Any

from pydantic import Field

from ...registry import mcp

logger = logging.getLogger("comms_mcp.admin")


@mcp.tool(
    annotations={
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": False,
    },
    output_schema={"type": "object"},
    version="0.4.0",
)
async def comms_shutdown(
    confirm: Annotated[
        bool, Field(description="Must be true — guards against accidental shutdown.")
    ] = False,
) -> dict[str, Any]:
    """Shut down the comms-mcp server process (orderly exit).

    Lets the NSSM service / fleet launcher bounce the daemon after deploys.
    Responds first, then exits after 500 ms so the response is delivered.

    ## Return Format
    {"success": bool, "message": str}

    ## Examples
    comms_shutdown(confirm=True)
    """
    if not confirm:
        return {"success": False, "message": "pass confirm=True to shut down"}

    def _exit() -> None:
        time.sleep(0.5)
        os._exit(0)

    threading.Thread(target=_exit, daemon=True, name="comms-shutdown").start()
    logger.warning("shutdown requested via MCP - exiting in 500 ms")
    return {"success": True, "message": "shutting down"}
