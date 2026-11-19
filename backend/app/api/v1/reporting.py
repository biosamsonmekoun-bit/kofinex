"""API — reporting et génération documentaire (lot 11).

- `/reporting/document-types` : types de documents et formats ;
- `/companies/{id}/documents` : rapport financier, suivi budgétaire, rapports du contrôle interne ;
- `/engagements/{id}/documents` : rapport d'audit interne émis, synthèse des anomalies d'audit financier ;
- `/documents/{id}` et `/documents/{id}/download` : document figé et lien signé (5 min), selon les droits de lecture ;
- `/organizations/{id}/report-templates`, `/report-templates/{id}…` : modèles versionnés, figés à la publication.
Les données viennent des services existants et ne sont prises qu'à l'état validé (analyse terminée, budget approuvé,
tests revus, rapport émis, seuils approuvés) ; la base le vérifie à nouveau à l'enregistrement."""

from __future__ import annotations

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import (
    CompanyContext,
    OrgContext,
    get_company_context,
    get_current_user,
    get_db,
    get_org_context,
    require_org_manager,
)
from app.core.errors import Conflict, NotFound
from app.core.permissions import Permission
from app.core.security import AuthenticatedUser
from app.engines.reporting.builders import FINANCIAL_SECTIONS
from app.models import Budget, Company, FinancialAnalysis, GeneratedReport, ReportTemplate
from app.services import internal_control as ic_svc
from app.services import reporting as svc
from app.services.audit import record_event
from app.services.engagements import AuditInvalid, EngagementContext, get_engagement_context, people

router = APIRouter(tags=["reporting"])
Db = Annotated[Session, Depends(get_db)]
Comp = Annotated[CompanyContext, Depends(get_company_context)]
Eng = Annotated[EngagementContext, Depends(get_engagement_context)]
Fmt = Literal["pdf", "xlsx", "docx"]


def _log(db, request, user_id, org_id, action, entity_id, details, company_id=None):
    record_event(
        db,
        user_id=user_id,
        action=action,
        entity_type="generated_reports",
        entity_id=entity_id,
        organization_id=org_id,
        company_id=company_id,
        details=details,
        request=request,
    )


def _list(db: Session, rows: list[GeneratedReport]) -> list[dict]:
    ppl = people(db, [g.requested_by for g in rows])
    return [svc.report_out(g, ppl) for g in rows]


@router.get("/reporting/document-types")
def document_types(_: Annotated[AuthenticatedUser, Depends(get_current_user)]):
    return {"types": svc.DOCUMENT_TYPES, "formats": list(svc.FORMATS), "template_sections": svc.TEMPLATE_SECTIONS}


# ======================================================================== entreprise
@router.get("/companies/{company_id}/documents", summary="Documents générés de l'entreprise (hors missions)")
def list_company(ctx: Comp, db: Db, document_type: str | None = None):
    q = select(GeneratedReport).where(GeneratedReport.company_id == ctx.company_id, GeneratedReport.engagement_id.is_(None))
    if document_type:
        q = q.where(GeneratedReport.document_type == document_type)
    return _list(db, list(db.scalars(q.order_by(GeneratedReport.created_at.desc()).limit(200))))


class CompanyReportIn(BaseModel):
    document_type: Literal["financial_report", "budget_report", "ic_report"]
    format: Fmt
    template_id: uuid.UUID | None = None
    analysis_id: uuid.UUID | None = None
    fiscal_year_id: uuid.UUID | None = None
    include_unreviewed_ai: bool = False
    budget_id: uuid.UUID | None = None
    ic_kind: (
        Literal[
            "assessment",
            "domain",
            "process",
            "cycle",
            "risk_map",
            "matrix",
            "ineffective_controls",
            "deficiencies",
            "remediation",
        ]
        | None
    ) = None
    domain_id: uuid.UUID | None = None
    process_id: uuid.UUID | None = None
    cycle_code: str | None = Field(default=None, max_length=40)


