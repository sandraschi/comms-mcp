param([switch]$Headless, [switch]$BackendOnly, [switch]$FrontendOnly)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$BackendPort = 11028
$FrontendPort = 11029

function Require-Command {
    param([string]$Cmd, [string]$WingetId, [string]$Label)
    if (Get-Command $Cmd -ErrorAction SilentlyContinue) { return }
    Write-Host "  $Label not found - installing via winget ..." -ForegroundColor Yellow
    winget install --id $WingetId --silent --accept-source-agreements --accept-package-agreements
    $env:PATH = [System.Environment]::GetEnvironmentVariable("PATH","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("PATH","User")
}

if (-not $FrontendOnly) {
    Require-Command "uv" "Astral.uv" "uv (Python package manager)"
    $uvExe = (Get-Command uv).Source
    Get-NetTCPConnection -LocalPort $BackendPort -ErrorAction SilentlyContinue |
        ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
    & $uvExe sync --project $Root
    if ($LASTEXITCODE -ne 0) { Write-Host "ERROR: uv sync failed" -ForegroundColor Red; exit 1 }
    & $uvExe run --project $Root python -c "import comms_mcp.server; print('  [ok] backend import OK')"
    if ($LASTEXITCODE -ne 0) { exit 1 }
    $env:MCP_PORT = "$BackendPort"
    Start-Process -NoNewWindow -FilePath $uvExe -ArgumentList "run --project $Root python -m comms_mcp"
    $ready = $false
    for ($i = 0; $i -lt 45; $i++) {
        try {
            $r = Invoke-WebRequest -Uri "http://127.0.0.1:$BackendPort/health" -TimeoutSec 2 -UseBasicParsing -ErrorAction SilentlyContinue
            if ($r.StatusCode -eq 200) { $ready = $true; break }
        } catch {}
        Start-Sleep 1
    }
    if (-not $ready) { Write-Host "ERROR: backend health timed out on :$BackendPort" -ForegroundColor Red; exit 1 }
}

if (-not $BackendOnly) {
    Require-Command "node" "OpenJS.NodeJS.LTS" "Node.js LTS"
    Require-Command "npm" "OpenJS.NodeJS.LTS" "npm"
    $npmExe = (Get-Command npm).Source
    $WebRoot = Join-Path $Root "web_sota"
    if (-not (Test-Path (Join-Path $WebRoot "node_modules"))) {
        Push-Location $WebRoot
        & $npmExe install --prefer-offline 2>&1
        if ($LASTEXITCODE -ne 0) { Pop-Location; Write-Host "ERROR: npm install failed" -ForegroundColor Red; exit 1 }
        Pop-Location
    }
    $viteLocal = Join-Path $WebRoot "node_modules\.bin\vite"
    if (-not (Test-Path $viteLocal)) {
        Write-Host "ERROR: vite missing from node_modules" -ForegroundColor Red; exit 1
    }
    Get-NetTCPConnection -LocalPort $FrontendPort -ErrorAction SilentlyContinue |
        ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
    Start-Process -NoNewWindow -FilePath "npx" -ArgumentList "vite --port $FrontendPort --host" -WorkingDirectory $WebRoot
    if (-not $Headless) {
        Start-Sleep 4
        Start-Process "http://127.0.0.1:$FrontendPort"
    }
}

Write-Host "  comms-mcp  backend :$BackendPort / console :$FrontendPort" -ForegroundColor Cyan
while ($true) { Start-Sleep 10 }
