"""Service de reporting (lot 11) : rassemble les données validées par les services existants, construit le document
neutre, le rend dans le format demandé, enregistre le fichier dans le compartiment privé « reports » et trace le
document généré (empreintes, sources, modèle). Un document généré est figé ; une nouvelle génération crée un nouveau
document."""

from __future__ import annotations

import re
import unicodedata
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import Conflict, NotFound
from app.engines.reporting import builders, render
from app.engines.reporting import document as rd
from app.models import (
    AiReport,
    AuditReport,
    Budget,
    Company,
    Engagement,
    FinancialAnalysis,
    FiscalYear,
    GeneratedReport,
    ReportTemplate,
)
from app.services import analysis as analysis_svc
from app.services import financial_audit as fa_svc
from app.services import internal_control as ic_svc
from app.services import management as mgmt_svc
from app.services.engagements import AuditInvalid, people
from app.services.storage import get_storage

BUCKET = "reports"
FORMATS = ("pdf", "xlsx", "docx")
DOCUMENT_TYPES = {
    "financial_report": "Rapport financier (analyse terminée)",
    "budget_report": "Suivi budgétaire (budget approuvé)",
    "ic_report": "Rapport de contrôle interne (tests revus, évaluations approuvées)",
    "internal_audit_report": "Rapport d'audit interne (rapport émis)",
    "fa_summary": "Synthèse des anomalies d'audit financier (seuils approuvés)",
}
REPORT_FIELDS = (
    "id",
    "company_id",
    "analysis_id",
    "engagement_id",
    "template_id",
    "template_version",
    "document_type",
    "subtype",
    "title",
    "format",
    "status",
    "filename",
    "mime_type",
    "size_bytes",
    "sha256",
    "data_sha256",
    "source_refs",
    "parameters",
    "contains_ai_drafts",
    "generator_version",
    "failure_reason",
    "requested_by",
    "created_at",
)
TEMPLATE_FIELDS = (
    "id",
    "organization_id",
    "name",
    "document_type",
    "version",
    "status",
    "sections",
    "content",
    "branding",
    "is_default",
    "published_by",
    "published_at",
    "created_by",
    "created_at",
    "updated_at",
)
TEMPLATE_SECTIONS = {"financial_report": list(builders.FINANCIAL_SECTIONS)}


# ------------------------------------------------------------------ modèles
def template_for(db: Session, org_id: uuid.UUID, doc_type: str, template_id: uuid.UUID | None) -> ReportTemplate | None:
    if template_id is None:
        return None
    t = db.get(ReportTemplate, template_id)
    if t is None or (t.organization_id not in (None, org_id)):
        raise NotFound("Modèle introuvable")
    if t.status != "published" or t.document_type != doc_type:
        raise AuditInvalid("Modèle : choisissez une version publiée de ce type de document.")
    return t


def _tpl(t: ReportTemplate | None) -> dict | None:
    if t is None:
        return None
    return {
        "name": t.name,
        "version": t.version,
        "sections": t.sections or [],
        "content": t.content or {},
        "branding": t.branding or {},
    }


# ------------------------------------------------------------------ données validées, par type
def financial_doc(db: Session, company: Company, a: FinancialAnalysis, include_unreviewed_ai: bool, tpl: dict | None):
    if a.status != "completed":
        raise AuditInvalid("Le rapport financier s'établit sur une analyse terminée.")
    fy = db.get(FiscalYear, a.fiscal_year_id)
    prev = db.get(FiscalYear, a.previous_fiscal_year_id) if a.previous_fiscal_year_id else None
    statuses = ("reviewed", "draft") if include_unreviewed_ai else ("reviewed",)
    ais = list(
        db.scalars(
            select(AiReport).where(AiReport.analysis_id == a.id, AiReport.status.in_(statuses)).order_by(AiReport.created_at)
        )
    )
    ppl = people(db, [x.reviewed_by for x in ais])
    ai_dicts = [
        {
            "id": x.id,
            "section": x.section,
            "status": x.status,
            "content": x.content,
            "model": x.model,
            "prompt_version": x.prompt_version,
            "reviewed_at": x.reviewed_at,
            "reviewed_by_name": _name(ppl.get(str(x.reviewed_by))),
        }
        for x in ais
    ]
    doc = builders.financial(
        {
            "entity": company.name,
            "fiscal_year": {"label": fy.label, "start": fy.start_date, "end": fy.end_date},
            "previous_label": prev.label if prev else None,
        },
        analysis_svc.analysis_detail(db, a),
        ai_dicts,
        tpl,
    )
    return doc, [x.id for x in ais], any(x.status == "draft" for x in ais)


def budget_doc(db: Session, company: Company, b: Budget, tpl: dict | None) -> dict:
    if b.status not in ("approved", "archived"):
        raise AuditInvalid("Le suivi budgétaire s'établit sur un budget approuvé.")
    fy = db.get(FiscalYear, b.fiscal_year_id)
    tr = mgmt_svc.tracking(db, b, fy)
    return builders.budget(
        {"entity": company.name, "budget": {"id": b.id, "name": b.name, "version": b.version, "approved_at": b.approved_at}},
        rd_json(tr),
        tpl,
    )


