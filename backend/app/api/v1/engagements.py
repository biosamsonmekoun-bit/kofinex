"""Socle commun d'audit : méthodologies, registre des risques, missions, équipe, risques, programmes,
feuilles de travail, éléments probants, notes de revue, signatures et supervision.

Les règles de circuit et de séparation des tâches sont appliquées par la base (migration 0007) ;
l'API les vérifie aussi en amont pour donner des messages clairs."""

from __future__ import annotations

import csv
import io
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, Request, Response, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.api.deps import CompanyContext, OrgContext, get_company_context, get_current_user, get_db, get_org_context
from app.core.errors import Conflict, Forbidden, NotFound
from app.core.security import AuthenticatedUser
from app.engines.audit import methodology as meth
from app.engines.audit import workflow as wf
from app.engines.audit.evidence import safe_filename, validate_evidence
from app.engines.importing.files import FileRejected, decode_text
from app.models import (
    ControlTest,
    ControlTestItem,
    IcAssessment,
    Company,
    Engagement,
    EngagementMember,
    EngagementRisk,
    EvidenceItem,
    EvidenceLink,
    FiscalYear,
    MethodologyItem,
    MethodologyVersion,
    Procedure,
    ProcedureRisk,
    Process,
    Profile,
    ReviewNote,
    Risk,
    Signoff,
    Workpaper,
    WorkProgram,
)
from app.services import engagements as svc
from app.services.audit import record_event
from app.services.engagements import AuditInvalid, EngagementContext, get_engagement_context, owned, row
from app.services.storage import get_storage

router = APIRouter(tags=["Audit — socle commun"])
EVIDENCE_BUCKET = "audit-evidence"


def _now() -> datetime:
    return datetime.now(UTC)


def _log(db, request, user_id, action, entity_type, entity_id, org_id, company_id=None, details=None):
    record_event(db, user_id=user_id, action=action, entity_type=entity_type, entity_id=entity_id,
                 organization_id=org_id, company_id=company_id, details=details, request=request)


def _elog(db, request, ctx: EngagementContext, action, entity_type, entity_id, details=None):
    _log(db, request, ctx.user.id, action, entity_type, entity_id, ctx.engagement.organization_id,
         ctx.engagement.company_id, {"engagement_id": str(ctx.engagement.id), **(details or {})})


# ======================================================================== méthodologies
class MethodologyCreate(BaseModel):
    organization_id: uuid.UUID | None = None
    kind: Literal["audit", "internal_control"]
    name: str = Field(min_length=1, max_length=200)
    version_label: str = Field(min_length=1, max_length=50)
    source_reference: str = Field(min_length=3, max_length=1000)
    description: str | None = Field(default=None, max_length=4000)
    # lot 9 : nature du référentiel (cadre de contrôle interne, norme professionnelle, exigence légale ou comptable,
    # méthodologie interne), organisme, dates et document source — renseignés par l'utilisateur, jamais déduits
    framework_category: Literal["ic_framework", "professional_standard", "legal_requirement",
                                "internal_methodology"] | None = None
    issuing_body: str | None = Field(default=None, max_length=300)
    published_on: date | None = None
    effective_from: date | None = None
    source_document: str | None = Field(default=None, max_length=1000)


M_FIELDS = ("id", "organization_id", "kind", "name", "version_label", "source_reference", "description", "status",
            "published_at", "created_at", "framework_category", "issuing_body", "published_on", "effective_from",
            "source_document")
ITEM_FIELDS = ("id", "item_type", "code", "label", "parent_code", "content", "display_order")


def _can_manage_methodology(db: Session, user: AuthenticatedUser, org_id: uuid.UUID | None) -> bool:
    if org_id is None:
        return bool(db.scalar(select(Profile.is_platform_admin).where(Profile.id == user.id)))
    return bool(db.execute(text("SELECT authz.has_org_role(:o, ARRAY['owner','admin'])"), {"o": org_id}).scalar())


def _methodology(db: Session, mid: uuid.UUID) -> MethodologyVersion:
    m = db.get(MethodologyVersion, mid)
    if m is None:
        raise NotFound("Méthodologie introuvable")
    return m


@router.get("/methodologies", summary="Méthodologies visibles (plateforme et organisations de l'utilisateur)")
def list_methodologies(organization_id: uuid.UUID | None = None, db: Session = Depends(get_db),
                       user: AuthenticatedUser = Depends(get_current_user)):
    q = select(MethodologyVersion).order_by(MethodologyVersion.kind, MethodologyVersion.name,
                                            MethodologyVersion.created_at.desc())
    if organization_id:
        q = q.where((MethodologyVersion.organization_id == organization_id) | MethodologyVersion.organization_id.is_(None))
    out = []
    for m in db.scalars(q):
        n = db.scalar(select(func.count()).select_from(MethodologyItem).where(MethodologyItem.version_id == m.id))
        out.append({**row(m, M_FIELDS), "items": n, "can_manage": _can_manage_methodology(db, user, m.organization_id)})
    return out


@router.post("/methodologies", status_code=status.HTTP_201_CREATED)
def create_methodology(payload: MethodologyCreate, request: Request, db: Session = Depends(get_db),
                       user: AuthenticatedUser = Depends(get_current_user)):
    if not _can_manage_methodology(db, user, payload.organization_id):
        raise Forbidden("Méthodologie de la plateforme : administrateurs de la plateforme ; d'une organisation : "
                        "ses propriétaires et administrateurs.")
    m = MethodologyVersion(id=uuid.uuid4(), created_by=user.id, **payload.model_dump())
    db.add(m)
    db.flush()
    _log(db, request, user.id, "methodology.create", "methodology_versions", m.id, payload.organization_id,
         details={"name": m.name, "version": m.version_label})
    return row(m, M_FIELDS)


@router.get("/methodologies/{methodology_id}")
def get_methodology(methodology_id: uuid.UUID, db: Session = Depends(get_db),
                    user: AuthenticatedUser = Depends(get_current_user)):
    m = _methodology(db, methodology_id)
    items = db.scalars(select(MethodologyItem).where(MethodologyItem.version_id == m.id)
                       .order_by(MethodologyItem.item_type, MethodologyItem.display_order, MethodologyItem.code))
    return {**row(m, M_FIELDS), "can_manage": _can_manage_methodology(db, user, m.organization_id),
            "items": [row(i, ITEM_FIELDS) for i in items]}


@router.post("/methodologies/{methodology_id}/items", summary="Charger les éléments (CSV), en remplacement")
async def upload_items(methodology_id: uuid.UUID, request: Request, file: UploadFile = File(...),
                       db: Session = Depends(get_db), user: AuthenticatedUser = Depends(get_current_user)):
    m = _methodology(db, methodology_id)
    if not _can_manage_methodology(db, user, m.organization_id):
        raise Forbidden("Droits insuffisants sur cette méthodologie.")
    if m.status != "draft":
        raise Conflict("Méthodologie publiée : créez une nouvelle version.")
    data = await file.read()
    if len(data) > 5 * 1024 * 1024:
        raise AuditInvalid("Fichier trop volumineux (5 Mo maximum).")
    try:
        txt, _enc = decode_text(data)
    except (FileRejected, ValueError) as exc:
        raise AuditInvalid(f"Fichier illisible : {exc}") from exc
    rep = meth.parse_rows(list(csv.reader(io.StringIO(txt), delimiter=";")))
    issues = [{"severity": i.severity, "row": i.row, "message": i.message} for i in rep.issues]
    if not rep.ok:
        return {"loaded": 0, "issues": issues}
    db.execute(MethodologyItem.__table__.delete().where(MethodologyItem.version_id == m.id))
    for it in rep.items:
        db.add(MethodologyItem(id=uuid.uuid4(), version_id=m.id, item_type=it.item_type, code=it.code, label=it.label,
                               parent_code=it.parent_code, content=it.content, display_order=it.display_order,
                               source_row=it.source_row))
    db.flush()
    _log(db, request, user.id, "methodology.items_loaded", "methodology_versions", m.id, m.organization_id,
         details={"items": len(rep.items), "filename": file.filename})
    return {"loaded": len(rep.items), "issues": issues}