@router.post(
    "/companies/{company_id}/documents", status_code=status.HTTP_201_CREATED, summary="Générer un document de l'entreprise"
)
def create_company(p: CompanyReportIn, request: Request, ctx: Comp, db: Db):
    company = db.get(Company, ctx.company_id)
    tpl = svc.template_for(db, ctx.organization_id, p.document_type, p.template_id)
    kw: dict = {}
    if p.document_type == "financial_report":
        ctx.require(Permission.REPORT_GENERATE)
        if p.analysis_id:
            a = db.get(FinancialAnalysis, p.analysis_id)
        elif p.fiscal_year_id:
            a = db.scalars(
                select(FinancialAnalysis)
                .where(
                    FinancialAnalysis.company_id == ctx.company_id,
                    FinancialAnalysis.fiscal_year_id == p.fiscal_year_id,
                    FinancialAnalysis.status == "completed",
                )
                .order_by(FinancialAnalysis.completed_at.desc())
            ).first()
        else:
            raise AuditInvalid("Choisissez l'exercice ou l'analyse.")
        if a is None or a.company_id != ctx.company_id:
            raise AuditInvalid("Aucune analyse terminée pour cet exercice.")
        doc, ai_ids, drafts = svc.financial_doc(db, company, a, p.include_unreviewed_ai, svc._tpl(tpl))
        kw = {"analysis_id": a.id, "ai_ids": ai_ids, "contains_drafts": drafts}
    elif p.document_type == "budget_report":
        ctx.require(Permission.REPORT_GENERATE)
        b = db.get(Budget, p.budget_id) if p.budget_id else None
        if b is None or b.company_id != ctx.company_id:
            raise NotFound("Budget introuvable")
        doc = svc.budget_doc(db, company, b, svc._tpl(tpl))
    else:
        if not p.ic_kind:
            raise AuditInvalid("Choisissez le rapport de contrôle interne.")
        ic_ctx = ic_svc.load_ic_context(db, ctx.company_id, ctx.user)
        doc = svc.ic_doc(
            db,
            company,
            ic_ctx,
            p.ic_kind,
            {"domain_id": p.domain_id, "process_id": p.process_id, "cycle_code": p.cycle_code},
            svc._tpl(tpl),
        )
        kw = {"subtype": p.ic_kind}
    g = svc.produce(
        db,
        user_id=ctx.user.id,
        org_id=ctx.organization_id,
        company_id=ctx.company_id,
        doc=doc,
        fmt=p.format,
        doc_type=p.document_type,
        template=tpl,
        parameters=p.model_dump(mode="json", exclude_none=True),
        **kw,
    )
    _log(
        db,
        request,
        ctx.user.id,
        ctx.organization_id,
        "report.generate",
        g.id,
        {"document_type": p.document_type, "format": p.format, "status": g.status, "sha256": g.sha256},
        ctx.company_id,
    )
    return svc.report_out(g, people(db, [g.requested_by]))


# ======================================================================== mission
@router.get("/engagements/{engagement_id}/documents", summary="Documents générés de la mission")
def list_engagement(ctx: Eng, db: Db):
    ctx.require("read_dossier")
    return _list(
        db,
        list(
            db.scalars(
                select(GeneratedReport)
                .where(GeneratedReport.engagement_id == ctx.engagement.id)
                .order_by(GeneratedReport.created_at.desc())
            )
        ),
    )


class EngagementReportIn(BaseModel):
    document_type: Literal["internal_audit_report", "fa_summary"]
    format: Fmt
    template_id: uuid.UUID | None = None


