"""Abonnement d'une organisation (lot 12A, sans paiement) : compte de facturation, état, droits, usages, essai,
aperçu chiffré, demande de résiliation et son retrait.

Les écritures sur l'abonnement passent par les fonctions SQL de la migration 0018 (règles imposées en base) ;
les calculs (droits, devis) par les moteurs purs. Le navigateur ne calcule aucun montant."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import ROUND_CEILING, Decimal

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.errors import NotFound
from app.engines.billing import entitlements as ent
from app.engines.billing import lifecycle as lc
from app.engines.billing import pricing as pr
from app.models import BillingAccount, BillingProduct, BillingProductVersion
from app.services.billing import catalog
from app.services.billing.catalog import BillingInvalid

ACCOUNT_FIELDS = ("legal_name", "tax_id", "address", "city", "country_code", "billing_email", "updated_at")
MB = Decimal(1024 * 1024)


# ------------------------------------------------------------------ compte de facturation
def account(db: Session, org_id: uuid.UUID) -> BillingAccount | None:
    return db.scalar(select(BillingAccount).where(BillingAccount.organization_id == org_id))


def account_out(db: Session, a: BillingAccount | None) -> dict | None:
    if a is None:
        return None
    cur = db.scalar(text("SELECT public.billing_currency_for(:c)"), {"c": a.country_code})
    return {**{f: getattr(a, f) for f in ACCOUNT_FIELDS}, "currency": cur}


def save_account(db: Session, org_id: uuid.UUID, **f) -> BillingAccount:
    a = account(db, org_id)
    if a is None:
        a = BillingAccount(id=uuid.uuid4(), organization_id=org_id, **f)
        db.add(a)
    else:
        for k, v in f.items():
            setattr(a, k, v)
    db.flush()
    db.refresh(a)      # valeurs normalisées par la base (identifiant fiscal, e-mail)
    return a


# ------------------------------------------------------------------ état
def state(db: Session, org_id: uuid.UUID) -> dict | None:
    row = db.execute(text("SELECT * FROM public.billing_subscription_state(:o)"), {"o": org_id}).mappings().first()
    return dict(row) if row else None


def _items(db: Session, org_id: uuid.UUID) -> list[dict]:
    return [dict(r) for r in db.execute(text("SELECT * FROM public.billing_subscription_items(:o)"), {"o": org_id}).mappings()]


def _effective(st: dict | None, now: datetime) -> str | None:
    return None if st is None else lc.effective_state(st["status"], now, st["trial_end"], st["cancel_at"])


def subscription_out(db: Session, org_id: uuid.UUID, now: datetime | None = None) -> dict:
    now = now or datetime.now(UTC)
    st = state(db, org_id)
    if st is None:
        return {"subscription": None}
    v = db.get(BillingProductVersion, st["product_version_id"]) if st["product_version_id"] else None
    p = db.get(BillingProduct, v.product_id) if v else None
    eff = _effective(st, now)
    return {"subscription": {
        **st, "effective_status": eff,
        "pending_transition": eff if eff != st["status"] else None,   # bascule planifiée (tâches de l'étape 12B)
        "plan": {"code": p.code, "name": p.name, "version_label": v.label, "version_status": v.status} if p else None,
        "items": _items(db, org_id),
        "can_cancel": st["status"] in lc.CANCELLABLE and st["cancel_at"] is None and eff == st["status"],
        "can_reactivate": st["cancel_at"] is not None and st["cancel_at"] > now and st["status"] in lc.CANCELLABLE,
    }}


# ------------------------------------------------------------------ droits
def entitlements(db: Session, org_id: uuid.UUID, now: datetime | None = None) -> ent.Entitlements:
    now = now or datetime.now(UTC)
    st = state(db, org_id)
    has_data = bool(db.scalar(text("SELECT public.billing_org_has_data(:o)"), {"o": org_id}))
    requires, _core = catalog.module_rules(db)
    plan: list[ent.Grant] = []
    addons: list[tuple[list[ent.Grant], int]] = []
    if st is not None:
        for it in _items(db, org_id):
            g = catalog.grants(db, it["product_version_id"])
            if it["kind"] == "plan":
                plan = g
            else:
                addons.append((g, it["quantity"]))
    return ent.aggregate(plan, addons, _effective(st, now), has_data, requires)


def entitlements_out(e: ent.Entitlements) -> dict:
    return {"access": e.access, "modules": e.modules, "quotas": e.quotas, "display_only": True}


# ------------------------------------------------------------------ usages
def period(st: dict | None, now: datetime) -> tuple[datetime, datetime]:
    """Période de mesure des quotas périodiques : période de l'abonnement (essai compris), sinon le mois civil."""
    if st and st["current_period_start"] and st["current_period_end"]:
        return st["current_period_start"], st["current_period_end"]
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    end = (start + timedelta(days=32)).replace(day=1)
    return start, end