@router.post("/methodologies/{methodology_id}/{action}", summary="publish | archive")
def methodology_action(methodology_id: uuid.UUID, action: Literal["publish", "archive"], request: Request,
                       db: Session = Depends(get_db), user: AuthenticatedUser = Depends(get_current_user)):
    m = _methodology(db, methodology_id)
    if not _can_manage_methodology(db, user, m.organization_id):
        raise Forbidden("Droits insuffisants sur cette méthodologie.")
    if action == "publish":
        if m.status != "draft":
            raise Conflict("Seule une méthodologie en brouillon peut être publiée.")
        items = [meth.Item(i.item_type, i.code, i.label, i.parent_code, i.content, i.display_order, i.source_row or 0)
                 for i in db.scalars(select(MethodologyItem).where(MethodologyItem.version_id == m.id))]
        errors = [i.message for i in meth.publication_issues(items, m.kind) if i.severity == "error"]
        if errors:
            raise AuditInvalid("Publication impossible : " + " ".join(errors))
        m.status, m.published_at, m.published_by = "published", _now(), user.id
    else:
        if m.status != "published":
            raise Conflict("Seule une méthodologie publiée peut être archivée.")
        m.status = "archived"
    db.flush()
    _log(db, request, user.id, f"methodology.{action}", "methodology_versions", m.id, m.organization_id)
    return row(m, M_FIELDS)


@router.get("/methodology-template.csv", summary="Modèle de fichier de méthodologie (vide, sans contenu normatif)")
def methodology_template():
    body = ";".join(meth.HEADER) + "\n"
    return Response(content=body.encode("utf-8"), media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=modele-methodologie.csv"})


# ======================================================================== registre de l'entité
class ProcessIn(BaseModel):
    code: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=200)
    parent_id: uuid.UUID | None = None
    owner_name: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    is_active: bool = True


class RegistryRiskIn(BaseModel):
    code: str = Field(min_length=1, max_length=40)
    title: str = Field(min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=4000)
    process_id: uuid.UUID | None = None
    cycle_code: str | None = Field(default=None, max_length=40)
    assertion_codes: list[str] = Field(default_factory=list, max_length=20)
    scale_version_id: uuid.UUID | None = None
    inherent_likelihood: int | None = Field(default=None, ge=1)
    inherent_impact: int | None = Field(default=None, ge=1)
    residual_likelihood: int | None = Field(default=None, ge=1)
    residual_impact: int | None = Field(default=None, ge=1)
    status: Literal["active", "retired"] = "active"


def _registry_write(ctx: CompanyContext) -> None:
    if ctx.role.value not in ("org_admin", "auditor"):
        raise Forbidden("Registre des processus et des risques : auditeurs de l'entité et administrateurs.")


def _check_scale(db: Session, version_id: uuid.UUID | None, pairs: list[tuple[int | None, int | None]]) -> None:
    if not any(a is not None or b is not None for a, b in pairs):
        return
    if version_id is None:
        raise AuditInvalid("Indiquez la méthodologie dont la grille sert à coter le risque.")
    scale = next((i.content for i in db.scalars(select(MethodologyItem).where(
        MethodologyItem.version_id == version_id, MethodologyItem.item_type == "risk_scale"))), None)
    if scale is None:
        raise AuditInvalid("La méthodologie choisie ne contient pas de grille de cotation.")
    for a, b in pairs:
        if (a is None) != (b is None):
            raise AuditInvalid("Cotation incomplète : probabilité et impact vont ensemble.")
        try:
            meth.rate(scale, a, b)
        except ValueError as exc:
            raise AuditInvalid(str(exc)) from exc


@router.get("/companies/{company_id}/processes")
def list_processes(ctx: CompanyContext = Depends(get_company_context), db: Session = Depends(get_db)):
    return [row(p, ("id", "code", "name", "parent_id", "owner_name", "description", "is_active"))
            for p in db.scalars(select(Process).where(Process.company_id == ctx.company_id).order_by(Process.code))]


@router.post("/companies/{company_id}/processes", status_code=status.HTTP_201_CREATED)
def create_process(payload: ProcessIn, request: Request, ctx: CompanyContext = Depends(get_company_context),
                   db: Session = Depends(get_db)):
    _registry_write(ctx)
    p = Process(id=uuid.uuid4(), organization_id=ctx.organization_id, company_id=ctx.company_id, created_by=ctx.user.id,
                **payload.model_dump())
    db.add(p)
    db.flush()
    _log(db, request, ctx.user.id, "process.create", "processes", p.id, ctx.organization_id, ctx.company_id, {"code": p.code})
    return row(p, ("id", "code", "name", "parent_id", "owner_name", "description", "is_active"))


RISK_FIELDS = ("id", "code", "title", "description", "process_id", "cycle_code", "assertion_codes", "scale_version_id",
               "inherent_likelihood", "inherent_impact", "residual_likelihood", "residual_impact", "status")


@router.get("/companies/{company_id}/risks", summary="Registre des risques de l'entité")
def list_registry_risks(ctx: CompanyContext = Depends(get_company_context), db: Session = Depends(get_db)):
    return [row(r, RISK_FIELDS) for r in db.scalars(select(Risk).where(Risk.company_id == ctx.company_id).order_by(Risk.code))]


@router.post("/companies/{company_id}/risks", status_code=status.HTTP_201_CREATED)
def create_registry_risk(payload: RegistryRiskIn, request: Request, ctx: CompanyContext = Depends(get_company_context),
                         db: Session = Depends(get_db)):
    _registry_write(ctx)
    _check_scale(db, payload.scale_version_id, [(payload.inherent_likelihood, payload.inherent_impact),
                                                (payload.residual_likelihood, payload.residual_impact)])
    r = Risk(id=uuid.uuid4(), organization_id=ctx.organization_id, company_id=ctx.company_id, created_by=ctx.user.id,
             **payload.model_dump())
    db.add(r)
    db.flush()
    _log(db, request, ctx.user.id, "risk.create", "risks", r.id, ctx.organization_id, ctx.company_id, {"code": r.code})
    return row(r, RISK_FIELDS)


@router.patch("/companies/{company_id}/risks/{risk_id}")
def update_registry_risk(risk_id: uuid.UUID, payload: RegistryRiskIn, request: Request,
                         ctx: CompanyContext = Depends(get_company_context), db: Session = Depends(get_db)):
    _registry_write(ctx)
    r = db.get(Risk, risk_id)
    if r is None or r.company_id != ctx.company_id:
        raise NotFound("Risque introuvable")
    _check_scale(db, payload.scale_version_id, [(payload.inherent_likelihood, payload.inherent_impact),
                                                (payload.residual_likelihood, payload.residual_impact)])
    for k, v in payload.model_dump().items():
        setattr(r, k, v)
    db.flush()
    _log(db, request, ctx.user.id, "risk.update", "risks", r.id, ctx.organization_id, ctx.company_id,
         payload.model_dump(mode="json"))
    return row(r, RISK_FIELDS)


# ======================================================================== missions
TYPE_LABELS = {"statutory_audit": "Audit légal", "contractual_audit": "Audit contractuel",
               "internal_audit": "Audit interne", "ic_assessment": "Évaluation du contrôle interne"}


class EngagementCreate(BaseModel):
    company_id: uuid.UUID
    engagement_type: Literal["statutory_audit", "contractual_audit", "internal_audit", "ic_assessment"]
    reference: str = Field(min_length=1, max_length=60)
    name: str = Field(min_length=1, max_length=200)
    fiscal_year_id: uuid.UUID | None = None
    objectives: str | None = Field(default=None, max_length=8000)
    scope: str | None = Field(default=None, max_length=8000)
    period_start: date | None = None
    period_end: date | None = None
    planned_start: date | None = None
    planned_end: date | None = None
    methodology_version_id: uuid.UUID | None = None


