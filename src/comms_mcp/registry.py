"""MCP registry - single FastMCP instance for the server."""

from pathlib import Path

from fastmcp import FastMCP
from fastmcp.server.providers import SkillsDirectoryProvider

mcp = FastMCP("comms-mcp")
mcp.add_provider(
    SkillsDirectoryProvider(roots=[Path(__file__).resolve().parent.parent.parent / "skills"])
)
