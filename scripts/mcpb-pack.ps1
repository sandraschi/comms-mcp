# MCPB pack for comms-mcp (MCPB_PACKAGING_STANDARDS).
# Fresh-stages src/ -> mcpb/src/ on every run (never ships a stale bundle).
# Requires mcpb/manifest.json + assets (prompts 3-4-100) — see Phase 5 notes.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Stage = Join-Path $Root "mcpb\src"

$manifest = Join-Path $Root "mcpb\manifest.json"
if (-not (Test-Path $manifest)) {
    Write-Host "ERROR: mcpb/manifest.json missing — full MCPB packaging pass not done yet." -ForegroundColor Red
    Write-Host "See docs/assess-reports/2026-10-05.md (deferred H12/H13)." -ForegroundColor Yellow
    exit 1
}

# Fresh stage: wipe + recopy (gitignore alone does not stop stale twins).
if (Test-Path $Stage) { Remove-Item -Recurse -Force $Stage }
New-Item -ItemType Directory -Force -Path $Stage | Out-Null
Copy-Item (Join-Path $Root "src\comms_mcp") (Join-Path $Stage "comms_mcp") -Recurse

# Self-import check: the bundle must import itself off mcpb/src alone.
$env:PYTHONPATH = $Stage
& (Get-Command uv).Source run --project $Root python -c "import importlib.util as u; s=u.find_spec('comms_mcp'); print(s.origin); assert s and 'mcpb' in s.origin"
if ($LASTEXITCODE -ne 0) { Write-Host "ERROR: staged bundle cannot import itself" -ForegroundColor Red; exit 1 }

# No caches or backups in the stage.
Get-ChildItem -Path (Join-Path $Root "mcpb") -Recurse -Include "__pycache__", "*.pyc", "*.bak", "*.bak.*" -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force

$ver = (& (Get-Command uv).Source run --project $Root python -c "import comms_mcp; print(comms_mcp.__version__)")
$out = Join-Path $Root "dist\comms-mcp-v$ver.mcpb"
New-Item -ItemType Directory -Force -Path (Join-Path $Root "dist") | Out-Null
mcpb pack (Join-Path $Root "mcpb") $out
Write-Host "Packed: $out" -ForegroundColor Green
