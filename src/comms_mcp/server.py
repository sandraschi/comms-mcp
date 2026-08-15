"""comms-mcp server - FastMCP instance + Starlette REST (status/outbox).

Dual transport: stdio (default) or HTTP daemon (MCP_PORT set, per
SOTA_REQUIREMENTS 2.3). The HTTP daemon owns the outbox/inbound store;
stdio instances probe the daemon and proxy when reachable.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import __version__
from .mcp import tools  # noqa: F401  # import registers tools
from .outbox import sqlite as store
from .registry import mcp  # noqa: F401  # re-exported for stdio entry

logging.basicConfig(level=logging.WARNING)
log = logging.getLogger("comms_mcp")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: purge expired inbound bodies (7-day TTL).
    purged = store.purge_expired()
    if purged:
        log.info("purged %d expired inbound messages", purged)
    yield


# REST surface (webapp + diagnostics)
app = FastAPI(title="comms-mcp", version=__version__, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:11029", "http://127.0.0.1:11029"],
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "server": "comms-mcp",
        "version": __version__,
        "channels": ["telegram"],
        "stats": store.status_counts(),
    }


@app.get("/api/v1/outbox")
async def api_outbox(status: str = "", limit: int = 25):
    return {"items": store.list_outbox(status=status, limit=limit)}


@app.get("/api/v1/inbound")
async def api_inbound(chat_id: str = "", limit: int = 20):
    return {"messages": store.list_inbound(chat_id=chat_id, limit=limit)}

