"""Modèles ORM — Fichier des Écritures Comptables (FEC) DGI Bénin : historique des générations et traçabilité des
lignes (migration 0016). Les règles (copie figée, version suivante, nommage, auteur, sources validées) sont imposées par
la base ; l'ORM ne fait que lire et insérer."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, Date, DateTime, Integer, Numeric, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class FecExport(Base):
    __tablename__ = "fec_exports"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    fiscal_year_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    version_no: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(10))
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    ifu: Mapped[str] = mapped_column(Text)
    filename: Mapped[str] = mapped_column(Text)
    file_format: Mapped[str] = mapped_column(String(3))
    encoding: Mapped[str] = mapped_column(String(15))
    field_separator: Mapped[str] = mapped_column(String(10))
    record_separator: Mapped[str] = mapped_column(String(4))
    max_lines_per_file: Mapped[int | None] = mapped_column(Integer)
    accounting_type: Mapped[str] = mapped_column(String(10))
    line_count: Mapped[int] = mapped_column(Integer)
    entry_count: Mapped[int] = mapped_column(Integer)
    total_debit: Mapped[Decimal] = mapped_column(Numeric(20, 2))
    total_credit: Mapped[Decimal] = mapped_column(Numeric(20, 2))
    blocking_count: Mapped[int] = mapped_column(Integer)
    warning_count: Mapped[int] = mapped_column(Integer)
    compliance: Mapped[str] = mapped_column(String(15))
    spec_version: Mapped[str] = mapped_column(Text)
    spec_confirmed: Mapped[bool] = mapped_column(Boolean)
    anomalies: Mapped[list] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    source_state: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    parts: Mapped[list] = mapped_column(JSONB)
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64))
    doc_storage_path: Mapped[str] = mapped_column(Text)
    doc_sha256: Mapped[str] = mapped_column(String(64))
    generator_version: Mapped[str] = mapped_column(Text)
    generated_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))


class FecExportLine(Base):
    __tablename__ = "fec_export_lines"

    export_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    row_no: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    entry_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    entry_line_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
