# Fleet local biome hook: lint/typecheck the web console when web files change.
# Runs from the repo root (pre-commit passes no filenames; hook scans web_sota).
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Web = Join-Path $Root "web_sota"
if (-not (Test-Path (Join-Path $Web "package.json"))) { exit 0 }

$biome = Join-Path $Web "node_modules\.bin\biome.exe"
if (-not (Test-Path $biome)) {
    Write-Host "[biome] not installed in web_sota — run bootstrap (npm ci). Skipping." -ForegroundColor Yellow
    exit 0
}
& $biome check $Web\src
if ($LASTEXITCODE -ne 0) { exit 1 }
Push-Location $Web
npx --no-install tsc --noEmit -p tsconfig.json
$code = $LASTEXITCODE
Pop-Location
exit $code
