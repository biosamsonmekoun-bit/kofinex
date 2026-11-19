"""API — tableau de bord financier d'un exercice (données validées uniquement, sans estimation)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import CompanyContext, get_company_context, get_db
from app.core.errors import NotFound
from app.models import Company, FiscalYear
from app.services import dashboard as svc

router = APIRouter(tags=["tableau de bord"])


@router.get(
    "/companies/{company_id}/fiscal-years/{fiscal_year_id}/dashboard",
    summary="Tableau de bord : indicateurs de l'analyse terminée, produits et charges validés, évolution mensuelle (grand livre)",
)
def dashboard(
    fiscal_year_id: uuid.UUID,
    ctx: Annotated[CompanyContext, Depends(get_company_context)],
    db: Annotated[Session, Depends(get_db)],
    period: str = "year",
):
    fy = db.get(FiscalYear, fiscal_year_id)
    if fy is None or fy.company_id != ctx.company_id:
        raise NotFound("Exercice introuvable")
    return svc.build(db, db.get(Company, ctx.company_id), fy, period)
