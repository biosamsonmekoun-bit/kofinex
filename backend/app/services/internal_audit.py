"""Audit interne : présentation des constats, assemblage du contenu du rapport, contrôles d'émission."""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.engines.audit import internal as ia
from app.engines.audit import methodology as meth
from app.models import (
    ActionPlan,
    ActionPlanUpdate,
    AuditReport,
    Company,
    Engagement,
    EngagementRisk,
    Finding,
    MethodologyVersion,
    Process,
    Recommendation,
)
from app.services.engagements import AuditInvalid, js, methodology_items, people, row

IA_TYPES = ("internal_audit", "ic_assessment")
FINDING_FIELDS = ("id", "reference", "title", "condition", "criteria", "cause", "effect", "rating_code", "process_id",
                  "engagement_risk_id", "workpaper_id", "status", "validated_by", "validated_at", "communicated_by",
                  "communicated_at", "response_due", "management_response", "response_by_name", "response_user_id",
                  "response_at", "reopen_reason", "created_by", "created_at", "updated_at", "kind", "control_id", "risk_id",
                  "domain_id", "closed_by", "closed_at", "closure_note", "origin", "ai_suggestion_id")
REC_FIELDS = ("id", "finding_id", "reference", "text", "created_at")
AP_FIELDS = ("id", "recommendation_id", "description", "owner_name", "owner_user_id", "due_date", "status", "created_by",
             "created_at", "updated_at")
UPD_FIELDS = ("id", "status", "comment", "new_due_date", "author_id", "author_role", "created_at")


def require_ia(e: Engagement) -> None:
    if e.engagement_type not in IA_TYPES:
        raise AuditInvalid("Fonction réservée aux missions d'audit interne et d'évaluation du contrôle interne.")


def levels(db: Session, e: Engagement, kind: str = "audit_finding") -> list[dict]:
    """Échelle des constats ; pour une déficience de contrôle interne, échelle des déficiences si la méthodologie en
    contient une (même règle que la base)."""
    if kind == "ic_deficiency":
        lv = meth.scale_levels([{"item_type": i.item_type, "content": i.content}
                                for i in methodology_items(db, e, "deficiency_scale")], "deficiency_scale")
        if lv:
            return lv
    return meth.finding_levels([{"item_type": i.item_type, "content": i.content}
                                for i in methodology_items(db, e, "finding_scale")])


def action_flag(db: Session, on: bool) -> None:
    db.execute(text("SELECT set_config('kofinex.action_update', :v, true)"), {"v": "on" if on else "off"})


def report_flag(db: Session, on: bool) -> None:
    db.execute(text("SELECT set_config('kofinex.report_issue', :v, true)"), {"v": "on" if on else "off"})


def findings_out(db: Session, e: Engagement, today: date | None = None) -> list[dict]:
    """Constats visibles de l'utilisateur (la RLS limite l'audité aux constats communiqués), avec recommandations,
    plans d'action et dernier état du suivi."""
    today = today or date.today()
    lv = {x["code"]: x for x in levels(db, e)}
    dlv = {x["code"]: x for x in levels(db, e, "ic_deficiency")}
    fs = list(db.scalars(select(Finding).where(Finding.engagement_id == e.id)))
    recs = list(db.scalars(select(Recommendation).where(Recommendation.engagement_id == e.id)
                           .order_by(Recommendation.reference)))
    aps = list(db.scalars(select(ActionPlan).where(ActionPlan.engagement_id == e.id).order_by(ActionPlan.due_date)))
    procs = {p.id: p for p in db.scalars(select(Process).where(Process.company_id == e.company_id))}
    risks = {r.id: r for r in db.scalars(select(EngagementRisk).where(EngagementRisk.engagement_id == e.id))}
    ppl = people(db, [f.validated_by for f in fs] + [f.communicated_by for f in fs] + [f.created_by for f in fs])
    out = []
    for f in fs:
        d = row(f, FINDING_FIELDS)
        scale = dlv if f.kind == "ic_deficiency" else lv
        d["rating_label"] = scale.get(f.rating_code, {}).get("label") if f.rating_code else None
        d["rating_rank"] = scale.get(f.rating_code, {}).get("rank") if f.rating_code else None
        p = procs.get(f.process_id)
        d["process"] = f"{p.code} — {p.name}" if p else None
        r = risks.get(f.engagement_risk_id)
        d["risk"] = f"{r.code} — {r.title}" if r else None
        d["created_by_user"], d["validated_by_user"] = ppl.get(str(f.created_by)), ppl.get(str(f.validated_by))
        d["communicated_by_user"] = ppl.get(str(f.communicated_by))
        d["recommendations"] = [{**row(rc, REC_FIELDS), "action_plans": [
            {**row(a, AP_FIELDS), "overdue": ia.is_overdue(a.status, a.due_date, today)}
            for a in aps if a.recommendation_id == rc.id]} for rc in recs if rc.finding_id == f.id]
        out.append(d)
    return ia.order_findings(out, list(lv.values()))


