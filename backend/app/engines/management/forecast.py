"""Projections statistiques d'une série annuelle (réalisés de plusieurs exercices).

Deux méthodes, restituées avec leurs hypothèses ; ce sont des extrapolations, pas des prévisions
validées : elles servent de point de départ aux budgets de prévision.
- Tendance linéaire (moindres carrés, x = rang de l'exercice) : ŷ = a + b·x, avec R². 3 points minimum.
- Taux de croissance annuel moyen : TCAM = (dernier / premier)^(1/(n−1)) − 1 ; valeurs strictement
  positives requises. 2 points minimum.
Calculs exacts en fractions pour la régression ; puissance fractionnaire en Decimal (34 chiffres).
"""

from __future__ import annotations

from decimal import Decimal, localcontext
from fractions import Fraction

from app.engines.management import ManagementError


def _dec(f: Fraction) -> Decimal:
    with localcontext() as ctx:
        ctx.prec = 34
        return Decimal(f.numerator) / Decimal(f.denominator)


def linear_trend(values: list[Decimal], horizon: int) -> dict:
    n = len(values)
    if n < 3:
        raise ManagementError("Tendance linéaire : au moins 3 exercices sont nécessaires.")
    xs = [Fraction(i + 1) for i in range(n)]
    ys = [Fraction(v) for v in values]
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))
    b = sxy / sxx
    a = my - b * mx
    ss_tot = sum((y - my) ** 2 for y in ys)
    ss_res = sum((y - (a + b * x)) ** 2 for x, y in zip(xs, ys, strict=True))
    r2 = None if ss_tot == 0 else 1 - ss_res / ss_tot
    return {"method": "linear_trend", "intercept": _dec(a), "slope": _dec(b),
            "r2": _dec(r2) if r2 is not None else None,
            "projections": [_dec(a + b * (n + h)) for h in range(1, horizon + 1)]}


def cagr(values: list[Decimal], horizon: int) -> dict:
    n = len(values)
    if n < 2:
        raise ManagementError("Taux de croissance moyen : au moins 2 exercices sont nécessaires.")
    if any(v <= 0 for v in values):
        raise ManagementError("Taux de croissance moyen : toutes les valeurs doivent être strictement positives.")
    with localcontext() as ctx:
        ctx.prec = 34
        rate = (values[-1] / values[0]) ** (Decimal(1) / Decimal(n - 1)) - 1
        proj, last = [], values[-1]
        for _ in range(horizon):
            last = last * (1 + rate)
            proj.append(last)
    return {"method": "cagr", "rate_pct": rate * 100, "projections": proj}
