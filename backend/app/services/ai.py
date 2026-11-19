"""Service IA (lot 10) : vérifie l'activation et la configuration, construit le contexte calculé, appelle le modèle,
contrôle sa réponse, puis l'enregistre sous l'acteur IA (aucune table métier ne peut alors être écrite). Les
décisions (accepter, rejeter, relire) sont prises hors acteur IA, au nom de l'utilisateur authentifié."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from decimal import Decimal

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import Conflict, Forbidden, NotFound, ServiceUnavailable
from app.engines.ai import context as aictx
from app.engines.ai import numbers, parse, prompts, provider
from app.models import (
    AiConversation,
    AiMessage,
    AiReport,
    AiSettings,
    AiSuggestion,
    Company,
    ControlTest,
    Engagement,
    EngagementRisk,
    FinancialAnalysis,
    Finding,
    FiscalYear,
    Procedure,
    ProcedureRisk,
    Process,
    Recommendation,
    Risk,
    WorkProgram,
    Workpaper,
)
from app.services import analysis as analysis_svc
from app.services import internal_audit as isvc
from app.services import ledger as ledger_svc
from app.services.engagements import AuditInvalid, EngagementContext, methodology_items, owned

USES = {
    "finance_assistant": "Assistant financier (questions sur les analyses)",
    "analysis_commentary": "Commentaires d'analyse financière",
    "audit_risks": "Suggestions de risques d'audit",
    "audit_procedures": "Suggestions de procédures (programmes types)",
    "anomaly_explanation": "Explication des analyses du grand livre",
    "drafting": "Projets de constats et de synthèses",
}
KIND_USE = {
    "engagement_risk": "audit_risks",
    "procedure": "audit_procedures",
    "anomaly_explanation": "anomaly_explanation",
    "finding_draft": "drafting",
    "synthesis_draft": "drafting",
}
KIND_CAP = {
    "engagement_risk": "plan",
    "procedure": "plan",
    "finding_draft": "edit_findings",
    "synthesis_draft": "edit_findings",
    "anomaly_explanation": "edit_procedures",
}
KIND_LABELS = {
    "engagement_risk": "Risques à évaluer",
    "procedure": "Procédures (programmes types)",
    "finding_draft": "Projet de constat",
    "synthesis_draft": "Projet de synthèse",
    "anomaly_explanation": "Explication des analyses du grand livre",
}
IA_TYPES = ("internal_audit", "ic_assessment")
SUGGESTION_FIELDS = (
    "id",
    "engagement_id",
    "kind",
    "payload",
    "sources",
    "context_snapshot",
    "validation",
    "model",
    "prompt_version",
    "status",
    "requested_by",
    "decided_by",
    "decided_at",
    "decision_note",
    "accepted_payload",
    "created_object_type",
    "created_object_id",
    "created_at",
)
EDITABLE = {
    "engagement_risk": ("code", "title", "description", "cycle_code", "assertion_codes"),
    "procedure": ("code", "title"),
    "finding_draft": (
        "reference",
        "title",
        "condition",
        "criteria",
        "cause",
        "effect",
        "recommendation",
        "recommendation_reference",
    ),
    "synthesis_draft": ("title", "text"),
    "anomaly_explanation": ("explanation", "what_to_examine"),
}


# ------------------------------------------------------------------ configuration et activation
def provider_config() -> provider.ProviderConfig:
    s = get_settings()
    return provider.ProviderConfig(
        s.ai_provider, s.ai_api_key, s.ai_model, s.ai_max_output_tokens, s.ai_timeout_seconds, s.ai_base_url
    )


def status_out() -> dict:
    cfg = provider_config()
    ok, reason = provider.status(cfg)
    return {
        "configured": ok,
        "reason": reason,
        "provider": cfg.provider if ok else None,
        "model": cfg.model if ok else None,
        "prompt_version": prompts.PROMPT_VERSION,
        "uses": USES,
    }


def settings_out(db: Session, org_id: uuid.UUID) -> dict:
    s = db.get(AiSettings, org_id)
    return {
        "organization_id": str(org_id),
        "enabled": bool(s and s.enabled),
        "allowed_uses": list(s.allowed_uses) if s else [],
        "acceptance_note": s.acceptance_note if s else None,
        "updated_at": s.updated_at if s else None,
        "updated_by": str(s.updated_by) if s else None,
    }


def save_settings(db: Session, org_id: uuid.UUID, user_id: uuid.UUID, enabled: bool, uses: list[str], note: str | None) -> dict:
    s = db.get(AiSettings, org_id)
    if s is None:
        s = AiSettings(organization_id=org_id, updated_by=user_id)
        db.add(s)
    s.enabled, s.allowed_uses, s.acceptance_note, s.updated_by = enabled, sorted(set(uses)), note, user_id
    db.flush()
    db.refresh(s)
    return settings_out(db, org_id)


def require_use(db: Session, org_id: uuid.UUID, use: str) -> None:
    if not db.execute(text("SELECT public.ai_allowed(:o, :u)"), {"o": org_id, "u": use}).scalar():
        raise Conflict(
            f"IA non activée pour l'usage « {USES[use]} » dans l'organisation (réglages réservés aux administrateurs)."
        )


@contextmanager
def ai_actor(db: Session) -> Iterator[None]:
    """Pendant l'enregistrement d'une sortie du modèle : la base refuse toute écriture métier."""
    db.execute(text("SELECT set_config('kofinex.actor', 'ai', true)"))
    try:
        yield
        db.flush()
    finally:
        db.execute(text("SELECT set_config('kofinex.actor', '', true)"))


def _complete(system: str, messages: list[dict]) -> provider.Completion:
    cfg = provider_config()
    ok, reason = provider.status(cfg)
    if not ok:
        raise ServiceUnavailable(f"IA indisponible : {reason}")
    try:
        return provider.complete(cfg, system, messages)
    except provider.ProviderError as exc:
        raise ServiceUnavailable(str(exc)) from exc


# ------------------------------------------------------------------ contexte financier
def _analysis_for(
    db: Session, company_id: uuid.UUID, fy_id: uuid.UUID | None, analysis_id: uuid.UUID | None
) -> FinancialAnalysis:
    if analysis_id:
        a = db.get(FinancialAnalysis, analysis_id)
        if a is None or a.company_id != company_id:
            raise NotFound("Analyse introuvable")
    else:
        a = db.scalars(
            select(FinancialAnalysis)
            .where(
                FinancialAnalysis.company_id == company_id,
                FinancialAnalysis.fiscal_year_id == fy_id,
                FinancialAnalysis.status == "completed",
            )
            .order_by(FinancialAnalysis.completed_at.desc())
        ).first()
        if a is None:
            raise AuditInvalid("Aucune analyse financière terminée pour cet exercice : lancez d'abord l'analyse.")
    if a.status != "completed":
        raise AuditInvalid("L'analyse doit être terminée : l'IA ne commente que des valeurs calculées.")
    return a


def finance_context(db: Session, a: FinancialAnalysis) -> aictx.Context:
    company = db.get(Company, a.company_id)
    fy = db.get(FiscalYear, a.fiscal_year_id)
    prev = db.get(FiscalYear, a.previous_fiscal_year_id) if a.previous_fiscal_year_id else None
    detail = analysis_svc.analysis_detail(db, a)
    return aictx.finance(
        {"name": company.name},
        {"label": fy.label, "start_date": fy.start_date, "end_date": fy.end_date},
        detail,
        prev.label if prev else None,
    )


# ------------------------------------------------------------------ assistant financier
CONV_FIELDS = ("id", "company_id", "fiscal_year_id", "analysis_id", "title", "created_at", "updated_at")
MSG_FIELDS = (
    "id",
    "role",
    "content",
    "context_snapshot",
    "model",
    "input_tokens",
    "output_tokens",
    "validation",
    "prompt_version",
    "created_at",
)


def create_conversation(db: Session, *, org_id, company_id, user_id, fiscal_year_id, analysis_id, title) -> AiConversation:
    require_use(db, org_id, "finance_assistant")
    a = _analysis_for(db, company_id, fiscal_year_id, analysis_id)
    c = AiConversation(
        id=uuid.uuid4(),
        organization_id=org_id,
        company_id=company_id,
        user_id=user_id,
        fiscal_year_id=a.fiscal_year_id,
        analysis_id=a.id,
        title=(title or "").strip() or None,
    )
    db.add(c)
    db.flush()
    return c


def post_message(db: Session, c: AiConversation, content: str) -> list[AiMessage]:
    require_use(db, c.organization_id, "finance_assistant")
    if c.analysis_id is None:
        raise AuditInvalid("Conversation sans analyse de référence.")
    ctx = finance_context(db, _analysis_for(db, c.company_id, c.fiscal_year_id, c.analysis_id))
    history = list(db.scalars(select(AiMessage).where(AiMessage.conversation_id == c.id).order_by(AiMessage.created_at)))[-10:]
    q = AiMessage(id=uuid.uuid4(), organization_id=c.organization_id, conversation_id=c.id, role="user", content=content.strip())
    db.add(q)
    db.flush()
    msgs = [{"role": m.role, "content": m.content} for m in history if m.role in ("user", "assistant")]
    msgs.append({"role": "user", "content": prompts.user_message(ctx.to_prompt(), content.strip())})
    out = _complete(prompts.CHAT, msgs)
    snap = ctx.snapshot()
    with ai_actor(db):
        r = AiMessage(
            id=uuid.uuid4(),
            organization_id=c.organization_id,
            conversation_id=c.id,
            role="assistant",
            content=out.text,
            context_snapshot=snap,
            model=out.model,
            input_tokens=out.input_tokens,
            output_tokens=out.output_tokens,
            validation=numbers.check(out.text, snap),
            prompt_version=prompts.PROMPT_VERSION,
        )
        db.add(r)
    c.title = c.title or content.strip()[:80]
    db.flush()
    return [q, r]


# ------------------------------------------------------------------ commentaires d'analyse
REPORT_FIELDS = (
    "id",
    "analysis_id",
    "section",
    "content",
    "context_snapshot",
    "model",
    "prompt_version",
    "validation",
    "status",
    "reviewed_by",
    "reviewed_at",
    "review_note",
    "created_by",
    "created_at",
)


def generate_commentary(db: Session, a: FinancialAnalysis, section: str, user_id: uuid.UUID) -> AiReport:
    if section not in prompts.SECTIONS:
        raise AuditInvalid("Section inconnue.")
    require_use(db, a.organization_id, "analysis_commentary")
    a = _analysis_for(db, a.company_id, a.fiscal_year_id, a.id)
    ctx = finance_context(db, a)
    out = _complete(
        prompts.commentary(section),
        [{"role": "user", "content": prompts.user_message(ctx.to_prompt(), f"Rédige la section « {section} ».")}],
    )
    snap = ctx.snapshot()
    with ai_actor(db):
        r = AiReport(
            id=uuid.uuid4(),
            organization_id=a.organization_id,
            company_id=a.company_id,
            analysis_id=a.id,
            section=section,
            content=out.text,
            context_snapshot=snap,
            model=out.model,
            prompt_version=prompts.PROMPT_VERSION,
            validation=numbers.check(out.text, snap),
            created_by=user_id,
        )
        db.add(r)
    return r


def review_commentary(db: Session, r: AiReport, user_id: uuid.UUID, decision: str, note: str | None) -> AiReport:
    if r.status != "draft":
        raise Conflict("Commentaire déjà relu.")
    r.status, r.reviewed_by, r.review_note = decision, user_id, (note or "").strip() or None
    db.flush()
    db.refresh(r)
    return r


# ------------------------------------------------------------------ suggestions d'audit
def _eng(e: Engagement) -> dict:
    return {k: getattr(e, k) for k in ("reference", "name", "engagement_type", "objectives", "scope")} | {
        "period_start": str(e.period_start) if e.period_start else None,
        "period_end": str(e.period_end) if e.period_end else None,
    }


def _items(db: Session, e: Engagement, t: str) -> list[dict]:
    return [{"code": i.code, "label": i.label, "content": i.content} for i in methodology_items(db, e, t)]


def suggestion_context(db: Session, ctx: EngagementContext, kind: str, params: dict) -> aictx.Context:
    e = ctx.engagement
    ers = list(db.scalars(select(EngagementRisk).where(EngagementRisk.engagement_id == e.id).order_by(EngagementRisk.code)))
    er_dicts = [
        {
            "code": r.code,
            "title": r.title,
            "description": r.description,
            "cycle_code": r.cycle_code,
            "assertion_codes": r.assertion_codes,
            "likelihood": r.likelihood,
            "impact": r.impact,
            "is_significant": r.is_significant,
        }
        for r in ers
    ]
    if kind == "engagement_risk":
        procs = {p.id: p.name for p in db.scalars(select(Process).where(Process.company_id == e.company_id))}
        reg = [
            {"code": r.code, "title": r.title, "description": r.description, "process": procs.get(r.process_id)}
            for r in db.scalars(select(Risk).where(Risk.company_id == e.company_id, Risk.status == "active").order_by(Risk.code))
        ]
        fin = None
        if e.fiscal_year_id:
            a = db.scalars(
                select(FinancialAnalysis)
                .where(FinancialAnalysis.fiscal_year_id == e.fiscal_year_id, FinancialAnalysis.status == "completed")
                .order_by(FinancialAnalysis.completed_at.desc())
            ).first()
            fin = finance_context(db, a) if a else None
        return aictx.audit_risks(_eng(e), reg, er_dicts, _items(db, e, "cycle"), _items(db, e, "assertion"), fin)
    if kind == "procedure":
        templates = _items(db, e, "procedure_template")
        if not templates:
            raise AuditInvalid("La méthodologie de la mission ne contient aucun programme type : rien à proposer.")
        if not ers:
            raise AuditInvalid("Évaluez d'abord les risques de la mission.")
        existing = [c for (c,) in db.execute(select(Procedure.code).where(Procedure.engagement_id == e.id))]
        return aictx.audit_procedures(_eng(e), templates, er_dicts, existing)
    if kind == "finding_draft":
        st, sid = params.get("source_type"), params.get("source_id")
        if st == "workpaper":
            w = owned(db, ctx, Workpaper, uuid.UUID(str(sid)), "Feuille de travail")
            source = {
                "type": "feuille de travail",
                "reference": w.reference,
                "title": w.title,
                "objective": w.objective,
                "work_performed": w.work_performed,
                "conclusion": w.conclusion,
                "status": w.status,
            }
        elif st == "control_test":
            t = owned(db, ctx, ControlTest, uuid.UUID(str(sid)), "Test de contrôle")
            source = {
                "type": "test de contrôle",
                "reference": t.reference,
                "test_type": t.test_type,
                "procedure": t.test_procedure,
                "period": [str(t.period_start), str(t.period_end)],
                "results_summary": t.results_summary,
                "exceptions_summary": t.exceptions_summary,
                "conclusion": t.conclusion,
                "rationale": t.conclusion_rationale,
                "status": t.status,
            }
        else:
            raise AuditInvalid("Source du projet de constat : feuille de travail ou test de contrôle.")
        if not any(source.get(k) for k in ("work_performed", "conclusion", "results_summary", "exceptions_summary")):
            raise AuditInvalid("La source ne contient encore aucun travail ni résultat enregistré.")
        return aictx.finding_draft(
            _eng(e), source, isvc.levels(db, e, "ic_deficiency" if e.engagement_type == "ic_assessment" else "audit_finding")
        )
    if kind == "synthesis_draft":
        fs = list(
            db.scalars(
                select(Finding).where(Finding.engagement_id == e.id, Finding.status != "draft").order_by(Finding.reference)
            )
        )
        if not fs:
            raise AuditInvalid("Aucun constat validé : la synthèse s'appuie sur des constats validés.")
        recs: dict = {}
        for r in db.scalars(select(Recommendation).where(Recommendation.finding_id.in_([f.id for f in fs]))):
            recs.setdefault(r.finding_id, []).append(r.text)
        lv = {x["code"]: x["label"] for x in isvc.levels(db, e) + isvc.levels(db, e, "ic_deficiency")}
        return aictx.synthesis_draft(
            _eng(e),
            [
                {
                    "reference": f.reference,
                    "title": f.title,
                    "condition": f.condition,
                    "criteria": f.criteria,
                    "cause": f.cause,
                    "effect": f.effect,
                    "rating_label": lv.get(f.rating_code or ""),
                    "recommendations": recs.get(f.id, []),
                    "management_response": f.management_response,
                }
                for f in fs
            ],
        )
    if kind == "anomaly_explanation":
        if not e.fiscal_year_id:
            raise AuditInvalid("Mission sans exercice : aucune analyse du grand livre.")
        fy = db.get(FiscalYear, e.fiscal_year_id)
        rm = params.get("round_multiple")
        data = ledger_svc.analytics(
            db, fy, round_multiple=Decimal(str(rm)) if rm else None, benford_min=Decimal(str(params.get("benford_min") or 0))
        )
        return aictx.anomalies(_eng(e), {"label": fy.label, "start_date": fy.start_date, "end_date": fy.end_date}, data)
    raise AuditInvalid("Type de suggestion inconnu.")


def generate_suggestions(db: Session, ctx: EngagementContext, kind: str, params: dict, request_text: str | None) -> dict:
    if kind in ("finding_draft", "synthesis_draft") and ctx.engagement.engagement_type not in IA_TYPES:
        raise AuditInvalid(
            "Les projets de constats et de synthèses concernent les missions d'audit interne et de contrôle interne."
        )
    ctx.require(KIND_CAP[kind])
    require_use(db, ctx.engagement.organization_id, KIND_USE[kind])
    c = suggestion_context(db, ctx, kind, params)
    ask = (request_text or "").strip() or "Formule tes propositions."
    out = _complete(prompts.TASKS[kind], [{"role": "user", "content": prompts.user_message(c.to_prompt(), ask)}])
    try:
        kept, rejected = parse.suggestions(kind, out.text, c)
    except parse.ParseError as exc:
        raise ServiceUnavailable(f"Réponse du modèle inexploitable : {exc}") from exc
    snap = c.snapshot()
    created = []
    with ai_actor(db):
        for k in kept:
            s = AiSuggestion(
                id=uuid.uuid4(),
                organization_id=ctx.engagement.organization_id,
                company_id=ctx.engagement.company_id,
                engagement_id=ctx.engagement.id,
                kind=kind,
                payload=k.payload,
                sources=k.sources,
                context_snapshot=snap,
                validation={**k.validation, "discarded_by_kofinex": rejected, "request": ask},
                model=out.model,
                prompt_version=prompts.PROMPT_VERSION,
                input_tokens=out.input_tokens,
                output_tokens=out.output_tokens,
                requested_by=ctx.user.id,
            )
            db.add(s)
            created.append(s)
    return {"created": [str(s.id) for s in created], "discarded": rejected}


def reject(db: Session, ctx: EngagementContext, s: AiSuggestion, note: str) -> AiSuggestion:
    ctx.require(KIND_CAP[s.kind])
    if s.status != "pending":
        raise Conflict("Suggestion déjà décidée.")
    s.status, s.decided_by, s.decision_note = "rejected", ctx.user.id, note.strip()
    db.flush()
    return s


def accept(db: Session, ctx: EngagementContext, s: AiSuggestion, edits: dict, params: dict, note: str | None) -> AiSuggestion:
    """Acceptation (éventuellement corrigée) puis création de l'objet en brouillon, au nom de l'utilisateur."""
    ctx.require(KIND_CAP[s.kind])
    if s.status != "pending":
        raise Conflict("Suggestion déjà décidée.")
    e = ctx.engagement
    payload = {**s.payload, **{k: v for k, v in (edits or {}).items() if k in EDITABLE[s.kind]}}
    s.status, s.decided_by, s.accepted_payload = "accepted", ctx.user.id, payload
    s.decision_note = (note or "").strip() or None
    db.flush()
    obj = None
    if s.kind == "engagement_risk":
        obj = EngagementRisk(
            id=uuid.uuid4(),
            organization_id=e.organization_id,
            engagement_id=e.id,
            code=str(payload["code"]).strip(),
            title=str(payload["title"]).strip(),
            description=payload.get("description"),
            cycle_code=payload.get("cycle_code"),
            assertion_codes=payload.get("assertion_codes") or [],
            origin="ai_suggestion",
            ai_suggestion_id=s.id,
            created_by=ctx.user.id,
        )
        db.add(obj)
        db.flush()
        s.created_object_type = "engagement_risks"
    elif s.kind == "procedure":
        pid = params.get("program_id")
        if not pid:
            raise AuditInvalid("Choisissez le programme de travail qui recevra la procédure.")
        prog = owned(db, ctx, WorkProgram, uuid.UUID(str(pid)), "Programme")
        t = next((i for i in methodology_items(db, e, "procedure_template") if i.code == payload["template_code"]), None)
        if t is None:
            raise AuditInvalid("Programme type absent de la méthodologie de la mission.")
        obj = Procedure(
            id=uuid.uuid4(),
            organization_id=e.organization_id,
            engagement_id=e.id,
            program_id=prog.id,
            code=str(payload.get("code") or t.code),
            title=str(payload.get("title") or t.label),
            objective=t.content.get("objective"),
            nature=t.content.get("nature", "other"),
            steps=t.content.get("steps", []),
            assertion_codes=t.content.get("assertions", []),
            template_item_id=t.id,
            origin="ai_suggestion",
            ai_suggestion_id=s.id,
        )
        db.add(obj)
        db.flush()
        risks = {r.code: r.id for r in db.scalars(select(EngagementRisk).where(EngagementRisk.engagement_id == e.id))}
        for code in payload.get("risk_codes") or []:
            if code in risks:
                db.add(ProcedureRisk(engagement_id=e.id, procedure_id=obj.id, engagement_risk_id=risks[code]))
        s.created_object_type = "procedures"
    elif s.kind == "finding_draft":
        ref = str(payload.get("reference") or "").strip()
        if not ref:
            raise AuditInvalid("Donnez une référence au constat.")
        kind = "ic_deficiency" if e.engagement_type == "ic_assessment" else "audit_finding"
        control_id = params.get("control_id")
        if kind == "ic_deficiency" and not control_id:
            raise AuditInvalid("Une déficience de contrôle interne vise un contrôle du catalogue : choisissez-le.")
        obj = Finding(
            id=uuid.uuid4(),
            organization_id=e.organization_id,
            engagement_id=e.id,
            reference=ref,
            title=payload["title"],
            condition=payload["condition"],
            criteria=payload["criteria"],
            cause=payload.get("cause"),
            effect=payload.get("effect"),
            kind=kind,
            control_id=uuid.UUID(str(control_id)) if control_id else None,
            origin="ai_suggestion",
            ai_suggestion_id=s.id,
            created_by=ctx.user.id,
        )
        db.add(obj)
        db.flush()
        if payload.get("recommendation"):
            db.add(
                Recommendation(
                    id=uuid.uuid4(),
                    organization_id=e.organization_id,
                    engagement_id=e.id,
                    finding_id=obj.id,
                    reference=str(payload.get("recommendation_reference") or f"{ref}-R1"),
                    text=payload["recommendation"],
                    created_by=ctx.user.id,
                )
            )
        s.created_object_type = "findings"
    if obj is not None:
        s.created_object_id = obj.id
    db.flush()
    return s


def suggestion_out(s: AiSuggestion, people: dict) -> dict:
    out = {k: getattr(s, k) for k in SUGGESTION_FIELDS}
    out.update(
        kind_label=KIND_LABELS[s.kind],
        requested_by_user=people.get(str(s.requested_by)),
        decided_by_user=people.get(str(s.decided_by)) if s.decided_by else None,
    )
    return out


def require_member_of(ctx: EngagementContext) -> None:
    if ctx.role in (None, "auditee"):
        raise Forbidden("Réservé à l'équipe de la mission.")
