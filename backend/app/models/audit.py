"""Modèles ORM — socle commun d'audit (migration 0007)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, Date, DateTime, Integer, Numeric, SmallInteger, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

_uuid_pk = dict(primary_key=True, server_default=text("gen_random_uuid()"))
_now = dict(server_default=text("now()"))
U = UUID(as_uuid=True)


class MethodologyVersion(Base):
    __tablename__ = "methodology_versions"
    id: Mapped[uuid.UUID] = mapped_column(U, **_uuid_pk)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(U)
    kind: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    version_label: Mapped[str] = mapped_column(Text)
    source_reference: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default="draft")
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_by: Mapped[uuid.UUID | None] = mapped_column(U)
    # lot 9 : nature et identification du référentiel
    framework_category: Mapped[str | None] = mapped_column(Text)
    issuing_body: Mapped[str | None] = mapped_column(Text)
    published_on: Mapped[date | None] = mapped_column(Date)
    effective_from: Mapped[date | None] = mapped_column(Date)
    source_document: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID] = mapped_column(U)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_now)


class MethodologyItem(Base):
    __tablename__ = "methodology_items"
    id: Mapped[uuid.UUID] = mapped_column(U, **_uuid_pk)
    version_id: Mapped[uuid.UUID] = mapped_column(U)
    item_type: Mapped[str] = mapped_column(Text)
    code: Mapped[str] = mapped_column(Text)
    label: Mapped[str] = mapped_column(Text)
    parent_code: Mapped[str | None] = mapped_column(Text)
    content: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    display_order: Mapped[int] = mapped_column(Integer, server_default="0")
    source_row: Mapped[int | None] = mapped_column(Integer)


class Process(Base):
    __tablename__ = "processes"
    id: Mapped[uuid.UUID] = mapped_column(U, **_uuid_pk)
    organization_id: Mapped[uuid.UUID] = mapped_column(U)
    company_id: Mapped[uuid.UUID] = mapped_column(U)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(U)
    code: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    owner_name: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    domain_id: Mapped[uuid.UUID | None] = mapped_column(U)          # lot 9
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(U)      # lot 9
    created_by: Mapped[uuid.UUID | None] = mapped_column(U)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_now)


class Risk(Base):
    __tablename__ = "risks"
    id: Mapped[uuid.UUID] = mapped_column(U, **_uuid_pk)
    organization_id: Mapped[uuid.UUID] = mapped_column(U)
    company_id: Mapped[uuid.UUID] = mapped_column(U)
    process_id: Mapped[uuid.UUID | None] = mapped_column(U)
    code: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    cycle_code: Mapped[str | None] = mapped_column(Text)
    assertion_codes: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    scale_version_id: Mapped[uuid.UUID | None] = mapped_column(U)
    inherent_likelihood: Mapped[int | None] = mapped_column(SmallInteger)
    inherent_impact: Mapped[int | None] = mapped_column(SmallInteger)
    residual_likelihood: Mapped[int | None] = mapped_column(SmallInteger)
    residual_impact: Mapped[int | None] = mapped_column(SmallInteger)
    status: Mapped[str] = mapped_column(Text, server_default="active")
    # lot 9
    domain_id: Mapped[uuid.UUID | None] = mapped_column(U)
    objective_id: Mapped[uuid.UUID | None] = mapped_column(U)
    category: Mapped[str | None] = mapped_column(Text)
    causes: Mapped[str | None] = mapped_column(Text)
    consequences: Mapped[str | None] = mapped_column(Text)
    owner_name: Mapped[str | None] = mapped_column(Text)
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(U)
    control_level_code: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(U)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_now)


class Engagement(Base):
    __tablename__ = "engagements"
    id: Mapped[uuid.UUID] = mapped_column(U, **_uuid_pk)
    organization_id: Mapped[uuid.UUID] = mapped_column(U)
    company_id: Mapped[uuid.UUID] = mapped_column(U)
    fiscal_year_id: Mapped[uuid.UUID | None] = mapped_column(U)
    engagement_type: Mapped[str] = mapped_column(Text)
    reference: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    objectives: Mapped[str | None] = mapped_column(Text)
    scope: Mapped[str | None] = mapped_column(Text)
    period_start: Mapped[date | None] = mapped_column(Date)
    period_end: Mapped[date | None] = mapped_column(Date)
    planned_start: Mapped[date | None] = mapped_column(Date)
    planned_end: Mapped[date | None] = mapped_column(Date)
    methodology_version_id: Mapped[uuid.UUID | None] = mapped_column(U)
    status: Mapped[str] = mapped_column(Text, server_default="planning")
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    issued_by: Mapped[uuid.UUID | None] = mapped_column(U)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reopened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reopened_by: Mapped[uuid.UUID | None] = mapped_column(U)
    reopen_reason: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID] = mapped_column(U)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_now)


class EngagementMember(Base):
    __tablename__ = "engagement_members"
    id: Mapped[uuid.UUID] = mapped_column(U, **_uuid_pk)
    organization_id: Mapped[uuid.UUID] = mapped_column(U)
    engagement_id: Mapped[uuid.UUID] = mapped_column(U)
    user_id: Mapped[uuid.UUID] = mapped_column(U)
    role: Mapped[str] = mapped_column(Text)
    planned_hours: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    independence_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    independence_statement: Mapped[str | None] = mapped_column(Text)
    added_by: Mapped[uuid.UUID | None] = mapped_column(U)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_now)


class EngagementRisk(Base):
    __tablename__ = "engagement_risks"
    id: Mapped[uuid.UUID] = mapped_column(U, **_uuid_pk)
    organization_id: Mapped[uuid.UUID] = mapped_column(U)
    engagement_id: Mapped[uuid.UUID] = mapped_column(U)
    risk_id: Mapped[uuid.UUID | None] = mapped_column(U)
    code: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    cycle_code: Mapped[str | None] = mapped_column(Text)
    assertion_codes: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    likelihood: Mapped[int | None] = mapped_column(SmallInteger)
    impact: Mapped[int | None] = mapped_column(SmallInteger)
    is_significant: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    planned_response: Mapped[str | None] = mapped_column(Text)
    origin: Mapped[str] = mapped_column(Text, server_default="manual")
    ai_suggestion_id: Mapped[uuid.UUID | None] = mapped_column(U)
    created_by: Mapped[uuid.UUID | None] = mapped_column(U)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_now)


class WorkProgram(Base):
    __tablename__ = "work_programs"
    id: Mapped[uuid.UUID] = mapped_column(U, **_uuid_pk)
    organization_id: Mapped[uuid.UUID] = mapped_column(U)
    engagement_id: Mapped[uuid.UUID] = mapped_column(U)
    code: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    cycle_code: Mapped[str | None] = mapped_column(Text)
    objective: Mapped[str | None] = mapped_column(Text)
    display_order: Mapped[int] = mapped_column(Integer, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_now)


class Procedure(Base):
    __tablename__ = "procedures"
    id: Mapped[uuid.UUID] = mapped_column(U, **_uuid_pk)
    organization_id: Mapped[uuid.UUID] = mapped_column(U)
    engagement_id: Mapped[uuid.UUID] = mapped_column(U)
    program_id: Mapped[uuid.UUID] = mapped_column(U)
    code: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    objective: Mapped[str | None] = mapped_column(Text)
    nature: Mapped[str] = mapped_column(Text)
    steps: Mapped[list] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    assertion_codes: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    template_item_id: Mapped[uuid.UUID | None] = mapped_column(U)
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(U)
    due_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(Text, server_default="not_started")
    na_reason: Mapped[str | None] = mapped_column(Text)
    origin: Mapped[str] = mapped_column(Text, server_default="manual")
    ai_suggestion_id: Mapped[uuid.UUID | None] = mapped_column(U)
    display_order: Mapped[int] = mapped_column(Integer, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_now)


class ProcedureRisk(Base):
    __tablename__ = "procedure_risks"
    procedure_id: Mapped[uuid.UUID] = mapped_column(U, primary_key=True)
    engagement_risk_id: Mapped[uuid.UUID] = mapped_column(U, primary_key=True)
    engagement_id: Mapped[uuid.UUID] = mapped_column(U)


class Workpaper(Base):
    __tablename__ = "workpapers"
    id: Mapped[uuid.UUID] = mapped_column(U, **_uuid_pk)
    organization_id: Mapped[uuid.UUID] = mapped_column(U)
    engagement_id: Mapped[uuid.UUID] = mapped_column(U)
    procedure_id: Mapped[uuid.UUID | None] = mapped_column(U)
    reference: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    objective: Mapped[str | None] = mapped_column(Text)
    work_performed: Mapped[str | None] = mapped_column(Text)
    conclusion: Mapped[str | None] = mapped_column(Text)
    content: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    status: Mapped[str] = mapped_column(Text, server_default="draft")
    version: Mapped[int] = mapped_column(Integer, server_default="1")
    content_hash: Mapped[str] = mapped_column(Text, server_default="")
    origin: Mapped[str] = mapped_column(Text, server_default="manual")
    created_by: Mapped[uuid.UUID | None] = mapped_column(U)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(U)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_now)


class EvidenceItem(Base):
    __tablename__ = "evidence_items"
    id: Mapped[uuid.UUID] = mapped_column(U, **_uuid_pk)
    organization_id: Mapped[uuid.UUID] = mapped_column(U)
    engagement_id: Mapped[uuid.UUID] = mapped_column(U)
    kind: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text)
    obtained_on: Mapped[date] = mapped_column(Date, server_default=text("current_date"))
    storage_path: Mapped[str | None] = mapped_column(Text)
    original_filename: Mapped[str | None] = mapped_column(Text)
    mime_type: Mapped[str | None] = mapped_column(Text)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    snapshot: Mapped[dict | list | None] = mapped_column(JSONB)
    snapshot_ref: Mapped[dict | None] = mapped_column(JSONB)
    sha256: Mapped[str] = mapped_column(Text)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(U)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_now)


class EvidenceLink(Base):
    __tablename__ = "evidence_links"
    id: Mapped[uuid.UUID] = mapped_column(U, **_uuid_pk)
    engagement_id: Mapped[uuid.UUID] = mapped_column(U)
    evidence_id: Mapped[uuid.UUID] = mapped_column(U)
    object_type: Mapped[str] = mapped_column(Text)
    object_id: Mapped[uuid.UUID] = mapped_column(U)
    created_by: Mapped[uuid.UUID | None] = mapped_column(U)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_now)


class ReviewNote(Base):
    __tablename__ = "review_notes"
    id: Mapped[uuid.UUID] = mapped_column(U, **_uuid_pk)
    organization_id: Mapped[uuid.UUID] = mapped_column(U)
    engagement_id: Mapped[uuid.UUID] = mapped_column(U)
    object_type: Mapped[str] = mapped_column(Text)
    object_id: Mapped[uuid.UUID] = mapped_column(U)
    body: Mapped[str] = mapped_column(Text)
    author_id: Mapped[uuid.UUID] = mapped_column(U)
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(U)
    status: Mapped[str] = mapped_column(Text, server_default="open")
    response: Mapped[str | None] = mapped_column(Text)
    responded_by: Mapped[uuid.UUID | None] = mapped_column(U)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_by: Mapped[uuid.UUID | None] = mapped_column(U)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_now)


class Signoff(Base):
    __tablename__ = "signoffs"
    id: Mapped[uuid.UUID] = mapped_column(U, **_uuid_pk)
    organization_id: Mapped[uuid.UUID] = mapped_column(U)
    engagement_id: Mapped[uuid.UUID] = mapped_column(U)
    object_type: Mapped[str] = mapped_column(Text)
    object_id: Mapped[uuid.UUID] = mapped_column(U)
    signoff_role: Mapped[str] = mapped_column(Text)
    user_id: Mapped[uuid.UUID] = mapped_column(U)
    member_role: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(Text)
    signed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_now)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_reason: Mapped[str | None] = mapped_column(Text)
