"""API — pilotage du contrôle de gestion : tableaux de bord financier, budgétaire, de trésorerie et de la masse
salariale, analyse, détail jusqu'aux écritures, filigrane des sources et seuils d'alerte.

Lecture seule des sources validées (aucune écriture comptable). Les calculs sont dans `services/steering.py` et
`engines/management/steering.py`."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from app.api.deps import CompanyContext, get_company_context, get_db
from app.core.errors import NotFound
from app.core.permissions import Permission
from app.models import Company, FiscalYear, ManagementAlertSettings
from app.services import steering as svc
from app.services.management import jsonable  # Decimal → texte exact, jamais de flottant
from app.services.audit import record_event

router = APIRouter(prefix="/companies/{company_id}", tags=["Contrôle de gestion — pilotage"])
Db = Annotated[Session, Depends(get_db)]
Comp = Annotated[CompanyContext, Depends(get_company_context)]
F = "/fiscal-years/{fiscal_year_id}/steering"
View = Literal["year", "month", "cumulative", "custom"]
Source = Literal["auto", "native", "imported", "trial_balance"]


def _fy(db: Session, ctx: CompanyContext, fy_id: uuid.UUID) -> tuple[Company, FiscalYear]:
    fy = db.get(FiscalYear, fy_id)
    if fy is None or fy.company_id != ctx.company_id:
        raise NotFound("Exercice introuvable")
    return db.get(Company, ctx.company_id), fy


class Period:
    def __init__(
        self,
        view: View = "year",
        month: int | None = Query(None, ge=1, le=12),
        date_from: date | None = None,
        date_to: date | None = None,
        source: Source = "auto",
    ):
        self.kw = {"view": view, "month": month, "d_from": date_from, "d_to": date_to, "source": source}


P = Annotated[Period, Depends(Period)]


@router.get(F + "/watermark", summary="Filigrane des sources : dernière écriture validée, imports actifs, écritures en attente")
def watermark(fiscal_year_id: uuid.UUID, ctx: Comp, db: Db):
    _, fy = _fy(db, ctx, fiscal_year_id)
    return jsonable(svc.watermark(db, fy))


@router.get(F + "/financial", summary="Tableau de bord financier : soldes AO / HAO, indicateurs, Top 10, évolutions, N / N-1")
def financial(fiscal_year_id: uuid.UUID, ctx: Comp, db: Db, p: P, compare: bool = True,
              partner_basis: Literal["revenue", "invoiced"] = "revenue"):
    """`partner_basis` : clients / fournisseurs par chiffre d'affaires et charges HT des écritures (par défaut), ou par
    montants facturés sur les comptes de tiers (présentation du modèle Excel de référence)."""
    company, fy = _fy(db, ctx, fiscal_year_id)
    return jsonable(svc.financial(db, company, fy, compare=compare, partner_basis=partner_basis, **p.kw))


@router.get(F + "/drilldown", summary="Détail d'un indicateur, d'un compte, d'un tiers ou de la trésorerie jusqu'aux écritures")
def drilldown(
    fiscal_year_id: uuid.UUID,
    ctx: Comp,
    db: Db,
    p: P,
    kind: str,
    key: str | None = None,
    limit: int = Query(200, ge=1, le=2000),
    offset: int = Query(0, ge=0),
):
    company, fy = _fy(db, ctx, fiscal_year_id)
    if kind == "personnel":
        ctx.require(Permission.PAYROLL_DETAIL)
    return jsonable(svc.drilldown(
        db, company, fy, kind=kind, key=key, limit=limit, offset=offset, payroll_detail=ctx.can(Permission.PAYROLL_DETAIL), **p.kw
    ))


@router.get(
    F + "/budget", summary="Tableau de bord budgétaire : budget, réalisé, écarts, prévision à terminaison, alertes, Top 10"
)
def budget(
    fiscal_year_id: uuid.UUID,
    ctx: Comp,
    db: Db,
    budget_id: uuid.UUID | None = None,
    source: Source = "auto",
    as_of: date | None = None,
):
    company, fy = _fy(db, ctx, fiscal_year_id)
    return jsonable(svc.budget_dashboard(
        db, company, fy, budget_id=budget_id, source=source, as_of=as_of, thresholds=svc.thresholds_for(db, company.id)
    ))


@router.get(F + "/treasury", summary="Tableau de bord de trésorerie (flux réels, transferts internes exclus)")
def treasury(fiscal_year_id: uuid.UUID, ctx: Comp, db: Db, p: P):
    company, fy = _fy(db, ctx, fiscal_year_id)
    return jsonable(svc.treasury(db, company, fy, **p.kw))


@router.get(F + "/payroll", summary="Tableau de bord de la masse salariale (montants agrégés par compte)")
def payroll(fiscal_year_id: uuid.UUID, ctx: Comp, db: Db, p: P):
    company, fy = _fy(db, ctx, fiscal_year_id)
    return jsonable(svc.payroll(db, company, fy, **p.kw))


@router.get(F + "/analysis", summary="Analyse et aide à la décision : points d'attention factuels")
def analysis(fiscal_year_id: uuid.UUID, ctx: Comp, db: Db, p: P):
    company, fy = _fy(db, ctx, fiscal_year_id)
    return jsonable(svc.analysis(db, company, fy, **p.kw))


# ------------------------------------------------------------------ seuils d'alerte
FIELDS = (
    "consumption_info_pct",
    "overrun_warning_pct",
    "overrun_critical_pct",
    "pace_gap_points",
    "under_execution_points",
    "center_variance_pct",
    "change_pct",
    "concentration_pct",
)


class ThresholdsIn(BaseModel):
    consumption_info_pct: Decimal = Field(ge=0, le=1000, decimal_places=2)
    overrun_warning_pct: Decimal = Field(ge=0, le=1000, decimal_places=2)
    overrun_critical_pct: Decimal = Field(ge=0, le=1000, decimal_places=2)
    pace_gap_points: Decimal = Field(ge=0, le=100, decimal_places=2)
    under_execution_points: Decimal = Field(ge=0, le=100, decimal_places=2)
    center_variance_pct: Decimal = Field(ge=0, le=1000, decimal_places=2)
    change_pct: Decimal = Field(ge=0, le=1000, decimal_places=2)
    concentration_pct: Decimal = Field(ge=0, le=100, decimal_places=2)

    @model_validator(mode="after")
    def _order(self):
        if not self.consumption_info_pct <= self.overrun_warning_pct <= self.overrun_critical_pct:
            raise ValueError("Seuils de consommation : information ≤ avertissement ≤ critique.")
        return self


@router.get("/management-alert-settings", summary="Seuils d'alerte du contrôle de gestion (valeurs par défaut si non paramétrés)")
def get_thresholds(ctx: Comp, db: Db):
    th = svc.thresholds_for(db, ctx.company_id)
    return jsonable({
        **{k: getattr(th, k) for k in FIELDS},
        "customized": db.get(ManagementAlertSettings, ctx.company_id) is not None,
        "can_edit": ctx.can(Permission.BUDGET_APPROVE),
    })


@router.put("/management-alert-settings", summary="Paramétrer les seuils d'alerte (contrôleurs et administrateurs)")
def put_thresholds(body: ThresholdsIn, request: Request, ctx: Comp, db: Db):
    ctx.require(Permission.BUDGET_APPROVE)
    s = db.get(ManagementAlertSettings, ctx.company_id)
    if s is None:
        s = ManagementAlertSettings(company_id=ctx.company_id, organization_id=ctx.organization_id)
        db.add(s)
    for k in FIELDS:
        setattr(s, k, getattr(body, k))
    db.flush()
    record_event(
        db,
        user_id=ctx.user.id,
        action="management.thresholds",
        entity_type="management_alert_settings",
        entity_id=None,
        organization_id=ctx.organization_id,
        company_id=ctx.company_id,
        details={k: str(getattr(body, k)) for k in FIELDS},
        request=request,
    )
    return get_thresholds(ctx, db)
