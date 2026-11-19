"""Socle d'audit : contexte de mission, sérialisation, supervision, instantanés de données."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from fastapi import Depends
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.errors import AppError, Forbidden, NotFound
from app.core.security import AuthenticatedUser
from app.engines.audit import workflow as wf
from app.models import (
    Engagement,
    EngagementMember,
    EngagementRisk,
    FiscalYear,
    MethodologyItem,
    Procedure,
    ProcedureRisk,
    Profile,
    ReviewNote,
    Signoff,
    TrialBalanceEntry,
    Workpaper,
)


class AuditInvalid(AppError):
    status_code = 422
    code = "audit_invalid"


def js(v):
    """Valeurs sérialisables : Decimal en texte exact, dates ISO."""
    if isinstance(v, Decimal):
        return format(v.normalize(), "f")
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    if isinstance(v, uuid.UUID):
        return str(v)
    if isinstance(v, dict):
        return {k: js(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [js(x) for x in v]
    return v


def row(obj, fields: tuple[str, ...]) -> dict:
    return {f: js(getattr(obj, f)) for f in fields}


# ------------------------------------------------------------------ contexte de mission
@dataclass
class EngagementContext:
    engagement: Engagement
    role: str | None
    independent: bool
    user: AuthenticatedUser
    is_org_admin: bool

    @property
    def caps(self) -> list[str]:
        return wf.capabilities(self.role, self.independent, self.engagement.status)

    def require(self, cap: str) -> None:
        if cap not in self.caps:
            if self.role and self.role not in ("auditee", "observer") and not self.independent:
                raise Forbidden("Confirmez d'abord votre indépendance pour cette mission.")
            raise Forbidden("Votre rôle sur cette mission ne permet pas cette action.",
                            details={"capability": cap, "role": self.role, "status": self.engagement.status})


def load_context(db: Session, engagement_id: uuid.UUID, user: AuthenticatedUser) -> EngagementContext:
    e = db.get(Engagement, engagement_id)       # RLS : invisible si l'utilisateur n'y a pas accès
    if e is None:
        raise NotFound("Mission introuvable")
    m = db.scalar(select(EngagementMember).where(EngagementMember.engagement_id == e.id,
                                                 EngagementMember.user_id == user.id))
    admin = bool(db.execute(text("SELECT authz.has_org_role(:o, ARRAY['owner','admin'])"),
                            {"o": e.organization_id}).scalar())
    return EngagementContext(e, m.role if m else None, bool(m and m.independence_confirmed_at), user, admin)


def get_engagement_context(engagement_id: uuid.UUID, db: Session = Depends(get_db),
                           user: AuthenticatedUser = Depends(get_current_user)) -> EngagementContext:
    return load_context(db, engagement_id, user)


def owned(db: Session, ctx: EngagementContext, model, obj_id: uuid.UUID, what: str):
    obj = db.get(model, obj_id)
    if obj is None or obj.engagement_id != ctx.engagement.id:
        raise NotFound(f"{what} introuvable")
    return obj


# ------------------------------------------------------------------ présentation
ENGAGEMENT_FIELDS = ("id", "organization_id", "company_id", "fiscal_year_id", "engagement_type", "reference", "name",
                     "objectives", "scope", "period_start", "period_end", "planned_start", "planned_end",
                     "methodology_version_id", "status", "issued_at", "issued_by", "archived_at", "reopened_at",
                     "reopen_reason", "created_by", "created_at")


def people(db: Session, ids) -> dict[str, dict]:
    ids = {i for i in ids if i}
    if not ids:
        return {}
    return {str(p.id): {"id": str(p.id), "email": p.email, "full_name": p.full_name}
            for p in db.scalars(select(Profile).where(Profile.id.in_(ids)))}


def members_out(db: Session, e: Engagement) -> list[dict]:
    ms = list(db.scalars(select(EngagementMember).where(EngagementMember.engagement_id == e.id)
                         .order_by(EngagementMember.created_at)))
    ppl = people(db, [m.user_id for m in ms])
    order = {r: i for i, r in enumerate(wf.ROLES)}
    out = [{**row(m, ("id", "user_id", "role", "planned_hours", "independence_confirmed_at", "created_at")),
            "user": ppl.get(str(m.user_id)), "role_label": wf.ROLE_LABELS[m.role]} for m in ms]
    return sorted(out, key=lambda x: order.get(x["role"], 99))


def signoffs_for(db: Session, object_type: str, object_id: uuid.UUID, active_only: bool = False) -> list[dict]:
    q = select(Signoff).where(Signoff.object_type == object_type, Signoff.object_id == object_id)
    if active_only:
        q = q.where(Signoff.revoked_at.is_(None))
    sos = list(db.scalars(q.order_by(Signoff.signed_at)))
    ppl = people(db, [s.user_id for s in sos])
    return [{**row(s, ("id", "signoff_role", "user_id", "member_role", "content_hash", "signed_at", "revoked_at",
                       "revoked_reason")), "user": ppl.get(str(s.user_id))} for s in sos]


def methodology_items(db: Session, e: Engagement, item_type: str | None = None) -> list[MethodologyItem]:
    if not e.methodology_version_id:
        return []
    q = select(MethodologyItem).where(MethodologyItem.version_id == e.methodology_version_id)
    if item_type:
        q = q.where(MethodologyItem.item_type == item_type)
    return list(db.scalars(q.order_by(MethodologyItem.item_type, MethodologyItem.display_order, MethodologyItem.code)))


def risk_scale(db: Session, e: Engagement) -> dict | None:
    items = methodology_items(db, e, "risk_scale")
    return items[0].content if items else None


# ------------------------------------------------------------------ supervision
def supervision(db: Session, e: Engagement) -> dict:
    wps = list(db.scalars(select(Workpaper).where(Workpaper.engagement_id == e.id)))
    procs = list(db.scalars(select(Procedure).where(Procedure.engagement_id == e.id)))
    notes = list(db.scalars(select(ReviewNote).where(ReviewNote.engagement_id == e.id)))
    risks = list(db.scalars(select(EngagementRisk).where(EngagementRisk.engagement_id == e.id)))
    links = list(db.scalars(select(ProcedureRisk).where(ProcedureRisk.engagement_id == e.id)))
    coverage: dict[str, int] = {}
    for link in links:
        coverage[str(link.engagement_risk_id)] = coverage.get(str(link.engagement_risk_id), 0) + 1
    members = members_out(db, e)
    sup = wf.supervise(
        workpapers=[{"status": w.status} for w in wps], procedures=[{"status": p.status} for p in procs],
        notes=[{"status": n.status} for n in notes],
        risks=[{"id": str(r.id), "code": r.code, "title": r.title, "is_significant": r.is_significant} for r in risks],
        coverage=coverage,
        members=[{"role": m["role"], "independent": bool(m["independence_confirmed_at"]),
                  "name": (m["user"] or {}).get("full_name") or (m["user"] or {}).get("email") or "?"} for m in members],
        engagement_signoffs=[s for s in signoffs_for(db, "engagement", e.id, active_only=True)])
    from app.services.financial_audit import fa_checks   # import local : évite un cycle

    checks = [{"code": c.code, "label": c.label, "passed": c.passed, "detail": c.detail} for c in sup.issuance_checks]
    checks += fa_checks(db, e)
    from app.services.internal_audit import ia_checks   # import local : évite un cycle

    checks += ia_checks(db, e)
    today = date.today()
    overdue = [row(p, ("id", "code", "title", "due_date", "assigned_to", "status")) for p in procs
               if p.due_date and p.due_date < today and p.status in ("not_started", "in_progress")]
    return {
        "workpapers": sup.workpapers, "procedures": sup.procedures, "open_notes": sup.open_notes,
        "answered_notes": sup.answered_notes, "risks_total": sup.risks_total, "risks_uncovered": sup.risks_uncovered,
        "significant_uncovered": sup.significant_uncovered, "members_pending_independence": sup.members_pending_independence,
        "overdue_procedures": overdue,
        "issuance_checks": checks,
        "ready_to_issue": all(c["passed"] for c in checks),
    }


# ------------------------------------------------------------------ instantané de balance (élément probant)
def balance_snapshot(db: Session, e: Engagement) -> tuple[dict, dict, str]:
    if not e.fiscal_year_id:
        raise AuditInvalid("La mission n'est rattachée à aucun exercice.")
    fy = db.get(FiscalYear, e.fiscal_year_id)
    if fy is None or fy.active_import_job_id is None:
        raise AuditInvalid("Aucune balance validée pour l'exercice de la mission.")
    rows = [{"account": r.account_number, "label": r.account_label,
             "opening_debit": js(r.opening_debit), "opening_credit": js(r.opening_credit),
             "movement_debit": js(r.movement_debit), "movement_credit": js(r.movement_credit),
             "closing_debit": js(r.closing_debit), "closing_credit": js(r.closing_credit)}
            for r in db.scalars(select(TrialBalanceEntry).where(TrialBalanceEntry.import_job_id == fy.active_import_job_id)
                                .order_by(TrialBalanceEntry.account_number))]
    snapshot = {"type": "trial_balance", "fiscal_year": fy.label, "rows": rows}
    ref = {"table": "trial_balance_entries", "import_job_id": str(fy.active_import_job_id), "fiscal_year_id": str(fy.id),
           "rows": len(rows)}
    digest = hashlib.sha256(json.dumps(snapshot, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return snapshot, ref, digest
