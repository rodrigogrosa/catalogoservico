from functools import lru_cache
from pathlib import Path
import os

from pydantic import BaseModel, Field


class Settings(BaseModel):
    app_env: str = Field(default_factory=lambda: os.getenv("APP_ENV", "development"))
    pipeline_version: str = Field(default_factory=lambda: os.getenv("PIPELINE_VERSION", "0.3.0"))
    backend_host: str = Field(default_factory=lambda: os.getenv("BACKEND_HOST", "0.0.0.0"))
    backend_port: int = Field(default_factory=lambda: int(os.getenv("BACKEND_PORT", "8000")))
    allowed_origins: list[str] = Field(
        default_factory=lambda: [
            origin.strip()
            for origin in os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",")
            if origin.strip()
        ]
    )
    storage_root: Path = Field(
        default_factory=lambda: Path(os.getenv("SNAPMAKER_STORAGE_ROOT", str(Path.home() / "Downloads" / "Projetos3d" / "SnapMaker3d")))
    )
    snapmaker_profile_name: str = Field(default_factory=lambda: os.getenv("SNAPMAKER_PROFILE_NAME", "Snapmaker U1 (perfil conservador)"))
    snapmaker_build_volume_x_mm: float = Field(default_factory=lambda: float(os.getenv("SNAPMAKER_BUILD_VOLUME_X_MM", "270")))
    snapmaker_build_volume_y_mm: float = Field(default_factory=lambda: float(os.getenv("SNAPMAKER_BUILD_VOLUME_Y_MM", "270")))
    snapmaker_build_volume_z_mm: float = Field(default_factory=lambda: float(os.getenv("SNAPMAKER_BUILD_VOLUME_Z_MM", "270")))
    max_upload_size_mb: int = Field(default_factory=lambda: int(os.getenv("MAX_UPLOAD_SIZE_MB", "1024")))
    max_project_files: int = Field(default_factory=lambda: int(os.getenv("MAX_PROJECT_FILES", "32")))
    max_zip_entries: int = Field(default_factory=lambda: int(os.getenv("MAX_ZIP_ENTRIES", "500")))
    max_zip_depth: int = Field(default_factory=lambda: int(os.getenv("MAX_ZIP_DEPTH", "8")))
    max_archive_xml_probe_bytes: int = Field(default_factory=lambda: int(os.getenv("MAX_ARCHIVE_XML_PROBE_BYTES", str(8 * 1024 * 1024))))
    max_triangles: int = Field(default_factory=lambda: int(os.getenv("MAX_TRIANGLES", "3000000")))
    stage_timeout_seconds: int = Field(default_factory=lambda: int(os.getenv("STAGE_TIMEOUT_SECONDS", "300")))
    ollama_enabled: bool = Field(default_factory=lambda: os.getenv("OLLAMA_ENABLED", "true").lower() in {"1", "true", "yes", "on"})
    ollama_base_url: str = Field(default_factory=lambda: os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434"))
    ollama_model: str = Field(default_factory=lambda: os.getenv("OLLAMA_MODEL", "qwen2.5:7b"))
    ollama_timeout_seconds: float = Field(default_factory=lambda: float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "45")))
    master_username: str = Field(default_factory=lambda: os.getenv("MASTER_USERNAME", "rodrigogrosa"))
    master_password: str = Field(default_factory=lambda: os.getenv("MASTER_PASSWORD", "Violao2021@"))
    master_password_aliases: list[str] = Field(
        default_factory=lambda: [
            password.strip()
            for password in os.getenv("MASTER_PASSWORD_ALIASES", "Vilao2021@").split(",")
            if password.strip()
        ]
    )
    auth_token_secret: str = Field(default_factory=lambda: os.getenv("AUTH_TOKEN_SECRET", "snapmaker3d-local-dev-secret"))
    auth_token_ttl_hours: int = Field(default_factory=lambda: int(os.getenv("AUTH_TOKEN_TTL_HOURS", "12")))
    google_oauth_client_id: str = Field(default_factory=lambda: os.getenv("GOOGLE_OAUTH_CLIENT_ID", ""))
    google_oauth_redirect_uri: str = Field(default_factory=lambda: os.getenv("GOOGLE_OAUTH_REDIRECT_URI", ""))
    apple_oauth_client_id: str = Field(default_factory=lambda: os.getenv("APPLE_OAUTH_CLIENT_ID", ""))
    apple_oauth_redirect_uri: str = Field(default_factory=lambda: os.getenv("APPLE_OAUTH_REDIRECT_URI", ""))
    instagram_oauth_client_id: str = Field(default_factory=lambda: os.getenv("INSTAGRAM_OAUTH_CLIENT_ID", ""))
    instagram_oauth_redirect_uri: str = Field(default_factory=lambda: os.getenv("INSTAGRAM_OAUTH_REDIRECT_URI", ""))
    public_backend_origin: str = Field(default_factory=lambda: os.getenv("PUBLIC_BACKEND_ORIGIN", "http://127.0.0.1:8010"))
    public_frontend_origin: str = Field(default_factory=lambda: os.getenv("PUBLIC_FRONTEND_ORIGIN", "http://127.0.0.1:3000"))


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.storage_root.mkdir(parents=True, exist_ok=True)
    return settings
