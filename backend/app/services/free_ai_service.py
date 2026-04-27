from __future__ import annotations

import json
import logging
from pathlib import Path
import re
from typing import Any
from urllib.parse import quote

import httpx
from PIL import Image, ImageEnhance, ImageFilter

from app.core.config import Settings, get_settings
from app.services.local_llm_service import LocalLlmService


logger = logging.getLogger(__name__)


class FreeAiService:
    """
    Provider chain focused on zero/low-cost AI runtimes.
    Order is configurable and failures automatically fallback.
    """

    POLLINATIONS_TEXT_URL = "https://text.pollinations.ai"
    POLLINATIONS_IMAGE_URL = "https://image.pollinations.ai/prompt"

    def __init__(
        self,
        settings: Settings | None = None,
        client: httpx.Client | None = None,
        llm_service: LocalLlmService | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        timeout_seconds = max(4.0, min(float(self.settings.ai_generation_timeout_seconds), 25.0))
        self.client = client or httpx.Client(
            timeout=httpx.Timeout(timeout_seconds, connect=3.0, read=timeout_seconds, write=timeout_seconds, pool=5.0)
        )
        self.llm = llm_service or LocalLlmService(self.settings)

    def is_enabled(self) -> bool:
        return bool(self.settings.free_ai_enabled)

    def provider_order(self) -> list[str]:
        raw = str(self.settings.free_ai_provider_order or "").strip()
        known = {"ollama", "pollinations", "huggingface"}
        providers = [item.strip().lower() for item in raw.split(",") if item.strip()]
        ordered = [provider for provider in providers if provider in known]
        if not ordered:
            ordered = ["ollama", "pollinations", "huggingface"]
        if not self.settings.free_ai_external_enabled:
            ordered = [provider for provider in ordered if provider == "ollama"]
        deduped: list[str] = []
        for provider in ordered:
            if provider not in deduped:
                deduped.append(provider)
        return deduped

    def generate_json_with_fallback(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        fallback: dict[str, Any],
        image_path: Path | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        if not self.is_enabled():
            return fallback, {"selected_provider": "disabled", "attempts": []}

        attempts: list[dict[str, Any]] = []
        for provider in self.provider_order():
            try:
                if provider == "ollama":
                    data = self._generate_with_ollama(system_prompt, user_prompt, fallback, image_path=image_path)
                elif provider == "pollinations":
                    data = self._generate_with_pollinations(system_prompt, user_prompt)
                elif provider == "huggingface":
                    data = self._generate_with_huggingface(system_prompt, user_prompt)
                else:
                    continue
                if isinstance(data, dict) and data:
                    attempts.append({"provider": provider, "status": "ok"})
                    return data, {"selected_provider": provider, "attempts": attempts}
                attempts.append({"provider": provider, "status": "empty"})
            except Exception as exc:  # noqa: BLE001
                attempts.append({"provider": provider, "status": "failed", "error": str(exc)})
                logger.warning("free_ai_provider_failed", extra={"provider": provider, "error": str(exc)})
                continue
        return fallback, {"selected_provider": "fallback", "attempts": attempts}

    def generate_marketplace_images(
        self,
        *,
        source_image: Path,
        output_dir: Path,
        project_name: str,
        context_text: str,
        count: int = 2,
    ) -> tuple[list[Path], dict[str, Any]]:
        if not self.is_enabled() or not source_image.exists():
            return [], {"selected_provider": "disabled", "attempts": []}

        output_dir.mkdir(parents=True, exist_ok=True)
        attempts: list[dict[str, Any]] = []
        generated: list[Path] = []
        subject_hint = self.describe_subject_for_prompt(source_image, project_name)
        prompts = self.build_image_prompts(subject_hint=subject_hint, context_text=context_text, count=count)

        for index, prompt in enumerate(prompts, start=1):
            target = output_dir / f"marketplace_ai_{index:02d}.jpg"
            produced = False
            for provider in self.provider_order():
                if provider not in {"pollinations", "huggingface"}:
                    continue
                try:
                    if provider == "pollinations":
                        self._generate_image_pollinations(prompt, target)
                    else:
                        self._generate_image_huggingface(prompt, target)
                    produced = True
                    attempts.append({"provider": provider, "status": "ok", "target": target.name})
                    break
                except Exception as exc:  # noqa: BLE001
                    attempts.append({"provider": provider, "status": "failed", "target": target.name, "error": str(exc)})
            if not produced:
                self._deterministic_image_fallback(source_image, target)
                attempts.append({"provider": "deterministic", "status": "ok", "target": target.name})
            generated.append(target)
        selected = next((item["provider"] for item in attempts if item.get("status") == "ok"), "deterministic")
        return generated, {"selected_provider": selected, "attempts": attempts, "subject_hint": subject_hint}

    def describe_subject_for_prompt(self, image_path: Path, project_name: str) -> str:
        fallback = {"subject": self.clean_subject_from_name(project_name)}
        if self.llm.is_vision_available():
            result = self.llm.generate_json_from_image(
                system_prompt=(
                    "Descreva o objeto principal para fotografia comercial de produto. "
                    "Retorne JSON valido com chave 'subject'."
                ),
                user_prompt=(
                    "Identifique apenas o objeto principal e uma frase curta de 8 a 14 palavras "
                    "focada em forma, material aparente e cores dominantes."
                ),
                image_path=image_path,
                fallback=fallback,
            )
            subject = str(result.get("subject", "")).strip()
            if subject:
                return subject
        return fallback["subject"]

    def build_image_prompts(self, *, subject_hint: str, context_text: str, count: int) -> list[str]:
        prompts = [
            (
                "professional ecommerce studio product photo, white clean background, "
                "soft shadow under object, ultra sharp details, 85mm lens look, "
                f"single product centered: {subject_hint}. Context: {context_text}"
            ),
            (
                "premium lifestyle ecommerce product photo, minimal modern desk setup, "
                "neutral colors, object in focus, scale perception, natural light, "
                f"single product featured: {subject_hint}. Context: {context_text}"
            ),
        ]
        return prompts[: max(1, count)]

    def clean_subject_from_name(self, project_name: str) -> str:
        text = re.sub(r"[_\-]+", " ", project_name or "").strip()
        text = re.sub(r"\s+", " ", text)
        return text or "produto impresso em 3D"

    def _generate_with_ollama(
        self,
        system_prompt: str,
        user_prompt: str,
        fallback: dict[str, Any],
        *,
        image_path: Path | None,
    ) -> dict[str, Any]:
        if image_path is not None and image_path.exists() and self.llm.is_vision_available():
            return self.llm.generate_json_from_image(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                image_path=image_path,
                fallback=fallback,
            )
        return self.llm.generate_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            fallback=fallback,
        )

    def _generate_with_pollinations(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        model = str(self.settings.pollinations_text_model or "openai-large").strip()
        prompt = (
            f"{system_prompt}\n\n"
            "Responda exclusivamente em JSON válido. Não use markdown.\n\n"
            f"{user_prompt}"
        )
        encoded = quote(prompt, safe="")
        url = f"{self.POLLINATIONS_TEXT_URL}/{encoded}"
        response = self.client.get(url, params={"model": model, "json": "true"})
        response.raise_for_status()
        return self._extract_json_dict(response.text)

    def _generate_with_huggingface(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        token = str(self.settings.huggingface_api_token or "").strip()
        if not token:
            raise ValueError("huggingface_api_token ausente")
        model = str(self.settings.huggingface_text_model or "").strip()
        prompt = (
            f"{system_prompt}\n\n"
            "Responda exclusivamente em JSON válido. Não use markdown.\n\n"
            f"{user_prompt}"
        )
        response = self.client.post(
            f"https://api-inference.huggingface.co/models/{model}",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            json={
                "inputs": prompt,
                "parameters": {
                    "max_new_tokens": 700,
                    "temperature": 0.2,
                    "return_full_text": False,
                },
            },
        )
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, list) and payload:
            text = str(payload[0].get("generated_text", "")).strip()
            return self._extract_json_dict(text)
        if isinstance(payload, dict):
            generated = payload.get("generated_text")
            if isinstance(generated, str):
                return self._extract_json_dict(generated)
        raise ValueError(f"Resposta HuggingFace inesperada: {payload}")

    def _extract_json_dict(self, text: str) -> dict[str, Any]:
        raw = text.strip()
        if not raw:
            raise ValueError("resposta vazia")
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
        match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
        if not match:
            raise ValueError("json ausente na resposta")
        parsed = json.loads(match.group(0))
        if not isinstance(parsed, dict):
            raise ValueError("json não é objeto")
        return parsed

    def _generate_image_pollinations(self, prompt: str, target: Path) -> None:
        model = str(self.settings.pollinations_image_model or "flux").strip()
        encoded = quote(prompt, safe="")
        url = f"{self.POLLINATIONS_IMAGE_URL}/{encoded}"
        response = self.client.get(
            url,
            params={
                "model": model,
                "width": 1600,
                "height": 1600,
                "nologo": "true",
                "enhance": "true",
                "safe": "true",
            },
            headers={"Accept": "image/*"},
        )
        response.raise_for_status()
        self._write_and_validate_image(response.content, target)

    def _generate_image_huggingface(self, prompt: str, target: Path) -> None:
        token = str(self.settings.huggingface_api_token or "").strip()
        if not token:
            raise ValueError("huggingface_api_token ausente")
        model = str(self.settings.huggingface_image_model or "").strip()
        response = self.client.post(
            f"https://api-inference.huggingface.co/models/{model}",
            headers={"Authorization": f"Bearer {token}", "Accept": "image/*"},
            json={"inputs": prompt},
        )
        response.raise_for_status()
        self._write_and_validate_image(response.content, target)

    def _write_and_validate_image(self, content: bytes, target: Path) -> None:
        if not content:
            raise ValueError("payload de imagem vazio")
        target.write_bytes(content)
        try:
            with Image.open(target) as image:
                image.load()
                rgb = image.convert("RGB")
                if min(rgb.size) < 900:
                    rgb = rgb.resize((1600, 1600), Image.Resampling.LANCZOS)
                rgb.save(target, format="JPEG", quality=95, subsampling=0, optimize=True)
        except Exception as exc:  # noqa: BLE001
            target.unlink(missing_ok=True)
            raise ValueError(f"arquivo de imagem inválido: {exc}") from exc

    def _deterministic_image_fallback(self, source_image: Path, target: Path) -> None:
        with Image.open(source_image) as image:
            image.load()
            rgba = image.convert("RGBA")
            resized = rgba.resize((1600, 1600), Image.Resampling.LANCZOS)
            background = Image.new("RGBA", resized.size, (248, 248, 246, 255))
            composed = Image.alpha_composite(background, resized)
            rgb = composed.convert("RGB")
            rgb = ImageEnhance.Contrast(rgb).enhance(1.06)
            rgb = ImageEnhance.Sharpness(rgb).enhance(1.22)
            rgb = rgb.filter(ImageFilter.UnsharpMask(radius=1.4, percent=130, threshold=2))
            rgb.save(target, format="JPEG", quality=95, subsampling=0, optimize=True)
