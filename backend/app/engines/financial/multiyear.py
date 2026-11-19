"""Comparaisons pluriannuelles : séries, variations, taux de croissance annuel moyen."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_EVEN, Decimal, localcontext

PCT = Decimal("0.01")


@dataclass
class YearPoint:
    label: str
    value: Decimal | None
    status: str
    variation: Decimal | None = None          # écart absolu avec l'exercice précédent de la série
    variation_pct: Decimal | None = None      # en %, base |N-1|


@dataclass
class Series:
    code: str
    unit: str
    points: list[YearPoint] = field(default_factory=list)
    cagr_pct: Decimal | None = None           # montants uniquement, valeurs extrêmes strictement positives


def _nth_root(x: Decimal, n: int) -> Decimal:
    with localcontext() as ctx:
        ctx.prec = 34
        return (x.ln() / n).exp()


def build_series(code: str, unit: str, values: list[tuple[str, Decimal | None, str]]) -> Series:
    """``values`` : [(libellé de l'exercice, valeur, statut)] dans l'ordre chronologique."""
    s = Series(code, unit)
    prev: Decimal | None = None
    for label, value, status in values:
        p = YearPoint(label, value, status)
        if value is not None and prev is not None:
            p.variation = value - prev
            if prev != 0:
                p.variation_pct = ((value - prev) / abs(prev) * 100).quantize(PCT, rounding=ROUND_HALF_EVEN)
        s.points.append(p)
        prev = value if value is not None else None
    known = [(i, p.value) for i, p in enumerate(s.points) if p.value is not None]
    if unit == "amount" and len(known) >= 2:
        (i0, first), (i1, last) = known[0], known[-1]
        if first > 0 and last > 0 and i1 > i0:
            s.cagr_pct = ((_nth_root(last / first, i1 - i0) - 1) * 100).quantize(PCT, rounding=ROUND_HALF_EVEN)
    return s
