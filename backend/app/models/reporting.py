"""Modèles ORM — reporting (tables du lot 1 complétées par la migration 0013)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

_pk = dict(primary_key=True, server_default=text("gen_random_uuid()"))
_now = dict(server_default=text("now()"))
U = UUID(as_uuid=True)
TS = DateTime(timezone=True)


class ReportTemplate(Base):
    __tablename__ = "report_templates"
    id: Mapped[uuid.UUID] = mapped_column(U, **_pk)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(U)
    name: Mapped[str] = mapped_column(Text)
    report_kind: Mapped[str] = mapped_column(Text, server_default="custom")
    document_type: Mapped[str] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, server_default="1")
    status: Mapped[str] = mapped_column(Text, server_default="draft")
    sections: Mapped[list] = mapped_column(JSONB)
    content: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    branding: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    is_default: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    published_by: Mapped[uuid.UUID | None] = mapped_column(U)
    published_at: Mapped[datetime | None] = mapped_column(TS)
    created_by: Mapped[uuid.UUID | None] = mapped_column(U)
    created_at: Mapped[datetime] = mapped_column(TS, **_now)
    updated_at: Mapped[datetime] = mapped_column(TS, **_now)


class GeneratedReport(Base):
    __tablename__ = "generated_reports"
    id: Mapped[uuid.UUID] = mapped_column(U, **_pk)
    organization_id: Mapped[uuid.UUID] = mapped_column(U)
    company_id: Mapped[uuid.UUID] = mapped_column(U)
    analysis_id: Mapped[uuid.UUID | None] = mapped_column(U)
    engagement_id: Mapped[uuid.UUID | None] = mapped_column(U)
    template_id: Mapped[uuid.UUID | None] = mapped_column(U)
    template_version: Mapped[int | None] = mapped_column(Integer)
    document_type: Mapped[str] = mapped_column(Text)
    subtype: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(Text)
    format: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    storage_path: Mapped[str | None] = mapped_column(Text)
    filename: Mapped[str | None] = mapped_column(Text)
    mime_type: Mapped[str | None] = mapped_column(Text)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    sha256: Mapped[str | None] = mapped_column(Text)
    data_sha256: Mapped[str | None] = mapped_column(Text)
    content_snapshot: Mapped[dict | None] = mapped_column(JSONB)
    source_refs: Mapped[list] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    parameters: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    ai_report_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(U), server_default="{}")
    contains_ai_drafts: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    generator_version: Mapped[str | None] = mapped_column(Text)
    failure_reason: Mapped[str | None] = mapped_column(Text)
    requested_by: Mapped[uuid.UUID] = mapped_column(U)
    created_at: Mapped[datetime] = mapped_column(TS, **_now)
    completed_at: Mapped[datetime | None] = mapped_column(TS)
