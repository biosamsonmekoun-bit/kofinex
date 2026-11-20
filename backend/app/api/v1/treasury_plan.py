"""Plan de trésorerie prévisionnel (phase 4 du correctif du contrôle de gestion ; docs/CONTROLE_GESTION.md § 12.5).

Lecture : membres de l'entreprise. Saisie : `budget.write`. Approbation et archivage : `budget.approve`. La RLS et les
déclencheurs de la migration 0021 appliquent les mêmes règles en base (rôles, gel après approbation, IA exclue)."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CompanyContext, get_company_context, get_db
from app.core.errors import NotFound
from app.core.permissions import Permission
from app.engines.reporting import render
from app.models import Budget, Company, FiscalYear, Profile, TreasuryPlan
from app.services import treasury_plan as svc
from app.services.audit import record_event
from app.services.management import ManagementInvalid, jsonable

router = APIRouter(prefix="/companies/{company_id}", tags=["Contrôle de gestion"])
Source = Literal["auto", "native", "ledger", "trial_balance"]
CODE = r"^[0-9]{1,20}$"


def _fy(db: Session, ctx: CompanyContext, fy_id: uuid.UUID) -> FiscalYear:
    fy = db.get(FiscalYear, fy_id)
    if fy is None or fy.company_id != ctx.company_id:
        raise NotFound("Exercice introuvable")
    return fy


def _audit(db, ctx: CompanyContext, request: Request, action: str, entity_id, details=None):
    record_event(db, user_id=ctx.user.id, action=action, entity_type="treasury_plans", entity_id=entity_id,
                 organization_id=ctx.organization_id, company_id=ctx.company_id, details=details, request=request)


class PlanIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    opening_balance: Decimal = Field(default=Decimal(0), max_digits=20, decimal_places=2)
    template: bool = False


class PlanPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    notes: str | None = Field(default=None, max_length=5000)
    opening_balance: Decimal | None = Field(default=None, max_digits=20, decimal_places=2)
    opening_source: Literal["manual", "accounting"] | None = None


class RubricIn(BaseModel):
    key: str = Field(min_length=1, max_length=64)
    parent_key: str | None = Field(default=None, max_length=64)
    section: Literal["receipts", "disbursements"]
    code: str | None = Field(default=None, pattern=CODE)
    label: str = Field(min_length=1, max_length=200)
    order: int = Field(default=0, ge=0, le=10000)
    prefixes: list[str] = Field(default_factory=list, max_length=50)
    method: Literal["manual", "percent_of", "from_budget"] = "manual"
    base_key: str | None = Field(default=None, max_length=64)
    rate: Decimal | None = Field(default=None, ge=0, max_digits=9, decimal_places=4)
    budget_id: uuid.UUID | None = None
    delay_months: int = Field(default=0, ge=0, le=12)
    cost_center_id: uuid.UUID | None = None


class RubricsIn(BaseModel):
    rubrics: list[RubricIn] = Field(max_length=500)


class AmountIn(BaseModel):
    rubric_id: uuid.UUID
    period: int = Field(ge=1, le=12)
    amount: Decimal = Field(ge=0, max_digits=20, decimal_places=2)


class AmountsIn(BaseModel):
    scenario: Literal["initial", "updated"]
    amounts: list[AmountIn] = Field(max_length=6000)


def _plan(db, ctx, plan_id) -> TreasuryPlan:
    return svc.plan(db, ctx.company_id, plan_id)


def _detail(db, p: TreasuryPlan) -> dict:
    return jsonable({**svc.out(p), "rubrics": [svc.rubric_out(r) for r in svc.rubrics(db, p)],
                     "amounts": {s: svc.amounts(db, p, s) for s in svc.SCENARIOS}})


@router.get("/fiscal-years/{fy_id}/treasury-plans")
def list_plans(fy_id: uuid.UUID, ctx: CompanyContext = Depends(get_company_context), db: Session = Depends(get_db)):
    fy = _fy(db, ctx, fy_id)
    ps = db.scalars(select(TreasuryPlan).where(TreasuryPlan.fiscal_year_id == fy.id).order_by(TreasuryPlan.created_at))
    return jsonable([svc.out(p) for p in ps])


@router.post("/fiscal-years/{fy_id}/treasury-plans", status_code=status.HTTP_201_CREATED)
def create_plan(fy_id: uuid.UUID, payload: PlanIn, request: Request, ctx: CompanyContext = Depends(get_company_context),
                db: Session = Depends(get_db)):
    ctx.require(Permission.BUDGET_WRITE)
    fy = _fy(db, ctx, fy_id)
    p = svc.create(db, db.get(Company, ctx.company_id), fy, ctx.user.id, name=payload.name.strip(),
                   opening_balance=payload.opening_balance, template=payload.template)
    _audit(db, ctx, request, "treasury_plan.create", p.id, {"name": p.name, "template": payload.template})
    return _detail(db, p)


@router.get("/fiscal-years/{fy_id}/treasury-plans/opening-proposal")
def opening_proposal(fy_id: uuid.UUID, source: Source = "auto", ctx: CompanyContext = Depends(get_company_context),
                     db: Session = Depends(get_db)):
    return svc.opening_proposal(db, db.get(Company, ctx.company_id), _fy(db, ctx, fy_id), source)


@router.get("/fiscal-years/{fy_id}/treasury-plans/budgets")
def budgets(fy_id: uuid.UUID, ctx: CompanyContext = Depends(get_company_context), db: Session = Depends(get_db)):
    """Budgets de l'exercice proposés pour la modalité « budget décalé »."""
    fy = _fy(db, ctx, fy_id)
    bs = db.scalars(select(Budget).where(Budget.fiscal_year_id == fy.id).order_by(Budget.name, Budget.version))
    return jsonable([{"id": b.id, "name": b.name, "version": b.version, "status": b.status} for b in bs])


