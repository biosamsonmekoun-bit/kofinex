"""Modèles ORM — audit interne (migration 0009)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, Integer, Numeric, SmallInteger, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

_pk = dict(primary_key=True, server_default=text("gen_random_uuid()"))
_now = dict(server_default=text("now()"))
U = UUID(as_uuid=True)
TS = DateTime(timezone=True)


class AuditPlan(Base):
    __tablename__ = "audit_plans"
    id: Mapped[uuid.UUID] = mapped_column(U, **_pk)
    organization_id: Mapped[uuid.UUID] = mapped_column(U)
    title: Mapped[str] = mapped_column(Text)
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default="draft")
    approval_body: Mapped[str | None] = mapped_column(Text)
    approval_reference: Mapped[str | None] = mapped_column(Text)
    approval_date: Mapped[date | None] = mapped_column(Date)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(U)
    approved_at: Mapped[datetime | None] = mapped_column(TS)
    created_by: Mapped[uuid.UUID] = mapped_column(U)
    created_at: Mapped[datetime] = mapped_column(TS, **_now)
    updated_at: Mapped[datetime] = mapped_column(TS, **_now)


class AuditPlanItem(Base):
    __tablename__ = "audit_plan_items"
    id: Mapped[uuid.UUID] = mapped_column(U, **_pk)
    organization_id: Mapped[uuid.UUID] = mapped_column(U)
    plan_id: Mapped[uuid.UUID] = mapped_column(U)
    company_id: Mapped[uuid.UUID] = mapped_column(U)
    process_id: Mapped[uuid.UUID | None] = mapped_column(U)
    title: Mapped[str] = mapped_column(Text)
    rationale: Mapped[str] = mapped_column(Text)
    priority_rank: Mapped[int | None] = mapped_column(Integer)
    planned_start: Mapped[date | None] = mapped_column(Date)
    planned_end: Mapped[date | None] = mapped_column(Date)
    budget_days: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    engagement_id: Mapped[uuid.UUID | None] = mapped_column(U)
    status: Mapped[str] = mapped_column(Text, server_default="planned")
    status_reason: Mapped[str | None] = mapped_column(Text)
    added_after_approval: Mapped[bool] = mapped_column(Boolean, server_default="false")
    change_reason: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID] = mapped_column(U)
    created_at: Mapped[datetime] = mapped_column(TS, **_now)
    updated_at: Mapped[datetime] = mapped_column(TS, **_now)


class AuditPlanItemHistory(Base):
    __tablename__ = "audit_plan_item_history"
    id: Mapped[uuid.UUID] = mapped_column(U, **_pk)
    organization_id: Mapped[uuid.UUID] = mapped_column(U)
    plan_item_id: Mapped[uuid.UUID] = mapped_column(U)
    operation: Mapped[str] = mapped_column(Text)
    before: Mapped[dict | None] = mapped_column(JSONB)
    after: Mapped[dict] = mapped_column(JSONB)
    reason: Mapped[str | None] = mapped_column(Text)
    changed_by: Mapped[uuid.UUID | None] = mapped_column(U)
    changed_at: Mapped[datetime] = mapped_column(TS, **_now)


class RiskRatingHistory(Base):
    __tablename__ = "risk_rating_history"
    id: Mapped[uuid.UUID] = mapped_column(U, **_pk)
    organization_id: Mapped[uuid.UUID] = mapped_column(U)
    company_id: Mapped[uuid.UUID] = mapped_column(U)
    risk_id: Mapped[uuid.UUID] = mapped_column(U)
    scale_version_id: Mapped[uuid.UUID | None] = mapped_column(U)
    inherent_likelihood: Mapped[int | None] = mapped_column(SmallInteger)
    inherent_impact: Mapped[int | None] = mapped_column(SmallInteger)
    residual_likelihood: Mapped[int | None] = mapped_column(SmallInteger)
    residual_impact: Mapped[int | None] = mapped_column(SmallInteger)
    control_level_code: Mapped[str | None] = mapped_column(Text)     # lot 9
    changed_by: Mapped[uuid.UUID | None] = mapped_column(U)
    changed_at: Mapped[datetime] = mapped_column(TS, **_now)


class Finding(Base):
    __tablename__ = "findings"
    id: Mapped[uuid.UUID] = mapped_column(U, **_pk)
    organization_id: Mapped[uuid.UUID] = mapped_column(U)
    engagement_id: Mapped[uuid.UUID] = mapped_column(U)
    reference: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    condition: Mapped[str] = mapped_column(Text)
    criteria: Mapped[str] = mapped_column(Text)
    cause: Mapped[str | None] = mapped_column(Text)
    effect: Mapped[str | None] = mapped_column(Text)
    rating_code: Mapped[str | None] = mapped_column(Text)
    process_id: Mapped[uuid.UUID | None] = mapped_column(U)
    engagement_risk_id: Mapped[uuid.UUID | None] = mapped_column(U)
    workpaper_id: Mapped[uuid.UUID | None] = mapped_column(U)
    status: Mapped[str] = mapped_column(Text, server_default="draft")
    validated_by: Mapped[uuid.UUID | None] = mapped_column(U)
    validated_at: Mapped[datetime | None] = mapped_column(TS)
    communicated_by: Mapped[uuid.UUID | None] = mapped_column(U)
    communicated_at: Mapped[datetime | None] = mapped_column(TS)
    response_due: Mapped[date | None] = mapped_column(Date)
    management_response: Mapped[str | None] = mapped_column(Text)
    response_by_name: Mapped[str | None] = mapped_column(Text)
    response_user_id: Mapped[uuid.UUID | None] = mapped_column(U)
    response_recorded_by: Mapped[uuid.UUID | None] = mapped_column(U)
    response_at: Mapped[datetime | None] = mapped_column(TS)
    reopen_reason: Mapped[str | None] = mapped_column(Text)
    # lot 9 : nature (constat d'audit, déficience de contrôle interne…), rattachements, clôture
    # lot 10 : provenance (projet rédigé par l'IA puis accepté par un auditeur)
    origin: Mapped[str] = mapped_column(Text, server_default="manual")
    ai_suggestion_id: Mapped[uuid.UUID | None] = mapped_column(U)
    kind: Mapped[str] = mapped_column(Text, server_default="audit_finding")
    control_id: Mapped[uuid.UUID | None] = mapped_column(U)
    risk_id: Mapped[uuid.UUID | None] = mapped_column(U)
    domain_id: Mapped[uuid.UUID | None] = mapped_column(U)
    closed_by: Mapped[uuid.UUID | None] = mapped_column(U)
    closed_at: Mapped[datetime | None] = mapped_column(TS)
    closure_note: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID] = mapped_column(U)
    created_at: Mapped[datetime] = mapped_column(TS, **_now)
    updated_at: Mapped[datetime] = mapped_column(TS, **_now)


class Recommendation(Base):
    __tablename__ = "recommendations"
    id: Mapped[uuid.UUID] = mapped_column(U, **_pk)
    organization_id: Mapped[uuid.UUID] = mapped_column(U)
    engagement_id: Mapped[uuid.UUID] = mapped_column(U)
    finding_id: Mapped[uuid.UUID] = mapped_column(U)
    reference: Mapped[str] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text)
    created_by: Mapped[uuid.UUID] = mapped_column(U)
    created_at: Mapped[datetime] = mapped_column(TS, **_now)


class ActionPlan(Base):
    __tablename__ = "action_plans"
    id: Mapped[uuid.UUID] = mapped_column(U, **_pk)
    organization_id: Mapped[uuid.UUID] = mapped_column(U)
    engagement_id: Mapped[uuid.UUID] = mapped_column(U)
    company_id: Mapped[uuid.UUID] = mapped_column(U)
    recommendation_id: Mapped[uuid.UUID] = mapped_column(U)
    description: Mapped[str] = mapped_column(Text)
    owner_name: Mapped[str] = mapped_column(Text)
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(U)
    due_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(Text, server_default="planned")
    created_by: Mapped[uuid.UUID] = mapped_column(U)
    created_at: Mapped[datetime] = mapped_column(TS, **_now)
    updated_at: Mapped[datetime] = mapped_column(TS, **_now)


class ActionPlanUpdate(Base):
    __tablename__ = "action_plan_updates"
    id: Mapped[uuid.UUID] = mapped_column(U, **_pk)
    organization_id: Mapped[uuid.UUID] = mapped_column(U)
    engagement_id: Mapped[uuid.UUID] = mapped_column(U)
    action_plan_id: Mapped[uuid.UUID] = mapped_column(U)
    status: Mapped[str] = mapped_column(Text)
    comment: Mapped[str] = mapped_column(Text)
    new_due_date: Mapped[date | None] = mapped_column(Date)
    author_id: Mapped[uuid.UUID] = mapped_column(U)
    author_role: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TS, **_now)


class AuditReport(Base):
    __tablename__ = "audit_reports"
    id: Mapped[uuid.UUID] = mapped_column(U, **_pk)
    organization_id: Mapped[uuid.UUID] = mapped_column(U)
    engagement_id: Mapped[uuid.UUID] = mapped_column(U)
    version: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(Text)
    executive_summary: Mapped[str | None] = mapped_column(Text)
    overall_conclusion: Mapped[str | None] = mapped_column(Text)
    distribution: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default="draft")
    snapshot: Mapped[dict | None] = mapped_column(JSONB)
    content_sha256: Mapped[str | None] = mapped_column(Text)
    issued_by: Mapped[uuid.UUID | None] = mapped_column(U)
    issued_at: Mapped[datetime | None] = mapped_column(TS)
    created_by: Mapped[uuid.UUID] = mapped_column(U)
    created_at: Mapped[datetime] = mapped_column(TS, **_now)
    updated_at: Mapped[datetime] = mapped_column(TS, **_now)
