"""Catalogue commercial (lot 12A) : modules, offres, versions, prix, droits, promotions, paramètres.

Écriture réservée à l'administrateur de la plateforme (RLS de la migration 0018) ; une version publiée est figée
par la base. La validation complète avant publication est faite par le moteur (engines/billing)."""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError, Conflict, NotFound
from app.engines.billing import entitlements as ent
from app.engines.billing import pricing as pr
from app.models import (
    BillingEntitlement,
    BillingModule,
    BillingPrice,
    BillingProduct,
    BillingProductVersion,
    BillingPromotion,
    BillingSettings,
)

PRODUCT_FIELDS = ("id", "code", "kind", "name", "description", "display_order", "created_at")
VERSION_FIELDS = ("id", "product_id", "version_no", "label", "description", "status", "trial_days", "published_at",
                  "retired_at", "created_at")
PROMOTION_FIELDS = ("id", "code", "label", "discount_type", "percent", "fixed_amount", "fixed_currency", "product_ids",
                    "billing_interval", "duration", "duration_periods", "valid_from", "valid_until", "max_redemptions",
                    "status", "created_at")
SETTINGS_FIELDS = ("grace_days", "suspension_to_cancel_days", "renewal_notice_days", "reminder_days", "max_orgs_per_user",
                   "seller_name", "seller_country", "seller_tax_id", "seller_address", "country_currencies", "updated_at")


class BillingInvalid(AppError):
    status_code = 422
    code = "billing_invalid"


def _out(obj, fields) -> dict:
    return {f: getattr(obj, f) for f in fields}


# ------------------------------------------------------------------ modules
def modules(db: Session) -> list[BillingModule]:
    return list(db.scalars(select(BillingModule).order_by(BillingModule.display_order)))


def module_rules(db: Session) -> tuple[dict[str, tuple[str, ...]], set[str]]:
    mods = modules(db)
    return {m.key: tuple(m.requires) for m in mods}, {m.key for m in mods if m.is_core}


def module_out(m: BillingModule) -> dict:
    return {"key": m.key, "label": m.label, "description": m.description, "requires": list(m.requires),
            "is_core": m.is_core, "display_order": m.display_order}


# ------------------------------------------------------------------ offres et versions
def product(db: Session, product_id: uuid.UUID) -> BillingProduct:
    p = db.get(BillingProduct, product_id)
    if p is None:
        raise NotFound("Offre introuvable")
    return p


def version(db: Session, version_id: uuid.UUID) -> BillingProductVersion:
    v = db.get(BillingProductVersion, version_id)
    if v is None:
        raise NotFound("Version introuvable")
    return v


def _draft(v: BillingProductVersion) -> None:
    if v.status != "draft":
        raise Conflict("Version publiée ou retirée : figée. Créez une nouvelle version.")


def create_product(db: Session, *, code: str, kind: str, name: str, description: str | None,
                   display_order: int) -> BillingProduct:
    if db.scalar(select(BillingProduct.id).where(BillingProduct.code == code)) is not None:
        raise Conflict(f"Le code {code} existe déjà")
    p = BillingProduct(id=uuid.uuid4(), code=code, kind=kind, name=name, description=description, display_order=display_order)
    db.add(p)
    db.flush()
    return p


def update_product(db: Session, p: BillingProduct, *, name: str, description: str | None, display_order: int) -> BillingProduct:
    p.name, p.description, p.display_order = name, description, display_order
    db.flush()
    return p


def create_version(db: Session, p: BillingProduct, *, label: str, description: str | None, trial_days: int | None,
                   copy_from: uuid.UUID | None) -> BillingProductVersion:
    if p.kind == "addon" and trial_days is not None:
        raise BillingInvalid("Une option n'a pas d'essai")
    no = (db.scalar(select(func.max(BillingProductVersion.version_no)).where(BillingProductVersion.product_id == p.id)) or 0) + 1
    v = BillingProductVersion(id=uuid.uuid4(), product_id=p.id, version_no=no, label=label, description=description,
                              trial_days=trial_days)
    db.add(v)
    db.flush()
    if copy_from is not None:
        src = version(db, copy_from)
        if src.product_id != p.id:
            raise BillingInvalid("La version copiée appartient à une autre offre")
        for pr_ in db.scalars(select(BillingPrice).where(BillingPrice.product_version_id == src.id)):
            db.add(BillingPrice(id=uuid.uuid4(), product_version_id=v.id, billing_interval=pr_.billing_interval,
                                currency=pr_.currency, amount=pr_.amount))
        for e in db.scalars(select(BillingEntitlement).where(BillingEntitlement.product_version_id == src.id)):
            db.add(BillingEntitlement(id=uuid.uuid4(), product_version_id=v.id, kind=e.kind, module_key=e.module_key,
                                      quota_key=e.quota_key, limit_value=e.limit_value))
        db.flush()
    return v


