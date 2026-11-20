"""Plan de trésorerie : calculs purs, en Decimal (phase 4 du correctif du contrôle de gestion).

Règles (docs/CONTROLE_GESTION.md § 12.5) :
- flux net du mois = total des encaissements (A) − total des décaissements (B) ;
- solde de fin de mois = solde de début + flux net ; solde de début du mois suivant = solde de fin du mois précédent ;
- totaux annuels = somme des douze mois ; un total de rubrique = somme de ses sous-rubriques (totaux A et B calculés
  sur les seules lignes de saisie : aucun double comptage) ;
- le réalisé est lu sur les mouvements de trésorerie réels (hors transferts internes), affecté aux rubriques par le
  compte de contrepartie : une charge n'est jamais tenue pour un décaissement du même mois ;
- aucune échéance n'est simulée : une prévision « budget décalé » applique le délai saisi par l'utilisateur.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

ZERO = Decimal("0.00")
CENT = Decimal("0.01")
HUNDRED = Decimal(100)
SECTIONS = ("receipts", "disbursements")


class TreasuryError(ValueError):
    pass


def q2(v: Decimal) -> Decimal:
    return v.quantize(CENT, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class Rubric:
    id: str
    section: str
    label: str
    parent_id: str | None = None
    code: str | None = None
    order: int = 0
    prefixes: tuple[str, ...] = ()


# ------------------------------------------------------------------ modalités de prévision
def spread(total: Decimal, months: int = 12) -> list[Decimal]:
    """Répartition égale d'un montant annuel ; l'arrondi au centime est porté sur le dernier mois (convention du lot 5)."""
    base = q2(total / months)
    out = [base] * months
    out[-1] = q2(total - base * (months - 1))
    return out


def percent_of(base: list[Decimal], rate_pct: Decimal) -> list[Decimal]:
    """Rubrique calculée : taux saisi par l'utilisateur appliqué, mois par mois, à une autre rubrique (ex. charges
    sociales = x % des rémunérations). Le taux n'est jamais une constante du code."""
    if rate_pct < 0:
        raise TreasuryError("Taux négatif")
    return [q2(v * rate_pct / HUNDRED) for v in base]


def shift(by_period: dict[int, Decimal], delay_months: int) -> tuple[list[Decimal], Decimal]:
    """Règle de calendrier : un montant prévu au mois m est encaissé ou décaissé au mois m + délai. `by_period` : 0 =
    annuel (réparti également), 1..12. Renvoie les douze mois et le montant reporté au-delà de l'exercice."""
    if not 0 <= delay_months <= 12:
        raise TreasuryError("Délai de 0 à 12 mois")
    months = [ZERO] * 12
    if 0 in by_period:
        for i, v in enumerate(spread(by_period[0])):
            months[i] += v
    for p, v in by_period.items():
        if p:
            months[p - 1] += v
    out, beyond = [ZERO] * 12, ZERO
    for i, v in enumerate(months):
        j = i + delay_months
        if j < 12:
            out[j] += v
        else:
            beyond += v
    return out, beyond


# ------------------------------------------------------------------ plan
@dataclass
class Plan:
    rows: list[dict]
    receipts: list[Decimal]
    disbursements: list[Decimal]
    net: list[Decimal]
    opening: list[Decimal]
    closing: list[Decimal]
    annual: dict[str, Decimal]
    negative_months: list[int] = field(default_factory=list)
    financing_need: Decimal = ZERO


def _tree(rubrics: list[Rubric]) -> tuple[dict[str, list[Rubric]], list[Rubric]]:
    children: dict[str, list[Rubric]] = defaultdict(list)
    roots = []
    ids = {r.id for r in rubrics}
    for r in rubrics:
        if r.section not in SECTIONS:
            raise TreasuryError(f"Section inconnue : {r.section}")
        if r.parent_id and r.parent_id in ids:
            children[r.parent_id].append(r)
        else:
            roots.append(r)
    for v in children.values():
        v.sort(key=lambda x: (x.order, x.label))
    roots.sort(key=lambda x: (SECTIONS.index(x.section), x.order, x.label))
    return children, roots


