from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: Literal["development", "staging", "production", "test"] = "development"
    app_name: str = "KOFINEX"
    api_v1_prefix: str = "/api/v1"
    log_level: str = "INFO"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    database_url: str
    db_pool_size: int = 10
    db_max_overflow: int = 20

    supabase_url: str
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""
    supabase_jwt_secret: str = ""
    supabase_jwks_url: str = ""
    supabase_jwt_audience: str = "authenticated"
    supabase_storage_bucket_documents: str = "financial-documents"
    supabase_storage_bucket_reports: str = "reports"

    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    max_upload_size_mb: int = 50
    allowed_upload_extensions: list[str] = Field(default_factory=lambda: ["xlsx", "xls", "csv", "pdf"])

    integrations_encryption_key: str = ""

    # Stockage des fichiers : « supabase » (production) ou « local » (développement / tests)
    storage_backend: Literal["supabase", "local"] = "supabase"
    local_storage_dir: str = "./.storage"
    # Traitement des imports : « celery » (production) ou « inline » (développement / tests)
    import_processing: Literal["celery", "inline"] = "celery"
    ocr_language: str = "fra"

    ai_provider: Literal["anthropic", "openai", "none"] = "none"
    ai_api_key: str = ""
    ai_model: str = ""
    ai_max_output_tokens: int = 4000
    ai_timeout_seconds: float = 60.0
    ai_base_url: str = ""   # facultatif : passerelle compatible avec l'API du fournisseur

    @field_validator("cors_origins", "allowed_upload_extensions", mode="before")
    @classmethod
    def _split_csv(cls, v: object) -> object:
        if isinstance(v, str):
            return [item.strip() for item in v.split(",") if item.strip()]
        return v

    @model_validator(mode="after")
    def _check_jwt_config(self) -> "Settings":
        if not self.supabase_jwt_secret and not self.supabase_jwks_url:
            raise ValueError("SUPABASE_JWT_SECRET ou SUPABASE_JWKS_URL doit être défini")
        if self.app_env == "production":
            if "*" in self.cors_origins:
                raise ValueError("CORS '*' interdit en production")
            if not self.integrations_encryption_key:
                raise ValueError("INTEGRATIONS_ENCRYPTION_KEY est obligatoire en production")
            if self.storage_backend != "supabase":
                raise ValueError("STORAGE_BACKEND=supabase est obligatoire en production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