class EngagementUpdate(BaseModel):
    reference: str = Field(min_length=1, max_length=60)
    name: str = Field(min_length=1, max_length=200)
    fiscal_year_id: uuid.UUID | None = None
    objectives: str | None = Field(default=None, max_length=8000)
    scope: str | None = Field(default=None, max_length=8000)
    period_start: date | None = None
    period_end: date | None = None
    planned_start: date | None = None
    planned_end: date | None = None
    methodology_version_id: uuid.UUID | None = None


def _engagement_out(db: Session, e: Engagement, ctx: EngagementContext | None = None) -> dict:
    company = db.get(Company, e.company_id)
    out = {**row(e, svc.ENGAGEMENT_FIELDS), "type_label": TYPE_LABELS[e.engagement_type],
           "status_label": wf.STATUS_LABELS[e.status], "company_name": company.name if company else None}
    if ctx is not None:
        fy = db.get(FiscalYear, e.fiscal_year_id) if e.fiscal_year_id else None
        mv = db.get(MethodologyVersion, e.methodology_version_id) if e.methodology_version_id else None
        out.update(my_role=ctx.role, my_role_label=wf.ROLE_LABELS.get(ctx.role) if ctx.role else None,
                   independent=ctx.independent, is_org_admin=ctx.is_org_admin, capabilities=ctx.caps,
                   next_statuses=wf.next_statuses(e.status, ctx.role) if ctx.independent else [],
                   fiscal_year_label=fy.label if fy else None,
                   methodology=row(mv, ("id", "name", "version_label", "source_reference")) if mv else None,
                   members=svc.members_out(db, e))
    return out


@router.get("/organizations/{org_id}/engagements", summary="Missions visibles de l'organisation")
def list_engagements(ctx: OrgContext = Depends(get_org_context), db: Session = Depends(get_db)):
    es = list(db.scalars(select(Engagement).where(Engagement.organization_id == ctx.organization_id)
                         .order_by(Engagement.created_at.desc())))
    mine = {m.engagement_id: m for m in db.scalars(select(EngagementMember).where(EngagementMember.user_id == ctx.user.id))}
    return [{**_engagement_out(db, e), "my_role": mine[e.id].role if e.id in mine else None,
             "independent": bool(mine[e.id].independence_confirmed_at) if e.id in mine else False} for e in es]


@router.post("/organizations/{org_id}/engagements", status_code=status.HTTP_201_CREATED)
def create_engagement(payload: EngagementCreate, request: Request, ctx: OrgContext = Depends(get_org_context),
                      db: Session = Depends(get_db)):
    company = db.get(Company, payload.company_id)
    if company is None or company.organization_id != ctx.organization_id:
        raise NotFound("Entreprise introuvable")
    role = db.execute(text("SELECT authz.company_role(:c)"), {"c": company.id}).scalar()
    ic_admin = bool(db.execute(text("SELECT authz.ic_admin(:c)"), {"c": company.id}).scalar())
    if role not in ("org_admin", "auditor") and not (payload.engagement_type == "ic_assessment" and ic_admin):
        raise Forbidden("Création de mission : administrateurs de l'organisation ou auditeurs de l'entreprise "
                        "(évaluation du contrôle interne : aussi le responsable du contrôle interne et le DAF).")
    if payload.fiscal_year_id:
        fy = db.get(FiscalYear, payload.fiscal_year_id)
        if fy is None or fy.company_id != company.id:
            raise NotFound("Exercice introuvable")
    e = Engagement(id=uuid.uuid4(), organization_id=ctx.organization_id, created_by=ctx.user.id,
                   **payload.model_dump(exclude={"reference", "name"}), reference=payload.reference.strip(),
                   name=payload.name.strip())
    db.add(e)
    db.flush()      # le trigger ajoute le créateur comme manager
    _log(db, request, ctx.user.id, "engagement.create", "engagements", e.id, ctx.organization_id, company.id,
         {"reference": e.reference, "type": e.engagement_type})
    return _engagement_out(db, e, svc.load_context(db, e.id, ctx.user))


@router.get("/engagements/{engagement_id}")
def get_engagement(ctx: EngagementContext = Depends(get_engagement_context), db: Session = Depends(get_db)):
    return _engagement_out(db, ctx.engagement, ctx)


@router.patch("/engagements/{engagement_id}")
def update_engagement(payload: EngagementUpdate, request: Request,
                      ctx: EngagementContext = Depends(get_engagement_context), db: Session = Depends(get_db)):
    ctx.require("edit_header")
    e = ctx.engagement
    if payload.fiscal_year_id:
        fy = db.get(FiscalYear, payload.fiscal_year_id)
        if fy is None or fy.company_id != e.company_id:
            raise NotFound("Exercice introuvable")
    for k, v in payload.model_dump().items():
        setattr(e, k, v.strip() if isinstance(v, str) and k in ("reference", "name") else v)
    db.flush()
    _elog(db, request, ctx, "engagement.update", "engagements", e.id, payload.model_dump(mode="json"))
    return _engagement_out(db, e, ctx)


class StatusIn(BaseModel):
    to: Literal["planning", "fieldwork", "review", "reporting", "issued", "archived"]
    reopen_reason: str | None = Field(default=None, max_length=2000)


@router.post("/engagements/{engagement_id}/status", summary="Changer de phase (circuit contrôlé par la base)")
def change_status(payload: StatusIn, request: Request, ctx: EngagementContext = Depends(get_engagement_context),
                  db: Session = Depends(get_db)):
    e = ctx.engagement
    if not ctx.independent or payload.to not in wf.next_statuses(e.status, ctx.role):
        raise Forbidden(f"Transition {wf.STATUS_LABELS[e.status]} → {wf.STATUS_LABELS[payload.to]} "
                        "non autorisée pour votre rôle.")
    if payload.to == "issued":
        sup = svc.supervision(db, e)
        failed = [c["label"] for c in sup["issuance_checks"] if not c["passed"]]
        if failed:
            raise Conflict("Émission impossible : " + " ; ".join(failed) + ".")
    prev = e.status
    if payload.reopen_reason is not None:
        e.reopen_reason = payload.reopen_reason
    e.status = payload.to
    db.flush()
    db.refresh(e)
    _elog(db, request, ctx, "engagement.status", "engagements", e.id,
          {"from": prev, "to": e.status, "reopen_reason": payload.reopen_reason})
    return _engagement_out(db, e, svc.load_context(db, e.id, ctx.user))


@router.delete("/engagements/{engagement_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_engagement(request: Request, ctx: EngagementContext = Depends(get_engagement_context),
                      db: Session = Depends(get_db)):
    ctx.require("manage_team")
    e = ctx.engagement
    db.delete(e)
    db.flush()
    _log(db, request, ctx.user.id, "engagement.delete", "engagements", e.id, e.organization_id, e.company_id,
         {"reference": e.reference})
    return Response(status_code=status.HTTP_204_NO_CONTENT)


class IndependenceIn(BaseModel):
    statement: str = Field(min_length=10, max_length=4000)


@router.post("/engagements/{engagement_id}/independence", summary="Confirmer son indépendance (par soi-même)")
def confirm_independence(payload: IndependenceIn, request: Request,
                         ctx: EngagementContext = Depends(get_engagement_context), db: Session = Depends(get_db)):
    if ctx.role is None:
        raise Forbidden("Vous n'êtes pas membre de cette mission.")
    db.execute(text("SELECT public.confirm_independence(:e, :s)"), {"e": ctx.engagement.id, "s": payload.statement})
    _elog(db, request, ctx, "engagement.independence", "engagement_members", ctx.engagement.id, {"role": ctx.role})
    return _engagement_out(db, ctx.engagement, svc.load_context(db, ctx.engagement.id, ctx.user))


class MemberIn(BaseModel):
    user_id: uuid.UUID
    role: Literal["partner", "manager", "in_charge", "staff", "quality_reviewer", "auditee", "observer"]
    planned_hours: Decimal | None = Field(default=None, ge=0, max_digits=8, decimal_places=2)


