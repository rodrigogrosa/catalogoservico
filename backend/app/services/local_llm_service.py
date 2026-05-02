from __future__ import annotations

import base64
import json
import time
from pathlib import Path
from typing import Any

import httpx

from app.core.config import Settings, get_settings

_RUNTIME_CACHE_TTL = 60.0  # seconds between Ollama availability probes


class LocalLlmService:
    def __init__(self, settings: Settings | None = None, client: httpx.Client | None = None) -> None:
        self.settings = settings or get_settings()
        timeout_seconds = min(float(self.settings.ollama_timeout_seconds), 12.0)
        self.client = client or httpx.Client(
            timeout=httpx.Timeout(timeout_seconds, connect=3.0, read=timeout_seconds, write=10.0, pool=5.0)
        )
        self._runtime_cache: dict[str, Any] | None = None
        self._runtime_cache_at: float = 0.0

    def is_enabled(self) -> bool:
        return self.settings.ollama_enabled

    def is_available(self) -> bool:
        if not self.is_enabled():
            return False
        try:
            response = self.client.get(f"{self.settings.ollama_base_url}/api/tags")
            response.raise_for_status()
            return True
        except Exception:
            return False

    def has_model(self, model_name: str | None) -> bool:
        if not self.is_enabled() or not model_name:
            return False
        try:
            response = self.client.get(f"{self.settings.ollama_base_url}/api/tags")
            response.raise_for_status()
            payload = response.json()
            models = payload.get("models") or []
            known = {str(model.get("name") or "") for model in models if isinstance(model, dict)}
            return model_name in known
        except Exception:
            return False

    def is_vision_available(self) -> bool:
        return self.has_model(self.settings.ollama_vision_model)

    def describe_runtime(self) -> dict[str, Any]:
        # Cache the result for _RUNTIME_CACHE_TTL seconds so repeated calls
        # during upload processing don't each make 2 blocking HTTP requests to
        # Ollama (is_available + is_vision_available), which could add up to
        # 30 s of latency per upload when Ollama is unreachable.
        now = time.monotonic()
        if self._runtime_cache is not None and (now - self._runtime_cache_at) < _RUNTIME_CACHE_TTL:
            return self._runtime_cache
        result = {
            "enabled": self.is_enabled(),
            "available": self.is_available(),
            "base_url": self.settings.ollama_base_url,
            "model": self.settings.ollama_model,
            "vision_model": self.settings.ollama_vision_model,
            "vision_available": self.is_vision_available(),
        }
        self._runtime_cache = result
        self._runtime_cache_at = now
        return result

    def generate_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        fallback: dict[str, Any],
    ) -> dict[str, Any]:
        if not self.is_available():
            return fallback

        prompt = (
            f"{system_prompt}\n\n"
            "Responda apenas JSON valido com as chaves esperadas. "
            "Nao use markdown, nao explique o raciocinio.\n\n"
            f"{user_prompt}"
        )
        try:
            response = self.client.post(
                f"{self.settings.ollama_base_url}/api/generate",
                json={
                    "model": self.settings.ollama_model,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json",
                    "options": {"temperature": 0.2},
                },
            )
            response.raise_for_status()
            payload = response.json()
            text = payload.get("response", "").strip()
            if not text:
                return fallback
            data = json.loads(text)
            return data if isinstance(data, dict) else fallback
        except Exception:
            return fallback

    def generate_json_from_image(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        image_path: Path,
        fallback: dict[str, Any],
    ) -> dict[str, Any]:
        if not self.is_vision_available() or not image_path.exists():
            return fallback

        prompt = (
            f"{system_prompt}\n\n"
            "Responda apenas JSON valido com as chaves esperadas. "
            "Nao use markdown, nao explique o raciocinio.\n\n"
            f"{user_prompt}"
        )
        try:
            encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
            response = self.client.post(
                f"{self.settings.ollama_base_url}/api/generate",
                json={
                    "model": self.settings.ollama_vision_model,
                    "prompt": prompt,
                    "images": [encoded],
                    "stream": False,
                    "format": "json",
                    "options": {"temperature": 0.2},
                },
            )
            response.raise_for_status()
            payload = response.json()
            text = payload.get("response", "").strip()
            if not text:
                return fallback
            data = json.loads(text)
            return data if isinstance(data, dict) else fallback
        except Exception:
            return fallback
