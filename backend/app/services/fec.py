"""Service — Fichier des Écritures Comptables (FEC) DGI Bénin.

Lecture des écritures : `native_ledger.posted` (écritures natives validées et extournées de l'exercice), complétée par
les libellés du plan, des journaux, des tiers et des lettrages. Aucune copie des écritures, aucune écriture modifiée.
Contrôles, rendu et documentation : moteur pur `engines.accounting.fec_bj`. Historique immuable : tables fec_exports et
fec_export_lines (migration 0016) ; fichiers dans le bucket privé « fec »."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError, NotFound
from app.engines.accounting import fec_bj as fec
from app.models import (
    ChartAccount,
    Company,
    CompanyAccount,
    FecExport,
    FecExportLine,
    FiscalYear,
    Journal,
    JournalEntry,
    Lettering,
    Profile,
    ThirdParty,
)
from app.services import native_ledger as gl
from app.services.journal_entries import POSTED
from app.services.storage import get_storage

BUCKET = "fec"
MIME = {"txt": "text/plain", "csv": "text/csv"}


class FecInvalid(AppError):
    status_code = 422
    code = "fec_invalid"


class FecBlocked(AppError):
    status_code = 409
    code = "fec_blocked"


# ------------------------------------------------------------------------------------------------- lecture des livres
def _period(fy: FiscalYear, start: date | None, end: date | None) -> tuple[date, date]:
    s, e = start or fy.start_date, end or fy.end_date
    if s > e or s < fy.start_date or e > fy.end_date:
        raise FecInvalid("La période doit être comprise dans l'exercice (date de début antérieure à la date de fin).")
    return s, e


def collect(db: Session, company: Company, fy: FiscalYear, start: date, end: date) -> tuple[list[fec.FecLine], fec.FecContext]:
    rows = gl.posted(db, fy)
    journals = {j.id: j for j in db.scalars(select(Journal).where(Journal.company_id == company.id))}
    accounts = {a.account_number: a for a in db.scalars(select(CompanyAccount).where(CompanyAccount.company_id == company.id))}
    chart = {}
    versions = {a.framework_version_id for a in accounts.values()}
    if versions:
        chart = {
            (c.framework_version_id, c.account_number): c.label
            for c in db.scalars(select(ChartAccount).where(ChartAccount.framework_version_id.in_(versions)))
        }
    tps = {t.id: t for t in db.scalars(select(ThirdParty).where(ThirdParty.company_id == company.id))}
    lets = {lt.id: lt for lt in db.scalars(select(Lettering).where(Lettering.company_id == company.id))}

    lines: list[fec.FecLine] = []
    fy_entries: dict[str, fec.FyEntry] = {}
    for p, m in rows:
        j = journals.get(m["journal_id"])
        eid = str(m["entry_id"])
        fy_entries.setdefault(eid, fec.FyEntry(eid, m["journal"], p.sequence or None, m["origin"], m["validated_at"]))
        if not (start <= p.entry_date <= end):
            continue
        acc = accounts.get(p.account)
        tp = tps.get(m["third_party_id"]) if m["third_party_id"] else None
        lt = lets.get(m["lettering_id"]) if m["lettering_id"] else None
        lines.append(
            fec.FecLine(
                entry_id=eid,
                line_id=str(m["line_id"]),
                journal_code=m["journal"],
                journal_label=j.label if j else "",
                number=m["number"],
                sequence_no=p.sequence or None,
                entry_date=p.entry_date,
                line_no=m["line_no"],
                account=p.account,
                account_label=acc.label if acc else None,
                debit=Decimal(p.debit),
                credit=Decimal(p.credit),
                validated_at=m["validated_at"],
                origin=m["origin"],
                status=m["status"],
                piece_ref=m["piece_ref"],
                piece_date=m["piece_date"],
                entry_label=m["entry_label"],
                line_label=m["label"],
                aux_code=tp.code if tp else None,
                aux_label=tp.name if tp else None,
                requires_third_party=bool(acc and acc.requires_third_party),
                lettering_code=lt.code if lt else None,
                lettering_date=fec.validation_date(lt.created_at) if lt else None,
                currency=m["currency"],
                currency_amount=Decimal(m["currency_amount"]) if m["currency_amount"] is not None else None,
                chart_account=acc.chart_account_number if acc else None,
                chart_label=chart.get((acc.framework_version_id, acc.chart_account_number)) if acc else None,
            )
        )
    pending = dict(
        db.execute(
            select(JournalEntry.status, func.count())
            .where(
                JournalEntry.fiscal_year_id == fy.id,
                JournalEntry.status.not_in(POSTED),
                JournalEntry.entry_date.between(start, end),
            )
            .group_by(JournalEntry.status)
        ).all()
    )
    has_previous = (
        db.scalar(
            select(func.count())
            .select_from(FiscalYear)
            .where(FiscalYear.company_id == company.id, FiscalYear.end_date < fy.start_date)
        )
        > 0
    )
    ctx = fec.FecContext(
        ifu=company.tax_id,
        country_code=company.country_code,
        framework_code=company.framework.code if company.framework else None,
        fy_start=fy.start_date,
        fy_end=fy.end_date,
        fy_closed=fy.status == "closed",
        period_start=start,
        period_end=end,
        has_previous_fy=has_previous,
        imported_ledger_active=fy.active_ledger_import_job_id is not None,
        pending=pending,
        fy_entries=list(fy_entries.values()),
    )
    return lines, ctx


def options(body: dict) -> fec.FecOptions:
    o = fec.FecOptions(
        file_format=body.get("file_format", ""),
        encoding=body.get("encoding", ""),
        record_separator=body.get("record_separator", ""),
        field_separator=body.get("field_separator") or "tab",
        accounting_type=body.get("accounting_type") or "accrual",
        max_lines_per_file=body.get("max_lines_per_file"),
    )
    errs = o.validate()
    if errs:
        raise FecInvalid(" ".join(errs))
    return o


def _source_state(lines: list[fec.FecLine], ctx: fec.FecContext) -> dict:
    last = max((ln.validated_at for ln in lines if ln.validated_at), default=None)
    return {
        "entries_fy": len(ctx.fy_entries),
        "last_validated_at": last.isoformat() if last else None,
        "pending": ctx.pending,
        "imported_ledger_active": ctx.imported_ledger_active,
        "fy_closed": ctx.fy_closed,
    }


def _summary(res: fec.CheckResult, ctx: fec.FecContext) -> dict:
    counts = res.entry_counts()
    return {
        "period_start": ctx.period_start.isoformat(),
        "period_end": ctx.period_end.isoformat(),
        **counts,
        "blocking": res.blocking,
        "warnings": res.warnings,
        "compliance": res.compliance,
        "can_generate_final": res.blocking == 0,
        "can_generate_working": not res.fatal,
        "total_debit": fec.fmt_amount(sum((ln.debit for ln in res.lines), Decimal(0))),
        "total_credit": fec.fmt_amount(sum((ln.credit for ln in res.lines), Decimal(0))),
        "anomalies": [a.as_dict() for a in res.anomalies],
        "spec_confirmed": fec.SPEC_CONFIRMED,
        "unconfirmed": list(fec.UNCONFIRMED),
    }


def run_check(db: Session, company: Company, fy_id: uuid.UUID, start: date | None, end: date | None, body: dict | None) -> dict:
    fy = gl._fy(db, company.id, fy_id)
    s, e = _period(fy, start, end)
    lines, ctx = collect(db, company, fy, s, e)
    opts = options(body) if body is not None else None
    res = fec.check(lines, ctx, opts)
    out = _summary(res, ctx)
    if opts is not None and company.tax_id and not res.fatal:
        out["filenames"] = [p.filename for p in fec.render(lines, opts, company.tax_id.strip(), fy.end_date)]
    return out


# ------------------------------------------------------------------------------------------------- tableau de bord
def dashboard(db: Session, company: Company, fy_id: uuid.UUID) -> dict:
    fy = gl._fy(db, company.id, fy_id)
    total = db.scalar(select(func.count()).select_from(JournalEntry).where(JournalEntry.fiscal_year_id == fy.id)) or 0
    validated = (
        db.scalar(
            select(func.count())
            .select_from(JournalEntry)
            .where(JournalEntry.fiscal_year_id == fy.id, JournalEntry.status.in_(POSTED))
        )
        or 0
    )
    lines, ctx = collect(db, company, fy, fy.start_date, fy.end_date)
    res = fec.check(lines, ctx)  # contrôles des données, sans les contrôles propres au format choisi
    last = db.scalars(
        select(FecExport)
        .where(FecExport.company_id == company.id, FecExport.fiscal_year_id == fy.id)
        .order_by(FecExport.version_no.desc())
    ).first()
    return {
        "fiscal_year": {
            "id": str(fy.id),
            "label": fy.label,
            "start_date": fy.start_date.isoformat(),
            "end_date": fy.end_date.isoformat(),
            "status": fy.status,
        },
        "company": {"name": company.name, "ifu": company.tax_id, "country_code": company.country_code},
        "entries_total": total,
        "entries_validated": validated,
        "entries_eligible": res.entry_counts()["eligible"],
        "anomalies_blocking": res.blocking,
        "anomalies_warning": res.warnings,
        "last_export": export_summary(last) if last else None,
        "spec_confirmed": fec.SPEC_CONFIRMED,
    }


# -------------------------------------------------------------------------------------------------------- génération
def _author(db: Session, user_id: uuid.UUID) -> str:
    p = db.get(Profile, user_id)
    return (p.full_name or p.email) if p else str(user_id)


def generate(
    db: Session,
    company: Company,
    user_id: uuid.UUID,
    fy_id: uuid.UUID,
    start: date | None,
    end: date | None,
    body: dict,
    kind: str,
) -> FecExport:
    if kind not in ("final", "working"):
        raise FecInvalid("Type de génération : final (définitive) ou working (fichier de travail).")
    fy = gl._fy(db, company.id, fy_id)
    s, e = _period(fy, start, end)
    opts = options(body)
    lines, ctx = collect(db, company, fy, s, e)
    res = fec.check(lines, ctx, opts)
    if res.fatal:
        raise FecBlocked(
            "Le fichier ne peut pas être produit fidèlement : " + " ; ".join(sorted({a.nature for a in res.fatal})) + ".",
            details={"anomalies": [a.as_dict() for a in res.fatal]},
        )
    if kind == "final" and res.blocking:
        raise FecBlocked(
            f"Génération définitive refusée : {res.blocking} anomalie(s) bloquante(s). Corrigez-les, ou produisez un fichier "
            "de travail (non conforme).",
            details={"blocking": res.blocking},
        )
    ifu = company.tax_id.strip()
    parts = fec.render(lines, opts, ifu, fy.end_date)
    version = (
        db.scalar(
            select(func.coalesce(func.max(FecExport.version_no), 0)).where(
                FecExport.company_id == company.id, FecExport.fiscal_year_id == fy.id
            )
        )
        + 1
    )
    export_id = uuid.uuid4()
    base = f"{company.organization_id}/{company.id}/{fy.id}/{export_id}"
    total_d = sum((ln.debit for ln in lines), Decimal(0))
    total_c = sum((ln.credit for ln in lines), Decimal(0))
    parts_meta = [
        {
            "part": p.part,
            "filename": p.filename,
            "storage_path": f"{base}/{p.filename}",
            "size_bytes": len(p.content),
            "sha256": p.sha256,
            "line_count": p.line_count,
        }
        for p in parts
    ]
    now = datetime.now(timezone.utc)
    meta = {
        "company": company.name,
        "ifu": ifu,
        "fiscal_year": fy.label,
        "fy_end": fy.end_date.isoformat(),
        "period_start": s.isoformat(),
        "period_end": e.isoformat(),
        "generated_at": now.astimezone(fec.LOCAL_TZ).isoformat(timespec="seconds"),
        "generated_by": _author(db, user_id),
        "parts": parts_meta,
        "sha256": fec.global_sha256(parts),
    }
    doc = fec.documentation(opts, meta)
    doc_path = f"{base}/DOCUMENTATION_{fec.filename(ifu, fy.end_date, 'txt')}"
    ex = FecExport(
        id=export_id,
        organization_id=company.organization_id,
        company_id=company.id,
        fiscal_year_id=fy.id,
        version_no=version,
        kind=kind,
        period_start=s,
        period_end=e,
        ifu=ifu,
        filename=fec.filename(ifu, fy.end_date, opts.file_format),
        file_format=opts.file_format,
        encoding=opts.encoding,
        field_separator=opts.field_separator,
        record_separator=opts.record_separator,
        max_lines_per_file=opts.max_lines_per_file,
        accounting_type=opts.accounting_type,
        line_count=len(lines),
        entry_count=len({ln.entry_id for ln in lines}),
        total_debit=total_d,
        total_credit=total_c,
        blocking_count=res.blocking,
        warning_count=res.warnings,
        compliance=res.compliance,
        spec_version=fec.SPEC_VERSION,
        spec_confirmed=fec.SPEC_CONFIRMED,
        anomalies=[a.as_dict() for a in res.anomalies],
        source_state=_source_state(lines, ctx),
        parts=parts_meta,
        size_bytes=sum(len(p.content) for p in parts),
        sha256=fec.global_sha256(parts),
        doc_storage_path=doc_path,
        doc_sha256=fec.sha256(doc),
        generator_version=fec.GENERATOR_VERSION,
        generated_by=user_id,
    )
    db.add(ex)
    db.flush()
    db.add_all(
        FecExportLine(
            export_id=export_id,
            row_no=i,
            organization_id=company.organization_id,
            company_id=company.id,
            entry_id=uuid.UUID(ln.entry_id),
            entry_line_id=uuid.UUID(ln.line_id),
        )
        for i, ln in enumerate(fec.ordered(lines), 1)
    )
    db.flush()
    st = get_storage()
    for p, pm in zip(parts, parts_meta, strict=True):
        st.upload(BUCKET, pm["storage_path"], p.content, MIME[opts.file_format])
    st.upload(BUCKET, doc_path, doc, "text/plain")
    db.refresh(ex)
    return ex


# ------------------------------------------------------------------------------------------------------- historique
def export_summary(ex: FecExport) -> dict:
    return {
        "id": str(ex.id),
        "version_no": ex.version_no,
        "kind": ex.kind,
        "period_start": ex.period_start.isoformat(),
        "period_end": ex.period_end.isoformat(),
        "filename": ex.filename,
        "parts": ex.parts,
        "file_format": ex.file_format,
        "encoding": ex.encoding,
        "field_separator": ex.field_separator,
        "record_separator": ex.record_separator,
        "accounting_type": ex.accounting_type,
        "line_count": ex.line_count,
        "entry_count": ex.entry_count,
        "total_debit": fec.fmt_amount(ex.total_debit),
        "total_credit": fec.fmt_amount(ex.total_credit),
        "blocking_count": ex.blocking_count,
        "warning_count": ex.warning_count,
        "compliance": ex.compliance,
        "spec_version": ex.spec_version,
        "spec_confirmed": ex.spec_confirmed,
        "sha256": ex.sha256,
        "size_bytes": ex.size_bytes,
        "doc_sha256": ex.doc_sha256,
        "generated_by": str(ex.generated_by),
        "generated_at": ex.generated_at.isoformat(),
    }


def exports(db: Session, company_id: uuid.UUID, fy_id: uuid.UUID | None) -> list[dict]:
    stmt = select(FecExport, Profile.full_name, Profile.email).join(Profile, Profile.id == FecExport.generated_by, isouter=True)
    stmt = stmt.where(FecExport.company_id == company_id)
    if fy_id:
        stmt = stmt.where(FecExport.fiscal_year_id == fy_id)
    out = []
    for ex, name, email in db.execute(stmt.order_by(FecExport.generated_at.desc())):
        out.append({**export_summary(ex), "generated_by_name": name or email})
    return out


def get_export(db: Session, company_id: uuid.UUID, export_id: uuid.UUID) -> FecExport:
    ex = db.get(FecExport, export_id)
    if ex is None or ex.company_id != company_id:
        raise NotFound("Génération FEC introuvable.")
    return ex


def file_part(ex: FecExport, part: int | None) -> tuple[str, bytes, str]:
    parts = ex.parts
    if part is None:
        if len(parts) != 1:
            raise FecInvalid("Fichier scindé : précisez la partie à télécharger.")
        pm = parts[0]
    else:
        pm = next((p for p in parts if p.get("part") == part), None)
        if pm is None:
            raise NotFound("Partie introuvable.")
    data = get_storage().download(BUCKET, pm["storage_path"])
    if fec.sha256(data) != pm["sha256"]:
        raise AppError("Le fichier archivé ne correspond plus à son empreinte : téléchargement refusé.")
    return pm["filename"], data, MIME[ex.file_format]


def documentation_file(ex: FecExport) -> tuple[str, bytes]:
    data = get_storage().download(BUCKET, ex.doc_storage_path)
    if fec.sha256(data) != ex.doc_sha256:
        raise AppError("La documentation archivée ne correspond plus à son empreinte : téléchargement refusé.")
    return ex.doc_storage_path.rsplit("/", 1)[-1], data


def trace(db: Session, ex: FecExport, row_no: int) -> dict:
    ln = db.get(FecExportLine, (ex.id, row_no))
    if ln is None:
        raise NotFound("Ligne du fichier introuvable.")
    return {"row_no": row_no, "entry_id": str(ln.entry_id), "entry_line_id": str(ln.entry_line_id)}