class MemberUpdate(BaseModel):
    role: Literal["partner", "manager", "in_charge", "staff", "quality_reviewer", "auditee", "observer"]
    planned_hours: Decimal | None = Field(default=None, ge=0, max_digits=8, decimal_places=2)


def _team_write(ctx: EngagementContext) -> None:
    if not (ctx.is_org_admin or "manage_team" in ctx.caps):
        raise Forbidden("Composition de l'équipe : manager ou associé de la mission (indépendance confirmée), "
                        "ou administrateurs de l'organisation.")


@router.post("/engagements/{engagement_id}/members", status_code=status.HTTP_201_CREATED)
def add_member(payload: MemberIn, request: Request, ctx: EngagementContext = Depends(get_engagement_context),
               db: Session = Depends(get_db)):
    _team_write(ctx)
    m = EngagementMember(id=uuid.uuid4(), organization_id=ctx.engagement.organization_id, engagement_id=ctx.engagement.id,
                         user_id=payload.user_id, role=payload.role, planned_hours=payload.planned_hours, added_by=ctx.user.id)
    db.add(m)
    db.flush()
    _elog(db, request, ctx, "engagement.member_added", "engagement_members", m.id,
          {"user_id": str(payload.user_id), "role": payload.role, "self": payload.user_id == ctx.user.id})
    return svc.members_out(db, ctx.engagement)


@router.patch("/engagements/{engagement_id}/members/{member_id}")
def update_member(member_id: uuid.UUID, payload: MemberUpdate, request: Request,
                  ctx: EngagementContext = Depends(get_engagement_context), db: Session = Depends(get_db)):
    _team_write(ctx)
    m = owned(db, ctx, EngagementMember, member_id, "Membre")
    prev = m.role
    m.role, m.planned_hours = payload.role, payload.planned_hours
    db.flush()
    _elog(db, request, ctx, "engagement.member_updated", "engagement_members", m.id, {"from": prev, "to": payload.role})
    return svc.members_out(db, ctx.engagement)


@router.delete("/engagements/{engagement_id}/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(member_id: uuid.UUID, request: Request, ctx: EngagementContext = Depends(get_engagement_context),
                  db: Session = Depends(get_db)):
    _team_write(ctx)
    m = owned(db, ctx, EngagementMember, member_id, "Membre")
    leads = db.scalar(select(func.count()).select_from(EngagementMember).where(
        EngagementMember.engagement_id == ctx.engagement.id, EngagementMember.role.in_(("partner", "manager"))))
    if m.role in ("partner", "manager") and leads <= 1:
        raise Conflict("La mission doit conserver au moins un manager ou un associé.")
    db.delete(m)
    db.flush()
    _elog(db, request, ctx, "engagement.member_removed", "engagement_members", member_id, {"user_id": str(m.user_id)})
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/engagements/{engagement_id}/candidates", summary="Membres de l'organisation pouvant rejoindre l'équipe")
def candidates(ctx: EngagementContext = Depends(get_engagement_context), db: Session = Depends(get_db)):
    _team_write(ctx)
    rows = db.execute(text("""SELECT p.id, p.email, p.full_name FROM public.organization_members om
                              JOIN public.profiles p ON p.id = om.user_id
                              WHERE om.organization_id = :o AND om.user_id NOT IN
                                (SELECT user_id FROM public.engagement_members WHERE engagement_id = :e)
                              ORDER BY coalesce(p.full_name, p.email)"""),
                      {"o": ctx.engagement.organization_id, "e": ctx.engagement.id}).all()
    return [{"id": str(r.id), "email": r.email, "full_name": r.full_name} for r in rows]


@router.get("/engagements/{engagement_id}/supervision", summary="Avancement, couverture des risques, conditions d'émission")
def supervision(ctx: EngagementContext = Depends(get_engagement_context), db: Session = Depends(get_db)):
    ctx.require("read_dossier")
    return {**svc.supervision(db, ctx.engagement),
            "engagement_signoffs": svc.signoffs_for(db, "engagement", ctx.engagement.id)}


@router.get("/engagements/{engagement_id}/methodology-items")
def engagement_methodology(item_type: str | None = None, ctx: EngagementContext = Depends(get_engagement_context),
                           db: Session = Depends(get_db)):
    ctx.require("read_dossier")
    return [row(i, ITEM_FIELDS) for i in svc.methodology_items(db, ctx.engagement, item_type)]


# ======================================================================== risques de la mission
class EngagementRiskIn(BaseModel):
    code: str = Field(min_length=1, max_length=40)
    title: str = Field(min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=4000)
    cycle_code: str | None = Field(default=None, max_length=40)
    assertion_codes: list[str] = Field(default_factory=list, max_length=20)
    likelihood: int | None = Field(default=None, ge=1)
    impact: int | None = Field(default=None, ge=1)
    is_significant: bool = False
    planned_response: str | None = Field(default=None, max_length=4000)
    risk_id: uuid.UUID | None = None


ER_FIELDS = ("id", "risk_id", "code", "title", "description", "cycle_code", "assertion_codes", "likelihood", "impact",
             "is_significant", "planned_response", "origin", "ai_suggestion_id", "created_at")


def _validate_er(db: Session, ctx: EngagementContext, p: EngagementRiskIn) -> None:
    e = ctx.engagement
    if p.likelihood is not None or p.impact is not None:
        scale = svc.risk_scale(db, e)
        if scale is None:
            raise AuditInvalid("La mission n'a pas de méthodologie avec grille de cotation : choisissez-en une pour coter.")
        try:
            meth.rate(scale, p.likelihood, p.impact)
        except ValueError as exc:
            raise AuditInvalid(str(exc)) from exc
    if e.methodology_version_id:
        known = {i.code for i in svc.methodology_items(db, e, "assertion")}
        unknown = [a for a in p.assertion_codes if a not in known]
        if unknown:
            raise AuditInvalid(f"Assertions absentes de la méthodologie : {', '.join(unknown)}.")
        if p.cycle_code and p.cycle_code not in {i.code for i in svc.methodology_items(db, e, "cycle")}:
            raise AuditInvalid(f"Cycle « {p.cycle_code} » absent de la méthodologie.")
    if p.risk_id:
        r = db.get(Risk, p.risk_id)
        if r is None or r.company_id != e.company_id:
            raise NotFound("Risque du registre introuvable")


def _er_out(db: Session, e: Engagement, risks: list[EngagementRisk]) -> list[dict]:
    scale = svc.risk_scale(db, e)
    cov: dict[uuid.UUID, int] = {}
    for link in db.scalars(select(ProcedureRisk).where(ProcedureRisk.engagement_id == e.id)):
        cov[link.engagement_risk_id] = cov.get(link.engagement_risk_id, 0) + 1
    out = []
    for r in risks:
        try:
            rating = meth.rate(scale, r.likelihood, r.impact) if scale else {"score": None, "significant": None}
        except ValueError:
            rating = {"score": None, "significant": None}
        out.append({**row(r, ER_FIELDS), "score": rating["score"], "scale_significant": rating["significant"],
                    "procedures": cov.get(r.id, 0)})
    return out


@router.get("/engagements/{engagement_id}/risks")
def list_er(ctx: EngagementContext = Depends(get_engagement_context), db: Session = Depends(get_db)):
    ctx.require("read_dossier")
    rs = list(db.scalars(select(EngagementRisk).where(EngagementRisk.engagement_id == ctx.engagement.id)
                         .order_by(EngagementRisk.code)))
    return {"risks": _er_out(db, ctx.engagement, rs), "scale": svc.risk_scale(db, ctx.engagement)}