@router.post(
    "/engagements/{engagement_id}/documents", status_code=status.HTTP_201_CREATED, summary="Générer un document de la mission"
)
def create_engagement(p: EngagementReportIn, request: Request, ctx: Eng, db: Db):
    ctx.require("read_dossier")
    e = ctx.engagement
    if ctx.role in (None, "auditee", "observer", "quality_reviewer"):
        raise AuditInvalid("Génération réservée à l'équipe de mission (associé, manager, chef de mission, auditeur).")
    tpl = svc.template_for(db, e.organization_id, p.document_type, p.template_id)
    if p.document_type == "internal_audit_report":
        if e.engagement_type not in ("internal_audit", "ic_assessment"):
            raise AuditInvalid("Rapport d'audit interne : mission d'audit interne ou de contrôle interne.")
        doc = svc.internal_audit_doc(db, e, svc._tpl(tpl))
    else:
        if e.engagement_type not in ("statutory_audit", "contractual_audit"):
            raise AuditInvalid("Synthèse des anomalies : mission d'audit financier.")
        doc = svc.fa_summary_doc(db, e, db.get(Company, e.company_id), svc._tpl(tpl))
    g = svc.produce(
        db,
        user_id=ctx.user.id,
        org_id=e.organization_id,
        company_id=e.company_id,
        doc=doc,
        fmt=p.format,
        doc_type=p.document_type,
        template=tpl,
        engagement_id=e.id,
        parameters=p.model_dump(mode="json", exclude_none=True),
    )
    _log(
        db,
        request,
        ctx.user.id,
        e.organization_id,
        "report.generate",
        g.id,
        {"document_type": p.document_type, "format": p.format, "status": g.status, "engagement_id": str(e.id)},
        e.company_id,
    )
    return svc.report_out(g, people(db, [g.requested_by]))


# ======================================================================== document et téléchargement (RLS)
def _visible(db: Session, report_id: uuid.UUID) -> GeneratedReport:
    g = db.get(GeneratedReport, report_id)  # session soumise à la RLS : invisible = introuvable
    if g is None:
        raise NotFound("Document introuvable")
    return g


@router.get("/documents/{report_id}", summary="Document généré : empreintes, sources, contenu structuré figé")
def get_report(report_id: uuid.UUID, db: Db):
    g = _visible(db, report_id)
    return {**svc.report_out(g, people(db, [g.requested_by])), "content_snapshot": g.content_snapshot}


@router.get("/documents/{report_id}/download", summary="Lien signé vers le fichier (5 min)")
def download(report_id: uuid.UUID, request: Request, db: Db, user: Annotated[AuthenticatedUser, Depends(get_current_user)]):
    g = _visible(db, report_id)
    out = svc.download(g)
    _log(db, request, user.id, g.organization_id, "report.download", g.id, {"sha256": g.sha256}, g.company_id)
    return out


# ======================================================================== modèles
class TemplateIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    document_type: Literal["financial_report", "budget_report", "ic_report", "internal_audit_report", "fa_summary"]
    sections: list[str] = Field(default_factory=list, max_length=20)
    title: str | None = Field(default=None, max_length=300)
    intro_title: str | None = Field(default=None, max_length=120)
    intro: str | None = Field(default=None, max_length=8000)
    closing_title: str | None = Field(default=None, max_length=120)
    closing: str | None = Field(default=None, max_length=8000)
    primary_color: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")


def _check_sections(p: TemplateIn) -> None:
    allowed = svc.TEMPLATE_SECTIONS.get(p.document_type, [])
    bad = [s for s in p.sections if s not in allowed]
    if bad:
        raise AuditInvalid(
            f"Sections inconnues pour ce type de document : {', '.join(bad)} (possibles : {', '.join(allowed) or 'aucune'})."
        )


def _content(p: TemplateIn) -> dict:
    return {
        k: v.strip()
        for k, v in p.model_dump(include={"title", "intro_title", "intro", "closing_title", "closing"}).items()
        if isinstance(v, str) and v.strip()
    }


def _tpl_own(db: Session, ctx: OrgContext, template_id: uuid.UUID) -> ReportTemplate:
    t = db.get(ReportTemplate, template_id)
    if t is None or t.organization_id != ctx.organization_id:
        raise NotFound("Modèle introuvable")
    return t


