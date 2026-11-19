"""Validation des fichiers déposés : extension, signature binaire, taille, structure.

On ne se fie jamais à l'extension ni au type MIME annoncé par le navigateur : le contenu
est vérifié (signature, structure ZIP des classeurs, texte décodable pour les CSV).
"""

from __future__ import annotations

import hashlib
import io
import zipfile
from dataclasses import dataclass

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
XLS_MIME = "application/vnd.ms-excel"
CSV_MIME = "text/csv"
PDF_MIME = "application/pdf"

# Limite de décompression d'un classeur (protection « zip bomb »)
MAX_XLSX_UNCOMPRESSED = 300 * 1024 * 1024
MAX_XLSX_RATIO = 200


class FileRejected(ValueError):
    """Fichier refusé ; le message est destiné à l'utilisateur."""


@dataclass(frozen=True)
class ValidatedFile:
    format: str          # xlsx | xls | csv | pdf
    mime_type: str
    extension: str
    size_bytes: int
    sha256: str


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def validate_upload(filename: str, data: bytes, *, max_bytes: int, allowed_extensions: list[str]) -> ValidatedFile:
    if not data:
        raise FileRejected("Le fichier est vide.")
    if len(data) > max_bytes:
        raise FileRejected(f"Fichier trop volumineux (maximum {max_bytes // (1024 * 1024)} Mo).")
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in allowed_extensions:
        raise FileRejected(f"Format non accepté : .{ext or '?'} (formats acceptés : "
                           f"{', '.join('.' + e for e in allowed_extensions)}).")

    if ext == "xlsx":
        _check_xlsx(data)
        fmt, mime = "xlsx", XLSX_MIME
    elif ext == "xls":
        if not data.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
            raise FileRejected("Le fichier .xls n'est pas un classeur Excel 97-2003 valide.")
        fmt, mime = "xls", XLS_MIME
    elif ext == "csv":
        _check_csv(data)
        fmt, mime = "csv", CSV_MIME
    elif ext == "pdf":
        if not data.lstrip()[:5].startswith(b"%PDF-"):
            raise FileRejected("Le fichier n'est pas un PDF valide.")
        if b"/Encrypt" in data[:4096] or b"/Encrypt" in data[-4096:]:
            raise FileRejected("PDF protégé par mot de passe : retirez la protection avant le dépôt.")
        fmt, mime = "pdf", PDF_MIME
    else:  # pragma: no cover - extension autorisée mais non prise en charge
        raise FileRejected(f"Format .{ext} non pris en charge.")

    return ValidatedFile(format=fmt, mime_type=mime, extension=ext, size_bytes=len(data), sha256=sha256_hex(data))


def _check_xlsx(data: bytes) -> None:
    if not data.startswith(b"PK\x03\x04"):
        raise FileRejected("Le fichier .xlsx n'est pas un classeur Excel valide.")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            names = set(zf.namelist())
            if "[Content_Types].xml" not in names or not any(n.startswith("xl/") for n in names):
                raise FileRejected("Le fichier .xlsx n'est pas un classeur Excel valide.")
            if "xl/vbaProject.bin" in names:
                raise FileRejected("Les classeurs contenant des macros ne sont pas acceptés.")
            total = sum(i.file_size for i in zf.infolist())
            if total > MAX_XLSX_UNCOMPRESSED or total > MAX_XLSX_RATIO * max(len(data), 1):
                raise FileRejected("Classeur refusé : taille décompressée anormale.")
    except zipfile.BadZipFile as exc:
        raise FileRejected("Le fichier .xlsx est corrompu.") from exc


def _check_csv(data: bytes) -> None:
    sample = data[:65536]
    if b"\x00" in sample:
        raise FileRejected("Le fichier CSV contient des données binaires.")
    decode_text(sample)


def decode_text(data: bytes) -> tuple[str, str]:
    """Décode un texte (UTF-8 avec ou sans BOM, sinon Windows-1252 courant dans les exports)."""
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return data.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    raise FileRejected("Encodage du fichier CSV non reconnu.")  # pragma: no cover (latin-1 décode tout)
