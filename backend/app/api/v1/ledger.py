"""API — grand livre (complément du lot 3) : import (dépôt, association des colonnes, contrôles, validation) et
exploitation (consultation avec solde progressif, écriture, comptes rapprochés de la balance, centralisation par
journal, analyses de données, export). Les missions d'audit consultent le grand livre de l'exercice audité."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, Query, Request, Response, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import CompanyContext, get_company_context, get_db
from app.core.config import get_settings
from app.core.errors import NotFound
from app.core.permissions import Permission
from app.db.session import commit_preserving_rls
from app.models import Company, FiscalYear, ImportJob, LedgerLine
from app.services import ledger as svc
from app.services.audit import record_event
from app.services.engagements import AuditInvalid, EngagementContext, get_engagement_context

router = APIRouter(tags=["Grand livre"])
Db = Annotated[Session, Depends(get_db)]
Comp = Annotated[CompanyContext, Depends(get_company_context)]
Eng = Annotated[EngagementContext, Depends(get_engagement_context)]
C = "/companies/{company_id}"


def _dispatch(db: Session, step: Literal["analyze", "process"], job: ImportJob) -> None:
    if get_settings().import_processing == "inline":
        (svc.analyze_ledger if step == "analyze" else svc.process_ledger)(db, job.id)
        return
    from app.workers.import_tasks import analyze_ledger_task, process_ledger_task

    commit_preserving_rls(db)
    task = (analyze_ledger_task if step == "analyze" else process_ledger_task).delay(str(job.id))
    job.celery_task_id = task.id
    db.flush()


def _log(db, request, ctx: CompanyContext, action: str, entity_id, details: dict | None = None):
    record_event(
        db,
        user_id=ctx.user.id,
        action=action,
        entity_type="import_jobs",
        entity_id=entity_id,
        organization_id=ctx.organization_id,
        company_id=ctx.company_id,
        details=details or {},
        request=request,
    )


# ======================================================================== import
@router.post(
    C + "/ledger-imports",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Déposer un grand livre (Excel ou CSV, dont le fichier des écritures comptables)",
)
async def create_ledger_import(
    request: Request, ctx: Comp, db: Db, file: UploadFile = File(...), fiscal_year_id: uuid.UUID = Form(...)
):
    ctx.require(Permission.IMPORT_WRITE)
    limit = get_settings().max_upload_size_mb * 1024 * 1024
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise svc.ImportRejected(f"Fichier trop volumineux (maximum {get_settings().max_upload_size_mb} Mo).")
    job = svc.create_ledger_import(
        db,
        company=db.get(Company, ctx.company_id),
        fiscal_year_id=fiscal_year_id,
        filename=file.filename or "grand-livre",
        data=data,
        user_id=ctx.user.id,
    )
    _log(db, request, ctx, "ledger_import.uploaded", job.id, {"filename": file.filename, "size_bytes": len(data)})
    _dispatch(db, "analyze", job)
    db.refresh(job)
    return svc.job_summary(job)


@router.get(C + "/ledger-imports", summary="Historique des imports de grand livre")
def list_ledger_imports(ctx: Comp, db: Db, fiscal_year_id: uuid.UUID | None = None):
    q = select(ImportJob).where(ImportJob.company_id == ctx.company_id, ImportJob.kind == "ledger")
    if fiscal_year_id:
        q = q.where(ImportJob.fiscal_year_id == fiscal_year_id)
    labels = dict(db.execute(select(FiscalYear.id, FiscalYear.label).where(FiscalYear.company_id == ctx.company_id)).all())
    active = {
        fy.active_ledger_import_job_id for fy in db.scalars(select(FiscalYear).where(FiscalYear.company_id == ctx.company_id))
    }
    return [
        {
            "id": j.id,
            "status": j.status,
            "source_format": j.source_format,
            "filename": (j.extraction or {}).get("filename"),
            "fiscal_year_id": j.fiscal_year_id,
            "fiscal_year_label": labels.get(j.fiscal_year_id),
            "valid_rows": j.valid_rows,
            "error_rows": j.error_rows,
            "blocking": (j.controls or {}).get("blocking"),
            "active": j.id in active,
            "created_at": j.created_at,
            "validated_at": j.validated_at,
        }
        for j in db.scalars(q.order_by(ImportJob.created_at.desc()).limit(200))
    ]


@router.get(C + "/ledger-imports/{job_id}")
def get_ledger_import(job_id: uuid.UUID, ctx: Comp, db: Db):
    return svc.job_summary(svc.get_job(db, ctx.company_id, job_id))


class ConfigureIn(BaseModel):
    sheet_name: str = Field(min_length=1, max_length=200)
    header_row: int = Field(ge=0)
    column_map: dict[str, int]
    options: dict = Field(default_factory=dict)


@router.post(
    C + "/ledger-imports/{job_id}/configure",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Associer les colonnes et lancer la lecture et les contrôles",
)
def configure_ledger_import(job_id: uuid.UUID, body: ConfigureIn, request: Request, ctx: Comp, db: Db):
    ctx.require(Permission.IMPORT_WRITE)
    job = svc.configure_ledger(
        db,
        svc.get_job(db, ctx.company_id, job_id),
        sheet_name=body.sheet_name,
        header_row=body.header_row,
        column_map=body.column_map,
        options=body.options,
    )
    _log(db, request, ctx, "ledger_import.configured", job.id, {"column_map": body.column_map, "options": job.options})
    _dispatch(db, "process", job)
    db.refresh(job)
    return svc.job_summary(job)


@router.get(C + "/ledger-imports/{job_id}/lines", summary="Lignes lues (avec anomalies), pour revue avant validation")
def ledger_import_lines(
    job_id: uuid.UUID,
    ctx: Comp,
    db: Db,
    status_filter: Literal["valid", "error", "skipped"] | None = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    svc.get_job(db, ctx.company_id, job_id)
    q = select(LedgerLine).where(LedgerLine.import_job_id == job_id)
    if status_filter:
        q = q.where(LedgerLine.status == status_filter)
    total = db.scalar(select(func.count()).select_from(q.subquery()))
    rows = db.scalars(q.order_by(LedgerLine.source_row).limit(limit).offset(offset))
    return {
        "total": total,
        "items": [
            {
                "source_row": r.source_row,
                "status": r.status,
                "issues": r.issues,
                **{f: svc._jsonable(getattr(r, f)) for f in svc.LINE_FIELDS},
            }
            for r in rows
        ],
    }


class ConfirmIn(BaseModel):
    acknowledge_warnings: bool = False
    save_mapping_as: str | None = Field(default=None, max_length=120)


@router.post(C + "/ledger-imports/{job_id}/confirm", summary="Valider : le grand livre devient celui de l'exercice")
def confirm_ledger_import(job_id: uuid.UUID, body: ConfirmIn, request: Request, ctx: Comp, db: Db):
    ctx.require(Permission.IMPORT_WRITE)
    job = svc.confirm_ledger(
        db,
        svc.get_job(db, ctx.company_id, job_id),
        user_id=ctx.user.id,
        acknowledge_warnings=body.acknowledge_warnings,
        save_mapping_as=body.save_mapping_as,
    )
    _log(
        db,
        request,
        ctx,
        "ledger_import.validated",
        job.id,
        {"valid_rows": job.valid_rows, "warnings_acknowledged": job.warnings_acknowledged},
    )
    return svc.job_summary(job)


@router.post(C + "/ledger-imports/{job_id}/cancel")
def cancel_ledger_import(job_id: uuid.UUID, request: Request, ctx: Comp, db: Db):
    ctx.require(Permission.IMPORT_WRITE)
    job = svc.cancel_ledger(db, svc.get_job(db, ctx.company_id, job_id))
    _log(db, request, ctx, "ledger_import.cancelled", job.id)
    return svc.job_summary(job)


# ======================================================================== exploitation
def _fy(db: Session, company_id: uuid.UUID, fy_id: uuid.UUID) -> FiscalYear:
    fy = db.get(FiscalYear, fy_id)
    if fy is None or fy.company_id != company_id:
        raise NotFound("Exercice introuvable")
    return fy


class Filters:
    def __init__(
        self,
        account: str | None = None,
        account_prefix: str | None = Query(None, pattern=r"^[0-9]{1,20}$"),
        journal: str | None = None,
        auxiliary: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        q: str | None = Query(None, max_length=100),
        min_amount: Decimal | None = None,
        max_amount: Decimal | None = None,
        lettered: bool | None = None,
    ):
        self.f = svc.LedgerFilters(
            account=account,
            account_prefix=account_prefix,
            journal=journal,
            date_from=date_from,
            date_to=date_to,
            q=q,
            min_amount=min_amount,
            max_amount=max_amount,
            lettered=lettered,
            auxiliary=auxiliary,
        )


F = Annotated[Filters, Depends()]
FY = C + "/fiscal-years/{fiscal_year_id}/ledger"


@router.get(FY, summary="Grand livre de l'exercice : lignes filtrées (solde progressif pour un compte)")
def ledger_lines(
    fiscal_year_id: uuid.UUID, ctx: Comp, db: Db, filters: F, limit: int = Query(200, ge=1, le=2000), offset: int = Query(0, ge=0)
):
    return svc.lines(db, _fy(db, ctx.company_id, fiscal_year_id), filters.f, limit, offset)


@router.get(FY + ".csv", summary="Export CSV des lignes filtrées")
def ledger_csv(fiscal_year_id: uuid.UUID, request: Request, ctx: Comp, db: Db, filters: F):
    fy = _fy(db, ctx.company_id, fiscal_year_id)
    data = svc.export_csv(db, fy, filters.f)
    record_event(
        db,
        user_id=ctx.user.id,
        action="ledger.exported",
        entity_type="fiscal_years",
        entity_id=fy.id,
        organization_id=ctx.organization_id,
        company_id=ctx.company_id,
        details={},
        request=request,
    )
    return Response(
        content=data, media_type="text/csv", headers={"Content-Disposition": f"attachment; filename=grand-livre-{fy.label}.csv"}
    )


@router.get(FY + "/entry", summary="Lignes d'une écriture")
def ledger_entry(fiscal_year_id: uuid.UUID, ctx: Comp, db: Db, number: str, journal: str | None = None):
    return svc.entry(db, _fy(db, ctx.company_id, fiscal_year_id), journal, number)


@router.get(FY + "/accounts", summary="Totaux par compte, rapprochés de la balance validée")
def ledger_accounts(fiscal_year_id: uuid.UUID, ctx: Comp, db: Db, prefix: str | None = Query(None, pattern=r"^[0-9]{1,20}$")):
    return svc.accounts(db, _fy(db, ctx.company_id, fiscal_year_id), prefix)


@router.get(FY + "/journals", summary="Centralisation par journal et par mois")
def ledger_journals(fiscal_year_id: uuid.UUID, ctx: Comp, db: Db):
    return svc.journals(db, _fy(db, ctx.company_id, fiscal_year_id))


@router.get(FY + "/analytics", summary="Analyses de données sur les écritures (à examiner, sans conclusion)")
def ledger_analytics(
    fiscal_year_id: uuid.UUID,
    ctx: Comp,
    db: Db,
    round_multiple: Decimal | None = Query(None, gt=0),
    benford_min: Decimal = Query(Decimal("0"), ge=0),
):
    return svc.analytics(db, _fy(db, ctx.company_id, fiscal_year_id), round_multiple=round_multiple, benford_min=benford_min)


# ======================================================================== consultation par une mission d'audit
def _engagement_fy(db: Session, ctx: EngagementContext) -> FiscalYear:
    ctx.require("read_dossier")
    if not ctx.engagement.fiscal_year_id:
        raise AuditInvalid("La mission n'est rattachée à aucun exercice.")
    return db.get(FiscalYear, ctx.engagement.fiscal_year_id)


E = "/engagements/{engagement_id}/ledger"


@router.get(E, summary="Grand livre de l'exercice audité (équipe de mission)")
def engagement_ledger(ctx: Eng, db: Db, filters: F, limit: int = Query(200, ge=1, le=2000), offset: int = Query(0, ge=0)):
    return svc.lines(db, _engagement_fy(db, ctx), filters.f, limit, offset)


@router.get(E + "/entry")
def engagement_entry(ctx: Eng, db: Db, number: str, journal: str | None = None):
    return svc.entry(db, _engagement_fy(db, ctx), journal, number)


@router.get(E + "/accounts")
def engagement_accounts(ctx: Eng, db: Db, prefix: str | None = Query(None, pattern=r"^[0-9]{1,20}$")):
    return svc.accounts(db, _engagement_fy(db, ctx), prefix)


@router.get(E + "/journals")
def engagement_journals(ctx: Eng, db: Db):
    return svc.journals(db, _engagement_fy(db, ctx))


@router.get(E + "/analytics")
def engagement_analytics(
    ctx: Eng, db: Db, round_multiple: Decimal | None = Query(None, gt=0), benford_min: Decimal = Query(Decimal("0"), ge=0)
):
    return svc.analytics(db, _engagement_fy(db, ctx), round_multiple=round_multiple, benford_min=benford_min)