@router.get("/organizations/{org_id}/report-templates")
def list_templates(ctx: Annotated[OrgContext, Depends(get_org_context)], db: Db, document_type: str | None = None):
    q = select(ReportTemplate).where(
        (ReportTemplate.organization_id == ctx.organization_id) | ReportTemplate.organization_id.is_(None)
    )
    if document_type:
        q = q.where(ReportTemplate.document_type == document_type)
    return {
        "can_edit": ctx.is_manager,
        "items": [svc.template_out(t) for t in db.scalars(q.order_by(ReportTemplate.name, ReportTemplate.version))],
        "financial_sections": list(FINANCIAL_SECTIONS),
    }


@router.post("/organizations/{org_id}/report-templates", status_code=status.HTTP_201_CREATED)
def create_template(p: TemplateIn, request: Request, ctx: Annotated[OrgContext, Depends(require_org_manager)], db: Db):
    _check_sections(p)
    t = ReportTemplate(
        id=uuid.uuid4(),
        organization_id=ctx.organization_id,
        name=p.name.strip(),
        report_kind="custom",
        document_type=p.document_type,
        sections=p.sections,
        content=_content(p),
        branding={"primary_color": p.primary_color} if p.primary_color else {},
    )
    db.add(t)
    db.flush()
    db.refresh(t)
    record_event(
        db,
        user_id=ctx.user.id,
        action="report_template.create",
        entity_type="report_templates",
        entity_id=t.id,
        organization_id=ctx.organization_id,
        details={"name": t.name},
        request=request,
    )
    return svc.template_out(t)


@router.patch("/organizations/{org_id}/report-templates/{template_id}", summary="Modifier un modèle en brouillon")
def update_template(template_id: uuid.UUID, p: TemplateIn, ctx: Annotated[OrgContext, Depends(require_org_manager)], db: Db):
    t = _tpl_own(db, ctx, template_id)
    if t.status != "draft":
        raise Conflict("Modèle publié : figé. Créez une nouvelle version.")
    if p.document_type != t.document_type:
        raise AuditInvalid("Le type de document d'un modèle ne change pas.")
    _check_sections(p)
    t.name, t.sections, t.content = p.name.strip(), p.sections, _content(p)
    t.branding = {"primary_color": p.primary_color} if p.primary_color else {}
    db.flush()
    db.refresh(t)
    return svc.template_out(t)


@router.post("/organizations/{org_id}/report-templates/{template_id}/{action}", summary="publish | archive | new-version")
def template_action(
    template_id: uuid.UUID,
    action: Literal["publish", "archive", "new-version"],
    request: Request,
    ctx: Annotated[OrgContext, Depends(require_org_manager)],
    db: Db,
):
    t = _tpl_own(db, ctx, template_id)
    if action == "publish":
        t.status, t.published_by = "published", ctx.user.id
        out = t
    elif action == "archive":
        t.status = "archived"
        out = t
    else:
        last = max(
            x.version
            for x in db.scalars(
                select(ReportTemplate).where(
                    ReportTemplate.organization_id == ctx.organization_id,
                    ReportTemplate.document_type == t.document_type,
                    ReportTemplate.name == t.name,
                )
            )
        )
        out = ReportTemplate(
            id=uuid.uuid4(),
            organization_id=ctx.organization_id,
            name=t.name,
            report_kind=t.report_kind,
            document_type=t.document_type,
            version=last + 1,
            sections=t.sections,
            content=t.content,
            branding=t.branding,
        )
        db.add(out)
    db.flush()
    db.refresh(out)
    record_event(
        db,
        user_id=ctx.user.id,
        action=f"report_template.{action}",
        entity_type="report_templates",
        entity_id=out.id,
        organization_id=ctx.organization_id,
        details={"version": out.version},
        request=request,
    )
    return svc.template_out(out)


@router.delete("/organizations/{org_id}/report-templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_template(template_id: uuid.UUID, ctx: Annotated[OrgContext, Depends(require_org_manager)], db: Db):
    t = _tpl_own(db, ctx, template_id)
    if t.status != "draft":
        raise Conflict("Modèle publié : conservé (archivez-le).")
    db.delete(t)
    db.flush()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
