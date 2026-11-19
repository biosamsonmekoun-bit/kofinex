"""Contrôle interne : contexte d'accès, lecture du dispositif, synthèses, tableau de bord, rapports.

La base reste l'autorité (migration 0011) : droits par domaine, séparation exécutant / superviseur et
préparateur / réviseur, gel des tests revus et des évaluations approuvées, synthèse IC-SYNTH-1.
Ce service assemble les données visibles de l'utilisateur (RLS) et les passe au moteur.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone

from fastapi import Depends
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.errors import Forbidden, NotFound
from app.core.security import AuthenticatedUser
from app.engines.audit import control as ic
from app.engines.audit import methodology as meth
from app.models import (
    ActionPlan,
    Control,
    ControlObjective,
    ControlRisk,
    ControlTest,
    ControlTestItem,
    EvidenceLink,
    Finding,
    IcAssessment,
    IcDomain,
    IcFrameworkLink,
    IcMember,
    MethodologyItem,
    MethodologyVersion,
    Process,
    Recommendation,
    Risk,
)
from app.services.engagements import js, people, row

DOMAIN_FIELDS = (
    "id",
    "code",
    "name",
    "category",
    "template_code",
    "cycle_code",
    "description",
    "owner_name",
    "owner_user_id",
    "is_active",
    "display_order",
)
PROCESS_FIELDS = ("id", "code", "name", "parent_id", "domain_id", "owner_name", "owner_user_id", "description", "is_active")
OBJECTIVE_FIELDS = ("id", "code", "statement", "domain_id", "process_id", "assertion_codes", "is_active")
RISK_FIELDS = (
    "id",
    "code",
    "title",
    "description",
    "process_id",
    "domain_id",
    "objective_id",
    "category",
    "causes",
    "consequences",
    "owner_name",
    "owner_user_id",
    "cycle_code",
    "assertion_codes",
    "scale_version_id",
    "inherent_likelihood",
    "inherent_impact",
    "residual_likelihood",
    "residual_impact",
    "control_level_code",
    "status",
)
CONTROL_FIELDS = (
    "id",
    "code",
    "title",
    "description",
    "control_objective",
    "domain_id",
    "process_id",
    "objective_id",
    "existence",
    "owner_name",
    "owner_user_id",
    "performer_name",
    "performer_user_id",
    "supervisor_name",
    "supervisor_user_id",
    "frequency",
    "nature",
    "automation",
    "timing",
    "execution_mode",
    "expected_evidence",
    "procedure_text",
    "success_criteria",
    "is_key",
    "implemented_on",
    "operational_status",
    "version",
    "updated_at",
)
TEST_FIELDS = (
    "id",
    "engagement_id",
    "control_id",
    "risk_id",
    "procedure_id",
    "workpaper_id",
    "reference",
    "test_type",
    "test_methods",
    "objective",
    "test_procedure",
    "responsible_user_id",
    "period_start",
    "period_end",
    "population_description",
    "population_size",
    "population_source",
    "selection_method",
    "sample_size",
    "sample_size_basis",
    "selection_params",
    "acceptance_criteria",
    "tolerable_exceptions",
    "expected_result",
    "design_answers",
    "operating_answers",
    "results_summary",
    "exceptions_summary",
    "conclusion",
    "conclusion_rationale",
    "status",
    "prepared_by",
    "prepared_at",
    "reviewed_by",
    "reviewed_at",
    "reopen_reason",
    "created_by",
    "created_at",
)
ITEM_FIELDS = (
    "id",
    "item_ref",
    "description",
    "item_date",
    "amount",
    "execution_id",
    "selection_order",
    "result",
    "exception_description",
    "na_reason",
    "tested_by",
    "tested_at",
)
ASSESSMENT_FIELDS = (
    "id",
    "engagement_id",
    "reference",
    "scope_type",
    "domain_id",
    "process_id",
    "risk_id",
    "control_id",
    "framework_item_id",
    "cycle_code",
    "as_of_date",
    "rating_code",
    "conclusion",
    "basis",
    "status",
    "prepared_by",
    "prepared_at",
    "approved_by",
    "approved_at",
    "return_reason",
    "created_at",
)


# ------------------------------------------------------------------ contexte d'accès
@dataclass
class IcContext:
    company_id: uuid.UUID
    organization_id: uuid.UUID
    user: AuthenticatedUser
    company_role: str | None
    is_admin: bool
    audits: bool
    roles: list[tuple[str, uuid.UUID | None]]

    def manages(self, domain_id: uuid.UUID | None) -> bool:
        return self.is_admin or (
            domain_id is not None and any(r in ("domain_owner", "process_owner") and d == domain_id for r, d in self.roles)
        )

    def require_admin(self) -> None:
        if not self.is_admin:
            raise Forbidden("Réservé aux pilotes du contrôle interne (administrateur, responsable du contrôle interne, DAF).")

    def require_manage(self, domain_id: uuid.UUID | None) -> None:
        if not self.manages(domain_id):
            raise Forbidden("Réservé aux pilotes du contrôle interne et au responsable de ce domaine.")

    def managed_domains(self) -> list[str]:
        return [str(d) for r, d in self.roles if r in ("domain_owner", "process_owner") and d]

    def out(self) -> dict:
        return {
            "company_role": self.company_role,
            "is_admin": self.is_admin,
            "audits": self.audits,
            "roles": [{"role": r, "role_label": ic.IC_ROLES[r], "domain_id": str(d) if d else None} for r, d in self.roles],
            "managed_domains": self.managed_domains(),
            "can_manage_registry": self.is_admin or bool(self.managed_domains()),
        }


def load_ic_context(db: Session, company_id: uuid.UUID, user: AuthenticatedUser) -> IcContext:
    r = db.execute(
        text(
            "SELECT c.organization_id, authz.ic_reader(c.id) AS reader, authz.ic_admin(c.id) AS admin, "
            "authz.company_role(c.id) AS role, authz.audits_company(c.id) AS audits "
            "FROM public.companies c WHERE c.id = :id"
        ),
        {"id": company_id},
    ).one_or_none()
    if r is None or not r.reader:
        # 404 : ne pas révéler l'existence d'une entité tierce
        raise NotFound("Entreprise introuvable")
    roles = [
        (m.role, m.domain_id)
        for m in db.scalars(select(IcMember).where(IcMember.company_id == company_id, IcMember.user_id == user.id))
    ]
    return IcContext(company_id, r.organization_id, user, r.role, bool(r.admin), bool(r.audits), roles)


def get_ic_context(
    company_id: uuid.UUID, db: Session = Depends(get_db), user: AuthenticatedUser = Depends(get_current_user)
) -> IcContext:
    return load_ic_context(db, company_id, user)


def in_company(db: Session, model, obj_id: uuid.UUID | None, company_id: uuid.UUID, what: str):
    if obj_id is None:
        return None
    obj = db.get(model, obj_id)
    if obj is None or obj.company_id != company_id:
        raise NotFound(f"{what} introuvable")
    return obj


# ------------------------------------------------------------------ lecture du dispositif
@dataclass
class Registry:
    domains: list[IcDomain]
    processes: list[Process]
    objectives: list[ControlObjective]
    risks: list[Risk]
    controls: list[Control]
    links: list[ControlRisk]
    framework_links: list[IcFrameworkLink]


def registry(db: Session, company_id: uuid.UUID) -> Registry:
    def q(m, order):
        return list(db.scalars(select(m).where(m.company_id == company_id).order_by(order)))

    return Registry(
        q(IcDomain, IcDomain.display_order),
        q(Process, Process.code),
        q(ControlObjective, ControlObjective.code),
        q(Risk, Risk.code),
        q(Control, Control.code),
        q(ControlRisk, ControlRisk.control_id),
        q(IcFrameworkLink, IcFrameworkLink.created_at),
    )


def descendants(processes: list[Process], root: uuid.UUID) -> set[uuid.UUID]:
    out, frontier = {root}, [root]
    while frontier:
        cur = frontier.pop()
        for p in processes:
            if p.parent_id == cur and p.id not in out:
                out.add(p.id)
                frontier.append(p.id)
    return out


def filtered(
    reg: Registry, domain_id: uuid.UUID | None = None, process_id: uuid.UUID | None = None, cycle_code: str | None = None
) -> Registry:
    """Restreint le dispositif à un domaine, un processus (et ses sous-processus) ou un cycle."""
    if not (domain_id or process_id or cycle_code):
        return reg
    doms = {
        d.id
        for d in reg.domains
        if (domain_id is None or d.id == domain_id) and (cycle_code is None or d.cycle_code == cycle_code)
    }
    procs = descendants(reg.processes, process_id) if process_id else {p.id for p in reg.processes if p.domain_id in doms}
    keep_p = [p for p in reg.processes if p.id in procs]
    keep_r = [
        r
        for r in reg.risks
        if (
            r.process_id in procs
            if process_id
            else (r.domain_id in doms or (cycle_code is not None and r.cycle_code == cycle_code))
        )
    ]
    keep_c = [c for c in reg.controls if (c.process_id in procs if process_id else c.domain_id in doms)]
    ids_c, ids_r = {c.id for c in keep_c}, {r.id for r in keep_r}
    return Registry(
        [d for d in reg.domains if d.id in doms or (process_id and d.id in {p.domain_id for p in keep_p})],
        keep_p,
        [o for o in reg.objectives if o.process_id in procs or (not process_id and o.domain_id in doms)],
        keep_r,
        keep_c,
        [lk for lk in reg.links if lk.control_id in ids_c or lk.risk_id in ids_r],
        [fl for fl in reg.framework_links if fl.object_id in ids_c | ids_r],
    )


def visible_tests(db: Session, company_id: uuid.UUID, control_ids: list[uuid.UUID] | None = None) -> list[ControlTest]:
    q = select(ControlTest).where(ControlTest.company_id == company_id)
    if control_ids is not None:
        q = q.where(ControlTest.control_id.in_(control_ids))
    return list(db.scalars(q.order_by(ControlTest.reviewed_at.desc().nulls_last(), ControlTest.created_at.desc())))


def status_map(controls: list[Control], tests: list[ControlTest], engagement_id: uuid.UUID | None = None) -> dict[str, dict]:
    rows = [
        ic.TestRow(
            str(t.id),
            str(t.control_id),
            t.test_type,
            t.status,
            t.conclusion,
            t.reviewed_at.isoformat() if t.reviewed_at else None,
            t.period_end,
            str(t.engagement_id),
        )
        for t in tests
    ]
    return ic.control_status([str(c.id) for c in controls], rows, str(engagement_id) if engagement_id else None)


def control_refs(controls: list[Control]) -> list[ic.ControlRef]:
    return [
        ic.ControlRef(
            str(c.id),
            c.code,
            c.title,
            c.existence,
            c.operational_status,
            c.is_key,
            c.owner_name,
            c.frequency,
            c.expected_evidence,
            str(c.domain_id) if c.domain_id else None,
            str(c.process_id) if c.process_id else None,
        )
        for c in controls
    ]


def risk_refs(risks: list[Risk]) -> list[ic.RiskRef]:
    return [
        ic.RiskRef(
            str(r.id),
            r.code,
            r.title,
            r.status,
            str(r.domain_id) if r.domain_id else None,
            str(r.process_id) if r.process_id else None,
            str(r.objective_id) if r.objective_id else None,
        )
        for r in risks
    ]


def link_dicts(links: list[ControlRisk]) -> list[dict]:
    return [
        {
            "control_id": str(lk.control_id),
            "risk_id": str(lk.risk_id),
            "coverage": lk.coverage,
            "assertion_codes": lk.assertion_codes,
            "rationale": lk.rationale,
        }
        for lk in links
    ]


def evidence_counts(db: Session, tests: list[ControlTest]) -> dict[str, int]:
    """Éléments probants visibles rattachés aux tests revus, par contrôle."""
    by_test = {t.id: t for t in tests if t.status == "reviewed"}
    if not by_test:
        return {}
    items = {i.id: i.test_id for i in db.scalars(select(ControlTestItem).where(ControlTestItem.test_id.in_(by_test)))}
    out: dict[str, int] = {}
    for lk in db.scalars(select(EvidenceLink).where(EvidenceLink.object_type.in_(("control_test", "control_test_item")))):
        tid = lk.object_id if lk.object_type == "control_test" else items.get(lk.object_id)
        if tid in by_test:
            k = str(by_test[tid].control_id)
            out[k] = out.get(k, 0) + 1
    return out


def scale_for(db: Session, version_id: uuid.UUID | None, item_type: str) -> dict | None:
    if not version_id:
        return None
    it = db.scalar(
        select(MethodologyItem).where(MethodologyItem.version_id == version_id, MethodologyItem.item_type == item_type)
    )
    return it.content if it else None


def levels_for(db: Session, version_id: uuid.UUID | None, item_type: str) -> list[dict]:
    if not version_id:
        return []
    items = list(
        db.scalars(
            select(MethodologyItem).where(MethodologyItem.version_id == version_id, MethodologyItem.item_type == item_type)
        )
    )
    return meth.scale_levels([{"item_type": i.item_type, "content": i.content} for i in items], item_type)


def risk_out(db: Session, r: Risk, scales: dict, indicator: str | None = None) -> dict:
    d = row(r, RISK_FIELDS)
    sc = scales.get(r.scale_version_id)
    if sc is None and r.scale_version_id:
        sc = scales[r.scale_version_id] = scale_for(db, r.scale_version_id, "risk_scale")
    for basis, (a, b) in (
        ("inherent", (r.inherent_likelihood, r.inherent_impact)),
        ("residual", (r.residual_likelihood, r.residual_impact)),
    ):
        try:
            d[f"{basis}_score"] = ic.risk_rating(sc, a, b)["score"] if sc else None
        except ValueError:
            d[f"{basis}_score"] = None
    if r.control_level_code:
        key = ("lvl", r.scale_version_id)
        lv = scales.get(key)
        if lv is None:
            lv = scales[key] = {x["code"]: x for x in levels_for(db, r.scale_version_id, "control_level_scale")}
        d["control_level_label"] = lv.get(r.control_level_code, {}).get("label")
    d["indicator"] = indicator
    d["indicator_label"] = ic.INDICATOR_LABELS.get(indicator) if indicator else None
    return d


def control_out(c: Control, st: dict | None, risks_count: int = 0) -> dict:
    d = row(c, CONTROL_FIELDS)
    st = st or {}
    concl = st.get("conclusion", "not_tested")
    d.update(
        design=st.get("design"),
        operating=st.get("operating"),
        conclusion=concl,
        conclusion_label=ic.CONCLUSION_LABELS[concl],
        existence_label=ic.EXISTENCE_LABELS[c.existence],
        frequency_label=ic.FREQUENCY_LABELS.get(c.frequency) if c.frequency else None,
        risks=risks_count,
        # « inefficace » est un résultat de test, distinct de l'existence déclarée
        display_state=("ineffective" if concl == "ineffective" else c.existence),
    )
    return d


# ------------------------------------------------------------------ déficiences et remédiation
def deficiencies(
    db: Session, company_id: uuid.UUID, control_ids: set[uuid.UUID] | None = None, today: date | None = None
) -> list[dict]:
    """Déficiences visibles (RLS) de l'entité, avec recommandations, plans d'action et étape du cycle."""
    today = today or date.today()
    from app.models import Engagement  # import local : modèles partagés

    engs = {e.id: e for e in db.scalars(select(Engagement).where(Engagement.company_id == company_id))}
    if not engs:
        return []
    fs = list(
        db.scalars(
            select(Finding)
            .where(Finding.engagement_id.in_(engs), Finding.kind == "ic_deficiency")
            .order_by(Finding.created_at.desc())
        )
    )
    if control_ids is not None:
        fs = [f for f in fs if f.control_id in control_ids]
    if not fs:
        return []
    recs = list(db.scalars(select(Recommendation).where(Recommendation.finding_id.in_([f.id for f in fs]))))
    aps = list(db.scalars(select(ActionPlan).where(ActionPlan.recommendation_id.in_([r.id for r in recs])))) if recs else []
    levels_cache: dict = {}
    ctl = {c.id: c for c in db.scalars(select(Control).where(Control.company_id == company_id))}
    out = []
    for f in fs:
        e = engs[f.engagement_id]
        if e.methodology_version_id not in levels_cache:
            levels_cache[e.methodology_version_id] = {
                x["code"]: x
                for x in (
                    levels_for(db, e.methodology_version_id, "deficiency_scale")
                    or levels_for(db, e.methodology_version_id, "finding_scale")
                )
            }
        lv = levels_cache[e.methodology_version_id].get(f.rating_code or "", {})
        my_recs = [r for r in recs if r.finding_id == f.id]
        my_aps = [a for a in aps if a.recommendation_id in {r.id for r in my_recs}]
        c = ctl.get(f.control_id)
        out.append(
            {
                **row(
                    f,
                    (
                        "id",
                        "engagement_id",
                        "reference",
                        "title",
                        "condition",
                        "criteria",
                        "cause",
                        "effect",
                        "rating_code",
                        "control_id",
                        "risk_id",
                        "domain_id",
                        "process_id",
                        "status",
                        "management_response",
                        "response_by_name",
                        "response_at",
                        "validated_at",
                        "communicated_at",
                        "closed_at",
                        "closure_note",
                    ),
                ),
                "engagement_reference": e.reference,
                "rating_label": lv.get("label"),
                "rating_rank": lv.get("rank"),
                "control": f"{c.code} — {c.title}" if c else None,
                "stage": ic.lifecycle_stage(f.status, bool(f.management_response), [a.status for a in my_aps]),
                "recommendations": [
                    {
                        **row(r, ("id", "reference", "text")),
                        "action_plans": [
                            {
                                **row(a, ("id", "description", "owner_name", "due_date", "status", "engagement_id")),
                                "overdue": a.status in ("planned", "in_progress") and a.due_date < today,
                            }
                            for a in my_aps
                            if a.recommendation_id == r.id
                        ],
                    }
                    for r in my_recs
                ],
            }
        )
    for d in out:
        d["stage_label"] = ic.STAGE_LABELS[d["stage"]]
    return out


def plans_of(defs: list[dict]) -> list[dict]:
    return [
        {
            **a,
            "deficiency_id": d["id"],
            "deficiency_reference": d["reference"],
            "recommendation": r["text"],
            "engagement_reference": d["engagement_reference"],
        }
        for d in defs
        for r in d["recommendations"]
        for a in r["action_plans"]
    ]


# ------------------------------------------------------------------ tableau de bord
def dashboard(
    db: Session,
    ctx: IcContext,
    domain_id: uuid.UUID | None = None,
    process_id: uuid.UUID | None = None,
    cycle_code: str | None = None,
    today: date | None = None,
) -> dict:
    today = today or date.today()
    reg = filtered(registry(db, ctx.company_id), domain_id, process_id, cycle_code)
    tests = visible_tests(db, ctx.company_id, [c.id for c in reg.controls])
    st = status_map(reg.controls, tests)
    defs = deficiencies(db, ctx.company_id, {c.id for c in reg.controls}, today)
    from app.models import Engagement

    mv = db.scalar(
        select(Engagement.methodology_version_id)
        .where(
            Engagement.company_id == ctx.company_id,
            Engagement.engagement_type == "ic_assessment",
            Engagement.methodology_version_id.is_not(None),
        )
        .order_by(Engagement.created_at.desc())
    )
    def_levels = levels_for(db, mv, "deficiency_scale") or levels_for(db, mv, "finding_scale")
    assessed = {
        a.domain_id
        for a in db.scalars(
            select(IcAssessment).where(
                IcAssessment.company_id == ctx.company_id, IcAssessment.status == "approved", IcAssessment.scope_type == "domain"
            )
        )
    }
    kpi = ic.dashboard(
        domains=[row(d, DOMAIN_FIELDS) for d in reg.domains if d.is_active],
        processes=[row(p, PROCESS_FIELDS) for p in reg.processes if p.is_active],
        risks=risk_refs(reg.risks),
        controls=control_refs(reg.controls),
        status=st,
        links=link_dicts(reg.links),
        deficiencies=[{"status": d["status"], "rating_code": d["rating_code"]} for d in defs],
        action_plans=[{"status": a["status"], "due_date": date.fromisoformat(a["due_date"])} for a in plans_of(defs)],
        deficiency_levels=def_levels,
        assessed_domain_ids={str(x) for x in assessed if x in {d.id for d in reg.domains}},
        today=today,
    )
    by_domain = []
    for d in reg.domains:
        cs = [c for c in reg.controls if c.domain_id == d.id]
        cnt = {k: 0 for k in ic.CONCLUSIONS}
        for c in cs:
            if c.existence in ic.COVERING and c.operational_status != "retired":
                cnt[st[str(c.id)]["conclusion"]] += 1
        by_domain.append(
            {
                "id": str(d.id),
                "code": d.code,
                "name": d.name,
                "is_active": d.is_active,
                "processes": sum(1 for p in reg.processes if p.domain_id == d.id),
                "risks": sum(1 for r in reg.risks if r.domain_id == d.id and r.status == "active"),
                "controls": len(cs),
                **cnt,
            }
        )
    return {
        **kpi,
        "by_domain": by_domain,
        "filters": {
            "domain_id": str(domain_id) if domain_id else None,
            "process_id": str(process_id) if process_id else None,
            "cycle_code": cycle_code,
        },
        "deficiency_scale_from": str(mv) if mv else None,
    }


# ------------------------------------------------------------------ rapports
def build_report(
    db: Session,
    ctx: IcContext,
    kind: str,
    domain_id: uuid.UUID | None = None,
    process_id: uuid.UUID | None = None,
    cycle_code: str | None = None,
    engagement_id: uuid.UUID | None = None,
) -> dict:
    """Rapports établis sur les données enregistrées ; seules les évaluations approuvées et les tests revus
    alimentent les conclusions."""
    if kind not in ic.REPORT_KINDS:
        raise NotFound("Rapport inconnu")
    reg = filtered(registry(db, ctx.company_id), domain_id, process_id, cycle_code)
    tests = [t for t in visible_tests(db, ctx.company_id, [c.id for c in reg.controls]) if t.status == "reviewed"]
    st = status_map(reg.controls, tests, engagement_id)
    procs = {p.id: p for p in reg.processes}
    doms = {d.id: d for d in reg.domains}
    ctl_rows = [
        {
            "code": c.code,
            "title": c.title,
            "domain": doms[c.domain_id].name if c.domain_id in doms else None,
            "process": procs[c.process_id].name if c.process_id in procs else None,
            "existence": ic.EXISTENCE_LABELS[c.existence],
            "owner": c.owner_name,
            "key": "Oui" if c.is_key else "Non",
            "design": ic.DESIGN_LABELS.get(st[str(c.id)]["design"] or "", None),
            "operating": ic.CONCLUSION_LABELS.get(st[str(c.id)]["operating"] or "", None),
            "conclusion": ic.CONCLUSION_LABELS[st[str(c.id)]["conclusion"]],
            "_c": st[str(c.id)]["conclusion"],
        }
        for c in reg.controls
        if c.operational_status != "retired"
    ]
    ctl_cols = [
        ("code", "Code"),
        ("title", "Contrôle"),
        ("domain", "Domaine"),
        ("process", "Processus"),
        ("existence", "Existence"),
        ("owner", "Responsable"),
        ("key", "Clé"),
        ("design", "Conception"),
        ("operating", "Efficacité opérationnelle"),
        ("conclusion", "Conclusion"),
    ]
    m = ic.matrix(risk_refs(reg.risks), control_refs(reg.controls), link_dicts(reg.links), st, evidence_counts(db, tests))
    defs = deficiencies(db, ctx.company_id, {c.id for c in reg.controls})
    def_rows = [
        {
            "reference": d["reference"],
            "title": d["title"],
            "control": d["control"],
            "rating": d["rating_label"],
            "condition": d["condition"],
            "criteria": d["criteria"],
            "cause": d["cause"],
            "effect": d["effect"],
            "response": d["management_response"],
            "stage": d["stage_label"],
        }
        for d in defs
        if d["status"] != "draft"
    ]
    def_cols = [
        ("reference", "Réf."),
        ("title", "Déficience"),
        ("control", "Contrôle"),
        ("rating", "Gravité"),
        ("condition", "Situation observée"),
        ("criteria", "Critère"),
        ("cause", "Cause"),
        ("effect", "Conséquence"),
        ("response", "Réponse de la direction"),
        ("stage", "Étape"),
    ]
    plan_rows = [
        {
            "deficiency": a["deficiency_reference"],
            "recommendation": a["recommendation"],
            "action": a["description"],
            "owner": a["owner_name"],
            "due_date": a["due_date"],
            "status": a["status"],
            "overdue": "Oui" if a["overdue"] else "Non",
        }
        for a in plans_of(defs)
    ]
    plan_cols = [
        ("deficiency", "Déficience"),
        ("recommendation", "Recommandation"),
        ("action", "Action"),
        ("owner", "Responsable"),
        ("due_date", "Échéance"),
        ("status", "Statut"),
        ("overdue", "En retard"),
    ]
    risk_scales: dict = {}
    risk_rows = [
        {
            **risk_out(db, r, risk_scales),
            "domain": doms[r.domain_id].name if r.domain_id in doms else None,
            "process": procs[r.process_id].name if r.process_id in procs else None,
        }
        for r in reg.risks
        if r.status == "active"
    ]
    risk_cols = [
        ("code", "Code"),
        ("title", "Risque"),
        ("domain", "Domaine"),
        ("process", "Processus"),
        ("category", "Catégorie"),
        ("inherent_score", "Risque inhérent"),
        ("control_level_label", "Niveau de maîtrise"),
        ("residual_score", "Risque résiduel"),
        ("owner_name", "Propriétaire"),
    ]
    approved = [
        a
        for a in db.scalars(
            select(IcAssessment)
            .where(IcAssessment.company_id == ctx.company_id, IcAssessment.status == "approved")
            .order_by(IcAssessment.as_of_date.desc())
        )
        if engagement_id is None or a.engagement_id == engagement_id
    ]
    ass_rows = [
        {
            "reference": a.reference,
            "scope": a.scope_type,
            "as_of_date": a.as_of_date,
            "rating": a.rating_code,
            "conclusion": a.conclusion,
            "controls": (a.basis or {}).get("controls"),
            "effective": (a.basis or {}).get("effective"),
            "ineffective": (a.basis or {}).get("ineffective"),
            "not_tested": (a.basis or {}).get("not_tested"),
            "uncovered_risks": (a.basis or {}).get("uncovered_risks"),
        }
        for a in approved
    ]
    ass_cols = [
        ("reference", "Réf."),
        ("scope", "Périmètre"),
        ("as_of_date", "Date"),
        ("rating", "Niveau de maîtrise"),
        ("conclusion", "Conclusion"),
        ("controls", "Contrôles"),
        ("effective", "Efficaces"),
        ("ineffective", "Inefficaces"),
        ("not_tested", "Non testés"),
        ("uncovered_risks", "Risques non couverts"),
    ]
    mat_cols = [
        ("risk_code", "Risque"),
        ("risk_title", "Intitulé"),
        ("control_code", "Contrôle"),
        ("control_title", "Intitulé"),
        ("existence", "Existence"),
        ("coverage", "Couverture"),
        ("owner", "Responsable"),
        ("frequency", "Fréquence"),
        ("expected_evidence", "Preuves attendues"),
        ("evidence_count", "Preuves rattachées"),
        ("conclusion", "Résultat des tests"),
        ("indicator", "Couverture du risque"),
    ]
    mat_rows = [
        {
            **r,
            "existence": ic.EXISTENCE_LABELS.get(r.get("existence") or "", r.get("existence")),
            "frequency": ic.FREQUENCY_LABELS.get(r.get("frequency") or "", r.get("frequency")),
            "conclusion": ic.CONCLUSION_LABELS.get(r.get("conclusion") or "", None) if r.get("control_id") else None,
            "indicator": ic.INDICATOR_LABELS[r["indicator"]],
        }
        for r in m["rows"]
    ]
    unc_cols = [("code", "Risque"), ("title", "Intitulé"), ("expected", "Contrôles attendus")]
    unc_rows = [{**u, "expected": ", ".join(u["expected_controls"]) or None} for u in m["uncovered_risks"]]

    S = ic.section
    sections_by_kind = {
        "assessment": [
            S("assessments", "Évaluations approuvées", ass_cols, ass_rows),
            S("controls", "Conclusions par contrôle", ctl_cols, ctl_rows),
            S("uncovered", "Risques non couverts", unc_cols, unc_rows),
            S("deficiencies", "Déficiences", def_cols, def_rows),
        ],
        "domain": [
            S("controls", "Contrôles du domaine", ctl_cols, ctl_rows),
            S("risks", "Risques", risk_cols, risk_rows),
            S("deficiencies", "Déficiences", def_cols, def_rows),
        ],
        "process": [
            S("controls", "Contrôles du processus", ctl_cols, ctl_rows),
            S("risks", "Risques", risk_cols, risk_rows),
            S("deficiencies", "Déficiences", def_cols, def_rows),
        ],
        "cycle": [
            S("controls", "Contrôles du cycle", ctl_cols, ctl_rows),
            S("risks", "Risques", risk_cols, risk_rows),
            S("deficiencies", "Déficiences", def_cols, def_rows),
        ],
        "risk_map": [S("risks", "Risques cotés", risk_cols, risk_rows)],
        "matrix": [
            S("matrix", "Matrice risques-contrôles", mat_cols, mat_rows),
            S("uncovered", "Risques non couverts", unc_cols, unc_rows),
        ],
        "ineffective_controls": [
            S(
                "controls",
                "Contrôles inefficaces ou partiellement efficaces",
                ctl_cols,
                [r for r in ctl_rows if r["_c"] in ("ineffective", "partially_effective")],
            )
        ],
        "deficiencies": [S("deficiencies", "Déficiences", def_cols, def_rows)],
        "remediation": [S("plans", "Plans de remédiation", plan_cols, plan_rows)],
    }
    suffix = None
    if domain_id and domain_id in doms:
        suffix = doms[domain_id].name
    elif process_id and process_id in procs:
        suffix = procs[process_id].name
    elif cycle_code:
        suffix = f"cycle {cycle_code}"
    return js(
        ic.report(
            kind,
            title_suffix=suffix,
            filters={"domain_id": domain_id, "process_id": process_id, "cycle_code": cycle_code, "engagement_id": engagement_id},
            generated_at=datetime.now(timezone.utc).isoformat(),
            sections=sections_by_kind[kind],
            sources={"reviewed_tests": len(tests), "approved_assessments": len(approved), "deficiencies": len(def_rows)},
        )
    )


def methodology_meta(db: Session, version_id: uuid.UUID | None) -> dict | None:
    mv = db.get(MethodologyVersion, version_id) if version_id else None
    return row(mv, ("id", "name", "version_label", "framework_category", "issuing_body")) if mv else None


def people_out(db: Session, ids) -> dict[str, dict]:
    return people(db, ids)
