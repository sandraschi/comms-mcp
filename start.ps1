param([switch]$Headless, [switch]$BackendOnly)
$ErrorActionPreference = "Stop"
$ScriptRoot = Split-Path -Parent $PSCommandPath
$BackendPort = 11205

function Require-Command {
    param([string]$Cmd, [string]$WingetId, [string]$Label)
    if (Get-Command $Cmd -ErrorAction SilentlyContinue) { return }
    Write-Host "  $Label not found - installing via winget ..." -ForegroundColor Yellow
    winget install --id $WingetId --silent --accept-source-agreements --accept-package-agreements
    $env:PATH = [System.Environment]::GetEnvironmentVariable("PATH","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("PATH","User")
}

Require-Command "uv" "Astral.uv" "uv (Python package manager)"
$uvExe = (Get-Command uv).Source

Get-NetTCPConnection -LocalPort $BackendPort -ErrorAction SilentlyContinue |
    ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }

& $uvExe sync --project $ScriptRoot
if ($LASTEXITCODE -ne 0) { Write-Host "ERROR: uv sync failed" -ForegroundColor Red; exit 1 }

Write-Host "  comms-mcp backend  http://127.0.0.1:$BackendPort" -ForegroundColor Gray
$env:MCP_PORT = "$BackendPort"
& $uvExe run --project $ScriptRoot python -m comms_mcp
