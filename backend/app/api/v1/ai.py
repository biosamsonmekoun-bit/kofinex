"""API — intelligence artificielle (lot 10).

- `/ai/status` : configuration du fournisseur (sans la clé) ;
- `/organizations/{id}/ai-settings` : activation par l'organisation, usage par usage ;
- `/companies/{id}/ai/conversations…` : assistant financier sur une analyse terminée ;
- `/companies/{id}/analyses/{id}/ai-reports`, `/companies/{id}/ai-reports/{id}/review` : commentaires d'analyse, relus ;
- `/engagements/{id}/ai/suggestions…` : suggestions d'audit, acceptées ou rejetées par l'équipe.
Les réponses du modèle sont contrôlées (chiffres, références, codes) et enregistrées sous l'acteur IA."""

from __future__ import annotations

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request, status
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
from app.core.errors import AppError, NotFound
from app.core.permissions import Permission
from app.core.security import AuthenticatedUser
from app.models import AiConversation, AiMessage, AiReport, AiSuggestion, FinancialAnalysis
from app.services import ai as svc
from app.services.audit import record_event
from app.services.engagements import EngagementContext, get_engagement_context, owned, people

router = APIRouter(tags=["ia"])
Db = Annotated[Session, Depends(get_db)]
Comp = Annotated[CompanyContext, Depends(get_company_context)]
Eng = Annotated[EngagementContext, Depends(get_engagement_context)]


def _row(o, fields) -> dict:
    return {k: getattr(o, k) for k in fields}


def _log(db, request, user_id, org_id, action, entity_type, entity_id, details=None, company_id=None):
    record_event(
        db,
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        organization_id=org_id,
        company_id=company_id,
        details=details or {},
        request=request,
    )


# ======================================================================== statut et réglages
@router.get("/ai/status", summary="Fournisseur d'IA configuré (jamais la clé)")
def ai_status(_: Annotated[AuthenticatedUser, Depends(get_current_user)]):
    return svc.status_out()


@router.get("/organizations/{org_id}/ai-settings")
def get_settings_(ctx: Annotated[OrgContext, Depends(get_org_context)], db: Db):
    return {**svc.settings_out(db, ctx.organization_id), "can_edit": ctx.is_manager, "status": svc.status_out()}


class SettingsIn(BaseModel):
    enabled: bool
    allowed_uses: list[
        Literal["finance_assistant", "analysis_commentary", "audit_risks", "audit_procedures", "anomaly_explanation", "drafting"]
    ] = Field(default_factory=list)
    acceptance_note: str | None = Field(default=None, max_length=2000)


@router.put("/organizations/{org_id}/ai-settings", summary="Activer ou désactiver l'IA (administrateurs)")
def put_settings(p: SettingsIn, request: Request, ctx: Annotated[OrgContext, Depends(require_org_manager)], db: Db):
    if p.enabled and len((p.acceptance_note or "").strip()) < 10:
        raise AppError(
            "Indiquez l'accord de l'organisation sur la transmission de données au fournisseur d'IA (10 caractères au moins)."
        )
    out = svc.save_settings(
        db, ctx.organization_id, ctx.user.id, p.enabled, list(p.allowed_uses), (p.acceptance_note or "").strip() or None
    )
    _log(
        db,
        request,
        ctx.user.id,
        ctx.organization_id,
        "ai.settings.update",
        "ai_settings",
        ctx.organization_id,
        {"enabled": p.enabled, "allowed_uses": list(p.allowed_uses)},
    )
    return {**out, "can_edit": True, "status": svc.status_out()}


# ======================================================================== assistant financier
C = "/companies/{company_id}/ai"


def _conv(db: Session, ctx: CompanyContext, conv_id: uuid.UUID) -> AiConversation:
    c = db.get(AiConversation, conv_id)
    if c is None or c.company_id != ctx.company_id or c.user_id != ctx.user.id:
        raise NotFound("Conversation introuvable")
    return c


@router.get(C + "/conversations", summary="Mes conversations sur l'entité")
def list_conversations(ctx: Comp, db: Db):
    cs = db.scalars(
        select(AiConversation)
        .where(AiConversation.company_id == ctx.company_id, AiConversation.user_id == ctx.user.id)
        .order_by(AiConversation.updated_at.desc())
    )
    return [_row(c, svc.CONV_FIELDS) for c in cs]


class ConversationIn(BaseModel):
    fiscal_year_id: uuid.UUID | None = None
    analysis_id: uuid.UUID | None = None
    title: str | None = Field(default=None, max_length=200)


