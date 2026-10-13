# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec - produce comms-mcp-backend.exe for Tauri NSIS embedding.
# Fleet standard: strip=False, upx=False, noarchive=True (TAURI_PRODUCTION_PITFALLS.md).
# Usage (from repo root, project venv):
#   .venv\Scripts\pyinstaller.exe comms-mcp-backend.spec --clean --noconfirm

from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

_hidden = [
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.asyncio",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.httptools_impl",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "h11",
    "beartype",
    "websockets",
    "sqlite3",
    "_strptime",
    "_datetime",
    "cachetools",
    "pytz",
    "jsonschema",
    "joserfc",
    "joserfc.jwk",
    "joserfc.jwt",
]
for _pkg in ("comms_mcp", "fastapi", "slack_sdk", "prefab_ui"):
    try:
        _hidden += collect_submodules(_pkg)
    except Exception:
        pass

a = Analysis(
    ["run_server.py"],
    pathex=["src"],
    binaries=[],
    datas=[("src/comms_mcp", "comms_mcp")],
    hiddenimports=_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "setuptools", "pip", "wheel", "test", "tests", "unittest", "_distutils_hack"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=True,
)
# Strip .dist-info but preserve metadata for packages that need it at runtime
_keep_dist = ["fastmcp-", "fastmcp_slim-", "mcp-", "fastapi-", "pydantic-", "prefab_ui-", "email_validator-", "slack_sdk-"]
_saved = [
    e
    for e in a.datas
    if isinstance(e, tuple) and any(k in str(e[0]) for k in _keep_dist) and ".dist-info" in str(e[0])
]
for _list in [a.datas, a.binaries, a.zipfiles, a.scripts]:
    _list[:] = [e for e in _list if not (isinstance(e, tuple) and ".dist-info" in str(e[0]))]
a.datas.extend(_saved)
SKIP = [
    "torch",
    "playwright",
    "bitsandbytes",
    "llvmlite",
    "pyarrow",
    "pymupdf",
    "grpc",
    "numba",
    "Cython",
    "google",
    "azure",
    "boto3",
    "botocore",
    "matplotlib",
    "pandas",
    "scipy",
    "sklearn",
    "onnxruntime",
]
a.binaries = [b for b in a.binaries if not any(s in b[0].lower() for s in SKIP)]
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="comms-mcp-backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
)
