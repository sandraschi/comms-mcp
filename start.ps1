#Requires -Version 5.1
<#
.SYNOPSIS
comms-mcp launcher - one entry point: check, install, start, stop.

Implements the One-Click Install UX contract (ONE_CLICK_INSTALL_UX_STANDARD.md):
state machine, -Check (diagnose only), -Yes (no prompts), -NoStart (install
only), -Json (machine-readable check), -Detach (background), -Stop (orderly).

Agents: docs/AI_SETUP.md. Start with:  start.bat -Check -Json
#>
param(
    [switch]$Check,
    [switch]$Json,
    [switch]$Yes,
    [switch]$NoStart,
    [switch]$Detach,
    [switch]$Stop,
    [switch]$BackendOnly,   # compat: backend is the only runtime service
    [switch]$NoBrowser,
    [switch]$Headless       # legacy alias for -NoBrowser
)

$ErrorActionPreference = 'Stop'
$RepoRoot = $PSScriptRoot
$BackendPort = 11205
$FrontendPort = 11204
$SidecarPort = 11208
$HealthUrl = "http://127.0.0.1:$BackendPort/health"
$McpHttpUrl = "http://127.0.0.1:$BackendPort/mcp"
$ConsoleUrl = "http://127.0.0.1:$BackendPort/"
$LogDir = Join-Path $RepoRoot 'logs'
$StartLog = Join-Path $LogDir 'start.log'
$BackendLog = Join-Path $LogDir 'backend.log'
$PidFile = Join-Path $LogDir 'pids.json'
$NeedMB = 500

if ($Headless) { $NoBrowser = $true }
if ($Json -and -not $Check) { $Check = $true }

function Say([string]$Text, [string]$Color = 'Gray') {
    if (-not $Json) { Write-Host $Text -ForegroundColor $Color }
}

if (-not $Yes -and -not $Check -and [Console]::IsInputRedirected) {
    $Yes = $true
    Say 'No interactive input detected - taking recommended defaults (-Yes).' 'DarkGray'
}

# ---------------------------------------------------------------- helpers

function Find-Exe([string]$Name) {
    # Applications only (.exe before .cmd): a .ps1 shim cannot be run from cmd.exe.
    $cmds = @(Get-Command $Name -CommandType Application -ErrorAction SilentlyContinue)
    $exe = $cmds | Where-Object { $_.Source -like '*.exe' } | Select-Object -First 1
    if (-not $exe) { $exe = $cmds | Select-Object -First 1 }
    if ($exe) { return $exe.Source }
    # Fleet-known off-PATH locations.
    $candidates = @(
        "$env:USERPROFILE\.local\bin\$Name.exe",
        "$env:USERPROFILE\.bun\bin\$Name.exe",
        "$env:USERPROFILE\scoop\shims\$Name.exe",
        "$env:LOCALAPPDATA\Microsoft\WindowsApps\$Name.exe"
    )
    foreach ($c in $candidates) { if (Test-Path -LiteralPath $c) { return $c } }
    return $null
}

function Update-SessionPath {
    $env:PATH = [Environment]::GetEnvironmentVariable('PATH', 'Machine') + ';' +
        [Environment]::GetEnvironmentVariable('PATH', 'User')
}

function Get-RepoVersion {
    $py = Join-Path $RepoRoot 'pyproject.toml'
    if (Test-Path -LiteralPath $py) {
        $m = [regex]::Match((Get-Content -LiteralPath $py -Raw), '(?m)^\s*version\s*=\s*"([^"]+)"')
        if ($m.Success) { return $m.Groups[1].Value }
    }
    return '0.0.0'
}

function Get-Listener([int]$Port) {
    $c = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if (-not $c) { return $null }
    $procId = $c.OwningProcess
    $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
    return [ordered]@{ ProcId = $procId; Name = $(if ($proc) { $proc.ProcessName } else { '?' }) }
}

function Test-OurHealth([string]$Url) {
    try {
        $r = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3
        return ($r.StatusCode -eq 200 -and $r.Content -match 'comms-mcp')
    } catch { return $false }
}

function Test-PythonInstalled { return (Test-Path -LiteralPath (Join-Path $RepoRoot '.venv\Scripts\python.exe')) }

# ---------------------------------------------------------------- check

