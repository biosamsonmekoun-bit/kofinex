"""Détection de la ligne d'en-tête et proposition d'association des colonnes.

Les propositions sont toujours soumises à l'utilisateur, qui peut les corriger avant validation.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

# Champs cibles d'une balance générale
FIELDS = (
    "account_number", "account_label", "account",          # « account » = numéro + libellé dans une cellule
    "opening_debit", "opening_credit", "opening_balance",
    "movement_debit", "movement_credit",
    "closing_debit", "closing_credit", "closing_balance",
)
AMOUNT_FIELDS = tuple(f for f in FIELDS if f.startswith(("opening", "movement", "closing")))

FIELD_LABELS = {
    "account_number": "N° de compte", "account_label": "Libellé", "account": "Compte et libellé (même cellule)",
    "opening_debit": "Ouverture — débit", "opening_credit": "Ouverture — crédit",
    "opening_balance": "Ouverture — solde signé",
    "movement_debit": "Mouvements — débit", "movement_credit": "Mouvements — crédit",
    "closing_debit": "Clôture — débit", "closing_credit": "Clôture — crédit",
    "closing_balance": "Clôture — solde signé",
}


def _norm(text: object) -> str:
    s = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", s)).strip()


_ACCOUNT_KW = ("compte", "comptes", "n compte", "no compte", "numero", "num compte", "cpte", "cptes", "account", "code")
_LABEL_KW = ("libelle", "libelles", "intitule", "intitules", "designation", "label", "description", "nom du compte",
             "nature")
_GROUP_KW = {
    "opening": ("ouverture", "a nouveau", "a nouveaux", "an", "report", "anterieur", "debut", "initial", "opening",
                "n 1", "exercice precedent"),
    "movement": ("mouvement", "mouvements", "periode", "flux", "movement", "movements", "de l exercice"),
    "closing": ("cloture", "final", "finale", "fin", "closing", "fin de periode", "solde final"),
}
_SIDE_KW = {"debit": ("debit", "debiteur", "debits"), "credit": ("credit", "crediteur", "credits")}


def _side(text: str) -> str | None:
    """Débit / crédit ; les abréviations « D » / « C » ne valent que seules (« solde d'ouverture »
    contient un « d » isolé qui n'est pas un débit)."""
    words = text.split()
    has_d = any(k in words for k in _SIDE_KW["debit"])
    has_c = any(k in words for k in _SIDE_KW["credit"])
    if has_d != has_c:
        return "debit" if has_d else "credit"
    if not has_d and words and words[-1] in ("d", "c") and (len(words) == 1 or words[-2] not in ("d", "l")):
        return "debit" if words[-1] == "d" else "credit"
    return None
_ALL_KW = (_ACCOUNT_KW + _LABEL_KW + tuple(k for v in _GROUP_KW.values() for k in v)
           + ("debit", "credit", "debiteur", "crediteur", "debits", "credits", "solde", "soldes", "intitules"))


def _has(text: str, keywords: tuple[str, ...]) -> bool:
    return any(re.search(rf"(^| ){re.escape(k)}( |$)", text) for k in keywords)


def header_score(cells: list[object]) -> int:
    """Nombre de cellules ressemblant à un intitulé de colonne de balance."""
    score = 0
    for c in cells:
        t = _norm(c)
        if t and len(t) <= 60 and _has(t, _ALL_KW) and not re.fullmatch(r"[0-9 ]+", t):
            score += 1
    return score


def detect_header_row(rows: list[list[object]], scan: int = 40) -> int | None:
    best, best_score = None, 1
    for i, row in enumerate(rows[:scan]):
        s = header_score(row)
        if s > best_score:
            best, best_score = i, s
    return best


def combined_headers(rows: list[list[object]], header_row: int) -> list[str]:
    """Intitulés effectifs : ligne d'en-tête complétée par la ligne au-dessus (en-têtes sur deux
    niveaux, cellules fusionnées propagées vers la droite)."""
    header = rows[header_row]
    width = max(len(header), *(len(r) for r in rows[max(0, header_row - 1):header_row + 1]))
    above: list[str] = [""] * width
    if header_row > 0 and header_score(rows[header_row - 1]) >= 1:
        last = ""
        prev = rows[header_row - 1]
        for j in range(width):
            v = str(prev[j]).strip() if j < len(prev) and prev[j] not in (None, "") else ""
            last = v or last
            above[j] = last
    out = []
    for j in range(width):
        own = str(header[j]).strip() if j < len(header) and header[j] is not None else ""
        out.append(" ".join(x for x in (above[j], own) if x).strip())
    return out


@dataclass
class MappingSuggestion:
    column_map: dict[str, int] = field(default_factory=dict)
    headers: list[str] = field(default_factory=list)
    unmapped_columns: list[int] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


_PERIOD_RE = re.compile(r"\bN\s*[-–]\s*(\d)\b|\bN\b(?!\s*[-–°])", re.IGNORECASE)


def _period(header: str) -> int | None:
    """« Solde N-2 débiteur » -> -2 ; « Solde N créditeur » -> 0 ; sans repère d'exercice -> None."""
    m = _PERIOD_RE.search(header or "")
    if not m:
        return None
    return -int(m.group(1)) if m.group(1) else 0


def _order_periods(sugg: MappingSuggestion, headers: list[str]) -> None:
    """Les soldes sont repérés par exercice (« Solde N-2 » / « Solde N-1 ») : le plus ancien est
    l'ouverture, le plus récent la clôture, quel que soit le mot employé."""
    solde_cols = {}
    for f, c in list(sugg.column_map.items()):
        if f.startswith(("opening", "closing")):
            p = _period(headers[c])
            if p is not None:
                solde_cols[f] = (c, p)
    periods = sorted({p for _, p in solde_cols.values()})
    if len(periods) != 2:
        return
    first, last = periods
    remapped = {}
    for f, (c, p) in solde_cols.items():
        side = f.split("_", 1)[1]
        remapped[f"{'opening' if p == first else 'closing'}_{side}"] = c
    if remapped != {f: c for f, (c, _) in solde_cols.items()}:
        for f in solde_cols:
            sugg.column_map.pop(f, None)
        sugg.column_map.update(remapped)
        sugg.notes.append("Soldes repérés par exercice : le plus ancien est retenu comme ouverture, le plus récent "
                          "comme clôture.")


def suggest_mapping(rows: list[list[object]], header_row: int) -> MappingSuggestion:
    headers = combined_headers(rows, header_row)
    sugg = MappingSuggestion(headers=headers)
    pending_sides: list[tuple[int, str]] = []   # colonnes Débit/Crédit sans groupe identifié

    for j, raw in enumerate(headers):
        t = _norm(raw)
        if not t:
            continue
        # « Mouvement N-1 » : le mot « mouvement » prime sur le repère d'exercice
        group = "movement" if _has(t, _GROUP_KW["movement"]) else \
            next((g for g, kws in _GROUP_KW.items() if _has(t, kws)), None)
        side = _side(t)
        if side is None and group is None and _has(t, _ACCOUNT_KW) and _has(t, _LABEL_KW):
            sugg.column_map.setdefault("account", j)
        elif side is None and group is None and _has(t, _ACCOUNT_KW):
            sugg.column_map.setdefault("account_number", j)
        elif side is None and _has(t, _LABEL_KW):
            sugg.column_map.setdefault("account_label", j)
        elif side and group:
            sugg.column_map.setdefault(f"{group}_{side}", j)
        elif side:
            pending_sides.append((j, side))
        elif group == "movement":
            sugg.notes.append(f"Colonne « {raw} » : mouvements sans sens débit/crédit, non associée.")
        elif "solde" in t.split() or "soldes" in t.split() or group:
            sugg.column_map.setdefault(f"{group or 'closing'}_balance", j)

    # Débit/Crédit répétés sans groupe : 3 paires = ouverture, mouvements, clôture ;
    # 2 paires = mouvements, clôture ; 1 paire = clôture.
    if pending_sides:
        pairs = len(pending_sides) // 2
        free_groups = [g for g in ("opening", "movement", "closing")
                       if f"{g}_debit" not in sugg.column_map and f"{g}_credit" not in sugg.column_map]
        order = {3: ["opening", "movement", "closing"], 2: ["movement", "closing"], 1: ["closing"]}.get(pairs, [])
        order = [g for g in order if g in free_groups]
        idx = {"debit": 0, "credit": 0}
        for j, side in pending_sides:
            if idx[side] < len(order):
                sugg.column_map.setdefault(f"{order[idx[side]]}_{side}", j)
                idx[side] += 1
        if pairs not in (1, 2, 3) or len(pending_sides) % 2:
            sugg.notes.append("Colonnes Débit/Crédit non appariées : vérifiez l'association proposée.")

    _order_periods(sugg, headers)

    # pas de solde signé proposé quand les colonnes débit/crédit du même groupe existent
    for g in ("opening", "closing"):
        if f"{g}_balance" in sugg.column_map and (f"{g}_debit" in sugg.column_map or f"{g}_credit" in sugg.column_map):
            col = sugg.column_map.pop(f"{g}_balance")
            sugg.notes.append(f"Colonne « {headers[col]} » non associée : les colonnes débit/crédit du même solde existent.")

    if "account" in sugg.column_map and "account_number" in sugg.column_map:
        sugg.column_map.pop("account")
    mapped = set(sugg.column_map.values())
    sugg.unmapped_columns = [j for j, h in enumerate(headers) if h and j not in mapped]
    return sugg