@router.post("/engagements/{engagement_id}/risks", status_code=status.HTTP_201_CREATED)
def create_er(payload: EngagementRiskIn, request: Request, ctx: EngagementContext = Depends(get_engagement_context),
              db: Session = Depends(get_db)):
    ctx.require("plan")
    _validate_er(db, ctx, payload)
    r = EngagementRisk(id=uuid.uuid4(), organization_id=ctx.engagement.organization_id, engagement_id=ctx.engagement.id,
                       created_by=ctx.user.id, origin="registry" if payload.risk_id else "manual", **payload.model_dump())
    db.add(r)
    db.flush()
    _elog(db, request, ctx, "engagement_risk.create", "engagement_risks", r.id, {"code": r.code})
    return _er_out(db, ctx.engagement, [r])[0]


@router.patch("/engagements/{engagement_id}/risks/{risk_id}")
def update_er(risk_id: uuid.UUID, payload: EngagementRiskIn, request: Request,
              ctx: EngagementContext = Depends(get_engagement_context), db: Session = Depends(get_db)):
    ctx.require("plan")
    r = owned(db, ctx, EngagementRisk, risk_id, "Risque")
    _validate_er(db, ctx, payload)
    for k, v in payload.model_dump().items():
        setattr(r, k, v)
    db.flush()
    _elog(db, request, ctx, "engagement_risk.update", "engagement_risks", r.id, payload.model_dump(mode="json"))
    return _er_out(db, ctx.engagement, [r])[0]


@router.delete("/engagements/{engagement_id}/risks/{risk_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_er(risk_id: uuid.UUID, request: Request, ctx: EngagementContext = Depends(get_engagement_context),
              db: Session = Depends(get_db)):
    ctx.require("plan")
    r = owned(db, ctx, EngagementRisk, risk_id, "Risque")
    db.delete(r)
    db.flush()
    _elog(db, request, ctx, "engagement_risk.delete", "engagement_risks", risk_id, {"code": r.code})
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ======================================================================== programmes et procédures
class ProgramIn(BaseModel):
    code: str = Field(min_length=1, max_length=40)
    title: str = Field(min_length=1, max_length=300)
    cycle_code: str | None = Field(default=None, max_length=40)
    objective: str | None = Field(default=None, max_length=4000)
    display_order: int = 0


class ProcedureIn(BaseModel):
    program_id: uuid.UUID
    code: str = Field(min_length=1, max_length=40)
    title: str = Field(min_length=1, max_length=300)
    objective: str | None = Field(default=None, max_length=4000)
    nature: Literal["control_test", "analytical", "detail_test", "inquiry", "observation", "inspection", "confirmation",
                    "recalculation", "other"]
    steps: list[str] = Field(default_factory=list, max_length=100)
    assertion_codes: list[str] = Field(default_factory=list, max_length=20)
    assigned_to: uuid.UUID | None = None
    due_date: date | None = None
    status: Literal["not_started", "in_progress", "done", "not_applicable"] = "not_started"
    na_reason: str | None = Field(default=None, max_length=2000)
    risk_ids: list[uuid.UUID] = Field(default_factory=list, max_length=100)
    display_order: int = 0


class FromTemplatesIn(BaseModel):
    program_id: uuid.UUID
    template_codes: list[str] = Field(min_length=1, max_length=200)


PG_FIELDS = ("id", "code", "title", "cycle_code", "objective", "display_order")
PR_FIELDS = ("id", "program_id", "code", "title", "objective", "nature", "steps", "assertion_codes", "template_item_id",
             "assigned_to", "due_date", "status", "na_reason", "origin", "ai_suggestion_id", "display_order")


@router.get("/engagements/{engagement_id}/programs", summary="Programmes de travail et procédures")
def list_programs(ctx: EngagementContext = Depends(get_engagement_context), db: Session = Depends(get_db)):
    ctx.require("read_dossier")
    e = ctx.engagement
    links: dict[uuid.UUID, list[str]] = {}
    for link in db.scalars(select(ProcedureRisk).where(ProcedureRisk.engagement_id == e.id)):
        links.setdefault(link.procedure_id, []).append(str(link.engagement_risk_id))
    wps: dict[uuid.UUID, list[dict]] = {}
    for w in db.scalars(select(Workpaper).where(Workpaper.engagement_id == e.id, Workpaper.procedure_id.is_not(None))):
        wps.setdefault(w.procedure_id, []).append(row(w, ("id", "reference", "title", "status")))
    procs = list(db.scalars(select(Procedure).where(Procedure.engagement_id == e.id)
                            .order_by(Procedure.display_order, Procedure.code)))
    return [{**row(pg, PG_FIELDS), "procedures": [{**row(p, PR_FIELDS), "risk_ids": links.get(p.id, []),
                                                    "workpapers": wps.get(p.id, [])}
                                                   for p in procs if p.program_id == pg.id]}
            for pg in db.scalars(select(WorkProgram).where(WorkProgram.engagement_id == e.id)
                                 .order_by(WorkProgram.display_order, WorkProgram.code))]


@router.post("/engagements/{engagement_id}/programs", status_code=status.HTTP_201_CREATED)
def create_program(payload: ProgramIn, request: Request, ctx: EngagementContext = Depends(get_engagement_context),
                   db: Session = Depends(get_db)):
    ctx.require("plan")
    pg = WorkProgram(id=uuid.uuid4(), organization_id=ctx.engagement.organization_id, engagement_id=ctx.engagement.id,
                     **payload.model_dump())
    db.add(pg)
    db.flush()
    _elog(db, request, ctx, "work_program.create", "work_programs", pg.id, {"code": pg.code})
    return row(pg, PG_FIELDS)


@router.delete("/engagements/{engagement_id}/programs/{program_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_program(program_id: uuid.UUID, request: Request, ctx: EngagementContext = Depends(get_engagement_context),
                   db: Session = Depends(get_db)):
    ctx.require("plan")
    pg = owned(db, ctx, WorkProgram, program_id, "Programme")
    if db.scalar(select(func.count()).select_from(Workpaper).join(Procedure, Procedure.id == Workpaper.procedure_id)
                 .where(Procedure.program_id == pg.id)):
        raise Conflict("Des feuilles de travail sont rattachées aux procédures de ce programme.")
    db.delete(pg)
    db.flush()
    _elog(db, request, ctx, "work_program.delete", "work_programs", program_id, {"code": pg.code})
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _set_procedure_risks(db: Session, ctx: EngagementContext, proc: Procedure, risk_ids: list[uuid.UUID]) -> None:
    for rid in risk_ids:
        owned(db, ctx, EngagementRisk, rid, "Risque")
    db.execute(ProcedureRisk.__table__.delete().where(ProcedureRisk.procedure_id == proc.id))
    for rid in dict.fromkeys(risk_ids):
        db.add(ProcedureRisk(procedure_id=proc.id, engagement_risk_id=rid, engagement_id=ctx.engagement.id))


def _check_assertions(db: Session, e: Engagement, codes: list[str]) -> None:
    if e.methodology_version_id and codes:
        known = {i.code for i in svc.methodology_items(db, e, "assertion")}
        unknown = [a for a in codes if a not in known]
        if unknown:
            raise AuditInvalid(f"Assertions absentes de la méthodologie : {', '.join(unknown)}.")


@router.post("/engagements/{engagement_id}/procedures", status_code=status.HTTP_201_CREATED)
def create_procedure(payload: ProcedureIn, request: Request, ctx: EngagementContext = Depends(get_engagement_context),
                     db: Session = Depends(get_db)):
    ctx.require("plan")
    owned(db, ctx, WorkProgram, payload.program_id, "Programme")
    _check_assertions(db, ctx.engagement, payload.assertion_codes)
    p = Procedure(id=uuid.uuid4(), organization_id=ctx.engagement.organization_id, engagement_id=ctx.engagement.id,
                  **payload.model_dump(exclude={"risk_ids"}))
    db.add(p)
    db.flush()
    _set_procedure_risks(db, ctx, p, payload.risk_ids)
    db.flush()
    _elog(db, request, ctx, "procedure.create", "procedures", p.id, {"code": p.code})
    return row(p, PR_FIELDS)


