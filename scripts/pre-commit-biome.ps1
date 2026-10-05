# Fleet local biome hook: lint/typecheck the web console when web files change.
# Runs from the repo root (pre-commit passes no filenames; hook scans web_sota).
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Web = Join-Path $Root "web_sota"
if (-not (Test-Path (Join-Path $Web "package.json"))) { exit 0 }

$binDir = Join-Path $Web "node_modules\.bin"
$biome = @("biome.exe", "biome.cmd", "biome.ps1") | ForEach-Object {
    Join-Path $binDir $_
} | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $biome) {
    Write-Host "[biome] not installed in web_sota - run bootstrap (npm ci). Skipping." -ForegroundColor Yellow
    exit 0
}
# Biome resolves the project root from the working directory, so run it with
# web_sota as CWD (else it flags web_sota/biome.json as nested).
Push-Location $Web
& $biome check src/
$code = $LASTEXITCODE
Pop-Location
if ($code -ne 0) { exit $code }
Push-Location $Web
npx --no-install tsc --noEmit -p tsconfig.json
$code = $LASTEXITCODE
Pop-Location
exit $code