function Invoke-Check {
    $checks = New-Object System.Collections.ArrayList
    function Add-Check($Name, $Status, $Detail, $Fix) {
        [void]$checks.Add([ordered]@{ name = $Name; status = $Status; detail = $Detail; fix = $Fix })
    }

    $os = [Environment]::OSVersion.Version
    $psv = $PSVersionTable.PSVersion
    Add-Check 'os' 'ok' "Windows $($os.Major).$($os.Minor) build $($os.Build), PowerShell $psv" $null

    $wingetExe = Find-Exe 'winget'
    if ($wingetExe) { Add-Check 'winget' 'ok' 'present' $null }
    else { Add-Check 'winget' 'warn' 'missing - needed only if uv must be installed' 'Install "App Installer" from the Microsoft Store' }

    if (Find-Exe 'uv') { Add-Check 'uv' 'ok' 'present' $null }
    elseif ($wingetExe) { Add-Check 'uv' 'install' 'missing - will install astral-sh.uv via winget' $null }
    else { Add-Check 'uv' 'fail' 'missing and winget unavailable' 'Install uv: winget install astral-sh.uv' }

    $pyOk = Test-PythonInstalled
    if ($pyOk) { Add-Check 'python_env' 'ok' '.venv present' $null }
    else { Add-Check 'python_env' 'install' 'will run uv sync (~200 MB, about 1 min the first time)' $null }

    $envFile = Join-Path $RepoRoot '.env'
    if (Test-Path -LiteralPath $envFile) { Add-Check 'env_file' 'ok' '.env present' $null }
    else { Add-Check 'env_file' 'warn' '.env missing - no channel can send until configured' 'copy .env.example .env, then set a channel token + allowlist; see docs/ONBOARDING.md' }

    $consoleDist = Test-Path -LiteralPath (Join-Path $RepoRoot 'web_sota\dist\index.html')
    if ($consoleDist) { Add-Check 'console' 'ok' 'web_sota/dist built (served on :11205)' $null }
    else { Add-Check 'console' 'info' 'web_sota/dist not built - MCP works, web console unavailable' 'Optional: cd web_sota; bun install; bun run build' }

    $drive = (Get-Item -LiteralPath $RepoRoot).PSDrive
    $freeMB = [int]($drive.Free / 1MB)
    if ($pyOk) { Add-Check 'disk' 'ok' "$freeMB MB free on $($drive.Name):" $null }
    elseif ($freeMB -ge $NeedMB) { Add-Check 'disk' 'ok' "needs ~$NeedMB MB, $freeMB MB free on $($drive.Name):" $null }
    else { Add-Check 'disk' 'fail' "needs ~$NeedMB MB, only $freeMB MB free on $($drive.Name):" 'Free disk space or clone to another drive' }

    $running = $false
    $owner = Get-Listener $BackendPort
    if (-not $owner) { Add-Check 'port_11205' 'ok' 'free (backend)' $null }
    elseif (Test-OurHealth $HealthUrl) {
        Add-Check 'port_11205' 'ok' "comms-mcp backend already running (pid $($owner.ProcId))" $null
        $running = $true
    } else {
        Add-Check 'port_11205' 'fail' "held by another program: pid $($owner.ProcId) ($($owner.Name))" 'Close that program, or ask the user; never kill it without asking'
    }

    $sidecarOwner = Get-Listener $SidecarPort
    if (-not $sidecarOwner) { Add-Check 'port_11208' 'info' 'free (WhatsApp sidecar, optional)' $null }
    else { Add-Check 'port_11208' 'ok' "sidecar present (pid $($sidecarOwner.ProcId))" $null }

    $fails = @($checks | Where-Object { $_.status -eq 'fail' })
    $warns = @($checks | Where-Object { $_.status -eq 'warn' })
    if ($fails.Count -gt 0) { $verdict = "BLOCKED: $($fails[0].detail)"; $code = 1 }
    elseif ($warns.Count -gt 0) { $verdict = 'READY WITH WARNINGS'; $code = 2 }
    else { $verdict = 'READY'; $code = 0 }

    return [ordered]@{
        repo      = 'comms-mcp'
        version   = Get-RepoVersion
        verdict   = $verdict
        exit_code = $code
        installed = $pyOk
        running   = $running
        urls      = [ordered]@{ console = $ConsoleUrl; health = $HealthUrl; mcp_http = $McpHttpUrl }
        logs      = [ordered]@{ start = $StartLog; backend = $BackendLog }
        checks    = $checks
    }
}

function Show-Report($Report) {
    if ($Json) { $Report | ConvertTo-Json -Depth 5; return }
    Say "=== comms-mcp $($Report.version) - check ===" 'Cyan'
    foreach ($c in $Report.checks) {
        $color = switch ($c.status) { 'ok' { 'Green' } 'install' { 'Cyan' } 'warn' { 'Yellow' } 'fail' { 'Red' } default { 'Gray' } }
        Say ('  [{0,-7}] {1,-11} {2}' -f $c.status, $c.name, $c.detail) $color
        if ($c.fix -and $c.status -ne 'ok') { Say "            fix: $($c.fix)" 'DarkGray' }
    }
    $vColor = if ($Report.exit_code -eq 0) { 'Green' } elseif ($Report.exit_code -eq 2) { 'Yellow' } else { 'Red' }
    Say "Verdict: $($Report.verdict)" $vColor
}

