"""Suivi budgétaire : budget, réalisé, écarts.

Une ligne de suivi regroupe les lignes de budget de même clé (racine de compte, centre de coûts).
Écart = réalisé − budget ; taux de réalisation = réalisé / budget × 100.
Sens : pour une charge, un réalisé inférieur au budget est favorable ; pour un produit, un réalisé
supérieur est favorable. L'appréciation porte sur le montant seul, pas sur sa cause.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_EVEN, Decimal

from app.engines.management import HUNDRED, ZERO, ManagementError, div, q2
from app.engines.management.actuals import (
    BalanceRow,
    CostEntry,
    balance_amount,
    cost_entries_by_period,
    descendants,
    prefix_nature,
)


@dataclass(frozen=True)
class BudgetLine:
    account_prefix: str | None
    cost_center_id: str | None
    label: str
    period: int                    # 0 = annuel, 1..12 = mois de l'exercice
    amount: Decimal


@dataclass
class TrackingRow:
    key: tuple[str | None, str | None]
    label: str
    nature: str
    budget: Decimal
    budget_by_period: dict[int, Decimal]
    actual: Decimal | None
    actual_by_period: dict[int, Decimal] | None
    actual_source: str             # trial_balance | cost_entries | none
    variance: Decimal | None = None
    realization_pct: Decimal | None = None
    favorable: bool | None = None
    notes: list[str] = field(default_factory=list)


@dataclass
class Tracking:
    rows: list[TrackingRow]
    totals: dict[str, dict[str, Decimal | None]]
    warnings: list[str]


def _assess(row: TrackingRow) -> None:
    if row.actual is None:
        return
    row.variance = q2(row.actual - row.budget)
    pct = div(row.actual * HUNDRED, row.budget)
    row.realization_pct = pct.quantize(Decimal("0.1"), rounding=ROUND_HALF_EVEN) if pct is not None else None
    if row.actual == row.budget:
        row.favorable = None
    elif row.nature == "charge":
        row.favorable = row.actual < row.budget
    else:
        row.favorable = row.actual > row.budget


def overlapping_prefixes(prefixes: Iterable[str]) -> list[tuple[str, str]]:
    ps = sorted(set(prefixes))
    return [(a, b) for a in ps for b in ps if a != b and b.startswith(a)]


def track(lines: Iterable[BudgetLine], *, chart_natures: dict[str, str | None], balance: list[BalanceRow] | None,
          cost_entries: list[CostEntry], center_parent: dict[str, str | None], fy_start: date,
          center_names: dict[str, str] | None = None,
          ledger_monthly: dict[str, dict[int, Decimal]] | None = None) -> Tracking:
    """``ledger_monthly`` : mouvements nets (débit − crédit) par compte et par mois du grand livre validé, hors
    à-nouveaux. S'il est fourni, il donne le réalisé mensuel des lignes par racine de comptes ; le réalisé annuel
    reste celui de la balance, et tout écart entre les deux est signalé."""
    groups: dict[tuple[str | None, str | None], list[BudgetLine]] = {}
    for ln in lines:
        groups.setdefault((ln.account_prefix, ln.cost_center_id), []).append(ln)

    warnings: list[str] = []
    if balance is None:
        warnings.append("Aucune balance validée pour l'exercice : le réalisé comptable n'est pas disponible.")
    acct_only = [k[0] for k in groups if k[0] and not k[1]]
    for a, b in overlapping_prefixes(acct_only):
        warnings.append(f"Les racines {a} et {b} se chevauchent : le réalisé de {b} est aussi compté dans {a}. "
                        "Les totaux par nature ne sont pas calculés.")
    overlap = bool(overlapping_prefixes(acct_only))

    rows: list[TrackingRow] = []
    for (prefix, center), group in groups.items():
        nature = prefix_nature(prefix, chart_natures) if prefix else "charge"
        by_period: dict[int, Decimal] = {}
        for ln in group:
            by_period[ln.period] = by_period.get(ln.period, ZERO) + ln.amount
        budget = sum(by_period.values(), ZERO)
        label = group[0].label
        if center:
            centers = descendants(center, center_parent)
            per = cost_entries_by_period(cost_entries, centers, prefix, fy_start)
            out_of_year = sum((v for p, v in per.items() if not 1 <= p <= 12), ZERO)
            row = TrackingRow((prefix, center), label, nature, budget, by_period, sum(per.values(), ZERO),
                              {p: v for p, v in per.items() if 1 <= p <= 12}, "cost_entries")
            if center_names and center in center_names:
                row.notes.append(f"Centre : {center_names[center]} (sous-centres inclus)")
            if out_of_year:
                row.notes.append(f"{q2(out_of_year)} de saisies hors des 12 mois de l'exercice incluses dans le réalisé.")
        elif balance is not None:
            annual = balance_amount(balance, prefix, nature)
            monthly = None
            if ledger_monthly is not None:
                monthly = {}
                for acc, per in ledger_monthly.items():
                    if acc.startswith(prefix):
                        for p, v in per.items():
                            monthly[p] = monthly.get(p, ZERO) + (v if nature == "charge" else -v)
            row = TrackingRow((prefix, None), label, nature, budget, by_period, annual, monthly, "trial_balance")
            if monthly is not None:
                row.notes.append("Réalisé mensuel : grand livre validé de l'exercice (hors à-nouveaux).")
                gap = sum(monthly.values(), ZERO) - annual
                if gap != 0:
                    row.notes.append(f"Le cumul mensuel du grand livre diffère du réalisé annuel de la balance de {q2(gap)}.")
            elif any(p != 0 for p in by_period):
                row.notes.append("Réalisé mensuel indisponible : importez et validez le grand livre de l'exercice.")
        else:
            row = TrackingRow((prefix, None), label, nature, budget, by_period, None, None, "none")
        _assess(row)
        rows.append(row)

    totals: dict[str, dict[str, Decimal | None]] = {}
    if not overlap:
        for nat in ("produit", "charge"):
            rs = [r for r in rows if r.nature == nat and r.key[1] is None]
            if not rs:
                continue
            b = sum((r.budget for r in rs), ZERO)
            a = None if any(r.actual is None for r in rs) else sum((r.actual for r in rs), ZERO)
            totals[nat] = {"budget": b, "actual": a, "variance": q2(a - b) if a is not None else None}
        if "produit" in totals and "charge" in totals:
            p, c = totals["produit"], totals["charge"]
            rb = p["budget"] - c["budget"]
            ra = p["actual"] - c["actual"] if p["actual"] is not None and c["actual"] is not None else None
            totals["solde"] = {"budget": rb, "actual": ra, "variance": q2(ra - rb) if ra is not None else None}
    rows.sort(key=lambda r: (r.key[1] is not None, r.key[0] or "", r.label))
    return Tracking(rows, totals, warnings)


def project_from_actuals(balance: list[BalanceRow], items: list[tuple[str, str, Decimal]],
                         chart_natures: dict[str, str | None], spread: str = "annual") -> list[BudgetLine]:
    """Prévision par hypothèses : montant = réalisé de la racine × (1 + taux / 100).
    `items` : (racine, libellé, taux en %) ; `spread` : « annual » (une ligne, période 0) ou « equal »
    (12 mensualités égales au centime, l'arrondi est porté sur le 12e mois)."""
    if spread not in ("annual", "equal"):
        raise ManagementError("Répartition inconnue (annual ou equal).")
    if overlapping_prefixes([i[0] for i in items]):
        raise ManagementError("Des racines se chevauchent : le réalisé serait compté deux fois.")
    out: list[BudgetLine] = []
    for prefix, label, rate in items:
        nature = prefix_nature(prefix, chart_natures)
        base = balance_amount(balance, prefix, nature)
        amount = q2(base * (HUNDRED + rate) / HUNDRED)
        if spread == "annual":
            out.append(BudgetLine(prefix, None, label, 0, amount))
        else:
            month = q2(amount / 12)
            for p in range(1, 13):
                out.append(BudgetLine(prefix, None, label, p, month if p < 12 else amount - month * 11))
    return out


# ------------------------------------------------------------------ import d'un fichier de budget
_MONTHS = {"janv": 1, "janvier": 1, "fevr": 2, "fevrier": 2, "mars": 3, "avr": 4, "avril": 4, "mai": 5, "juin": 6,
           "juil": 7, "juillet": 7, "aout": 8, "sept": 9, "septembre": 9, "oct": 10, "octobre": 10, "nov": 11, "novembre": 11,
           "dec": 12, "decembre": 12}


def _norm(v: object) -> str:
    import unicodedata

    s = unicodedata.normalize("NFKD", str(v or "")).encode("ascii", "ignore").decode().lower().strip()
    return s.replace(".", "").replace("_", " ")


def parse_budget_sheet(rows: list[list[object]]) -> tuple[list[dict], list[str]]:
    """Lignes de budget à partir d'un tableau (Excel ou CSV), en deux présentations :
    - en ligne : colonnes compte (racine), centre (code), libellé, période (0 = annuel, 1 à 12 = mois de l'exercice), montant ;
    - en colonnes : compte, centre, libellé, puis une colonne par mois de l'exercice (« M1 »… « M12 », ou le rang 1 à 12)
      et/ou une colonne « annuel ».
    Les montants sont lus en Decimal par le lecteur commun des imports. Rien n'est enregistré ici."""
    from app.engines.importing.numbers import parse_amount

    errors: list[str] = []
    if not rows:
        return [], ["Fichier vide."]
    head = [_norm(c) for c in rows[0]]

    def col(*names):
        return next((i for i, h in enumerate(head) if h in names), None)

    c_acc = col("compte", "racine", "account", "compte comptable", "racine de compte")
    c_cc = col("centre", "center", "centre de couts", "code centre")
    c_lab = col("libelle", "label", "intitule")
    c_per = col("periode", "period", "mois de l'exercice")
    c_amt = col("montant", "amount")
    month_cols = {}
    for i, h in enumerate(head):
        k = h.removeprefix("m").strip() if h.startswith("m") and h[1:].strip().isdigit() else h
        if k.isdigit() and 1 <= int(k) <= 12 and i not in (c_acc, c_cc, c_lab, c_per, c_amt):
            month_cols[i] = int(k)
    c_year = col("annuel", "total annuel", "annual")
    if c_lab is None or (c_acc is None and c_cc is None):
        return [], ["Colonnes attendues : « compte » et/ou « centre », « libellé », puis « période » et « montant », "
                    "ou une colonne par mois (M1 à M12) et/ou « annuel »."]
    if c_amt is None and not month_cols and c_year is None:
        return [], ["Aucune colonne de montant (« montant », « M1 »… « M12 » ou « annuel »)."]
    out: list[dict] = []
    for n, r in enumerate(rows[1:], start=2):
        def cell(i, r=r):
            return r[i] if i is not None and i < len(r) else None

        acc = str(cell(c_acc) or "").strip().split(".")[0] or None
        cc = str(cell(c_cc) or "").strip() or None
        lab = str(cell(c_lab) or "").strip()
        if not (acc or cc or lab):
            continue
        if acc and not acc.isdigit():
            errors.append(f"Ligne {n} : racine de compte « {acc} » non numérique.")
            continue
        if not lab:
            errors.append(f"Ligne {n} : libellé manquant.")
            continue
        pairs: list[tuple[int, object]] = []
        if c_amt is not None:
            per = cell(c_per)
            try:
                p = 0 if per in (None, "") else int(str(per).split(".")[0])
            except ValueError:
                p = _MONTHS.get(_norm(per), -1)
            if not 0 <= p <= 12:
                errors.append(f"Ligne {n} : période « {per} » invalide (0 = annuel, 1 à 12).")
                continue
            pairs.append((p, cell(c_amt)))
        else:
            pairs += [(p, cell(i)) for i, p in sorted(month_cols.items(), key=lambda kv: kv[1])]
            if c_year is not None:
                pairs.append((0, cell(c_year)))
        for p, raw in pairs:
            if raw in (None, ""):
                continue
            try:
                amt = parse_amount(raw)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"Ligne {n} : montant illisible ({exc}).")
                continue
            if amt is None:
                continue
            if amt != amt.quantize(Decimal("0.01")):
                errors.append(f"Ligne {n} : montant {amt} à plus de deux décimales.")
                continue
            out.append({"account_prefix": acc, "cost_center_code": cc, "label": lab, "period": p, "amount": amt})
    return out, errors