def update_version(db: Session, v: BillingProductVersion, *, label: str, description: str | None,
                   trial_days: int | None) -> BillingProductVersion:
    _draft(v)
    if product(db, v.product_id).kind == "addon" and trial_days is not None:
        raise BillingInvalid("Une option n'a pas d'essai")
    v.label, v.description, v.trial_days = label, description, trial_days
    db.flush()
    return v


def set_prices(db: Session, v: BillingProductVersion, prices: list[tuple[str, str, Decimal]]) -> None:
    _draft(v)
    seen = set()
    for interval, currency, amount in prices:
        if interval not in pr.INTERVALS:
            raise BillingInvalid(f"Périodicité inconnue : {interval}")
        try:
            pr.check_amount(amount, currency)
        except pr.PricingError as exc:
            raise BillingInvalid(f"Prix {interval} {currency} : {exc}") from exc
        if (interval, currency) in seen:
            raise BillingInvalid(f"Prix en double : {interval} {currency}")
        seen.add((interval, currency))
    db.execute(delete(BillingPrice).where(BillingPrice.product_version_id == v.id))
    for interval, currency, amount in prices:
        db.add(BillingPrice(id=uuid.uuid4(), product_version_id=v.id, billing_interval=interval, currency=currency,
                            amount=amount))
    db.flush()


def set_entitlements(db: Session, v: BillingProductVersion, module_keys: list[str], quotas: dict[str, int | None]) -> None:
    _draft(v)
    requires, _core = module_rules(db)
    unknown = sorted(set(module_keys) - set(requires))
    if unknown:
        raise BillingInvalid(f"Modules inconnus : {', '.join(unknown)}")
    bad = sorted(set(quotas) - set(ent.QUOTA_KEYS))
    if bad:
        raise BillingInvalid(f"Quotas inconnus : {', '.join(bad)}")
    db.execute(delete(BillingEntitlement).where(BillingEntitlement.product_version_id == v.id))
    for k in sorted(set(module_keys)):
        db.add(BillingEntitlement(id=uuid.uuid4(), product_version_id=v.id, kind="module", module_key=k))
    for k, limit in quotas.items():
        db.add(BillingEntitlement(id=uuid.uuid4(), product_version_id=v.id, kind="quota", quota_key=k, limit_value=limit))
    db.flush()


def grants(db: Session, version_id: uuid.UUID) -> list[ent.Grant]:
    rows = db.scalars(select(BillingEntitlement).where(BillingEntitlement.product_version_id == version_id))
    return [ent.Grant("module", e.module_key) if e.kind == "module" else ent.Grant("quota", e.quota_key, e.limit_value)
            for e in rows]


def prices_of(db: Session, version_id: uuid.UUID) -> list[BillingPrice]:
    return list(db.scalars(select(BillingPrice).where(BillingPrice.product_version_id == version_id)
                           .order_by(BillingPrice.billing_interval, BillingPrice.currency)))


def validation_issues(db: Session, v: BillingProductVersion) -> list[str]:
    p = product(db, v.product_id)
    requires, core = module_rules(db)
    g = grants(db, v.id)
    issues = ent.validate_plan(g, requires, core) if p.kind == "plan" else ent.validate_addon(g)
    if not prices_of(db, v.id):
        issues.insert(0, "Aucun prix saisi")
    return issues


def publish(db: Session, v: BillingProductVersion) -> BillingProductVersion:
    _draft(v)
    issues = validation_issues(db, v)
    if issues:
        raise Conflict("Version non publiable : corrigez les anomalies listées.", details={"issues": issues})
    current = db.scalar(select(BillingProductVersion).where(BillingProductVersion.product_id == v.product_id,
                                                            BillingProductVersion.status == "published"))
    if current is not None:          # la version publiée précédente est retirée : ses abonnés y restent
        current.status = "retired"
        db.flush()
    v.status = "published"
    db.flush()
    db.refresh(v)
    return v