# ---------------------------------------------------------------- stop

function Stop-Tree([int]$ProcId) { & taskkill.exe /PID $ProcId /T /F 2>&1 | Out-Null }

function Invoke-Stop {
    $stopped = 0
    if (Test-Path -LiteralPath $PidFile) {
        $saved = Get-Content -LiteralPath $PidFile -Raw | ConvertFrom-Json
        $entry = $saved.backend
        if ($entry) {
            $proc = Get-Process -Id $entry.pid -ErrorAction SilentlyContinue
            # PID-reuse guard: only stop the exact process we started.
            if ($proc -and $proc.StartTime.ToString('o') -eq $entry.started) { Stop-Tree $entry.pid; $stopped++ }
        }
        Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
    }
    $owner = Get-Listener $BackendPort
    if ($owner -and (Test-OurHealth $HealthUrl)) {
        $parentId = (Get-CimInstance Win32_Process -Filter "ProcessId=$($owner.ProcId)" -ErrorAction SilentlyContinue).ParentProcessId
        $parent = if ($parentId) { Get-Process -Id $parentId -ErrorAction SilentlyContinue } else { $null }
        if ($parent -and $parent.ProcessName -eq 'nssm') {
            Say "Port $BackendPort is served by an NSSM service - stop it with sc.exe stop comms-mcp, not here." 'Yellow'
        } elseif ($stopped -eq 0) {
            # Orderly path for an instance we did not start: ask it to exit.
            try { Invoke-WebRequest -Uri "http://127.0.0.1:$BackendPort/api/shutdown" -Method Post -UseBasicParsing -TimeoutSec 5 | Out-Null; $stopped++ } catch { }
        }
    }
    Say "Stopped $stopped instance(s)." 'Green'
}

# ---------------------------------------------------------------- install

function Require-Command([string]$Cmd, [string]$WingetId, [string]$Label) {
    if (Find-Exe $Cmd) { return }
    Say "$Label not found - installing via winget ($WingetId) ..." 'Yellow'
    if (-not (Find-Exe 'winget')) {
        Say "ERROR: winget unavailable. Install $Label manually (winget id $WingetId), then rerun start.bat." 'Red'
        exit 1
    }
    & winget install --id $WingetId --exact --source winget --silent --accept-source-agreements --accept-package-agreements --disable-interactivity
    Update-SessionPath
    if (-not (Find-Exe $Cmd)) {
        Say "Installed $Label but '$Cmd' is not on PATH yet. Open a new terminal and rerun start.bat (safe)." 'Yellow'
        exit 1
    }
}

function Invoke-Install {
    Require-Command 'uv' 'astral-sh.uv' 'uv'
    $uvExe = Find-Exe 'uv'
    # Only sync when the venv is missing or cannot import the server. A bare
    # `uv sync` on an existing dev checkout would strip the optional `dev`
    # extras (ruff/pyright/pytest) and break `just ci`; the import probe is the
    # "incomplete" signal from the one-click state machine.
    $needsSync = -not (Test-PythonInstalled)
    if (-not $needsSync) {
        & $uvExe run --project $RepoRoot python -c "import comms_mcp.server" 2>$null | Out-Null
        if ($LASTEXITCODE -ne 0) { $needsSync = $true }
    }
    if ($needsSync) {
        Say 'Installing Python dependencies (uv sync). First time about 1 minute; the window may sit quiet. This is normal.' 'Cyan'
        & $uvExe sync --project $RepoRoot
        if ($LASTEXITCODE -ne 0) { Say 'ERROR: uv sync failed (see above). Rerunning start.bat is safe.' 'Red'; exit 1 }
        & $uvExe run --project $RepoRoot python -c "import comms_mcp.server" 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) {
            Say 'ERROR: import check failed - see the traceback above. Attach logs\start.log to an issue.' 'Red'
            exit 1
        }
    }
    Say 'Install OK.' 'Green'
}

# ---------------------------------------------------------------- start