@router.patch("/engagements/{engagement_id}/procedures/{procedure_id}")
def update_procedure(procedure_id: uuid.UUID, payload: ProcedureIn, request: Request,
                     ctx: EngagementContext = Depends(get_engagement_context), db: Session = Depends(get_db)):
    p = owned(db, ctx, Procedure, procedure_id, "Procédure")
    planning_fields = ("program_id", "code", "title", "objective", "nature", "steps", "assertion_codes", "assigned_to",
                       "due_date", "display_order")
    changes_plan = any(getattr(p, f) != v for f, v in payload.model_dump(include=set(planning_fields)).items())
    current_risks = {link.engagement_risk_id
                     for link in db.scalars(select(ProcedureRisk).where(ProcedureRisk.procedure_id == p.id))}
    if changes_plan or set(payload.risk_ids) != current_risks:
        ctx.require("plan")
    else:   # exécution : statut et motif « non applicable »
        ctx.require("edit_procedures")
    owned(db, ctx, WorkProgram, payload.program_id, "Programme")
    _check_assertions(db, ctx.engagement, payload.assertion_codes)
    for k, v in payload.model_dump(exclude={"risk_ids"}).items():
        setattr(p, k, v)
    _set_procedure_risks(db, ctx, p, payload.risk_ids)
    db.flush()
    _elog(db, request, ctx, "procedure.update", "procedures", p.id, {"status": p.status})
    return row(p, PR_FIELDS)


@router.delete("/engagements/{engagement_id}/procedures/{procedure_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_procedure(procedure_id: uuid.UUID, request: Request, ctx: EngagementContext = Depends(get_engagement_context),
                     db: Session = Depends(get_db)):
    ctx.require("plan")
    p = owned(db, ctx, Procedure, procedure_id, "Procédure")
    if db.scalar(select(func.count()).select_from(Workpaper).where(Workpaper.procedure_id == p.id)):
        raise Conflict("Des feuilles de travail sont rattachées à cette procédure.")
    db.delete(p)
    db.flush()
    _elog(db, request, ctx, "procedure.delete", "procedures", procedure_id, {"code": p.code})
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/engagements/{engagement_id}/procedures/from-templates", status_code=status.HTTP_201_CREATED,
             summary="Créer des procédures à partir des programmes types de la méthodologie")
def procedures_from_templates(payload: FromTemplatesIn, request: Request,
                              ctx: EngagementContext = Depends(get_engagement_context), db: Session = Depends(get_db)):
    ctx.require("plan")
    owned(db, ctx, WorkProgram, payload.program_id, "Programme")
    templates = {i.code: i for i in svc.methodology_items(db, ctx.engagement, "procedure_template")}
    missing = [c for c in payload.template_codes if c not in templates]
    if missing:
        raise AuditInvalid(f"Programmes types absents de la méthodologie de la mission : {', '.join(missing)}.")
    existing = {c for (c,) in db.execute(select(Procedure.code).where(Procedure.engagement_id == ctx.engagement.id))}
    created = []
    for code in payload.template_codes:
        t = templates[code]
        if code in existing:
            continue
        p = Procedure(id=uuid.uuid4(), organization_id=ctx.engagement.organization_id, engagement_id=ctx.engagement.id,
                      program_id=payload.program_id, code=code, title=t.label, objective=t.content.get("objective"),
                      nature=t.content.get("nature", "other"), steps=t.content.get("steps", []),
                      assertion_codes=t.content.get("assertions", []), template_item_id=t.id, origin="template",
                      display_order=t.display_order)
        db.add(p)
        created.append(code)
    db.flush()
    _elog(db, request, ctx, "procedure.from_templates", "work_programs", payload.program_id, {"codes": created})
    return {"created": created, "skipped": [c for c in payload.template_codes if c not in created]}


# ======================================================================== feuilles de travail
class WorkpaperIn(BaseModel):
    reference: str = Field(min_length=1, max_length=40)
    title: str = Field(min_length=1, max_length=300)
    procedure_id: uuid.UUID | None = None
    objective: str | None = Field(default=None, max_length=8000)
    work_performed: str | None = Field(default=None, max_length=100000)
    conclusion: str | None = Field(default=None, max_length=20000)
    content: dict = Field(default_factory=dict)


WP_FIELDS = ("id", "procedure_id", "reference", "title", "objective", "work_performed", "conclusion", "content", "status",
             "version", "content_hash", "origin", "created_by", "updated_by", "created_at", "updated_at")


def _wp_detail(db: Session, w: Workpaper) -> dict:
    links = list(db.scalars(select(EvidenceLink).where(EvidenceLink.object_type == "workpaper", EvidenceLink.object_id == w.id)))
    ev = ({e.id: e for e in db.scalars(select(EvidenceItem).where(EvidenceItem.id.in_([lk.evidence_id for lk in links])))}
          if links else {})
    notes = list(db.scalars(select(ReviewNote).where(ReviewNote.object_type == "workpaper", ReviewNote.object_id == w.id)
                            .order_by(ReviewNote.created_at)))
    ppl = svc.people(db, [w.created_by, w.updated_by] + [n.author_id for n in notes] + [n.responded_by for n in notes])
    return {**row(w, WP_FIELDS), "signoffs": svc.signoffs_for(db, "workpaper", w.id),
            "evidence": [{**row(ev[lk.evidence_id], ("id", "title", "kind", "sha256", "original_filename")),
                          "link_id": str(lk.id)}
                         for lk in links if lk.evidence_id in ev],
            "review_notes": [{**row(n, NOTE_FIELDS), "author": ppl.get(str(n.author_id))} for n in notes],
            "created_by_user": ppl.get(str(w.created_by)), "updated_by_user": ppl.get(str(w.updated_by))}


@router.get("/engagements/{engagement_id}/workpapers")
def list_workpapers(ctx: EngagementContext = Depends(get_engagement_context), db: Session = Depends(get_db)):
    ctx.require("read_dossier")
    wps = list(db.scalars(select(Workpaper).where(Workpaper.engagement_id == ctx.engagement.id).order_by(Workpaper.reference)))
    open_notes = dict(db.execute(select(ReviewNote.object_id, func.count()).where(
        ReviewNote.engagement_id == ctx.engagement.id, ReviewNote.object_type == "workpaper",
        ReviewNote.status != "closed").group_by(ReviewNote.object_id)).all())
    return [{**row(w, ("id", "procedure_id", "reference", "title", "status", "version", "updated_at")),
             "open_notes": open_notes.get(w.id, 0)} for w in wps]


@router.post("/engagements/{engagement_id}/workpapers", status_code=status.HTTP_201_CREATED)
def create_workpaper(payload: WorkpaperIn, request: Request, ctx: EngagementContext = Depends(get_engagement_context),
                     db: Session = Depends(get_db)):
    ctx.require("edit_workpapers")
    if payload.procedure_id:
        owned(db, ctx, Procedure, payload.procedure_id, "Procédure")
    w = Workpaper(id=uuid.uuid4(), organization_id=ctx.engagement.organization_id, engagement_id=ctx.engagement.id,
                  created_by=ctx.user.id, updated_by=ctx.user.id, **payload.model_dump())
    db.add(w)
    db.flush()
    db.refresh(w)
    _elog(db, request, ctx, "workpaper.create", "workpapers", w.id, {"reference": w.reference})
    return _wp_detail(db, w)


@router.get("/engagements/{engagement_id}/workpapers/{workpaper_id}")
def get_workpaper(workpaper_id: uuid.UUID, ctx: EngagementContext = Depends(get_engagement_context),
                  db: Session = Depends(get_db)):
    ctx.require("read_dossier")
    return _wp_detail(db, owned(db, ctx, Workpaper, workpaper_id, "Feuille"))


@router.patch("/engagements/{engagement_id}/workpapers/{workpaper_id}",
              summary="Modifier (toute modification d'une feuille signée révoque ses signatures)")
