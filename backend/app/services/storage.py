"""Stockage des fichiers : Supabase Storage (production) ou disque local (développement, tests).

Les documents sources sont écrits une seule fois (pas d'écrasement) et lus par le backend
avec la clé de service ; les utilisateurs n'obtiennent que des URL signées de courte durée.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Protocol
from urllib.parse import quote

import httpx

from app.core.config import get_settings
from app.core.errors import AppError, ServiceUnavailable

DOCUMENTS_BUCKET = "financial-documents"
SIGNED_URL_SECONDS = 300


class StorageError(AppError):
    code = "storage_error"


class Storage(Protocol):
    def upload(self, bucket: str, path: str, data: bytes, content_type: str) -> None: ...
    def download(self, bucket: str, path: str) -> bytes: ...
    def signed_url(self, bucket: str, path: str, expires_in: int = SIGNED_URL_SECONDS,
                   download_name: str | None = None) -> str: ...


class SupabaseStorage:
    def __init__(self, url: str, service_key: str) -> None:
        if not service_key:
            raise ServiceUnavailable("Stockage indisponible : SUPABASE_SERVICE_ROLE_KEY non configurée")
        self._base = f"{url.rstrip('/')}/storage/v1"
        self._public_base = url.rstrip("/")
        self._headers = {"apikey": service_key, "Authorization": f"Bearer {service_key}"}

    def _call(self, method: str, endpoint: str, **kw) -> httpx.Response:
        try:
            resp = httpx.request(method, f"{self._base}{endpoint}", headers={**self._headers, **kw.pop("headers", {})},
                                 timeout=120.0, **kw)
        except httpx.HTTPError as exc:
            raise ServiceUnavailable("Service de stockage injoignable") from exc
        if resp.status_code >= 400:
            raise StorageError(f"Erreur du stockage ({resp.status_code}) : {resp.text[:300]}")
        return resp

    def upload(self, bucket: str, path: str, data: bytes, content_type: str) -> None:
        self._call("POST", f"/object/{bucket}/{quote(path)}", content=data,
                   headers={"Content-Type": content_type, "x-upsert": "false", "cache-control": "no-store"})

    def download(self, bucket: str, path: str) -> bytes:
        return self._call("GET", f"/object/authenticated/{bucket}/{quote(path)}").content

    def signed_url(self, bucket: str, path: str, expires_in: int = SIGNED_URL_SECONDS,
                   download_name: str | None = None) -> str:
        body = self._call("POST", f"/object/sign/{bucket}/{quote(path)}", json={"expiresIn": expires_in}).json()
        signed = body.get("signedURL") or body.get("signedUrl")
        if not signed:
            raise StorageError("Réponse inattendue du stockage")
        url = f"{self._base}{signed}" if signed.startswith("/") else signed
        if download_name:
            url += f"&download={quote(download_name)}"
        return url


class LocalStorage:
    """Développement et tests uniquement (refusé en production par la configuration)."""

    def __init__(self, root: str) -> None:
        self._root = Path(root).resolve()

    def _path(self, bucket: str, path: str) -> Path:
        p = (self._root / bucket / path).resolve()
        if self._root not in p.parents:
            raise StorageError("Chemin de stockage invalide")
        return p

    def upload(self, bucket: str, path: str, data: bytes, content_type: str) -> None:
        p = self._path(bucket, path)
        if p.exists():
            raise StorageError("Le fichier existe déjà")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)

    def download(self, bucket: str, path: str) -> bytes:
        p = self._path(bucket, path)
        if not p.exists():
            raise StorageError("Fichier introuvable dans le stockage")
        return p.read_bytes()

    def signed_url(self, bucket: str, path: str, expires_in: int = SIGNED_URL_SECONDS,
                   download_name: str | None = None) -> str:
        raise ServiceUnavailable("Téléchargement direct indisponible avec le stockage local")


@lru_cache
def get_storage() -> Storage:
    s = get_settings()
    if s.storage_backend == "local":
        return LocalStorage(s.local_storage_dir)
    return SupabaseStorage(s.supabase_url, s.supabase_service_role_key)
