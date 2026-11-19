"""Contrôle « chaque chiffre cité existe dans le contexte » (règle KOFINEX-NUM-1).

Les nombres d'une réponse sont extraits (formats français et anglais, pourcentages, unités d'échelle) puis
rapprochés des valeurs du contexte transmis au modèle. Un nombre est traçable s'il égale une valeur du contexte,
éventuellement arrondie à la précision affichée, mise à l'échelle (k, M, Md…), en valeur absolue ou exprimée en
pourcentage. Tout nombre non traçable est signalé : la réponse porte alors un avertissement visible.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

RULE = "KOFINEX-NUM-1"

_SCALES = {
    "k": Decimal(1000),
    "K": Decimal(1000),
    "millier": Decimal(1000),
    "milliers": Decimal(1000),
    "M": Decimal(10) ** 6,
    "million": Decimal(10) ** 6,
    "millions": Decimal(10) ** 6,
    "Md": Decimal(10) ** 9,
    "Mds": Decimal(10) ** 9,
    "milliard": Decimal(10) ** 9,
    "milliards": Decimal(10) ** 9,
}
_NUM = re.compile(
    r"(?<![\w.,])(?P<sign>[-−–]\s?)?(?P<num>\d{1,3}(?:[   ]\d{3})+(?:,\d+)?|\d{1,3}(?:\.\d{3})+(?:,\d+)?"
    r"|\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:[.,]\d+)?)"
    r"(?P<pct>\s?%)?(?:\s?(?P<scale>milliards?|millions?|milliers?|Mds|Md|M|k|K)\b)?",
)
_REF = re.compile(r"\[[A-Z]{1,3}\d+(?:\s*,\s*[A-Z]{1,3}\d+)*\]")
_LIST_MARKER = re.compile(r"(?m)^\s*\d{1,2}[.)]\s")


@dataclass(frozen=True)
class Num:
    text: str
    value: Decimal
    decimals: int
    percent: bool
    scale: Decimal


def _to_decimal(raw: str) -> tuple[Decimal, int] | None:
    s = raw.replace(" ", " ").replace(" ", " ")
    if " " in s:  # 1 234 567,89
        s = s.replace(" ", "").replace(",", ".")
    elif "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):  # 1.234,56
            s = s.replace(".", "").replace(",", ".")
        else:  # 1,234.56
            s = s.replace(",", "")
    elif re.fullmatch(r"\d{1,3}(?:\.\d{3})+", s):  # 1.234.567
        s = s.replace(".", "")
    elif re.fullmatch(r"\d{1,3}(?:,\d{3})+", s):  # 1,234,567 (ambigu : lu comme milliers)
        s = s.replace(",", "")
    else:
        s = s.replace(",", ".")
    try:
        d = Decimal(s)
    except InvalidOperation:
        return None
    decimals = len(s.split(".")[1]) if "." in s else 0
    return d, decimals


def extract(text: str) -> list[Num]:
    """Nombres cités dans un texte, hors références [F12] et numéros de liste."""
    clean = _LIST_MARKER.sub(" ", _REF.sub(" ", text or ""))
    out = []
    for m in _NUM.finditer(clean):
        parsed = _to_decimal(m.group("num"))
        if parsed is None:
            continue
        value, decimals = parsed
        if m.group("sign"):
            value = -value
        scale = _SCALES.get(m.group("scale") or "", Decimal(1))
        out.append(Num(m.group(0).strip(), value, decimals, bool(m.group("pct")), scale))
    return out


def context_values(obj) -> set[Decimal]:
    """Toutes les valeurs numériques présentes dans le contexte (nombres, chaînes numériques, nombres des textes)."""
    vals: set[Decimal] = set()

    def walk(o):
        if isinstance(o, bool) or o is None:
            return
        if isinstance(o, (int, float, Decimal)):
            try:
                vals.add(Decimal(str(o)))
            except InvalidOperation:
                pass
        elif isinstance(o, str):
            try:
                vals.add(Decimal(o))
            except InvalidOperation:
                for n in extract(o):
                    vals.add(n.value * n.scale)
        elif isinstance(o, dict):
            for v in o.values():
                walk(v)
        elif isinstance(o, (list, tuple, set)):
            for v in o:
                walk(v)

    walk(obj)
    return vals


def _round(v: Decimal, decimals: int) -> Decimal:
    return v.quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_UP)


def traceable(n: Num, values: set[Decimal]) -> bool:
    for v in values:
        for cand in (v, -v, v * 100, -v * 100):
            target = cand / n.scale if n.scale != 1 else cand
            if target == n.value or _round(target, n.decimals) == n.value:
                return True
    return False


def check(text: str, context) -> dict:
    """Résultat stocké avec la réponse : statut, nombres contrôlés, nombres non traçables."""
    values = context_values(context)
    nums = extract(text)
    bad = [n for n in nums if not traceable(n, values)]
    return {
        "rule": RULE,
        "status": "warning" if bad else "verified",
        "checked": len(nums),
        "untraceable": [{"text": n.text, "value": str(n.value * n.scale)} for n in bad],
    }
