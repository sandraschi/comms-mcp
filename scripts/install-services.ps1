# Install comms-mcp backend + WhatsApp sidecar as NSSM services.
# Run elevated:  powershell -ExecutionPolicy Bypass -File scripts\install-services.ps1
#
# Notes (v0.8):
# - The backend auto-manages sidecars on boot (adopt-if-alive, opt-in
#   autostart via COMMS_SIDECAR_AUTOSTART). The comms-mcp-wa service below is
#   the standalone/always-on path — pick ONE manager per sidecar, not both.
#   If the backend owns the sidecar, remove the wa service (nssm remove).
# - Signal needs no NSSM service: the backend runs it as a Docker container
#   with --restart unless-stopped, so Docker restarts it, not NSSM.
# - COMMS_INBOUND_SECRET is passed through to the wa sidecar so the webhook
#   check matches the backend (was missing -> 401 on every inbound with a
#   secret set).
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
        # Split-brain guard: LocalSystem has its own profile/temp. Pin the
        # user profile + an absolute DB path so the service and interactive
        # runs share one store (TRAPS_AND_PITFALLS NSSM split-brain).
        Env     = "MCP_PORT=11205;USERPROFILE=$env:USERPROFILE;COMMS_DB_PATH=$Root\data\comms.db"
        Log     = Join-Path $Root "logs"
    },
    @{
        Name    = "comms-mcp-wa"
        Cmd     = "`"$node`" index.js"
        Dir     = Join-Path $Root "wa-sidecar"
        Env     = "WA_PORT=11208;COMMS_INBOUND_WEBHOOK=http://127.0.0.1:11205/api/v1/inbound/wa;COMMS_INBOUND_SECRET=$env:COMMS_INBOUND_SECRET"
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
