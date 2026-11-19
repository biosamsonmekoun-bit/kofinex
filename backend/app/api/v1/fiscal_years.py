from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CompanyContext, get_company_context, get_db
from app.core.errors import Conflict, Forbidden, NotFound
from app.core.permissions import CompanyRole, Permission
from app.models import FiscalYear
from app.schemas.tenancy import FiscalYearCreate, FiscalYearOut
from app.services.audit import record_event

router = APIRouter(prefix="/companies/{company_id}/fiscal-years", tags=["Exercices comptables"])


def _get(db: Session, ctx: CompanyContext, fy_id: uuid.UUID) -> FiscalYear:
    fy = db.get(FiscalYear, fy_id)
    if fy is None or fy.company_id != ctx.company_id:
        raise NotFound("Exercice introuvable")
    return fy


@router.get("", response_model=list[FiscalYearOut])
def list_fiscal_years(ctx: CompanyContext = Depends(get_company_context), db: Session = Depends(get_db)):
    return db.scalars(select(FiscalYear).where(FiscalYear.company_id == ctx.company_id)
                      .order_by(FiscalYear.start_date.desc())).all()


@router.post("", response_model=FiscalYearOut, status_code=status.HTTP_201_CREATED)
def create_fiscal_year(payload: FiscalYearCreate, ctx: CompanyContext = Depends(get_company_context),
                       db: Session = Depends(get_db)):
    ctx.require(Permission.FISCAL_YEAR_WRITE)
    fy = FiscalYear(organization_id=ctx.organization_id, company_id=ctx.company_id,
                    label=payload.label.strip(), start_date=payload.start_date, end_date=payload.end_date,
                    created_by=ctx.user.id)
    db.add(fy)
    db.flush()  # contrainte d'exclusion : chevauchement -> 409 « overlap »
    db.refresh(fy)
    return fy


class CloseRequest(BaseModel):
    confirm_label: str = Field(description="Libellé exact de l'exercice, pour confirmation")


@router.post("/{fy_id}/close", response_model=FiscalYearOut,
             summary="Clôturer l'exercice (balances et états deviennent non modifiables)")
def close_fiscal_year(fy_id: uuid.UUID, body: CloseRequest, request: Request,
                      ctx: CompanyContext = Depends(get_company_context), db: Session = Depends(get_db)):
    ctx.require(Permission.FISCAL_YEAR_CLOSE)
    fy = _get(db, ctx, fy_id)
    if fy.status != "open":
        raise Conflict("L'exercice n'est pas ouvert")
    if body.confirm_label != fy.label:
        raise Conflict("Confirmation incorrecte : saisissez le libellé exact de l'exercice")
    fy.status, fy.closed_at, fy.closed_by = "closed", datetime.now(UTC), ctx.user.id
    db.flush()
    record_event(db, user_id=ctx.user.id, action="fiscal_year.closed", entity_type="fiscal_years",
                 entity_id=fy.id, organization_id=ctx.organization_id, company_id=ctx.company_id,
                 request=request)
    return fy


class ReopenRequest(BaseModel):
    reason: str = Field(min_length=10, max_length=1000, description="Motif de réouverture (journalisé)")


@router.post("/{fy_id}/reopen", response_model=FiscalYearOut,
             summary="Rouvrir un exercice clôturé (owner/admin, motif obligatoire)")
def reopen_fiscal_year(fy_id: uuid.UUID, body: ReopenRequest, request: Request,
                       ctx: CompanyContext = Depends(get_company_context), db: Session = Depends(get_db)):
    if ctx.role != CompanyRole.ORG_ADMIN:
        raise Forbidden("Seuls les propriétaires et administrateurs peuvent rouvrir un exercice")
    fy = _get(db, ctx, fy_id)
    if fy.status != "closed":
        raise Conflict("Seul un exercice clôturé peut être rouvert")
    fy.status, fy.closed_at, fy.closed_by = "open", None, None
    db.flush()
    record_event(db, user_id=ctx.user.id, action="fiscal_year.reopened", entity_type="fiscal_years",
                 entity_id=fy.id, organization_id=ctx.organization_id, company_id=ctx.company_id,
                 details={"reason": body.reason}, request=request)
    return fy


@router.delete("/{fy_id}", status_code=status.HTTP_204_NO_CONTENT,
               summary="Supprimer un exercice ouvert et ses données")
def delete_fiscal_year(fy_id: uuid.UUID, ctx: CompanyContext = Depends(get_company_context),
                       db: Session = Depends(get_db)):
    if ctx.role != CompanyRole.ORG_ADMIN:
        raise Forbidden("Seuls les propriétaires et administrateurs peuvent supprimer un exercice")
    fy = _get(db, ctx, fy_id)
    if fy.status != "open":
        raise Conflict("Un exercice clôturé ne peut pas être supprimé")
    db.delete(fy)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
