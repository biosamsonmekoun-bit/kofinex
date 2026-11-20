"""Prix, remises et prorata (sans taxe : les règles fiscales arrivent avec l'étape 12B).

Règles (docs/LOT12_SAAS_CONCEPTION.md, § 4, § 5.2 et § 16) :
- décimales selon la norme ISO 4217 pour les devises retenues : XOF, XAF, GNF, KMF sans décimale, CDF deux ;
- arrondi au plus proche, la moitié vers le haut (ROUND_HALF_UP) : décision du 20 novembre 2026, arrondi à confirmer
  par le fiscaliste ;
- une remise ne rend jamais un montant négatif et ne porte jamais sur une taxe ;
- montée en gamme : crédit au prorata des jours restants de la période payée, imputé sur la nouvelle offre.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

# ISO 4217 (nombre de décimales de l'unité monétaire), devises de facturation retenues au § 16 (décisions 2 et 5)
CURRENCY_DECIMALS: dict[str, int] = {"XOF": 0, "XAF": 0, "GNF": 0, "KMF": 0, "CDF": 2}
INTERVALS = ("month", "year")
ZERO = Decimal(0)
HUNDRED = Decimal(100)


class PricingError(ValueError):
    pass


def _exp(currency: str) -> Decimal:
    if currency not in CURRENCY_DECIMALS:
        raise PricingError(f"Devise non prise en charge : {currency}")
    return Decimal(1).scaleb(-CURRENCY_DECIMALS[currency])


def quantize(amount: Decimal, currency: str) -> Decimal:
    """Montant arrondi à l'unité de la devise."""
    if not isinstance(amount, Decimal):
        raise PricingError("Montant attendu en Decimal")
    return amount.quantize(_exp(currency), rounding=ROUND_HALF_UP)


def check_amount(amount: Decimal, currency: str) -> None:
    """Refuse un montant négatif ou plus précis que la devise (XOF 1 500,50 n'existe pas)."""
    if not isinstance(amount, Decimal) or not amount.is_finite():
        raise PricingError("Montant invalide")
    if amount < 0:
        raise PricingError("Montant négatif")
    if amount != quantize(amount, currency):
        raise PricingError(f"{currency} : {CURRENCY_DECIMALS[currency]} décimale(s) au plus")


@dataclass(frozen=True)
class Promotion:
    code: str
    discount_type: str                      # 'percent' | 'fixed'
    percent: Decimal | None = None          # 0 < p ≤ 100
    fixed_amount: Decimal | None = None
    fixed_currency: str | None = None
    product_ids: frozenset[str] | None = None   # None : toutes les offres et options
    interval: str | None = None                 # None : toutes les périodicités


@dataclass(frozen=True)
class Line:
    product_id: str
    label: str
    unit_amount: Decimal
    quantity: int = 1


@dataclass(frozen=True)
class QuoteLine:
    product_id: str
    label: str
    unit_amount: Decimal
    quantity: int
    amount: Decimal
    discount: Decimal


@dataclass(frozen=True)
class Quote:
    currency: str
    interval: str
    lines: list[QuoteLine] = field(default_factory=list)
    subtotal: Decimal = ZERO
    discount: Decimal = ZERO
    credit: Decimal = ZERO
    total: Decimal = ZERO
    promotion_code: str | None = None


def _applies(promo: Promotion, line: Line, interval: str) -> bool:
    return (promo.product_ids is None or line.product_id in promo.product_ids) and \
        (promo.interval is None or promo.interval == interval)


def build_quote(lines: list[Line], currency: str, interval: str, promotion: Promotion | None = None,
                credit: Decimal = ZERO) -> Quote:
    """Aperçu chiffré : lignes, remise, crédit de prorata, total (jamais négatif)."""
    if interval not in INTERVALS:
        raise PricingError(f"Périodicité inconnue : {interval}")
    if not lines:
        raise PricingError("Aucune ligne")
    check_amount(credit, currency)
    raw = []
    for ln in lines:
        if ln.quantity < 1:
            raise PricingError("Quantité invalide")
        check_amount(ln.unit_amount, currency)
        raw.append((ln, ln.unit_amount * ln.quantity))
    discounts = [ZERO] * len(raw)
    if promotion is not None:
        eligible = [i for i, (ln, _a) in enumerate(raw) if _applies(promotion, ln, interval)]
        if not eligible:
            raise PricingError(f"Le code « {promotion.code} » ne s'applique à aucune ligne")
        if promotion.discount_type == "percent":
            p = promotion.percent
            if p is None or not (ZERO < p <= HUNDRED):
                raise PricingError("Pourcentage de remise invalide")
            for i in eligible:
                discounts[i] = quantize(raw[i][1] * p / HUNDRED, currency)
        elif promotion.discount_type == "fixed":
            if promotion.fixed_currency != currency or promotion.fixed_amount is None:
                raise PricingError(f"Remise fixe non définie en {currency}")
            check_amount(promotion.fixed_amount, currency)
            remaining = promotion.fixed_amount     # répartie dans l'ordre des lignes, sans dépasser chacune
            for i in eligible:
                d = min(remaining, raw[i][1])
                discounts[i], remaining = d, remaining - d
        else:
            raise PricingError("Type de remise inconnu")
    qlines = [QuoteLine(ln.product_id, ln.label, ln.unit_amount, ln.quantity, amount, discounts[i])
              for i, (ln, amount) in enumerate(raw)]
    subtotal = sum((q.amount for q in qlines), ZERO)
    discount = sum((q.discount for q in qlines), ZERO)
    net = subtotal - discount
    applied_credit = min(credit, net)
    return Quote(currency, interval, qlines, subtotal, discount, applied_credit, net - applied_credit,
                 promotion.code if promotion else None)


def prorata_credit(amount_paid: Decimal, period_start: date, period_end: date, at: date, currency: str) -> Decimal:
    """Crédit des jours restants d'une période payée [period_start, period_end[ à la date `at` (jours civils)."""
    check_amount(amount_paid, currency)
    total = (period_end - period_start).days
    if total <= 0:
        raise PricingError("Période invalide")
    if at <= period_start:
        return amount_paid
    if at >= period_end:
        return quantize(ZERO, currency)
    return quantize(amount_paid * Decimal((period_end - at).days) / Decimal(total), currency)
