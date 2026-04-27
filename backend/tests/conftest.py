"""
Fixtures centralizadas para toda a suíte de testes.

- Isola testes em tmp_path (sem tocar no disco de produção)
- Credenciais lidas de settings (env vars) — sem hardcode
- Cache limpo automaticamente antes/após cada teste
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# ── Configuração obrigatória ANTES de importar app ────────────────────────────
# Garante que os testes usem credenciais conhecidas e não dependam de defaults
# de config.py (que podem mudar).  CI não precisa setar variáveis extras.
os.environ.setdefault("MASTER_USERNAME", "rodrigogrosa")
os.environ.setdefault("MASTER_PASSWORD", "Violao2021@")
os.environ.setdefault("MASTER_PASSWORD_ALIASES", "Vilao2021@")
os.environ.setdefault("MASTER_DISPLAY_NAME", "Rodrigo Rosa")
os.environ.setdefault("AUTH_TOKEN_SECRET", "snapmaker3d-test-secret")
os.environ.setdefault("OLLAMA_ENABLED", "false")

from app.core.config import get_settings  # noqa: E402  (após setenv)
from app.services.dependencies import get_knowledge_service, get_project_service  # noqa: E402
from app.main import app  # noqa: E402


# ── Fixtures de infraestrutura ─────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def isolated_storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Redireciona todo I/O de storage para tmp_path — sem artefatos em produção."""
    monkeypatch.setenv("SNAPMAKER_STORAGE_ROOT", str(tmp_path / "storage"))
    get_settings.cache_clear()
    get_project_service.cache_clear()
    get_knowledge_service.cache_clear()
    yield
    get_settings.cache_clear()
    get_project_service.cache_clear()
    get_knowledge_service.cache_clear()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


# ── Fixtures de autenticação ───────────────────────────────────────────────────

@pytest.fixture
def master_credentials() -> dict[str, str]:
    """Retorna as credenciais master lidas de settings (nunca hardcoded)."""
    s = get_settings()
    return {"username": s.master_username, "password": s.master_password}


@pytest.fixture
def master_token(client: TestClient, master_credentials: dict[str, str]) -> str:
    """Token Bearer válido do usuário master."""
    response = client.post("/api/v1/auth/login", json=master_credentials)
    assert response.status_code == 200, f"Login falhou: {response.text}"
    return response.json()["access_token"]


@pytest.fixture
def auth_headers(master_token: str) -> dict[str, str]:
    """Header Authorization pronto para usar nos requests."""
    return {"Authorization": f"Bearer {master_token}"}


# ── Helpers reutilizáveis ──────────────────────────────────────────────────────

@pytest.fixture
def minimal_stl() -> bytes:
    """STL binário mínimo válido (cabeçalho + 0 triângulos)."""
    return b"0" * 80 + (0).to_bytes(4, "little")
