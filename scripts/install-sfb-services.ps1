# Install remaining SFB services as NSSM: comms-mcp, comms-mcp-wa,
# fritz-console, cline-mcp. Run elevated:
#   powershell -ExecutionPolicy Bypass -File scripts\install-sfb-services.ps1
$ErrorActionPreference = "Stop"
$nssm = "C:\Users\sandr\AppData\Local\Microsoft\WinGet\Links\nssm.exe"
if (-not (Test-Path $nssm)) { $nssm = "nssm.exe" }
$uv = (Get-Command uv).Source
$node = (Get-Command node).Source

# comms-mcp backend + wa-sidecar (delegates to the comms installer logic)
& (Join-Path $PSScriptRoot "install-services.ps1")

$services = @(
    @{
        Name = "fritz-console"
        Cmd  = "`"$uv`" run --project D:\Dev\repos\fleet-agent-mcp python -m fleet_agent.console"
        Dir  = "D:\Dev\repos\fleet-agent-mcp"
        Env  = ""
        Log  = "D:\Dev\repos\fleet-agent-mcp\logs"
    },
    @{
        Name = "cline-mcp"
        Cmd  = "`"$node`" dist/index.js"
        Dir  = "D:\Dev\repos\cline-mcp"
        Env  = "CLINE_MCP_HTTP_PORT=11103"
        Log  = "D:\Dev\repos\cline-mcp\logs"
    }
)

foreach ($svc in $services) {
    & $nssm stop $svc.Name 2>$null | Out-Null
    & $nssm remove $svc.Name confirm 2>$null | Out-Null
    New-Item -ItemType Directory -Force -Path $svc.Log | Out-Null
    & $nssm install $svc.Name $svc.Cmd | Out-Null
    & $nssm set $svc.Name AppDirectory $svc.Dir
    if ($svc.Env) { & $nssm set $svc.Name AppEnvironmentExtra $svc.Env }
    & $nssm set $svc.Name AppStdout (Join-Path $svc.Log "$($svc.Name).out.log")
    & $nssm set $svc.Name AppStderr (Join-Path $svc.Log "$($svc.Name).err.log")
    & $nssm set $svc.Name AppExit Default Restart
    & $nssm set $svc.Name AppRestartDelay 5000
    & $nssm set $svc.Name Start SERVICE_AUTO_START
    & $nssm start $svc.Name
    Write-Host "  $($svc.Name) installed + started" -ForegroundColor Green
}
Write-Host "SFB services installed: comms-mcp, comms-mcp-wa, fritz-console, cline-mcp" -ForegroundColor Cyan
