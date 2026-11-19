"""Modèles ORM — contrôle interne (migration 0011)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, Date, DateTime, Integer, Numeric, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

_pk = dict(primary_key=True, server_default=text("gen_random_uuid()"))
_now = dict(server_default=text("now()"))
U = UUID(as_uuid=True)
TS = DateTime(timezone=True)


class FrameworkMapping(Base):
    __tablename__ = "framework_mappings"
    id: Mapped[uuid.UUID] = mapped_column(U, **_pk)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(U)
    source_item_id: Mapped[uuid.UUID] = mapped_column(U)
    target_item_id: Mapped[uuid.UUID] = mapped_column(U)
    relation: Mapped[str] = mapped_column(Text)
    rationale: Mapped[str] = mapped_column(Text)
    source_reference: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID] = mapped_column(U)
    created_at: Mapped[datetime] = mapped_column(TS, **_now)


class IcDomain(Base):
    __tablename__ = "ic_domains"
    id: Mapped[uuid.UUID] = mapped_column(U, **_pk)
    organization_id: Mapped[uuid.UUID] = mapped_column(U)
    company_id: Mapped[uuid.UUID] = mapped_column(U)
    code: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(Text, server_default="custom")
    template_code: Mapped[str | None] = mapped_column(Text)
    cycle_code: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    owner_name: Mapped[str | None] = mapped_column(Text)
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(U)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    display_order: Mapped[int] = mapped_column(Integer, server_default="0")
    created_by: Mapped[uuid.UUID | None] = mapped_column(U)
    created_at: Mapped[datetime] = mapped_column(TS, **_now)
    updated_at: Mapped[datetime] = mapped_column(TS, **_now)


class IcMember(Base):
    __tablename__ = "ic_members"
    id: Mapped[uuid.UUID] = mapped_column(U, **_pk)
    organization_id: Mapped[uuid.UUID] = mapped_column(U)
    company_id: Mapped[uuid.UUID] = mapped_column(U)
    user_id: Mapped[uuid.UUID] = mapped_column(U)
    role: Mapped[str] = mapped_column(Text)
    domain_id: Mapped[uuid.UUID | None] = mapped_column(U)
    granted_by: Mapped[uuid.UUID | None] = mapped_column(U)
    created_at: Mapped[datetime] = mapped_column(TS, **_now)


class ControlObjective(Base):
    __tablename__ = "control_objectives"
    id: Mapped[uuid.UUID] = mapped_column(U, **_pk)
    organization_id: Mapped[uuid.UUID] = mapped_column(U)
    company_id: Mapped[uuid.UUID] = mapped_column(U)
    domain_id: Mapped[uuid.UUID | None] = mapped_column(U)
    process_id: Mapped[uuid.UUID | None] = mapped_column(U)
    code: Mapped[str] = mapped_column(Text)
    statement: Mapped[str] = mapped_column(Text)
    assertion_codes: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    created_by: Mapped[uuid.UUID | None] = mapped_column(U)
    created_at: Mapped[datetime] = mapped_column(TS, **_now)
    updated_at: Mapped[datetime] = mapped_column(TS, **_now)


class Control(Base):
    __tablename__ = "controls"
    id: Mapped[uuid.UUID] = mapped_column(U, **_pk)
    organization_id: Mapped[uuid.UUID] = mapped_column(U)
    company_id: Mapped[uuid.UUID] = mapped_column(U)
    domain_id: Mapped[uuid.UUID | None] = mapped_column(U)
    process_id: Mapped[uuid.UUID | None] = mapped_column(U)
    objective_id: Mapped[uuid.UUID | None] = mapped_column(U)
    code: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    control_objective: Mapped[str | None] = mapped_column(Text)
    existence: Mapped[str] = mapped_column(Text, server_default="existing")
    owner_name: Mapped[str] = mapped_column(Text)
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(U)
    performer_name: Mapped[str | None] = mapped_column(Text)
    performer_user_id: Mapped[uuid.UUID | None] = mapped_column(U)
    supervisor_name: Mapped[str | None] = mapped_column(Text)
    supervisor_user_id: Mapped[uuid.UUID | None] = mapped_column(U)
    frequency: Mapped[str | None] = mapped_column(Text)
    nature: Mapped[str | None] = mapped_column(Text)
    automation: Mapped[str | None] = mapped_column(Text)
    timing: Mapped[str | None] = mapped_column(Text)
    execution_mode: Mapped[str | None] = mapped_column(Text)
    expected_evidence: Mapped[str | None] = mapped_column(Text)
    procedure_text: Mapped[str | None] = mapped_column(Text)
    success_criteria: Mapped[str | None] = mapped_column(Text)
    is_key: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    implemented_on: Mapped[date | None] = mapped_column(Date)
    operational_status: Mapped[str] = mapped_column(Text, server_default="active")
    version: Mapped[int] = mapped_column(Integer, server_default="1")
    created_by: Mapped[uuid.UUID | None] = mapped_column(U)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(U)
    created_at: Mapped[datetime] = mapped_column(TS, **_now)
    updated_at: Mapped[datetime] = mapped_column(TS, **_now)


class ControlRisk(Base):
    __tablename__ = "control_risks"
    organization_id: Mapped[uuid.UUID] = mapped_column(U)
    company_id: Mapped[uuid.UUID] = mapped_column(U)
    control_id: Mapped[uuid.UUID] = mapped_column(U, primary_key=True)
    risk_id: Mapped[uuid.UUID] = mapped_column(U, primary_key=True)
    coverage: Mapped[str] = mapped_column(Text, server_default="full")
    assertion_codes: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    rationale: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(U)
    created_at: Mapped[datetime] = mapped_column(TS, **_now)


class IcFrameworkLink(Base):
    __tablename__ = "ic_framework_links"
    id: Mapped[uuid.UUID] = mapped_column(U, **_pk)
    organization_id: Mapped[uuid.UUID] = mapped_column(U)
    company_id: Mapped[uuid.UUID] = mapped_column(U)
    object_type: Mapped[str] = mapped_column(Text)
    object_id: Mapped[uuid.UUID] = mapped_column(U)
    item_id: Mapped[uuid.UUID] = mapped_column(U)
    created_by: Mapped[uuid.UUID | None] = mapped_column(U)
    created_at: Mapped[datetime] = mapped_column(TS, **_now)


class ControlExecution(Base):
    __tablename__ = "control_executions"
    id: Mapped[uuid.UUID] = mapped_column(U, **_pk)
    organization_id: Mapped[uuid.UUID] = mapped_column(U)
    company_id: Mapped[uuid.UUID] = mapped_column(U)
    control_id: Mapped[uuid.UUID] = mapped_column(U)
    occurrence_label: Mapped[str] = mapped_column(Text)
    occurrence_date: Mapped[date] = mapped_column(Date)
    outcome: Mapped[str] = mapped_column(Text)
    comment: Mapped[str | None] = mapped_column(Text)
    exceptions: Mapped[str | None] = mapped_column(Text)
    performed_by: Mapped[uuid.UUID] = mapped_column(U)
    performed_at: Mapped[datetime] = mapped_column(TS, **_now)
    evidence_path: Mapped[str | None] = mapped_column(Text)
    evidence_filename: Mapped[str | None] = mapped_column(Text)
    evidence_mime: Mapped[str | None] = mapped_column(Text)
    evidence_size: Mapped[int | None] = mapped_column(BigInteger)
    evidence_sha256: Mapped[str | None] = mapped_column(Text)
    supervision_status: Mapped[str] = mapped_column(Text, server_default="pending")
    supervised_by: Mapped[uuid.UUID | None] = mapped_column(U)
    supervised_at: Mapped[datetime | None] = mapped_column(TS)
    supervision_comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TS, **_now)


class ControlTest(Base):
    __tablename__ = "control_tests"
    id: Mapped[uuid.UUID] = mapped_column(U, **_pk)
    organization_id: Mapped[uuid.UUID] = mapped_column(U)
    engagement_id: Mapped[uuid.UUID] = mapped_column(U)
    company_id: Mapped[uuid.UUID] = mapped_column(U)
    control_id: Mapped[uuid.UUID] = mapped_column(U)
    risk_id: Mapped[uuid.UUID | None] = mapped_column(U)
    procedure_id: Mapped[uuid.UUID | None] = mapped_column(U)
    workpaper_id: Mapped[uuid.UUID | None] = mapped_column(U)
    reference: Mapped[str] = mapped_column(Text)
    test_type: Mapped[str] = mapped_column(Text)
    test_methods: Mapped[list[str]] = mapped_column(ARRAY(Text))
    objective: Mapped[str | None] = mapped_column(Text)
    test_procedure: Mapped[str] = mapped_column(Text)
    responsible_user_id: Mapped[uuid.UUID | None] = mapped_column(U)
    period_start: Mapped[date | None] = mapped_column(Date)
    period_end: Mapped[date | None] = mapped_column(Date)
    population_description: Mapped[str | None] = mapped_column(Text)
    population_size: Mapped[int | None] = mapped_column(Integer)
    population_source: Mapped[str | None] = mapped_column(Text)
    selection_method: Mapped[str | None] = mapped_column(Text)
    sample_size: Mapped[int | None] = mapped_column(Integer)
    sample_size_basis: Mapped[str | None] = mapped_column(Text)
    selection_params: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    acceptance_criteria: Mapped[str | None] = mapped_column(Text)
    tolerable_exceptions: Mapped[int | None] = mapped_column(Integer)
    expected_result: Mapped[str | None] = mapped_column(Text)
    design_answers: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    operating_answers: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    results_summary: Mapped[str | None] = mapped_column(Text)
    exceptions_summary: Mapped[str | None] = mapped_column(Text)
    conclusion: Mapped[str | None] = mapped_column(Text)
    conclusion_rationale: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default="planned")
    prepared_by: Mapped[uuid.UUID | None] = mapped_column(U)
    prepared_at: Mapped[datetime | None] = mapped_column(TS)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(U)
    reviewed_at: Mapped[datetime | None] = mapped_column(TS)
    reopen_reason: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID] = mapped_column(U)
    created_at: Mapped[datetime] = mapped_column(TS, **_now)
    updated_at: Mapped[datetime] = mapped_column(TS, **_now)


class ControlTestItem(Base):
    __tablename__ = "control_test_items"
    id: Mapped[uuid.UUID] = mapped_column(U, **_pk)
    organization_id: Mapped[uuid.UUID] = mapped_column(U)
    engagement_id: Mapped[uuid.UUID] = mapped_column(U)
    test_id: Mapped[uuid.UUID] = mapped_column(U)
    item_ref: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    item_date: Mapped[date | None] = mapped_column(Date)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    execution_id: Mapped[uuid.UUID | None] = mapped_column(U)
    selection_order: Mapped[int | None] = mapped_column(Integer)
    result: Mapped[str] = mapped_column(Text, server_default="pending")
    exception_description: Mapped[str | None] = mapped_column(Text)
    na_reason: Mapped[str | None] = mapped_column(Text)
    tested_by: Mapped[uuid.UUID | None] = mapped_column(U)
    tested_at: Mapped[datetime | None] = mapped_column(TS)


class IcAssessment(Base):
    __tablename__ = "ic_assessments"
    id: Mapped[uuid.UUID] = mapped_column(U, **_pk)
    organization_id: Mapped[uuid.UUID] = mapped_column(U)
    engagement_id: Mapped[uuid.UUID] = mapped_column(U)
    company_id: Mapped[uuid.UUID] = mapped_column(U)
    reference: Mapped[str] = mapped_column(Text)
    scope_type: Mapped[str] = mapped_column(Text)
    domain_id: Mapped[uuid.UUID | None] = mapped_column(U)
    process_id: Mapped[uuid.UUID | None] = mapped_column(U)
    risk_id: Mapped[uuid.UUID | None] = mapped_column(U)
    control_id: Mapped[uuid.UUID | None] = mapped_column(U)
    framework_item_id: Mapped[uuid.UUID | None] = mapped_column(U)
    cycle_code: Mapped[str | None] = mapped_column(Text)
    as_of_date: Mapped[date] = mapped_column(Date)
    rating_code: Mapped[str | None] = mapped_column(Text)
    conclusion: Mapped[str | None] = mapped_column(Text)
    basis: Mapped[dict | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(Text, server_default="draft")
    prepared_by: Mapped[uuid.UUID | None] = mapped_column(U)
    prepared_at: Mapped[datetime | None] = mapped_column(TS)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(U)
    approved_at: Mapped[datetime | None] = mapped_column(TS)
    return_reason: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID] = mapped_column(U)
    created_at: Mapped[datetime] = mapped_column(TS, **_now)
    updated_at: Mapped[datetime] = mapped_column(TS, **_now)


class ControlTestReliance(Base):
    __tablename__ = "control_test_reliances"
    id: Mapped[uuid.UUID] = mapped_column(U, **_pk)
    organization_id: Mapped[uuid.UUID] = mapped_column(U)
    engagement_id: Mapped[uuid.UUID] = mapped_column(U)
    company_id: Mapped[uuid.UUID] = mapped_column(U)
    control_test_id: Mapped[uuid.UUID] = mapped_column(U)
    cycle_code: Mapped[str | None] = mapped_column(Text)
    assertion_codes: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    decision: Mapped[str] = mapped_column(Text)
    rationale: Mapped[str] = mapped_column(Text)
    approach_impact: Mapped[str | None] = mapped_column(Text)
    period_overlap: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    snapshot: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    decided_by: Mapped[uuid.UUID] = mapped_column(U)
    decided_at: Mapped[datetime] = mapped_column(TS, **_now)
    status: Mapped[str] = mapped_column(Text, server_default="active")
    withdrawn_reason: Mapped[str | None] = mapped_column(Text)


class IcHistory(Base):
    __tablename__ = "ic_history"
    id: Mapped[uuid.UUID] = mapped_column(U, **_pk)
    organization_id: Mapped[uuid.UUID] = mapped_column(U)
    company_id: Mapped[uuid.UUID] = mapped_column(U)
    object_type: Mapped[str] = mapped_column(Text)
    object_id: Mapped[uuid.UUID] = mapped_column(U)
    action: Mapped[str] = mapped_column(Text)
    reason: Mapped[str | None] = mapped_column(Text)
    before: Mapped[dict | None] = mapped_column(JSONB)
    after: Mapped[dict | None] = mapped_column(JSONB)
    changed_by: Mapped[uuid.UUID | None] = mapped_column(U)
    changed_at: Mapped[datetime] = mapped_column(TS, **_now)