def snapshot(db: Session, e: Engagement, rep: AuditReport, issuer_id: uuid.UUID | None) -> dict:
    """Contenu du rapport : uniquement ce que l'équipe a saisi et validé, figé à l'émission."""
    lv = levels(db, e)
    fs = findings_out(db, e)
    company = db.get(Company, e.company_id)
    mv = db.get(MethodologyVersion, e.methodology_version_id) if e.methodology_version_id else None
    issuer = people(db, [issuer_id]).get(str(issuer_id)) if issuer_id else None
    return js({
        "title": rep.title, "version": rep.version, "executive_summary": rep.executive_summary,
        "overall_conclusion": rep.overall_conclusion, "distribution": rep.distribution,
        "engagement": {"id": e.id, "reference": e.reference, "name": e.name, "type": e.engagement_type,
                       "company": company.name if company else "", "objectives": e.objectives, "scope": e.scope,
                       "period_start": e.period_start, "period_end": e.period_end},
        "methodology": ({"name": mv.name, "version_label": mv.version_label, "source_reference": mv.source_reference}
                        if mv else None),
        "rating_counts": ia.rating_counts(fs, lv),
        "findings": [{"reference": f["reference"], "title": f["title"], "rating_code": f["rating_code"],
                      "rating_label": f["rating_label"], "condition": f["condition"], "criteria": f["criteria"],
                      "cause": f["cause"], "effect": f["effect"], "process": f["process"], "risk": f["risk"],
                      "management_response": f["management_response"], "response_by_name": f["response_by_name"],
                      "response_at": f["response_at"],
                      "recommendations": [{"reference": r["reference"], "text": r["text"],
                                           "action_plans": [{k: a[k] for k in ("description", "owner_name", "due_date", "status")}
                                                            for a in r["action_plans"]]}
                                          for r in f["recommendations"]]} for f in fs],
        "issued_by_name": (issuer.get("full_name") or issuer.get("email")) if issuer else None,
    })


def ia_checks(db: Session, e: Engagement) -> list[dict]:
    if e.engagement_type != "internal_audit":
        return []
    pending = len(list(db.scalars(select(Finding.id).where(Finding.engagement_id == e.id,
                                                           Finding.status.not_in(("communicated", "closed"))))))
    issued = db.scalar(select(AuditReport.id).where(AuditReport.engagement_id == e.id, AuditReport.status == "issued"))
    return [
        {"code": "IA_FINDINGS", "label": "Constats validés et communiqués", "passed": pending == 0,
         "detail": f"{pending} en cours" if pending else None},
        {"code": "IA_REPORT", "label": "Rapport émis", "passed": issued is not None, "detail": None},
    ]


def updates_out(db: Session, action_plan_id: uuid.UUID) -> list[dict]:
    ups = list(db.scalars(select(ActionPlanUpdate).where(ActionPlanUpdate.action_plan_id == action_plan_id)
                          .order_by(ActionPlanUpdate.created_at)))
    ppl = people(db, [u.author_id for u in ups])
    return [{**row(u, UPD_FIELDS), "author": ppl.get(str(u.author_id))} for u in ups]
