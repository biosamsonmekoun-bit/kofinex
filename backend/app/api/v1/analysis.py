"""Moteur financier : analyses d'exercice, séries pluriannuelles, bibliothèque de formules."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import CompanyContext, OrgContext, get_company_context, get_db, require_org_manager
from app.core.errors import AppError, Conflict, NotFound
from app.core.permissions import Permission
from app.engines.financial.expressions import FormulaSyntaxError, parse, references, to_text
from app.engines.financial.library import CONCEPTS
from app.models import Company, FinancialAnalysis, FinancialFormula, FiscalYear
from app.services import analysis as svc
from app.services.audit import record_event

router = APIRouter(tags=["Moteur financier"])


class FormulaRejected(AppError):
    status_code = 422
    code = "formula_invalid"


# ------------------------------------------------------------------------------ analyses
def _fy(db: Session, ctx: CompanyContext, fy_id: uuid.UUID) -> FiscalYear:
    fy = db.get(FiscalYear, fy_id)
    if fy is None or fy.company_id != ctx.company_id:
        raise NotFound("Exercice introuvable")
    return fy


def _analysis(db: Session, ctx: CompanyContext, analysis_id: uuid.UUID) -> FinancialAnalysis:
    a = db.get(FinancialAnalysis, analysis_id)
    if a is None or a.company_id != ctx.company_id:
        raise NotFound("Analyse introuvable")
    return a


@router.post("/companies/{company_id}/fiscal-years/{fiscal_year_id}/analyses", status_code=status.HTTP_201_CREATED,
             summary="Établir les états financiers et calculer les indicateurs de l'exercice")
def run_analysis(fiscal_year_id: uuid.UUID, request: Request, ctx: CompanyContext = Depends(get_company_context),
                 db: Session = Depends(get_db)):
    ctx.require(Permission.ANALYSIS_RUN)
    fy = _fy(db, ctx, fiscal_year_id)
    a = svc.run_analysis(db, company=db.get(Company, ctx.company_id), fy=fy, user_id=ctx.user.id)
    record_event(db, user_id=ctx.user.id, action="analysis.run", entity_type="financial_analyses", entity_id=a.id,
                 organization_id=ctx.organization_id, company_id=ctx.company_id,
                 details={"status": a.status, "fiscal_year": fy.label, "summary": a.summary}, request=request)
    return svc.analysis_detail(db, a)


@router.get("/companies/{company_id}/fiscal-years/{fiscal_year_id}/analyses", summary="Historique des analyses")
def list_analyses(fiscal_year_id: uuid.UUID, ctx: CompanyContext = Depends(get_company_context),
                  db: Session = Depends(get_db)):
    _fy(db, ctx, fiscal_year_id)
    rows = db.scalars(select(FinancialAnalysis).where(FinancialAnalysis.fiscal_year_id == fiscal_year_id)
                      .order_by(FinancialAnalysis.started_at.desc()).limit(50)).all()
    return [{"id": a.id, "status": a.status, "started_at": a.started_at, "completed_at": a.completed_at,
             "engine_version": a.engine_version, "summary": a.summary, "failure_reason": a.failure_reason}
            for a in rows]


@router.get("/companies/{company_id}/analyses/{analysis_id}", summary="États, indicateurs et contrôles d'une analyse")
def get_analysis(analysis_id: uuid.UUID, ctx: CompanyContext = Depends(get_company_context),
                 db: Session = Depends(get_db)):
    return svc.analysis_detail(db, _analysis(db, ctx, analysis_id))


@router.get("/companies/{company_id}/analyses/{analysis_id}/lines/{line_code}",
            summary="Comptes et règles ayant produit le montant d'une ligne d'état")
def get_line_trace(analysis_id: uuid.UUID, line_code: str, ctx: CompanyContext = Depends(get_company_context),
                   db: Session = Depends(get_db)):
    return svc.line_trace(db, _analysis(db, ctx, analysis_id), line_code)


@router.get("/companies/{company_id}/financial-series", summary="Comparaison pluriannuelle des indicateurs")
def get_series(codes: str | None = None, ctx: CompanyContext = Depends(get_company_context),
               db: Session = Depends(get_db)):
    wanted = [c.strip().upper() for c in (codes or "").split(",") if c.strip()][:60]
    return svc.series(db, db.get(Company, ctx.company_id), wanted)


# ------------------------------------------------------------------------------ bibliothèque
def _formula_out(f: FinancialFormula) -> dict:
    return {"id": f.id, "code": f.code, "version": f.version, "name": f.name, "category": f.category,
            "expression": f.expression, "unit": f.unit, "rounding_scale": f.rounding_scale,
            "zero_division_policy": f.zero_division_policy, "missing_input_policy": f.missing_input_policy,
            "description": f.description, "convention_notes": f.convention_notes, "status": f.status,
            "library_version": f.library_version, "organization_id": f.organization_id,
            "published_at": f.published_at, "custom": f.organization_id is not None}


@router.get("/financial-formulas", summary="Bibliothèque de formules (standard et propres à l'organisation)")
def list_formulas(organization_id: uuid.UUID | None = None, include_history: bool = False,
                  db: Session = Depends(get_db)):
    stmt = select(FinancialFormula)
    if organization_id:
        stmt = stmt.where(or_(FinancialFormula.organization_id.is_(None),
                              FinancialFormula.organization_id == organization_id))
    else:
        stmt = stmt.where(FinancialFormula.organization_id.is_(None))
    if not include_history:
        stmt = stmt.where(FinancialFormula.status == "published")
    rows = db.scalars(stmt.order_by(FinancialFormula.category, FinancialFormula.code,
                                    FinancialFormula.version.desc())).all()
    return [_formula_out(f) for f in rows]


class FormulaCheck(BaseModel):
    expression: str = Field(max_length=2000)


def _check_expression(db: Session, expression: str, organization_id: uuid.UUID | None, own_code: str | None) -> dict:
    try:
        node = parse(expression)
    except FormulaSyntaxError as exc:
        raise FormulaRejected(str(exc)) from exc
    known_ind = set(db.scalars(select(FinancialFormula.code).where(
        FinancialFormula.status == "published",
        or_(FinancialFormula.organization_id.is_(None), FinancialFormula.organization_id == organization_id))).all())
    if own_code:
        known_ind.add(own_code)
    refs = references(node)
    unknown = sorted({f"{fn}({a})" for fn, a in refs if (fn in ("concept", "prev_concept") and a not in CONCEPTS)
                      or (fn in ("ind", "prev_ind") and a not in known_ind)})
    if unknown:
        raise FormulaRejected(f"Références inconnues : {', '.join(unknown)}.")
    if own_code and ("ind", own_code) in refs:
        raise FormulaRejected("Une formule ne peut pas se référencer elle-même pour l'exercice courant.")
    if any(fn in ("line", "prev_line", "acct", "prev_acct") for fn, _ in refs):
        warning = ("La formule utilise des lignes ou des comptes d'un référentiel précis : elle ne sera calculable que "
                   "pour les entreprises de ce référentiel. Préférez les concepts d'analyse.")
    else:
        warning = None
    return {"ast": node, "normalized": to_text(node), "references": sorted(f"{fn}({a})" for fn, a in refs),
            "warning": warning}


@router.post("/financial-formulas/check", summary="Vérifier une expression de formule")
def check_formula(body: FormulaCheck, organization_id: uuid.UUID | None = None, db: Session = Depends(get_db)):
    r = _check_expression(db, body.expression, organization_id, None)
    return {"valid": True, "normalized": r["normalized"], "references": r["references"], "warning": r["warning"]}


class FormulaCreate(BaseModel):
    code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{1,59}$")
    name: str = Field(min_length=2, max_length=200)
    category: Literal["sig", "caf", "structure", "liquidity", "solvency", "profitability", "activity", "growth",
                      "cash", "custom"] = "custom"
    expression: str = Field(max_length=2000)
    unit: Literal["amount", "ratio", "percent", "days", "times", "years"]
    rounding_scale: int = Field(default=2, ge=0, le=6)
    zero_division_policy: Literal["null", "zero"] = "null"
    missing_input_policy: Literal["null", "zero"] = "null"
    description: str = Field(min_length=5, max_length=2000)
    convention_notes: str | None = Field(default=None, max_length=4000)

    @field_validator("code")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.upper()


@router.post("/organizations/{org_id}/financial-formulas", status_code=status.HTTP_201_CREATED,
             summary="Publier une formule propre à l'organisation (nouvelle version si le code existe)")
def create_formula(body: FormulaCreate, request: Request, ctx: OrgContext = Depends(require_org_manager),
                   db: Session = Depends(get_db)):
    checked = _check_expression(db, body.expression, ctx.organization_id, body.code)
    last = db.scalar(select(func.max(FinancialFormula.version)).where(
        FinancialFormula.organization_id == ctx.organization_id, FinancialFormula.code == body.code)) or 0
    previous = db.scalar(select(FinancialFormula).where(
        FinancialFormula.organization_id == ctx.organization_id, FinancialFormula.code == body.code,
        FinancialFormula.status == "published"))
    if previous is not None:
        previous.status = "deprecated"
        db.flush()
    f = FinancialFormula(organization_id=ctx.organization_id, framework_id=None, code=body.code, version=last + 1,
                         name=body.name.strip(), category=body.category, expression=body.expression.strip(),
                         expression_ast=checked["ast"], unit=body.unit, rounding_scale=body.rounding_scale,
                         zero_division_policy=body.zero_division_policy,
                         missing_input_policy=body.missing_input_policy, description=body.description.strip(),
                         convention_notes=body.convention_notes, status="published",
                         published_at=datetime.now(UTC), created_by=ctx.user.id)
    db.add(f)
    db.flush()
    db.refresh(f)
    record_event(db, user_id=ctx.user.id, action="formula.published", entity_type="financial_formulas",
                 entity_id=f.id, organization_id=ctx.organization_id,
                 details={"code": f.code, "version": f.version, "expression": f.expression}, request=request)
    return {**_formula_out(f), "warning": checked["warning"]}


@router.post("/organizations/{org_id}/financial-formulas/{formula_id}/deprecate",
             summary="Retirer une formule propre à l'organisation")
def deprecate_formula(formula_id: uuid.UUID, ctx: OrgContext = Depends(require_org_manager),
                      db: Session = Depends(get_db)):
    f = db.get(FinancialFormula, formula_id)
    if f is None or f.organization_id != ctx.organization_id:
        raise NotFound("Formule introuvable")
    if f.status != "published":
        raise Conflict("Seule une formule publiée peut être retirée.")
    f.status = "deprecated"
    db.flush()
    return _formula_out(f)
