"""Lot 12A — catalogue commercial et abonnements (sans paiement : étape 12B).

- public : catalogue publié, lisible sans connexion (session `anon` soumise à RLS) ;
- organisation : compte de facturation, abonnement, droits (affichage seulement), usages, essai, aperçu chiffré,
  demande de résiliation et son retrait ;
- administration de la plateforme : offres, versions, prix, droits, publication, promotions, paramètres.

Montants transmis en texte exact (jamais de flottant), calculés par le serveur."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator
from sqlalchemy.orm import Session

from app.api.deps import OrgContext, get_db, get_org_context, require_org_manager, require_org_owner
from app.api.v1.frameworks import require_platform_admin
from app.core.security import AuthenticatedUser
from app.db.session import anon_session
from app.engines.billing.entitlements import QUOTA_KEYS
from app.services.audit import record_event
from app.services.billing import catalog
from app.services.billing import subscriptions as subs
from app.services.management import jsonable

router = APIRouter(tags=["Abonnements (lot 12A)"])

Db = Annotated[Session, Depends(get_db)]
Member = Annotated[OrgContext, Depends(get_org_context)]
Manager = Annotated[OrgContext, Depends(require_org_manager)]
Owner = Annotated[OrgContext, Depends(require_org_owner)]
Admin = Annotated[AuthenticatedUser, Depends(require_platform_admin)]
ORG = "/organizations/{org_id}"
A = "/admin/billing"

Interval = Literal["month", "year"]
Currency = Literal["XOF", "XAF", "GNF", "KMF", "CDF"]


def get_anon_db() -> Iterator[Session]:
    with anon_session() as session:
        yield session


AnonDb = Annotated[Session, Depends(get_anon_db)]


def _log(db: Session, request: Request, user_id: uuid.UUID, action: str, entity_type: str, entity_id: uuid.UUID | None,
         details: dict | None = None, org_id: uuid.UUID | None = None) -> None:
    record_event(db, user_id=user_id, action=action, entity_type=entity_type, entity_id=entity_id,
                 organization_id=org_id, details=jsonable(details) if details else None, request=request)


# ================================================================== public
@router.get("/billing/catalog", summary="Catalogue publié : offres, options, prix par devise, modules (sans connexion)")
def public_catalog(db: AnonDb):
    return jsonable(catalog.public_catalog(db))


# ================================================================== organisation
class AccountIn(BaseModel):
    legal_name: str = Field(min_length=1, max_length=200)
    tax_id: str | None = Field(default=None, max_length=60)
    address: str = Field(min_length=1, max_length=500)
    city: str | None = Field(default=None, max_length=120)
    country_code: str = Field(pattern=r"^[A-Za-z]{2}$")
    billing_email: EmailStr

    @field_validator("country_code")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.upper()


@router.get(ORG + "/billing-account", summary="Informations de facturation (propriétaire et administrateurs)")
def get_account(ctx: Manager, db: Db):
    return jsonable({"account": subs.account_out(db, subs.account(db, ctx.organization_id))})


@router.put(ORG + "/billing-account", summary="Enregistrer les informations de facturation (propriétaire)")
def put_account(body: AccountIn, request: Request, ctx: Owner, db: Db):
    a = subs.save_account(db, ctx.organization_id, **body.model_dump())
    _log(db, request, ctx.user.id, "billing.account_updated", "billing_accounts", a.id,
         {"country_code": a.country_code}, ctx.organization_id)
    return jsonable({"account": subs.account_out(db, a)})


@router.get(ORG + "/subscription", summary="Abonnement : état, offre, échéances (propriétaire et administrateurs)")
def get_subscription(ctx: Manager, db: Db):
    return jsonable(subs.subscription_out(db, ctx.organization_id))


@router.get(ORG + "/entitlements", summary="Droits effectifs (affichage seulement : le contrôle est fait par le serveur)")
def get_entitlements(ctx: Member, db: Db):
    return jsonable(subs.entitlements_out(subs.entitlements(db, ctx.organization_id)))


@router.get(ORG + "/usage", summary="Usages mesurés et limites (propriétaire et administrateurs)")
def get_usage(ctx: Manager, db: Db):
    return jsonable(subs.usage(db, ctx.organization_id))


class TrialIn(BaseModel):
    version_id: uuid.UUID
    billing_interval: Interval = "month"


@router.post(ORG + "/subscription/trial", status_code=status.HTTP_201_CREATED,
             summary="Démarrer l'essai gratuit (propriétaire ; sans moyen de paiement)")
def start_trial(body: TrialIn, request: Request, ctx: Owner, db: Db):
    sid = subs.start_trial(db, ctx.organization_id, body.version_id, body.billing_interval)
    _log(db, request, ctx.user.id, "subscription.trial_started", "subscriptions", sid,
         {"version_id": body.version_id, "billing_interval": body.billing_interval}, ctx.organization_id)
    return jsonable(subs.subscription_out(db, ctx.organization_id))


class AddonIn(BaseModel):
    version_id: uuid.UUID
    quantity: int = Field(default=1, ge=1, le=1000)


class QuoteIn(BaseModel):
    version_id: uuid.UUID
    billing_interval: Interval = "month"
    addons: list[AddonIn] = Field(default_factory=list, max_length=20)
    promotion_code: str | None = Field(default=None, max_length=40)


@router.post(ORG + "/subscription/quote", summary="Aperçu chiffré par le serveur (aucune commande créée)")
def post_quote(body: QuoteIn, ctx: Manager, db: Db):
    return jsonable(subs.quote(db, ctx.organization_id, version_id=body.version_id, interval=body.billing_interval,
                               addons=[(a.version_id, a.quantity) for a in body.addons],
                               promotion_code=body.promotion_code))


class CancelIn(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


@router.post(ORG + "/subscription/cancel", summary="Demander la résiliation (effet en fin d'essai ou de période)")
def cancel(body: CancelIn, request: Request, ctx: Owner, db: Db):
    at = subs.schedule_cancel(db, ctx.organization_id, body.reason)
    _log(db, request, ctx.user.id, "subscription.cancel_requested", "subscriptions", None,
         {"cancel_at": at, "reason": body.reason}, ctx.organization_id)
    return jsonable(subs.subscription_out(db, ctx.organization_id))


@router.post(ORG + "/subscription/reactivate", summary="Retirer la demande de résiliation")
def reactivate(request: Request, ctx: Owner, db: Db):
    subs.reactivate(db, ctx.organization_id)
    _log(db, request, ctx.user.id, "subscription.reactivated", "subscriptions", None, None, ctx.organization_id)
    return jsonable(subs.subscription_out(db, ctx.organization_id))


# ================================================================== administration de la plateforme
@router.get(A + "/modules", summary="Modules commercialisables (modules livrés)")
def admin_modules(_admin: Admin, db: Db):
    return [catalog.module_out(m) for m in catalog.modules(db)]


@router.get(A + "/products", summary="Offres et options, avec toutes leurs versions")
def admin_products(_admin: Admin, db: Db):
    return jsonable(catalog.products_out(db))


class ProductIn(BaseModel):
    code: str = Field(pattern=r"^[A-Z0-9_]{2,40}$")
    kind: Literal["plan", "addon"]
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    display_order: int = Field(default=0, ge=0, le=10000)


class ProductPatch(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    display_order: int = Field(default=0, ge=0, le=10000)


@router.post(A + "/products", status_code=status.HTTP_201_CREATED, summary="Créer une offre ou une option")
def admin_create_product(body: ProductIn, request: Request, admin: Admin, db: Db):
    p = catalog.create_product(db, **body.model_dump())
    _log(db, request, admin.id, "admin.billing.product_created", "billing_products", p.id, {"code": p.code, "kind": p.kind})
    return jsonable(catalog._out(p, catalog.PRODUCT_FIELDS))


@router.patch(A + "/products/{product_id}", summary="Modifier le nom, la description ou l'ordre d'affichage")
def admin_update_product(product_id: uuid.UUID, body: ProductPatch, request: Request, admin: Admin, db: Db):
    p = catalog.update_product(db, catalog.product(db, product_id), **body.model_dump())
    _log(db, request, admin.id, "admin.billing.product_updated", "billing_products", p.id, body.model_dump())
    return jsonable(catalog._out(p, catalog.PRODUCT_FIELDS))


class VersionIn(BaseModel):
    label: str = Field(min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=2000)
    trial_days: int | None = Field(default=None, ge=1, le=365)
    copy_from: uuid.UUID | None = None


class VersionPatch(BaseModel):
    label: str = Field(min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=2000)
    trial_days: int | None = Field(default=None, ge=1, le=365)


@router.post(A + "/products/{product_id}/versions", status_code=status.HTTP_201_CREATED,
             summary="Nouvelle version en brouillon (éventuellement copiée d'une version existante)")
def admin_create_version(product_id: uuid.UUID, body: VersionIn, request: Request, admin: Admin, db: Db):
    v = catalog.create_version(db, catalog.product(db, product_id), **body.model_dump())
    _log(db, request, admin.id, "admin.billing.version_created", "billing_product_versions", v.id,
         {"version_no": v.version_no, "copy_from": body.copy_from})
    return jsonable(catalog.version_out(db, v))


@router.get(A + "/versions/{version_id}", summary="Version : prix, modules, quotas")
def admin_get_version(version_id: uuid.UUID, _admin: Admin, db: Db):
    return jsonable(catalog.version_out(db, catalog.version(db, version_id)))


@router.patch(A + "/versions/{version_id}", summary="Modifier un brouillon")
def admin_update_version(version_id: uuid.UUID, body: VersionPatch, request: Request, admin: Admin, db: Db):
    v = catalog.update_version(db, catalog.version(db, version_id), **body.model_dump())
    _log(db, request, admin.id, "admin.billing.version_updated", "billing_product_versions", v.id, body.model_dump())
    return jsonable(catalog.version_out(db, v))


class PriceIn(BaseModel):
    billing_interval: Interval
    currency: Currency
    amount: Decimal = Field(ge=0, max_digits=14, decimal_places=2)


class PricesIn(BaseModel):
    prices: list[PriceIn] = Field(max_length=10)


@router.put(A + "/versions/{version_id}/prices", summary="Prix d'un brouillon (remplace l'existant)")
def admin_set_prices(version_id: uuid.UUID, body: PricesIn, request: Request, admin: Admin, db: Db):
    v = catalog.version(db, version_id)
    catalog.set_prices(db, v, [(p.billing_interval, p.currency, p.amount) for p in body.prices])
    _log(db, request, admin.id, "admin.billing.prices_set", "billing_product_versions", v.id,
         {"prices": [p.model_dump() for p in body.prices]})
    return jsonable(catalog.version_out(db, v))


class EntitlementsIn(BaseModel):
    modules: list[str] = Field(default_factory=list, max_length=50)
    # limite par grandeur ; null : illimité. Une grandeur absente n'est pas accordée.
    quotas: dict[str, int | None] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check(self):
        bad = [k for k in self.quotas if k not in QUOTA_KEYS]
        if bad:
            raise ValueError(f"Quotas inconnus : {', '.join(bad)}")
        if any(v is not None and v < 0 for v in self.quotas.values()):
            raise ValueError("Limite négative")
        return self


@router.put(A + "/versions/{version_id}/entitlements", summary="Modules et quotas d'un brouillon (remplace l'existant)")
def admin_set_entitlements(version_id: uuid.UUID, body: EntitlementsIn, request: Request, admin: Admin, db: Db):
    v = catalog.version(db, version_id)
    catalog.set_entitlements(db, v, body.modules, body.quotas)
    _log(db, request, admin.id, "admin.billing.entitlements_set", "billing_product_versions", v.id, body.model_dump())
    return jsonable(catalog.version_out(db, v))


@router.post(A + "/versions/{version_id}/validate", summary="Anomalies bloquantes avant publication")
def admin_validate(version_id: uuid.UUID, _admin: Admin, db: Db):
    return {"issues": catalog.validation_issues(db, catalog.version(db, version_id))}


@router.post(A + "/versions/{version_id}/publish",
             summary="Publier (version figée ; la version publiée précédente est retirée, ses abonnés y restent)")
def admin_publish(version_id: uuid.UUID, request: Request, admin: Admin, db: Db):
    v = catalog.publish(db, catalog.version(db, version_id))
    _log(db, request, admin.id, "admin.billing.version_published", "billing_product_versions", v.id,
         {"version_no": v.version_no})
    return jsonable(catalog.version_out(db, v))


@router.post(A + "/versions/{version_id}/retire", summary="Retirer du catalogue (les abonnés y restent)")
def admin_retire(version_id: uuid.UUID, request: Request, admin: Admin, db: Db):
    v = catalog.retire(db, catalog.version(db, version_id))
    _log(db, request, admin.id, "admin.billing.version_retired", "billing_product_versions", v.id)
    return jsonable(catalog.version_out(db, v))


@router.delete(A + "/versions/{version_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Supprimer un brouillon")
def admin_delete_version(version_id: uuid.UUID, request: Request, admin: Admin, db: Db):
    v = catalog.version(db, version_id)
    catalog.delete_draft(db, v)
    _log(db, request, admin.id, "admin.billing.version_deleted", "billing_product_versions", version_id)


class PromotionIn(BaseModel):
    code: str = Field(pattern=r"^[A-Z0-9_-]{3,40}$")
    label: str = Field(min_length=1, max_length=200)
    discount_type: Literal["percent", "fixed"]
    percent: Decimal | None = Field(default=None, gt=0, le=100, decimal_places=2)
    fixed_amount: Decimal | None = Field(default=None, gt=0, max_digits=14, decimal_places=2)
    fixed_currency: Currency | None = None
    product_ids: list[uuid.UUID] | None = None
    billing_interval: Interval | None = None
    duration: Literal["once", "repeating", "forever"]
    duration_periods: int | None = Field(default=None, ge=1, le=120)
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    max_redemptions: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def _check(self):
        if self.discount_type == "percent" and (self.percent is None or self.fixed_amount is not None):
            raise ValueError("Remise en pourcentage : pourcentage seul")
        if self.discount_type == "fixed" and (self.fixed_amount is None or self.fixed_currency is None or self.percent):
            raise ValueError("Remise fixe : montant et devise")
        if (self.duration == "repeating") != (self.duration_periods is not None):
            raise ValueError("Nombre de périodes requis pour une remise répétée, et seulement pour elle")
        return self


class PromotionPatch(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=200)
    status: Literal["active", "disabled"] | None = None
    valid_until: datetime | None = None
    max_redemptions: int | None = Field(default=None, ge=1)


@router.get(A + "/promotions", summary="Promotions")
def admin_promotions(_admin: Admin, db: Db):
    return jsonable([catalog._out(p, catalog.PROMOTION_FIELDS) for p in catalog.promotions(db)])


@router.post(A + "/promotions", status_code=status.HTTP_201_CREATED, summary="Créer une promotion (conditions figées)")
def admin_create_promotion(body: PromotionIn, request: Request, admin: Admin, db: Db):
    data = body.model_dump(exclude_none=True)
    p = catalog.create_promotion(db, **data)
    _log(db, request, admin.id, "admin.billing.promotion_created", "billing_promotions", p.id, data)
    return jsonable(catalog._out(p, catalog.PROMOTION_FIELDS))


@router.patch(A + "/promotions/{promo_id}", summary="Libellé, statut, fin de validité, plafond d'utilisation")
def admin_update_promotion(promo_id: uuid.UUID, body: PromotionPatch, request: Request, admin: Admin, db: Db):
    data = body.model_dump(exclude_unset=True)
    p = catalog.update_promotion(db, promo_id, **data)
    _log(db, request, admin.id, "admin.billing.promotion_updated", "billing_promotions", p.id, data)
    return jsonable(catalog._out(p, catalog.PROMOTION_FIELDS))


class SettingsIn(BaseModel):
    grace_days: int = Field(ge=0, le=90)
    suspension_to_cancel_days: int | None = Field(default=None, ge=1, le=3650)
    renewal_notice_days: int | None = Field(default=None, ge=1, le=90)
    reminder_days: list[int] = Field(default_factory=list, max_length=10)
    max_orgs_per_user: int | None = Field(default=None, ge=1)
    seller_name: str | None = Field(default=None, max_length=200)
    seller_tax_id: str | None = Field(default=None, max_length=60)
    seller_address: str | None = Field(default=None, max_length=500)


@router.get(A + "/settings", summary="Paramètres de la plateforme (impayés, relances, vendeur, pays)")
def admin_settings(_admin: Admin, db: Db):
    return jsonable(catalog._out(catalog.settings(db), catalog.SETTINGS_FIELDS))


@router.put(A + "/settings", summary="Modifier les paramètres de la plateforme (journalisé)")
def admin_update_settings(body: SettingsIn, request: Request, admin: Admin, db: Db):
    before = catalog._out(catalog.settings(db), body.model_fields.keys())
    s = catalog.update_settings(db, **body.model_dump())
    _log(db, request, admin.id, "admin.billing.settings_updated", "billing_settings", s.id,
         {"before": before, "after": body.model_dump()})
    return jsonable(catalog._out(s, catalog.SETTINGS_FIELDS))
