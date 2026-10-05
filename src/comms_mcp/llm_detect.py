"""LLM_DETECT_VERSION = 1

GPU detection, VRAM tiering, and model recommendation for local LLM onboarding.

Canonical source: godot-mcp/src/godot_mcp/services/llm_detect.py
Mirrored here for fleet reuse. Update both files when changing the tier table.

Usage:
    from detect import detect, recommend
    result = detect()
    rec = recommend(result)
    print(rec.model)  # e.g. "gemma4:12b"
"""

from __future__ import annotations

import json as _json
import logging
import subprocess
import urllib.request
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("llm-detect")

TIERS: list[tuple[int, int, str, list[str]]] = [
    (32000, 5, "Monster", ["qwen2.5-coder:32b-instruct-q4_K_M", "deepseek-r1:32b", "gemma4:26b"]),
    (20000, 4, "High-end", ["gemma4:12b", "qwen2.5-coder:14b", "llama3.1:8b"]),
    (14000, 3, "Mid", ["qwen2.5-coder:7b", "mistral:7b", "llama3.2:3b"]),
    (10000, 2, "Entry", ["llama3.2:3b", "qwen2.5-coder:1.5b"]),
    (6000, 1, "Minimal", ["llama3.2:1b", "tinyllama:latest", "gemma3:1b"]),
]

CLOUD_DEFAULTS = {
    "provider": "deepseek",
    "model": "deepseek-v4-flash",
    "base_url": "https://api.deepseek.com/v1",
    "cost_per_mtok": 0.15,
}


@dataclass
class GpuInfo:
    available: bool = False
    name: str = ""
    vram_mb: int = 0
    vram_gb: float = 0.0
    driver: str = ""

    @property
    def tier(self) -> int:
        for min_vram, tier, _l, _m in TIERS:
            if self.vram_mb >= min_vram:
                return tier
        return 0

    @property
    def tier_label(self) -> str:
        for min_vram, _t, label, _m in TIERS:
            if self.vram_mb >= min_vram:
                return label
        return "Cloud-only"

    @property
    def recommended_models(self) -> list[str]:
        for min_vram, _t, _l, models in TIERS:
            if self.vram_mb >= min_vram:
                return models
        return []


@dataclass
class OllamaInfo:
    available: bool = False
    # 127.0.0.1, not localhost: on some Windows setups localhost resolves
    # to ::1 where nothing listens (measured 2026-09-21: LM Studio 404s
    # localhost:1234 while 127.0.0.1:1234 works). Mirror: godot-mcp.
    url: str = "http://127.0.0.1:11434"
    models: list[str] = field(default_factory=list)
    error: str = ""


@dataclass
class DetectResult:
    gpu: GpuInfo = field(default_factory=GpuInfo)
    ollama: OllamaInfo = field(default_factory=OllamaInfo)
    mode: str = "local"


@dataclass
class RecommendResult:
    mode: str = "local"
    tier: int = 0
    tier_label: str = ""
    vram_gb: float = 0.0
    model: str = ""
    installed: bool = False
    cloud_fallback: dict[str, Any] = field(default_factory=lambda: dict(CLOUD_DEFAULTS))
    message: str = ""


def detect_gpu() -> GpuInfo:
    try:
        out = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,driver_version",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if out.returncode != 0:
            return GpuInfo()
        parts = [p.strip() for p in out.stdout.strip().split(", ")]
        vram = int(parts[1])
        return GpuInfo(
            available=True,
            name=parts[0],
            vram_mb=vram,
            vram_gb=round(vram / 1024, 1),
            driver=parts[2] if len(parts) > 2 else "",
        )
    except FileNotFoundError:
        return GpuInfo()
    except (ValueError, IndexError, subprocess.TimeoutExpired) as e:
        logger.debug("GPU detection failed: %s", e)
        return GpuInfo()


def check_ollama(url: str = "http://127.0.0.1:11434") -> OllamaInfo:
    try:
        resp = urllib.request.urlopen(f"{url}/api/tags", timeout=3)
        data = _json.loads(resp.read())
        models = [m["name"] for m in data.get("models", [])]
        return OllamaInfo(available=True, url=url, models=models)
    except Exception as e:
        return OllamaInfo(error=str(e))


def detect() -> DetectResult:
    gpu = detect_gpu()
    ollama = check_ollama()
    return DetectResult(
        gpu=gpu, ollama=ollama, mode="local" if (gpu.available or ollama.available) else "cloud"
    )


def recommend(result: DetectResult | None = None) -> RecommendResult:
    if result is None:
        result = detect()
    out = RecommendResult(mode=result.mode, cloud_fallback=dict(CLOUD_DEFAULTS))
    if not result.gpu.available and not result.ollama.available:
        out.mode = "cloud"
        out.message = f"No local GPU or Ollama. Configure {CLOUD_DEFAULTS['provider']} API key."
        return out
    if result.ollama.available and result.ollama.models:
        installed_set = set(result.ollama.models)
        for min_vram, tier_num, label, models in TIERS:
            if result.gpu.available and result.gpu.vram_mb < min_vram:
                continue
            for m in models:
                if m in installed_set:
                    out.tier, out.tier_label, out.model, out.installed = tier_num, label, m, True
                    out.vram_gb = result.gpu.vram_gb
                    out.message = f"Using installed {m} ({label})"
                    return out
    if result.gpu.available:
        for min_vram, tier_num, label, models in TIERS:
            if result.gpu.vram_mb >= min_vram:
                out.tier, out.tier_label, out.model = tier_num, label, models[0]
                out.vram_gb = result.gpu.vram_gb
                out.message = (
                    f"GPU {result.gpu.name} ({result.gpu.vram_gb} GB). Run: ollama pull {models[0]}"
                )
                return out
    if result.ollama.available:
        models = TIERS[-1][3]
        for m in models:
            if m in set(result.ollama.models):
                out.tier, out.tier_label, out.model, out.installed = 1, "Minimal", m, True
                out.message = f"CPU mode using {m}"
                return out
        out.tier, out.tier_label, out.model = 1, "Minimal", models[0]
        out.message = f"CPU mode. Run: ollama pull {models[0]}"
        return out
    return out
