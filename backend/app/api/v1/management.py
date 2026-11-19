"""Contrôle de gestion : centres de coûts, saisies analytiques, budgets et suivi, modèles de coûts, projections."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, File, Query, Request, Response, UploadFile, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import CompanyContext, get_company_context, get_db
from app.core.errors import Conflict, NotFound
from app.core.permissions import CompanyRole, Permission
from app.models import Budget, BudgetLineRow, Company, CostCenter, CostEntryRow, CostingModel, FiscalYear
from app.services import management as svc
from app.services.audit import record_event

router = APIRouter(prefix="/companies/{company_id}", tags=["Contrôle de gestion"])

ACCOUNT_PATTERN = r"^[0-9]{1,20}$"


def _now() -> datetime:
    return datetime.now(UTC)


def _fy(db: Session, ctx: CompanyContext, fy_id: uuid.UUID) -> FiscalYear:
    fy = db.get(FiscalYear, fy_id)
    if fy is None or fy.company_id != ctx.company_id:
        raise NotFound("Exercice introuvable")
    return fy


def _owned(db: Session, ctx: CompanyContext, model, obj_id: uuid.UUID, what: str):
    obj = db.get(model, obj_id)
    if obj is None or obj.company_id != ctx.company_id:
        raise NotFound(f"{what} introuvable")
    return obj


def _audit(db, ctx: CompanyContext, request: Request, action: str, entity_type: str, entity_id, details=None):
    record_event(db, user_id=ctx.user.id, action=action, entity_type=entity_type, entity_id=entity_id,
                 organization_id=ctx.organization_id, company_id=ctx.company_id, details=details, request=request)


# ============================================================ centres de coûts
class CostCenterIn(BaseModel):
    code: str = Field(min_length=1, max_length=30)
    name: str = Field(min_length=1, max_length=200)
    center_type: Literal["main", "auxiliary", "structure", "profit", "investment"]
    parent_id: uuid.UUID | None = None
    description: str | None = Field(default=None, max_length=2000)
    work_unit: str | None = Field(default=None, max_length=100)
    is_active: bool = True


def _center_out(c: CostCenter) -> dict:
    return {k: getattr(c, k) for k in ("id", "code", "name", "center_type", "parent_id", "description", "work_unit",
                                       "is_active")}


@router.get("/cost-centers", summary="Centres de coûts de l'entreprise")
def list_centers(ctx: CompanyContext = Depends(get_company_context), db: Session = Depends(get_db)):
    return [_center_out(c) for c in db.scalars(select(CostCenter).where(CostCenter.company_id == ctx.company_id)
                                                .order_by(CostCenter.code))]


def _check_parent(db: Session, ctx: CompanyContext, parent_id: uuid.UUID | None, self_id: uuid.UUID | None = None):
    if parent_id is None:
        return
    seen, cur = set(), parent_id
    while cur is not None:
        if cur == self_id or cur in seen:
            raise svc.ManagementInvalid("Hiérarchie circulaire : un centre ne peut pas dépendre de lui-même.")
        seen.add(cur)
        p = _owned(db, ctx, CostCenter, cur, "Centre parent")
        cur = p.parent_id


@router.post("/cost-centers", status_code=status.HTTP_201_CREATED)
def create_center(payload: CostCenterIn, request: Request, ctx: CompanyContext = Depends(get_company_context),
                  db: Session = Depends(get_db)):
    ctx.require(Permission.BUDGET_WRITE)
    _check_parent(db, ctx, payload.parent_id)
    c = CostCenter(id=uuid.uuid4(), organization_id=ctx.organization_id, company_id=ctx.company_id,
                   **payload.model_dump(exclude={"code", "name"}), code=payload.code.strip().upper(),
                   name=payload.name.strip())
    db.add(c)
    db.flush()
    _audit(db, ctx, request, "cost_center.create", "cost_centers", c.id, {"code": c.code})
    return _center_out(c)


@router.patch("/cost-centers/{center_id}")
def update_center(center_id: uuid.UUID, payload: CostCenterIn, request: Request,
                  ctx: CompanyContext = Depends(get_company_context), db: Session = Depends(get_db)):
    ctx.require(Permission.BUDGET_WRITE)
    c = _owned(db, ctx, CostCenter, center_id, "Centre")
    _check_parent(db, ctx, payload.parent_id, c.id)
    for k, v in payload.model_dump().items():
        setattr(c, k, v.strip().upper() if k == "code" else (v.strip() if k == "name" else v))
    db.flush()
    _audit(db, ctx, request, "cost_center.update", "cost_centers", c.id, payload.model_dump(mode="json"))
    return _center_out(c)


@router.delete("/cost-centers/{center_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_center(center_id: uuid.UUID, request: Request, ctx: CompanyContext = Depends(get_company_context),
                  db: Session = Depends(get_db)):
    ctx.require(Permission.BUDGET_WRITE)
    c = _owned(db, ctx, CostCenter, center_id, "Centre")
    used = (db.scalar(select(func.count()).select_from(CostEntryRow).where(CostEntryRow.cost_center_id == c.id))
            + db.scalar(select(func.count()).select_from(BudgetLineRow).where(BudgetLineRow.cost_center_id == c.id))
            + db.scalar(select(func.count()).select_from(CostCenter).where(CostCenter.parent_id == c.id)))
    if used:
        raise Conflict("Centre utilisé (saisies, lignes de budget ou sous-centres) : "
                       "désactivez-le plutôt que de le supprimer.")
    db.delete(c)
    _audit(db, ctx, request, "cost_center.delete", "cost_centers", center_id, {"code": c.code})
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ============================================================ saisies analytiques
class CostEntryIn(BaseModel):
    cost_center_id: uuid.UUID
    account_number: str | None = Field(default=None, pattern=ACCOUNT_PATTERN)
    entry_date: date
    amount: Decimal = Field(max_digits=20, decimal_places=2)
    cost_nature: Literal["direct", "indirect", "fixed", "variable", "semi_variable"]
    description: str | None = Field(default=None, max_length=500)


@router.get("/fiscal-years/{fiscal_year_id}/cost-entries", summary="Saisies analytiques de l'exercice")
def list_entries(fiscal_year_id: uuid.UUID, cost_center_id: uuid.UUID | None = None,
                 limit: int = Query(200, ge=1, le=1000), offset: int = Query(0, ge=0),
                 ctx: CompanyContext = Depends(get_company_context), db: Session = Depends(get_db)):
    _fy(db, ctx, fiscal_year_id)
    q = select(CostEntryRow).where(CostEntryRow.fiscal_year_id == fiscal_year_id)
    if cost_center_id:
        q = q.where(CostEntryRow.cost_center_id == cost_center_id)
    total = db.scalar(select(func.count()).select_from(q.subquery()))
    amount = db.scalar(select(func.coalesce(func.sum(q.subquery().c.amount), 0)))
    rows = db.scalars(q.order_by(CostEntryRow.entry_date.desc(), CostEntryRow.created_at.desc())
                      .limit(limit).offset(offset)).all()
    return {"total": total, "total_amount": svc.jsonable(Decimal(amount)), "items": [
        {k: svc.jsonable(getattr(e, k)) for k in ("id", "cost_center_id", "account_number", "entry_date", "amount",
                                                  "cost_nature", "description", "source")} for e in rows]}


@router.post("/fiscal-years/{fiscal_year_id}/cost-entries", status_code=status.HTTP_201_CREATED)
def create_entry(fiscal_year_id: uuid.UUID, payload: CostEntryIn, request: Request,
                 ctx: CompanyContext = Depends(get_company_context), db: Session = Depends(get_db)):
    ctx.require(Permission.BUDGET_WRITE)
    fy = _fy(db, ctx, fiscal_year_id)
    _owned(db, ctx, CostCenter, payload.cost_center_id, "Centre")
    if not fy.start_date <= payload.entry_date <= fy.end_date:
        raise svc.ManagementInvalid("La date doit appartenir à l'exercice.")
    e = CostEntryRow(id=uuid.uuid4(), organization_id=ctx.organization_id, company_id=ctx.company_id,
                     fiscal_year_id=fy.id, source="manual", created_by=ctx.user.id, **payload.model_dump())
    db.add(e)
    db.flush()
    _audit(db, ctx, request, "cost_entry.create", "cost_entries", e.id, payload.model_dump(mode="json"))
    return {"id": e.id}


@router.delete("/cost-entries/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_entry(entry_id: uuid.UUID, request: Request, ctx: CompanyContext = Depends(get_company_context),
                 db: Session = Depends(get_db)):
    ctx.require(Permission.BUDGET_WRITE)
    e = _owned(db, ctx, CostEntryRow, entry_id, "Saisie")
    details = {"amount": svc.jsonable(e.amount), "entry_date": e.entry_date.isoformat(), "cost_center_id": str(e.cost_center_id)}
    db.delete(e)
    db.flush()
    _audit(db, ctx, request, "cost_entry.delete", "cost_entries", entry_id, details)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ============================================================ budgets
class BudgetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    scenario: Literal["budget", "forecast"] = "budget"
    currency: str = Field(default="XOF", pattern=r"^[A-Z]{3}$")
    notes: str | None = Field(default=None, max_length=4000)


class BudgetUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    notes: str | None = Field(default=None, max_length=4000)


class BudgetLineIn(BaseModel):
    account_prefix: str | None = Field(default=None, pattern=ACCOUNT_PATTERN)
    cost_center_id: uuid.UUID | None = None
    label: str = Field(min_length=1, max_length=200)
    period: int = Field(ge=0, le=12)
    amount: Decimal = Field(max_digits=20, decimal_places=2)
    notes: str | None = Field(default=None, max_length=500)

    @field_validator("label")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()


class ProjectionItem(BaseModel):
    prefix: str = Field(pattern=ACCOUNT_PATTERN)
    label: str = Field(min_length=1, max_length=200)
    rate_pct: Decimal = Field(ge=Decimal("-100"), le=Decimal("1000"), max_digits=8, decimal_places=4)


class ProjectionIn(BaseModel):
    source_fiscal_year_id: uuid.UUID
    items: list[ProjectionItem] = Field(min_length=1, max_length=500)
    spread: Literal["annual", "equal"] = "annual"
    replace: bool = False


def _budget_out(db: Session, b: Budget, with_lines: bool = False) -> dict:
    out = {k: svc.jsonable(getattr(b, k)) for k in (
        "id", "fiscal_year_id", "name", "version", "status", "scenario", "currency", "notes", "assumptions",
        "source_budget_id", "submitted_by", "submitted_at", "approved_by", "approved_at", "created_by", "created_at")}
    lines = svc.budget_lines(db, b)
    out["total_lines"] = len(lines)
    if with_lines:
        out["lines"] = [{"id": ln.id, "account_prefix": ln.account_number, "cost_center_id": ln.cost_center_id,
                         "label": ln.label, "period": ln.period, "amount": svc.jsonable(ln.amount), "notes": ln.notes}
                        for ln in lines]
    return out


def _draft(b: Budget) -> None:
    if b.status != "draft":
        raise Conflict("Seul un budget en brouillon est modifiable : créez une nouvelle version.")


@router.get("/fiscal-years/{fiscal_year_id}/budgets", summary="Budgets et prévisions de l'exercice")
def list_budgets(fiscal_year_id: uuid.UUID, ctx: CompanyContext = Depends(get_company_context),
                 db: Session = Depends(get_db)):
    _fy(db, ctx, fiscal_year_id)
    return [_budget_out(db, b) for b in db.scalars(select(Budget).where(Budget.fiscal_year_id == fiscal_year_id)
                                                     .order_by(Budget.scenario, Budget.name, Budget.version.desc()))]


@router.post("/fiscal-years/{fiscal_year_id}/budgets", status_code=status.HTTP_201_CREATED)
def create_budget(fiscal_year_id: uuid.UUID, payload: BudgetCreate, request: Request,
                  ctx: CompanyContext = Depends(get_company_context), db: Session = Depends(get_db)):
    ctx.require(Permission.BUDGET_WRITE)
    fy = _fy(db, ctx, fiscal_year_id)
    b = Budget(id=uuid.uuid4(), organization_id=ctx.organization_id, company_id=ctx.company_id, fiscal_year_id=fy.id,
               name=payload.name.strip(), scenario=payload.scenario, currency=payload.currency, notes=payload.notes,
               assumptions={}, created_by=ctx.user.id)
    db.add(b)
    db.flush()
    _audit(db, ctx, request, "budget.create", "budgets", b.id, {"name": b.name, "scenario": b.scenario})
    return _budget_out(db, b)


@router.get("/budgets/{budget_id}")
def get_budget(budget_id: uuid.UUID, ctx: CompanyContext = Depends(get_company_context), db: Session = Depends(get_db)):
    return _budget_out(db, _owned(db, ctx, Budget, budget_id, "Budget"), with_lines=True)


@router.patch("/budgets/{budget_id}")
def update_budget(budget_id: uuid.UUID, payload: BudgetUpdate, request: Request,
                  ctx: CompanyContext = Depends(get_company_context), db: Session = Depends(get_db)):
    ctx.require(Permission.BUDGET_WRITE)
    b = _owned(db, ctx, Budget, budget_id, "Budget")
    _draft(b)
    b.name, b.notes = payload.name.strip(), payload.notes
    db.flush()
    _audit(db, ctx, request, "budget.update", "budgets", b.id, payload.model_dump())
    return _budget_out(db, b)


@router.put("/budgets/{budget_id}/lines", summary="Remplacer les lignes d'un budget en brouillon")
def replace_lines(budget_id: uuid.UUID, lines: list[BudgetLineIn], request: Request,
                  ctx: CompanyContext = Depends(get_company_context), db: Session = Depends(get_db)):
    ctx.require(Permission.BUDGET_WRITE)
    b = _owned(db, ctx, Budget, budget_id, "Budget")
    _draft(b)
    if len(lines) > 5000:
        raise svc.ManagementInvalid("5 000 lignes au maximum par budget.")
    fy = db.get(FiscalYear, b.fiscal_year_id)
    natures = svc.chart_natures(db, fy)
    keys_periods: dict[tuple, set[int]] = {}
    for ln in lines:
        if not ln.account_prefix and not ln.cost_center_id:
            raise svc.ManagementInvalid(f"Ligne « {ln.label} » : indiquez une racine de compte ou un centre de coûts.")
        if ln.account_prefix:
            svc.engine_call(svc.prefix_nature, ln.account_prefix, natures)
        if ln.cost_center_id:
            _owned(db, ctx, CostCenter, ln.cost_center_id, "Centre")
        key = (ln.account_prefix, ln.cost_center_id)
        periods = keys_periods.setdefault(key, set())
        if ln.period in periods:
            raise svc.ManagementInvalid(f"Ligne « {ln.label} » : la période {ln.period} est saisie deux fois.")
        if (ln.period == 0 and periods) or (ln.period != 0 and 0 in periods):
            raise svc.ManagementInvalid(f"Ligne « {ln.label} » : montant annuel et montants mensuels mélangés.")
        periods.add(ln.period)
    for old in svc.budget_lines(db, b):
        db.delete(old)
    db.flush()
    for ln in lines:
        db.add(BudgetLineRow(id=uuid.uuid4(), organization_id=ctx.organization_id, company_id=ctx.company_id,
                             budget_id=b.id, account_number=ln.account_prefix, cost_center_id=ln.cost_center_id,
                             label=ln.label, period=ln.period, amount=ln.amount, notes=ln.notes))
    db.flush()
    _audit(db, ctx, request, "budget.lines_replaced", "budgets", b.id, {"lines": len(lines)})
    return _budget_out(db, b, with_lines=True)


@router.post("/budgets/{budget_id}/project", summary="Prévision par hypothèses à partir du réalisé d'un exercice")
def project(budget_id: uuid.UUID, payload: ProjectionIn, request: Request,
            ctx: CompanyContext = Depends(get_company_context), db: Session = Depends(get_db)):
    ctx.require(Permission.BUDGET_WRITE)
    b = _owned(db, ctx, Budget, budget_id, "Budget")
    _draft(b)
    src = _fy(db, ctx, payload.source_fiscal_year_id)
    fy = db.get(FiscalYear, b.fiscal_year_id)
    new = svc.projected_lines(db, src, [(i.prefix, i.label.strip(), i.rate_pct) for i in payload.items],
                              payload.spread, fy)
    existing = svc.budget_lines(db, b)
    if payload.replace:
        for old in existing:
            db.delete(old)
        db.flush()
    else:
        clash = {ln.account_number for ln in existing if ln.cost_center_id is None} & {n.account_prefix for n in new}
        if clash:
            raise Conflict(f"Racines déjà budgétées : {', '.join(sorted(clash))}. Cochez « remplacer » ou retirez-les.")
    for n in new:
        db.add(BudgetLineRow(id=uuid.uuid4(), organization_id=ctx.organization_id, company_id=ctx.company_id,
                             budget_id=b.id, account_number=n.account_prefix, cost_center_id=None, label=n.label,
                             period=n.period, amount=n.amount,
                             notes=f"Réalisé {src.label} × (1 + taux)"))
    b.assumptions = {**(b.assumptions or {}), "projection": {
        "source_fiscal_year": src.label, "source_import_job_id": str(src.active_import_job_id), "spread": payload.spread,
        "items": [{"prefix": i.prefix, "label": i.label, "rate_pct": str(i.rate_pct)} for i in payload.items],
        "at": _now().isoformat(), "by": str(ctx.user.id)}}
    db.flush()
    _audit(db, ctx, request, "budget.projected", "budgets", b.id, b.assumptions["projection"])
    return _budget_out(db, b, with_lines=True)


@router.post("/budgets/{budget_id}/new-version", status_code=status.HTTP_201_CREATED,
             summary="Nouvelle version en brouillon (copie des lignes)")
def new_version(budget_id: uuid.UUID, request: Request, ctx: CompanyContext = Depends(get_company_context),
                db: Session = Depends(get_db)):
    ctx.require(Permission.BUDGET_WRITE)
    src = _owned(db, ctx, Budget, budget_id, "Budget")
    last = db.scalar(select(func.max(Budget.version)).where(Budget.fiscal_year_id == src.fiscal_year_id,
                                                             Budget.name == src.name))
    b = Budget(id=uuid.uuid4(), organization_id=ctx.organization_id, company_id=ctx.company_id,
               fiscal_year_id=src.fiscal_year_id, name=src.name, version=last + 1, scenario=src.scenario,
               currency=src.currency, notes=src.notes, assumptions=src.assumptions or {}, source_budget_id=src.id,
               created_by=ctx.user.id)
    db.add(b)
    db.flush()
    for ln in svc.budget_lines(db, src):
        db.add(BudgetLineRow(id=uuid.uuid4(), organization_id=ctx.organization_id, company_id=ctx.company_id,
                             budget_id=b.id, account_number=ln.account_number, cost_center_id=ln.cost_center_id,
                             label=ln.label, period=ln.period, amount=ln.amount, notes=ln.notes))
    db.flush()
    _audit(db, ctx, request, "budget.new_version", "budgets", b.id, {"source": str(src.id), "version": b.version})
    return _budget_out(db, b)


@router.delete("/budgets/{budget_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_budget(budget_id: uuid.UUID, request: Request, ctx: CompanyContext = Depends(get_company_context),
                  db: Session = Depends(get_db)):
    ctx.require(Permission.BUDGET_WRITE)
    b = _owned(db, ctx, Budget, budget_id, "Budget")
    _draft(b)
    db.delete(b)
    db.flush()
    _audit(db, ctx, request, "budget.delete", "budgets", budget_id, {"name": b.name, "version": b.version})
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# routes fixes (/project, /new-version) déclarées avant la route paramétrée {action}
@router.post("/budgets/{budget_id}/{action}", summary="Circuit : submit, return, approve, archive")
def transition(budget_id: uuid.UUID, action: Literal["submit", "return", "approve", "archive"], request: Request,
               ctx: CompanyContext = Depends(get_company_context), db: Session = Depends(get_db)):
    b = _owned(db, ctx, Budget, budget_id, "Budget")
    if action == "approve":
        ctx.require(Permission.BUDGET_APPROVE)
        if b.status != "submitted":
            raise Conflict("Seul un budget soumis peut être approuvé.")
        if b.created_by == ctx.user.id and ctx.role != CompanyRole.ORG_ADMIN:
            raise Conflict("Séparation des tâches : le budget doit être approuvé par une autre personne que son auteur.")
        b.status, b.approved_by, b.approved_at = "approved", ctx.user.id, _now()
    elif action == "return":
        ctx.require(Permission.BUDGET_APPROVE)
        if b.status != "submitted":
            raise Conflict("Seul un budget soumis peut être renvoyé en brouillon.")
        b.status = "draft"
    elif action == "submit":
        ctx.require(Permission.BUDGET_WRITE)
        if b.status != "draft":
            raise Conflict("Seul un brouillon peut être soumis.")
        if not svc.budget_lines(db, b):
            raise svc.ManagementInvalid("Budget vide : ajoutez des lignes avant de le soumettre.")
        b.status, b.submitted_by, b.submitted_at = "submitted", ctx.user.id, _now()
    else:
        ctx.require(Permission.BUDGET_APPROVE)
        if b.status not in ("draft", "approved"):
            raise Conflict("Seuls un brouillon ou un budget approuvé peuvent être archivés.")
        b.status = "archived"
    db.flush()   # le trigger contrôle la transition et la séparation auteur / approbateur
    _audit(db, ctx, request, f"budget.{action}", "budgets", b.id, {"status": b.status})
    return _budget_out(db, b)


@router.get("/budgets/{budget_id}/tracking", summary="Suivi budgétaire : budget, réalisé, écarts")
def budget_tracking(budget_id: uuid.UUID, ctx: CompanyContext = Depends(get_company_context),
                    db: Session = Depends(get_db),
                    source: Literal["auto", "native", "imported", "trial_balance"] | None = None):
    """Sans `source` : comportement du lot 5 (balance et grand livre importés). Avec `source` : réalisé tiré de la couche
    de pilotage (écritures natives validées en priorité, voir `services/steering.py`)."""
    b = _owned(db, ctx, Budget, budget_id, "Budget")
    return svc.tracking(db, b, db.get(FiscalYear, b.fiscal_year_id), source=source)


@router.post("/budgets/{budget_id}/lines/import", summary="Importer les lignes d'un budget en brouillon (Excel ou CSV)")
async def import_budget_lines(budget_id: uuid.UUID, request: Request, file: UploadFile = File(...), dry_run: bool = False,
                              ctx: CompanyContext = Depends(get_company_context), db: Session = Depends(get_db)):
    """Lit le fichier avec les lecteurs communs des imports, contrôle chaque ligne, puis remplace les lignes du brouillon
    par le même traitement que la saisie (`replace_lines`). `dry_run` : contrôle sans enregistrer."""
    from app.core.config import get_settings
    from app.engines.importing.files import FileRejected, validate_upload
    from app.engines.importing.readers import extract
    from app.engines.management.budget import parse_budget_sheet

    ctx.require(Permission.BUDGET_WRITE)
    b = _owned(db, ctx, Budget, budget_id, "Budget")
    _draft(b)
    cfg = get_settings()
    data = await file.read(cfg.max_upload_size_mb * 1024 * 1024 + 1)
    try:
        vf = validate_upload(file.filename or "budget", data, max_bytes=cfg.max_upload_size_mb * 1024 * 1024,
                             allowed_extensions=tuple(x for x in cfg.allowed_upload_extensions if x in ("xlsx", "xls", "csv")))
    except FileRejected as exc:
        raise svc.ManagementInvalid(str(exc)) from exc
    ex = extract(vf.extension, data)
    if not ex.sheets:
        raise svc.ManagementInvalid("Aucune feuille lisible dans le fichier.")
    parsed, errors = parse_budget_sheet(ex.sheets[0].rows)
    centers = {c.code: c.id for c in db.scalars(select(CostCenter).where(CostCenter.company_id == ctx.company_id))}
    lines: list[BudgetLineIn] = []
    for r in parsed:
        cc = None
        if r["cost_center_code"]:
            cc = centers.get(r["cost_center_code"])
            if cc is None:
                errors.append(f"« {r['label']} » : centre « {r['cost_center_code']} » inconnu.")
                continue
        try:
            lines.append(BudgetLineIn(account_prefix=r["account_prefix"], cost_center_id=cc, label=r["label"],
                                      period=r["period"], amount=r["amount"]))
        except ValueError as exc:
            errors.append(f"« {r['label']} » : {exc}")
    summary = {"file": file.filename, "sheet": ex.sheets[0].name, "lines": len(lines), "errors": errors,
               "total": str(sum((ln.amount for ln in lines), Decimal(0)))}
    if errors or dry_run:
        return {"imported": False, **summary}
    out = replace_lines(budget_id, lines, request, ctx, db)
    _audit(db, ctx, request, "budget.lines_imported", "budgets", b.id,
           {"file": file.filename, "sha256": vf.sha256, "lines": len(lines)})
    return {"imported": True, **summary, "budget": out}


# ============================================================ modèles de coûts
class ModelCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    model_type: Literal["full_cost", "cvp", "standard_cost"]
    parameters: dict = Field(default_factory=dict)


def _model_out(m: CostingModel, fy: FiscalYear | None = None, full: bool = False) -> dict:
    out = {k: svc.jsonable(getattr(m, k)) for k in ("id", "fiscal_year_id", "name", "model_type", "version", "status",
                                                     "computed_at", "validated_by", "validated_at", "created_at")}
    if full:
        out["parameters"] = m.parameters
        out["results"] = m.results
        out["results_current"] = bool(m.results) and fy is not None and svc.results_are_current(m, fy)
    return out


@router.get("/fiscal-years/{fiscal_year_id}/costing-models", summary="Modèles de calcul de coûts de l'exercice")
def list_models(fiscal_year_id: uuid.UUID, ctx: CompanyContext = Depends(get_company_context),
                db: Session = Depends(get_db)):
    _fy(db, ctx, fiscal_year_id)
    return [_model_out(m) for m in db.scalars(select(CostingModel).where(CostingModel.fiscal_year_id == fiscal_year_id)
                                              .order_by(CostingModel.model_type, CostingModel.name,
                                                        CostingModel.version.desc()))]


@router.post("/fiscal-years/{fiscal_year_id}/costing-models", status_code=status.HTTP_201_CREATED)
def create_model(fiscal_year_id: uuid.UUID, payload: ModelCreate, request: Request,
                 ctx: CompanyContext = Depends(get_company_context), db: Session = Depends(get_db)):
    ctx.require(Permission.BUDGET_WRITE)
    fy = _fy(db, ctx, fiscal_year_id)
    m = CostingModel(id=uuid.uuid4(), organization_id=ctx.organization_id, company_id=ctx.company_id,
                     fiscal_year_id=fy.id, name=payload.name.strip(), model_type=payload.model_type,
                     parameters=payload.parameters, created_by=ctx.user.id)
    db.add(m)
    db.flush()
    _audit(db, ctx, request, "costing_model.create", "costing_models", m.id, {"name": m.name, "type": m.model_type})
    return _model_out(m, fy, full=True)


@router.get("/costing-models/{model_id}")
def get_model(model_id: uuid.UUID, ctx: CompanyContext = Depends(get_company_context), db: Session = Depends(get_db)):
    m = _owned(db, ctx, CostingModel, model_id, "Modèle")
    return _model_out(m, db.get(FiscalYear, m.fiscal_year_id), full=True)


@router.put("/costing-models/{model_id}/parameters", summary="Enregistrer les paramètres (brouillon)")
def save_parameters(model_id: uuid.UUID, parameters: dict, request: Request,
                    ctx: CompanyContext = Depends(get_company_context), db: Session = Depends(get_db)):
    ctx.require(Permission.BUDGET_WRITE)
    m = _owned(db, ctx, CostingModel, model_id, "Modèle")
    if m.status != "draft":
        raise Conflict("Modèle validé : créez une nouvelle version pour le modifier.")
    if len(str(parameters)) > 500_000:
        raise svc.ManagementInvalid("Paramètres trop volumineux.")
    m.parameters = parameters
    db.flush()
    _audit(db, ctx, request, "costing_model.parameters", "costing_models", m.id,
           {"sha256": svc.params_hash(parameters)})
    return _model_out(m, db.get(FiscalYear, m.fiscal_year_id), full=True)


@router.post("/costing-models/{model_id}/compute", summary="Calculer (balance validée de l'exercice)")
def compute_model(model_id: uuid.UUID, request: Request, ctx: CompanyContext = Depends(get_company_context),
                  db: Session = Depends(get_db)):
    ctx.require(Permission.BUDGET_WRITE)
    m = _owned(db, ctx, CostingModel, model_id, "Modèle")
    if m.status != "draft":
        raise Conflict("Modèle validé : résultats figés.")
    fy = db.get(FiscalYear, m.fiscal_year_id)
    m.results = svc.compute_model(db, m, fy)
    m.computed_at = _now()
    m.balance_import_job_id = fy.active_import_job_id if m.model_type != "standard_cost" else None
    db.flush()
    _audit(db, ctx, request, "costing_model.compute", "costing_models", m.id, m.results.get("_meta"))
    return _model_out(m, fy, full=True)


@router.post("/costing-models/{model_id}/validate", summary="Valider et figer le modèle")
def validate_model(model_id: uuid.UUID, request: Request, ctx: CompanyContext = Depends(get_company_context),
                   db: Session = Depends(get_db)):
    ctx.require(Permission.BUDGET_APPROVE)
    m = _owned(db, ctx, CostingModel, model_id, "Modèle")
    fy = db.get(FiscalYear, m.fiscal_year_id)
    if m.status != "draft":
        raise Conflict("Modèle déjà validé.")
    if not m.results or not svc.results_are_current(m, fy):
        raise Conflict("Résultats absents ou périmés (paramètres ou balance modifiés depuis le calcul) : recalculez.")
    if m.model_type == "full_cost" and not m.results.get("check_passed"):
        raise Conflict("Contrôle de répartition en échec : charges incorporées ≠ coûts imputés + différences.")
    m.status, m.validated_by, m.validated_at = "validated", ctx.user.id, _now()
    db.flush()
    _audit(db, ctx, request, "costing_model.validate", "costing_models", m.id, m.results.get("_meta"))
    return _model_out(m, fy, full=True)


@router.post("/costing-models/{model_id}/new-version", status_code=status.HTTP_201_CREATED)
def model_new_version(model_id: uuid.UUID, request: Request, ctx: CompanyContext = Depends(get_company_context),
                      db: Session = Depends(get_db)):
    ctx.require(Permission.BUDGET_WRITE)
    src = _owned(db, ctx, CostingModel, model_id, "Modèle")
    last = db.scalar(select(func.max(CostingModel.version)).where(CostingModel.fiscal_year_id == src.fiscal_year_id,
                                                                   CostingModel.name == src.name))
    m = CostingModel(id=uuid.uuid4(), organization_id=ctx.organization_id, company_id=ctx.company_id,
                     fiscal_year_id=src.fiscal_year_id, name=src.name, model_type=src.model_type, version=last + 1,
                     parameters=src.parameters, created_by=ctx.user.id)
    db.add(m)
    db.flush()
    _audit(db, ctx, request, "costing_model.new_version", "costing_models", m.id, {"source": str(src.id)})
    return _model_out(m, db.get(FiscalYear, m.fiscal_year_id), full=True)


@router.delete("/costing-models/{model_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_model(model_id: uuid.UUID, request: Request, ctx: CompanyContext = Depends(get_company_context),
                 db: Session = Depends(get_db)):
    ctx.require(Permission.BUDGET_WRITE)
    m = _owned(db, ctx, CostingModel, model_id, "Modèle")
    if m.status != "draft":
        raise Conflict("Modèle validé : non supprimable.")
    db.delete(m)
    db.flush()
    _audit(db, ctx, request, "costing_model.delete", "costing_models", model_id, {"name": m.name})
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ============================================================ tableau de bord
@router.get("/fiscal-years/{fiscal_year_id}/management-dashboard", summary="Tableau de bord du contrôle de gestion")
def management_dashboard(fiscal_year_id: uuid.UUID, ctx: CompanyContext = Depends(get_company_context),
                         db: Session = Depends(get_db)):
    return svc.dashboard(db, _fy(db, ctx, fiscal_year_id))


# ============================================================ projections
@router.get("/projections", summary="Projection statistique d'une racine de compte (réalisés des exercices)")
def projections(prefix: str = Query(pattern=ACCOUNT_PATTERN), horizon: int = Query(1, ge=1, le=5),
                ctx: CompanyContext = Depends(get_company_context), db: Session = Depends(get_db)):
    return svc.account_series(db, db.get(Company, ctx.company_id), prefix, horizon)
