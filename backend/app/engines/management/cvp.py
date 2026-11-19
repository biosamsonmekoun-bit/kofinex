"""Analyse coût-volume-profit (marge sur coût variable, seuil de rentabilité).

Données : chiffre d'affaires (racines de produits de la balance) et charges classées par
l'utilisateur, racine par racine, avec leur part variable en %. Aucune part variable n'est présumée.
Formules :
  MCV = CA − charges variables ; taux de MCV = MCV / CA ; résultat = MCV − charges fixes ;
  seuil de rentabilité = charges fixes / taux de MCV ; point mort (jours) = seuil / CA × durée réelle
  de l'exercice en jours ; marge de sécurité = CA − seuil ; indice de sécurité = marge de sécurité / CA ;
  levier opérationnel = MCV / résultat.
Hypothèses du modèle : linéarité des charges variables, charges fixes constantes sur l'exercice,
activité régulière (pour la date du point mort).
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import ROUND_CEILING, Decimal, localcontext

from app.engines.management import HUNDRED, ZERO, ManagementError, div
from app.engines.management.actuals import BalanceRow, balance_amount, prefix_nature
from app.engines.management.budget import overlapping_prefixes
from app.engines.management.costing import _d


def cvp(params: dict, balance: list[BalanceRow], chart_natures: dict[str, str | None],
        fy_start: date, fy_end: date) -> dict:
    with localcontext() as ctx:
        ctx.prec = 34
        return _cvp(params, balance, chart_natures, fy_start, fy_end)


def _cvp(params: dict, balance: list[BalanceRow], chart_natures: dict[str, str | None],
        fy_start: date, fy_end: date) -> dict:
    rev_prefixes = params.get("revenue_prefixes") or []
    if not rev_prefixes:
        raise ManagementError("Indiquez les racines de comptes du chiffre d'affaires.")
    if overlapping_prefixes(rev_prefixes):
        raise ManagementError("Les racines du chiffre d'affaires se chevauchent.")
    for p in rev_prefixes:
        if prefix_nature(p, chart_natures) != "produit":
            raise ManagementError(f"Racine {p} : le chiffre d'affaires doit provenir de comptes de produits.")
    revenue = sum((balance_amount(balance, p, "produit") for p in rev_prefixes), ZERO)

    rows = params.get("charges") or []
    if overlapping_prefixes([r["prefix"] for r in rows]):
        raise ManagementError("Des racines de charges se chevauchent : chaque compte ne doit être classé qu'une fois.")
    variable = fixed = ZERO
    detail = []
    for r in rows:
        if prefix_nature(r["prefix"], chart_natures) != "charge":
            raise ManagementError(f"Racine {r['prefix']} : ce n'est pas un compte de charges.")
        pct = _d(r.get("variable_pct"), f"Part variable de {r['prefix']}")
        if not ZERO <= pct <= HUNDRED:
            raise ManagementError(f"Racine {r['prefix']} : part variable hors de 0-100 %.")
        amount = balance_amount(balance, r["prefix"], "charge")
        v = amount * pct / HUNDRED
        variable += v
        fixed += amount - v
        detail.append({"prefix": r["prefix"], "label": r.get("label"), "amount": amount, "variable_pct": pct,
                       "variable": v, "fixed": amount - v})

    classified = {r["prefix"] for r in rows}
    unclassified = sum((r.net_debit for r in balance if _charge(r.account, chart_natures)
                        and not any(r.account.startswith(p) for p in classified)), ZERO)

    margin = revenue - variable
    rate = div(margin, revenue)
    result = margin - fixed
    breakeven = div(fixed, rate) if rate not in (None, ZERO) else None
    days = Decimal((fy_end - fy_start).days + 1)
    breakeven_days = div(breakeven * days, revenue) if breakeven is not None else None
    breakeven_date = None
    if breakeven_days is not None and ZERO <= breakeven_days <= days:
        # le seuil est atteint au cours du k-ième jour, k = arrondi supérieur du nombre de jours
        k = int(breakeven_days.to_integral_value(rounding=ROUND_CEILING))
        breakeven_date = fy_start + timedelta(days=max(k, 1) - 1)
    safety = revenue - breakeven if breakeven is not None else None
    return {
        "revenue": revenue, "variable_costs": variable, "contribution_margin": margin,
        "contribution_rate_pct": rate * HUNDRED if rate is not None else None,
        "fixed_costs": fixed, "result": result, "breakeven": breakeven, "breakeven_days": breakeven_days,
        "breakeven_date": breakeven_date, "safety_margin": safety,
        "safety_index_pct": div(safety * HUNDRED, revenue) if safety is not None else None,
        "operating_leverage": div(margin, result) if result != 0 else None,
        "charges": detail, "unclassified_charges": unclassified, "fiscal_year_days": days,
        "notes": ([] if breakeven is not None else
                  ["Seuil de rentabilité non significatif : marge sur coût variable nulle ou négative."]),
    }


def _charge(account: str, natures: dict[str, str | None]) -> bool:
    for k in range(len(account), 0, -1):
        n = natures.get(account[:k])
        if n:
            return n == "charge"
    return False
