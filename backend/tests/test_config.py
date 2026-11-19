"""Lecture des listes séparées par des virgules depuis l'environnement (format de `.env.example`)."""

from app.core.config import Settings

REQUIRED = {"database_url": "postgresql+psycopg://u:p@localhost/db", "supabase_url": "http://supabase.test",
            "supabase_jwt_secret": "x" * 32}


def test_csv_lists_from_environment(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:3000, https://app.example")
    monkeypatch.setenv("ALLOWED_UPLOAD_EXTENSIONS", "xlsx,csv")
    s = Settings(_env_file=None, **REQUIRED)
    assert s.cors_origins == ["http://localhost:3000", "https://app.example"]
    assert s.allowed_upload_extensions == ["xlsx", "csv"]


def test_single_origin_from_environment(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:3000")
    assert Settings(_env_file=None, **REQUIRED).cors_origins == ["http://localhost:3000"]
