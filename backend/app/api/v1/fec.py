"""API — Fichier des Écritures Comptables (FEC) DGI Bénin, rubrique du module Comptabilité.

Toutes les routes exigent la permission `fec.export` (comptables et administrateurs ; la RLS de la migration 0016 applique
la même règle). Générations et téléchargements sont journalisés (`fec.generated`, `fec.downloaded`)."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import CompanyContext, get_company_context, get_db
from app.core.permissions import Permission
from app.engines.accounting import fec_bj
from app.models import Company
from app.services import fec as svc
from app.services.audit import record_event

router = APIRouter(tags=["Comptabilité — FEC Bénin"])
Db = Annotated[Session, Depends(get_db)]
Comp = Annotated[CompanyContext, Depends(get_company_context)]
F = "/companies/{company_id}/accounting/fec"


class FecOptionsIn(BaseModel):
    fiscal_year_id: uuid.UUID
    period_start: date | None = None
    period_end: date | None = None
    file_format: Literal["txt", "csv"]
    encoding: Literal["ascii", "iso-8859-15"]
    record_separator: Literal["crlf", "lf", "cr"]
    field_separator: Literal["tab"] = "tab"
    accounting_type: Literal["accrual", "cash"] = "accrual"
    max_lines_per_file: int | None = Field(default=None, ge=1)


class FecGenerateIn(FecOptionsIn):
    kind: Literal["final", "working"]


def _company(db: Session, ctx: CompanyContext) -> Company:
    ctx.require(Permission.FEC_EXPORT)
    return db.get(Company, ctx.company_id)


def _log(db: Session, request: Request, ctx: CompanyContext, action: str, entity_id, details: dict) -> None:
    record_event(
        db,
        user_id=ctx.user.id,
        action=action,
        entity_type="fec_export",
        entity_id=entity_id,
        organization_id=ctx.organization_id,
        company_id=ctx.company_id,
        details=details,
        request=request,
    )


def _attachment(data: bytes, filename: str, mime: str) -> Response:
    return Response(content=data, media_type=mime, headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get(F + "/spec", summary="Champs, formats et points réglementaires du FEC béninois")
def get_spec(ctx: Comp, db: Db):
    _company(db, ctx)
    return fec_bj.spec()


@router.get(F + "/dashboard", summary="Tableau de bord FEC de l'exercice")
def get_dashboard(ctx: Comp, db: Db, fiscal_year_id: uuid.UUID):
    return svc.dashboard(db, _company(db, ctx), fiscal_year_id)


@router.post(F + "/check", summary="Contrôle de conformité préalable (aucun fichier produit)")
def post_check(body: FecOptionsIn, ctx: Comp, db: Db):
    company = _company(db, ctx)
    return svc.run_check(
        db,
        company,
        body.fiscal_year_id,
        body.period_start,
        body.period_end,
        body.model_dump(exclude={"fiscal_year_id", "period_start", "period_end"}),
    )


@router.post(F + "/exports", status_code=status.HTTP_201_CREATED, summary="Générer le FEC (nouvelle version, archivée)")
def post_export(body: FecGenerateIn, request: Request, ctx: Comp, db: Db):
    company = _company(db, ctx)
    ex = svc.generate(
        db,
        company,
        ctx.user.id,
        body.fiscal_year_id,
        body.period_start,
        body.period_end,
        body.model_dump(exclude={"fiscal_year_id", "period_start", "period_end", "kind"}),
        body.kind,
    )
    _log(
        db,
        request,
        ctx,
        "fec.generated",
        ex.id,
        {
            "version": ex.version_no,
            "kind": ex.kind,
            "filename": ex.filename,
            "lines": ex.line_count,
            "compliance": ex.compliance,
            "sha256": ex.sha256,
        },
    )
    return svc.export_summary(ex)


@router.get(F + "/exports", summary="Historique des générations")
def get_exports(ctx: Comp, db: Db, fiscal_year_id: uuid.UUID | None = None):
    _company(db, ctx)
    return svc.exports(db, ctx.company_id, fiscal_year_id)


@router.get(F + "/exports/{export_id}", summary="Détail d'une génération (avec le rapport d'anomalies)")
def get_export(export_id: uuid.UUID, ctx: Comp, db: Db):
    _company(db, ctx)
    ex = svc.get_export(db, ctx.company_id, export_id)
    return {**svc.export_summary(ex), "anomalies": ex.anomalies, "source_state": ex.source_state}


@router.get(F + "/exports/{export_id}/file", summary="Télécharger le fichier FEC (ou une partie s'il est scindé)")
def get_file(export_id: uuid.UUID, request: Request, ctx: Comp, db: Db, part: Annotated[int | None, Query(ge=1)] = None):
    _company(db, ctx)
    ex = svc.get_export(db, ctx.company_id, export_id)
    name, data, mime = svc.file_part(ex, part)
    _log(db, request, ctx, "fec.downloaded", ex.id, {"file": name, "version": ex.version_no})
    return _attachment(data, name, mime)


@router.get(F + "/exports/{export_id}/documentation", summary="Télécharger la documentation du fichier (art. 7)")
def get_documentation(export_id: uuid.UUID, request: Request, ctx: Comp, db: Db):
    _company(db, ctx)
    ex = svc.get_export(db, ctx.company_id, export_id)
    name, data = svc.documentation_file(ex)
    _log(db, request, ctx, "fec.downloaded", ex.id, {"file": name, "version": ex.version_no})
    return _attachment(data, name, "text/plain; charset=utf-8")


@router.get(F + "/exports/{export_id}/anomalies.csv", summary="Rapport des anomalies (CSV)")
def get_anomalies_csv(export_id: uuid.UUID, ctx: Comp, db: Db):
    _company(db, ctx)
    ex = svc.get_export(db, ctx.company_id, export_id)
    return _attachment(
        fec_bj.anomalies_csv(ex.anomalies),
        f"anomalies_{ex.filename.rsplit('.', 1)[0]}_v{ex.version_no}.csv",
        "text/csv; charset=utf-8",
    )


@router.get(F + "/exports/{export_id}/trace", summary="Écriture source d'une ligne du fichier")
def get_trace(export_id: uuid.UUID, ctx: Comp, db: Db, row: Annotated[int, Query(ge=1)]):
    _company(db, ctx)
    return svc.trace(db, svc.get_export(db, ctx.company_id, export_id), row)