@router.get("/treasury-plans/{plan_id}")
def get_plan(plan_id: uuid.UUID, ctx: CompanyContext = Depends(get_company_context), db: Session = Depends(get_db)):
    return _detail(db, _plan(db, ctx, plan_id))


@router.patch("/treasury-plans/{plan_id}")
def patch_plan(plan_id: uuid.UUID, payload: PlanPatch, request: Request, ctx: CompanyContext = Depends(get_company_context),
               db: Session = Depends(get_db)):
    ctx.require(Permission.BUDGET_WRITE)
    p = svc.update(db, _plan(db, ctx, plan_id), name=payload.name, notes=payload.notes,
                   opening_balance=payload.opening_balance, opening_source=payload.opening_source)
    _audit(db, ctx, request, "treasury_plan.update", p.id, payload.model_dump(mode="json", exclude_none=True))
    return _detail(db, p)


@router.delete("/treasury-plans/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_plan(plan_id: uuid.UUID, request: Request, ctx: CompanyContext = Depends(get_company_context),
                db: Session = Depends(get_db)):
    ctx.require(Permission.BUDGET_WRITE)
    p = _plan(db, ctx, plan_id)
    svc._draft(p)
    _audit(db, ctx, request, "treasury_plan.delete", p.id, {"name": p.name})
    db.delete(p)
    db.flush()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/treasury-plans/{plan_id}/rubrics")
def put_rubrics(plan_id: uuid.UUID, payload: RubricsIn, request: Request, ctx: CompanyContext = Depends(get_company_context),
                db: Session = Depends(get_db)):
    ctx.require(Permission.BUDGET_WRITE)
    p = _plan(db, ctx, plan_id)
    for r in payload.rubrics:
        if r.budget_id is not None:
            b = db.get(Budget, r.budget_id)
            if b is None or b.company_id != ctx.company_id:
                raise ManagementInvalid(f"Rubrique « {r.label} » : budget introuvable.")
        if any(not x.isdigit() for x in r.prefixes):
            raise ManagementInvalid(f"Rubrique « {r.label} » : les comptes associés sont des racines numériques.")
    svc.replace_rubrics(db, p, [r.model_dump() for r in payload.rubrics])
    _audit(db, ctx, request, "treasury_plan.rubrics", p.id, {"count": len(payload.rubrics)})
    return _detail(db, p)


