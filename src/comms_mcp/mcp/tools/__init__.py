"""Portmanteau imports - FastMCP registers tools at import time."""

from . import admin, comms  # noqa: F401  # import registers tools

__all__ = ["admin", "comms"]
