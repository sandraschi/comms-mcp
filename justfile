set shell := ["powershell.exe", "-NoProfile", "-Command"]

serve:
    uv run python -m comms_mcp

lint:
    uv run ruff check src/ tests/

fix:
    uv run ruff check --fix src/ tests/
    uv run ruff format src/ tests/

test:
    uv run pytest -q

types:
    uv run pyright src/
