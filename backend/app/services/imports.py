"""Orchestration des importations de balances.

Cycle d'un import :
  pending -> parsing -> awaiting_mapping -> validating -> awaiting_confirmation -> completed
                     \\-> failed                                 \\-> (nouvelle configuration)
Un import validé remplace l'import actif précédent de l'exercice (statut « superseded »,
ses lignes restent consultables pour la traçabilité).

Les fonctions reçoivent une ``Session`` : session RLS de l'utilisateur (mode inline) ou
session de service (worker Celery, qui ne traite que l'identifiant de job reçu).
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import asdict
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import delete, func, insert, select, text, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError, Conflict, NotFound
from app.engines.importing import readers
from app.engines.importing.balance import ImportOptions, MappingError, build_balance, validate_column_map
from app.engines.importing.controls import ChartContext, run_controls
from app.engines.importing.detection import FIELD_LABELS, detect_header_row, header_score, suggest_mapping
from app.engines.importing.files import FileRejected, validate_upload
from app.models import (
    AccountingFramework,
    ChartAccount,
    Company,
    FinancialDocument,
    FiscalYear,
    FrameworkVersion,
    ImportJob,
    ImportMapping,
    ImportStagingRow,
    TrialBalanceEntry,
)
from app.services.storage import DOCUMENTS_BUCKET, get_storage

logger = logging.getLogger(__name__)

PREVIEW_ROWS = 40
ACTIVE_STATUSES = ("pending", "parsing", "awaiting_mapping", "validating", "awaiting_confirmation")


class ImportRejected(AppError):
    status_code = 422
    code = "import_error"


# ------------------------------------------------------------------------------ création
def create_import(db: Session, *, company: Company, fiscal_year_id: uuid.UUID, filename: str, data: bytes,
                  user_id: uuid.UUID, kind: str = "trial_balance", allowed_formats: tuple[str, ...] | None = None) -> ImportJob:
    s = get_settings()
    fy = db.get(FiscalYear, fiscal_year_id)
    if fy is None or fy.company_id != company.id:
        raise NotFound("Exercice introuvable")
    if fy.status != "open":
        raise Conflict("L'exercice est clôturé : aucun import n'est possible.")

    try:
        vf = validate_upload(filename, data, max_bytes=s.max_upload_size_mb * 1024 * 1024,
                             allowed_extensions=s.allowed_upload_extensions)
    except FileRejected as exc:
        raise ImportRejected(str(exc)) from exc
    if allowed_formats and vf.format not in allowed_formats:
        raise ImportRejected(f"Format non accepté pour cet import : {', '.join(allowed_formats)}.")

    duplicate_of = db.execute(text("SELECT public.find_duplicate_document(:c, :h)"),
                              {"c": company.id, "h": vf.sha256}).scalar()

    doc_id = uuid.uuid4()
    path = f"{company.organization_id}/{company.id}/{doc_id}.{vf.extension}"
    get_storage().upload(DOCUMENTS_BUCKET, path, data, vf.mime_type)

    safe_name = filename.replace("/", "_").replace("\\", "_")[:255]
    db.add(FinancialDocument(id=doc_id, organization_id=company.organization_id, company_id=company.id,
                             fiscal_year_id=fy.id, document_type="general_ledger" if kind == "ledger" else "trial_balance",
                             original_filename=safe_name,
                             storage_path=path, mime_type=vf.mime_type, size_bytes=vf.size_bytes, sha256=vf.sha256,
                             uploaded_by=user_id))
    db.flush()

    version_id = db.execute(text("SELECT public.applicable_framework_version(:c, :d)"),
                            {"c": company.id, "d": fy.end_date}).scalar()
    job = ImportJob(id=uuid.uuid4(), organization_id=company.organization_id, company_id=company.id,
                    fiscal_year_id=fy.id, document_id=doc_id, source_format=vf.format, status="pending", kind=kind,
                    started_by=user_id, framework_version_id=version_id,
                    extraction={"duplicate_of_document": str(duplicate_of) if duplicate_of else None,
                                "filename": safe_name, "sha256": vf.sha256, "size_bytes": vf.size_bytes})
    db.add(job)
    db.flush()
    return job


def _load_file(db: Session, job: ImportJob) -> tuple[FinancialDocument, bytes]:
    doc = db.get(FinancialDocument, job.document_id)
    if doc is None:
        raise NotFound("Document source introuvable")
    return doc, get_storage().download(DOCUMENTS_BUCKET, doc.storage_path)


def _extract(db: Session, job: ImportJob) -> readers.Extraction:
    """Relit le fichier. Pour un PDF, la lecture (OCR coûteux) est mise en cache dans le job."""
    cache = (job.extraction or {}).get("pdf_cache")
    if job.source_format == "pdf" and cache:
        sheet = readers.Sheet(name="PDF", rows=cache["rows"], source=cache["source"],
                              confidence=cache.get("confidence"), row_pages=cache.get("pages"),
                              warnings=cache.get("warnings", []))
        return readers.Extraction([sheet], cache["method"], cache.get("page_count"), cache.get("ocr_pages", []))
    _, data = _load_file(db, job)
    return readers.extract(job.source_format, data, ocr_lang=get_settings().ocr_language)


# ------------------------------------------------------------------------------ analyse
def analyze_import(db: Session, job_id: uuid.UUID) -> ImportJob:
    job = db.get(ImportJob, job_id)
    if job is None:
        raise NotFound("Import introuvable")
    if job.status not in ("pending", "parsing", "failed"):
        return job
    job.status = "parsing"
    db.flush()
    try:
        ext = _extract(db, job)
    except FileRejected as exc:
        return _fail(db, job, str(exc))

    sheets_meta = []
    for sh in ext.sheets:
        header = detect_header_row(sh.rows)
        sugg = suggest_mapping(sh.rows, header) if header is not None else None
        start = max(0, (header or 0) - 3)
        sheets_meta.append({
            "name": sh.name, "rows": sh.row_count, "columns": sh.column_count, "source": sh.source,
            "header_row": header, "header_score": header_score(sh.rows[header]) if header is not None else 0,
            "suggested_mapping": sugg.column_map if sugg else {}, "headers": sugg.headers if sugg else [],
            "notes": sugg.notes if sugg else ["En-tête non détecté : indiquez la ligne d'en-tête."],
            "warnings": sh.warnings, "preview_start": start,
            "preview": [[readers.jsonable(v) for v in r] for r in sh.rows[start:start + PREVIEW_ROWS]],
            "preview_confidence": sh.confidence[start:start + PREVIEW_ROWS] if sh.confidence else None,
        })
    job.sheets = sheets_meta
    extraction = dict(job.extraction or {})
    extraction.update(method=ext.method, page_count=ext.page_count, ocr_pages=ext.ocr_pages)
    if job.source_format == "pdf":
        sh = ext.sheets[0]
        extraction["pdf_cache"] = {"rows": [[readers.jsonable(v) for v in r] for r in sh.rows], "source": sh.source,
                                   "confidence": sh.confidence, "pages": sh.row_pages, "warnings": sh.warnings,
                                   "method": ext.method, "page_count": ext.page_count, "ocr_pages": ext.ocr_pages}
    job.extraction = extraction
    best = max(sheets_meta, key=lambda m: m["header_score"]) if sheets_meta else None
    job.sheet_name = best["name"] if best else None
    job.header_row = best["header_row"] if best else None
    job.column_map = best["suggested_mapping"] if best else None

    # modèle d'association enregistré pour l'entreprise : appliqué s'il correspond aux colonnes
    saved = db.scalar(select(ImportMapping).where(ImportMapping.company_id == job.company_id,
                                                  ImportMapping.kind == "trial_balance",
                                                  ImportMapping.is_default.is_(True)))
    if saved and best and _mapping_fits(saved.column_map, best):
        job.column_map = {k: int(v) for k, v in saved.column_map.items()}
        job.options = saved.options or {}
        job.mapping_id = saved.id

    job.status = "awaiting_mapping"
    db.flush()
    return job


def _mapping_fits(column_map: dict, sheet_meta: dict) -> bool:
    return all(isinstance(v, int) and v < max(sheet_meta["columns"], 1) for v in column_map.values())


def _fail(db: Session, job: ImportJob, reason: str) -> ImportJob:
    job.status = "failed"
    job.failure_reason = reason[:2000]
    db.flush()
    return job


# ------------------------------------------------------------------------------ configuration
def configure_import(db: Session, job: ImportJob, *, sheet_name: str, header_row: int,
                     column_map: dict[str, int], options: dict) -> ImportJob:
    if job.status not in ("awaiting_mapping", "awaiting_confirmation", "failed") or not job.sheets:
        raise Conflict("Cet import ne peut pas être reconfiguré dans son état actuel.")
    meta = next((m for m in job.sheets if m["name"] == sheet_name), None)
    if meta is None:
        raise ImportRejected(f"Feuille « {sheet_name} » introuvable dans le fichier.")
    if not 0 <= header_row < max(meta["rows"], 1):
        raise ImportRejected("Ligne d'en-tête hors du tableau.")
    try:
        validate_column_map(column_map)
        ImportOptions.from_dict(options)
    except (MappingError, TypeError, ValueError) as exc:
        raise ImportRejected(str(exc)) from exc
    if any(c >= meta["columns"] for c in column_map.values()):
        raise ImportRejected("Une colonne associée n'existe pas dans la feuille.")

    job.sheet_name, job.header_row, job.column_map, job.options = sheet_name, header_row, column_map, options
    job.status = "validating"
    job.failure_reason = None
    job.warnings_acknowledged = False
    db.flush()
    return job


# ------------------------------------------------------------------------------ traitement
def process_import(db: Session, job_id: uuid.UUID) -> ImportJob:
    job = db.get(ImportJob, job_id)
    if job is None:
        raise NotFound("Import introuvable")
    if job.status != "validating":
        return job
    try:
        ext = _extract(db, job)
    except FileRejected as exc:
        return _fail(db, job, str(exc))
    sheet = next((s for s in ext.sheets if s.name == job.sheet_name), None)
    if sheet is None:
        return _fail(db, job, "Feuille introuvable lors du traitement.")

    options = ImportOptions.from_dict(job.options)
    try:
        parsed = build_balance(sheet.rows, job.header_row or 0, {k: int(v) for k, v in (job.column_map or {}).items()},
                               options, confidence=sheet.confidence, row_pages=sheet.row_pages)
    except MappingError as exc:
        return _fail(db, job, str(exc))

    chart = _chart_context(db, job.framework_version_id)
    previous = _previous_closing(db, job) if chart else None
    report = run_controls(parsed, options, chart=chart, previous_closing=previous)

    db.execute(delete(ImportStagingRow).where(ImportStagingRow.import_job_id == job.id))
    payload = []
    for line in parsed.lines:
        payload.append(dict(
            organization_id=job.organization_id, company_id=job.company_id, fiscal_year_id=job.fiscal_year_id,
            import_job_id=job.id, source_row=line.source_row, source_page=line.page, status=line.status,
            account_number=line.account_number, account_label=line.account_label,
            opening_debit=line.opening_debit, opening_credit=line.opening_credit,
            movement_debit=line.movement_debit, movement_credit=line.movement_credit,
            closing_debit=line.closing_debit, closing_credit=line.closing_credit,
            closing_computed=line.closing_computed,
            ocr_confidence=Decimal(f"{line.min_confidence:.2f}") if line.min_confidence is not None else None,
            issues=[asdict(i) for i in line.issues], raw=line.raw))
    for i in range(0, len(payload), 1000):
        db.execute(insert(ImportStagingRow), payload[i:i + 1000])

    job.controls = report.to_dict()
    job.control_totals = report.totals
    job.total_rows = len(parsed.lines)
    job.valid_rows = len(parsed.valid)
    job.error_rows = len(parsed.errors)
    job.errors = [{"row": x.source_row, "issues": [i.message for i in x.issues]} for x in parsed.errors[:100]]
    job.status = "awaiting_confirmation"
    db.flush()
    return job


def _chart_context(db: Session, version_id: uuid.UUID | None) -> ChartContext | None:
    if version_id is None:
        return None
    version = db.get(FrameworkVersion, version_id)
    if version is None or version.status != "published":
        return None
    fw = db.get(AccountingFramework, version.framework_id)
    rows = db.execute(select(ChartAccount.account_number, ChartAccount.nature)
                      .where(ChartAccount.framework_version_id == version_id)).all()
    if not rows:
        return None
    return ChartContext(version_label=version.version_label, framework_code=fw.code if fw else "",
                        natures={r.account_number: r.nature for r in rows})


def _previous_closing(db: Session, job: ImportJob) -> dict[str, Decimal] | None:
    fy = db.get(FiscalYear, job.fiscal_year_id)
    prev = db.scalar(select(FiscalYear).where(FiscalYear.company_id == job.company_id,
                                              FiscalYear.end_date < fy.start_date)
                     .order_by(FiscalYear.end_date.desc()).limit(1))
    if prev is None or prev.active_import_job_id is None:
        return None
    rows = db.execute(select(TrialBalanceEntry.account_number,
                             TrialBalanceEntry.closing_debit - TrialBalanceEntry.closing_credit)
                      .where(TrialBalanceEntry.import_job_id == prev.active_import_job_id)).all()
    return {a: Decimal(n) for a, n in rows}


# ------------------------------------------------------------------------------ validation finale
def confirm_import(db: Session, job: ImportJob, *, user_id: uuid.UUID, acknowledge_warnings: bool,
                   save_mapping_as: str | None) -> ImportJob:
    if job.status != "awaiting_confirmation" or not job.controls:
        raise Conflict("L'import n'est pas prêt à être validé.")
    if job.controls.get("blocking"):
        raise Conflict("Des contrôles bloquants ont échoué : corrigez le fichier ou l'association des colonnes.")
    if job.controls.get("requires_acknowledgment") and not acknowledge_warnings:
        raise Conflict("Des avertissements doivent être explicitement acceptés avant la validation.")
    fy = db.get(FiscalYear, job.fiscal_year_id)
    if fy.status != "open":
        raise Conflict("L'exercice est clôturé.")

    db.execute(text("""
        INSERT INTO public.trial_balance_entries
          (organization_id, company_id, fiscal_year_id, import_job_id, account_number, account_label,
           opening_debit, opening_credit, movement_debit, movement_credit, closing_debit, closing_credit,
           source_row, source_page, closing_computed, ocr_confidence, raw_data)
        SELECT organization_id, company_id, fiscal_year_id, import_job_id, account_number, account_label,
               coalesce(opening_debit, 0), coalesce(opening_credit, 0),
               coalesce(movement_debit, 0), coalesce(movement_credit, 0),
               coalesce(closing_debit, 0), coalesce(closing_credit, 0),
               source_row, source_page, closing_computed, ocr_confidence, raw
          FROM public.import_staging_rows
         WHERE import_job_id = :job AND status = 'valid'
    """), {"job": job.id})

    # contrôle final en base : équilibre des lignes réellement enregistrées
    check = db.execute(text("""
        SELECT sum(closing_debit) - sum(closing_credit) AS diff, count(*) AS n
          FROM public.trial_balance_entries WHERE import_job_id = :job
    """), {"job": job.id}).one()
    tolerance = Decimal(str((job.options or {}).get("balance_tolerance", "0")))
    if check.n == 0 or abs(check.diff or 0) > tolerance:
        raise Conflict("Contrôle final : la balance enregistrée n'est pas équilibrée. Import annulé.")

    now = datetime.now(UTC)
    if fy.active_import_job_id and fy.active_import_job_id != job.id:
        db.execute(update(ImportJob).where(ImportJob.id == fy.active_import_job_id).values(status="superseded"))
    fy.active_import_job_id = job.id
    if fy.framework_version_id is None and job.framework_version_id is not None:
        fy.framework_version_id = job.framework_version_id

    job.status = "completed"
    job.validated_by, job.validated_at, job.completed_at = user_id, now, now
    job.warnings_acknowledged = bool(job.controls.get("requires_acknowledgment"))
    job.acknowledged_by = user_id if job.warnings_acknowledged else None
    if job.source_format == "pdf" and job.extraction:   # le cache OCR n'est plus utile
        job.extraction = {k: v for k, v in job.extraction.items() if k != "pdf_cache"}

    if save_mapping_as:
        db.execute(update(ImportMapping).where(ImportMapping.company_id == job.company_id,
                                               ImportMapping.kind == "trial_balance")
                   .values(is_default=False))
        mapping = ImportMapping(organization_id=job.organization_id, company_id=job.company_id,
                                name=save_mapping_as[:120], source_format=job.source_format,
                                column_map=job.column_map, options=job.options or {}, is_default=True,
                                created_by=user_id)
        db.add(mapping)
        db.flush()
        job.mapping_id = mapping.id
    db.flush()
    return job


def cancel_import(db: Session, job: ImportJob) -> ImportJob:
    if job.status not in ACTIVE_STATUSES + ("failed",):
        raise Conflict("Cet import ne peut plus être annulé.")
    db.execute(delete(ImportStagingRow).where(ImportStagingRow.import_job_id == job.id))
    job.status = "cancelled"
    if job.extraction:
        job.extraction = {k: v for k, v in job.extraction.items() if k != "pdf_cache"}
    db.flush()
    return job


# ------------------------------------------------------------------------------ lecture
def job_summary(job: ImportJob) -> dict:
    extraction = {k: v for k, v in (job.extraction or {}).items() if k != "pdf_cache"}
    return {
        "id": job.id, "company_id": job.company_id, "fiscal_year_id": job.fiscal_year_id,
        "document_id": job.document_id, "source_format": job.source_format, "status": job.status,
        "sheet_name": job.sheet_name, "header_row": job.header_row, "column_map": job.column_map,
        "options": job.options, "mapping_id": job.mapping_id, "sheets": job.sheets, "extraction": extraction,
        "controls": job.controls,
        "control_totals": job.control_totals, "total_rows": job.total_rows, "valid_rows": job.valid_rows,
        "error_rows": job.error_rows, "failure_reason": job.failure_reason,
        "framework_version_id": job.framework_version_id, "warnings_acknowledged": job.warnings_acknowledged,
        "started_by": job.started_by, "validated_by": job.validated_by, "validated_at": job.validated_at,
        "created_at": job.created_at, "updated_at": job.updated_at, "field_labels": FIELD_LABELS,
    }


def trial_balance(db: Session, fy: FiscalYear, *, account_class: str | None, q: str | None,
                  limit: int, offset: int) -> dict:
    if fy.active_import_job_id is None:
        return {"import": None, "items": [], "total_count": 0, "totals": None}
    base = select(TrialBalanceEntry).where(TrialBalanceEntry.import_job_id == fy.active_import_job_id)
    if account_class:
        base = base.where(TrialBalanceEntry.account_number.startswith(account_class))
    if q:
        term = q.strip().replace("\\", "").replace("%", "").replace("_", "")[:100]
        if term:
            base = base.where(TrialBalanceEntry.account_number.startswith(term)
                              | TrialBalanceEntry.account_label.ilike(f"%{term}%"))
    sub = base.subquery()
    agg = db.execute(select(func.count(), *[func.coalesce(func.sum(getattr(sub.c, f)), 0) for f in (
        "opening_debit", "opening_credit", "movement_debit", "movement_credit", "closing_debit", "closing_credit")])
    ).one()
    items = db.scalars(base.order_by(TrialBalanceEntry.account_number).limit(limit).offset(offset)).all()
    job = db.get(ImportJob, fy.active_import_job_id)
    fields = ("opening_debit", "opening_credit", "movement_debit", "movement_credit", "closing_debit",
              "closing_credit")
    return {
        "import": {"id": job.id, "validated_at": job.validated_at, "document_id": job.document_id,
                   "filename": (job.extraction or {}).get("filename"), "method": (job.extraction or {}).get("method")},
        "total_count": agg[0],
        "totals": {f: str(v) for f, v in zip(fields, agg[1:], strict=True)},
        "items": [{"account_number": e.account_number, "account_label": e.account_label,
                   **{f: str(getattr(e, f)) for f in fields},
                   "source_row": e.source_row, "source_page": e.source_page,
                   "closing_computed": e.closing_computed,
                   "ocr_confidence": str(e.ocr_confidence) if e.ocr_confidence is not None else None}
                  for e in items],
    }