def update_workpaper(workpaper_id: uuid.UUID, payload: WorkpaperIn, request: Request,
                     ctx: EngagementContext = Depends(get_engagement_context), db: Session = Depends(get_db)):
    ctx.require("edit_workpapers")
    w = owned(db, ctx, Workpaper, workpaper_id, "Feuille")
    if payload.procedure_id:
        owned(db, ctx, Procedure, payload.procedure_id, "Procédure")
    was = w.status
    for k, v in payload.model_dump().items():
        setattr(w, k, v)
    w.updated_by = ctx.user.id
    db.flush()
    db.refresh(w)
    _elog(db, request, ctx, "workpaper.update", "workpapers", w.id,
          {"version": w.version, "signatures_revoked": was != "draft" and w.status == "draft"})
    return _wp_detail(db, w)


@router.delete("/engagements/{engagement_id}/workpapers/{workpaper_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_workpaper(workpaper_id: uuid.UUID, request: Request, ctx: EngagementContext = Depends(get_engagement_context),
                     db: Session = Depends(get_db)):
    ctx.require("edit_workpapers")
    w = owned(db, ctx, Workpaper, workpaper_id, "Feuille")
    db.delete(w)
    db.flush()
    _elog(db, request, ctx, "workpaper.delete", "workpapers", workpaper_id, {"reference": w.reference})
    return Response(status_code=status.HTTP_204_NO_CONTENT)


class SignIn(BaseModel):
    role: Literal["preparer", "reviewer", "approver", "quality_reviewer"]


@router.post("/engagements/{engagement_id}/workpapers/{workpaper_id}/sign", summary="Signer une feuille")
def sign_workpaper(workpaper_id: uuid.UUID, payload: SignIn, request: Request,
                   ctx: EngagementContext = Depends(get_engagement_context), db: Session = Depends(get_db)):
    ctx.require({"preparer": "sign_preparer", "reviewer": "sign_reviewer", "approver": "sign_approver",
                 "quality_reviewer": "sign_quality"}[payload.role])
    w = owned(db, ctx, Workpaper, workpaper_id, "Feuille")
    s = Signoff(id=uuid.uuid4(), organization_id=ctx.engagement.organization_id, engagement_id=ctx.engagement.id,
                object_type="workpaper", object_id=w.id, signoff_role=payload.role, user_id=ctx.user.id,
                member_role="(base)", content_hash="(base)")
    db.add(s)
    db.flush()      # les règles (ordre, séparation des tâches, notes ouvertes) sont vérifiées par la base
    db.refresh(w)
    _elog(db, request, ctx, f"signoff.{payload.role}", "workpapers", w.id, {"version": w.version, "hash": w.content_hash})
    return _wp_detail(db, w)


class RevokeIn(BaseModel):
    reason: str = Field(min_length=3, max_length=2000)


@router.post("/engagements/{engagement_id}/signoffs/{signoff_id}/revoke", summary="Révoquer une signature (motivé)")
def revoke_signoff(signoff_id: uuid.UUID, payload: RevokeIn, request: Request,
                   ctx: EngagementContext = Depends(get_engagement_context), db: Session = Depends(get_db)):
    ctx.require("read_dossier")
    s = owned(db, ctx, Signoff, signoff_id, "Signature")
    if s.revoked_at is not None:
        raise Conflict("Signature déjà révoquée.")
    s.revoked_at, s.revoked_reason = _now(), payload.reason
    db.flush()
    _elog(db, request, ctx, "signoff.revoke", "signoffs", s.id, {"role": s.signoff_role, "reason": payload.reason})
    return {"revoked": str(s.id)}


class EngagementSignIn(BaseModel):
    role: Literal["quality_reviewer", "approver"]


@router.post("/engagements/{engagement_id}/sign", summary="Revue qualité ou approbation de la mission (phase de rapport)")
def sign_engagement(payload: EngagementSignIn, request: Request, ctx: EngagementContext = Depends(get_engagement_context),
                    db: Session = Depends(get_db)):
    ctx.require("sign_quality" if payload.role == "quality_reviewer" else "approve_engagement")
    s = Signoff(id=uuid.uuid4(), organization_id=ctx.engagement.organization_id, engagement_id=ctx.engagement.id,
                object_type="engagement", object_id=ctx.engagement.id, signoff_role=payload.role, user_id=ctx.user.id,
                member_role="(base)", content_hash="(base)")
    db.add(s)
    db.flush()
    _elog(db, request, ctx, f"engagement.sign_{payload.role}", "engagements", ctx.engagement.id)
    return svc.signoffs_for(db, "engagement", ctx.engagement.id)


# ======================================================================== éléments probants
EV_FIELDS = ("id", "kind", "title", "description", "source", "obtained_on", "original_filename", "mime_type", "size_bytes",
             "sha256", "snapshot_ref", "uploaded_by", "created_at")


def _evidence_out(db: Session, items: list[EvidenceItem]) -> list[dict]:
    if not items:
        return []
    links: dict[uuid.UUID, list[dict]] = {}
    for lk in db.scalars(select(EvidenceLink).where(EvidenceLink.evidence_id.in_([i.id for i in items]))):
        links.setdefault(lk.evidence_id, []).append(row(lk, ("id", "object_type", "object_id")))
    ppl = svc.people(db, [i.uploaded_by for i in items])
    return [{**row(i, EV_FIELDS), "links": links.get(i.id, []), "uploaded_by_user": ppl.get(str(i.uploaded_by))} for i in items]


@router.get("/engagements/{engagement_id}/evidence")
def list_evidence(ctx: EngagementContext = Depends(get_engagement_context), db: Session = Depends(get_db)):
    ctx.require("read_dossier")
    return _evidence_out(db, list(db.scalars(select(EvidenceItem).where(EvidenceItem.engagement_id == ctx.engagement.id)
                                             .order_by(EvidenceItem.created_at.desc()))))


@router.post("/engagements/{engagement_id}/evidence", status_code=status.HTTP_201_CREATED,
             summary="Déposer un fichier (original immuable, empreinte SHA-256)")
async def upload_evidence(request: Request, file: UploadFile = File(...), title: str = Form(..., max_length=300),
                          description: str | None = Form(None, max_length=4000),
                          source: Literal["auditor", "auditee", "third_party"] = Form("auditor"),
                          obtained_on: date | None = Form(None),
                          ctx: EngagementContext = Depends(get_engagement_context), db: Session = Depends(get_db)):
    ctx.require("add_evidence")
    data = await file.read()
    try:
        vf = validate_evidence(file.filename or "fichier", data)
    except FileRejected as exc:
        raise AuditInvalid(str(exc)) from exc
    eid = uuid.uuid4()
    name = safe_filename(file.filename or f"fichier.{vf.extension}")
    path = f"{ctx.engagement.organization_id}/{ctx.engagement.id}/{eid}_{name}"
    item = EvidenceItem(id=eid, organization_id=ctx.engagement.organization_id, engagement_id=ctx.engagement.id, kind="file",
                        title=title.strip() or name, description=description, source=source,
                        obtained_on=obtained_on or date.today(), storage_path=path, original_filename=name,
                        mime_type=vf.mime_type, size_bytes=vf.size_bytes, sha256=vf.sha256, uploaded_by=ctx.user.id)
    db.add(item)
    db.flush()          # contrôles de la base (mission ouverte, déposant authentifié) avant le stockage
    get_storage().upload(EVIDENCE_BUCKET, path, data, vf.mime_type)
    _elog(db, request, ctx, "evidence.upload", "evidence_items", eid, {"sha256": vf.sha256, "filename": name})
    return _evidence_out(db, [item])[0]


class SnapshotIn(BaseModel):
    title: str = Field(default="Balance validée de l'exercice", min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=4000)


@router.post("/engagements/{engagement_id}/evidence/balance-snapshot", status_code=status.HTTP_201_CREATED,
             summary="Figer la balance validée de l'exercice comme élément probant")
