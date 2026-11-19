"""Importation des balances : dépôt, analyse, association des colonnes, contrôles, validation."""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import CompanyContext, get_company_context, get_db
from app.core.config import get_settings
from app.core.errors import NotFound
from app.core.permissions import Permission
from app.db.session import commit_preserving_rls
from app.models import Company, FinancialDocument, FiscalYear, ImportJob, ImportMapping, ImportStagingRow
from app.services import imports as svc
from app.services.audit import record_event
from app.services.storage import DOCUMENTS_BUCKET, get_storage

router = APIRouter(prefix="/companies/{company_id}", tags=["Importation des balances"])


def _job(db: Session, ctx: CompanyContext, job_id: uuid.UUID) -> ImportJob:
    job = db.get(ImportJob, job_id)
    if job is None or job.company_id != ctx.company_id or job.kind != "trial_balance":
        raise NotFound("Import introuvable")
    return job


def _dispatch(db: Session, step: Literal["analyze", "process"], job: ImportJob) -> None:
    if get_settings().import_processing == "inline":
        (svc.analyze_import if step == "analyze" else svc.process_import)(db, job.id)
        return
    from app.workers.import_tasks import analyze_import_task, process_import_task

    commit_preserving_rls(db)   # le worker doit voir le job
    task = (analyze_import_task if step == "analyze" else process_import_task).delay(str(job.id))
    job.celery_task_id = task.id
    db.flush()


async def _read_limited(upload: UploadFile) -> bytes:
    limit = get_settings().max_upload_size_mb * 1024 * 1024
    data = await upload.read(limit + 1)
    if len(data) > limit:
        raise svc.ImportRejected(f"Fichier trop volumineux (maximum {get_settings().max_upload_size_mb} Mo).")
    return data


@router.post("/imports", status_code=status.HTTP_202_ACCEPTED,
             summary="Déposer une balance (Excel, CSV ou PDF) pour un exercice")
async def create_import(request: Request, file: UploadFile = File(...), fiscal_year_id: uuid.UUID = Form(...),
                        ctx: CompanyContext = Depends(get_company_context), db: Session = Depends(get_db)):
    ctx.require(Permission.IMPORT_WRITE)
    data = await _read_limited(file)
    company = db.get(Company, ctx.company_id)
    job = svc.create_import(db, company=company, fiscal_year_id=fiscal_year_id, filename=file.filename or "fichier",
                            data=data, user_id=ctx.user.id)
    record_event(db, user_id=ctx.user.id, action="document.uploaded", entity_type="financial_documents",
                 entity_id=job.document_id, organization_id=ctx.organization_id, company_id=ctx.company_id,
                 details={"filename": file.filename, "size_bytes": len(data), "import_job_id": str(job.id)},
                 request=request)
    _dispatch(db, "analyze", job)
    db.refresh(job)
    return svc.job_summary(job)


@router.get("/imports", summary="Historique des importations")
def list_imports(fiscal_year_id: uuid.UUID | None = None, ctx: CompanyContext = Depends(get_company_context),
                 db: Session = Depends(get_db)):
    stmt = select(ImportJob).where(ImportJob.company_id == ctx.company_id, ImportJob.kind == "trial_balance")
    if fiscal_year_id:
        stmt = stmt.where(ImportJob.fiscal_year_id == fiscal_year_id)
    jobs = db.scalars(stmt.order_by(ImportJob.created_at.desc()).limit(200)).all()
    labels = dict(db.execute(select(FiscalYear.id, FiscalYear.label)
                             .where(FiscalYear.company_id == ctx.company_id)).all())
    return [{"id": j.id, "status": j.status, "source_format": j.source_format,
             "filename": (j.extraction or {}).get("filename"), "method": (j.extraction or {}).get("method"),
             "fiscal_year_id": j.fiscal_year_id, "fiscal_year_label": labels.get(j.fiscal_year_id),
             "valid_rows": j.valid_rows, "error_rows": j.error_rows,
             "blocking": (j.controls or {}).get("blocking"), "created_at": j.created_at,
             "validated_at": j.validated_at} for j in jobs]


@router.get("/imports/{job_id}")
def get_import(job_id: uuid.UUID, ctx: CompanyContext = Depends(get_company_context), db: Session = Depends(get_db)):
    return svc.job_summary(_job(db, ctx, job_id))


class ConfigureRequest(BaseModel):
    sheet_name: str
    header_row: int = Field(ge=0, description="Index (0 = première ligne) de la ligne d'en-tête")
    column_map: dict[str, int]
    options: dict = Field(default_factory=dict)


@router.post("/imports/{job_id}/configure", status_code=status.HTTP_202_ACCEPTED,
             summary="Choisir la feuille, la ligne d'en-tête et l'association des colonnes, puis contrôler")
def configure_import(job_id: uuid.UUID, body: ConfigureRequest, ctx: CompanyContext = Depends(get_company_context),
                     db: Session = Depends(get_db)):
    ctx.require(Permission.IMPORT_WRITE)
    job = svc.configure_import(db, _job(db, ctx, job_id), sheet_name=body.sheet_name, header_row=body.header_row,
                               column_map=body.column_map, options=body.options)
    _dispatch(db, "process", job)
    db.refresh(job)
    return svc.job_summary(job)