def compute(rubrics: list[Rubric], amounts: dict[str, list[Decimal]], opening_balance: Decimal) -> Plan:
    """Tableau mensuel : lignes (rubriques et sous-rubriques, douze mois, total), totaux A et B, flux net, soldes."""
    children, roots = _tree(rubrics)
    rows: list[dict] = []
    totals = {s: [ZERO] * 12 for s in SECTIONS}

    def months_of(r: Rubric) -> list[Decimal]:
        kids = children.get(r.id, [])
        if not kids:
            m = [q2(v) for v in amounts.get(r.id, [ZERO] * 12)]
            if len(m) != 12:
                raise TreasuryError(f"Rubrique « {r.label} » : douze mois attendus")
            if any(v < 0 for v in m):
                raise TreasuryError(f"Rubrique « {r.label} » : montant négatif (le sens vient de la section)")
            for i, v in enumerate(m):
                totals[r.section][i] += v          # totaux A et B : lignes de saisie seulement
            return m
        sub = [months_of(k) for k in kids]
        return [sum((s[i] for s in sub), ZERO) for i in range(12)]

    for root in roots:
        start = len(rows)
        rows.append({})                             # place de la rubrique, remplie après ses sous-rubriques
        m = months_of(root)
        rows[start] = {"id": root.id, "section": root.section, "code": root.code, "label": root.label, "level": 0,
                       "has_children": bool(children.get(root.id)), "months": m, "total": sum(m, ZERO)}
        for k in children.get(root.id, []):
            km = [q2(v) for v in amounts.get(k.id, [ZERO] * 12)]
            rows.append({"id": k.id, "section": k.section, "code": k.code, "label": k.label, "level": 1,
                         "has_children": False, "months": km, "total": sum(km, ZERO)})
    net = [totals["receipts"][i] - totals["disbursements"][i] for i in range(12)]
    opening, closing = [], []
    cur = q2(opening_balance)
    for i in range(12):
        opening.append(cur)
        cur = cur + net[i]
        closing.append(cur)
    negative = [i + 1 for i, v in enumerate(closing) if v < 0]
    need = -min(closing) if negative else ZERO
    annual = {"receipts": sum(totals["receipts"], ZERO), "disbursements": sum(totals["disbursements"], ZERO),
              "net": sum(net, ZERO), "opening": opening[0], "closing": closing[-1]}
    # contrôle de cohérence de l'exercice : solde de fin = solde initial + flux de l'exercice
    if annual["closing"] != annual["opening"] + annual["net"]:
        raise TreasuryError("Incohérence des soldes")
    return Plan(rows, totals["receipts"], totals["disbursements"], net, opening, closing, annual, negative, need)


# ------------------------------------------------------------------ réalisé
@dataclass(frozen=True)
class CashLine:
    """Ligne d'une écriture qui mouvemente la trésorerie (hors à-nouveaux) : compte, mois de l'exercice, débit, crédit,
    et si le compte est un compte de trésorerie."""
    entry: str
    account: str
    period: int
    debit: Decimal
    credit: Decimal
    treasury: bool


