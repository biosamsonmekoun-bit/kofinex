"""Tests d'intégration : API réelle + PostgreSQL réel (shim Supabase + migrations).

Prérequis :
    TEST_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/kofinex_test
    (base créée avec sql/local/00_supabase_shim.sql puis `alembic upgrade head`)
Ignorés automatiquement si la variable n'est pas définie.
"""

from __future__ import annotations

import os
import time
import uuid

import pytest

DB_URL = os.environ.get("TEST_DATABASE_URL")
if not DB_URL:
    pytest.skip("TEST_DATABASE_URL non défini : tests d'intégration ignorés", allow_module_level=True)

pytest.importorskip("fastapi")
pytest.importorskip("sqlalchemy")
import email_validator  # noqa: E402
import jwt  # noqa: E402

# les comptes de test utilisent le domaine réservé « .test » (RFC 2606), refusé par défaut par email-validator
if "test" in email_validator.SPECIAL_USE_DOMAIN_NAMES:
    email_validator.SPECIAL_USE_DOMAIN_NAMES.remove("test")

JWT_SECRET = "integration-test-secret-0123456789abcdef"
SUPABASE_URL = "http://supabase.test"

os.environ.update({
    "APP_ENV": "test",
    "DATABASE_URL": DB_URL,
    "SUPABASE_URL": SUPABASE_URL,
    "SUPABASE_JWT_SECRET": JWT_SECRET,
    "SUPABASE_SERVICE_ROLE_KEY": "",
    "CORS_ORIGINS": "http://localhost:3000",
    "STORAGE_BACKEND": "local",
    "LOCAL_STORAGE_DIR": os.environ.get("TEST_STORAGE_DIR", "/tmp/kofinex-test-storage"),
    "IMPORT_PROCESSING": "inline",
})

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.db.session import engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client() -> TestClient:
    return TestClient(app)


class User:
    def __init__(self, email: str) -> None:
        self.id = uuid.uuid4()
        self.email = email
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO auth.users (id, email, raw_user_meta_data) "
                              "VALUES (:id, :email, jsonb_build_object('full_name', CAST(:email AS text)))"),
                         {"id": self.id, "email": email})

    def token(self, **overrides) -> str:
        now = int(time.time())
        claims = {"sub": str(self.id), "email": self.email, "aud": "authenticated", "role": "authenticated",
                  "iss": f"{SUPABASE_URL}/auth/v1", "iat": now, "exp": now + 600, **overrides}
        return jwt.encode(claims, JWT_SECRET, algorithm="HS256")

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token()}"}

    def make_platform_admin(self) -> None:
        with engine.begin() as conn:
            conn.execute(text("UPDATE public.profiles SET is_platform_admin = true WHERE id = :id"), {"id": self.id})


@pytest.fixture
def make_user():
    run = uuid.uuid4().hex[:8]

    def _make(name: str) -> User:
        return User(f"{name}.{run}@kofinex.test")
    return _make
