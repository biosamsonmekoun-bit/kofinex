"""Modèles ORM du lot 12A (sql/0018_billing_catalog.sql) : catalogue, compte de facturation, paramètres.

Les abonnements ne sont pas écrits par l'ORM : l'essai, la résiliation et son retrait passent par les fonctions
SQL de la migration 0018, qui imposent les règles en base."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import ARRAY, Boolean, DateTime, Integer, Numeric, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

_now = dict(server_default=text("now()"))
# identifiants fournis par l'application : pas de RETURNING sur les valeurs par défaut serveur
_no_returning = {"eager_defaults": False}


class BillingSettings(Base):
    __tablename__ = "billing_settings"
    __mapper_args__ = _no_returning

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    grace_days: Mapped[int] = mapped_column(Integer)
    suspension_to_cancel_days: Mapped[int | None] = mapped_column(Integer)
    renewal_notice_days: Mapped[int | None] = mapped_column(Integer)
    reminder_days: Mapped[list[int]] = mapped_column(ARRAY(Integer))
    max_orgs_per_user: Mapped[int | None] = mapped_column(Integer)
    seller_name: Mapped[str | None] = mapped_column(Text)
    seller_country: Mapped[str] = mapped_column(String(2))
    seller_tax_id: Mapped[str | None] = mapped_column(Text)
    seller_address: Mapped[str | None] = mapped_column(Text)
    country_currencies: Mapped[dict] = mapped_column(JSONB)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_now)


class BillingModule(Base):
    __tablename__ = "billing_modules"
    __mapper_args__ = _no_returning

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    label: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    requires: Mapped[list[str]] = mapped_column(ARRAY(Text))
    is_core: Mapped[bool] = mapped_column(Boolean)
    display_order: Mapped[int] = mapped_column(Integer)


class BillingProduct(Base):
    __tablename__ = "billing_products"
    __mapper_args__ = _no_returning

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    code: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    display_order: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_now)


class BillingProductVersion(Base):
    __tablename__ = "billing_product_versions"
    __mapper_args__ = _no_returning

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    version_no: Mapped[int] = mapped_column(Integer)
    label: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default=text("'draft'"))
    trial_days: Mapped[int | None] = mapped_column(Integer)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_now)


class BillingPrice(Base):
    __tablename__ = "billing_prices"
    __mapper_args__ = _no_returning

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    product_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    billing_interval: Mapped[str] = mapped_column(Text)
    currency: Mapped[str] = mapped_column(String(3))
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))


class BillingEntitlement(Base):
    __tablename__ = "billing_entitlements"
    __mapper_args__ = _no_returning

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    product_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    kind: Mapped[str] = mapped_column(Text)
    module_key: Mapped[str | None] = mapped_column(Text)
    quota_key: Mapped[str | None] = mapped_column(Text)
    limit_value: Mapped[int | None] = mapped_column(Integer)


class BillingPromotion(Base):
    __tablename__ = "billing_promotions"
    __mapper_args__ = _no_returning

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    code: Mapped[str] = mapped_column(Text)
    label: Mapped[str] = mapped_column(Text)
    discount_type: Mapped[str] = mapped_column(Text)
    percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    fixed_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    fixed_currency: Mapped[str | None] = mapped_column(String(3))
    product_ids: Mapped[list[uuid.UUID] | None] = mapped_column(ARRAY(UUID(as_uuid=True)))
    billing_interval: Mapped[str | None] = mapped_column(Text)
    duration: Mapped[str] = mapped_column(Text)
    duration_periods: Mapped[int | None] = mapped_column(Integer)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_now)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    max_redemptions: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(Text, server_default=text("'active'"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_now)


class BillingAccount(Base):
    __tablename__ = "billing_accounts"
    __mapper_args__ = _no_returning

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    legal_name: Mapped[str] = mapped_column(Text)
    tax_id: Mapped[str | None] = mapped_column(Text)
    address: Mapped[str] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(Text)
    country_code: Mapped[str] = mapped_column(String(2))
    billing_email: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_now)