function Start-Hidden([string]$Exe, [string[]]$ArgList, [string]$WorkDir, [string]$Log, [hashtable]$EnvVars) {
    # Win32_Process.Create, not Start-Process: Start-Process children inherit the
    # caller's stdout pipe, so `start.bat -Detach` would block until the server exits.
    $quoted = ($ArgList | ForEach-Object { if ($_ -match '\s') { '"' + $_ + '"' } else { $_ } }) -join ' '
    $sets = ($EnvVars.GetEnumerator() | ForEach-Object { "set `"$($_.Key)=$($_.Value)`"" }) -join ' && '
    $cmdLine = "cmd.exe /d /s /c `"$sets && `"$Exe`" $quoted > `"$Log`" 2> `"$Log.err`"`""
    $startup = New-CimInstance -ClassName Win32_ProcessStartup -ClientOnly -Property @{ ShowWindow = [uint16]0 }
    $result = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
        CommandLine = $cmdLine; CurrentDirectory = $WorkDir; ProcessStartupInformation = $startup
    }
    if ($result.ReturnValue -ne 0) { throw "Could not start $Exe (Win32_Process.Create returned $($result.ReturnValue))" }
    return Get-Process -Id $result.ProcessId
}

function Wait-Until([scriptblock]$Probe, [int]$Seconds, [System.Diagnostics.Process]$Proc, [string]$What) {
    for ($i = 1; $i -le $Seconds; $i++) {
        if (& $Probe) { return $true }
        if ($Proc.HasExited) { return $false }
        if ($i % 10 -eq 0) { Say "  still waiting for $What ($i s) - first start can take ~30 s ..." 'DarkGray' }
        Start-Sleep -Seconds 1
    }
    return $false
}

function Show-LogTail([string]$Log) {
    foreach ($f in @($Log, "$Log.err")) {
        if (Test-Path -LiteralPath $f) { Get-Content -LiteralPath $f -Tail 15 | ForEach-Object { Say "  | $_" 'DarkGray' } }
    }
}

function Invoke-Start {
    $uvExe = Find-Exe 'uv'
    $backendEnv = @{ MCP_PORT = "$BackendPort"; MCP_HOST = '127.0.0.1'; PYTHONUNBUFFERED = '1' }
    Say "Starting comms-mcp backend on 127.0.0.1:$BackendPort ..." 'Cyan'
    $backendArgs = @('run', '--project', $RepoRoot, 'python', '-m', 'comms_mcp')
    $backend = Start-Hidden $uvExe $backendArgs $RepoRoot $BackendLog $backendEnv
    if (-not (Wait-Until { Test-OurHealth $HealthUrl } 90 $backend 'backend')) {
        Say "ERROR: backend did not become healthy. Last log lines ($BackendLog):" 'Red'
        Show-LogTail $BackendLog
        Stop-Tree $backend.Id
        Say 'Rerunning start.bat is safe. If it fails again, attach logs\backend.log to an issue.' 'Yellow'
        exit 1
    }
    $pidRecord = [ordered]@{ backend = [ordered]@{ pid = $backend.Id; started = $backend.StartTime.ToString('o') } }
    $pidRecord | ConvertTo-Json | Set-Content -LiteralPath $PidFile -Encoding ASCII

    Say ''
    Say '=== comms-mcp is running ===' 'Green'
    if (Test-Path -LiteralPath (Join-Path $RepoRoot 'web_sota\dist\index.html')) { Say "  Console   : $ConsoleUrl" 'Green' }
    Say "  MCP (HTTP): $McpHttpUrl" 'Green'
    Say "  Health    : $HealthUrl" 'Green'
    Say "  Logs      : $LogDir" 'Gray'
    Say '  Stop      : stop.bat  (or start.bat -Stop)' 'Gray'

    if (-not $NoBrowser) { Start-Process $ConsoleUrl }
}

# ---------------------------------------------------------------- main

if ($Check) {
    $report = Invoke-Check
    Show-Report $report
    exit $report.exit_code
}

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

if ($Stop) { Invoke-Stop; exit 0 }

try { Start-Transcript -LiteralPath $StartLog -Force | Out-Null } catch { Say "(could not write $StartLog)" 'DarkGray' }
Say "=== comms-mcp $(Get-RepoVersion) ===" 'Cyan'
Say "Log of this run: $StartLog" 'DarkGray'

$report = Invoke-Check
if ($report.running) {
    Say 'comms-mcp is already running - nothing to do.' 'Green'
    Say "  MCP (HTTP): $McpHttpUrl" 'Green'
    Say '  Stop it with start.bat -Stop, then rerun start.bat to pick up changes.' 'Gray'
    exit 0
}
if ($report.exit_code -eq 1) {
    Show-Report $report
    Say 'Fix the item above, then rerun start.bat (safe).' 'Yellow'
    exit 1
}

Invoke-Install
if ($NoStart) {
    Say 'Installed. Start it with start.bat (or start.bat -Detach for background).' 'Green'
    exit 0
}

Invoke-Start
if ($Detach) { exit 0 }

Say ''
Say 'Press Ctrl+C to stop this window. The server keeps running; stop.bat stops it.' 'Yellow'
try {
    while ($true) {
        Start-Sleep -Seconds 2
        if (-not (Test-OurHealth $HealthUrl)) {
            Say 'Backend stopped. Last log lines:' 'Red'
            Show-LogTail $BackendLog
            break
        }
    }
} finally {
    Invoke-Stop
}
