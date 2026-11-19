"""Lecture des montants tels qu'ils apparaissent dans les balances (formats français et anglo-saxons).

Toutes les valeurs sont converties en ``Decimal`` : aucun ``float`` n'est conservé. Une valeur
ambiguë lève ``AmountError`` plutôt que d'être devinée.
"""

from __future__ import annotations

import re
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation

CENT = Decimal("0.01")

_SPACES = re.compile(r"[\s   ']")       # espaces, insécables, fines, apostrophes
_CURRENCY = re.compile(r"(?i)\b(f\s?cfa|xof|xaf|fcfa|eur|usd|€|\$)\b|[€$]")
_EMPTY_MARKERS = {"", "-", "–", "—", "néant", "neant", "n/a", "na", "nil"}


class AmountError(ValueError):
    """Valeur non interprétable comme montant."""


def parse_amount(value: object, *, decimal_separator: str | None = None) -> Decimal | None:
    """Convertit une cellule en montant arrondi au centime.

    ``None`` est renvoyé pour une cellule vide ou un tiret. ``decimal_separator`` (``","`` ou
    ``"."``) force l'interprétation ; sinon elle est déduite quand c'est sans ambiguïté.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        raise AmountError("valeur booléenne")
    if isinstance(value, int):
        return Decimal(value).quantize(CENT)
    if isinstance(value, Decimal):
        return value.quantize(CENT, rounding=ROUND_HALF_EVEN)
    if isinstance(value, float):
        # Excel stocke les nombres en binaire : on passe par repr() (plus courte représentation
        # exacte) pour éviter 0.1 -> 0.1000000000000000055…
        if value != value or value in (float("inf"), float("-inf")):
            raise AmountError("valeur non numérique")
        return Decimal(repr(value)).quantize(CENT, rounding=ROUND_HALF_EVEN)

    text = str(value).strip()
    if text.lower() in _EMPTY_MARKERS:
        return None

    negative = False
    if text.startswith("(") and text.endswith(")"):
        negative, text = True, text[1:-1]
    text = _CURRENCY.sub("", text).strip()
    if text.endswith("-") and not text.startswith("-"):      # 1 234,00-
        negative, text = True, text[:-1]
    if text.startswith(("-", "−")):
        negative, text = not negative, text[1:]
    elif text.startswith("+"):
        text = text[1:]
    text = _SPACES.sub("", text)

    if not text or not re.fullmatch(r"[0-9.,]+", text):
        raise AmountError(f"montant illisible : {value!r}")

    text = _normalize_separators(text, decimal_separator, original=value)
    try:
        amount = Decimal(text)
    except InvalidOperation as exc:
        raise AmountError(f"montant illisible : {value!r}") from exc
    amount = amount.quantize(CENT, rounding=ROUND_HALF_EVEN)
    return -amount if negative else amount


def _normalize_separators(text: str, decimal_separator: str | None, *, original: object) -> str:
    commas, dots = text.count(","), text.count(".")
    if decimal_separator == ",":
        return text.replace(".", "").replace(",", ".") if commas <= 1 else _fail(original)
    if decimal_separator == ".":
        return text.replace(",", "") if dots <= 1 else _fail(original)

    if commas and dots:
        # le dernier séparateur rencontré est le séparateur décimal : 1.234.567,89 / 1,234,567.89
        if text.rfind(",") > text.rfind("."):
            return text.replace(".", "").replace(",", ".") if commas == 1 else _fail(original)
        return text.replace(",", "") if dots == 1 else _fail(original)
    if commas:
        if commas > 1:
            return _thousands_only(text, ",", original)
        integer, frac = text.split(",")
        if len(frac) == 3 and integer not in ("", "0"):
            raise AmountError(f"séparateur ambigu dans {original!r} : précisez le séparateur décimal")
        return text.replace(",", ".")                       # 1234,56 (usage français)
    if dots > 1:
        return _thousands_only(text, ".", original)
    if dots == 1:
        integer, frac = text.split(".")
        # « 1.234 » est ambigu (mille deux cent trente-quatre ou 1,234) : on refuse de deviner
        if len(frac) == 3 and integer not in ("", "0"):
            raise AmountError(f"séparateur ambigu dans {original!r} : précisez le séparateur décimal")
    return text


def _thousands_only(text: str, sep: str, original: object) -> str:
    groups = text.split(sep)
    if all(len(g) == 3 for g in groups[1:]) and 1 <= len(groups[0]) <= 3:
        return text.replace(sep, "")
    return _fail(original)


def _fail(original: object) -> str:
    raise AmountError(f"montant illisible : {original!r}")


def infer_decimal_separator(samples: list[object]) -> str | None:
    """Déduit le séparateur décimal d'une colonne de textes (``","``, ``"."`` ou ``None``)."""
    votes = {",": 0, ".": 0}
    for v in samples:
        if not isinstance(v, str):
            continue
        t = _SPACES.sub("", _CURRENCY.sub("", v)).strip("()-+−")
        if re.fullmatch(r"[0-9.]*[0-9],[0-9]{1,2}", t) or re.fullmatch(r"[0-9]{1,3}(\.[0-9]{3})+,[0-9]+", t):
            votes[","] += 1
        elif re.fullmatch(r"[0-9,]*[0-9]\.[0-9]{1,2}", t) or re.fullmatch(r"[0-9]{1,3}(,[0-9]{3})+\.[0-9]+", t):
            votes["."] += 1
    if votes[","] and not votes["."]:
        return ","
    if votes["."] and not votes[","]:
        return "."
    return None