@router.get("/imports/{job_id}/rows", summary="Lignes lues (avec anomalies), pour revue avant validation")
def import_rows(job_id: uuid.UUID, status_filter: Literal["valid", "error", "skipped", "total", "issues"] | None = None,
                limit: int = 100, offset: int = 0, ctx: CompanyContext = Depends(get_company_context),
                db: Session = Depends(get_db)):
    _job(db, ctx, job_id)
    limit = max(1, min(limit, 500))
    stmt = select(ImportStagingRow).where(ImportStagingRow.import_job_id == job_id)
    if status_filter == "issues":
        stmt = stmt.where(func.jsonb_array_length(ImportStagingRow.issues) > 0)
    elif status_filter:
        stmt = stmt.where(ImportStagingRow.status == status_filter)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(ImportStagingRow.source_row).limit(limit).offset(max(offset, 0))).all()
    amounts = ("opening_debit", "opening_credit", "movement_debit", "movement_credit", "closing_debit",
               "closing_credit")
    return {"total": total, "items": [
        {"source_row": r.source_row, "source_page": r.source_page, "status": r.status,
         "account_number": r.account_number, "account_label": r.account_label,
         **{a: (str(getattr(r, a)) if getattr(r, a) is not None else None) for a in amounts},
         "closing_computed": r.closing_computed,
         "ocr_confidence": str(r.ocr_confidence) if r.ocr_confidence is not None else None,
         "issues": r.issues, "raw": r.raw} for r in rows]}


class ConfirmRequest(BaseModel):
    acknowledge_warnings: bool = False
    save_mapping_as: str | None = Field(default=None, max_length=120)


@router.post("/imports/{job_id}/confirm", summary="Valider l'import : la balance devient la balance de l'exercice")
def confirm_import(job_id: uuid.UUID, body: ConfirmRequest, request: Request,
                   ctx: CompanyContext = Depends(get_company_context), db: Session = Depends(get_db)):
    ctx.require(Permission.IMPORT_WRITE)
    job = svc.confirm_import(db, _job(db, ctx, job_id), user_id=ctx.user.id,
                             acknowledge_warnings=body.acknowledge_warnings, save_mapping_as=body.save_mapping_as)
    record_event(db, user_id=ctx.user.id, action="import.validated", entity_type="import_jobs", entity_id=job.id,
                 organization_id=ctx.organization_id, company_id=ctx.company_id,
                 details={"valid_rows": job.valid_rows, "warnings_acknowledged": job.warnings_acknowledged,
                          "totals": job.control_totals}, request=request)
    return svc.job_summary(job)


@router.post("/imports/{job_id}/cancel")
def cancel_import(job_id: uuid.UUID, ctx: CompanyContext = Depends(get_company_context),
                  db: Session = Depends(get_db)):
    ctx.require(Permission.IMPORT_WRITE)
    return svc.job_summary(svc.cancel_import(db, _job(db, ctx, job_id)))


@router.get("/documents/{document_id}/download", summary="Lien de téléchargement temporaire du document original")
def download_document(document_id: uuid.UUID, request: Request, ctx: CompanyContext = Depends(get_company_context),
                      db: Session = Depends(get_db)):
    doc = db.get(FinancialDocument, document_id)
    if doc is None or doc.company_id != ctx.company_id or doc.deleted_at is not None:
        raise NotFound("Document introuvable")
    url = get_storage().signed_url(DOCUMENTS_BUCKET, doc.storage_path, download_name=doc.original_filename)
    record_event(db, user_id=ctx.user.id, action="document.downloaded", entity_type="financial_documents",
                 entity_id=doc.id, organization_id=ctx.organization_id, company_id=ctx.company_id, request=request)
    return {"url": url, "expires_in": 300, "filename": doc.original_filename, "sha256": doc.sha256}


@router.get("/import-mappings", summary="Modèles d'association de colonnes enregistrés")
def list_mappings(ctx: CompanyContext = Depends(get_company_context), db: Session = Depends(get_db)):
    rows = db.scalars(select(ImportMapping).where(ImportMapping.company_id == ctx.company_id)
                      .order_by(ImportMapping.created_at.desc())).all()
    return [{"id": m.id, "name": m.name, "source_format": m.source_format, "column_map": m.column_map,
             "options": m.options, "is_default": m.is_default, "kind": m.kind, "created_at": m.created_at} for m in rows]


@router.delete("/import-mappings/{mapping_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_mapping(mapping_id: uuid.UUID, ctx: CompanyContext = Depends(get_company_context),
                   db: Session = Depends(get_db)):
    ctx.require(Permission.IMPORT_WRITE)
    m = db.get(ImportMapping, mapping_id)
    if m is None or m.company_id != ctx.company_id:
        raise NotFound("Modèle introuvable")
    db.delete(m)


@router.get("/fiscal-years/{fiscal_year_id}/trial-balance", tags=["Balances"],
            summary="Balance validée de l'exercice (import actif)")
def get_trial_balance(fiscal_year_id: uuid.UUID, account_class: str | None = None, q: str | None = None,
                      limit: int = 200, offset: int = 0, ctx: CompanyContext = Depends(get_company_context),
                      db: Session = Depends(get_db)):
    fy = db.get(FiscalYear, fiscal_year_id)
    if fy is None or fy.company_id != ctx.company_id:
        raise NotFound("Exercice introuvable")
    if account_class is not None and not (len(account_class) == 1 and account_class.isdigit()):
        raise svc.ImportRejected("Classe de compte invalide (un chiffre attendu).")
    return svc.trial_balance(db, fy, account_class=account_class, q=q, limit=max(1, min(limit, 1000)),
                             offset=max(offset, 0))