@router.post(C + "/conversations", status_code=status.HTTP_201_CREATED)
def create_conversation(p: ConversationIn, request: Request, ctx: Comp, db: Db):
    ctx.require(Permission.ANALYSIS_RUN)
    if not p.fiscal_year_id and not p.analysis_id:
        raise AppError("Choisissez l'exercice ou l'analyse de référence.")
    c = svc.create_conversation(
        db,
        org_id=ctx.organization_id,
        company_id=ctx.company_id,
        user_id=ctx.user.id,
        fiscal_year_id=p.fiscal_year_id,
        analysis_id=p.analysis_id,
        title=p.title,
    )
    _log(
        db,
        request,
        ctx.user.id,
        ctx.organization_id,
        "ai.conversation.create",
        "ai_conversations",
        c.id,
        {"analysis_id": str(c.analysis_id)},
        ctx.company_id,
    )
    return _row(c, svc.CONV_FIELDS)


@router.get(C + "/conversations/{conv_id}")
def get_conversation(conv_id: uuid.UUID, ctx: Comp, db: Db):
    c = _conv(db, ctx, conv_id)
    ms = db.scalars(select(AiMessage).where(AiMessage.conversation_id == c.id).order_by(AiMessage.created_at))
    return {**_row(c, svc.CONV_FIELDS), "messages": [_row(m, svc.MSG_FIELDS) for m in ms]}


class MessageIn(BaseModel):
    content: str = Field(min_length=2, max_length=4000)


@router.post(
    C + "/conversations/{conv_id}/messages",
    status_code=status.HTTP_201_CREATED,
    summary="Poser une question (réponse du modèle contrôlée, enregistrée sous l'acteur IA)",
)
def post_message(conv_id: uuid.UUID, p: MessageIn, request: Request, ctx: Comp, db: Db):
    ctx.require(Permission.ANALYSIS_RUN)
    c = _conv(db, ctx, conv_id)
    q, r = svc.post_message(db, c, p.content)
    _log(
        db,
        request,
        ctx.user.id,
        ctx.organization_id,
        "ai.message",
        "ai_messages",
        r.id,
        {"model": r.model, "validation": (r.validation or {}).get("status"), "tokens": [r.input_tokens, r.output_tokens]},
        ctx.company_id,
    )
    return [_row(q, svc.MSG_FIELDS), _row(r, svc.MSG_FIELDS)]


# ======================================================================== commentaires d'analyse
def _analysis(db: Session, ctx: CompanyContext, analysis_id: uuid.UUID) -> FinancialAnalysis:
    a = db.get(FinancialAnalysis, analysis_id)
    if a is None or a.company_id != ctx.company_id:
        raise NotFound("Analyse introuvable")
    return a


@router.get("/companies/{company_id}/analyses/{analysis_id}/ai-reports", summary="Commentaires IA d'une analyse")
def list_reports(analysis_id: uuid.UUID, ctx: Comp, db: Db):
    a = _analysis(db, ctx, analysis_id)
    rs = list(db.scalars(select(AiReport).where(AiReport.analysis_id == a.id).order_by(AiReport.created_at.desc())))
    ppl = people(db, [r.created_by for r in rs] + [r.reviewed_by for r in rs])
    return {
        "sections": {k: v for k, v in svc.prompts.SECTIONS.items()},
        "items": [
            {
                **_row(r, svc.REPORT_FIELDS),
                "created_by_user": ppl.get(str(r.created_by)),
                "reviewed_by_user": ppl.get(str(r.reviewed_by)) if r.reviewed_by else None,
            }
            for r in rs
        ],
    }


class ReportIn(BaseModel):
    section: Literal["executive_summary", "balance_sheet", "income_statement", "cash", "ratios", "risks"]


@router.post("/companies/{company_id}/analyses/{analysis_id}/ai-reports", status_code=status.HTTP_201_CREATED)
def create_report(analysis_id: uuid.UUID, p: ReportIn, request: Request, ctx: Comp, db: Db):
    ctx.require(Permission.REPORT_GENERATE)
    r = svc.generate_commentary(db, _analysis(db, ctx, analysis_id), p.section, ctx.user.id)
    _log(
        db,
        request,
        ctx.user.id,
        ctx.organization_id,
        "ai.commentary",
        "ai_reports",
        r.id,
        {"section": p.section, "validation": (r.validation or {}).get("status")},
        ctx.company_id,
    )
    return _row(r, svc.REPORT_FIELDS)


class ReviewIn(BaseModel):
    decision: Literal["reviewed", "rejected"]
    note: str | None = Field(default=None, max_length=2000)


