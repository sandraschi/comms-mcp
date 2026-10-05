"""Tests for the LLM provider surface (WEBAPP_SOTA_STANDARDS §VI)."""

from __future__ import annotations

import httpx
import pytest

from comms_mcp.server import app


@pytest.fixture
def client():
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


async def test_providers_shape(client):
    async with client as c:
        r = await c.get("/api/llm/providers")
    assert r.status_code == 200
    providers = r.json()["providers"]
    ids = {p["id"] for p in providers}
    assert {"ollama", "lmstudio", "vllm", "openai", "deepseek", "anthropic"} <= ids
    # key bytes must never be returned
    for p in providers:
        assert "api_key" not in p
        assert "key" not in p


async def test_models_unknown_provider_404(client):
    async with client as c:
        r = await c.get("/api/llm/models", params={"provider": "nope"})
    assert r.status_code == 404


async def test_chat_requires_model(client):
    async with client as c:
        r = await c.post("/api/llm/chat", json={"provider": "ollama", "model": ""})
    assert r.status_code == 400


async def test_chat_unknown_provider(client):
    async with client as c:
        r = await c.post("/api/llm/chat", json={"provider": "nope", "model": "x"})
    assert r.status_code == 404


async def test_settings_shape(client):
    async with client as c:
        r = await c.get("/api/settings/llm")
    assert r.status_code == 200
    body = r.json()
    assert set(body["keys_configured"]) == {"openai", "deepseek", "anthropic"}
    assert isinstance(body["stored_keys"], list)


async def test_onboarding_shape(client):
    async with client as c:
        r = await c.get("/api/llm/onboarding")
    assert r.status_code == 200
    body = r.json()
    assert "recommendation" in body and "mode" in body["recommendation"]
    assert "clouds_configured" in body


async def test_delete_key_unknown_provider(client):
    async with client as c:
        r = await c.delete("/api/settings/llm/key", params={"provider": "nope"})
    assert r.status_code == 404
