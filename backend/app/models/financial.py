"""Modèles ORM — structure des états, concepts, formules, analyses, indicateurs, alertes."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, SmallInteger, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

_uuid_pk = dict(primary_key=True, server_default=text("gen_random_uuid()"))
_now = dict(server_default=text("now()"))


class StatementLineDefinition(Base):
    __tablename__ = "statement_line_definitions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **_uuid_pk)
    framework_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("framework_versions.id"))
    statement_type: Mapped[str] = mapped_column(Text)
    line_code: Mapped[str] = mapped_column(Text)
    label: Mapped[str] = mapped_column(Text)
    display_order: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(Text)
    total_formula: Mapped[list | None] = mapped_column(JSONB)
    total_formula_text: Mapped[str | None] = mapped_column(Text)
    role: Mapped[str | None] = mapped_column(Text)
    level: Mapped[int] = mapped_column(SmallInteger, server_default="0")
    source_row: Mapped[int | None] = mapped_column(Integer)


class FrameworkConcept(Base):
    __tablename__ = "framework_concepts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **_uuid_pk)
    framework_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("framework_versions.id"))
    concept_code: Mapped[str] = mapped_column(Text)
    expression: Mapped[str] = mapped_column(Text)
    expression_ast: Mapped[dict] = mapped_column(JSONB)
    source_reference: Mapped[str | None] = mapped_column(Text)
    source_row: Mapped[int | None] = mapped_column(Integer)


class FinancialFormula(Base):
    __tablename__ = "financial_formulas"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **_uuid_pk)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    framework_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    code: Mapped[str] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(Text)
    expression: Mapped[str] = mapped_column(Text)
    expression_ast: Mapped[dict] = mapped_column(JSONB)
    unit: Mapped[str] = mapped_column(Text)
    rounding_scale: Mapped[int] = mapped_column(SmallInteger, server_default="2")
    zero_division_policy: Mapped[str] = mapped_column(Text, server_default="null")
    missing_input_policy: Mapped[str] = mapped_column(Text, server_default="null")
    description: Mapped[str | None] = mapped_column(Text)
    convention_notes: Mapped[str | None] = mapped_column(Text)
    source_reference: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default="draft")
    library_version: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_now)


class FinancialAnalysis(Base):
    __tablename__ = "financial_analyses"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    fiscal_year_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    analysis_type: Mapped[str] = mapped_column(Text)
    compared_fiscal_year_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(UUID(as_uuid=True)),
                                                                      server_default=text("'{}'"))
    parameters: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    engine_version: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default="pending")
    failure_reason: Mapped[str | None] = mapped_column(Text)
    started_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    framework_version_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    source_import_job_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    previous_fiscal_year_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    previous_import_job_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    controls: Mapped[dict | None] = mapped_column(JSONB)
    summary: Mapped[dict | None] = mapped_column(JSONB)


class FinancialStatement(Base):
    __tablename__ = "financial_statements"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    fiscal_year_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    framework_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    statement_type: Mapped[str] = mapped_column(Text)
    source_import_job_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    status: Mapped[str] = mapped_column(Text, server_default="draft")
    engine_version: Mapped[str] = mapped_column(Text)
    control_results: Mapped[list] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    generated_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_now)
    analysis_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class FinancialStatementLine(Base):
    __tablename__ = "financial_statement_lines"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **_uuid_pk)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    statement_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    line_code: Mapped[str] = mapped_column(Text)
    label: Mapped[str] = mapped_column(Text)
    display_order: Mapped[int] = mapped_column(Integer)
    is_total: Mapped[bool] = mapped_column(server_default=text("false"))
    amount_gross: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    amount_depreciation: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    amount_net: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    amount_previous: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    computation_trace: Mapped[dict | list] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    kind: Mapped[str] = mapped_column(Text, server_default="detail")
    role: Mapped[str | None] = mapped_column(Text)
    level: Mapped[int] = mapped_column(SmallInteger, server_default="0")


class FinancialIndicator(Base):
    __tablename__ = "financial_indicators"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **_uuid_pk)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    analysis_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    formula_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    formula_code: Mapped[str] = mapped_column(Text)
    formula_version: Mapped[int] = mapped_column(Integer)
    value: Mapped[Decimal | None] = mapped_column(Numeric(24, 6))
    status: Mapped[str] = mapped_column(Text)
    unit: Mapped[str] = mapped_column(Text)
    inputs: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    message: Mapped[str | None] = mapped_column(Text)
    previous_value: Mapped[Decimal | None] = mapped_column(Numeric(24, 6))
    previous_status: Mapped[str | None] = mapped_column(Text)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_now)


class FinancialAlert(Base):
    __tablename__ = "financial_alerts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **_uuid_pk)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    fiscal_year_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    analysis_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    indicator_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    severity: Mapped[str] = mapped_column(Text)
    rule_code: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    message: Mapped[str] = mapped_column(Text)
    evidence: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    status: Mapped[str] = mapped_column(Text, server_default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_now)
