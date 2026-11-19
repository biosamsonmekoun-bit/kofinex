"""API — contrôle interne (lot 9).

Entité (/companies/{id}/ic/…) : rôles, domaines et modèles, processus, objectifs, risques (registre partagé),
contrôles, matrice risques-contrôles, rattachements aux référentiels, exécutions supervisées, tableau de bord,
tests et évaluations consultables, déficiences et remédiation, rapports, historique.
Mission (/engagements/{id}/ic/…) : programmes de contrôle, tests (conception, efficacité), éléments testés et
sélection, évaluations, prise en compte des tests par l'audit financier.

Les règles décisives sont imposées par la base (migration 0011) ; l'API les explique et journalise.
"""

from __future__ import annotations

import csv
import hashlib
import io
import uuid
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, Request, Response, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.errors import Conflict, Forbidden, NotFound
from app.engines.audit import control as ic
from app.engines.audit import financial as fa
from app.engines.audit import ic_templates as tpl
from app.engines.audit.evidence import safe_filename, validate_evidence
from app.engines.importing.files import FileRejected
from app.models import (
    Control,
    ControlExecution,
    ControlObjective,
    ControlRisk,
    ControlTest,
    ControlTestItem,
    ControlTestReliance,
    EvidenceItem,
    EvidenceLink,
    FrameworkMapping,
    IcAssessment,
    IcDomain,
    IcFrameworkLink,
    IcHistory,
    IcMember,
    MethodologyItem,
    MethodologyVersion,
    Procedure,
    Process,
    Risk,
    RiskRatingHistory,
    WorkProgram,
)
from app.services import internal_control as svc
from app.services.audit import record_event
from app.services.engagements import AuditInvalid, EngagementContext, js, methodology_items, owned, people, row
from app.services.engagements import get_engagement_context as _ectx
from app.services.internal_control import IcContext, get_ic_context
from app.services.storage import get_storage

router = APIRouter(tags=["Contrôle interne"])
Db = Annotated[Session, Depends(get_db)]
Ic = Annotated[IcContext, Depends(get_ic_context)]
Ctx = Annotated[EngagementContext, Depends(_ectx)]
C = "/companies/{company_id}/ic"
E = "/engagements/{engagement_id}/ic"
EXEC_BUCKET = "ic-evidence"


def _log(db, request, ctx: IcContext, action, entity_type, entity_id, details=None):
    record_event(
        db,
        user_id=ctx.user.id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        organization_id=ctx.organization_id,
        company_id=ctx.company_id,
        details=js(details or {}),
        request=request,
    )


def _elog(db, request, ctx: EngagementContext, action, entity_type, entity_id, details=None):
    record_event(
        db,
        user_id=ctx.user.id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        organization_id=ctx.engagement.organization_id,
        company_id=ctx.engagement.company_id,
        details=js({"engagement_id": str(ctx.engagement.id), **(details or {})}),
        request=request,
    )


def _clean(d: dict) -> dict:
    return {k: ((v.strip() or None) if isinstance(v, str) else v) for k, v in d.items()}


# ======================================================================== accès, rôles, référentiels
@router.get(C + "/access", summary="Mes droits sur le dispositif de contrôle interne de l'entité")
def access(ctx: Ic):
    return ctx.out()


class MemberIn(BaseModel):
    user_id: uuid.UUID
    role: Literal["ic_manager", "daf", "domain_owner", "process_owner", "control_performer", "supervisor", "observer"]
    domain_id: uuid.UUID | None = None


@router.get(C + "/members")
def list_members(ctx: Ic, db: Db):
    ms = list(db.scalars(select(IcMember).where(IcMember.company_id == ctx.company_id).order_by(IcMember.role)))
    ppl = people(db, [m.user_id for m in ms])
    return [
        {
            **row(m, ("id", "user_id", "role", "domain_id", "created_at")),
            "role_label": ic.IC_ROLES[m.role],
            "user": ppl.get(str(m.user_id)),
        }
        for m in ms
    ]


@router.get(C + "/candidates", summary="Membres de l'organisation pouvant recevoir un rôle")
def member_candidates(ctx: Ic, db: Db):
    ctx.require_admin()
    ids = [
        r[0]
        for r in db.execute(
            text("SELECT user_id FROM public.organization_members WHERE organization_id = :o"), {"o": ctx.organization_id}
        )
    ]
    return list(people(db, ids).values())


@router.post(C + "/members", status_code=status.HTTP_201_CREATED)
def add_member(p: MemberIn, request: Request, ctx: Ic, db: Db):
    ctx.require_admin()
    if p.role in ("domain_owner", "process_owner") and p.domain_id is None:
        raise AuditInvalid("Un responsable de domaine ou de processus est rattaché à un domaine.")
    if p.role in ("ic_manager", "daf", "observer") and p.domain_id is not None:
        raise AuditInvalid("Ce rôle porte sur toute l'entité, sans domaine.")
    svc.in_company(db, IcDomain, p.domain_id, ctx.company_id, "Domaine")
    m = IcMember(
        id=uuid.uuid4(), organization_id=ctx.organization_id, company_id=ctx.company_id, granted_by=ctx.user.id, **p.model_dump()
    )
    db.add(m)
    db.flush()
    _log(db, request, ctx, "ic.member.add", "ic_members", m.id, p.model_dump(mode="json"))
    return row(m, ("id", "user_id", "role", "domain_id"))


