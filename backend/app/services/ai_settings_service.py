from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any

from app.core.config import Settings, get_settings
from app.schemas.ai_settings import AiProviderState, AiRuntimeSettingsResponse, AiRuntimeSettingsUpdateRequest


class AiSettingsService:
    KNOWN_PROVIDERS = ("ollama", "pollinations", "huggingface")

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.data_dir = self.settings.storage_root / "_system"
        self.data_path = self.data_dir / "ai_runtime.json"
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def get_runtime_settings(self) -> AiRuntimeSettingsResponse:
        runtime = self.runtime_preferences()
        return self.to_response(runtime)

    def update_runtime_settings(self, payload: AiRuntimeSettingsUpdateRequest) -> AiRuntimeSettingsResponse:
        current = self.runtime_preferences()

        if payload.free_ai_enabled is not None:
            current["free_ai_enabled"] = bool(payload.free_ai_enabled)
        if payload.external_providers_enabled is not None:
            current["external_providers_enabled"] = bool(payload.external_providers_enabled)
        if payload.provider_order is not None:
            current["provider_order"] = self.normalize_provider_order(payload.provider_order)

        current["updated_at"] = datetime.now(tz=timezone.utc).isoformat()
        self.write_overrides(
            {
                "free_ai_enabled": current["free_ai_enabled"],
                "external_providers_enabled": current["external_providers_enabled"],
                "provider_order": current["provider_order"],
                "updated_at": current["updated_at"],
            }
        )
        return self.to_response(current)

    def runtime_preferences(self) -> dict[str, Any]:
        defaults = {
            "free_ai_enabled": bool(self.settings.free_ai_enabled),
            "external_providers_enabled": bool(self.settings.free_ai_external_enabled),
            "provider_order": self.normalize_provider_order(str(self.settings.free_ai_provider_order).split(",")),
            "updated_at": None,
        }
        overrides = self.load_overrides()
        runtime = {
            "free_ai_enabled": bool(overrides.get("free_ai_enabled", defaults["free_ai_enabled"])),
            "external_providers_enabled": bool(overrides.get("external_providers_enabled", defaults["external_providers_enabled"])),
            "provider_order": self.normalize_provider_order(overrides.get("provider_order", defaults["provider_order"])),
            "updated_at": overrides.get("updated_at"),
        }
        return runtime

    def to_response(self, runtime: dict[str, Any]) -> AiRuntimeSettingsResponse:
        provider_order = self.normalize_provider_order(runtime.get("provider_order", []))
        external_enabled = bool(runtime.get("external_providers_enabled", False))
        providers = [
            AiProviderState(
                key="ollama",
                label="Ollama (local)",
                provider_type="local",
                enabled="ollama" in provider_order and bool(runtime.get("free_ai_enabled", False)),
                description="Executa no seu ambiente com modelo local.",
            ),
            AiProviderState(
                key="pollinations",
                label="Pollinations (externo)",
                provider_type="external",
                enabled=external_enabled and "pollinations" in provider_order and bool(runtime.get("free_ai_enabled", False)),
                description="Fallback gratuito para texto e imagem via API pública.",
            ),
            AiProviderState(
                key="huggingface",
                label="Hugging Face (externo)",
                provider_type="external",
                enabled=external_enabled and "huggingface" in provider_order and bool(runtime.get("free_ai_enabled", False)),
                description="Fallback com modelos hospedados na Hugging Face.",
            ),
        ]

        notes = [
            "Quando provedores externos estão desativados, apenas Ollama local é usado.",
            "A ordem define a cadeia de fallback: o sistema tenta em sequência até obter resposta válida.",
        ]

        return AiRuntimeSettingsResponse(
            free_ai_enabled=bool(runtime.get("free_ai_enabled", False)),
            external_providers_enabled=external_enabled,
            provider_order=provider_order,
            providers=providers,
            updated_at=runtime.get("updated_at"),
            notes=notes,
        )

    def normalize_provider_order(self, values: Any) -> list[str]:
        if isinstance(values, str):
            raw = [item.strip().lower() for item in values.split(",") if item.strip()]
        elif isinstance(values, list):
            raw = [str(item).strip().lower() for item in values if str(item).strip()]
        else:
            raw = []

        normalized: list[str] = []
        for provider in raw:
            if provider not in self.KNOWN_PROVIDERS:
                continue
            if provider in normalized:
                continue
            normalized.append(provider)

        if "ollama" not in normalized:
            normalized.insert(0, "ollama")
        return normalized

    def load_overrides(self) -> dict[str, Any]:
        if not self.data_path.exists():
            return {}
        try:
            payload = json.loads(self.data_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
        if isinstance(payload, dict):
            return payload
        return {}

    def write_overrides(self, payload: dict[str, Any]) -> None:
        self.data_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
