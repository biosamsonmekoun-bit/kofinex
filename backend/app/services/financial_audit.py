"""Audit financier : accès aux balances validées de la mission, états recalculés, synthèse des anomalies."""

from __future__ import annotations

import hashlib
import json
import uuid
from decimal import Decimal

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.engines.accounting.statements import LineDef, MappingRule, StatementError, TBEntry, build_statements
from app.engines.audit import financial as fa
from app.models import (
    Engagement,
    FaAccountReview,
    FaConclusion,
    FaConfirmation,
    FaMateriality,
    FaMisstatement,
    FaMisstatementLine,
    FaSample,
    FiscalYear,
    FrameworkVersion,
)
from app.services.analysis import _entries, _framework, _previous_fy
from app.services.engagements import AuditInvalid, js

FA_TYPES = ("statutory_audit", "contractual_audit")


def require_fa(e: Engagement) -> None:
    if e.engagement_type not in FA_TYPES:
        raise AuditInvalid("Fonction réservée aux missions d'audit légal ou contractuel.")


def sampling_on(db: Session) -> None:
    """Autorise, pour la transaction en cours, les écritures réservées au moteur (sélection, projection)."""
    db.execute(text("SELECT set_config('kofinex.sampling', 'on', true)"))


def sampling_off(db: Session) -> None:
    db.execute(text("SELECT set_config('kofinex.sampling', 'off', true)"))


# ------------------------------------------------------------------ balances de la mission
class Balances:
    def __init__(self, fy: FiscalYear, cur_job: uuid.UUID, prev_fy: FiscalYear | None, prev_job: uuid.UUID | None,
                 cur: list[TBEntry], prev: list[TBEntry] | None):
        self.fy, self.cur_job, self.prev_fy, self.prev_job, self.cur, self.prev = fy, cur_job, prev_fy, prev_job, cur, prev


def balances(db: Session, e: Engagement) -> Balances:
    if not e.fiscal_year_id:
        raise AuditInvalid("La mission n'est rattachée à aucun exercice : rattachez-la à l'exercice audité.")
    fy = db.get(FiscalYear, e.fiscal_year_id)
    if fy is None or fy.active_import_job_id is None:
        raise AuditInvalid("Aucune balance validée pour l'exercice audité : importez et validez la balance d'abord.")
    prev_fy = _previous_fy(db, fy)
    prev_job = prev_fy.active_import_job_id if prev_fy else None
    return Balances(fy, fy.active_import_job_id, prev_fy, prev_job, _entries(db, fy.active_import_job_id),
                    _entries(db, prev_job) if prev_job else None)


def framework(db: Session, fy: FiscalYear) -> tuple[list[LineDef], list[MappingRule]] | None:
    v = db.get(FrameworkVersion, fy.framework_version_id) if fy.framework_version_id else None
    if v is None or v.status not in ("published", "deprecated"):
        return None
    structure, rules, _ = _framework(db, v.id)
    return (structure, rules) if structure else None


def statement_lines(db: Session, e: Engagement) -> list[dict]:
    """Lignes des états de l'exercice (pour choisir l'agrégat de référence des seuils)."""
    b = balances(db, e)
    fw = framework(db, b.fy)
    if fw is None:
        return []
    try:
        res = build_statements(b.cur, *fw)
    except StatementError:
        return []
    return [{"statement_type": st, "code": ln.definition.code, "label": ln.definition.label, "kind": ln.definition.kind,
             "role": ln.definition.role, "net": js(ln.net) if ln.net is not None else None}
            for st, lines in res.statements.items() for ln in lines if ln.definition.kind != "title"]


def approved_materiality(db: Session, e: Engagement) -> FaMateriality | None:
    return db.scalar(select(FaMateriality).where(FaMateriality.engagement_id == e.id, FaMateriality.status == "approved"))


