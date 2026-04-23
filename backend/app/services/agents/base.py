from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseAgent(ABC):
    prompt: str
    name: str

    @abstractmethod
    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    def result(
        self,
        *,
        status: str,
        etapa: str,
        achados: list[str] | None = None,
        riscos: list[str] | None = None,
        perguntas_ao_usuario: list[dict[str, Any]] | None = None,
        acoes_executadas: list[str] | None = None,
        artefatos_gerados: list[str] | None = None,
        caminho_de_saida: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = {
            "agent": self.name,
            "status": status,
            "etapa": etapa,
            "achados": achados or [],
            "riscos": riscos or [],
            "perguntas_ao_usuario": perguntas_ao_usuario or [],
            "acoes_executadas": acoes_executadas or [],
            "artefatos_gerados": artefatos_gerados or [],
            "caminho_de_saida": caminho_de_saida or "",
        }
        if extra:
            payload["extra"] = extra
        return payload
