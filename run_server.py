"""Frozen (PyInstaller) entry point for the comms-mcp Tauri backend.

Dev stdio/HTTP entry stays `python -m comms_mcp`; this file exists so the frozen
backend can (a) resolve the bundled package from `_MEIPASS` and (b) survive
`console=False`, where `sys.stdout`/`sys.stderr` are `None` and uvicorn's logging
crashes with `'NoneType' object has no attribute 'isatty'`
(TAURI_PRODUCTION_PITFALLS.md).
"""

from __future__ import annotations

# Stdlib C extensions must be imported eagerly or PyInstaller may omit them.
import _datetime  # noqa: F401
import _strptime  # noqa: F401
import os
import sys
from pathlib import Path

# Freeze the `mcp` bootstrap before fastmcp touches it (frozen-context pitfall).
try:
    import mcp.types  # noqa: F401
except Exception:
    pass

if getattr(sys, "frozen", False):
    _base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    sys.path.insert(0, str(_base))
else:
    sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))


class _NullStream:
    """Write-through to nothing, with isatty() -> False (console=False shim)."""

    def write(self, *args: object) -> int:
        return 0

    def flush(self) -> None:
        return None

    def isatty(self) -> bool:
        return False


for _name in ("stdout", "stderr"):
    if getattr(sys, _name, None) is None:
        setattr(sys, _name, _NullStream())

os.environ.setdefault("COMMS_MCP_TAURI", "1")

from comms_mcp.__main__ import main  # noqa: E402

if __name__ == "__main__":
    main()