def snapshot_balance(payload: SnapshotIn, request: Request, ctx: EngagementContext = Depends(get_engagement_context),
                     db: Session = Depends(get_db)):
    ctx.require("add_evidence")
    snap, ref, digest = svc.balance_snapshot(db, ctx.engagement)
    item = EvidenceItem(id=uuid.uuid4(), organization_id=ctx.engagement.organization_id, engagement_id=ctx.engagement.id,
                        kind="snapshot", title=payload.title, description=payload.description, source="platform",
                        obtained_on=date.today(), snapshot=snap, snapshot_ref=ref, sha256=digest, uploaded_by=ctx.user.id)
    db.add(item)
    db.flush()
    _elog(db, request, ctx, "evidence.snapshot", "evidence_items", item.id, {**ref, "sha256": digest})
    return _evidence_out(db, [item])[0]


@router.get("/engagements/{engagement_id}/evidence/{evidence_id}/download", summary="Lien de téléchargement signé (5 min)")
def download_evidence(evidence_id: uuid.UUID, request: Request, ctx: EngagementContext = Depends(get_engagement_context),
                      db: Session = Depends(get_db)):
    ctx.require("read_dossier")
    item = owned(db, ctx, EvidenceItem, evidence_id, "Élément probant")
    _elog(db, request, ctx, "evidence.download", "evidence_items", item.id, {"sha256": item.sha256})
    if item.kind == "snapshot":
        return {"kind": "snapshot", "snapshot": item.snapshot, "sha256": item.sha256}
    return {"kind": "file", "url": get_storage().signed_url(EVIDENCE_BUCKET, item.storage_path,
                                                             download_name=item.original_filename),
            "sha256": item.sha256}


@router.delete("/engagements/{engagement_id}/evidence/{evidence_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_evidence(evidence_id: uuid.UUID, request: Request, ctx: EngagementContext = Depends(get_engagement_context),
                    db: Session = Depends(get_db)):
    ctx.require("add_evidence")
    item = owned(db, ctx, EvidenceItem, evidence_id, "Élément probant")
    if item.uploaded_by != ctx.user.id and ctx.role not in ("partner", "manager"):
        raise Forbidden("Suppression : par le déposant, le manager ou l'associé.")
    db.delete(item)
    db.flush()
    # l'original reste dans le stockage (immuable) ; seule la référence au dossier est retirée, et journalisée
    _elog(db, request, ctx, "evidence.delete", "evidence_items", evidence_id,
          {"sha256": item.sha256, "storage_path": item.storage_path})
    return Response(status_code=status.HTTP_204_NO_CONTENT)


class LinkIn(BaseModel):
    object_type: Literal["workpaper", "procedure", "engagement_risk", "control_test", "control_test_item", "ic_assessment"]
    object_id: uuid.UUID


LINK_MODELS = {"workpaper": (Workpaper, "Feuille"), "procedure": (Procedure, "Procédure"),
               "engagement_risk": (EngagementRisk, "Risque"), "control_test": (ControlTest, "Test de contrôle"),
               "control_test_item": (ControlTestItem, "Élément testé"), "ic_assessment": (IcAssessment, "Évaluation")}


@router.post("/engagements/{engagement_id}/evidence/{evidence_id}/links", status_code=status.HTTP_201_CREATED)
def link_evidence(evidence_id: uuid.UUID, payload: LinkIn, request: Request,
                  ctx: EngagementContext = Depends(get_engagement_context), db: Session = Depends(get_db)):
    ctx.require("add_evidence")
    owned(db, ctx, EvidenceItem, evidence_id, "Élément probant")
    model, what = LINK_MODELS[payload.object_type]
    owned(db, ctx, model, payload.object_id, what)
    lk = EvidenceLink(id=uuid.uuid4(), engagement_id=ctx.engagement.id, evidence_id=evidence_id,
                      object_type=payload.object_type, object_id=payload.object_id, created_by=ctx.user.id)
    db.add(lk)
    db.flush()
    _elog(db, request, ctx, "evidence.link", "evidence_links", lk.id, payload.model_dump(mode="json"))
    return row(lk, ("id", "object_type", "object_id"))


@router.delete("/engagements/{engagement_id}/evidence-links/{link_id}", status_code=status.HTTP_204_NO_CONTENT)
def unlink_evidence(link_id: uuid.UUID, request: Request, ctx: EngagementContext = Depends(get_engagement_context),
                    db: Session = Depends(get_db)):
    ctx.require("add_evidence")
    lk = owned(db, ctx, EvidenceLink, link_id, "Lien")
    db.delete(lk)
    db.flush()
    _elog(db, request, ctx, "evidence.unlink", "evidence_links", link_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ======================================================================== notes de revue
NOTE_FIELDS = ("id", "object_type", "object_id", "body", "author_id", "assigned_to", "status", "response", "responded_by",
               "responded_at", "closed_by", "closed_at", "created_at")


class NoteIn(BaseModel):
    object_type: Literal["engagement", "workpaper", "procedure", "engagement_risk", "control_test", "ic_assessment"]
    object_id: uuid.UUID
    body: str = Field(min_length=1, max_length=8000)
    assigned_to: uuid.UUID | None = None


class NoteAction(BaseModel):
    action: Literal["answer", "close", "reopen"]
    response: str | None = Field(default=None, max_length=8000)


@router.get("/engagements/{engagement_id}/review-notes")
def list_notes(status_filter: Literal["open", "answered", "closed", "all"] = "all",
               ctx: EngagementContext = Depends(get_engagement_context), db: Session = Depends(get_db)):
    ctx.require("read_dossier")
    q = select(ReviewNote).where(ReviewNote.engagement_id == ctx.engagement.id)
    if status_filter != "all":
        q = q.where(ReviewNote.status == status_filter)
    notes = list(db.scalars(q.order_by(ReviewNote.created_at.desc())))
    ppl = svc.people(db, [n.author_id for n in notes] + [n.assigned_to for n in notes] + [n.responded_by for n in notes])
    refs = {w.id: w.reference for w in db.scalars(select(Workpaper).where(Workpaper.engagement_id == ctx.engagement.id))}
    return [{**row(n, NOTE_FIELDS), "author": ppl.get(str(n.author_id)), "assignee": ppl.get(str(n.assigned_to)),
             "object_label": refs.get(n.object_id) if n.object_type == "workpaper" else None} for n in notes]


@router.post("/engagements/{engagement_id}/review-notes", status_code=status.HTTP_201_CREATED)
def create_note(payload: NoteIn, request: Request, ctx: EngagementContext = Depends(get_engagement_context),
                db: Session = Depends(get_db)):
    ctx.require("write_review_notes")
    if payload.object_type == "engagement":
        if payload.object_id != ctx.engagement.id:
            raise NotFound("Objet introuvable")
    else:
        model, what = LINK_MODELS[payload.object_type]
        owned(db, ctx, model, payload.object_id, what)
    n = ReviewNote(id=uuid.uuid4(), organization_id=ctx.engagement.organization_id, engagement_id=ctx.engagement.id,
                   author_id=ctx.user.id, **payload.model_dump())
    db.add(n)
    db.flush()
    _elog(db, request, ctx, "review_note.create", "review_notes", n.id, {"object": payload.object_type})
    return row(n, NOTE_FIELDS)


@router.post("/engagements/{engagement_id}/review-notes/{note_id}", summary="Répondre, clore ou rouvrir une note")
def note_action(note_id: uuid.UUID, payload: NoteAction, request: Request,
                ctx: EngagementContext = Depends(get_engagement_context), db: Session = Depends(get_db)):
    ctx.require("answer_review_notes")
    n = owned(db, ctx, ReviewNote, note_id, "Note")
    if payload.action == "answer":
        if not (payload.response or "").strip():
            raise AuditInvalid("Réponse obligatoire.")
        n.response, n.status = payload.response, "answered"
    elif payload.action == "close":
        n.status = "closed"
    else:
        n.status = "open"
    db.flush()      # qui peut répondre / clore / rouvrir : contrôlé par la base
    db.refresh(n)
    _elog(db, request, ctx, f"review_note.{payload.action}", "review_notes", n.id)
    return row(n, NOTE_FIELDS)
