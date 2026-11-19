"""Document neutre : titre, métadonnées, avertissements, sections (paragraphes, champs, tableaux typés), sources.

Le même document alimente les trois formats. Son empreinte de données (`data_digest`) ne dépend que du contenu : deux
générations des mêmes données donnent la même empreinte, quel que soit le format, le modèle ou la date."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

GENERATOR_VERSION = "KOFINEX-REPORT-1"
DEFAULT_COLOR = "#172554"  # bleu nuit KOFINEX (docs/DESIGN_SYSTEM.md)
ACCENT_COLOR = "#D6A84F"  # or KOFINEX : filets uniquement
COLUMN_TYPES = ("text", "amount", "number", "percent", "ratio", "date")


def new(
    doc_type: str,
    title: str,
    *,
    subtype: str | None = None,
    entity: str | None = None,
    period: str | None = None,
    subtitle: str | None = None,
) -> dict:
    return {
        "type": doc_type,
        "subtype": subtype,
        "title": title,
        "subtitle": subtitle,
        "entity": entity,
        "period": period,
        "notices": [],
        "sections": [],
        "sources": [],
    }


def section(doc: dict, title: str) -> list:
    blocks: list = []
    doc["sections"].append({"title": title, "blocks": blocks})
    return blocks


def paragraph(text: str | None, *, style: str = "normal") -> dict | None:
    t = (text or "").strip()
    return {"kind": "paragraph", "text": t, "style": style} if t else None


def fields(items: list[tuple[str, object]]) -> dict:
    return {"kind": "fields", "items": [[k, _plain(v)] for k, v in items if v not in (None, "")]}


def table(columns: list[tuple[str, str, str]], rows: list[dict], *, title: str | None = None) -> dict:
    """columns : (clé, libellé, type) ; type ∈ COLUMN_TYPES."""
    for _, _, t in columns:
        if t not in COLUMN_TYPES:
            raise ValueError(f"Type de colonne inconnu : {t}")
    return {
        "kind": "table",
        "title": title,
        "columns": [{"key": k, "label": lbl, "type": t} for k, lbl, t in columns],
        "rows": [{c[0]: _plain(r.get(c[0])) for c in columns} for r in rows],
    }


def notice(text: str, level: str = "warning") -> dict:
    return {"kind": "notice", "level": level, "text": text}


def add(blocks: list, *items) -> None:
    blocks.extend(i for i in items if i)


def _plain(v):
    if isinstance(v, Decimal):
        return str(v)
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, (list, tuple)):
        return ", ".join(str(_plain(x)) for x in v)
    return v


# ------------------------------------------------------------------ empreintes
def canonical(obj) -> bytes:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def data_digest(doc: dict) -> str:
    core = {k: doc.get(k) for k in ("type", "subtype", "title", "entity", "period", "notices", "sections", "sources")}
    return hashlib.sha256(canonical(core)).hexdigest()


def file_digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ------------------------------------------------------------------ mise en forme (française)
def to_decimal(v) -> Decimal | None:
    if v is None or v == "":
        return None
    try:
        return Decimal(str(v))
    except (InvalidOperation, ValueError):
        return None


def _group(int_part: str) -> str:
    out = []
    while len(int_part) > 3:
        out.insert(0, int_part[-3:])
        int_part = int_part[:-3]
    out.insert(0, int_part)
    return " ".join(out)


def fmt_number(v, decimals: int = 2) -> str:
    d = to_decimal(v)
    if d is None:
        return "" if v in (None, "") else str(v)
    q = d.quantize(Decimal(1).scaleb(-decimals)) if decimals else d.quantize(Decimal(1))
    sign = "-" if q < 0 else ""
    s = f"{abs(q):f}"
    ip, _, fp = s.partition(".")
    return sign + _group(ip) + ("," + fp if fp else "")


def fmt_date(v) -> str:
    if not v:
        return ""
    s = str(v)[:10]
    try:
        y, m, d = s.split("-")
        return f"{d}/{m}/{y}"
    except ValueError:
        return s


def fmt(v, col_type: str) -> str:
    if v is None or v == "":
        return "—" if col_type != "text" else ""
    if col_type == "amount":
        return fmt_number(v, 2)
    if col_type == "number":
        d = to_decimal(v)
        return fmt_number(v, 0 if d is not None and d == d.to_integral_value() else 2)
    if col_type == "percent":
        return fmt_number(v, 1) + " %"
    if col_type == "ratio":
        return fmt_number(v, 2)
    if col_type == "date":
        return fmt_date(v)
    return str(v)


def numeric(col_type: str) -> bool:
    return col_type in ("amount", "number", "percent", "ratio")
