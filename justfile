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

bootstrap:
    uv sync --extra dev
    pre-commit install
    npm ci --prefix web_sota

mcpb-pack:
    powershell.exe -NoProfile -File scripts/mcpb-pack.ps1
