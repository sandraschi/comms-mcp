"""MCPB bootstrap for comms-mcp.

Claude Desktop runs this bundle over stdio. The bundle's own src/ is put on
sys.path first so the staged package resolves from the bundle and never from a
dev editable install left in site-packages (MCPB_PACKAGING_STANDARDS 2.5).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from comms_mcp.__main__ import main  # noqa: E402

if __name__ == "__main__":
    main()
