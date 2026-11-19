"""Tableau de bord financier : regroupements et séries à partir de montants déjà validés (balance ou grand livre).

Aucune règle comptable n'est codée ici : la nature produit / charge et les libellés viennent du plan de comptes de la
version publiée du référentiel ; les indicateurs viennent du moteur d'analyse (bibliothèque KOFINEX-STD-1). Les seuls
calculs sont des sommes, des parts et des variations, dont les conventions sont explicites."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

ZERO = Decimal(0)
HUNDRED = Decimal(100)
MONTHS_FR = ("Janv.", "Févr.", "Mars", "Avr.", "Mai", "Juin", "Juil.", "Août", "Sept.", "Oct.", "Nov.", "Déc.")
TOP_GROUPS = 3


@dataclass(frozen=True)
class Chart:
    """Plan de comptes publié : numéro -> (libellé, nature)."""

    entries: dict[str, tuple[str, str | None]]

    def __post_init__(self) -> None:
        object.__setattr__(self, "_lengths", sorted({len(n) for n in self.entries}, reverse=True))

    def nature(self, account: str) -> str | None:
        for n in self._lengths:  # type: ignore[attr-defined]
            if n <= len(account) and account[:n] in self.entries:
                return self.entries[account[:n]][1]
        return None

    def group(self, account: str) -> tuple[str, str]:
        """Rubrique la plus courte du plan (2 chiffres, sinon 3) dont le compte relève."""
        for n in (2, 3):
            key = account[:n]
            if len(account) >= n and key in self.entries:
                return key, self.entries[key][0]
        return account[:3], f"Comptes {account[:3]}"


def pct(part: Decimal, total: Decimal) -> Decimal | None:
    if not total:
        return None
    return (part / total * HUNDRED).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def variation(value, previous) -> Decimal | None:
    """Convention de la bibliothèque (indicateurs de croissance) : (N − N-1) / |N-1| ; non calculée si N-1 est absent ou nul."""
    if value is None or previous is None:
        return None
    v, p = Decimal(str(value)), Decimal(str(previous))
    if p == 0:
        return None
    return ((v - p) / abs(p) * HUNDRED).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def signed(amount_debit_minus_credit: Decimal, nature: str) -> Decimal:
    """Montant d'un compte de gestion dans son sens normal : charge = débit − crédit ; produit = crédit − débit."""
    return amount_debit_minus_credit if nature == "expense" else -amount_debit_minus_credit


def breakdown(balances: dict[str, Decimal], chart: Chart, nature: str, top: int = TOP_GROUPS) -> dict:
    """balances : compte -> débit − crédit. Rubriques les plus importantes, puis « Autres »."""
    groups: dict[str, dict] = {}
    unclassified = 0
    for acc, net in balances.items():
        nat = chart.nature(acc)
        if nat is None:
            unclassified += 1
            continue
        if nat != nature:
            continue
        key, label = chart.group(acc)
        g = groups.setdefault(key, {"key": key, "label": label, "amount": ZERO})
        g["amount"] += signed(net, nature)
    total = sum((g["amount"] for g in groups.values()), ZERO)
    ordered = sorted(groups.values(), key=lambda g: (-g["amount"], g["key"]))
    shown = ordered[:top]
    rest = ordered[top:]
    if rest:
        shown.append(
            {
                "key": "autres",
                "label": "Autres",
                "amount": sum((g["amount"] for g in rest), ZERO),
                "includes": [g["key"] for g in rest],
            }
        )
    for g in shown:
        g["share"] = pct(g["amount"], total)
    return {"total": total, "groups": shown, "unclassified_accounts": unclassified}


def monthly(series: dict[str, dict[int, Decimal]], chart: Chart, months: list[tuple[int, int, int]]) -> list[dict]:
    """series : compte -> {période 1..n -> débit − crédit} ; months : (période, année, mois) dans l'ordre de l'exercice."""
    out = []
    for period, year, month in months:
        inc = exp = ZERO
        for acc, by in series.items():
            net = by.get(period)
            if net is None:
                continue
            nat = chart.nature(acc)
            if nat == "income":
                inc += -net
            elif nat == "expense":
                exp += net
        out.append({"period": period, "label": MONTHS_FR[month - 1], "year": year, "income": inc, "expense": exp})
    return out


def fiscal_months(start_year: int, start_month: int, end_year: int, end_month: int) -> list[tuple[int, int, int]]:
    out, y, m, p = [], start_year, start_month, 1
    while (y, m) <= (end_year, end_month):
        out.append((p, y, m))
        p, m = p + 1, m + 1
        if m == 13:
            y, m = y + 1, 1
    return out