def actuals(lines: list[CashLine], rubrics: list[Rubric]) -> dict:
    """Réalisé par rubrique et par mois, d'après les comptes de contrepartie des mouvements de trésorerie.

    - une écriture dont toutes les lignes portent sur la trésorerie est un transfert interne : ignorée ;
    - chaque ligne de contrepartie est rattachée à la rubrique dont un compte associé est la racine la plus longue de
      son compte ; un crédit de contrepartie est un encaissement, un débit un décaissement (pour une rubrique
      d'encaissements : crédit − débit ; de décaissements : débit − crédit) ;
    - une contrepartie sans rubrique est « non affectée » (encaissement si crédit, décaissement si débit) ;
    - contrôle : encaissements − décaissements = variation des comptes de trésorerie."""
    by_entry: dict[str, list[CashLine]] = defaultdict(list)
    for ln in lines:
        by_entry[ln.entry].append(ln)
    index = sorted(((p, r) for r in rubrics for p in r.prefixes), key=lambda x: -len(x[0]))
    per: dict[str, list[Decimal]] = defaultdict(lambda: [ZERO] * 12)
    unassigned = {s: [ZERO] * 12 for s in SECTIONS}
    cash_change = [ZERO] * 12
    for ls in by_entry.values():
        tre = [x for x in ls if x.treasury]
        if not tre or len(tre) == len(ls):
            continue
        for x in tre:
            cash_change[x.period - 1] += x.debit - x.credit
        for x in ls:
            if x.treasury:
                continue
            i = x.period - 1
            r = next((r for p, r in index if x.account.startswith(p)), None)
            if r is None:
                if x.credit:
                    unassigned["receipts"][i] += x.credit
                if x.debit:
                    unassigned["disbursements"][i] += x.debit
            elif r.section == "receipts":
                per[r.id][i] += x.credit - x.debit
            else:
                per[r.id][i] += x.debit - x.credit
    receipts = [sum((per[r.id][i] for r in rubrics if r.section == "receipts"), ZERO) + unassigned["receipts"][i]
                for i in range(12)]
    disb = [sum((per[r.id][i] for r in rubrics if r.section == "disbursements"), ZERO) + unassigned["disbursements"][i]
            for i in range(12)]
    check = all(receipts[i] - disb[i] == cash_change[i] for i in range(12))
    return {"by_rubric": dict(per), "unassigned": unassigned, "receipts": receipts, "disbursements": disb,
            "cash_change": cash_change, "check": check}


def rollup(rubrics: list[Rubric], by_rubric: dict[str, list[Decimal]]) -> dict[str, list[Decimal]]:
    """Réalisé des rubriques parentes = leur propre affectation + celle de leurs sous-rubriques."""
    children, _ = _tree(rubrics)
    out = {r.id: list(by_rubric.get(r.id, [ZERO] * 12)) for r in rubrics}
    for pid, kids in children.items():
        for k in kids:
            out[pid] = [out[pid][i] + out[k.id][i] for i in range(12)]
    return out


def variance(forecast: list[Decimal], actual: list[Decimal | None]) -> list[dict]:
    """Écart = réalisé − prévision ; taux de réalisation = réalisé / prévision × 100 (non calculé si la prévision est nulle)."""
    out = []
    for f, a in zip(forecast, actual, strict=True):
        if a is None:
            out.append({"forecast": f, "actual": None, "variance": None, "rate": None})
            continue
        rate = (a * HUNDRED / f).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP) if f else None
        out.append({"forecast": f, "actual": a, "variance": a - f, "rate": rate})
    return out


# ------------------------------------------------------------------ prévision glissante
def rolling(opening: Decimal, actual_net: list[Decimal | None], forecast_net: list[Decimal | None]) -> dict:
    """Prévision glissante sur douze mois : réalisé pour les mois clos, prévision actualisée ensuite. Une valeur `None`
    (mois sans prévision, par exemple au-delà du dernier plan) interrompt la projection, sans valeur inventée."""
    if len(actual_net) != len(forecast_net):
        raise TreasuryError("Séries de longueurs différentes")
    months, cur, stopped = [], q2(opening), False
    for a, f in zip(actual_net, forecast_net, strict=True):
        flow, basis = (a, "actual") if a is not None else (f, "forecast")
        if flow is None or stopped:
            stopped = True
            months.append({"basis": "none", "net": None, "opening": None, "closing": None})
            continue
        months.append({"basis": basis, "net": flow, "opening": cur, "closing": cur + flow})
        cur = cur + flow
    closings = [m["closing"] for m in months if m["closing"] is not None]
    negative = [i + 1 for i, m in enumerate(months) if m["closing"] is not None and m["closing"] < 0]
    return {"months": months, "negative_months": negative,
            "financing_need": -min(closings) if closings and min(closings) < 0 else ZERO, "complete": not stopped}
