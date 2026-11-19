"""Modèles ORM — référentiels (contenu), documents, importations, balances."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, SmallInteger, String, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

_uuid_pk = dict(primary_key=True, server_default=text("gen_random_uuid()"))
_now = dict(server_default=text("now()"))
Amount = Numeric(20, 2)


class ChartAccount(Base):
    __tablename__ = "chart_of_accounts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **_uuid_pk)
    framework_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("framework_versions.id"))
    account_number: Mapped[str] = mapped_column(String(20))
    label: Mapped[str] = mapped_column(Text)
    account_class: Mapped[int] = mapped_column(SmallInteger)
    parent_number: Mapped[str | None] = mapped_column(String(20))
    nature: Mapped[str | None] = mapped_column(Text)
    normal_balance: Mapped[str | None] = mapped_column(Text)
    is_postable: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    source_row: Mapped[int | None] = mapped_column(Integer)


class AccountMapping(Base):
    __tablename__ = "account_mappings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **_uuid_pk)
    framework_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("framework_versions.id"))
    organization_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    statement_type: Mapped[str] = mapped_column(Text)
    line_code: Mapped[str] = mapped_column(Text)
    line_label: Mapped[str] = mapped_column(Text)
    account_prefix: Mapped[str] = mapped_column(String(20))
    excluded_prefixes: Mapped[list[str]] = mapped_column(ARRAY(String(20)), server_default=text("'{}'"))
    balance_rule: Mapped[str] = mapped_column(Text)
    amount_column: Mapped[str] = mapped_column(Text, server_default="net")
    sign: Mapped[int] = mapped_column(SmallInteger, server_default="1")
    priority: Mapped[int] = mapped_column(Integer, server_default="100")
    source_reference: Mapped[str | None] = mapped_column(Text)
    source_row: Mapped[int | None] = mapped_column(Integer)


class FinancialDocument(Base):
    __tablename__ = "financial_documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    fiscal_year_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    document_type: Mapped[str] = mapped_column(Text)
    original_filename: Mapped[str] = mapped_column(Text)
    storage_path: Mapped[str] = mapped_column(Text)
    mime_type: Mapped[str] = mapped_column(Text)
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    is_confidential: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    uploaded_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_now)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ImportMapping(Base):
    __tablename__ = "import_mappings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **_uuid_pk)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    company_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    name: Mapped[str] = mapped_column(Text)
    source_format: Mapped[str] = mapped_column(Text)
    column_map: Mapped[dict] = mapped_column(JSONB)
    options: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    is_default: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    kind: Mapped[str] = mapped_column(Text, server_default="trial_balance")
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_now)


class ImportJob(Base):
    __tablename__ = "import_jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    fiscal_year_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    mapping_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    source_format: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(Text, server_default="trial_balance")   # trial_balance | ledger
    status: Mapped[str] = mapped_column(Text, server_default="pending")
    sheet_name: Mapped[str | None] = mapped_column(Text)
    header_row: Mapped[int | None] = mapped_column(Integer)
    column_map: Mapped[dict | None] = mapped_column(JSONB)
    preview: Mapped[dict | list | None] = mapped_column(JSONB)
    total_rows: Mapped[int | None] = mapped_column(Integer)
    valid_rows: Mapped[int | None] = mapped_column(Integer)
    error_rows: Mapped[int | None] = mapped_column(Integer)
    errors: Mapped[list] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    control_totals: Mapped[dict | None] = mapped_column(JSONB)
    celery_task_id: Mapped[str | None] = mapped_column(Text)
    started_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    validated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_reason: Mapped[str | None] = mapped_column(Text)
    sheets: Mapped[list | None] = mapped_column(JSONB)
    extraction: Mapped[dict | None] = mapped_column(JSONB)
    options: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    controls: Mapped[dict | None] = mapped_column(JSONB)
    framework_version_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    warnings_acknowledged: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    acknowledged_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_now)


class ImportStagingRow(Base):
    __tablename__ = "import_staging_rows"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **_uuid_pk)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    fiscal_year_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    import_job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    source_row: Mapped[int] = mapped_column(Integer)
    source_page: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(Text)
    account_number: Mapped[str | None] = mapped_column(String(20))
    account_label: Mapped[str | None] = mapped_column(Text)
    opening_debit: Mapped[Decimal | None] = mapped_column(Amount)
    opening_credit: Mapped[Decimal | None] = mapped_column(Amount)
    movement_debit: Mapped[Decimal | None] = mapped_column(Amount)
    movement_credit: Mapped[Decimal | None] = mapped_column(Amount)
    closing_debit: Mapped[Decimal | None] = mapped_column(Amount)
    closing_credit: Mapped[Decimal | None] = mapped_column(Amount)
    closing_computed: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    ocr_confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    issues: Mapped[list] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    raw: Mapped[list] = mapped_column(JSONB)


class TrialBalanceEntry(Base):
    __tablename__ = "trial_balance_entries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **_uuid_pk)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    fiscal_year_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    import_job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    account_number: Mapped[str] = mapped_column(String(20))
    account_label: Mapped[str | None] = mapped_column(Text)
    opening_debit: Mapped[Decimal] = mapped_column(Amount)
    opening_credit: Mapped[Decimal] = mapped_column(Amount)
    movement_debit: Mapped[Decimal] = mapped_column(Amount)
    movement_credit: Mapped[Decimal] = mapped_column(Amount)
    closing_debit: Mapped[Decimal] = mapped_column(Amount)
    closing_credit: Mapped[Decimal] = mapped_column(Amount)
    source_row: Mapped[int | None] = mapped_column(Integer)
    source_page: Mapped[int | None] = mapped_column(Integer)
    closing_computed: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    ocr_confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    raw_data: Mapped[dict | list | None] = mapped_column(JSONB)


class LedgerLine(Base):
    """Ligne d'écriture d'un grand livre importé (migration 0010)."""

    __tablename__ = "ledger_lines"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **_uuid_pk)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    fiscal_year_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    import_job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    source_row: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(Text)
    journal_code: Mapped[str | None] = mapped_column(Text)
    journal_label: Mapped[str | None] = mapped_column(Text)
    entry_number: Mapped[str | None] = mapped_column(Text)
    entry_date: Mapped[date | None] = mapped_column(Date)
    document_ref: Mapped[str | None] = mapped_column(Text)
    document_date: Mapped[date | None] = mapped_column(Date)
    account_number: Mapped[str | None] = mapped_column(String(20))
    account_label: Mapped[str | None] = mapped_column(Text)
    auxiliary_account: Mapped[str | None] = mapped_column(Text)
    auxiliary_label: Mapped[str | None] = mapped_column(Text)
    label: Mapped[str | None] = mapped_column(Text)
    debit: Mapped[Decimal] = mapped_column(Amount, server_default=text("0"))
    credit: Mapped[Decimal] = mapped_column(Amount, server_default=text("0"))
    lettering: Mapped[str | None] = mapped_column(Text)
    lettering_date: Mapped[date | None] = mapped_column(Date)
    validation_date: Mapped[date | None] = mapped_column(Date)
    currency_amount: Mapped[Decimal | None] = mapped_column(Amount)
    currency: Mapped[str | None] = mapped_column(Text)
    issues: Mapped[list] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    raw: Mapped[list] = mapped_column(JSONB)