@router.delete(C + "/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(member_id: uuid.UUID, request: Request, ctx: Ic, db: Db):
    ctx.require_admin()
    m = svc.in_company(db, IcMember, member_id, ctx.company_id, "Rôle")
    db.delete(m)
    db.flush()
    _log(db, request, ctx, "ic.member.remove", "ic_members", member_id, {"user_id": m.user_id, "role": m.role})
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(C + "/frameworks", summary="Référentiels de contrôle interne disponibles et leurs éléments")
def frameworks(ctx: Ic, db: Db):
    vs = list(
        db.scalars(
            select(MethodologyVersion)
            .where(
                MethodologyVersion.kind == "internal_control",
                (MethodologyVersion.organization_id == ctx.organization_id) | MethodologyVersion.organization_id.is_(None),
            )
            .order_by(MethodologyVersion.name, MethodologyVersion.version_label)
        )
    )
    items = (
        list(
            db.scalars(
                select(MethodologyItem).where(
                    MethodologyItem.version_id.in_([v.id for v in vs]),
                    MethodologyItem.item_type.in_(
                        (
                            "ic_component",
                            "ic_principle",
                            "ic_requirement",
                            "ic_criterion",
                            "control_level_scale",
                            "deficiency_scale",
                        )
                    ),
                )
            )
        )
        if vs
        else []
    )
    maps = list(db.scalars(select(FrameworkMapping)))
    return {
        "versions": [
            {
                **row(
                    v,
                    (
                        "id",
                        "organization_id",
                        "name",
                        "version_label",
                        "status",
                        "framework_category",
                        "issuing_body",
                        "published_on",
                        "effective_from",
                        "source_reference",
                        "source_document",
                    ),
                ),
                "items": [
                    row(i, ("id", "item_type", "code", "label", "parent_code", "content")) for i in items if i.version_id == v.id
                ],
            }
            for v in vs
        ],
        "mappings": [
            row(
                m,
                (
                    "id",
                    "organization_id",
                    "source_item_id",
                    "target_item_id",
                    "relation",
                    "rationale",
                    "source_reference",
                    "created_at",
                ),
            )
            for m in maps
        ],
    }


class MappingIn(BaseModel):
    source_item_id: uuid.UUID
    target_item_id: uuid.UUID
    relation: Literal["equivalent", "partial", "related"]
    rationale: str = Field(min_length=3, max_length=4000)
    source_reference: str | None = Field(default=None, max_length=1000)


@router.post(
    C + "/framework-mappings",
    status_code=status.HTTP_201_CREATED,
    summary="Déclarer une correspondance entre éléments de deux référentiels (motivée)",
)
def add_mapping(p: MappingIn, request: Request, ctx: Ic, db: Db):
    m = FrameworkMapping(id=uuid.uuid4(), organization_id=ctx.organization_id, created_by=ctx.user.id, **_clean(p.model_dump()))
    db.add(m)
    db.flush()
    _log(db, request, ctx, "ic.mapping.add", "framework_mappings", m.id, p.model_dump(mode="json"))
    return row(m, ("id", "source_item_id", "target_item_id", "relation", "rationale"))


@router.delete(C + "/framework-mappings/{mapping_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_mapping(mapping_id: uuid.UUID, request: Request, ctx: Ic, db: Db):
    m = db.get(FrameworkMapping, mapping_id)
    if m is None or m.organization_id != ctx.organization_id:
        raise NotFound("Correspondance introuvable")
    db.delete(m)
    db.flush()
    _log(db, request, ctx, "ic.mapping.delete", "framework_mappings", mapping_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ======================================================================== domaines et modèles
@router.get(C + "/templates", summary="Modèles de domaines et de processus (structure configurable)")
def templates(ctx: Ic, db: Db):
    used = {d.template_code for d in db.scalars(select(IcDomain).where(IcDomain.company_id == ctx.company_id))}
    return [{**t, "used": t["code"] in used} for t in tpl.catalogue()]


class FromTemplates(BaseModel):
    codes: list[str] = Field(min_length=1, max_length=40)
    with_processes: bool = True


@router.post(
    C + "/domains/from-templates",
    status_code=status.HTTP_201_CREATED,
    summary="Créer les domaines choisis (et leurs processus) à partir des modèles",
)
def domains_from_templates(p: FromTemplates, request: Request, ctx: Ic, db: Db):
    ctx.require_admin()
    existing = {d.code for d in db.scalars(select(IcDomain).where(IcDomain.company_id == ctx.company_id))}
    pcodes = {x.code for x in db.scalars(select(Process).where(Process.company_id == ctx.company_id))}
    created = []
    order = len(existing)
    for code in p.codes:
        t = tpl.TEMPLATES.get(code)
        if t is None:
            raise AuditInvalid(f"Modèle inconnu « {code} ».")
        if t.code in existing:
            raise Conflict(f"Le domaine {t.code} existe déjà.")
        order += 1
        d = IcDomain(
            id=uuid.uuid4(),
            organization_id=ctx.organization_id,
            company_id=ctx.company_id,
            code=t.code,
            name=t.name,
            category=t.category,
            template_code=t.code,
            display_order=order,
            created_by=ctx.user.id,
        )
        db.add(d)
        db.flush()
        n = 0
        if p.with_processes:
            for pc, name in tpl.process_codes(t):
                if pc in pcodes:
                    continue
                db.add(
                    Process(
                        id=uuid.uuid4(),
                        organization_id=ctx.organization_id,
                        company_id=ctx.company_id,
                        domain_id=d.id,
                        code=pc,
                        name=name,
                        created_by=ctx.user.id,
                    )
                )
                n += 1
        db.flush()
        created.append({"code": t.code, "processes": n})
    _log(db, request, ctx, "ic.domains.from_templates", "ic_domains", None, {"created": created})
    return {"created": created}


class DomainIn(BaseModel):
    code: str = Field(min_length=1, max_length=40, pattern=r"^[A-Za-z0-9_.-]+$")
    name: str = Field(min_length=1, max_length=200)
    category: Literal["accounting_financial", "organizational", "custom"] = "custom"
    cycle_code: str | None = Field(default=None, max_length=40)
    description: str | None = Field(default=None, max_length=4000)
    owner_name: str | None = Field(default=None, max_length=200)
    owner_user_id: uuid.UUID | None = None
    is_active: bool = True
    display_order: int = 0


@router.get(C + "/domains")
def list_domains(ctx: Ic, db: Db):
    return [
        row(d, svc.DOMAIN_FIELDS)
        for d in db.scalars(
            select(IcDomain).where(IcDomain.company_id == ctx.company_id).order_by(IcDomain.display_order, IcDomain.code)
        )
    ]


@router.post(C + "/domains", status_code=status.HTTP_201_CREATED)
def create_domain(p: DomainIn, request: Request, ctx: Ic, db: Db):
    ctx.require_admin()
    d = IcDomain(
        id=uuid.uuid4(),
        organization_id=ctx.organization_id,
        company_id=ctx.company_id,
        created_by=ctx.user.id,
        **_clean(p.model_dump()),
    )
    db.add(d)
    db.flush()
    _log(db, request, ctx, "ic.domain.create", "ic_domains", d.id, {"code": d.code})
    return row(d, svc.DOMAIN_FIELDS)


@router.patch(C + "/domains/{domain_id}")
def update_domain(domain_id: uuid.UUID, p: DomainIn, request: Request, ctx: Ic, db: Db):
    d = svc.in_company(db, IcDomain, domain_id, ctx.company_id, "Domaine")
    ctx.require_manage(d.id)
    for k, v in _clean(p.model_dump(exclude={"code"})).items():
        setattr(d, k, v)
    db.flush()
    _log(db, request, ctx, "ic.domain.update", "ic_domains", d.id, p.model_dump(mode="json"))
    return row(d, svc.DOMAIN_FIELDS)


@router.delete(
    C + "/domains/{domain_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Supprimer un domaine vide (sinon : le désactiver)",
)
def delete_domain(domain_id: uuid.UUID, request: Request, ctx: Ic, db: Db):
    ctx.require_admin()
    d = svc.in_company(db, IcDomain, domain_id, ctx.company_id, "Domaine")
    for m in (Process, Risk, Control, ControlObjective):
        if db.scalar(select(m.id).where(m.domain_id == d.id).limit(1)):
            raise Conflict("Domaine utilisé : désactivez-le plutôt que de le supprimer.")
    db.delete(d)
    db.flush()
    _log(db, request, ctx, "ic.domain.delete", "ic_domains", domain_id, {"code": d.code})
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    C + "/domains/{domain_id}/overview",
    summary="Navigation par domaine : processus, risques, contrôles, tests, déficiences, recommandations",
)
def domain_overview(domain_id: uuid.UUID, ctx: Ic, db: Db):
    d = svc.in_company(db, IcDomain, domain_id, ctx.company_id, "Domaine")
    reg = svc.filtered(svc.registry(db, ctx.company_id), domain_id=d.id)
    tests = svc.visible_tests(db, ctx.company_id, [c.id for c in reg.controls])
    st = svc.status_map(reg.controls, tests)
    m = ic.matrix(svc.risk_refs(reg.risks), svc.control_refs(reg.controls), svc.link_dicts(reg.links), st)
    ind = {}
    for r in m["rows"]:
        ind[r["risk_id"]] = r["indicator"]
    scales: dict = {}
    nlinks = {}
    for lk in reg.links:
        nlinks[lk.control_id] = nlinks.get(lk.control_id, 0) + 1
    defs = svc.deficiencies(db, ctx.company_id, {c.id for c in reg.controls})
    return {
        "domain": row(d, svc.DOMAIN_FIELDS),
        "can_manage": ctx.manages(d.id),
        "processes": [row(p, svc.PROCESS_FIELDS) for p in reg.processes],
        "objectives": [row(o, svc.OBJECTIVE_FIELDS) for o in reg.objectives],
        "risks": [svc.risk_out(db, r, scales, ind.get(str(r.id))) for r in reg.risks],
        "controls": [svc.control_out(c, st[str(c.id)], nlinks.get(c.id, 0)) for c in reg.controls],
        "tests": [_test_brief(t) for t in tests],
        "deficiencies": defs,
        "uncovered_risks": m["uncovered_risks"],
        "dashboard": svc.dashboard(db, ctx, domain_id=d.id),
    }


def _test_brief(t: ControlTest) -> dict:
    return {
        **row(
            t,
            (
                "id",
                "engagement_id",
                "control_id",
                "reference",
                "test_type",
                "period_start",
                "period_end",
                "conclusion",
                "status",
                "reviewed_at",
            ),
        ),
        "conclusion_label": ic.CONCLUSION_LABELS.get(t.conclusion or "", None),
    }


# ======================================================================== processus, objectifs, risques (registre partagé)
class ProcessIn(BaseModel):
    code: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=200)
    parent_id: uuid.UUID | None = None
    domain_id: uuid.UUID | None = None
    owner_name: str | None = Field(default=None, max_length=200)
    owner_user_id: uuid.UUID | None = None
    description: str | None = Field(default=None, max_length=4000)
    is_active: bool = True


def _process_domain(db: Session, ctx: IcContext, p: ProcessIn) -> uuid.UUID | None:
    parent = svc.in_company(db, Process, p.parent_id, ctx.company_id, "Processus parent")
    svc.in_company(db, IcDomain, p.domain_id, ctx.company_id, "Domaine")
    return p.domain_id or (parent.domain_id if parent else None)


@router.get(C + "/processes")
def list_processes(ctx: Ic, db: Db):
    return [
        row(p, svc.PROCESS_FIELDS)
        for p in db.scalars(select(Process).where(Process.company_id == ctx.company_id).order_by(Process.code))
    ]


@router.post(C + "/processes", status_code=status.HTTP_201_CREATED)
def create_process(p: ProcessIn, request: Request, ctx: Ic, db: Db):
    ctx.require_manage(_process_domain(db, ctx, p))
    x = Process(
        id=uuid.uuid4(),
        organization_id=ctx.organization_id,
        company_id=ctx.company_id,
        created_by=ctx.user.id,
        **_clean(p.model_dump()),
    )
    db.add(x)
    db.flush()
    _log(db, request, ctx, "process.create", "processes", x.id, {"code": x.code, "domain_id": x.domain_id})
    return row(x, svc.PROCESS_FIELDS)


@router.patch(C + "/processes/{process_id}")
def update_process(process_id: uuid.UUID, p: ProcessIn, request: Request, ctx: Ic, db: Db):
    x = svc.in_company(db, Process, process_id, ctx.company_id, "Processus")
    ctx.require_manage(x.domain_id)
    ctx.require_manage(_process_domain(db, ctx, p))
    if p.parent_id:
        seen, cur = {x.id}, db.get(Process, p.parent_id)
        while cur is not None:
            if cur.id in seen:
                raise AuditInvalid("Processus parent invalide (boucle).")
            seen.add(cur.id)
            cur = db.get(Process, cur.parent_id) if cur.parent_id else None
    for k, v in _clean(p.model_dump(exclude={"code"})).items():
        setattr(x, k, v)
    db.flush()
    _log(db, request, ctx, "process.update", "processes", x.id, p.model_dump(mode="json"))
    return row(x, svc.PROCESS_FIELDS)


class ObjectiveIn(BaseModel):
    code: str = Field(min_length=1, max_length=40)
    statement: str = Field(min_length=1, max_length=2000)
    domain_id: uuid.UUID | None = None
    process_id: uuid.UUID | None = None
    assertion_codes: list[str] = Field(default_factory=list, max_length=20)
    is_active: bool = True


def _object_domain(db: Session, ctx: IcContext, domain_id, process_id) -> uuid.UUID | None:
    svc.in_company(db, IcDomain, domain_id, ctx.company_id, "Domaine")
    proc = svc.in_company(db, Process, process_id, ctx.company_id, "Processus")
    if proc and proc.domain_id and domain_id and proc.domain_id != domain_id:
        raise AuditInvalid("Le processus appartient à un autre domaine.")
    return domain_id or (proc.domain_id if proc else None)


@router.get(C + "/objectives")
def list_objectives(ctx: Ic, db: Db):
    return [
        row(o, svc.OBJECTIVE_FIELDS)
        for o in db.scalars(
            select(ControlObjective).where(ControlObjective.company_id == ctx.company_id).order_by(ControlObjective.code)
        )
    ]


@router.post(C + "/objectives", status_code=status.HTTP_201_CREATED)
def create_objective(p: ObjectiveIn, request: Request, ctx: Ic, db: Db):
    dom = _object_domain(db, ctx, p.domain_id, p.process_id)
    ctx.require_manage(dom)
    o = ControlObjective(
        id=uuid.uuid4(),
        organization_id=ctx.organization_id,
        company_id=ctx.company_id,
        created_by=ctx.user.id,
        **{**_clean(p.model_dump()), "domain_id": dom},
    )
    db.add(o)
    db.flush()
    _log(db, request, ctx, "ic.objective.create", "control_objectives", o.id, {"code": o.code})
    return row(o, svc.OBJECTIVE_FIELDS)


@router.patch(C + "/objectives/{objective_id}")
def update_objective(objective_id: uuid.UUID, p: ObjectiveIn, request: Request, ctx: Ic, db: Db):
    o = svc.in_company(db, ControlObjective, objective_id, ctx.company_id, "Objectif")
    ctx.require_manage(o.domain_id)
    dom = _object_domain(db, ctx, p.domain_id, p.process_id)
    ctx.require_manage(dom)
    for k, v in {**_clean(p.model_dump(exclude={"code"})), "domain_id": dom}.items():
        setattr(o, k, v)
    db.flush()
    _log(db, request, ctx, "ic.objective.update", "control_objectives", o.id, p.model_dump(mode="json"))
    return row(o, svc.OBJECTIVE_FIELDS)


class RiskIn(BaseModel):
    code: str = Field(min_length=1, max_length=40)
    title: str = Field(min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=4000)
    domain_id: uuid.UUID | None = None
    process_id: uuid.UUID | None = None
    objective_id: uuid.UUID | None = None
    category: str | None = Field(default=None, max_length=100)
    causes: str | None = Field(default=None, max_length=4000)
    consequences: str | None = Field(default=None, max_length=4000)
    owner_name: str | None = Field(default=None, max_length=200)
    owner_user_id: uuid.UUID | None = None
    cycle_code: str | None = Field(default=None, max_length=40)
    assertion_codes: list[str] = Field(default_factory=list, max_length=20)
    scale_version_id: uuid.UUID | None = None
    inherent_likelihood: int | None = Field(default=None, ge=1)
    inherent_impact: int | None = Field(default=None, ge=1)
    residual_likelihood: int | None = Field(default=None, ge=1)
    residual_impact: int | None = Field(default=None, ge=1)
    control_level_code: str | None = Field(default=None, max_length=40)
    status: Literal["active", "retired"] = "active"


def _check_scale_version(db: Session, version_id: uuid.UUID | None) -> None:
    if version_id is None:
        return
    v = db.get(MethodologyVersion, version_id)
    if v is None or v.status != "published":
        raise AuditInvalid("La cotation utilise la grille d'une méthodologie publiée (version figée).")


@router.get(C + "/risks", summary="Registre des risques enrichi (cotations sur la grille, indicateur de couverture)")
def list_risks(ctx: Ic, db: Db, domain_id: uuid.UUID | None = None, process_id: uuid.UUID | None = None, q: str | None = None):
    reg = svc.filtered(svc.registry(db, ctx.company_id), domain_id, process_id)
    st = svc.status_map(reg.controls, svc.visible_tests(db, ctx.company_id, [c.id for c in reg.controls]))
    m = ic.matrix(svc.risk_refs(reg.risks), svc.control_refs(reg.controls), svc.link_dicts(reg.links), st)
    ind = {r["risk_id"]: r["indicator"] for r in m["rows"]}
    scales: dict = {}
    out = [svc.risk_out(db, r, scales, ind.get(str(r.id))) for r in reg.risks]
    if q:
        ql = q.lower()
        out = [r for r in out if ql in (r["code"] + " " + r["title"]).lower()]
    return out


@router.post(C + "/risks", status_code=status.HTTP_201_CREATED)
def create_risk(p: RiskIn, request: Request, ctx: Ic, db: Db):
    dom = _object_domain(db, ctx, p.domain_id, p.process_id)
    ctx.require_manage(dom)
    svc.in_company(db, ControlObjective, p.objective_id, ctx.company_id, "Objectif")
    _check_scale_version(db, p.scale_version_id)
    r = Risk(
        id=uuid.uuid4(),
        organization_id=ctx.organization_id,
        company_id=ctx.company_id,
        created_by=ctx.user.id,
        **{**_clean(p.model_dump()), "domain_id": dom},
    )
    db.add(r)
    db.flush()
    _log(db, request, ctx, "risk.create", "risks", r.id, {"code": r.code})
    return svc.risk_out(db, r, {})


@router.patch(C + "/risks/{risk_id}")
def update_risk(risk_id: uuid.UUID, p: RiskIn, request: Request, ctx: Ic, db: Db):
    r = svc.in_company(db, Risk, risk_id, ctx.company_id, "Risque")
    ctx.require_manage(r.domain_id)
    dom = _object_domain(db, ctx, p.domain_id, p.process_id)
    ctx.require_manage(dom)
    svc.in_company(db, ControlObjective, p.objective_id, ctx.company_id, "Objectif")
    _check_scale_version(db, p.scale_version_id)
    for k, v in {**_clean(p.model_dump()), "domain_id": dom}.items():
        setattr(r, k, v)
    db.flush()
    _log(db, request, ctx, "risk.update", "risks", r.id, p.model_dump(mode="json"))
    return svc.risk_out(db, r, {})


@router.get(C + "/risks/{risk_id}/history", summary="Historique des évaluations d'un risque")
def risk_history(risk_id: uuid.UUID, ctx: Ic, db: Db):
    svc.in_company(db, Risk, risk_id, ctx.company_id, "Risque")
    hs = list(
        db.scalars(
            select(RiskRatingHistory).where(RiskRatingHistory.risk_id == risk_id).order_by(RiskRatingHistory.changed_at.desc())
        )
    )
    ppl = people(db, [h.changed_by for h in hs])
    return [
        {
            **row(
                h,
                (
                    "scale_version_id",
                    "inherent_likelihood",
                    "inherent_impact",
                    "residual_likelihood",
                    "residual_impact",
                    "control_level_code",
                    "changed_at",
                ),
            ),
            "changed_by": ppl.get(str(h.changed_by)),
        }
        for h in hs
    ]


# ======================================================================== contrôles et matrice
class ControlIn(BaseModel):
    code: str = Field(min_length=1, max_length=40)
    title: str = Field(min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=8000)
    control_objective: str | None = Field(default=None, max_length=2000)
    domain_id: uuid.UUID | None = None
    process_id: uuid.UUID | None = None
    objective_id: uuid.UUID | None = None
    existence: Literal["existing", "expected", "not_formalized", "absent"] = "existing"
    owner_name: str = Field(min_length=1, max_length=200)
    owner_user_id: uuid.UUID | None = None
    performer_name: str | None = Field(default=None, max_length=200)
    performer_user_id: uuid.UUID | None = None
    supervisor_name: str | None = Field(default=None, max_length=200)
    supervisor_user_id: uuid.UUID | None = None
    frequency: Literal["on_occurrence", "daily", "weekly", "monthly", "quarterly", "semiannual", "annual", "ad_hoc"] | None = None
    nature: Literal["preventive", "detective"] | None = None
    automation: Literal["manual", "automated", "semi_automated"] | None = None
    timing: Literal["permanent", "periodic"] | None = None
    execution_mode: str | None = Field(default=None, max_length=4000)
    expected_evidence: str | None = Field(default=None, max_length=4000)
    procedure_text: str | None = Field(default=None, max_length=20000)
    success_criteria: str | None = Field(default=None, max_length=4000)
    is_key: bool = False
    implemented_on: date | None = None
    operational_status: Literal["active", "suspended", "retired"] = "active"


def _check_control(db: Session, ctx: IcContext, p: ControlIn) -> uuid.UUID | None:
    if p.existence == "existing" and not (p.frequency and p.nature and p.automation):
        raise AuditInvalid("Un contrôle existant est caractérisé : fréquence, nature (préventif / détectif) et mode.")
    if p.performer_user_id and p.performer_user_id == p.supervisor_user_id:
        raise AuditInvalid("L'exécutant et le superviseur sont deux personnes distinctes.")
    svc.in_company(db, ControlObjective, p.objective_id, ctx.company_id, "Objectif")
    return _object_domain(db, ctx, p.domain_id, p.process_id)


@router.get(C + "/controls", summary="Catalogue des contrôles (avec la conclusion des derniers tests revus)")
def list_controls(
    ctx: Ic,
    db: Db,
    domain_id: uuid.UUID | None = None,
    process_id: uuid.UUID | None = None,
    conclusion: str | None = None,
    existence: str | None = None,
    q: str | None = None,
):
    reg = svc.filtered(svc.registry(db, ctx.company_id), domain_id, process_id)
    st = svc.status_map(reg.controls, svc.visible_tests(db, ctx.company_id, [c.id for c in reg.controls]))
    n: dict = {}
    for lk in reg.links:
        n[lk.control_id] = n.get(lk.control_id, 0) + 1
    out = [svc.control_out(c, st[str(c.id)], n.get(c.id, 0)) for c in reg.controls]
    if conclusion:
        out = [c for c in out if c["conclusion"] == conclusion]
    if existence:
        out = [c for c in out if c["existence"] == existence]
    if q:
        ql = q.lower()
        out = [c for c in out if ql in (c["code"] + " " + c["title"]).lower()]
    return out


@router.post(C + "/controls", status_code=status.HTTP_201_CREATED)
def create_control(p: ControlIn, request: Request, ctx: Ic, db: Db):
    dom = _check_control(db, ctx, p)
    ctx.require_manage(dom)
    c = Control(
        id=uuid.uuid4(),
        organization_id=ctx.organization_id,
        company_id=ctx.company_id,
        **{**_clean(p.model_dump()), "domain_id": dom},
    )
    db.add(c)
    db.flush()
    _log(db, request, ctx, "ic.control.create", "controls", c.id, {"code": c.code})
    return svc.control_out(c, None)


@router.get(C + "/controls/{control_id}", summary="Fiche du contrôle")
def get_control(control_id: uuid.UUID, ctx: Ic, db: Db):
    c = svc.in_company(db, Control, control_id, ctx.company_id, "Contrôle")
    tests = svc.visible_tests(db, ctx.company_id, [c.id])
    st = svc.status_map([c], tests)[str(c.id)]
    links = list(db.scalars(select(ControlRisk).where(ControlRisk.control_id == c.id)))
    risks = {r.id: r for r in db.scalars(select(Risk).where(Risk.id.in_([lk.risk_id for lk in links])))} if links else {}
    fl = list(
        db.scalars(select(IcFrameworkLink).where(IcFrameworkLink.object_type == "control", IcFrameworkLink.object_id == c.id))
    )
    items = (
        {i.id: i for i in db.scalars(select(MethodologyItem).where(MethodologyItem.id.in_([x.item_id for x in fl])))}
        if fl
        else {}
    )
    vers = (
        {
            v.id: v
            for v in db.scalars(
                select(MethodologyVersion).where(MethodologyVersion.id.in_({i.version_id for i in items.values()}))
            )
        }
        if items
        else {}
    )
    execs = list(
        db.scalars(
            select(ControlExecution)
            .where(ControlExecution.control_id == c.id)
            .order_by(ControlExecution.occurrence_date.desc())
            .limit(100)
        )
    )
    ppl = people(db, [e.performed_by for e in execs] + [e.supervised_by for e in execs])
    return {
        **svc.control_out(c, st, len(links)),
        "can_manage": ctx.manages(c.domain_id),
        "can_execute": c.performer_user_id == ctx.user.id
        or ctx.manages(c.domain_id)
        or any(r == "control_performer" and d in (None, c.domain_id) for r, d in ctx.roles),
        "can_supervise": c.supervisor_user_id == ctx.user.id
        or ctx.manages(c.domain_id)
        or any(r == "supervisor" and d in (None, c.domain_id) for r, d in ctx.roles),
        "risks_covered": [
            {
                **row(lk, ("risk_id", "coverage", "assertion_codes", "rationale")),
                "code": risks[lk.risk_id].code,
                "title": risks[lk.risk_id].title,
            }
            for lk in links
            if lk.risk_id in risks
        ],
        "framework_links": [
            {
                "id": str(x.id),
                "item_id": str(x.item_id),
                "code": items[x.item_id].code,
                "label": items[x.item_id].label,
                "item_type": items[x.item_id].item_type,
                "framework": f"{vers[items[x.item_id].version_id].name} {vers[items[x.item_id].version_id].version_label}",
            }
            for x in fl
            if x.item_id in items
        ],
        "tests": [_test_brief(t) for t in tests],
        "executions": [
            {
                **row(
                    e,
                    (
                        "id",
                        "occurrence_label",
                        "occurrence_date",
                        "outcome",
                        "comment",
                        "exceptions",
                        "performed_at",
                        "evidence_filename",
                        "evidence_sha256",
                        "supervision_status",
                        "supervised_at",
                        "supervision_comment",
                    ),
                ),
                "performed_by": ppl.get(str(e.performed_by)),
                "supervised_by": ppl.get(str(e.supervised_by)),
                "performed_by_id": str(e.performed_by),
            }
            for e in execs
        ],
        "deficiencies": svc.deficiencies(db, ctx.company_id, {c.id}),
    }


@router.patch(C + "/controls/{control_id}")
def update_control(control_id: uuid.UUID, p: ControlIn, request: Request, ctx: Ic, db: Db):
    c = svc.in_company(db, Control, control_id, ctx.company_id, "Contrôle")
    ctx.require_manage(c.domain_id)
    dom = _check_control(db, ctx, p)
    ctx.require_manage(dom)
    for k, v in {**_clean(p.model_dump()), "domain_id": dom}.items():
        setattr(c, k, v)
    db.flush()
    _log(db, request, ctx, "ic.control.update", "controls", c.id, {"version": c.version})
    return svc.control_out(c, None)


@router.get(C + "/controls/{control_id}/history", summary="Historique du contrôle (versions, liens, exécutions)")
def control_history(control_id: uuid.UUID, ctx: Ic, db: Db):
    svc.in_company(db, Control, control_id, ctx.company_id, "Contrôle")
    hs = list(db.scalars(select(IcHistory).where(IcHistory.object_id == control_id).order_by(IcHistory.changed_at.desc())))
    ppl = people(db, [h.changed_by for h in hs])
    out = []
    for h in hs:
        changed = sorted(
            k
            for k in set((h.before or {}) | (h.after or {}))
            if (h.before or {}).get(k) != (h.after or {}).get(k) and k not in ("updated_at", "updated_by")
        )
        out.append(
            {
                **row(h, ("object_type", "action", "reason", "changed_at")),
                "changed_fields": changed,
                "version": (h.after or {}).get("version"),
                "changed_by": ppl.get(str(h.changed_by)),
            }
        )
    return out


class LinkIn(BaseModel):
    risk_id: uuid.UUID
    coverage: Literal["full", "partial"] = "full"
    assertion_codes: list[str] = Field(default_factory=list, max_length=20)
    rationale: str | None = Field(default=None, max_length=2000)


@router.post(
    C + "/controls/{control_id}/risks",
    status_code=status.HTTP_201_CREATED,
    summary="Associer le contrôle à un risque (matrice N-N)",
)
def link_risk(control_id: uuid.UUID, p: LinkIn, request: Request, ctx: Ic, db: Db):
    c = svc.in_company(db, Control, control_id, ctx.company_id, "Contrôle")
    ctx.require_manage(c.domain_id)
    svc.in_company(db, Risk, p.risk_id, ctx.company_id, "Risque")
    if db.get(ControlRisk, (c.id, p.risk_id)):
        raise Conflict("Ce contrôle couvre déjà ce risque.")
    lk = ControlRisk(
        organization_id=ctx.organization_id,
        company_id=ctx.company_id,
        control_id=c.id,
        created_by=ctx.user.id,
        **_clean(p.model_dump()),
    )
    db.add(lk)
    db.flush()
    _log(db, request, ctx, "ic.control_risk.add", "control_risks", c.id, p.model_dump(mode="json"))
    return row(lk, ("control_id", "risk_id", "coverage"))


@router.delete(C + "/controls/{control_id}/risks/{risk_id}", status_code=status.HTTP_204_NO_CONTENT)
def unlink_risk(control_id: uuid.UUID, risk_id: uuid.UUID, request: Request, ctx: Ic, db: Db):
    c = svc.in_company(db, Control, control_id, ctx.company_id, "Contrôle")
    ctx.require_manage(c.domain_id)
    lk = db.get(ControlRisk, (control_id, risk_id))
    if lk is None:
        raise NotFound("Association introuvable")
    db.delete(lk)
    db.flush()
    _log(db, request, ctx, "ic.control_risk.remove", "control_risks", control_id, {"risk_id": risk_id})
    return Response(status_code=status.HTTP_204_NO_CONTENT)


class FwLinkIn(BaseModel):
    object_type: Literal["control", "risk", "objective", "domain"]
    object_id: uuid.UUID
    item_id: uuid.UUID


FW_MODELS = {
    "control": (Control, "Contrôle"),
    "risk": (Risk, "Risque"),
    "objective": (ControlObjective, "Objectif"),
    "domain": (IcDomain, "Domaine"),
}


@router.post(
    C + "/framework-links",
    status_code=status.HTTP_201_CREATED,
    summary="Rattacher un objet à une composante, un principe, une exigence ou un critère",
)
def add_fw_link(p: FwLinkIn, request: Request, ctx: Ic, db: Db):
    model, what = FW_MODELS[p.object_type]
    obj = svc.in_company(db, model, p.object_id, ctx.company_id, what)
    ctx.require_manage(obj.id if p.object_type == "domain" else obj.domain_id)
    lk = IcFrameworkLink(id=uuid.uuid4(), organization_id=ctx.organization_id, company_id=ctx.company_id, **p.model_dump())
    db.add(lk)
    db.flush()
    _log(db, request, ctx, "ic.framework_link.add", "ic_framework_links", lk.id, p.model_dump(mode="json"))
    return row(lk, ("id", "object_type", "object_id", "item_id"))


@router.delete(C + "/framework-links/{link_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_fw_link(link_id: uuid.UUID, request: Request, ctx: Ic, db: Db):
    lk = svc.in_company(db, IcFrameworkLink, link_id, ctx.company_id, "Rattachement")
    model, what = FW_MODELS[lk.object_type]
    obj = db.get(model, lk.object_id)
    ctx.require_manage(lk.object_id if lk.object_type == "domain" else (obj.domain_id if obj else None))
    db.delete(lk)
    db.flush()
    _log(db, request, ctx, "ic.framework_link.remove", "ic_framework_links", link_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(C + "/matrix", summary="Matrice risques-contrôles")
def get_matrix(ctx: Ic, db: Db, domain_id: uuid.UUID | None = None, process_id: uuid.UUID | None = None):
    reg = svc.filtered(svc.registry(db, ctx.company_id), domain_id, process_id)
    tests = svc.visible_tests(db, ctx.company_id, [c.id for c in reg.controls])
    st = svc.status_map(reg.controls, tests)
    m = ic.matrix(
        svc.risk_refs(reg.risks), svc.control_refs(reg.controls), svc.link_dicts(reg.links), st, svc.evidence_counts(db, tests)
    )
    procs = {str(p.id): p for p in reg.processes}
    objs = {str(o.id): o for o in reg.objectives}
    risks = {str(r.id): r for r in reg.risks}
    for r in m["rows"]:
        rk = risks.get(r["risk_id"])
        p = procs.get(str(rk.process_id)) if rk and rk.process_id else None
        o = objs.get(str(rk.objective_id)) if rk and rk.objective_id else None
        r.update(
            process=f"{p.code} — {p.name}" if p else None,
            objective=o.statement if o else None,
            conclusion_label=ic.CONCLUSION_LABELS.get(r.get("conclusion") or "") if r.get("control_id") else None,
            indicator_label=ic.INDICATOR_LABELS[r["indicator"]],
        )
    return js(m)


@router.get(
    C + "/deficiency-candidates",
    summary="Points à examiner (contrôles inefficaces, attendus absents, risques non couverts) sans déficience",
)
def deficiency_candidates(ctx: Ic, db: Db, domain_id: uuid.UUID | None = None):
    reg = svc.filtered(svc.registry(db, ctx.company_id), domain_id)
    st = svc.status_map(reg.controls, svc.visible_tests(db, ctx.company_id, [c.id for c in reg.controls]))
    m = ic.matrix(svc.risk_refs(reg.risks), svc.control_refs(reg.controls), svc.link_dicts(reg.links), st)
    defs = svc.deficiencies(db, ctx.company_id)
    return ic.deficiency_candidates(
        svc.control_refs(reg.controls), st, {d["control_id"] for d in defs if d["control_id"]}, m["uncovered_risks"]
    )


# ======================================================================== exécutions
@router.post(
    C + "/controls/{control_id}/executions",
    status_code=status.HTTP_201_CREATED,
    summary="Documenter l'exécution d'un contrôle (preuve facultative, empreinte SHA-256)",
)
async def add_execution(
    control_id: uuid.UUID,
    request: Request,
    ctx: Ic,
    db: Db,
    occurrence_label: str = Form(..., min_length=1, max_length=300),
    occurrence_date: date = Form(...),
    outcome: Literal["performed", "performed_with_exceptions", "not_performed"] = Form(...),
    comment: str | None = Form(None, max_length=4000),
    exceptions: str | None = Form(None, max_length=4000),
    file: UploadFile | None = File(None),
):
    c = svc.in_company(db, Control, control_id, ctx.company_id, "Contrôle")
    eid = uuid.uuid4()
    x = ControlExecution(
        id=eid,
        organization_id=ctx.organization_id,
        company_id=ctx.company_id,
        control_id=c.id,
        occurrence_label=occurrence_label.strip(),
        occurrence_date=occurrence_date,
        outcome=outcome,
        comment=(comment or "").strip() or None,
        exceptions=(exceptions or "").strip() or None,
        performed_by=ctx.user.id,
    )
    data = None
    if file is not None and file.filename:
        data = await file.read()
        try:
            vf = validate_evidence(file.filename, data)
        except FileRejected as exc:
            raise AuditInvalid(str(exc)) from exc
        name = safe_filename(file.filename)
        x.evidence_path = f"{ctx.organization_id}/{ctx.company_id}/{eid}_{name}"
        x.evidence_filename, x.evidence_mime, x.evidence_size, x.evidence_sha256 = name, vf.mime_type, vf.size_bytes, vf.sha256
    db.add(x)
    db.flush()  # droits de l'exécutant contrôlés par la base avant le stockage
    if data is not None:
        get_storage().upload(EXEC_BUCKET, x.evidence_path, data, x.evidence_mime)
    _log(
        db,
        request,
        ctx,
        "ic.execution.add",
        "control_executions",
        eid,
        {"control_id": c.id, "occurrence_date": occurrence_date, "sha256": x.evidence_sha256},
    )
    return row(x, ("id", "occurrence_label", "occurrence_date", "outcome", "supervision_status", "evidence_sha256"))


class SuperviseIn(BaseModel):
    decision: Literal["approved", "rejected"]
    comment: str | None = Field(default=None, max_length=4000)


@router.post(C + "/executions/{execution_id}/supervise", summary="Superviser une exécution (autre personne que l'exécutant)")
def supervise(execution_id: uuid.UUID, p: SuperviseIn, request: Request, ctx: Ic, db: Db):
    x = svc.in_company(db, ControlExecution, execution_id, ctx.company_id, "Exécution")
    if x.performed_by == ctx.user.id:
        raise Forbidden("La supervision est faite par une autre personne que l'exécutant.")
    if p.decision == "rejected" and len((p.comment or "").strip()) < 3:
        raise AuditInvalid("Un rejet est motivé.")
    x.supervision_status, x.supervised_by, x.supervision_comment = p.decision, ctx.user.id, (p.comment or "").strip() or None
    db.flush()
    _log(db, request, ctx, f"ic.execution.{p.decision}", "control_executions", x.id)
    return row(x, ("id", "supervision_status", "supervised_at"))


@router.get(C + "/executions/{execution_id}/download", summary="Lien signé vers la preuve d'exécution (5 min)")
def download_execution(execution_id: uuid.UUID, request: Request, ctx: Ic, db: Db):
    x = svc.in_company(db, ControlExecution, execution_id, ctx.company_id, "Exécution")
    if not x.evidence_path:
        raise NotFound("Aucune preuve déposée")
    _log(db, request, ctx, "ic.execution.download", "control_executions", x.id, {"sha256": x.evidence_sha256})
    return {
        "url": get_storage().signed_url(EXEC_BUCKET, x.evidence_path, download_name=x.evidence_filename),
        "sha256": x.evidence_sha256,
    }


# ======================================================================== pilotage
@router.get(C + "/dashboard", summary="Tableau de bord du contrôle interne (calculé sur les données, filtrable)")
def dashboard(
    ctx: Ic, db: Db, domain_id: uuid.UUID | None = None, process_id: uuid.UUID | None = None, cycle_code: str | None = None
):
    return js(svc.dashboard(db, ctx, domain_id, process_id, cycle_code))


@router.get(C + "/tests", summary="Tests de contrôles visibles (dossiers dont vous êtes membre, tests revus)")
def company_tests(ctx: Ic, db: Db, control_id: uuid.UUID | None = None, status_filter: str | None = None):
    ts = svc.visible_tests(db, ctx.company_id, [control_id] if control_id else None)
    if status_filter:
        ts = [t for t in ts if t.status == status_filter]
    ctl = {c.id: c for c in db.scalars(select(Control).where(Control.company_id == ctx.company_id))}
    from app.models import Engagement

    engs = {e.id: e for e in db.scalars(select(Engagement).where(Engagement.company_id == ctx.company_id))}
    return [
        {
            **_test_brief(t),
            "control": f"{ctl[t.control_id].code} — {ctl[t.control_id].title}" if t.control_id in ctl else None,
            "engagement_reference": engs[t.engagement_id].reference if t.engagement_id in engs else None,
        }
        for t in ts
    ]


@router.get(C + "/assessments", summary="Évaluations (approuvées, ou des missions dont vous êtes membre)")
def company_assessments(ctx: Ic, db: Db):
    return [
        row(a, svc.ASSESSMENT_FIELDS)
        for a in db.scalars(
            select(IcAssessment)
            .where(IcAssessment.company_id == ctx.company_id)
            .order_by(IcAssessment.as_of_date.desc(), IcAssessment.reference)
        )
    ]


@router.get(C + "/deficiencies", summary="Déficiences de contrôle interne et leur cycle de traitement")
def company_deficiencies(ctx: Ic, db: Db, domain_id: uuid.UUID | None = None, stage: str | None = None):
    ids = None
    if domain_id:
        ids = {
            c.id for c in db.scalars(select(Control).where(Control.company_id == ctx.company_id, Control.domain_id == domain_id))
        }
    out = svc.deficiencies(db, ctx.company_id, ids)
    return [d for d in out if not stage or d["stage"] == stage]


@router.get(C + "/action-plans", summary="Plans de remédiation et suivi des actions")
def company_plans(ctx: Ic, db: Db, overdue: bool = False, status_filter: str | None = None):
    out = svc.plans_of(svc.deficiencies(db, ctx.company_id))
    if overdue:
        out = [a for a in out if a["overdue"]]
    if status_filter:
        out = [a for a in out if a["status"] == status_filter]
    return sorted(out, key=lambda a: a["due_date"])


@router.get(C + "/reports/{kind}", summary="Rapport structuré (préparé pour les exports du lot 11)")
def get_report(
    kind: str,
    ctx: Ic,
    db: Db,
    domain_id: uuid.UUID | None = None,
    process_id: uuid.UUID | None = None,
    cycle_code: str | None = None,
    engagement_id: uuid.UUID | None = None,
):
    return svc.build_report(db, ctx, kind, domain_id, process_id, cycle_code, engagement_id)


@router.get(C + "/reports/{kind}/{section_key}.csv", summary="Section d'un rapport en CSV")
def get_report_csv(
    kind: str,
    section_key: str,
    request: Request,
    ctx: Ic,
    db: Db,
    domain_id: uuid.UUID | None = None,
    process_id: uuid.UUID | None = None,
    cycle_code: str | None = None,
):
    rep = svc.build_report(db, ctx, kind, domain_id, process_id, cycle_code)
    sec = next((s for s in rep["sections"] if s["key"] == section_key), None)
    if sec is None:
        raise NotFound("Section introuvable")
    buf = io.StringIO()
    csv.writer(buf, delimiter=";").writerows(ic.csv_rows(sec))
    _log(db, request, ctx, "ic.report.export", "reports", None, {"kind": kind, "section": section_key})
    return Response(
        content=("﻿" + buf.getvalue()).encode("utf-8"),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=controle-interne-{kind}-{section_key}.csv"},
    )


@router.get(C + "/history", summary="Historique du dispositif")
def history(ctx: Ic, db: Db, limit: int = 200):
    hs = list(
        db.scalars(
            select(IcHistory)
            .where(IcHistory.company_id == ctx.company_id)
            .order_by(IcHistory.changed_at.desc())
            .limit(min(limit, 1000))
        )
    )
    ppl = people(db, [h.changed_by for h in hs])
    return [
        {
            **row(h, ("object_type", "object_id", "action", "reason", "changed_at")),
            "label": (h.after or h.before or {}).get("code") or (h.after or h.before or {}).get("reference"),
            "changed_by": ppl.get(str(h.changed_by)),
        }
        for h in hs
    ]


# ======================================================================== mission : programme, tests
def _ic_ctx(ctx: EngagementContext) -> None:
    ctx.require("read_dossier")


def _test(db: Session, ctx: EngagementContext, test_id: uuid.UUID) -> ControlTest:
    return owned(db, ctx, ControlTest, test_id, "Test")


def _test_out(db: Session, ctx: EngagementContext, t: ControlTest) -> dict:
    items = list(
        db.scalars(
            select(ControlTestItem)
            .where(ControlTestItem.test_id == t.id)
            .order_by(ControlTestItem.selection_order.nulls_last(), ControlTestItem.item_ref)
        )
    )
    links = list(
        db.scalars(
            select(EvidenceLink).where(
                ((EvidenceLink.object_type == "control_test") & (EvidenceLink.object_id == t.id))
                | (
                    (EvidenceLink.object_type == "control_test_item")
                    & (EvidenceLink.object_id.in_([i.id for i in items] or [uuid.uuid4()]))
                )
            )
        )
    )
    ev = (
        {e.id: e for e in db.scalars(select(EvidenceItem).where(EvidenceItem.id.in_([lk.evidence_id for lk in links])))}
        if links
        else {}
    )
    c = db.get(Control, t.control_id)
    answers = t.design_answers if t.test_type == "design" else t.operating_answers
    chk = ic.check_test(
        test_type=t.test_type,
        answers=answers or {},
        items=[i.result for i in items],
        sample_size=t.sample_size,
        tolerable=t.tolerable_exceptions,
        has_period=bool(t.period_start and t.period_end),
        has_evidence=bool(links),
        rationale=t.conclusion_rationale,
    )
    ppl = people(db, [t.prepared_by, t.reviewed_by, t.created_by, t.responsible_user_id] + [i.tested_by for i in items])
    return {
        **row(t, svc.TEST_FIELDS),
        "control": svc.control_out(c, None) if c else None,
        "criteria": ic.criteria(t.test_type),
        "conclusion_label": ic.CONCLUSION_LABELS.get(t.conclusion or ""),
        "prepared_by_user": ppl.get(str(t.prepared_by)),
        "reviewed_by_user": ppl.get(str(t.reviewed_by)),
        "responsible_user": ppl.get(str(t.responsible_user_id)),
        "items": [{**row(i, svc.ITEM_FIELDS), "tested_by_user": ppl.get(str(i.tested_by))} for i in items],
        "evidence": [
            {
                "link_id": str(lk.id),
                "object_type": lk.object_type,
                "object_id": str(lk.object_id),
                "evidence_id": str(lk.evidence_id),
                "title": ev[lk.evidence_id].title,
                "sha256": ev[lk.evidence_id].sha256,
            }
            for lk in links
            if lk.evidence_id in ev
        ],
        "check": {
            "items": chk.items,
            "pending": chk.pending,
            "compliant": chk.compliant,
            "exceptions": chk.exceptions,
            "not_applicable": chk.not_applicable,
            "missing": chk.missing,
            "negative": chk.negative,
            "allowed": chk.allowed,
            "blockers": chk.blockers,
        },
    }


@router.get(E + "/tests", summary="Tests de contrôles de la mission")
def list_tests(ctx: Ctx, db: Db):
    _ic_ctx(ctx)
    ts = list(
        db.scalars(select(ControlTest).where(ControlTest.engagement_id == ctx.engagement.id).order_by(ControlTest.reference))
    )
    ctl = {c.id: c for c in db.scalars(select(Control).where(Control.company_id == ctx.engagement.company_id))}
    return [
        {
            **_test_brief(t),
            "control": f"{ctl[t.control_id].code} — {ctl[t.control_id].title}" if t.control_id in ctl else None,
            "procedure_id": str(t.procedure_id) if t.procedure_id else None,
            "sample_size": t.sample_size,
        }
        for t in ts
    ]


class TestIn(BaseModel):
    control_id: uuid.UUID
    reference: str = Field(min_length=1, max_length=60)
    test_type: Literal["design", "operating"]
    test_methods: list[
        Literal[
            "document_review",
            "observation",
            "inquiry",
            "inspection",
            "reconciliation",
            "recalculation",
            "reperformance",
            "data_analysis",
        ]
    ] = Field(min_length=1)
    risk_id: uuid.UUID | None = None
    procedure_id: uuid.UUID | None = None
    workpaper_id: uuid.UUID | None = None
    objective: str | None = Field(default=None, max_length=2000)
    test_procedure: str = Field(min_length=1, max_length=8000)
    responsible_user_id: uuid.UUID | None = None
    period_start: date | None = None
    period_end: date | None = None
    population_description: str | None = Field(default=None, max_length=2000)
    population_size: int | None = Field(default=None, ge=0)
    population_source: Literal["manual", "executions", "file"] | None = None
    selection_method: Literal["all", "random", "systematic", "judgmental"] | None = None
    sample_size: int | None = Field(default=None, ge=1)
    sample_size_basis: str | None = Field(default=None, max_length=2000)
    acceptance_criteria: str | None = Field(default=None, max_length=2000)
    tolerable_exceptions: int | None = Field(default=None, ge=0)
    expected_result: str | None = Field(default=None, max_length=2000)


class TestUpdate(TestIn):
    control_id: uuid.UUID | None = None  # type: ignore[assignment]
    design_answers: dict | None = None
    operating_answers: dict | None = None
    results_summary: str | None = Field(default=None, max_length=8000)
    exceptions_summary: str | None = Field(default=None, max_length=8000)
    conclusion: Literal["effective", "partially_effective", "ineffective", "not_tested", "not_applicable"] | None = None
    conclusion_rationale: str | None = Field(default=None, max_length=8000)


def _check_test_in(db: Session, ctx: EngagementContext, p: TestIn) -> None:
    if p.sample_size is not None and not (p.sample_size_basis or "").strip():
        raise AuditInvalid("Indiquez le fondement de la taille d'échantillon (règle de la méthodologie ou jugement motivé).")
    if p.period_start and p.period_end and p.period_end < p.period_start:
        raise AuditInvalid("Période incohérente.")
    cid = ctx.engagement.company_id
    if p.control_id:
        svc.in_company(db, Control, p.control_id, cid, "Contrôle")
    svc.in_company(db, Risk, p.risk_id, cid, "Risque")
    if p.procedure_id:
        owned(db, ctx, Procedure, p.procedure_id, "Procédure")


@router.post(E + "/tests", status_code=status.HTTP_201_CREATED)
def create_test(p: TestIn, request: Request, ctx: Ctx, db: Db):
    ctx.require("edit_procedures")
    _check_test_in(db, ctx, p)
    t = ControlTest(
        id=uuid.uuid4(),
        organization_id=ctx.engagement.organization_id,
        engagement_id=ctx.engagement.id,
        company_id=ctx.engagement.company_id,
        created_by=ctx.user.id,
        **_clean(p.model_dump()),
    )
    db.add(t)
    db.flush()
    _elog(db, request, ctx, "ic.test.create", "control_tests", t.id, {"reference": t.reference})
    return _test_out(db, ctx, t)


@router.get(E + "/tests/{test_id}")
def get_test(test_id: uuid.UUID, ctx: Ctx, db: Db):
    _ic_ctx(ctx)
    return {**_test_out(db, ctx, _test(db, ctx, test_id)), "capabilities": ctx.caps, "me": str(ctx.user.id)}


@router.patch(E + "/tests/{test_id}")
def update_test(test_id: uuid.UUID, p: TestUpdate, request: Request, ctx: Ctx, db: Db):
    ctx.require("edit_procedures")
    t = _test(db, ctx, test_id)
    if t.status not in ("planned", "in_progress"):
        raise Conflict("Test préparé ou revu : renvoyez-le en cours (ou rouvrez-le) pour le modifier.")
    _check_test_in(db, ctx, p)
    data = _clean(p.model_dump(exclude_unset=True, exclude={"control_id"}))
    for k in ("design_answers", "operating_answers"):
        if k in data and data[k] is not None:
            try:
                ic.check_test(
                    test_type="design" if k == "design_answers" else "operating",
                    answers=data[k],
                    items=[],
                    sample_size=None,
                    tolerable=None,
                    has_period=True,
                    has_evidence=True,
                    rationale="ok",
                )
            except ValueError as exc:
                raise AuditInvalid(str(exc)) from exc
        elif k in data:
            data[k] = {}
    for k, v in data.items():
        setattr(t, k, v)
    if t.status == "planned":
        t.status = "in_progress"
    db.flush()
    _elog(db, request, ctx, "ic.test.update", "control_tests", t.id, {"fields": sorted(data)})
    return _test_out(db, ctx, t)


@router.delete(E + "/tests/{test_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_test(test_id: uuid.UUID, request: Request, ctx: Ctx, db: Db):
    ctx.require("plan")
    t = _test(db, ctx, test_id)
    db.delete(t)
    db.flush()
    _elog(db, request, ctx, "ic.test.delete", "control_tests", test_id, {"reference": t.reference})
    return Response(status_code=status.HTTP_204_NO_CONTENT)


class TestAction(BaseModel):
    action: Literal["prepare", "review", "return", "reopen"]
    reason: str | None = Field(default=None, max_length=2000)


@router.post(E + "/tests/{test_id}/status", summary="Préparer, revoir, renvoyer en cours, rouvrir (motivé)")
def test_status(test_id: uuid.UUID, p: TestAction, request: Request, ctx: Ctx, db: Db):
    t = _test(db, ctx, test_id)
    if p.action == "prepare":
        ctx.require("sign_preparer")
        out = _test_out(db, ctx, t)
        reasons = out["check"]["blockers"].get(t.conclusion or "", ["Choisissez une conclusion."])
        if reasons:
            raise AuditInvalid("Préparation impossible : " + " ".join(reasons))
        t.status, t.prepared_by = "prepared", ctx.user.id
    elif p.action == "review":
        ctx.require("sign_reviewer")
        if t.prepared_by == ctx.user.id:
            raise Forbidden("La revue est faite par une autre personne que le préparateur.")
        t.status, t.reviewed_by = "reviewed", ctx.user.id
    elif p.action == "return":
        ctx.require("sign_preparer")
        t.status = "in_progress"
    else:
        ctx.require("approve_ic")
        if len((p.reason or "").strip()) < 3:
            raise AuditInvalid("La réouverture d'un test revu est motivée.")
        t.status, t.reopen_reason = "in_progress", p.reason.strip()
    db.flush()
    _elog(db, request, ctx, f"ic.test.{p.action}", "control_tests", t.id, {"reason": p.reason})
    return _test_out(db, ctx, t)


class ItemIn(BaseModel):
    item_ref: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    item_date: date | None = None
    amount: Decimal | None = None


class ItemsIn(BaseModel):
    items: list[ItemIn] = Field(min_length=1, max_length=2000)


@router.post(E + "/tests/{test_id}/items", status_code=status.HTTP_201_CREATED, summary="Ajouter des éléments testés")
def add_items(test_id: uuid.UUID, p: ItemsIn, request: Request, ctx: Ctx, db: Db):
    ctx.require("edit_procedures")
    t = _test(db, ctx, test_id)
    n0 = len(list(db.scalars(select(ControlTestItem.id).where(ControlTestItem.test_id == t.id))))
    for k, it in enumerate(p.items, start=1):
        db.add(
            ControlTestItem(
                id=uuid.uuid4(),
                organization_id=t.organization_id,
                engagement_id=t.engagement_id,
                test_id=t.id,
                selection_order=n0 + k,
                **_clean(it.model_dump()),
            )
        )
    db.flush()
    _elog(db, request, ctx, "ic.test.items_add", "control_tests", t.id, {"count": len(p.items)})
    return _test_out(db, ctx, t)


class SelectIn(BaseModel):
    source: Literal["executions", "list"]
    method: Literal["all", "random", "systematic", "judgmental"]
    size: int | None = Field(default=None, ge=1)
    seed: int | None = None
    execution_ids: list[uuid.UUID] = Field(default_factory=list, max_length=5000)
    population_text: str | None = Field(default=None, max_length=2_000_000)  # lignes « réf;libellé;date;montant »
    approved_only: bool = True


def _parse_population(txt: str) -> list[ItemIn]:
    out, seen = [], set()
    for n, line in enumerate(txt.splitlines(), start=1):
        if not line.strip():
            continue
        cells = [c.strip() for c in line.split(";")] + ["", "", ""]
        ref = cells[0]
        if ref in seen:
            raise AuditInvalid(f"Ligne {n} : référence « {ref} » en double.")
        seen.add(ref)
        try:
            d = date.fromisoformat(cells[2]) if cells[2] else None
            amt = Decimal(cells[3].replace(" ", "").replace(",", ".")) if cells[3] else None
        except (ValueError, InvalidOperation) as exc:
            raise AuditInvalid(f"Ligne {n} : date (AAAA-MM-JJ) ou montant illisible.") from exc
        out.append(ItemIn(item_ref=ref[:200], description=cells[1] or None, item_date=d, amount=amt))
    if not out:
        raise AuditInvalid("Population vide.")
    return out


@router.post(
    E + "/tests/{test_id}/select",
    summary="Sélectionner les éléments (moteur d'échantillonnage du projet ; taille fournie par l'utilisateur)",
)
def select_items(test_id: uuid.UUID, p: SelectIn, request: Request, ctx: Ctx, db: Db):
    ctx.require("edit_procedures")
    t = _test(db, ctx, test_id)
    if db.scalar(select(ControlTestItem.id).where(ControlTestItem.test_id == t.id).limit(1)):
        raise Conflict("Des éléments existent déjà : supprimez-les avant une nouvelle sélection.")
    if p.source == "executions":
        q = select(ControlExecution).where(ControlExecution.control_id == t.control_id)
        if t.period_start:
            q = q.where(ControlExecution.occurrence_date >= t.period_start)
        if t.period_end:
            q = q.where(ControlExecution.occurrence_date <= t.period_end)
        if p.approved_only:
            q = q.where(ControlExecution.supervision_status == "approved")
        pop = list(db.scalars(q.order_by(ControlExecution.occurrence_date, ControlExecution.id)))
        cands = [
            (
                str(x.id),
                ItemIn(
                    item_ref=f"{x.occurrence_date.isoformat()} {x.occurrence_label}"[:200],
                    description=x.comment,
                    item_date=x.occurrence_date,
                ),
                x.id,
            )
            for x in pop
        ]
    else:
        lst = _parse_population(p.population_text or "")
        cands = [(it.item_ref, it, None) for it in lst]
    if not cands:
        raise AuditInvalid("Population vide sur la période du test.")
    if p.method in ("random", "systematic") and (p.size is None or p.seed is None):
        raise AuditInvalid("Tirage aléatoire ou systématique : taille et graine requises (aucune taille n'est proposée).")
    if p.method in ("random", "systematic") and t.sample_size and p.size != t.sample_size:
        raise AuditInvalid(f"Taille demandée différente de celle du test ({t.sample_size}).")
    pop_items = [fa.PopItem(k, Decimal(0)) for k, _, _ in cands]
    try:
        if p.method == "all":
            chosen = [k for k, _, _ in cands]
            params = {}
        elif p.method == "random":
            s = fa.select_random(pop_items, p.size, p.seed)
            chosen, params = s.item_ids, s.parameters
        elif p.method == "systematic":
            s = fa.select_systematic(pop_items, p.size, p.seed)
            chosen, params = s.item_ids, s.parameters
        else:
            wanted = {str(i) for i in p.execution_ids}
            chosen = [k for k, _, _ in cands if k in wanted] if p.source == "executions" else [k for k, _, _ in cands]
            if not chosen:
                raise AuditInvalid("Sélection par jugement : indiquez les éléments retenus.")
            params = {}
    except ValueError as exc:
        raise AuditInvalid(str(exc)) from exc
    digest = hashlib.sha256("\n".join(k for k, _, _ in cands).encode()).hexdigest()
    by_key = {k: (it, xid) for k, it, xid in cands}
    for order, k in enumerate(chosen, start=1):
        it, xid = by_key[k]
        db.add(
            ControlTestItem(
                id=uuid.uuid4(),
                organization_id=t.organization_id,
                engagement_id=t.engagement_id,
                test_id=t.id,
                execution_id=xid,
                selection_order=order,
                **_clean(it.model_dump()),
            )
        )
    t.selection_method = p.method
    t.population_source = "executions" if p.source == "executions" else (t.population_source or "manual")
    t.population_size = len(cands)
    t.selection_params = js(
        {
            **params,
            "source": p.source,
            "population_sha256": digest,
            "selected": len(chosen),
            "approved_only": p.approved_only if p.source == "executions" else None,
        }
    )
    if t.status == "planned":
        t.status = "in_progress"
    db.flush()
    _elog(db, request, ctx, "ic.test.select", "control_tests", t.id, t.selection_params)
    return _test_out(db, ctx, t)


class ItemResult(BaseModel):
    result: Literal["pending", "compliant", "exception", "not_applicable"]
    exception_description: str | None = Field(default=None, max_length=4000)
    na_reason: str | None = Field(default=None, max_length=2000)


@router.patch(E + "/test-items/{item_id}", summary="Résultat d'un élément testé")
def set_item(item_id: uuid.UUID, p: ItemResult, request: Request, ctx: Ctx, db: Db):
    ctx.require("edit_procedures")
    it = owned(db, ctx, ControlTestItem, item_id, "Élément")
    if p.result == "exception" and not (p.exception_description or "").strip():
        raise AuditInvalid("Décrivez l'exception constatée.")
    if p.result == "not_applicable" and not (p.na_reason or "").strip():
        raise AuditInvalid("Justifiez le caractère non applicable.")
    for k, v in _clean(p.model_dump()).items():
        setattr(it, k, v)
    db.flush()
    _elog(db, request, ctx, "ic.test.item_result", "control_test_items", it.id, {"result": p.result})
    return row(it, svc.ITEM_FIELDS)


@router.delete(E + "/test-items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_item(item_id: uuid.UUID, request: Request, ctx: Ctx, db: Db):
    ctx.require("edit_procedures")
    it = owned(db, ctx, ControlTestItem, item_id, "Élément")
    db.delete(it)
    db.flush()
    _elog(db, request, ctx, "ic.test.item_delete", "control_test_items", item_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


class ProgramIn(BaseModel):
    code: str = Field(min_length=1, max_length=40)
    title: str = Field(min_length=1, max_length=200)
    objective: str | None = Field(default=None, max_length=4000)
    control_ids: list[uuid.UUID] = Field(min_length=1, max_length=500)
    test_types: list[Literal["design", "operating"]] = Field(min_length=1)
    period_start: date | None = None
    period_end: date | None = None


@router.post(
    E + "/program",
    status_code=status.HTTP_201_CREATED,
    summary="Programme de contrôle : programme de travail, une procédure et un test planifié par contrôle et type",
)
def create_program(p: ProgramIn, request: Request, ctx: Ctx, db: Db):
    ctx.require("plan")
    cid = ctx.engagement.company_id
    ctls = [svc.in_company(db, Control, i, cid, "Contrôle") for i in p.control_ids]
    wp = WorkProgram(
        id=uuid.uuid4(),
        organization_id=ctx.engagement.organization_id,
        engagement_id=ctx.engagement.id,
        code=p.code,
        title=p.title,
        objective=p.objective,
    )
    db.add(wp)
    db.flush()
    n = 0
    labels = {"design": "Conception", "operating": "Efficacité"}
    for c in ctls:
        for tt in p.test_types:
            n += 1
            ref = f"{p.code}-{c.code}-{'CO' if tt == 'design' else 'EF'}"
            proc = Procedure(
                id=uuid.uuid4(),
                organization_id=wp.organization_id,
                engagement_id=wp.engagement_id,
                program_id=wp.id,
                code=ref,
                title=f"{labels[tt]} — {c.title}"[:200],
                objective=c.control_objective,
                nature="control_test",
                display_order=n,
            )
            db.add(proc)
            db.flush()
            db.add(
                ControlTest(
                    id=uuid.uuid4(),
                    organization_id=wp.organization_id,
                    engagement_id=wp.engagement_id,
                    company_id=cid,
                    control_id=c.id,
                    procedure_id=proc.id,
                    reference=ref,
                    test_type=tt,
                    test_methods=["document_review" if tt == "design" else "inspection"],
                    objective=c.control_objective,
                    test_procedure=c.procedure_text or "Procédure de test à rédiger par l'équipe.",
                    period_start=p.period_start if tt == "operating" else None,
                    period_end=p.period_end if tt == "operating" else None,
                    created_by=ctx.user.id,
                )
            )
    db.flush()
    _elog(db, request, ctx, "ic.program.create", "work_programs", wp.id, {"tests": n})
    return {"program_id": str(wp.id), "tests": n}


# ======================================================================== mission : évaluations
class AssessmentIn(BaseModel):
    reference: str = Field(min_length=1, max_length=60)
    scope_type: Literal["overall", "domain", "process", "cycle", "component", "risk", "control"]
    domain_id: uuid.UUID | None = None
    process_id: uuid.UUID | None = None
    risk_id: uuid.UUID | None = None
    control_id: uuid.UUID | None = None
    framework_item_id: uuid.UUID | None = None
    cycle_code: str | None = Field(default=None, max_length=40)
    as_of_date: date
    rating_code: str | None = Field(default=None, max_length=40)
    conclusion: str | None = Field(default=None, max_length=8000)


SCOPE_FIELD = {
    "domain": "domain_id",
    "process": "process_id",
    "risk": "risk_id",
    "control": "control_id",
    "component": "framework_item_id",
    "cycle": "cycle_code",
}


def _scope_clean(p: AssessmentIn) -> dict:
    d = p.model_dump()
    keep = SCOPE_FIELD.get(p.scope_type)
    for f in SCOPE_FIELD.values():
        if f != keep:
            d[f] = None
    if keep and d[keep] is None:
        raise AuditInvalid("Précisez l'objet du périmètre évalué.")
    return d


def _synthesis(db: Session, e, d: dict) -> dict:
    return db.execute(
        text("SELECT public.ic_synthesis(:c, :e, :s, :d, :p, :r, :ct, :i, :cy)"),
        {
            "c": e.company_id,
            "e": e.id,
            "s": d["scope_type"],
            "d": d.get("domain_id"),
            "p": d.get("process_id"),
            "r": d.get("risk_id"),
            "ct": d.get("control_id"),
            "i": d.get("framework_item_id"),
            "cy": d.get("cycle_code"),
        },
    ).scalar_one()


def _assessment_out(db: Session, ctx: EngagementContext, a: IcAssessment) -> dict:
    lv = {x["code"]: x for x in svc.levels_for(db, ctx.engagement.methodology_version_id, "control_level_scale")}
    ppl = people(db, [a.prepared_by, a.approved_by])
    return {
        **row(a, svc.ASSESSMENT_FIELDS),
        "rating_label": lv.get(a.rating_code or "", {}).get("label"),
        "prepared_by_user": ppl.get(str(a.prepared_by)),
        "approved_by_user": ppl.get(str(a.approved_by)),
        "preview": _synthesis(
            db,
            ctx.engagement,
            row(a, svc.ASSESSMENT_FIELDS)
            | {k: getattr(a, k) for k in ("domain_id", "process_id", "risk_id", "control_id", "framework_item_id")},
        )
        if a.status == "draft"
        else None,
    }


@router.get(E + "/assessments")
def list_assessments(ctx: Ctx, db: Db):
    _ic_ctx(ctx)
    lv = svc.levels_for(db, ctx.engagement.methodology_version_id, "control_level_scale")
    return {
        "levels": lv,
        "items": [
            _assessment_out(db, ctx, a)
            for a in db.scalars(
                select(IcAssessment).where(IcAssessment.engagement_id == ctx.engagement.id).order_by(IcAssessment.reference)
            )
        ],
    }


@router.post(E + "/assessments", status_code=status.HTTP_201_CREATED)
def create_assessment(p: AssessmentIn, request: Request, ctx: Ctx, db: Db):
    ctx.require("edit_procedures")
    a = IcAssessment(
        id=uuid.uuid4(),
        organization_id=ctx.engagement.organization_id,
        engagement_id=ctx.engagement.id,
        company_id=ctx.engagement.company_id,
        created_by=ctx.user.id,
        **_clean(_scope_clean(p)),
    )
    db.add(a)
    db.flush()
    _elog(db, request, ctx, "ic.assessment.create", "ic_assessments", a.id, {"reference": a.reference})
    return _assessment_out(db, ctx, a)


@router.patch(E + "/assessments/{assessment_id}")
def update_assessment(assessment_id: uuid.UUID, p: AssessmentIn, request: Request, ctx: Ctx, db: Db):
    ctx.require("edit_procedures")
    a = owned(db, ctx, IcAssessment, assessment_id, "Évaluation")
    if a.status != "draft":
        raise Conflict("Évaluation soumise ou approuvée : non modifiable.")
    for k, v in _clean(_scope_clean(p)).items():
        setattr(a, k, v)
    db.flush()
    _elog(db, request, ctx, "ic.assessment.update", "ic_assessments", a.id)
    return _assessment_out(db, ctx, a)


class AssessmentAction(BaseModel):
    action: Literal["submit", "approve", "return"]
    reason: str | None = Field(default=None, max_length=2000)


@router.post(E + "/assessments/{assessment_id}/status", summary="Soumettre (synthèse figée), approuver, renvoyer")
def assessment_status(assessment_id: uuid.UUID, p: AssessmentAction, request: Request, ctx: Ctx, db: Db):
    a = owned(db, ctx, IcAssessment, assessment_id, "Évaluation")
    if p.action == "submit":
        ctx.require("sign_preparer")
        a.status, a.prepared_by = "submitted", ctx.user.id
    elif p.action == "approve":
        ctx.require("approve_ic")
        if a.prepared_by == ctx.user.id:
            raise Forbidden("L'approbation est faite par une autre personne que le préparateur.")
        a.status, a.approved_by = "approved", ctx.user.id
    else:
        ctx.require("approve_ic")
        a.status, a.return_reason = "draft", (p.reason or "").strip() or None
    db.flush()
    _elog(db, request, ctx, f"ic.assessment.{p.action}", "ic_assessments", a.id, {"reason": p.reason})
    return _assessment_out(db, ctx, a)


@router.delete(E + "/assessments/{assessment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_assessment(assessment_id: uuid.UUID, request: Request, ctx: Ctx, db: Db):
    ctx.require("edit_procedures")
    a = owned(db, ctx, IcAssessment, assessment_id, "Évaluation")
    db.delete(a)
    db.flush()
    _elog(db, request, ctx, "ic.assessment.delete", "ic_assessments", assessment_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(E + "/registry", summary="Contrôles et risques de l'entité pour la mission (sélecteurs)")
def engagement_registry(ctx: Ctx, db: Db):
    ctx.require("read_findings")
    reg = svc.registry(db, ctx.engagement.company_id)
    return {
        "domains": [row(d, svc.DOMAIN_FIELDS) for d in reg.domains],
        "processes": [row(x, svc.PROCESS_FIELDS) for x in reg.processes],
        "risks": [row(r, ("id", "code", "title", "domain_id", "process_id")) for r in reg.risks],
        "controls": [row(c, ("id", "code", "title", "domain_id", "process_id", "existence", "is_key")) for c in reg.controls],
        "components": [
            row(i, ("id", "item_type", "code", "label"))
            for i in db.scalars(
                select(MethodologyItem).where(
                    MethodologyItem.version_id == ctx.engagement.methodology_version_id,
                    MethodologyItem.item_type.in_(("ic_component", "ic_principle", "ic_requirement")),
                )
            )
        ]
        if ctx.engagement.methodology_version_id
        else [],
        "control_levels": svc.levels_for(db, ctx.engagement.methodology_version_id, "control_level_scale"),
        "cycles": [row(i, ("code", "label")) for i in methodology_items(db, ctx.engagement, "cycle")],
    }


# ======================================================================== audit financier : prise en compte
@router.get(E + "/reliance-candidates", summary="Tests de contrôles revus de l'entité (réutilisables)")
def reliance_candidates(ctx: Ctx, db: Db):
    ctx.require("read_dossier")
    ts = [t for t in svc.visible_tests(db, ctx.engagement.company_id) if t.status == "reviewed"]
    ctl = {c.id: c for c in db.scalars(select(Control).where(Control.company_id == ctx.engagement.company_id))}
    return [
        {
            **_test_brief(t),
            "test_methods": t.test_methods,
            "control": f"{ctl[t.control_id].code} — {ctl[t.control_id].title}" if t.control_id in ctl else None,
            "is_key": ctl[t.control_id].is_key if t.control_id in ctl else None,
            "conclusion_rationale": t.conclusion_rationale,
        }
        for t in ts
    ]


class RelianceIn(BaseModel):
    control_test_id: uuid.UUID
    cycle_code: str | None = Field(default=None, max_length=40)
    assertion_codes: list[str] = Field(default_factory=list, max_length=20)
    decision: Literal["rely", "partial_rely", "no_reliance"]
    rationale: str = Field(min_length=3, max_length=4000)
    approach_impact: str | None = Field(default=None, max_length=4000)


@router.get(E + "/reliances")
def list_reliances(ctx: Ctx, db: Db):
    ctx.require("read_dossier")
    rs = list(
        db.scalars(
            select(ControlTestReliance)
            .where(ControlTestReliance.engagement_id == ctx.engagement.id)
            .order_by(ControlTestReliance.decided_at.desc())
        )
    )
    ppl = people(db, [r.decided_by for r in rs])
    return [
        {
            **row(
                r,
                (
                    "id",
                    "control_test_id",
                    "cycle_code",
                    "assertion_codes",
                    "decision",
                    "rationale",
                    "approach_impact",
                    "period_overlap",
                    "snapshot",
                    "decided_at",
                    "status",
                    "withdrawn_reason",
                ),
            ),
            "decided_by": ppl.get(str(r.decided_by)),
        }
        for r in rs
    ]


@router.post(
    E + "/reliances",
    status_code=status.HTTP_201_CREATED,
    summary="Prendre en compte un test de contrôle (période, périmètre, preuves et conclusion figés)",
)
def add_reliance(p: RelianceIn, request: Request, ctx: Ctx, db: Db):
    ctx.require("plan")
    if ctx.engagement.engagement_type not in ("statutory_audit", "contractual_audit"):
        raise AuditInvalid("Réservé aux missions d'audit financier.")
    r = ControlTestReliance(
        id=uuid.uuid4(),
        organization_id=ctx.engagement.organization_id,
        engagement_id=ctx.engagement.id,
        company_id=ctx.engagement.company_id,
        decided_by=ctx.user.id,
        **_clean(p.model_dump()),
    )
    db.add(r)
    db.flush()
    db.refresh(r)
    _elog(db, request, ctx, "ic.reliance.add", "control_test_reliances", r.id, {"decision": r.decision})
    return row(r, ("id", "decision", "period_overlap", "snapshot", "status"))


class WithdrawIn(BaseModel):
    reason: str = Field(min_length=3, max_length=2000)


@router.post(E + "/reliances/{reliance_id}/withdraw")
def withdraw_reliance(reliance_id: uuid.UUID, p: WithdrawIn, request: Request, ctx: Ctx, db: Db):
    ctx.require("plan")
    r = owned(db, ctx, ControlTestReliance, reliance_id, "Prise en compte")
    r.status, r.withdrawn_reason = "withdrawn", p.reason.strip()
    db.flush()
    _elog(db, request, ctx, "ic.reliance.withdraw", "control_test_reliances", r.id, {"reason": p.reason})
    return row(r, ("id", "status", "withdrawn_reason"))