def retire(db: Session, v: BillingProductVersion) -> BillingProductVersion:
    if v.status != "published":
        raise Conflict("Seule une version publiée se retire")
    v.status = "retired"
    db.flush()
    db.refresh(v)
    return v


def delete_draft(db: Session, v: BillingProductVersion) -> None:
    _draft(v)
    db.delete(v)
    db.flush()


def version_out(db: Session, v: BillingProductVersion) -> dict:
    return {**_out(v, VERSION_FIELDS),
            "prices": [{"billing_interval": p.billing_interval, "currency": p.currency, "amount": p.amount}
                       for p in prices_of(db, v.id)],
            "modules": sorted(g.key for g in grants(db, v.id) if g.kind == "module"),
            "quotas": {g.key: g.limit for g in grants(db, v.id) if g.kind == "quota"}}


def products_out(db: Session) -> list[dict]:
    out = []
    for p in db.scalars(select(BillingProduct).order_by(BillingProduct.kind, BillingProduct.display_order, BillingProduct.code)):
        vs = db.scalars(select(BillingProductVersion).where(BillingProductVersion.product_id == p.id)
                        .order_by(BillingProductVersion.version_no.desc()))
        out.append({**_out(p, PRODUCT_FIELDS), "versions": [version_out(db, v) for v in vs]})
    return out


def public_catalog(db: Session) -> dict:
    """Catalogue publié (session anonyme soumise à RLS : seules les versions publiées sont visibles)."""
    settings = db.execute(select(BillingSettings.country_currencies)).scalar_one()
    plans, addons = [], []
    rows = db.execute(select(BillingProduct, BillingProductVersion)
                      .join(BillingProductVersion, BillingProductVersion.product_id == BillingProduct.id)
                      .where(BillingProductVersion.status == "published")
                      .order_by(BillingProduct.display_order, BillingProduct.code)).all()
    for p, v in rows:
        item = {"product_id": p.id, "code": p.code, "name": p.name, "description": p.description,
                **{k: val for k, val in version_out(db, v).items()
                   if k in ("prices", "modules", "quotas", "trial_days", "label", "description")},
                "version_id": v.id}
        item["description"] = p.description if v.description is None else v.description
        (plans if p.kind == "plan" else addons).append(item)
    return {"plans": plans, "addons": addons, "modules": [module_out(m) for m in modules(db)],
            "countries": settings, "quota_keys": list(ent.QUOTA_KEYS)}


# ------------------------------------------------------------------ promotions
def promotions(db: Session) -> list[BillingPromotion]:
    return list(db.scalars(select(BillingPromotion).order_by(BillingPromotion.created_at.desc())))


def create_promotion(db: Session, **f) -> BillingPromotion:
    if f["discount_type"] == "fixed":
        if f.get("fixed_amount") is None or f.get("fixed_currency") is None:
            raise BillingInvalid("Remise fixe : montant et devise requis")
        try:
            pr.check_amount(f["fixed_amount"], f["fixed_currency"])
        except pr.PricingError as exc:
            raise BillingInvalid(f"Remise fixe : {exc}") from exc
    if db.scalar(select(BillingPromotion.id).where(BillingPromotion.code == f["code"])) is not None:
        raise Conflict(f"Le code {f['code']} existe déjà")
    p = BillingPromotion(id=uuid.uuid4(), **f)
    db.add(p)
    db.flush()
    db.refresh(p)
    return p


def update_promotion(db: Session, promo_id: uuid.UUID, **f) -> BillingPromotion:
    p = db.get(BillingPromotion, promo_id)
    if p is None:
        raise NotFound("Promotion introuvable")
    for k, val in f.items():
        setattr(p, k, val)
    db.flush()
    db.refresh(p)
    return p


# ------------------------------------------------------------------ paramètres
def settings(db: Session) -> BillingSettings:
    return db.execute(select(BillingSettings)).scalar_one()


def update_settings(db: Session, **f) -> BillingSettings:
    s = settings(db)
    for k, val in f.items():
        setattr(s, k, val)
    db.flush()
    db.refresh(s)
    return s
