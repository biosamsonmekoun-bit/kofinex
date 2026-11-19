"""Contrôle des fichiers déposés comme éléments probants.

Le contenu est vérifié (signature binaire, structure des documents bureautiques, macros refusées,
taille décompressée) ; l'extension et le type annoncés par le navigateur ne suffisent jamais.
"""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass

from app.engines.importing.files import FileRejected, sha256_hex

MAX_BYTES = 50 * 1024 * 1024
MAX_UNCOMPRESSED = 300 * 1024 * 1024
MAX_RATIO = 200

TYPES = {
    "pdf": "application/pdf",
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "csv": "text/csv",
    "txt": "text/plain",
}


@dataclass(frozen=True)
class EvidenceFile:
    extension: str
    mime_type: str
    size_bytes: int
    sha256: str


def _office(data: bytes, folder: str, macro: str, what: str) -> None:
    if not data.startswith(b"PK\x03\x04"):
        raise FileRejected(f"Le fichier n'est pas un {what} valide.")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            names = set(zf.namelist())
            if "[Content_Types].xml" not in names or not any(n.startswith(folder) for n in names):
                raise FileRejected(f"Le fichier n'est pas un {what} valide.")
            if macro in names:
                raise FileRejected("Les documents contenant des macros ne sont pas acceptés.")
            total = sum(i.file_size for i in zf.infolist())
            if total > MAX_UNCOMPRESSED or total > MAX_RATIO * max(len(data), 1):
                raise FileRejected("Document refusé : taille décompressée anormale.")
    except zipfile.BadZipFile as exc:
        raise FileRejected(f"Le {what} est corrompu.") from exc


def validate_evidence(filename: str, data: bytes) -> EvidenceFile:
    if not data:
        raise FileRejected("Le fichier est vide.")
    if len(data) > MAX_BYTES:
        raise FileRejected(f"Fichier trop volumineux (maximum {MAX_BYTES // (1024 * 1024)} Mo).")
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in TYPES:
        raise FileRejected(f"Format non accepté : .{ext or '?'} (formats acceptés : "
                           f"{', '.join('.' + e for e in TYPES)}).")
    if ext == "pdf":
        if not data.lstrip()[:5].startswith(b"%PDF-"):
            raise FileRejected("Le fichier n'est pas un PDF valide.")
    elif ext == "png":
        if not data.startswith(b"\x89PNG\r\n\x1a\n"):
            raise FileRejected("Le fichier n'est pas une image PNG valide.")
    elif ext in ("jpg", "jpeg"):
        if not data.startswith(b"\xff\xd8\xff"):
            raise FileRejected("Le fichier n'est pas une image JPEG valide.")
    elif ext == "xlsx":
        _office(data, "xl/", "xl/vbaProject.bin", "classeur Excel")
    elif ext == "docx":
        _office(data, "word/", "word/vbaProject.bin", "document Word")
    else:   # csv, txt
        sample = data[:65536]
        if b"\x00" in sample:
            raise FileRejected("Le fichier texte contient des données binaires.")
        for enc in ("utf-8-sig", "cp1252"):
            try:
                sample.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            raise FileRejected("Texte illisible (encodage non reconnu).")
    return EvidenceFile(ext, TYPES[ext], len(data), sha256_hex(data))


def safe_filename(name: str) -> str:
    base = name.replace("\\", "/").rsplit("/", 1)[-1]
    cleaned = "".join(c if c.isalnum() or c in "._- " else "_" for c in base).strip(" .")
    return (cleaned or "fichier")[:120]
