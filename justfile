set shell := ["powershell.exe", "-NoProfile", "-Command"]

serve:
    uv run python -m comms_mcp

lint:
    uv run ruff check src/ tests/

fmt:
    uv run ruff format src/ tests/

fix:
    uv run ruff check --fix src/ tests/
    uv run ruff format src/ tests/

test:
    uv run pytest -q

types:
    uv run pyright src/

ci:
    uv run ruff check src/ tests/
    uv run ruff format src/ tests/ --check
    uv run pyright src/
    uv run pytest -q
    Push-Location web_sota; & "$env:USERPROFILE\.bun\bin\bun.exe" run biome:ci; & "$env:USERPROFILE\.bun\bin\bun.exe" run typecheck; Pop-Location

bootstrap:
    uv sync --extra dev
    pre-commit install
    Push-Location web_sota; & "$env:USERPROFILE\.bun\bin\bun.exe" install; Pop-Location

e2e:
    Push-Location web_sota; & "$env:USERPROFILE\.bun\bin\bun.exe" run e2e; Pop-Location

cua-webapp-test: e2e

mcpb-pack:
    powershell.exe -NoProfile -File scripts/mcpb-pack.ps1