def usage(db: Session, org_id: uuid.UUID, now: datetime | None = None) -> dict:
    now = now or datetime.now(UTC)
    st = state(db, org_id)
    p_from, p_to = period(st, now)
    used = {r.key: r.used for r in db.execute(text("SELECT * FROM public.billing_org_usage(:o, :f, :t)"),
                                               {"o": org_id, "f": p_from, "t": p_to})}
    used["storage_mb"] = int((Decimal(used.pop("storage_bytes")) / MB).to_integral_value(rounding=ROUND_CEILING))
    used.pop("all_companies", None)
    limits = entitlements(db, org_id, now).quotas
    return {"period_start": p_from, "period_end": p_to,
            "quotas": [{"key": k, "used": used.get(k, 0), "limit": limits.get(k, 0) if limits else 0,
                        "unlimited": bool(limits) and limits.get(k, 0) is None} for k in ent.QUOTA_KEYS]}


# ------------------------------------------------------------------ opérations
def start_trial(db: Session, org_id: uuid.UUID, version_id: uuid.UUID, interval: str) -> uuid.UUID:
    return db.scalar(text("SELECT public.billing_start_trial(:o, :v, :i)"), {"o": org_id, "v": version_id, "i": interval})


def schedule_cancel(db: Session, org_id: uuid.UUID, reason: str | None) -> datetime:
    return db.scalar(text("SELECT public.billing_schedule_cancel(:o, :r)"), {"o": org_id, "r": reason})


def reactivate(db: Session, org_id: uuid.UUID) -> None:
    db.execute(text("SELECT public.billing_reactivate(:o)"), {"o": org_id})


def _published(db: Session, version_id: uuid.UUID, kind: str) -> tuple[BillingProduct, BillingProductVersion]:
    v = db.get(BillingProductVersion, version_id)
    p = db.get(BillingProduct, v.product_id) if v else None
    if v is None or p is None or v.status != "published" or p.kind != kind:
        raise NotFound("Offre introuvable" if kind == "plan" else "Option introuvable")
    return p, v


def _price(db: Session, v: BillingProductVersion, interval: str, currency: str, name: str) -> Decimal:
    for p in catalog.prices_of(db, v.id):
        if p.billing_interval == interval and p.currency == currency:
            return Decimal(p.amount)
    raise BillingInvalid(f"{name} : aucun prix publié en {currency} pour cette périodicité")


def quote(db: Session, org_id: uuid.UUID, *, version_id: uuid.UUID, interval: str,
          addons: list[tuple[uuid.UUID, int]], promotion_code: str | None) -> dict:
    """Aperçu chiffré calculé par le serveur (sans taxe : règles fiscales à l'étape 12B). Aucune commande n'est créée."""
    a = account(db, org_id)
    if a is None:
        raise BillingInvalid("Renseignez d'abord les informations de facturation (le pays fixe la devise)")
    currency = db.scalar(text("SELECT public.billing_currency_for(:c)"), {"c": a.country_code})
    p, v = _published(db, version_id, "plan")
    lines = [pr.Line(str(p.id), f"{p.name} ({v.label})", _price(db, v, interval, currency, p.name))]
    requires, _core = catalog.module_rules(db)
    modules = {g.key for g in catalog.grants(db, v.id) if g.kind == "module"}
    for addon_id, qty in addons:
        ap, av = _published(db, addon_id, "addon")
        lines.append(pr.Line(str(ap.id), f"{ap.name} ({av.label})", _price(db, av, interval, currency, ap.name), qty))
        modules |= {g.key for g in catalog.grants(db, av.id) if g.kind == "module"}
    missing = ent.missing_dependencies(modules, requires)
    if missing:
        raise BillingInvalid("Dépendances de modules non couvertes : "
                             + " ; ".join(f"{m} exige {', '.join(d)}" for m, d in missing.items()))
    promo = None
    if promotion_code:
        row = db.execute(text("SELECT * FROM public.billing_promotion_lookup(:o, :c)"),
                         {"o": org_id, "c": promotion_code}).mappings().first()
        if row is None:
            raise BillingInvalid("Code promotionnel inconnu, expiré ou déjà utilisé")
        promo = pr.Promotion(row["code"], row["discount_type"], row["percent"], row["fixed_amount"], row["fixed_currency"],
                             frozenset(str(x) for x in row["product_ids"]) if row["product_ids"] else None,
                             row["billing_interval"])
    try:
        q = pr.build_quote(lines, currency, interval, promo)
    except pr.PricingError as exc:
        raise BillingInvalid(str(exc)) from exc
    st = state(db, org_id)
    return {
        "currency": q.currency, "interval": q.interval, "promotion_code": q.promotion_code,
        "lines": [{"label": ln.label, "unit_amount": ln.unit_amount, "quantity": ln.quantity, "amount": ln.amount,
                   "discount": ln.discount} for ln in q.lines],
        "subtotal": q.subtotal, "discount": q.discount, "credit": q.credit, "total": q.total,
        "taxes": None,
        "notes": ["Montants hors taxes : les règles fiscales seront appliquées à la commande (étape 12B).",
                  *(["Le crédit au prorata d'une période payée sera calculé sur la commande (étape 12B)."]
                    if st and st["status"] in ("active", "past_due") else [])],
    }
