from functools import lru_cache
from pathlib import Path
import os

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: str = "development"
    pipeline_version: str = "0.3.0"
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000
    allowed_origins_raw: str = Field(
        default="http://localhost:3000,http://127.0.0.1:3000",
        alias="ALLOWED_ORIGINS",
    )
    snapmaker_storage_root: str = Field(
        default="",
        alias="SNAPMAKER_STORAGE_ROOT",
    )
    snapmaker_profile_name: str = "Snapmaker U1 (perfil conservador)"
    snapmaker_build_volume_x_mm: float = 270.0
    snapmaker_build_volume_y_mm: float = 270.0
    snapmaker_build_volume_z_mm: float = 270.0
    max_upload_size_mb: int = 1024
    max_project_files: int = 32
    max_project_previews: int = 5
    max_zip_entries: int = 500
    max_zip_depth: int = 8
    max_archive_xml_probe_bytes: int = 8 * 1024 * 1024
    max_triangles: int = 3_000_000
    stage_timeout_seconds: int = 300
    processing_stale_seconds: int = 900
    ollama_enabled: bool = True
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen2.5:7b"
    ollama_vision_model: str = ""
    ollama_timeout_seconds: float = 45.0
    free_ai_enabled: bool = True
    free_ai_external_enabled: bool = False
    free_ai_provider_order: str = "ollama,pollinations,huggingface"
    ai_generation_timeout_seconds: float = 6.0
    pollinations_image_model: str = "flux"
    pollinations_text_model: str = "openai-large"
    huggingface_api_token: str = ""
    huggingface_text_model: str = "mistralai/Mistral-7B-Instruct-v0.3"
    huggingface_image_model: str = "stabilityai/stable-diffusion-xl-base-1.0"
    # --- Credenciais sensíveis: obrigatório setar via env var em produção ---
    master_username: str = "admin"
    master_display_name: str = Field(default="Administrador", alias="MASTER_DISPLAY_NAME")
    master_password: str = ""
    master_password_aliases_raw: str = Field(default="", alias="MASTER_PASSWORD_ALIASES")
    auth_token_secret: str = "snapmaker3d-local-dev-secret-change-in-prod"
    auth_token_ttl_hours: int = 12
    google_oauth_client_id: str = ""
    google_oauth_redirect_uri: str = ""
    apple_oauth_client_id: str = ""
    apple_oauth_redirect_uri: str = ""
    instagram_oauth_client_id: str = ""
    instagram_oauth_redirect_uri: str = ""
    public_backend_origin: str = "http://127.0.0.1:8010"
    public_frontend_origin: str = "http://127.0.0.1:3000"

    @property
    def storage_root(self) -> Path:
        raw = self.snapmaker_storage_root
        if raw:
            return Path(raw)
        return Path.home() / "Downloads" / "Projetos3d" / "SnapMaker3d"

    @property
    def allowed_origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins_raw.split(",") if o.strip()]

    @property
    def master_password_aliases(self) -> list[str]:
        return [p.strip() for p in self.master_password_aliases_raw.split(",") if p.strip()]


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.storage_root.mkdir(parents=True, exist_ok=True)
    return settings
