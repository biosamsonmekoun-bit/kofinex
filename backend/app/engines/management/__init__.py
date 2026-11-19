"""Contrôle de gestion : budgets et écarts, coûts complets, coût-volume-profit, coûts préétablis,
projections. Python pur, montants en Decimal (précision 34) ; aucune règle de gestion n'est
présumée : clés de répartition, taux de variabilité, standards et hypothèses sont fournis par
l'utilisateur et restitués avec chaque résultat."""

from decimal import ROUND_HALF_EVEN, Decimal, localcontext

ZERO = Decimal(0)
CENT = Decimal("0.01")
HUNDRED = Decimal(100)


class ManagementError(ValueError):
    """Paramètres incohérents (clés ≠ 100 %, système de prestations réciproques insoluble…)."""


def q2(d: Decimal) -> Decimal:
    """Arrondi au centime (bancaire) pour l'affichage et le stockage des montants."""
    return d.quantize(CENT, rounding=ROUND_HALF_EVEN)


def div(a: Decimal, b: Decimal) -> Decimal | None:
    """Division exacte à 34 chiffres ; None si le dénominateur est nul."""
    if b == 0:
        return None
    with localcontext() as ctx:
        ctx.prec = 34
        return a / b
