# Install comms-mcp backend + WhatsApp sidecar as NSSM services.
# Run elevated:  powershell -ExecutionPolicy Bypass -File scripts\install-services.ps1
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$nssm = "C:\Users\sandr\AppData\Local\Microsoft\WinGet\Links\nssm.exe"
if (-not (Test-Path $nssm)) { $nssm = "nssm.exe" }
$uv = (Get-Command uv).Source
$node = (Get-Command node).Source

$services = @(
    @{
        Name    = "comms-mcp"
        Cmd     = "`"$uv`" run --project `"$Root`" python -m comms_mcp"
        Dir     = $Root
        Env     = "MCP_PORT=11205"
        Log     = Join-Path $Root "logs"
    },
    @{
        Name    = "comms-mcp-wa"
        Cmd     = "`"$node`" index.js"
        Dir     = Join-Path $Root "wa-sidecar"
        Env     = "WA_PORT=10709;COMMS_INBOUND_WEBHOOK=http://127.0.0.1:11205/api/v1/inbound/wa"
        Log     = Join-Path $Root "logs"
    }
)

foreach ($svc in $services) {
    & $nssm stop $svc.Name 2>$null | Out-Null
    & $nssm remove $svc.Name confirm 2>$null | Out-Null
    New-Item -ItemType Directory -Force -Path $svc.Log | Out-Null
    & $nssm install $svc.Name $svc.Cmd | Out-Null
    & $nssm set $svc.Name AppDirectory $svc.Dir
    & $nssm set $svc.Name AppEnvironmentExtra $svc.Env
    & $nssm set $svc.Name AppStdout (Join-Path $svc.Log "$($svc.Name).out.log")
    & $nssm set $svc.Name AppStderr (Join-Path $svc.Log "$($svc.Name).err.log")
    & $nssm set $svc.Name AppExit Default Restart
    & $nssm set $svc.Name AppRestartDelay 5000
    & $nssm set $svc.Name Start SERVICE_AUTO_START
    & $nssm start $svc.Name
    Write-Host "  $($svc.Name) installed + started" -ForegroundColor Green
}
Write-Host "Services installed. Console: http://127.0.0.1:11205" -ForegroundColor Cyan