@router.post("/companies/{company_id}/ai-reports/{report_id}/review", summary="Relire un commentaire IA (relu ou rejeté)")
def review_report(report_id: uuid.UUID, p: ReviewIn, request: Request, ctx: Comp, db: Db):
    ctx.require(Permission.REPORT_GENERATE)
    r = db.get(AiReport, report_id)
    if r is None or r.company_id != ctx.company_id:
        raise NotFound("Commentaire introuvable")
    if p.decision == "rejected" and len((p.note or "").strip()) < 3:
        raise AppError("Motif du rejet requis.")
    r = svc.review_commentary(db, r, ctx.user.id, p.decision, p.note)
    _log(
        db,
        request,
        ctx.user.id,
        ctx.organization_id,
        "ai.commentary.review",
        "ai_reports",
        r.id,
        {"decision": p.decision},
        ctx.company_id,
    )
    return _row(r, svc.REPORT_FIELDS)


# ======================================================================== suggestions d'audit
E = "/engagements/{engagement_id}/ai"


def _elog(db, request, ctx: EngagementContext, action, entity_id, details=None):
    _log(
        db,
        request,
        ctx.user.id,
        ctx.engagement.organization_id,
        action,
        "ai_suggestions",
        entity_id,
        {"engagement_id": str(ctx.engagement.id), **(details or {})},
        ctx.engagement.company_id,
    )


@router.get(E + "/suggestions", summary="Suggestions IA de la mission et usages disponibles")
def list_suggestions(ctx: Eng, db: Db):
    ctx.require("read_dossier")
    ss = list(
        db.scalars(
            select(AiSuggestion).where(AiSuggestion.engagement_id == ctx.engagement.id).order_by(AiSuggestion.created_at.desc())
        )
    )
    ppl = people(db, [s.requested_by for s in ss] + [s.decided_by for s in ss])
    allowed = svc.settings_out(db, ctx.engagement.organization_id)
    kinds = []
    for k, label in svc.KIND_LABELS.items():
        use = svc.KIND_USE[k]
        reason = None
        if k in ("finding_draft", "synthesis_draft") and ctx.engagement.engagement_type not in svc.IA_TYPES:
            reason = "Réservé aux missions d'audit interne et de contrôle interne."
        elif not (allowed["enabled"] and use in allowed["allowed_uses"]):
            reason = "Usage non activé par l'organisation."
        elif svc.KIND_CAP[k] not in ctx.caps:
            reason = "Votre rôle sur la mission ne le permet pas."
        kinds.append({"kind": k, "label": label, "available": reason is None, "reason": reason})
    return {"status": svc.status_out(), "kinds": kinds, "items": [svc.suggestion_out(s, ppl) for s in ss]}


class GenerateIn(BaseModel):
    kind: Literal["engagement_risk", "procedure", "finding_draft", "synthesis_draft", "anomaly_explanation"]
    request: str | None = Field(default=None, max_length=2000)
    source_type: Literal["workpaper", "control_test"] | None = None
    source_id: uuid.UUID | None = None
    round_multiple: float | None = Field(default=None, gt=0)
    benford_min: float | None = Field(default=None, ge=0)


@router.post(E + "/suggestions", status_code=status.HTTP_201_CREATED, summary="Demander des suggestions au modèle")
def generate(p: GenerateIn, request: Request, ctx: Eng, db: Db):
    out = svc.generate_suggestions(db, ctx, p.kind, p.model_dump(exclude={"kind", "request"}, mode="json"), p.request)
    _elog(
        db,
        request,
        ctx,
        "ai.suggestion.generate",
        None,
        {"kind": p.kind, "created": out["created"], "discarded": len(out["discarded"])},
    )
    return out


class AcceptIn(BaseModel):
    edits: dict = Field(default_factory=dict)
    program_id: uuid.UUID | None = None
    control_id: uuid.UUID | None = None
    note: str | None = Field(default=None, max_length=2000)


@router.post(E + "/suggestions/{suggestion_id}/accept", summary="Accepter (éventuellement corrigée) : objet créé en brouillon")
def accept(suggestion_id: uuid.UUID, p: AcceptIn, request: Request, ctx: Eng, db: Db):
    s = owned(db, ctx, AiSuggestion, suggestion_id, "Suggestion")
    s = svc.accept(db, ctx, s, p.edits, p.model_dump(include={"program_id", "control_id"}, mode="json"), p.note)
    _elog(db, request, ctx, "ai.suggestion.accept", s.id, {"created_object": [s.created_object_type, str(s.created_object_id)]})
    return svc.suggestion_out(s, people(db, [s.requested_by, s.decided_by]))


class RejectIn(BaseModel):
    note: str = Field(min_length=3, max_length=2000)


@router.post(E + "/suggestions/{suggestion_id}/reject")
def reject(suggestion_id: uuid.UUID, p: RejectIn, request: Request, ctx: Eng, db: Db):
    s = svc.reject(db, ctx, owned(db, ctx, AiSuggestion, suggestion_id, "Suggestion"), p.note)
    _elog(db, request, ctx, "ai.suggestion.reject", s.id, {"note": p.note})
    return svc.suggestion_out(s, people(db, [s.requested_by, s.decided_by]))
