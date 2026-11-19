"""Extraction des balances du cas pratique du « Manuel de montage des états financiers du
SYSCOHADA révisé » (texte du PDF en mise en page conservée) vers un CSV, pour servir de jeu de
contrôle des tables de référentiel. Outil de vérification, pas un composant de la plateforme."""

import csv
import re
import sys

HEAD = re.compile(r"DEBITEUR|CREDITEUR|DEBIT|CREDIT")
FIELD = re.compile(r"\S+(?: \S+)*")          # champs séparés par au moins deux espaces
AMOUNT = re.compile(r"^-?\d{1,3}(?: \d{3})*$")


def _split(text: str, start: int, end: int, ends: list[int]) -> list[tuple[str, int]]:
    """Plusieurs montants séparés par une seule espace (« 1 864 651 283 1 814 012 866 ») : on énumère
    les découpages valides (premier groupe de 1 à 3 chiffres, puis groupes de 3) et on garde celui
    qui aligne le mieux chaque montant sur une colonne distincte."""
    groups = text.split(" ")
    best: tuple[tuple[int, int], list[tuple[str, int]]] | None = None

    def rec(i: int, pos: int, acc: list[tuple[str, int]]) -> None:
        nonlocal best
        if i == len(groups):
            cols = [min(range(len(ends)), key=lambda c: abs(ends[c] - e)) for _, e in acc]
            if cols != sorted(set(cols)):
                return
            # un montant ne déborde pas sur la colonne précédente
            for c, (piece, e) in zip(cols, acc, strict=True):
                if c > 0 and e - len(piece) < ends[c - 1] - 1:
                    return
            # à alignement égal, le découpage le plus équilibré l'emporte (montants de même ordre)
            cost = (sum(abs(ends[c] - e) for c, (_, e) in zip(cols, acc, strict=True)),
                    max(len(p) for p, _ in acc))
            if best is None or cost < best[0]:
                best = (cost, list(acc))
            return
        if not 1 <= len(groups[i]) <= 3 or (groups[i].startswith("0") and groups[i] != "0"):
            return       # un montant ne commence pas par un zéro
        j = i + 1
        while True:
            piece = " ".join(groups[i:j])
            piece_end = pos + len(piece)
            rec(j, piece_end + 1, acc + [(piece, piece_end)])
            if j >= len(groups) or len(groups[j]) != 3 or j - i >= 5:
                break
            j += 1

    rec(0, start, [])
    return best[1] if best else [(text, end)]


def _consistent(v: list[int | None]) -> bool:
    z = [x or 0 for x in v]
    return z[0] - z[1] + z[2] - z[3] == z[4] - z[5]


def _repair(line: str, account: str, ends: list[int]) -> list[int | None] | None:
    """Dernier recours : toutes les répartitions des groupes de chiffres en montants et en colonnes,
    en ne gardant que celles qui respectent ouverture + mouvements = solde, la mieux alignée."""
    tokens = [(m.group(), m.end()) for m in re.finditer(r"\d+", line[len(account):])]
    tokens = [(t, e + len(account)) for t, e in tokens if not (len(t) > 3)]
    # on ne garde que la suite finale de groupes numériques (après le libellé)
    best = None

    def rec(i: int, col: int, vals: list, cost: int) -> None:
        nonlocal best
        if i == len(tokens):
            if _consistent(vals) and (best is None or cost < best[0]):
                best = (cost, list(vals))
            return
        if col >= 6 or tokens[i][0].startswith("0") and tokens[i][0] != "0":
            return
        for j in range(i + 1, min(i + 5, len(tokens)) + 1):
            if any(len(t) != 3 for t, _ in tokens[i + 1:j]) or not 1 <= len(tokens[i][0]) <= 3:
                break
            amount = int("".join(t for t, _ in tokens[i:j]))
            end = tokens[j - 1][1]
            for c in range(col, 6):
                vals2 = list(vals)
                vals2[c] = amount
                rec(j, c + 1, vals2, cost + abs(ends[c] - end))

    # le libellé peut contenir des chiffres : on part du premier groupe proche d'une colonne
    for k in range(len(tokens)):
        if tokens[k][1] >= ends[0] - 20:
            tokens = tokens[k:]
            break
    rec(0, 0, [None] * 6, 0)
    return best[1] if best else None


def parse(path: str) -> list[dict]:
    rows, ends = [], None
    for line in open(path, encoding="utf-8"):
        line = line.rstrip("\n")
        if "DEBITEUR" in line and "CREDIT" in line:
            ends = [m.end() for m in HEAD.finditer(line)]
            continue
        m = re.match(r"^\s*(\d{6})\s+(.*)$", line)
        if not m or ends is None:
            continue
        fields = [(f.group(), f.start(), f.end()) for f in re.finditer(r"\S+(?: \S+)*", line)]
        # le premier champ contient le numéro puis le libellé ; les champs numériques sont les montants
        account = m.group(1)
        amounts = [f for f in fields if AMOUNT.match(f[0])]
        label_parts = [f[0] for f in fields if not AMOUNT.match(f[0])]
        label = " ".join(label_parts)[len(account):].strip()
        values = [None] * 6
        pieces = []
        for text, start, end in amounts:
            if text == account:
                continue
            pieces.extend(_split(text, start, end, ends))
        for text, end in pieces:
            k = min(range(6), key=lambda i: abs(ends[i] - end))
            values[k] = int(text.replace(" ", ""))
        if not _consistent(values):
            label = re.sub(r"[\d ]+$", "", label).strip()
            values = _repair(line, account, ends) or values
        rows.append({"compte": account, "libelle": label, **dict(zip(
            ["ouv_debit", "ouv_credit", "mvt_debit", "mvt_credit", "solde_debit", "solde_credit"], values, strict=True))})
    return rows


if __name__ == "__main__":
    rows = parse(sys.argv[1])
    with open(sys.argv[2], "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), delimiter=";")
        w.writeheader()
        w.writerows(rows)
    tot = {k: sum(r[k] or 0 for r in rows) for k in rows[0] if k not in ("compte", "libelle")}
    print(len(rows), "comptes", tot)
