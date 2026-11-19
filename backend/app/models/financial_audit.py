"""Modèles ORM — audit financier et comptable (migration 0008)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, Computed, Date, DateTime, Integer, Numeric, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

_uuid_pk = dict(primary_key=True, server_default=text("gen_random_uuid()"))
_now = dict(server_default=text("now()"))
U = UUID(as_uuid=True)
M = Numeric(20, 2)
P = Numeric(7, 4)


class FaMateriality(Base):
    __tablename__ = "fa_materiality"
    id: Mapped[uuid.UUID] = mapped_column(U, **_uuid_pk)
    organization_id: Mapped[uuid.UUID] = mapped_column(U)
    engagement_id: Mapped[uuid.UUID] = mapped_column(U)
    version: Mapped[int] = mapped_column(Integer)
    benchmark_label: Mapped[str] = mapped_column(Text)
    benchmark_source: Mapped[str] = mapped_column(Text)
    benchmark_line_code: Mapped[str | None] = mapped_column(Text)
    source_import_job_id: Mapped[uuid.UUID | None] = mapped_column(U)
    benchmark_amount: Mapped[Decimal] = mapped_column(M)
    overall_pct: Mapped[Decimal] = mapped_column(P)
    overall_amount: Mapped[Decimal] = mapped_column(M)
    performance_pct: Mapped[Decimal] = mapped_column(P)
    performance_amount: Mapped[Decimal] = mapped_column(M)
    trivial_pct: Mapped[Decimal] = mapped_column(P)
    trivial_amount: Mapped[Decimal] = mapped_column(M)
    basis: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default="draft")
    created_by: Mapped[uuid.UUID] = mapped_column(U)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(U)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_now)


class FaCycleMapping(Base):
    __tablename__ = "fa_cycle_mappings"
    id: Mapped[uuid.UUID] = mapped_column(U, **_uuid_pk)
    organization_id: Mapped[uuid.UUID] = mapped_column(U)
    engagement_id: Mapped[uuid.UUID] = mapped_column(U)
    account_prefix: Mapped[str] = mapped_column(Text)
    cycle_code: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_now)


class FaAccountReview(Base):
    __tablename__ = "fa_account_reviews"
    id: Mapped[uuid.UUID] = mapped_column(U, **_uuid_pk)
    organization_id: Mapped[uuid.UUID] = mapped_column(U)
    engagement_id: Mapped[uuid.UUID] = mapped_column(U)
    account_number: Mapped[str] = mapped_column(Text)
    account_label: Mapped[str | None] = mapped_column(Text)
    cycle_code: Mapped[str | None] = mapped_column(Text)
    source_import_job_id: Mapped[uuid.UUID] = mapped_column(U)
    previous_import_job_id: Mapped[uuid.UUID | None] = mapped_column(U)
    balance_n: Mapped[Decimal] = mapped_column(M)
    balance_n1: Mapped[Decimal | None] = mapped_column(M)
    variation: Mapped[Decimal | None] = mapped_column(M, Computed("balance_n - balance_n1"))
    threshold_used: Mapped[Decimal | None] = mapped_column(M)
    requires_explanation: Mapped[bool] = mapped_column(Boolean, server_default="false")
    explanation: Mapped[str | None] = mapped_column(Text)
    conclusion: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default="to_review")
    workpaper_id: Mapped[uuid.UUID | None] = mapped_column(U)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(U)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_now)


class FaPopulation(Base):
    __tablename__ = "fa_populations"
    id: Mapped[uuid.UUID] = mapped_column(U, **_uuid_pk)
    organization_id: Mapped[uuid.UUID] = mapped_column(U)
    engagement_id: Mapped[uuid.UUID] = mapped_column(U)
    name: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text)
    account_prefixes: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    source_import_job_id: Mapped[uuid.UUID | None] = mapped_column(U)
    source_evidence_id: Mapped[uuid.UUID | None] = mapped_column(U)
    filters: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    item_count: Mapped[int] = mapped_column(Integer)
    total_amount: Mapped[Decimal] = mapped_column(M)
    absolute_total: Mapped[Decimal] = mapped_column(M)
    sha256: Mapped[str] = mapped_column(Text)
    created_by: Mapped[uuid.UUID] = mapped_column(U)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_now)


class FaPopulationItem(Base):
    __tablename__ = "fa_population_items"
    id: Mapped[uuid.UUID] = mapped_column(U, **_uuid_pk)
    organization_id: Mapped[uuid.UUID] = mapped_column(U)
    engagement_id: Mapped[uuid.UUID] = mapped_column(U)
    population_id: Mapped[uuid.UUID] = mapped_column(U)
    line_no: Mapped[int] = mapped_column(Integer)
    reference: Mapped[str] = mapped_column(Text)
    item_date: Mapped[date | None] = mapped_column(Date)
    label: Mapped[str | None] = mapped_column(Text)
    account_number: Mapped[str | None] = mapped_column(Text)
    amount: Mapped[Decimal] = mapped_column(M)
    ledger_line_id: Mapped[uuid.UUID | None] = mapped_column(U)


class FaSample(Base):
    __tablename__ = "fa_samples"
    id: Mapped[uuid.UUID] = mapped_column(U, **_uuid_pk)
    organization_id: Mapped[uuid.UUID] = mapped_column(U)
    engagement_id: Mapped[uuid.UUID] = mapped_column(U)
    population_id: Mapped[uuid.UUID] = mapped_column(U)
    reference: Mapped[str] = mapped_column(Text)
    objective: Mapped[str] = mapped_column(Text)
    method: Mapped[str] = mapped_column(Text)
    requested_size: Mapped[int | None] = mapped_column(Integer)
    size_basis: Mapped[str] = mapped_column(Text)
    seed: Mapped[int | None] = mapped_column(BigInteger)
    parameters: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    selected_count: Mapped[int] = mapped_column(Integer)
    procedure_id: Mapped[uuid.UUID | None] = mapped_column(U)
    workpaper_id: Mapped[uuid.UUID | None] = mapped_column(U)
    status: Mapped[str] = mapped_column(Text, server_default="testing")
    actual_misstatement: Mapped[Decimal | None] = mapped_column(M)
    projected_misstatement: Mapped[Decimal | None] = mapped_column(M)
    projection: Mapped[dict | None] = mapped_column(JSONB)
    conclusion: Mapped[str | None] = mapped_column(Text)
    concluded_by: Mapped[uuid.UUID | None] = mapped_column(U)
    concluded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID] = mapped_column(U)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_now)


class FaSampleItem(Base):
    __tablename__ = "fa_sample_items"
    id: Mapped[uuid.UUID] = mapped_column(U, **_uuid_pk)
    organization_id: Mapped[uuid.UUID] = mapped_column(U)
    engagement_id: Mapped[uuid.UUID] = mapped_column(U)
    sample_id: Mapped[uuid.UUID] = mapped_column(U)
    population_item_id: Mapped[uuid.UUID] = mapped_column(U)
    selection_reason: Mapped[str] = mapped_column(Text)
    book_amount: Mapped[Decimal] = mapped_column(M)
    audited_amount: Mapped[Decimal | None] = mapped_column(M)
    misstatement: Mapped[Decimal | None] = mapped_column(M, Computed("book_amount - audited_amount"))
    result: Mapped[str] = mapped_column(Text, server_default="pending")
    comment: Mapped[str | None] = mapped_column(Text)
    tested_by: Mapped[uuid.UUID | None] = mapped_column(U)
    tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class FaConfirmation(Base):
    __tablename__ = "fa_confirmations"
    id: Mapped[uuid.UUID] = mapped_column(U, **_uuid_pk)
    organization_id: Mapped[uuid.UUID] = mapped_column(U)
    engagement_id: Mapped[uuid.UUID] = mapped_column(U)
    reference: Mapped[str] = mapped_column(Text)
    confirmation_type: Mapped[str] = mapped_column(Text)
    third_party: Mapped[str] = mapped_column(Text)
    contact: Mapped[str | None] = mapped_column(Text)
    account_number: Mapped[str | None] = mapped_column(Text)
    balance_date: Mapped[date] = mapped_column(Date)
    book_balance: Mapped[Decimal | None] = mapped_column(M)
    request_form: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default="prepared")
    sent_on: Mapped[date | None] = mapped_column(Date)
    reminder_dates: Mapped[list[date]] = mapped_column(ARRAY(Date), server_default="{}")
    received_on: Mapped[date | None] = mapped_column(Date)
    confirmed_amount: Mapped[Decimal | None] = mapped_column(M)
    difference: Mapped[Decimal | None] = mapped_column(M, Computed("book_balance - confirmed_amount"))
    reconciliation: Mapped[str | None] = mapped_column(Text)
    alternative_procedures: Mapped[str | None] = mapped_column(Text)
    conclusion: Mapped[str | None] = mapped_column(Text)
    population_item_id: Mapped[uuid.UUID | None] = mapped_column(U)
    workpaper_id: Mapped[uuid.UUID | None] = mapped_column(U)
    created_by: Mapped[uuid.UUID] = mapped_column(U)
    closed_by: Mapped[uuid.UUID | None] = mapped_column(U)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_now)


class FaMisstatement(Base):
    __tablename__ = "fa_misstatements"
    id: Mapped[uuid.UUID] = mapped_column(U, **_uuid_pk)
    organization_id: Mapped[uuid.UUID] = mapped_column(U)
    engagement_id: Mapped[uuid.UUID] = mapped_column(U)
    reference: Mapped[str] = mapped_column(Text)
    source_type: Mapped[str] = mapped_column(Text)
    source_id: Mapped[uuid.UUID | None] = mapped_column(U)
    kind: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default="proposed")
    entity_response: Mapped[str | None] = mapped_column(Text)
    withdrawn_reason: Mapped[str | None] = mapped_column(Text)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(U)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID] = mapped_column(U)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_now)


class FaMisstatementLine(Base):
    __tablename__ = "fa_misstatement_lines"
    id: Mapped[uuid.UUID] = mapped_column(U, **_uuid_pk)
    organization_id: Mapped[uuid.UUID] = mapped_column(U)
    engagement_id: Mapped[uuid.UUID] = mapped_column(U)
    misstatement_id: Mapped[uuid.UUID] = mapped_column(U)
    account_number: Mapped[str] = mapped_column(Text)
    label: Mapped[str | None] = mapped_column(Text)
    debit: Mapped[Decimal] = mapped_column(M, server_default="0")
    credit: Mapped[Decimal] = mapped_column(M, server_default="0")


class FaConclusion(Base):
    __tablename__ = "fa_conclusions"
    engagement_id: Mapped[uuid.UUID] = mapped_column(U, primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(U)
    uncorrected_conclusion: Mapped[str] = mapped_column(Text)
    updated_by: Mapped[uuid.UUID] = mapped_column(U)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_now)
