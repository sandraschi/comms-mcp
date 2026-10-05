"""Portmanteau imports - FastMCP registers tools at import time."""

from . import admin, comms, prefab_cards  # noqa: F401  # import registers tools

__all__ = ["admin", "comms", "prefab_cards"]
