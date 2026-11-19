"""Modèles ORM — intelligence artificielle (tables du lot 1 complétées et migration 0012)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

_pk = dict(primary_key=True, server_default=text("gen_random_uuid()"))
_now = dict(server_default=text("now()"))
U = UUID(as_uuid=True)
TS = DateTime(timezone=True)


class AiSettings(Base):
    __tablename__ = "ai_settings"
    organization_id: Mapped[uuid.UUID] = mapped_column(U, primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    allowed_uses: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    acceptance_note: Mapped[str | None] = mapped_column(Text)
    updated_by: Mapped[uuid.UUID] = mapped_column(U)
    updated_at: Mapped[datetime] = mapped_column(TS, **_now)


class AiConversation(Base):
    __tablename__ = "ai_conversations"
    id: Mapped[uuid.UUID] = mapped_column(U, **_pk)
    organization_id: Mapped[uuid.UUID] = mapped_column(U)
    company_id: Mapped[uuid.UUID] = mapped_column(U)
    fiscal_year_id: Mapped[uuid.UUID | None] = mapped_column(U)
    analysis_id: Mapped[uuid.UUID | None] = mapped_column(U)
    user_id: Mapped[uuid.UUID] = mapped_column(U)
    title: Mapped[str | None] = mapped_column(Text)
    purpose: Mapped[str] = mapped_column(Text, server_default="finance_assistant")
    created_at: Mapped[datetime] = mapped_column(TS, **_now)
    updated_at: Mapped[datetime] = mapped_column(TS, **_now)


class AiMessage(Base):
    __tablename__ = "ai_messages"
    id: Mapped[uuid.UUID] = mapped_column(U, **_pk)
    organization_id: Mapped[uuid.UUID] = mapped_column(U)
    conversation_id: Mapped[uuid.UUID] = mapped_column(U)
    role: Mapped[str] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text)
    context_snapshot: Mapped[dict | None] = mapped_column(JSONB)
    model: Mapped[str | None] = mapped_column(Text)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    validation: Mapped[dict | None] = mapped_column(JSONB)
    prompt_version: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TS, **_now)


class AiReport(Base):
    __tablename__ = "ai_reports"
    id: Mapped[uuid.UUID] = mapped_column(U, **_pk)
    organization_id: Mapped[uuid.UUID] = mapped_column(U)
    company_id: Mapped[uuid.UUID] = mapped_column(U)
    analysis_id: Mapped[uuid.UUID] = mapped_column(U)
    section: Mapped[str] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text)
    context_snapshot: Mapped[dict] = mapped_column(JSONB)
    model: Mapped[str] = mapped_column(Text)
    prompt_version: Mapped[str] = mapped_column(Text)
    validation: Mapped[dict | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(Text, server_default="draft")
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(U)
    reviewed_at: Mapped[datetime | None] = mapped_column(TS)
    review_note: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID] = mapped_column(U)
    created_at: Mapped[datetime] = mapped_column(TS, **_now)


class AiSuggestion(Base):
    __tablename__ = "ai_suggestions"
    id: Mapped[uuid.UUID] = mapped_column(U, **_pk)
    organization_id: Mapped[uuid.UUID] = mapped_column(U)
    company_id: Mapped[uuid.UUID] = mapped_column(U)
    engagement_id: Mapped[uuid.UUID] = mapped_column(U)
    kind: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSONB)
    sources: Mapped[list] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    context_snapshot: Mapped[dict] = mapped_column(JSONB)
    validation: Mapped[dict] = mapped_column(JSONB)
    model: Mapped[str] = mapped_column(Text)
    prompt_version: Mapped[str] = mapped_column(Text)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(Text, server_default="pending")
    requested_by: Mapped[uuid.UUID] = mapped_column(U)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(U)
    decided_at: Mapped[datetime | None] = mapped_column(TS)
    decision_note: Mapped[str | None] = mapped_column(Text)
    accepted_payload: Mapped[dict | None] = mapped_column(JSONB)
    created_object_type: Mapped[str | None] = mapped_column(Text)
    created_object_id: Mapped[uuid.UUID | None] = mapped_column(U)
    created_at: Mapped[datetime] = mapped_column(TS, **_now)
