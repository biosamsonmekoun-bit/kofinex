"""Modèles ORM — comptabilité générale native (lot 3B) : paramètres, plan comptable de l'entreprise, tiers, journaux,
séquences, écritures natives, lignes, pièces, historique du circuit, lettrages (migration 0014).

Ces tables sont distinctes des imports (ledger_lines, trial_balance_entries). Les règles (équilibre, circuit,
immutabilité, numérotation, lettrage) sont imposées par la base ; l'ORM ne fait que lire et écrire."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, Integer, Numeric, String, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

_uuid_pk = dict(primary_key=True, server_default=text("gen_random_uuid()"))
_now = dict(server_default=text("now()"))


class AccountingSettings(Base):
    __tablename__ = "accounting_settings"

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    review_required: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    segregation_required: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    updated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_now)


class CompanyAccount(Base):
    __tablename__ = "company_accounts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **_uuid_pk)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    account_number: Mapped[str] = mapped_column(String(20))
    label: Mapped[str] = mapped_column(Text)
    framework_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    chart_account_number: Mapped[str] = mapped_column(String(20))
    nature: Mapped[str | None] = mapped_column(Text)
    requires_third_party: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    third_party_kind: Mapped[str | None] = mapped_column(Text)
    lettering_enabled: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_now)


class ThirdParty(Base):
    __tablename__ = "third_parties"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **_uuid_pk)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    code: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(Text)
    collective_account_number: Mapped[str | None] = mapped_column(String(20))
    tax_id: Mapped[str | None] = mapped_column(Text)
    registration_number: Mapped[str | None] = mapped_column(Text)
    address: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(Text)
    country_code: Mapped[str | None] = mapped_column(String(2))
    email: Mapped[str | None] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_now)


class Journal(Base):
    __tablename__ = "journals"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **_uuid_pk)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    code: Mapped[str] = mapped_column(Text)
    label: Mapped[str] = mapped_column(Text)
    journal_type: Mapped[str] = mapped_column(Text)
    number_prefix: Mapped[str] = mapped_column(Text)
    counterpart_account_number: Mapped[str | None] = mapped_column(String(20))
    allowed_users: Mapped[list[uuid.UUID] | None] = mapped_column(ARRAY(UUID(as_uuid=True)))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_now)


class JournalSequence(Base):
    __tablename__ = "journal_sequences"

    journal_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    fiscal_year_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    last_number: Mapped[int] = mapped_column(Integer)


class JournalEntry(Base):
    __tablename__ = "journal_entries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **_uuid_pk)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    fiscal_year_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    journal_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    entry_date: Mapped[date] = mapped_column(Date)
    piece_ref: Mapped[str | None] = mapped_column(Text)
    piece_date: Mapped[date | None] = mapped_column(Date)
    label: Mapped[str] = mapped_column(Text)
    third_party_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    origin: Mapped[str] = mapped_column(Text, server_default="manual")
    source_type: Mapped[str | None] = mapped_column(Text)
    source_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    reverses_entry_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    corrects_entry_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    status: Mapped[str] = mapped_column(Text, server_default="draft")
    number: Mapped[str | None] = mapped_column(Text)
    sequence_no: Mapped[int | None] = mapped_column(Integer)
    total_debit: Mapped[Decimal] = mapped_column(Numeric(20, 2), server_default="0")
    total_credit: Mapped[Decimal] = mapped_column(Numeric(20, 2), server_default="0")
    line_count: Mapped[int] = mapped_column(Integer, server_default="0")
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    submitted_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    validated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejected_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    reversed_by_entry_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_now)


class JournalEntryLine(Base):
    __tablename__ = "journal_entry_lines"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **_uuid_pk)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    fiscal_year_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    entry_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    line_no: Mapped[int] = mapped_column(Integer)
    account_number: Mapped[str] = mapped_column(String(20))
    third_party_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    label: Mapped[str | None] = mapped_column(Text)
    debit: Mapped[Decimal] = mapped_column(Numeric(20, 2), server_default="0")
    credit: Mapped[Decimal] = mapped_column(Numeric(20, 2), server_default="0")
    cost_center_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    currency: Mapped[str | None] = mapped_column(String(3))
    currency_amount: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    lettering_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class JournalEntryAttachment(Base):
    __tablename__ = "journal_entry_attachments"

    entry_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    attached_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    attached_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_now)


class JournalEntryEvent(Base):
    __tablename__ = "journal_entry_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **_uuid_pk)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    entry_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    action: Mapped[str] = mapped_column(Text)
    from_status: Mapped[str | None] = mapped_column(Text)
    to_status: Mapped[str | None] = mapped_column(Text)
    actor: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_now)


class Lettering(Base):
    __tablename__ = "letterings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **_uuid_pk)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    account_number: Mapped[str] = mapped_column(String(20))
    third_party_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    code: Mapped[str] = mapped_column(Text)
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 2))
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_now)
