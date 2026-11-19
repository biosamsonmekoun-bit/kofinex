"""Modèles ORM — contrôle de gestion : centres de coûts, saisies analytiques, budgets, modèles de coûts."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, SmallInteger, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

_uuid_pk = dict(primary_key=True, server_default=text("gen_random_uuid()"))
_now = dict(server_default=text("now()"))
Amount = Numeric(20, 2)


class CostCenter(Base):
    __tablename__ = "cost_centers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **_uuid_pk)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"))
    parent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    code: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    center_type: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    work_unit: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_now)


class CostEntryRow(Base):
    __tablename__ = "cost_entries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **_uuid_pk)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    fiscal_year_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    cost_center_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    account_number: Mapped[str | None] = mapped_column(String(20))
    entry_date: Mapped[date] = mapped_column(Date)
    amount: Mapped[Decimal] = mapped_column(Amount)
    cost_nature: Mapped[str] = mapped_column(Text)
    allocation_key: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_now)


class Budget(Base):
    __tablename__ = "budgets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **_uuid_pk)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    fiscal_year_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    name: Mapped[str] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, server_default="1")
    status: Mapped[str] = mapped_column(Text, server_default="draft")
    scenario: Mapped[str] = mapped_column(Text, server_default="budget")
    currency: Mapped[str] = mapped_column(String(3), server_default="XOF")
    notes: Mapped[str | None] = mapped_column(Text)
    assumptions: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    source_budget_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    submitted_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_now)


class BudgetLineRow(Base):
    __tablename__ = "budget_lines"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **_uuid_pk)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    budget_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    cost_center_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    account_number: Mapped[str | None] = mapped_column(String(20))
    label: Mapped[str] = mapped_column(Text)
    period: Mapped[int] = mapped_column(SmallInteger)
    amount: Mapped[Decimal] = mapped_column(Amount)
    notes: Mapped[str | None] = mapped_column(Text)


class CostingModel(Base):
    __tablename__ = "costing_models"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **_uuid_pk)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    fiscal_year_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    name: Mapped[str] = mapped_column(Text)
    model_type: Mapped[str] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, server_default="1")
    status: Mapped[str] = mapped_column(Text, server_default="draft")
    parameters: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    results: Mapped[dict | None] = mapped_column(JSONB)
    computed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    balance_import_job_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    validated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_now)


class ManagementAlertSettings(Base):
    """Seuils d'alerte du contrôle de gestion, par entreprise (migration 0015). Absence de ligne : valeurs par défaut."""

    __tablename__ = "management_alert_settings"

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    consumption_info_pct: Mapped[Decimal] = mapped_column(Numeric(6, 2), server_default="80")
    overrun_warning_pct: Mapped[Decimal] = mapped_column(Numeric(6, 2), server_default="100")
    overrun_critical_pct: Mapped[Decimal] = mapped_column(Numeric(6, 2), server_default="110")
    pace_gap_points: Mapped[Decimal] = mapped_column(Numeric(6, 2), server_default="15")
    under_execution_points: Mapped[Decimal] = mapped_column(Numeric(6, 2), server_default="25")
    center_variance_pct: Mapped[Decimal] = mapped_column(Numeric(6, 2), server_default="10")
    change_pct: Mapped[Decimal] = mapped_column(Numeric(6, 2), server_default="10")
    concentration_pct: Mapped[Decimal] = mapped_column(Numeric(6, 2), server_default="30")
    updated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