def population_hash(items: list[dict]) -> str:
    return hashlib.sha256(json.dumps(items, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


# ------------------------------------------------------------------ anomalies
def misstatement_lines(db: Session, mid: uuid.UUID) -> list[fa.AdjLine]:
    return [fa.AdjLine(r.account_number, r.label, r.debit, r.credit)
            for r in db.scalars(select(FaMisstatementLine).where(FaMisstatementLine.misstatement_id == mid))]


def _role_effect(effects: list[fa.LineEffect], role: str) -> Decimal:
    return next((x.delta for x in effects if x.role == role), Decimal(0))


def summary(db: Session, e: Engagement) -> dict:
    """Synthèse : anomalies par statut, effet de chacune et du cumul sur les états (même moteur que les états publiés),
    position par rapport aux seuils approuvés. Aucune conclusion n'est tirée : elle revient à l'auditeur."""
    mat = approved_materiality(db, e)
    overall, trivial = (mat.overall_amount, mat.trivial_amount) if mat else (None, None)
    b = balances(db, e)
    fw = framework(db, b.fy)
    ms = list(db.scalars(select(FaMisstatement).where(FaMisstatement.engagement_id == e.id).order_by(FaMisstatement.reference)))
    lines = {m.id: misstatement_lines(db, m.id) for m in ms}
    out_items = []
    for m in ms:
        eff = fa.effects(b.cur, lines[m.id], *fw) if fw else []
        res = _role_effect(eff, "resultat_compte_resultat")
        out_items.append({"id": str(m.id), "reference": m.reference, "kind": m.kind, "status": m.status,
                          "description": m.description, "amount": js(sum((ln.debit for ln in lines[m.id]), Decimal(0))),
                          "effect_result": js(res) if fw else None,
                          "position": fa.compare_to_materiality(res, overall, trivial) if fw else None})

    def aggregate(statuses: tuple[str, ...]) -> dict:
        all_lines = [ln for m in ms if m.status in statuses for ln in lines[m.id]]
        if not fw:
            return {"count": sum(1 for m in ms if m.status in statuses), "effects": None}
        eff = fa.effects(b.cur, all_lines, *fw) if all_lines else []
        res = _role_effect(eff, "resultat_compte_resultat")
        return {"count": sum(1 for m in ms if m.status in statuses),
                "effect_result": js(res), "effect_total_assets": js(_role_effect(eff, "total_actif")),
                "position": fa.compare_to_materiality(res, overall, trivial),
                "effects": [{"statement_type": x.statement_type, "code": x.code, "label": x.label, "before": js(x.before),
                             "after": js(x.after), "delta": js(x.delta)} for x in eff]}

    concl = db.get(FaConclusion, e.id)
    return {
        "framework_available": fw is not None,
        "materiality": {"overall": js(overall), "performance": js(mat.performance_amount), "trivial": js(trivial),
                        "version": mat.version} if mat else None,
        "items": out_items,
        "corrected": aggregate(("corrected",)),
        "uncorrected": aggregate(("uncorrected",)),
        "proposed": aggregate(("proposed",)),
        "conclusion": {"text": concl.uncorrected_conclusion, "updated_by": str(concl.updated_by),
                       "updated_at": js(concl.updated_at)} if concl else None,
    }


def adjusted_balance(db: Session, e: Engagement) -> list[dict]:
    """Balance validée + ajustements corrigés par l'entité = balance ajustée (calculée, jamais enregistrée)."""
    b = balances(db, e)
    corrected = [ln for m in db.scalars(select(FaMisstatement).where(FaMisstatement.engagement_id == e.id,
                                                                     FaMisstatement.status == "corrected"))
                 for ln in misstatement_lines(db, m.id)]
    adj = {x.account_number: x for x in fa.adjust(b.cur, corrected)}
    orig = {x.account_number: x for x in b.cur}
    out = []
    for acc in sorted(adj):
        o, a = orig.get(acc), adj[acc]
        bn = o.closing_net if o else Decimal(0)
        out.append({"account": acc, "label": (o or a).account_label, "balance": js(bn), "adjustments": js(a.closing_net - bn),
                    "adjusted": js(a.closing_net)})
    return out


# ------------------------------------------------------------------ contrôles d'émission (miroir du trigger)
def fa_checks(db: Session, e: Engagement) -> list[dict]:
    if e.engagement_type not in FA_TYPES:
        return []

    def count(model, *cond) -> int:
        return len(list(db.scalars(select(model.id).where(model.engagement_id == e.id, *cond))))

    unrev = count(FaAccountReview, FaAccountReview.status != "reviewed")
    open_s = count(FaSample, FaSample.status != "concluded")
    open_c = count(FaConfirmation, FaConfirmation.status != "closed")
    prop = count(FaMisstatement, FaMisstatement.status == "proposed")
    unc = count(FaMisstatement, FaMisstatement.status == "uncorrected")
    concl = db.get(FaConclusion, e.id) is not None
    return [
        {"code": "FA_MATERIALITY", "label": "Seuils approuvés", "passed": approved_materiality(db, e) is not None,
         "detail": None},
        {"code": "FA_ACCOUNTS", "label": "Comptes revus", "passed": unrev == 0,
         "detail": f"{unrev} à revoir" if unrev else None},
        {"code": "FA_SAMPLES", "label": "Échantillons conclus", "passed": open_s == 0,
         "detail": f"{open_s} en cours" if open_s else None},
        {"code": "FA_CONFIRMATIONS", "label": "Circularisations closes", "passed": open_c == 0,
         "detail": f"{open_c} en cours" if open_c else None},
        {"code": "FA_MISSTATEMENTS", "label": "Décision prise sur chaque anomalie", "passed": prop == 0,
         "detail": f"{prop} sans décision" if prop else None},
        {"code": "FA_UNCORRECTED", "label": "Conclusion sur les anomalies non corrigées", "passed": unc == 0 or concl,
         "detail": None if unc == 0 or concl else f"{unc} anomalie(s) non corrigée(s)"},
    ]
