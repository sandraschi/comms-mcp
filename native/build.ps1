$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$RepoName = "comms-mcp"
$Triple = "x86_64-pc-windows-msvc"
$ResourceDir = "$PSScriptRoot\resources"
$DevDir = "$PSScriptRoot\binaries"
New-Item -ItemType Directory -Force -Path $ResourceDir, $DevDir | Out-Null

Write-Host "=== $RepoName Tauri Release Build ===" -ForegroundColor Cyan
$env:Path = "$env:USERPROFILE\.bun\bin;$env:USERPROFILE\.cargo\bin;$env:Path"

# Step 1: frontend (web_sota) - bun + tsc gate
$frontend = Join-Path $Root "web_sota"
if (Test-Path "$frontend\package.json") {
    Write-Host "-> [1/4] Building frontend (web_sota)..." -ForegroundColor Yellow
    Push-Location $frontend
    & bun install
    if ($LASTEXITCODE -ne 0) { throw "bun install failed" }

    Write-Host "  tsc --noEmit..." -ForegroundColor Gray
    $tscOut = & bunx tsc --noEmit 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host $tscOut
        throw "TypeScript compilation failed - fix all errors before building NSIS"
    }
    & bun run build
    if ($LASTEXITCODE -ne 0) { throw "Frontend build failed" }
    Pop-Location
}

# Step 2: PyInstaller backend (onefile) - MUST use the project venv, never `uv run pyinstaller`
Write-Host "-> [2/4] PyInstaller backend..." -ForegroundColor Yellow
$specFile = "$Root\comms-mcp-backend.spec"
if (-not (Test-Path $specFile)) { throw "spec file not found at $specFile" }
$pyiExe = "$Root\.venv\Scripts\pyinstaller.exe"
if (-not (Test-Path $pyiExe)) {
    Write-Host "  pyinstaller missing from project venv - adding as dev dependency" -ForegroundColor Yellow
    Push-Location $Root
    & uv add --dev pyinstaller pefile altgraph
    & uv sync
    Pop-Location
    if (-not (Test-Path $pyiExe)) { throw "pyinstaller still missing at $pyiExe" }
}
Remove-Item "$Root\dist\$RepoName-backend.exe" -Force -ErrorAction SilentlyContinue
Push-Location $Root
& $pyiExe "$specFile" --clean --noconfirm
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed with exit code $LASTEXITCODE" }
Pop-Location

# Step 3: Embed in Tauri resources (+ dev fallback)
Write-Host "-> [3/4] Embedding backend..." -ForegroundColor Yellow
$src = "$Root\dist\$RepoName-backend.exe"
if (-not (Test-Path $src)) { throw "Backend exe not found at $src - PyInstaller step failed" }
$sizeMB = [math]::Round((Get-Item $src).Length / 1MB, 1)
if ($sizeMB -lt 5) { throw "Backend exe is only $sizeMB MB - PyInstaller produced a runt (see pitfall: build gate >=5 MB)" }
Copy-Item $src "$ResourceDir\$RepoName-backend.exe" -Force
Copy-Item $src "$DevDir\$RepoName-backend-$Triple.exe" -Force
Write-Host "  Backend exe: $sizeMB MB" -ForegroundColor Green

# Step 4: Single NSIS installer
Write-Host "-> [4/4] Tauri NSIS bundle..." -ForegroundColor Yellow
Push-Location $PSScriptRoot
& bunx @tauri-apps/cli build --bundles nsis
if ($LASTEXITCODE -ne 0) { throw "Tauri build failed with exit code $LASTEXITCODE" }
Pop-Location

# Remove stale flat shadow copy (pitfall F: resources/ wins, flat copy confuses)
Remove-Item -Force "$PSScriptRoot\target\release\$RepoName-backend.exe" -ErrorAction SilentlyContinue

# Stage NSIS installer to repo dist/
$distDir = Join-Path $Root "dist"
New-Item -ItemType Directory -Force -Path $distDir | Out-Null
$nsisDir = "$PSScriptRoot\target\release\bundle\nsis"
if (Test-Path $nsisDir) { Copy-Item "$nsisDir\*-setup.exe" "$distDir\" -Force }

Write-Host "=== Build complete ===" -ForegroundColor Green
Write-Host "Ship: $nsisDir\*-setup.exe"