def ic_doc(db: Session, company: Company, ic_ctx, kind: str, filters: dict, tpl: dict | None) -> dict:
    rep = ic_svc.build_report(db, ic_ctx, kind, filters.get("domain_id"), filters.get("process_id"), filters.get("cycle_code"))
    return builders.internal_control({"entity": company.name}, rd_json(rep), tpl)


def internal_audit_doc(db: Session, e: Engagement, tpl: dict | None) -> dict:
    r = db.scalar(select(AuditReport).where(AuditReport.engagement_id == e.id, AuditReport.status == "issued"))
    if r is None:
        raise AuditInvalid("Aucun rapport émis pour cette mission : seul le rapport émis, figé, s'exporte ici.")
    return builders.internal_audit(
        {"id": r.id, "content_sha256": r.content_sha256, "snapshot": {**rd_json(r.snapshot), "issued_at": r.issued_at}}, tpl
    )


def fa_summary_doc(db: Session, e: Engagement, company: Company, tpl: dict | None) -> dict:
    m = fa_svc.approved_materiality(db, e)
    if m is None:
        raise AuditInvalid("Seuils de signification approuvés requis pour la synthèse des anomalies.")
    period = f"du {rd.fmt_date(e.period_start)} au {rd.fmt_date(e.period_end)}" if e.period_start else None
    return builders.fa_summary(
        {"engagement": {"id": e.id, "reference": e.reference, "name": e.name}, "entity": company.name, "period": period},
        rd_json(fa_svc.summary(db, e)),
        {"id": m.id, "benchmark_label": m.benchmark_label, "basis": m.basis, "approved_at": m.approved_at},
        tpl,
    )


def rd_json(obj):
    """Valeurs JSON (Decimal, dates, UUID en texte) : le document ne contient que des valeurs sérialisables."""
    import json

    return json.loads(rd.canonical(obj))


# ------------------------------------------------------------------ génération
def _name(p: dict | None) -> str | None:
    return (p.get("full_name") or p.get("email")) if p else None


def _filename(title: str, fmt: str, when: datetime) -> str:
    s = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    s = re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-").lower()[:80] or "rapport"
    return f"{s}-{when:%Y%m%d-%H%M}.{fmt}"


def produce(
    db: Session,
    *,
    user_id: uuid.UUID,
    org_id: uuid.UUID,
    company_id: uuid.UUID,
    doc: dict,
    fmt: str,
    doc_type: str,
    template: ReportTemplate | None,
    analysis_id=None,
    engagement_id=None,
    subtype=None,
    ai_ids=(),
    contains_drafts=False,
    parameters: dict | None = None,
) -> GeneratedReport:
    if fmt not in FORMATS:
        raise AuditInvalid("Format : pdf, xlsx ou docx.")
    doc = rd_json(doc)
    now = datetime.now(timezone.utc)
    rid = uuid.uuid4()
    meta = {
        "generated_at": now,
        "generated_by": _name(people(db, [user_id]).get(str(user_id))),
        "data_sha256": rd.data_digest(doc),
        "branding": (template.branding if template else {}) or {},
    }
    base = dict(
        id=rid,
        organization_id=org_id,
        company_id=company_id,
        analysis_id=analysis_id,
        engagement_id=engagement_id,
        template_id=template.id if template else None,
        template_version=template.version if template else None,
        document_type=doc_type,
        subtype=subtype,
        title=doc["title"],
        format=fmt,
        requested_by=user_id,
        parameters=parameters or {},
        generator_version=rd.GENERATOR_VERSION,
    )
    try:
        data = render.render(doc, fmt, meta)
    except Exception as exc:  # noqa: BLE001 — l'échec est tracé, jamais masqué
        g = GeneratedReport(**base, status="failed", failure_reason=f"Rendu impossible : {exc.__class__.__name__}: {exc}"[:2000])
        db.add(g)
        db.flush()
        return g
    filename = _filename(doc["title"], fmt, now)
    path = f"{org_id}/{company_id}/{rid}.{fmt}"
    g = GeneratedReport(
        **base,
        status="ready",
        storage_path=path,
        filename=filename,
        mime_type=render.MIME[fmt],
        size_bytes=len(data),
        sha256=rd.file_digest(data),
        data_sha256=meta["data_sha256"],
        content_snapshot=doc,
        source_refs=doc["sources"],
        ai_report_ids=list(ai_ids),
        contains_ai_drafts=contains_drafts,
    )
    db.add(g)
    db.flush()  # la base vérifie d'abord les sources ; le fichier n'est déposé qu'ensuite (échec du dépôt = annulation)
    get_storage().upload(BUCKET, path, data, render.MIME[fmt])
    db.refresh(g)
    return g


def report_out(g: GeneratedReport, ppl: dict | None = None) -> dict:
    out = {k: getattr(g, k) for k in REPORT_FIELDS}
    out["document_label"] = DOCUMENT_TYPES.get(g.document_type, g.document_type)
    if ppl is not None:
        out["requested_by_user"] = ppl.get(str(g.requested_by))
    return out


def download(g: GeneratedReport) -> dict:
    if g.status != "ready" or not g.storage_path:
        raise Conflict("Document en échec : aucun fichier.")
    return {
        "url": get_storage().signed_url(BUCKET, g.storage_path, download_name=g.filename),
        "filename": g.filename,
        "sha256": g.sha256,
        "data_sha256": g.data_sha256,
    }


def template_out(t: ReportTemplate) -> dict:
    return {k: getattr(t, k) for k in TEMPLATE_FIELDS}
