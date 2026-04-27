from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.core.config import Settings
from app.services.free_ai_service import FreeAiService


def test_provider_order_respects_external_toggle(tmp_path: Path) -> None:
    disabled_external = Settings(
        storage_root=tmp_path,
        free_ai_enabled=True,
        free_ai_external_enabled=False,
        free_ai_provider_order="ollama,pollinations,huggingface",
    )
    service = FreeAiService(settings=disabled_external)
    assert service.provider_order() == ["ollama"]

    enabled_external = Settings(
        storage_root=tmp_path,
        free_ai_enabled=True,
        free_ai_external_enabled=True,
        free_ai_provider_order="ollama,pollinations,huggingface,ollama",
    )
    service = FreeAiService(settings=enabled_external)
    assert service.provider_order() == ["ollama", "pollinations", "huggingface"]


def test_json_generation_falls_back_to_next_provider(monkeypatch, tmp_path: Path) -> None:
    settings = Settings(
        storage_root=tmp_path,
        free_ai_enabled=True,
        free_ai_external_enabled=True,
        free_ai_provider_order="ollama,pollinations,huggingface",
    )
    service = FreeAiService(settings=settings)

    def fail_ollama(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("ollama unavailable")

    def ok_pollinations(*args, **kwargs):  # type: ignore[no-untyped-def]
        return {"product_explanation": "ok"}

    monkeypatch.setattr(service, "_generate_with_ollama", fail_ollama)
    monkeypatch.setattr(service, "_generate_with_pollinations", ok_pollinations)

    result, meta = service.generate_json_with_fallback(
        system_prompt="sys",
        user_prompt="usr",
        fallback={"product_explanation": "fallback"},
    )
    assert result["product_explanation"] == "ok"
    assert meta["selected_provider"] == "pollinations"
    assert meta["attempts"][0]["provider"] == "ollama"
    assert meta["attempts"][1]["provider"] == "pollinations"
