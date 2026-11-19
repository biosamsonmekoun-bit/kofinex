"""API — audit interne (lot 8) : plan annuel, cartographie des risques, constats et recommandations, plans d'action
et suivi, rapports d'audit (aperçu, émission, export Word).

Les règles décisives (approbation et modifications motivées du plan, validation par une autre personne, réponse de
l'audité, vérification par l'encadrement, historique du suivi, rapport figé avec empreinte, émission) sont aussi
imposées par la base (migration 0009).
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.api.deps import CompanyContext, OrgContext, get_company_context, get_current_user, get_db, get_org_context
from app.core.errors import Conflict, Forbidden, NotFound
from app.core.security import AuthenticatedUser
from app.engines.audit import internal as ia
from app.models import (
    ActionPlan,
    ActionPlanUpdate,
    AuditPlan,
    AuditPlanItem,
    AuditPlanItemHistory,
    AuditReport,
    Company,
    Control,
    Engagement,
    EngagementMember,
    EngagementRisk,
    Finding,
    IcDomain,
    MethodologyItem,
    Process,
    Recommendation,
    Risk,
    RiskRatingHistory,
    Workpaper,
)
from app.services import internal_audit as isvc
from app.services.audit import record_event
from app.services.engagements import AuditInvalid, EngagementContext, js, owned, people, row
from app.services.engagements import get_engagement_context as _ctx

router = APIRouter(tags=["Audit interne"])
Db = Annotated[Session, Depends(get_db)]


def ctx_ia(ctx: EngagementContext = Depends(_ctx)) -> EngagementContext:
    isvc.require_ia(ctx.engagement)
    return ctx


Ctx = Annotated[EngagementContext, Depends(ctx_ia)]
Org = Annotated[OrgContext, Depends(get_org_context)]
Comp = Annotated[CompanyContext, Depends(get_company_context)]
User = Annotated[AuthenticatedUser, Depends(get_current_user)]


def _log(db, request, user_id, org_id, action, entity_type, entity_id, details=None, company_id=None):
    record_event(db, user_id=user_id, action=action, entity_type=entity_type, entity_id=entity_id, organization_id=org_id,
                 company_id=company_id, details=js(details or {}), request=request)


def _elog(db, request, ctx: EngagementContext, action, entity_type, entity_id, details=None):
    _log(db, request, ctx.user.id, ctx.engagement.organization_id, action, entity_type, entity_id,
         {"engagement_id": str(ctx.engagement.id), **(details or {})}, ctx.engagement.company_id)


def _ids(ctx: EngagementContext) -> dict:
    return {"organization_id": ctx.engagement.organization_id, "engagement_id": ctx.engagement.id}


def _clean(v):
    return (v.strip() or None) if isinstance(v, str) else v


# ======================================================================== plan annuel
PLAN_FIELDS = ("id", "organization_id", "title", "period_start", "period_end", "description", "status", "approval_body",
               "approval_reference", "approval_date", "approved_by", "approved_at", "created_by", "created_at", "updated_at")
ITEM_FIELDS = ("id", "plan_id", "company_id", "process_id", "title", "rationale", "priority_rank", "planned_start",
               "planned_end", "budget_days", "engagement_id", "status", "status_reason", "added_after_approval",
               "change_reason", "created_at", "updated_at")


def _plan_ctx(db: Session, user: AuthenticatedUser, plan_id: uuid.UUID) -> tuple[AuditPlan, bool]:
    p = db.get(AuditPlan, plan_id)          # RLS : membres de l'organisation
    if p is None:
        raise NotFound("Plan introuvable")
    manager = bool(db.execute(text("SELECT authz.has_org_role(:o, ARRAY['owner','admin'])"), {"o": p.organization_id}).scalar())
    return p, manager


def _require_plan_manager(manager: bool) -> None:
    if not manager:
        raise Forbidden("Plan d'audit : propriétaires et administrateurs de l'organisation.")


def _plan_out(db: Session, p: AuditPlan, manager: bool) -> dict:
    items = list(db.scalars(select(AuditPlanItem).where(AuditPlanItem.plan_id == p.id)
                            .order_by(AuditPlanItem.priority_rank.nulls_last(), AuditPlanItem.planned_start.nulls_last())))
    companies = {c.id: c.name for c in db.scalars(select(Company).where(Company.organization_id == p.organization_id))}
    procs = {x.id: f"{x.code} — {x.name}"
             for x in db.scalars(select(Process).where(Process.organization_id == p.organization_id))}
    eng_ids = [i.engagement_id for i in items if i.engagement_id]
    engs = {x.id: x for x in db.scalars(select(Engagement).where(Engagement.id.in_(eng_ids)))} if eng_ids else {}
    out_items = [{**row(i, ITEM_FIELDS), "company": companies.get(i.company_id), "process": procs.get(i.process_id),
                  "engagement": {"id": str(engs[i.engagement_id].id), "reference": engs[i.engagement_id].reference,
                                 "status": engs[i.engagement_id].status} if i.engagement_id in engs else None}
                 for i in items]
    ppl = people(db, [p.approved_by, p.created_by])
    return {**row(p, PLAN_FIELDS), "approved_by_user": ppl.get(str(p.approved_by)), "can_manage": manager,
            "items": out_items, "summary": js(ia.plan_summary(out_items))}


class PlanIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    period_start: date
    period_end: date
    description: str | None = Field(default=None, max_length=4000)


@router.get("/organizations/{org_id}/audit-plans")
def list_plans(ctx: Org, db: Db):
    plans = list(db.scalars(select(AuditPlan).where(AuditPlan.organization_id == ctx.organization_id)
                            .order_by(AuditPlan.period_start.desc())))
    counts = dict(db.execute(select(AuditPlanItem.plan_id, func.count())
                             .where(AuditPlanItem.organization_id == ctx.organization_id)
                             .group_by(AuditPlanItem.plan_id)).all())
    return {"plans": [{**row(p, PLAN_FIELDS), "items": counts.get(p.id, 0)} for p in plans], "can_manage": ctx.is_manager}


@router.post("/organizations/{org_id}/audit-plans", status_code=status.HTTP_201_CREATED)
def create_plan(p: PlanIn, request: Request, ctx: Org, db: Db):
    if not ctx.is_manager:
        raise Forbidden("Plan d'audit : propriétaires et administrateurs de l'organisation.")
    if p.period_end <= p.period_start:
        raise AuditInvalid("La fin de période doit suivre le début.")
    plan = AuditPlan(id=uuid.uuid4(), organization_id=ctx.organization_id, created_by=ctx.user.id, **p.model_dump())
    db.add(plan)
    db.flush()
    _log(db, request, ctx.user.id, ctx.organization_id, "audit_plan.create", "audit_plans", plan.id, {"title": plan.title})
    return _plan_out(db, plan, True)


@router.get("/audit-plans/{plan_id}")
def get_plan(plan_id: uuid.UUID, user: User, db: Db):
    p, manager = _plan_ctx(db, user, plan_id)
    return _plan_out(db, p, manager)


@router.patch("/audit-plans/{plan_id}")
def update_plan(plan_id: uuid.UUID, payload: PlanIn, request: Request, user: User, db: Db):
    p, manager = _plan_ctx(db, user, plan_id)
    _require_plan_manager(manager)
    if p.status != "draft":
        data = payload.model_dump()
        if (data["title"], data["period_start"], data["period_end"]) != (p.title, p.period_start, p.period_end):
            raise Conflict("Plan approuvé : seul le descriptif peut évoluer.")
    for k, v in payload.model_dump().items():
        setattr(p, k, _clean(v))
    db.flush()
    _log(db, request, user.id, p.organization_id, "audit_plan.update", "audit_plans", p.id)
    return _plan_out(db, p, manager)


class ApproveIn(BaseModel):
    approval_body: str = Field(min_length=2, max_length=300)
    approval_reference: str | None = Field(default=None, max_length=300)
    approval_date: date


@router.post("/audit-plans/{plan_id}/approve", summary="Enregistrer l'approbation du plan par l'instance compétente")
def approve_plan(plan_id: uuid.UUID, payload: ApproveIn, request: Request, user: User, db: Db):
    p, manager = _plan_ctx(db, user, plan_id)
    _require_plan_manager(manager)
    if p.status != "draft":
        raise Conflict("Plan déjà approuvé.")
    p.status, p.approved_by = "approved", user.id
    p.approval_body, p.approval_reference, p.approval_date = payload.approval_body.strip(), _clean(payload.approval_reference), \
        payload.approval_date
    db.flush()
    db.refresh(p)
    _log(db, request, user.id, p.organization_id, "audit_plan.approve", "audit_plans", p.id, payload.model_dump())
    return _plan_out(db, p, manager)


@router.post("/audit-plans/{plan_id}/close")
def close_plan(plan_id: uuid.UUID, request: Request, user: User, db: Db):
    p, manager = _plan_ctx(db, user, plan_id)
    _require_plan_manager(manager)
    if p.status != "approved":
        raise Conflict("Seul un plan approuvé se clôture.")
    open_items = [i for i in db.scalars(select(AuditPlanItem).where(AuditPlanItem.plan_id == p.id))
                  if i.status in ("planned", "in_progress")]
    if open_items:
        raise AuditInvalid(f"{len(open_items)} mission(s) prévue(s) ou en cours : réalisez-les, reportez-les ou annulez-les.")
    p.status = "closed"
    db.flush()
    _log(db, request, user.id, p.organization_id, "audit_plan.close", "audit_plans", p.id)
    return _plan_out(db, p, manager)


@router.delete("/audit-plans/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_plan(plan_id: uuid.UUID, request: Request, user: User, db: Db):
    p, manager = _plan_ctx(db, user, plan_id)
    _require_plan_manager(manager)
    db.delete(p)
    db.flush()
    _log(db, request, user.id, p.organization_id, "audit_plan.delete", "audit_plans", plan_id)
    return Response(status_code=204)


class PlanItemIn(BaseModel):
    company_id: uuid.UUID
    process_id: uuid.UUID | None = None
    title: str = Field(min_length=1, max_length=300)
    rationale: str = Field(min_length=10, max_length=4000)
    priority_rank: int | None = Field(default=None, ge=1)
    planned_start: date | None = None
    planned_end: date | None = None
    budget_days: Decimal | None = Field(default=None, ge=0)
    change_reason: str | None = Field(default=None, max_length=2000)


class PlanItemUpdate(BaseModel):
    company_id: uuid.UUID | None = None
    process_id: uuid.UUID | None = None
    title: str | None = Field(default=None, min_length=1, max_length=300)
    rationale: str | None = Field(default=None, min_length=10, max_length=4000)
    priority_rank: int | None = Field(default=None, ge=1)
    planned_start: date | None = None
    planned_end: date | None = None
    budget_days: Decimal | None = Field(default=None, ge=0)
    engagement_id: uuid.UUID | None = None
    status: Literal["planned", "in_progress", "completed", "postponed", "cancelled"] | None = None
    status_reason: str | None = Field(default=None, max_length=2000)
    change_reason: str | None = Field(default=None, max_length=2000)


def _check_item_refs(db: Session, org_id: uuid.UUID, company_id: uuid.UUID, process_id: uuid.UUID | None) -> None:
    c = db.get(Company, company_id)
    if c is None or c.organization_id != org_id:
        raise AuditInvalid("Entité introuvable dans l'organisation.")
    if process_id:
        pr = db.get(Process, process_id)
        if pr is None or pr.company_id != company_id:
            raise AuditInvalid("Processus hors de l'entité choisie.")


@router.post("/audit-plans/{plan_id}/items", status_code=status.HTTP_201_CREATED)
def add_item(plan_id: uuid.UUID, payload: PlanItemIn, request: Request, user: User, db: Db):
    p, manager = _plan_ctx(db, user, plan_id)
    _require_plan_manager(manager)
    if p.status == "approved" and not (payload.change_reason or "").strip():
        raise AuditInvalid("Plan approuvé : indiquez le motif de l'ajout (décision, demande).")
    _check_item_refs(db, p.organization_id, payload.company_id, payload.process_id)
    it = AuditPlanItem(id=uuid.uuid4(), organization_id=p.organization_id, plan_id=p.id, created_by=user.id,
                       **{k: _clean(v) for k, v in payload.model_dump().items()})
    db.add(it)
    db.flush()
    _log(db, request, user.id, p.organization_id, "audit_plan.item_add", "audit_plan_items", it.id, {"title": it.title})
    return _plan_out(db, p, manager)


@router.patch("/audit-plan-items/{item_id}")
def update_item(item_id: uuid.UUID, payload: PlanItemUpdate, request: Request, user: User, db: Db):
    it = db.get(AuditPlanItem, item_id)
    if it is None:
        raise NotFound("Mission prévue introuvable")
    p, manager = _plan_ctx(db, user, it.plan_id)
    _require_plan_manager(manager)
    data = payload.model_dump(exclude_unset=True)
    if "company_id" in data or "process_id" in data:
        _check_item_refs(db, p.organization_id, data.get("company_id", it.company_id), data.get("process_id", it.process_id))
    if data.get("engagement_id"):
        eng = db.get(Engagement, data["engagement_id"])
        if eng is None or eng.organization_id != p.organization_id:
            raise AuditInvalid("Mission introuvable.")
    if data.get("status") in ("postponed", "cancelled") and not (data.get("status_reason") or "").strip():
        raise AuditInvalid("Motif du report ou de l'annulation requis.")
    for k, v in data.items():
        setattr(it, k, _clean(v))
    db.flush()
    _log(db, request, user.id, p.organization_id, "audit_plan.item_update", "audit_plan_items", it.id, data)
    return _plan_out(db, p, manager)


@router.delete("/audit-plan-items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_item(item_id: uuid.UUID, request: Request, user: User, db: Db):
    it = db.get(AuditPlanItem, item_id)
    if it is None:
        raise NotFound("Mission prévue introuvable")
    p, manager = _plan_ctx(db, user, it.plan_id)
    _require_plan_manager(manager)
    db.delete(it)
    db.flush()
    _log(db, request, user.id, p.organization_id, "audit_plan.item_delete", "audit_plan_items", item_id)
    return Response(status_code=204)


@router.get("/audit-plan-items/{item_id}/history")
def item_history(item_id: uuid.UUID, user: User, db: Db):
    rows = list(db.scalars(select(AuditPlanItemHistory).where(AuditPlanItemHistory.plan_item_id == item_id)
                           .order_by(AuditPlanItemHistory.changed_at)))
    ppl = people(db, [r.changed_by for r in rows])
    out = []
    for r in rows:
        before = r.before or {}
        changed = sorted(k for k in r.after if k not in ("updated_at",) and before.get(k) != r.after.get(k)) if r.before else []
        out.append({"id": str(r.id), "operation": r.operation, "changed_fields": changed, "reason": r.reason,
                    "after": r.after, "changed_by": ppl.get(str(r.changed_by)), "changed_at": js(r.changed_at)})
    return out


# ======================================================================== cartographie
@router.get("/companies/{company_id}/risk-map", summary="Cartographie des risques de l'entité (grille de la méthodologie)")
def risk_map(ctx: Comp, db: Db, basis: Literal["inherent", "residual"] = "inherent",
             scale_version_id: uuid.UUID | None = None):
    risks = list(db.scalars(select(Risk).where(Risk.company_id == ctx.company_id, Risk.status == "active").order_by(Risk.code)))
    versions = sorted({r.scale_version_id for r in risks if r.scale_version_id}, key=str)
    # grille par défaut : celle qui cote le plus de risques
    usage = {v: sum(1 for r in risks if r.scale_version_id == v) for v in versions}
    vid = scale_version_id or (max(versions, key=usage.__getitem__) if versions else None)
    procs = {p.id: p for p in db.scalars(select(Process).where(Process.company_id == ctx.company_id).order_by(Process.code))}
    scale = None
    if vid:
        scale = next((i.content for i in db.scalars(select(MethodologyItem).where(
            MethodologyItem.version_id == vid, MethodologyItem.item_type == "risk_scale"))), None)
    rated = [ia.RatedRisk(str(r.id), r.code, r.title, procs[r.process_id].code if r.process_id in procs else None,
                          getattr(r, f"{basis}_likelihood"), getattr(r, f"{basis}_impact"))
             for r in risks if r.scale_version_id == vid]
    other_scale = [{"id": str(r.id), "code": r.code, "title": r.title} for r in risks if r.scale_version_id not in (vid, None)]
    # couverture : missions du plan et constats par processus
    items = list(db.scalars(select(AuditPlanItem).where(AuditPlanItem.company_id == ctx.company_id)))
    plans = {p.id: p for p in db.scalars(select(AuditPlan).where(AuditPlan.id.in_({i.plan_id for i in items})))} if items else {}
    coverage = []
    for p in procs.values():
        its = sorted((i for i in items if i.process_id == p.id), key=lambda i: str(i.planned_start or ""))
        coverage.append({"id": str(p.id), "code": p.code, "name": p.name, "parent_id": js(p.parent_id),
                         "owner_name": p.owner_name, "is_active": p.is_active,
                         "risks": sum(1 for r in risks if r.process_id == p.id),
                         "plan_items": [{"title": i.title, "status": i.status,
                                         "plan": plans[i.plan_id].title if i.plan_id in plans else None,
                                         "planned_start": js(i.planned_start)} for i in its]})
    return {"basis": basis, "scale_version_id": js(vid), "scale_versions": js(versions),
            "map": ia.risk_map(rated, scale) if scale else None, "unscaled": [{"id": str(r.id), "code": r.code, "title": r.title}
                                                                         for r in risks if r.scale_version_id is None],
            "other_scale": other_scale, "processes": coverage}


@router.get("/companies/{company_id}/risks/{risk_id}/history", summary="Historique des cotations d'un risque")
def risk_history(risk_id: uuid.UUID, ctx: Comp, db: Db):
    r = db.get(Risk, risk_id)
    if r is None or r.company_id != ctx.company_id:
        raise NotFound("Risque introuvable")
    rows = list(db.scalars(select(RiskRatingHistory).where(RiskRatingHistory.risk_id == risk_id)
                           .order_by(RiskRatingHistory.changed_at)))
    ppl = people(db, [x.changed_by for x in rows])
    return [{**row(x, ("scale_version_id", "inherent_likelihood", "inherent_impact", "residual_likelihood", "residual_impact",
                       "changed_at")), "changed_by": ppl.get(str(x.changed_by))} for x in rows]


class ProcessUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    parent_id: uuid.UUID | None = None
    owner_name: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    is_active: bool | None = None


@router.patch("/companies/{company_id}/processes/{process_id}")
def update_process(process_id: uuid.UUID, payload: ProcessUpdate, request: Request, ctx: Comp, db: Db):
    if ctx.role.value not in ("org_admin", "auditor"):
        raise Forbidden("Registre des processus et des risques : auditeurs de l'entité et administrateurs.")
    p = db.get(Process, process_id)
    if p is None or p.company_id != ctx.company_id:
        raise NotFound("Processus introuvable")
    data = payload.model_dump(exclude_unset=True)
    if data.get("parent_id"):
        seen, cur = {p.id}, db.get(Process, data["parent_id"])
        while cur is not None:
            if cur.company_id != ctx.company_id or cur.id in seen:
                raise AuditInvalid("Processus parent invalide (autre entité ou boucle).")
            seen.add(cur.id)
            cur = db.get(Process, cur.parent_id) if cur.parent_id else None
    for k, v in data.items():
        setattr(p, k, _clean(v))
    db.flush()
    _log(db, request, ctx.user.id, ctx.organization_id, "process.update", "processes", p.id, data, ctx.company_id)
    return row(p, ("id", "code", "name", "parent_id", "owner_name", "description", "is_active"))


# ======================================================================== constats et recommandations
class FindingIn(BaseModel):
    reference: str = Field(min_length=1, max_length=40)
    title: str = Field(min_length=1, max_length=300)
    condition: str = Field(min_length=1, max_length=8000)
    criteria: str = Field(min_length=1, max_length=8000)
    cause: str | None = Field(default=None, max_length=8000)
    effect: str | None = Field(default=None, max_length=8000)
    rating_code: str | None = Field(default=None, max_length=40)
    process_id: uuid.UUID | None = None
    engagement_risk_id: uuid.UUID | None = None
    workpaper_id: uuid.UUID | None = None
    # lot 9 : déficience de contrôle interne (kind = ic_deficiency), rattachée au contrôle, au risque, au domaine
    kind: Literal["audit_finding", "ic_deficiency"] = "audit_finding"
    control_id: uuid.UUID | None = None
    risk_id: uuid.UUID | None = None
    domain_id: uuid.UUID | None = None


def _check_finding(db: Session, ctx: EngagementContext, p: FindingIn) -> None:
    if p.rating_code and p.rating_code not in {lv["code"] for lv in isvc.levels(db, ctx.engagement, p.kind)}:
        raise AuditInvalid("Cotation absente de l'échelle de la méthodologie de la mission.")
    if p.kind == "ic_deficiency" and p.control_id is None:
        raise AuditInvalid("Une déficience de contrôle interne vise un contrôle du catalogue.")
    refs = ((Control, p.control_id, "Contrôle"), (Risk, p.risk_id, "Risque"), (IcDomain, p.domain_id, "Domaine"))
    for model, oid, what in refs:
        if oid:
            o = db.get(model, oid)
            if o is None or o.company_id != ctx.engagement.company_id:
                raise AuditInvalid(f"{what} hors de l'entité auditée.")
    if p.process_id:
        pr = db.get(Process, p.process_id)
        if pr is None or pr.company_id != ctx.engagement.company_id:
            raise AuditInvalid("Processus hors de l'entité auditée.")
    if p.engagement_risk_id:
        owned(db, ctx, EngagementRisk, p.engagement_risk_id, "Risque")
    if p.workpaper_id:
        owned(db, ctx, Workpaper, p.workpaper_id, "Feuille de travail")


B = "/engagements/{engagement_id}"


@router.get(B + "/findings", summary="Constats (l'audité ne voit que les constats communiqués)")
def list_findings(ctx: Ctx, db: Db):
    ctx.require("read_findings")
    return {"findings": isvc.findings_out(db, ctx.engagement), "levels": isvc.levels(db, ctx.engagement),
            "deficiency_levels": isvc.levels(db, ctx.engagement, "ic_deficiency"), "capabilities": ctx.caps}


@router.post(B + "/findings", status_code=status.HTTP_201_CREATED)
def create_finding(p: FindingIn, request: Request, ctx: Ctx, db: Db):
    ctx.require("edit_findings")
    _check_finding(db, ctx, p)
    f = Finding(id=uuid.uuid4(), **_ids(ctx), created_by=ctx.user.id, **{k: _clean(v) for k, v in p.model_dump().items()})
    db.add(f)
    db.flush()
    _elog(db, request, ctx, "finding.create", "findings", f.id, {"reference": f.reference})
    return list_findings(ctx, db)


@router.patch(B + "/findings/{finding_id}")
def update_finding(finding_id: uuid.UUID, p: FindingIn, request: Request, ctx: Ctx, db: Db):
    ctx.require("edit_findings")
    f = owned(db, ctx, Finding, finding_id, "Constat")
    if f.status != "draft":
        raise Conflict("Constat validé : remettez-le en brouillon (avec un motif) pour le modifier.")
    if p.kind != f.kind:
        raise AuditInvalid("La nature du constat ne change pas.")
    _check_finding(db, ctx, p)
    for k, v in p.model_dump(exclude={"kind"}).items():
        setattr(f, k, _clean(v))
    db.flush()
    _elog(db, request, ctx, "finding.update", "findings", f.id, {"reference": f.reference})
    return list_findings(ctx, db)


@router.delete(B + "/findings/{finding_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_finding(finding_id: uuid.UUID, request: Request, ctx: Ctx, db: Db):
    ctx.require("edit_findings")
    db.delete(owned(db, ctx, Finding, finding_id, "Constat"))
    db.flush()
    _elog(db, request, ctx, "finding.delete", "findings", finding_id)
    return Response(status_code=204)


class FindingAction(BaseModel):
    action: Literal["validate", "communicate", "reopen", "close"]
    reason: str | None = Field(default=None, max_length=2000)
    response_due: date | None = None


@router.post(B + "/findings/{finding_id}/status", summary="Valider, communiquer à l'audité, remettre en brouillon")
def finding_status(finding_id: uuid.UUID, p: FindingAction, request: Request, ctx: Ctx, db: Db):
    f = owned(db, ctx, Finding, finding_id, "Constat")
    if p.action == "validate":
        ctx.require("validate_findings")
        if f.status != "draft":
            raise Conflict("Seul un constat en brouillon se valide.")
        if f.created_by == ctx.user.id:
            raise AuditInvalid("Le constat doit être validé par une autre personne que son auteur.")
        if not f.rating_code:
            raise AuditInvalid("Cotez le constat avant de le valider.")
        if not db.scalar(select(Recommendation.id).where(Recommendation.finding_id == f.id)):
            raise AuditInvalid("Au moins une recommandation est requise.")
        f.status, f.validated_by = "validated", ctx.user.id
    elif p.action == "communicate":
        ctx.require("communicate_findings")
        if f.status != "validated":
            raise Conflict("Seul un constat validé se communique.")
        f.status, f.communicated_by, f.response_due = "communicated", ctx.user.id, p.response_due
    elif p.action == "close":
        # clôture après vérification des plans d'action ; possible après l'émission (suivi)
        ctx.require("close_findings")
        if f.status != "communicated":
            raise Conflict("Seul un constat communiqué se clôture.")
        if len((p.reason or "").strip()) < 3:
            raise AuditInvalid("Note de clôture requise.")
        f.status, f.closed_by, f.closure_note = "closed", ctx.user.id, p.reason.strip()
    else:
        ctx.require("validate_findings")
        if f.status in ("draft", "closed"):
            raise Conflict("Constat en brouillon ou clos.")
        if len((p.reason or "").strip()) < 3:
            raise AuditInvalid("Motif de la remise en brouillon requis.")
        f.status, f.reopen_reason = "draft", p.reason.strip()
    db.flush()
    _elog(db, request, ctx, f"finding.{p.action}", "findings", f.id, {"reference": f.reference, "reason": p.reason})
    return list_findings(ctx, db)


class ResponseIn(BaseModel):
    management_response: str | None = Field(default=None, max_length=8000)
    response_by_name: str | None = Field(default=None, max_length=300)


@router.post(B + "/findings/{finding_id}/response", summary="Réponse de la direction (par l'audité, ou saisie par l'équipe)")
def finding_response(finding_id: uuid.UUID, p: ResponseIn, request: Request, ctx: Ctx, db: Db):
    ctx.require("respond_findings")
    f = owned(db, ctx, Finding, finding_id, "Constat")
    if f.status != "communicated":
        raise Conflict("Le constat doit avoir été communiqué.")
    text_ = _clean(p.management_response)
    name = _clean(p.response_by_name)
    if ctx.role == "auditee":
        me = people(db, [ctx.user.id]).get(str(ctx.user.id)) or {}
        name = name or me.get("full_name") or me.get("email")
        f.response_user_id = ctx.user.id
    else:
        if text_ and not name:
            raise AuditInvalid("Indiquez l'auteur de la réponse (nom et fonction).")
        f.response_user_id = None
    f.management_response, f.response_by_name = text_, name if text_ else None
    db.flush()
    _elog(db, request, ctx, "finding.response", "findings", f.id, {"reference": f.reference, "by": name})
    return list_findings(ctx, db)


class RecommendationIn(BaseModel):
    reference: str = Field(min_length=1, max_length=40)
    text: str = Field(min_length=1, max_length=8000)


@router.post(B + "/findings/{finding_id}/recommendations", status_code=status.HTTP_201_CREATED)
def add_recommendation(finding_id: uuid.UUID, p: RecommendationIn, request: Request, ctx: Ctx, db: Db):
    ctx.require("edit_findings")
    f = owned(db, ctx, Finding, finding_id, "Constat")
    rc = Recommendation(id=uuid.uuid4(), **_ids(ctx), finding_id=f.id, reference=p.reference.strip(), text=p.text.strip(),
                        created_by=ctx.user.id)
    db.add(rc)
    db.flush()
    _elog(db, request, ctx, "recommendation.create", "recommendations", rc.id, {"reference": rc.reference})
    return list_findings(ctx, db)


@router.patch(B + "/recommendations/{rec_id}")
def update_recommendation(rec_id: uuid.UUID, p: RecommendationIn, request: Request, ctx: Ctx, db: Db):
    ctx.require("edit_findings")
    rc = owned(db, ctx, Recommendation, rec_id, "Recommandation")
    rc.reference, rc.text = p.reference.strip(), p.text.strip()
    db.flush()
    _elog(db, request, ctx, "recommendation.update", "recommendations", rc.id)
    return list_findings(ctx, db)


@router.delete(B + "/recommendations/{rec_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_recommendation(rec_id: uuid.UUID, request: Request, ctx: Ctx, db: Db):
    ctx.require("edit_findings")
    db.delete(owned(db, ctx, Recommendation, rec_id, "Recommandation"))
    db.flush()
    _elog(db, request, ctx, "recommendation.delete", "recommendations", rec_id)
    return Response(status_code=204)


# ======================================================================== plans d'action et suivi
class ActionPlanIn(BaseModel):
    description: str = Field(min_length=1, max_length=4000)
    owner_name: str = Field(min_length=1, max_length=300)
    owner_user_id: uuid.UUID | None = None
    due_date: date


@router.post(B + "/recommendations/{rec_id}/action-plans", status_code=status.HTTP_201_CREATED)
def add_action_plan(rec_id: uuid.UUID, p: ActionPlanIn, request: Request, ctx: Ctx, db: Db):
    ctx.require("follow_up")
    rc = owned(db, ctx, Recommendation, rec_id, "Recommandation")
    if p.owner_user_id and not db.scalar(select(EngagementMember.id).where(
            EngagementMember.engagement_id == ctx.engagement.id, EngagementMember.user_id == p.owner_user_id)):
        raise AuditInvalid("Le responsable désigné doit être membre de la mission (rôle audité).")
    a = ActionPlan(id=uuid.uuid4(), **_ids(ctx), company_id=ctx.engagement.company_id, recommendation_id=rc.id,
                   created_by=ctx.user.id, **{k: _clean(v) for k, v in p.model_dump().items()})
    db.add(a)
    db.flush()
    _elog(db, request, ctx, "action_plan.create", "action_plans", a.id, {"recommendation": rc.reference})
    return list_findings(ctx, db)


@router.patch(B + "/action-plans/{ap_id}", summary="Modifier le contenu d'un plan d'action (avant l'émission)")
def update_action_plan(ap_id: uuid.UUID, p: ActionPlanIn, request: Request, ctx: Ctx, db: Db):
    ctx.require("follow_up")
    a = owned(db, ctx, ActionPlan, ap_id, "Plan d'action")
    if p.due_date != a.due_date:
        raise AuditInvalid("L'échéance se modifie par une mise à jour de suivi (avec un commentaire).")
    a.description, a.owner_name, a.owner_user_id = p.description.strip(), p.owner_name.strip(), p.owner_user_id
    db.flush()
    _elog(db, request, ctx, "action_plan.update", "action_plans", a.id)
    return list_findings(ctx, db)


@router.delete(B + "/action-plans/{ap_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_action_plan(ap_id: uuid.UUID, request: Request, ctx: Ctx, db: Db):
    ctx.require("edit_findings")
    db.delete(owned(db, ctx, ActionPlan, ap_id, "Plan d'action"))
    db.flush()
    _elog(db, request, ctx, "action_plan.delete", "action_plans", ap_id)
    return Response(status_code=204)


class UpdateIn(BaseModel):
    status: Literal["planned", "in_progress", "implemented", "verified", "not_implemented", "risk_accepted"]
    comment: str = Field(min_length=3, max_length=4000)
    new_due_date: date | None = None


@router.get(B + "/action-plans/{ap_id}/updates")
def list_updates(ap_id: uuid.UUID, ctx: Ctx, db: Db):
    ctx.require("read_findings")
    owned(db, ctx, ActionPlan, ap_id, "Plan d'action")
    return isvc.updates_out(db, ap_id)


@router.post(B + "/action-plans/{ap_id}/updates", status_code=status.HTTP_201_CREATED, summary="Mise à jour de suivi")
def add_update(ap_id: uuid.UUID, p: UpdateIn, request: Request, ctx: Ctx, db: Db):
    ctx.require("verify_actions" if p.status == "verified" else "follow_up")
    a = owned(db, ctx, ActionPlan, ap_id, "Plan d'action")
    if a.status == "verified":
        raise Conflict("Action vérifiée : suivi clos.")
    if p.status == "verified" and a.status != "implemented":
        raise AuditInvalid("Vérification : l'action doit d'abord être déclarée mise en œuvre.")
    db.add(ActionPlanUpdate(id=uuid.uuid4(), **_ids(ctx), action_plan_id=a.id, status=p.status, comment=p.comment.strip(),
                            new_due_date=p.new_due_date, author_id=ctx.user.id, author_role=ctx.role or ""))
    db.flush()
    db.refresh(a)
    _elog(db, request, ctx, "action_plan.follow_up", "action_plans", a.id, {"status": p.status, "new_due_date": p.new_due_date})
    return {**row(a, isvc.AP_FIELDS), "updates": isvc.updates_out(db, a.id)}


@router.get("/organizations/{org_id}/action-plans", summary="Suivi des recommandations, toutes missions confondues")
def follow_up(ctx: Org, db: Db, company_id: uuid.UUID | None = None, status_filter: str | None = None, overdue: bool = False):
    q = (select(ActionPlan, Recommendation, Finding, Engagement)
         .join(Recommendation, Recommendation.id == ActionPlan.recommendation_id)
         .join(Finding, Finding.id == Recommendation.finding_id)
         .join(Engagement, Engagement.id == ActionPlan.engagement_id)
         .where(ActionPlan.organization_id == ctx.organization_id))
    if company_id:
        q = q.where(ActionPlan.company_id == company_id)
    if status_filter:
        q = q.where(ActionPlan.status.in_(status_filter.split(",")))
    today = date.today()
    companies = {c.id: c.name for c in db.scalars(select(Company).where(Company.organization_id == ctx.organization_id))}
    rows = []
    for a, rc, f, e in db.execute(q.order_by(ActionPlan.due_date)).all():
        od = ia.is_overdue(a.status, a.due_date, today)
        if overdue and not od:
            continue
        rows.append({**row(a, isvc.AP_FIELDS), "overdue": od, "company": companies.get(a.company_id),
                     "engagement": {"id": str(e.id), "reference": e.reference, "name": e.name, "status": e.status},
                     "finding": {"id": str(f.id), "reference": f.reference, "title": f.title, "rating_code": f.rating_code},
                     "recommendation": {"id": str(rc.id), "reference": rc.reference, "text": rc.text}})
    return {"actions": rows, "summary": js(ia.follow_up_summary(
        [{"status": r["status"], "due_date": date.fromisoformat(r["due_date"])} for r in rows], today))}


# ======================================================================== rapports
REPORT_FIELDS = ("id", "version", "title", "executive_summary", "overall_conclusion", "distribution", "status",
                 "content_sha256", "issued_by", "issued_at", "created_by", "created_at", "updated_at")


class ReportIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    executive_summary: str | None = Field(default=None, max_length=20000)
    overall_conclusion: str | None = Field(default=None, max_length=20000)
    distribution: str | None = Field(default=None, max_length=4000)


def _reports(db: Session, ctx: EngagementContext) -> dict:
    reps = list(db.scalars(select(AuditReport).where(AuditReport.engagement_id == ctx.engagement.id)
                           .order_by(AuditReport.version.desc())))
    ppl = people(db, [r.issued_by for r in reps])
    return {"reports": [{**row(r, REPORT_FIELDS), "issued_by_user": ppl.get(str(r.issued_by))} for r in reps],
            "capabilities": ctx.caps}


@router.get(B + "/reports")
def list_reports(ctx: Ctx, db: Db):
    ctx.require("read_findings")
    return _reports(db, ctx)


@router.post(B + "/reports", status_code=status.HTTP_201_CREATED, summary="Nouveau projet de rapport (version suivante)")
def create_report(p: ReportIn, request: Request, ctx: Ctx, db: Db):
    ctx.require("edit_report")
    v = db.scalar(select(func.coalesce(func.max(AuditReport.version), 0)).where(AuditReport.engagement_id == ctx.engagement.id))
    if db.scalar(select(AuditReport.id).where(AuditReport.engagement_id == ctx.engagement.id, AuditReport.status == "draft")):
        raise Conflict("Un projet de rapport existe déjà.")
    r = AuditReport(id=uuid.uuid4(), **_ids(ctx), version=v + 1, created_by=ctx.user.id,
                    **{k: _clean(x) for k, x in p.model_dump().items()})
    db.add(r)
    db.flush()
    _elog(db, request, ctx, "report.create", "audit_reports", r.id, {"version": r.version})
    return _reports(db, ctx)


@router.patch(B + "/reports/{report_id}")
def update_report(report_id: uuid.UUID, p: ReportIn, request: Request, ctx: Ctx, db: Db):
    ctx.require("edit_report")
    r = owned(db, ctx, AuditReport, report_id, "Rapport")
    if r.status != "draft":
        raise Conflict("Rapport émis : non modifiable.")
    for k, x in p.model_dump().items():
        setattr(r, k, _clean(x))
    db.flush()
    _elog(db, request, ctx, "report.update", "audit_reports", r.id, {"version": r.version})
    return _reports(db, ctx)


@router.delete(B + "/reports/{report_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_report(report_id: uuid.UUID, request: Request, ctx: Ctx, db: Db):
    ctx.require("edit_report")
    db.delete(owned(db, ctx, AuditReport, report_id, "Rapport"))
    db.flush()
    _elog(db, request, ctx, "report.delete", "audit_reports", report_id)
    return Response(status_code=204)


def _content(db: Session, ctx: EngagementContext, r: AuditReport) -> dict:
    if r.status != "draft":
        return {**r.snapshot, "issued_at": js(r.issued_at), "content_sha256": r.content_sha256, "draft": False}
    if ctx.role == "auditee":
        raise Forbidden("Le projet de rapport n'est pas accessible à l'audité.")
    return {**isvc.snapshot(db, ctx.engagement, r, None), "draft": True}


@router.get(B + "/reports/{report_id}/content", summary="Contenu du rapport (assemblé pour un projet, figé pour un rapport émis)")
def report_content(report_id: uuid.UUID, ctx: Ctx, db: Db):
    ctx.require("read_findings")
    return _content(db, ctx, owned(db, ctx, AuditReport, report_id, "Rapport"))


@router.get(B + "/reports/{report_id}/docx", summary="Rapport au format Word")
def report_docx(report_id: uuid.UUID, request: Request, ctx: Ctx, db: Db):
    ctx.require("read_findings")
    r = owned(db, ctx, AuditReport, report_id, "Rapport")
    c = _content(db, ctx, r)
    data = ia.render_docx(c, draft=c["draft"])
    _elog(db, request, ctx, "report.export", "audit_reports", r.id, {"version": r.version, "draft": c["draft"]})
    name = f"rapport-{ctx.engagement.reference}-v{r.version}{'-projet' if c['draft'] else ''}.docx"
    return Response(content=data, headers={"Content-Disposition": f"attachment; filename={name}"},
                    media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")


@router.post(B + "/reports/{report_id}/issue", summary="Émettre le rapport : contenu figé, empreinte calculée par la base")
def issue_report(report_id: uuid.UUID, request: Request, ctx: Ctx, db: Db):
    ctx.require("issue_report")
    r = owned(db, ctx, AuditReport, report_id, "Rapport")
    if r.status != "draft":
        raise Conflict("Rapport déjà émis.")
    if not r.overall_conclusion:
        raise AuditInvalid("Conclusion générale requise avant l'émission.")
    pending = [f.reference for f in db.scalars(select(Finding).where(Finding.engagement_id == ctx.engagement.id,
                                                                    Finding.status != "communicated"))]
    if pending:
        raise AuditInvalid(f"Constats non validés ou non communiqués : {', '.join(sorted(pending))}.")
    snap = isvc.snapshot(db, ctx.engagement, r, ctx.user.id)
    r.status, r.issued_by, r.snapshot = "issued", ctx.user.id, snap
    isvc.report_flag(db, True)
    try:
        db.flush()
    finally:
        isvc.report_flag(db, False)
    db.refresh(r)
    _elog(db, request, ctx, "report.issue", "audit_reports", r.id, {"version": r.version, "sha256": r.content_sha256})
    return _reports(db, ctx)


@router.get(B + "/finding-levels")
def finding_levels(ctx: Ctx, db: Db):
    return isvc.levels(db, ctx.engagement)

