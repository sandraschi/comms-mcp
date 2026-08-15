"""Portmanteau imports - FastMCP registers tools at import time."""

from . import comms  # noqa: F401  # import registers tools

__all__ = ["comms"]
