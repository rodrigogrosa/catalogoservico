from __future__ import annotations

from pathlib import Path
import re
from typing import Any
from urllib.parse import unquote, urlparse

from app.core.config import get_settings
from app.services.local_llm_service import LocalLlmService
from app.services.sales_service import SalesService


class ProjectNamingService:
    SMALL_WORDS = {"da", "de", "do", "das", "dos", "e", "em", "para", "com", "of", "and", "the", "to", "from", "a"}
    DROP_TERMS = {
        "snapmaker",
        "compatible",
        "profile",
        "project",
        "file",
        "stampa",
        "fixed",
        "final",
        "converted",
        "processado",
        "plated",
        "zoocre8tions",
        # slicer / printer noise codes
        "h2c",
        "h1c",
        "p1s",
        "p1p",
        "x1c",
        "a1m",
        "knitted",
        "textured",
        "fdm",
        "fff",
        "printed",
        "printing",
        "bambu",
        "prusa",
        "creality",
        "ender",
        "voron",
        "ratrig",
    }
    # Common misspellings / phonetic variants that should be normalised before
    # character detection so that e.g. "yoshy" is correctly recognised as Yoshi.
    SPELLING_CORRECTIONS: dict[str, str] = {
        "yoshy": "yoshi",
        "yoshii": "yoshi",
        "yosi": "yoshi",
        "turtels": "turtles",
        "michelangello": "michelangelo",
        "narotu": "naruto",
        "gocu": "goku",
        "gokku": "goku",
        "vegita": "vegeta",
        "deadpol": "deadpool",
        "spidey": "spiderman",
        "spiderma": "spiderman",
        "ironma": "ironman",
        "thanos2": "thanos",
        "sonic2": "sonic",
        "tails2": "tails",
        "pikachou": "pikachu",
        "pikatchu": "pikachu",
        "charizerd": "charizard",
        "charmander2": "charmander",
        "bulbasor": "bulbasaur",
        "mewtow": "mewtwo",
        "darthvader": "darth vader",
        "r2d2": "r2-d2",
        "c3po": "c-3po",
        "lukes": "luke",
        "mandaloriann": "mandalorian",
        "boba fett2": "boba fett",
        "spongebob": "bob esponja",
        "minecraf": "minecraft",
        "creeper2": "creeper",
        "batman2": "batman",
        "superman2": "superman",
        "wonderwoman": "wonder woman",
        "aguaman": "aquaman",
    }
    HIGHLIGHT_PATTERNS = [
        (r"\bmask\b", "Máscara"),
        (r"\bhelmet\b", "Capacete"),
        (r"\bhead(set)?\b", "Cabeça"),
        (r"\bbust\b", "Busto"),
        (r"\bchibi\b", "Chibi"),
        (r"\bssj4\b", "SSJ4"),
        (r"\bui\b", "Ultra Instinto"),
        (r"\bbaby\b", "Baby"),
        (r"\bmini\b", "Mini"),
        (r"\bkey(chain)?\b|\bchaveiro\b|\bllavero\b", "Chaveiro"),
        (r"\bflexi\b|\bflex\b", "Flex"),
        (r"\barticulated\b|\barticulado\b", "Articulado"),
        (r"\bmultipart(es)?\b", "Multipartes"),
        (r"\bmulticolou?r\b|\bmulticor\b|\b\d+\s*x\s*colou?rs?\b|\b\d+colou?rs?\b|\bams\b", "Multicor"),
        (r"\b1\s*color\b|\bsingle\s*color\b|\bmonocrom", "Monocromático"),
        (r"\bstand\b|\bsuporte\b", "Suporte"),
        (r"\bholder\b", "Suporte"),
        (r"\bmount\b", "Suporte"),
    ]
    NAME_VISION_PROMPT = """
Voce nomeia produtos impressos em 3D em portugues do Brasil.
Observe a imagem e a dica textual. Identifique o objeto principal e um destaque visual/comercial curto.
Se for personagem conhecido, use o nome do personagem e um destaque marcante.
Responda JSON valido com: subject, highlight, title.
subject: o que e o produto.
highlight: detalhe curto e vendavel.
title: nome final curto, amigavel e comercial, maximo 70 caracteres.
Nao invente franquia ou personagem sem boa base visual/textual.
"""

    def __init__(self, llm: LocalLlmService | None = None, sales_service: SalesService | None = None) -> None:
        self.settings = get_settings()
        self.llm = llm or LocalLlmService()
        self.sales_service = sales_service or SalesService()

    def generate_name(
        self,
        *,
        source_name: str,
        previews: list[dict[str, Any]] | None = None,
        source_url: str | None = None,
        allow_vision: bool = True,
    ) -> str:
        cleaned = self._clean_source_name(source_name, source_url=source_url)
        character = self.sales_service.detect_character_context(cleaned)
        heuristic = self._heuristic_name(cleaned, character)
        if not allow_vision:
            return heuristic
        preview_file = self._resolve_preview_file(previews)
        if preview_file is None:
            return heuristic

        fallback = {
            "subject": heuristic,
            "highlight": self._extract_highlight(cleaned) or "",
            "title": heuristic,
        }
        vision = self.llm.generate_json_from_image(
            system_prompt=self.NAME_VISION_PROMPT,
            user_prompt=f"Dica textual do arquivo: {cleaned}",
            image_path=preview_file,
            fallback=fallback,
        )
        proposed = str(vision.get("title") or "").strip()
        if not proposed:
            return heuristic
        if character.get("is_character") and str(character.get("name") or "").lower() not in proposed.lower():
            return heuristic
        return self._finalize_title(proposed)

    def _clean_source_name(self, source_name: str, *, source_url: str | None = None) -> str:
        raw = Path(source_name or "projeto-3d").stem
        if source_url:
            parsed = urlparse(source_url)
            if parsed.path:
                raw = Path(unquote(parsed.path)).stem or raw
        text = unquote(raw).replace("+", " ")
        text = re.sub(r"\.(stl|3mf|obj|step|stp|amf|zip)$", "", text, flags=re.IGNORECASE)
        text = re.sub(r"[_\-]+", " ", text)
        text = re.sub(r"\((\d+)\)$", "", text).strip()
        text = re.sub(r"\b(v|ver|version)\s*\d+([._-]\d+)*\b", " ", text, flags=re.IGNORECASE)
        text = re.sub(r"\bpart\s*\d+\b", " ", text, flags=re.IGNORECASE)
        text = re.sub(r"\b\d+%\s*scale\b", " ", text, flags=re.IGNORECASE)
        # Strip Bambu AMS slot counts like "4x color", "2x colour"
        text = re.sub(r"\b\d+\s*x\s*colou?r\b", " Multicor ", text, flags=re.IGNORECASE)
        text = re.sub(r"\b\d+\s*colou?rs?\b|\b3\s*colors?\b|\b3colors\b", " Multicor ", text, flags=re.IGNORECASE)
        text = re.sub(r"\bfrom a to z\b", " ", text, flags=re.IGNORECASE)
        # Apply spelling corrections token by token
        corrected: list[str] = []
        for token in text.split():
            lower = token.lower()
            corrected.append(self.SPELLING_CORRECTIONS.get(lower, token))
        text = " ".join(corrected)
        # Drop printer/noise tokens
        tokens = []
        for token in text.split():
            if token.lower() in self.DROP_TERMS:
                continue
            tokens.append(token)
        return re.sub(r"\s+", " ", " ".join(tokens)).strip() or "Projeto 3D"

    def _heuristic_name(self, cleaned: str, character: dict[str, Any]) -> str:
        highlight = self._extract_highlight(cleaned)
        if character.get("is_character"):
            character_name = str(character.get("name") or "").strip()
            if highlight:
                return self._finalize_title(f"{character_name} {highlight}")
            return self._finalize_title(character_name)

        title = self._titleize(cleaned)
        if highlight and highlight.lower() not in title.lower():
            title = f"{title} {highlight}"
        return self._finalize_title(title)

    def _extract_highlight(self, cleaned: str) -> str:
        for pattern, label in self.HIGHLIGHT_PATTERNS:
            if re.search(pattern, cleaned, flags=re.IGNORECASE):
                return label
        return ""

    def _titleize(self, text: str) -> str:
        words: list[str] = []
        for index, word in enumerate(text.split()):
            lowered = word.lower()
            if lowered.isdigit():
                words.append(word)
                continue
            if index > 0 and lowered in self.SMALL_WORDS:
                words.append(lowered)
                continue
            if lowered in {"ui", "rc2", "cf", "gf", "ams", "u1", "3d", "rc", "ssj4"}:
                words.append(lowered.upper())
                continue
            words.append(lowered.capitalize())
        title = " ".join(words)
        title = title.replace(" Keychain", " Chaveiro")
        title = title.replace(" Holder", " Suporte")
        title = title.replace(" Mount", " Suporte")
        title = title.replace(" Stand", " Suporte")
        title = title.replace(" Toy", "")
        return re.sub(r"\s+", " ", title).strip()

    def _resolve_preview_file(self, previews: list[dict[str, Any]] | None) -> Path | None:
        if not previews:
            return None
        for item in previews:
            path = str(item.get("path") or "")
            if not path.startswith("/storage/"):
                continue
            candidate = self.settings.storage_root / path.replace("/storage/", "", 1)
            if candidate.exists():
                return candidate
        return None

    def _finalize_title(self, title: str) -> str:
        title = re.sub(r"\s+", " ", title).strip(" -_")
        return title[:70] or "Projeto 3D"