@router.put("/treasury-plans/{plan_id}/amounts")
def put_amounts(plan_id: uuid.UUID, payload: AmountsIn, request: Request, ctx: CompanyContext = Depends(get_company_context),
                db: Session = Depends(get_db)):
    ctx.require(Permission.BUDGET_WRITE)
    p = _plan(db, ctx, plan_id)
    svc.set_amounts(db, p, payload.scenario, [(a.rubric_id, a.period, a.amount) for a in payload.amounts])
    _audit(db, ctx, request, "treasury_plan.amounts", p.id, {"scenario": payload.scenario, "count": len(payload.amounts)})
    return _detail(db, p)


@router.post("/treasury-plans/{plan_id}/rubrics/{rubric_id}/calculate")
def calculate(plan_id: uuid.UUID, rubric_id: uuid.UUID, request: Request,
              scenario: Literal["initial", "updated"] = "initial",
              ctx: CompanyContext = Depends(get_company_context), db: Session = Depends(get_db)):
    ctx.require(Permission.BUDGET_WRITE)
    p = _plan(db, ctx, plan_id)
    r = svc.calculate(db, p, rubric_id, scenario)
    _audit(db, ctx, request, "treasury_plan.calculate", p.id, {"rubric_id": str(rubric_id), "scenario": scenario,
                                                                "basis": r["basis"]})
    return jsonable(r)


@router.post("/treasury-plans/{plan_id}/approve")
def approve(plan_id: uuid.UUID, request: Request, ctx: CompanyContext = Depends(get_company_context),
            db: Session = Depends(get_db)):
    ctx.require(Permission.BUDGET_APPROVE)
    p = svc.transition(db, _plan(db, ctx, plan_id), "approved")
    _audit(db, ctx, request, "treasury_plan.approve", p.id)
    return _detail(db, p)


@router.post("/treasury-plans/{plan_id}/archive")
def archive(plan_id: uuid.UUID, request: Request, ctx: CompanyContext = Depends(get_company_context),
            db: Session = Depends(get_db)):
    ctx.require(Permission.BUDGET_APPROVE)
    p = svc.transition(db, _plan(db, ctx, plan_id), "archived")
    _audit(db, ctx, request, "treasury_plan.archive", p.id)
    return _detail(db, p)


@router.get("/treasury-plans/{plan_id}/view")
def view(plan_id: uuid.UUID, scenario: Literal["initial", "updated"] | None = None, source: Source = "auto",
         as_of: date | None = None, ctx: CompanyContext = Depends(get_company_context), db: Session = Depends(get_db)):
    return svc.view(db, db.get(Company, ctx.company_id), _plan(db, ctx, plan_id), scenario=scenario, source=source,
                    as_of=as_of)


@router.get("/treasury-plans/{plan_id}/rolling")
def rolling(plan_id: uuid.UUID, as_of: date | None = None, source: Source = "auto",
            ctx: CompanyContext = Depends(get_company_context), db: Session = Depends(get_db)):
    return svc.rolling(db, db.get(Company, ctx.company_id), _plan(db, ctx, plan_id), as_of=as_of, source=source)


@router.get("/treasury-plans/{plan_id}/export")
def export(plan_id: uuid.UUID, request: Request, fmt: Literal["xlsx", "pdf"] = Query("xlsx", alias="format"),
           scenario: Literal["initial", "updated"] | None = None, source: Source = "auto",
           ctx: CompanyContext = Depends(get_company_context), db: Session = Depends(get_db)):
    p = _plan(db, ctx, plan_id)
    prof = db.get(Profile, ctx.user.id)
    doc, meta = svc.document(db, db.get(Company, ctx.company_id), p, scenario, source,
                             (prof.full_name or prof.email) if prof else None)
    body = render.to_xlsx(doc, meta) if fmt == "xlsx" else render.to_pdf(doc, meta)
    _audit(db, ctx, request, "treasury_plan.export", p.id, {"format": fmt, "data_sha256": meta["data_sha256"]})
    media = ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" if fmt == "xlsx" else "application/pdf")
    return Response(content=body, media_type=media,
                    headers={"Content-Disposition": f"attachment; filename=plan-tresorerie-{p.id}.{fmt}"})
