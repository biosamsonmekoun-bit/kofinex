"""Lecture des numéros de compte dans les cellules de balance."""

from __future__ import annotations

import re
from dataclasses import dataclass

MIN_LEN, MAX_LEN = 2, 20

_TOTAL_RE = re.compile(r"(?i)\b(total|totaux|sous[-\s]?total|cumul|report|à reporter|a reporter)\b")
_COMBINED_RE = re.compile(r"^\s*'?([0-9][0-9 . ]*[0-9]|[0-9])\s*(?:[-–—:|/]\s*)?(.*)$")


@dataclass(frozen=True)
class AccountCell:
    number: str | None          # chiffres uniquement, ou None si la cellule n'est pas un compte
    label_remainder: str | None # texte situé après le numéro (« 411100 Clients »)
    is_total: bool              # ligne de total / sous-total à exclure


def is_total_label(text: object) -> bool:
    return bool(text) and bool(_TOTAL_RE.search(str(text)))


def parse_account_cell(value: object) -> AccountCell:
    if value is None:
        return AccountCell(None, None, False)
    if isinstance(value, bool):
        return AccountCell(None, None, False)
    if isinstance(value, int):
        text = str(value)
    elif isinstance(value, float):
        if not value.is_integer():
            return AccountCell(None, None, False)
        text = str(int(value))
    else:
        text = str(value).strip()
    if not text:
        return AccountCell(None, None, False)
    if is_total_label(text):
        return AccountCell(None, None, True)

    m = _COMBINED_RE.match(text)
    if not m:
        return AccountCell(None, text, False)
    digits = re.sub(r"[ . ]", "", m.group(1))
    remainder = m.group(2).strip() or None
    # « 2025 » isolé dans une colonne de comptes reste un compte ; la longueur est contrôlée
    if not (MIN_LEN <= len(digits) <= MAX_LEN):
        return AccountCell(None, text, False)
    return AccountCell(digits, remainder, False)
