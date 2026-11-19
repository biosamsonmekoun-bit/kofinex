"""API — audit financier et comptable (lot 7) : seuils, cycles et revue des comptes, populations et échantillons,
tests, circularisations, anomalies et ajustements, synthèse, balance ajustée.

Les règles décisives (soldes conformes aux balances validées, sélection et projection par le moteur, séparation des
décisions, conditions d'émission, gel) sont aussi imposées par la base (migration 0008).
"""

from __future__ import annotations

import csv
import io
import secrets
import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.errors import Conflict, NotFound
from app.engines.audit import financial as fa
from app.engines.importing.files import FileRejected
from app.engines.importing.readers import extract
from app.models import (
    EvidenceItem,
    FaAccountReview,
    FaConclusion,
    FaConfirmation,
    FaCycleMapping,
    FaMateriality,
    FaMisstatement,
    FaMisstatementLine,
    FaPopulation,
    FaPopulationItem,
    FaSample,
    FaSampleItem,
    FiscalYear,
    LedgerLine,
    Procedure,
    Workpaper,
)
from app.services import financial_audit as fsvc
from app.services.audit import record_event
from app.services.engagements import AuditInvalid, EngagementContext, js, methodology_items, owned, people, row
from app.services.engagements import get_engagement_context as _ctx
from app.services.storage import get_storage

router = APIRouter(tags=["Audit financier"])
EVIDENCE_BUCKET = "audit-evidence"
Money = Decimal


def ctx_fa(ctx: EngagementContext = Depends(_ctx)) -> EngagementContext:
    fsvc.require_fa(ctx.engagement)
    return ctx


def _log(db, request, ctx: EngagementContext, action, entity_type, entity_id, details=None):
    record_event(
        db,
        user_id=ctx.user.id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        organization_id=ctx.engagement.organization_id,
        company_id=ctx.engagement.company_id,
        details={"engagement_id": str(ctx.engagement.id), **js(details or {})},
        request=request,
    )


def _ids(ctx: EngagementContext) -> dict:
    return {"organization_id": ctx.engagement.organization_id, "engagement_id": ctx.engagement.id}


def _check_links(db: Session, ctx: EngagementContext, workpaper_id: uuid.UUID | None, procedure_id: uuid.UUID | None = None):
    if workpaper_id:
        owned(db, ctx, Workpaper, workpaper_id, "Feuille de travail")
    if procedure_id:
        owned(db, ctx, Procedure, procedure_id, "Procédure")


B = "/engagements/{engagement_id}/fa"
Ctx = Annotated[EngagementContext, Depends(ctx_fa)]
Db = Annotated[Session, Depends(get_db)]


# ======================================================================== vue d'ensemble
@router.get(B, summary="Vue d'ensemble de l'audit financier")
def overview(ctx: Ctx, db: Db):
    ctx.require("read_dossier")
    e = ctx.engagement
    mat = fsvc.approved_materiality(db, e)

    def by_status(model):
        q = select(model.status, func.count()).where(model.engagement_id == e.id).group_by(model.status)
        return dict(db.execute(q).all())

    return {
        "materiality": row(mat, MAT_FIELDS) if mat else None,
        "accounts": by_status(FaAccountReview),
        "samples": by_status(FaSample),
        "confirmations": by_status(FaConfirmation),
        "misstatements": by_status(FaMisstatement),
        "checks": fsvc.fa_checks(db, e),
        "capabilities": ctx.caps,
    }


# ======================================================================== seuils
MAT_FIELDS = (
    "id",
    "version",
    "benchmark_label",
    "benchmark_source",
    "benchmark_line_code",
    "source_import_job_id",
    "benchmark_amount",
    "overall_pct",
    "overall_amount",
    "performance_pct",
    "performance_amount",
    "trivial_pct",
    "trivial_amount",
    "basis",
    "status",
    "created_by",
    "approved_by",
    "approved_at",
    "created_at",
)


class MaterialityIn(BaseModel):
    benchmark_label: str = Field(min_length=1, max_length=200)
    benchmark_source: Literal["statement_line", "manual"]
    benchmark_line_code: str | None = Field(default=None, max_length=40)
    benchmark_amount: Money | None = None  # saisi si « manual » ; calculé sinon
    overall_pct: Decimal = Field(gt=0, le=100)
    performance_pct: Decimal = Field(gt=0, le=100)
    trivial_pct: Decimal = Field(gt=0, le=100)
    basis: str = Field(min_length=10, max_length=4000)


def _materiality_values(db: Session, ctx: EngagementContext, p: MaterialityIn) -> dict:
    job = None
    if p.benchmark_source == "statement_line":
        if not p.benchmark_line_code:
            raise AuditInvalid("Choisissez la ligne des états servant de référence.")
        line = next((x for x in fsvc.statement_lines(db, ctx.engagement) if x["code"] == p.benchmark_line_code), None)
        if line is None or line["net"] is None:
            raise AuditInvalid("Ligne introuvable dans les états de l'exercice (référentiel publié et balance validée requis).")
        amount = abs(Decimal(line["net"]))
        job = fsvc.balances(db, ctx.engagement).cur_job
    else:
        if p.benchmark_amount is None:
            raise AuditInvalid("Saisissez le montant de référence.")
        amount = p.benchmark_amount
    try:
        m = fa.materiality(amount, p.overall_pct, p.performance_pct, p.trivial_pct)
    except ValueError as exc:
        raise AuditInvalid(str(exc)) from exc
    return dict(
        benchmark_label=p.benchmark_label.strip(),
        benchmark_source=p.benchmark_source,
        benchmark_line_code=p.benchmark_line_code if p.benchmark_source == "statement_line" else None,
        source_import_job_id=job,
        benchmark_amount=m.benchmark_amount,
        overall_pct=m.overall_pct,
        overall_amount=m.overall,
        performance_pct=m.performance_pct,
        performance_amount=m.performance,
        trivial_pct=m.trivial_pct,
        trivial_amount=m.trivial,
        basis=p.basis.strip(),
    )


@router.get(B + "/materiality")
def list_materiality(ctx: Ctx, db: Db):
    ctx.require("read_dossier")
    rows = list(
        db.scalars(
            select(FaMateriality).where(FaMateriality.engagement_id == ctx.engagement.id).order_by(FaMateriality.version.desc())
        )
    )
    ppl = people(db, [r.created_by for r in rows] + [r.approved_by for r in rows])
    params = [
        {"code": i.code, "label": i.label, "content": i.content} for i in methodology_items(db, ctx.engagement, "parameter")
    ]
    return {
        "versions": [
            {**row(r, MAT_FIELDS), "created_by_user": ppl.get(str(r.created_by)), "approved_by_user": ppl.get(str(r.approved_by))}
            for r in rows
        ],
        "methodology_parameters": params,
    }


@router.get(B + "/materiality/benchmarks", summary="Lignes des états de l'exercice, calculées depuis la balance validée")
def benchmarks(ctx: Ctx, db: Db):
    ctx.require("read_dossier")
    return fsvc.statement_lines(db, ctx.engagement)


@router.post(B + "/materiality", status_code=status.HTTP_201_CREATED)
def create_materiality(p: MaterialityIn, request: Request, ctx: Ctx, db: Db):
    ctx.require("plan")
    v = db.scalar(
        select(func.coalesce(func.max(FaMateriality.version), 0)).where(FaMateriality.engagement_id == ctx.engagement.id)
    )
    m = FaMateriality(id=uuid.uuid4(), **_ids(ctx), version=v + 1, created_by=ctx.user.id, **_materiality_values(db, ctx, p))
    db.add(m)
    db.flush()
    _log(
        db,
        request,
        ctx,
        "fa.materiality.create",
        "fa_materiality",
        m.id,
        {"version": m.version, "overall": m.overall_amount, "performance": m.performance_amount, "trivial": m.trivial_amount},
    )
    return row(m, MAT_FIELDS)


@router.patch(B + "/materiality/{mid}")
def update_materiality(mid: uuid.UUID, p: MaterialityIn, request: Request, ctx: Ctx, db: Db):
    ctx.require("plan")
    m = owned(db, ctx, FaMateriality, mid, "Seuils")
    if m.status != "draft":
        raise Conflict("Seuils approuvés : créez une nouvelle version.")
    for k, val in _materiality_values(db, ctx, p).items():
        setattr(m, k, val)
    db.flush()
    _log(db, request, ctx, "fa.materiality.update", "fa_materiality", m.id, {"version": m.version})
    return row(m, MAT_FIELDS)


@router.post(B + "/materiality/{mid}/approve")
def approve_materiality(mid: uuid.UUID, request: Request, ctx: Ctx, db: Db):
    ctx.require("approve_materiality")
    m = owned(db, ctx, FaMateriality, mid, "Seuils")
    if m.status != "draft":
        raise Conflict("Seule une version en brouillon peut être approuvée.")
    m.status, m.approved_by = "approved", ctx.user.id
    db.flush()
    db.refresh(m)
    _log(db, request, ctx, "fa.materiality.approve", "fa_materiality", m.id, {"version": m.version})
    return row(m, MAT_FIELDS)


@router.delete(B + "/materiality/{mid}", status_code=status.HTTP_204_NO_CONTENT)
def delete_materiality(mid: uuid.UUID, request: Request, ctx: Ctx, db: Db):
    ctx.require("plan")
    m = owned(db, ctx, FaMateriality, mid, "Seuils")
    db.delete(m)
    db.flush()
    _log(db, request, ctx, "fa.materiality.delete", "fa_materiality", mid)
    return Response(status_code=204)


# ======================================================================== cycles et revue des comptes
class CycleMappingIn(BaseModel):
    account_prefix: str = Field(pattern=r"^[0-9]{1,20}$")
    cycle_code: str = Field(min_length=1, max_length=40)


@router.get(B + "/cycles", summary="Cycles de la méthodologie et rattachement des comptes")
def get_cycles(ctx: Ctx, db: Db):
    ctx.require("read_dossier")
    maps = db.scalars(
        select(FaCycleMapping).where(FaCycleMapping.engagement_id == ctx.engagement.id).order_by(FaCycleMapping.account_prefix)
    )
    return {
        "cycles": [
            {"code": i.code, "label": i.label, "account_prefixes": (i.content or {}).get("account_prefixes")}
            for i in methodology_items(db, ctx.engagement, "cycle")
        ],
        "mappings": [{"account_prefix": m.account_prefix, "cycle_code": m.cycle_code} for m in maps],
    }


@router.put(B + "/cycles", summary="Remplacer le rattachement préfixes de comptes → cycles")
def put_cycles(payload: list[CycleMappingIn], request: Request, ctx: Ctx, db: Db):
    ctx.require("plan")
    codes = {i.code for i in methodology_items(db, ctx.engagement, "cycle")}
    unknown = sorted({p.cycle_code for p in payload} - codes)
    if unknown:
        raise AuditInvalid(f"Cycle(s) absent(s) de la méthodologie de la mission : {', '.join(unknown)}.")
    if len({p.account_prefix for p in payload}) != len(payload):
        raise AuditInvalid("Un même préfixe est rattaché deux fois.")
    db.execute(FaCycleMapping.__table__.delete().where(FaCycleMapping.engagement_id == ctx.engagement.id))
    for p in payload:
        db.add(FaCycleMapping(id=uuid.uuid4(), **_ids(ctx), account_prefix=p.account_prefix, cycle_code=p.cycle_code))
    db.flush()
    _log(db, request, ctx, "fa.cycles.update", "engagements", ctx.engagement.id, {"mappings": len(payload)})
    return get_cycles(ctx, db)


AR_FIELDS = (
    "id",
    "account_number",
    "account_label",
    "cycle_code",
    "balance_n",
    "balance_n1",
    "variation",
    "threshold_used",
    "requires_explanation",
    "explanation",
    "conclusion",
    "status",
    "workpaper_id",
    "reviewed_by",
    "reviewed_at",
)


@router.post(B + "/account-reviews/refresh", summary="Établir ou actualiser la revue des comptes depuis les balances validées")
def refresh_accounts(request: Request, ctx: Ctx, db: Db):
    ctx.require("edit_procedures")
    e = ctx.engagement
    b = fsvc.balances(db, e)
    mat = fsvc.approved_materiality(db, e)
    thr = mat.performance_amount if mat else None
    maps = [
        (m.account_prefix, m.cycle_code) for m in db.scalars(select(FaCycleMapping).where(FaCycleMapping.engagement_id == e.id))
    ]
    existing = {r.account_number: r for r in db.scalars(select(FaAccountReview).where(FaAccountReview.engagement_id == e.id))}
    created = updated = reset = 0
    for v in fa.account_variations(b.cur, b.prev, thr):
        r = existing.pop(v.account, None)
        values = dict(
            account_label=v.label,
            cycle_code=fa.cycle_for(v.account, maps),
            source_import_job_id=b.cur_job,
            previous_import_job_id=b.prev_job,
            balance_n=v.balance_n,
            balance_n1=v.balance_n1,
            threshold_used=thr,
        )
        if r is None:
            db.add(FaAccountReview(id=uuid.uuid4(), **_ids(ctx), account_number=v.account, **values))
            created += 1
            continue
        changed = (r.balance_n, r.balance_n1, r.source_import_job_id) != (v.balance_n, v.balance_n1, b.cur_job)
        for k, val in values.items():
            setattr(r, k, val)
        if changed and r.status == "reviewed":
            r.status = "to_review"  # solde modifié : nouvelle revue
            reset += 1
        updated += 1
    for r in existing.values():  # compte devenu nul dans les deux balances
        if r.status == "to_review" and not r.conclusion:
            db.delete(r)
    db.flush()
    _log(
        db,
        request,
        ctx,
        "fa.accounts.refresh",
        "engagements",
        e.id,
        {"created": created, "updated": updated, "reset": reset, "import_job_id": b.cur_job},
    )
    return {"created": created, "updated": updated, "reset": reset}


@router.get(B + "/account-reviews", summary="Revue des comptes et feuilles maîtresses par cycle")
def list_accounts(ctx: Ctx, db: Db):
    ctx.require("read_dossier")
    rows = list(
        db.scalars(
            select(FaAccountReview)
            .where(FaAccountReview.engagement_id == ctx.engagement.id)
            .order_by(FaAccountReview.account_number)
        )
    )
    cycles: dict[str, dict] = {}
    for r in rows:
        c = cycles.setdefault(
            r.cycle_code or "",
            {
                "cycle_code": r.cycle_code,
                "accounts": 0,
                "balance_n": Decimal(0),
                "balance_n1": Decimal(0),
                "to_review": 0,
                "to_explain": 0,
            },
        )
        c["accounts"] += 1
        c["balance_n"] += r.balance_n
        c["balance_n1"] += r.balance_n1 or 0
        c["to_review"] += r.status != "reviewed"
        c["to_explain"] += r.requires_explanation and not r.explanation
    return {
        "accounts": [row(r, AR_FIELDS) for r in rows],
        "cycles": js(list(cycles.values())),
        "has_previous": any(r.balance_n1 is not None for r in rows),
    }


class AccountReviewIn(BaseModel):
    explanation: str | None = Field(default=None, max_length=4000)
    conclusion: str | None = Field(default=None, max_length=4000)
    workpaper_id: uuid.UUID | None = None
    status: Literal["to_review", "reviewed"] | None = None


@router.patch(B + "/account-reviews/{rid}")
def update_account(rid: uuid.UUID, p: AccountReviewIn, request: Request, ctx: Ctx, db: Db):
    ctx.require("edit_procedures")
    r = owned(db, ctx, FaAccountReview, rid, "Compte")
    _check_links(db, ctx, p.workpaper_id)
    data = p.model_dump(exclude_unset=True)
    for k in ("explanation", "conclusion", "workpaper_id"):
        if k in data:
            setattr(r, k, (data[k].strip() or None) if isinstance(data[k], str) else data[k])
    if p.status == "reviewed":
        if r.requires_explanation and not r.explanation:
            raise AuditInvalid("Variation supérieure au seuil de planification : expliquez-la avant de conclure.")
        if not r.conclusion:
            raise AuditInvalid("Conclusion requise.")
        r.status, r.reviewed_by = "reviewed", ctx.user.id
    elif p.status == "to_review":
        r.status = "to_review"
    db.flush()
    db.refresh(r)
    _log(db, request, ctx, "fa.account.update", "fa_account_reviews", r.id, {"account": r.account_number, "status": r.status})
    return row(r, AR_FIELDS)


# ======================================================================== populations
POP_FIELDS = (
    "id",
    "name",
    "description",
    "source",
    "account_prefixes",
    "filters",
    "source_import_job_id",
    "source_evidence_id",
    "item_count",
    "total_amount",
    "absolute_total",
    "sha256",
    "created_by",
    "created_at",
)
ITEM_FIELDS = ("id", "line_no", "reference", "item_date", "label", "account_number", "amount", "ledger_line_id")


def _save_population(db: Session, ctx: EngagementContext, pop: FaPopulation, items: list[dict]) -> FaPopulation:
    pop.item_count = len(items)
    pop.total_amount = sum((i["amount"] for i in items), Decimal(0))
    pop.absolute_total = sum((abs(i["amount"]) for i in items), Decimal(0))
    pop.sha256 = fsvc.population_hash(items)
    db.add(pop)
    db.flush()
    db.execute(FaPopulationItem.__table__.insert(), [{**_ids(ctx), "population_id": pop.id, **i} for i in items])
    db.flush()
    return pop


class PopulationFromBalance(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    account_prefixes: list[str] = Field(min_length=1, max_length=50)
    exclude_zero: bool = True

    @field_validator("account_prefixes")
    @classmethod
    def _digits(cls, v: list[str]) -> list[str]:
        if any(not x.isdigit() for x in v):
            raise ValueError("Préfixes de comptes : chiffres uniquement.")
        return v


@router.post(
    B + "/populations/from-balance",
    status_code=status.HTTP_201_CREATED,
    summary="Population = comptes de la balance validée (soldes nets)",
)
def population_from_balance(p: PopulationFromBalance, request: Request, ctx: Ctx, db: Db):
    ctx.require("edit_procedures")
    b = fsvc.balances(db, ctx.engagement)
    entries = [
        x
        for x in b.cur
        if any(x.account_number.startswith(pr) for pr in p.account_prefixes) and (x.closing_net != 0 or not p.exclude_zero)
    ]
    if not entries:
        raise AuditInvalid("Aucun compte de la balance validée ne correspond à ces préfixes.")
    items = [
        {
            "line_no": n,
            "reference": x.account_number,
            "item_date": None,
            "label": x.account_label,
            "account_number": x.account_number,
            "amount": x.closing_net,
        }
        for n, x in enumerate(entries, start=1)
    ]
    pop = FaPopulation(
        id=uuid.uuid4(),
        **_ids(ctx),
        name=p.name,
        description=p.description,
        source="balance",
        account_prefixes=p.account_prefixes,
        source_import_job_id=b.cur_job,
        created_by=ctx.user.id,
    )
    _save_population(db, ctx, pop, items)
    _log(
        db,
        request,
        ctx,
        "fa.population.create",
        "fa_populations",
        pop.id,
        {"source": "balance", "items": pop.item_count, "sha256": pop.sha256},
    )
    return row(pop, POP_FIELDS)


class PopulationFromLedger(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    account_prefixes: list[str] = Field(default_factory=list, max_length=50)
    journals: list[str] = Field(default_factory=list, max_length=50)
    date_from: date | None = None
    date_to: date | None = None
    min_abs_amount: Money | None = Field(default=None, ge=0)
    side: Literal["all", "debit", "credit"] = "all"

    @field_validator("account_prefixes")
    @classmethod
    def _digits_l(cls, v: list[str]) -> list[str]:
        if any(not x.isdigit() for x in v):
            raise ValueError("Préfixes de comptes : chiffres uniquement.")
        return v


MAX_LEDGER_POPULATION = 200_000


@router.post(
    B + "/populations/from-ledger",
    status_code=status.HTTP_201_CREATED,
    summary="Population = lignes d'écritures du grand livre validé de l'exercice audité",
)
def population_from_ledger(p: PopulationFromLedger, request: Request, ctx: Ctx, db: Db):
    ctx.require("edit_procedures")
    fy = db.get(FiscalYear, ctx.engagement.fiscal_year_id) if ctx.engagement.fiscal_year_id else None
    if fy is None or fy.active_ledger_import_job_id is None:
        raise AuditInvalid("Aucun grand livre validé pour l'exercice audité : importez et validez le grand livre.")
    q = select(LedgerLine).where(LedgerLine.import_job_id == fy.active_ledger_import_job_id, LedgerLine.status == "valid")
    if p.account_prefixes:
        q = q.where(or_(*[LedgerLine.account_number.startswith(x) for x in p.account_prefixes]))
    if p.journals:
        q = q.where(LedgerLine.journal_code.in_(p.journals))
    if p.date_from:
        q = q.where(LedgerLine.entry_date >= p.date_from)
    if p.date_to:
        q = q.where(LedgerLine.entry_date <= p.date_to)
    if p.min_abs_amount is not None:
        q = q.where(LedgerLine.debit + LedgerLine.credit >= p.min_abs_amount)
    if p.side == "debit":
        q = q.where(LedgerLine.debit > 0)
    elif p.side == "credit":
        q = q.where(LedgerLine.credit > 0)
    n = db.scalar(select(func.count()).select_from(q.subquery()))
    if not n:
        raise AuditInvalid("Aucune ligne du grand livre ne correspond à ces critères.")
    if n > MAX_LEDGER_POPULATION:
        raise AuditInvalid(f"{n} lignes : restreignez la population (maximum {MAX_LEDGER_POPULATION}).")
    lines = db.scalars(q.order_by(LedgerLine.entry_date, LedgerLine.journal_code, LedgerLine.entry_number, LedgerLine.source_row))
    items = [
        {
            "line_no": k,
            "reference": f"{ln.journal_code or '—'}/{ln.entry_number or ln.document_ref or ln.source_row}/L{ln.source_row}"[:200],
            "item_date": ln.entry_date,
            "label": ln.label or ln.auxiliary_label,
            "account_number": ln.account_number,
            "amount": ln.debit - ln.credit,
            "ledger_line_id": ln.id,
        }
        for k, ln in enumerate(lines, start=1)
    ]
    filters = js(p.model_dump(exclude={"name", "description"}))
    pop = FaPopulation(
        id=uuid.uuid4(),
        **_ids(ctx),
        name=p.name,
        description=p.description,
        source="ledger",
        account_prefixes=p.account_prefixes,
        filters=filters,
        source_import_job_id=fy.active_ledger_import_job_id,
        created_by=ctx.user.id,
    )
    _save_population(db, ctx, pop, items)
    _log(
        db,
        request,
        ctx,
        "fa.population.create",
        "fa_populations",
        pop.id,
        {"source": "ledger", "items": pop.item_count, "sha256": pop.sha256, "filters": filters},
    )
    return row(pop, POP_FIELDS)


class PopulationFromFile(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    evidence_id: uuid.UUID
    sheet: int = Field(default=0, ge=0)
    header_row: int = Field(default=0, ge=0)
    columns: dict[Literal["reference", "date", "label", "account", "amount"], int | None]
    decimal_separator: Literal[",", "."] | None = None


def _read_evidence_rows(db: Session, ctx: EngagementContext, evidence_id: uuid.UUID, sheet: int) -> list[list[object]]:
    ev = owned(db, ctx, EvidenceItem, evidence_id, "Élément probant")
    if ev.kind != "file" or not ev.original_filename:
        raise AuditInvalid("Choisissez un fichier déposé (CSV ou XLSX).")
    ext = ev.original_filename.rsplit(".", 1)[-1].lower()
    if ext not in ("csv", "txt", "xlsx"):
        raise AuditInvalid("Population : fichiers CSV ou XLSX uniquement.")
    try:
        data = get_storage().download(EVIDENCE_BUCKET, ev.storage_path)
        ext_ = extract("csv" if ext in ("csv", "txt") else "xlsx", data)
    except FileRejected as exc:
        raise AuditInvalid(f"Fichier illisible : {exc}") from exc
    if sheet >= len(ext_.sheets):
        raise AuditInvalid("Feuille inexistante.")
    return ext_.sheets[sheet].rows


@router.post(B + "/populations/preview", summary="Aperçu des premières lignes d'un fichier probant")
def population_preview(p: PopulationFromFile, ctx: Ctx, db: Db):
    ctx.require("edit_procedures")
    rows = _read_evidence_rows(db, ctx, p.evidence_id, p.sheet)
    return {
        "rows": js([[c if isinstance(c, (str, int, Decimal)) or c is None else str(c) for c in r] for r in rows[:15]]),
        "total_rows": len(rows),
    }


@router.post(
    B + "/populations/from-file",
    status_code=status.HTTP_201_CREATED,
    summary="Population lue dans un fichier probant (grand livre, liste de factures…)",
)
def population_from_file(p: PopulationFromFile, request: Request, ctx: Ctx, db: Db):
    ctx.require("edit_procedures")
    rows = _read_evidence_rows(db, ctx, p.evidence_id, p.sheet)
    try:
        parsed = fa.parse_population(rows, p.header_row, dict(p.columns), p.decimal_separator)
    except ValueError as exc:
        raise AuditInvalid(str(exc)) from exc
    if not parsed.ok:
        raise AuditInvalid("Fichier rejeté : aucune population créée.", details={"issues": parsed.issues[:200]})
    items = [
        {
            "line_no": i.line_no,
            "reference": i.reference[:200],
            "item_date": i.item_date,
            "label": i.label,
            "account_number": i.account,
            "amount": i.amount,
        }
        for i in parsed.items
    ]
    pop = FaPopulation(
        id=uuid.uuid4(),
        **_ids(ctx),
        name=p.name,
        description=p.description,
        source="file",
        source_evidence_id=p.evidence_id,
        created_by=ctx.user.id,
    )
    _save_population(db, ctx, pop, items)
    _log(
        db,
        request,
        ctx,
        "fa.population.create",
        "fa_populations",
        pop.id,
        {"source": "file", "evidence_id": p.evidence_id, "items": pop.item_count, "sha256": pop.sha256},
    )
    return {**row(pop, POP_FIELDS), "issues": parsed.issues}


@router.get(B + "/populations")
def list_populations(ctx: Ctx, db: Db):
    ctx.require("read_dossier")
    pops = list(
        db.scalars(select(FaPopulation).where(FaPopulation.engagement_id == ctx.engagement.id).order_by(FaPopulation.created_at))
    )
    used = {pid for (pid,) in db.execute(select(FaSample.population_id).where(FaSample.engagement_id == ctx.engagement.id))}
    return [{**row(x, POP_FIELDS), "frozen": x.id in used} for x in pops]


@router.get(B + "/populations/{pid}/items")
def population_items(pid: uuid.UUID, ctx: Ctx, db: Db, offset: int = 0, limit: int = 200):
    ctx.require("read_dossier")
    owned(db, ctx, FaPopulation, pid, "Population")
    q = select(FaPopulationItem).where(FaPopulationItem.population_id == pid).order_by(FaPopulationItem.line_no)
    return [row(i, ITEM_FIELDS) for i in db.scalars(q.offset(max(offset, 0)).limit(min(max(limit, 1), 1000)))]


@router.delete(B + "/populations/{pid}", status_code=status.HTTP_204_NO_CONTENT)
def delete_population(pid: uuid.UUID, request: Request, ctx: Ctx, db: Db):
    ctx.require("edit_procedures")
    pop = owned(db, ctx, FaPopulation, pid, "Population")
    db.delete(pop)
    db.flush()
    _log(db, request, ctx, "fa.population.delete", "fa_populations", pid)
    return Response(status_code=204)


# ======================================================================== échantillons et tests
S_FIELDS = (
    "id",
    "population_id",
    "reference",
    "objective",
    "method",
    "requested_size",
    "size_basis",
    "seed",
    "parameters",
    "selected_count",
    "procedure_id",
    "workpaper_id",
    "status",
    "actual_misstatement",
    "projected_misstatement",
    "projection",
    "conclusion",
    "concluded_by",
    "concluded_at",
    "created_by",
    "created_at",
)
SI_FIELDS = (
    "id",
    "population_item_id",
    "selection_reason",
    "book_amount",
    "audited_amount",
    "misstatement",
    "result",
    "comment",
    "tested_by",
    "tested_at",
)


class SampleIn(BaseModel):
    population_id: uuid.UUID
    reference: str = Field(min_length=1, max_length=40)
    objective: str = Field(min_length=1, max_length=2000)
    method: Literal["random", "systematic", "mus", "key_items", "judgmental"]
    size: int | None = Field(default=None, ge=1, le=10000)
    size_basis: str = Field(min_length=10, max_length=2000)
    threshold: Money | None = None  # éléments clés
    item_ids: list[uuid.UUID] | None = None  # sélection raisonnée
    procedure_id: uuid.UUID | None = None
    workpaper_id: uuid.UUID | None = None


def _sample_out(db: Session, s: FaSample, with_items: bool = False) -> dict:
    out = row(s, S_FIELDS)
    pop = db.get(FaPopulation, s.population_id)
    out["population"] = (
        {"id": str(pop.id), "name": pop.name, "item_count": pop.item_count, "absolute_total": js(pop.absolute_total)}
        if pop
        else None
    )
    items = list(db.scalars(select(FaSampleItem).where(FaSampleItem.sample_id == s.id)))
    out["tested"] = sum(1 for i in items if i.result != "pending")
    out["exceptions"] = sum(1 for i in items if i.result == "exception")
    if with_items:
        pitems = (
            {
                p.id: p
                for p in db.scalars(
                    select(FaPopulationItem).where(FaPopulationItem.id.in_([i.population_item_id for i in items]))
                )
            }
            if items
            else {}
        )
        out["items"] = sorted(
            ({**row(i, SI_FIELDS), "item": row(pitems[i.population_item_id], ITEM_FIELDS)} for i in items),
            key=lambda x: x["item"]["line_no"],
        )
        out["preview"] = js(_projection(s, pop, items).__dict__) if pop else None
    return out


def _projection(s: FaSample, pop: FaPopulation, items: list[FaSampleItem]) -> fa.Projection:
    interval = Decimal(s.parameters["interval"]) if s.method == "mus" and s.parameters.get("interval") else None
    return fa.project(
        s.method,
        pop.absolute_total,
        [fa.TestedItem(i.book_amount, i.audited_amount if i.result != "pending" else None) for i in items],
        interval,
    )


@router.post(B + "/samples", status_code=status.HTTP_201_CREATED, summary="Tirer un échantillon (sélection reproductible)")
def create_sample(p: SampleIn, request: Request, ctx: Ctx, db: Db):
    ctx.require("edit_procedures")
    pop = owned(db, ctx, FaPopulation, p.population_id, "Population")
    _check_links(db, ctx, p.workpaper_id, p.procedure_id)
    pitems = list(
        db.scalars(select(FaPopulationItem).where(FaPopulationItem.population_id == pop.id).order_by(FaPopulationItem.line_no))
    )
    eng_items = [fa.PopItem(str(i.id), i.amount) for i in pitems]
    seed = secrets.randbelow(2**62) if p.method in ("random", "systematic", "mus") else None
    try:
        if p.method in ("random", "systematic", "mus"):
            if not p.size:
                raise ValueError("Taille de l'échantillon requise.")
            sel = {"random": fa.select_random, "systematic": fa.select_systematic, "mus": fa.select_mus}[p.method](
                eng_items, p.size, seed
            )
        elif p.method == "key_items":
            if p.threshold is None:
                raise ValueError("Seuil des éléments clés requis.")
            sel = fa.select_key_items(eng_items, p.threshold)
        else:
            ids = {str(i) for i in (p.item_ids or [])}
            known = {i.id for i in eng_items}
            if not ids or not ids <= known:
                raise ValueError("Sélection raisonnée : choisissez des éléments de la population.")
            sel = fa.Selection("judgmental", [i.id for i in eng_items if i.id in ids], {i: "judgment" for i in ids})
    except ValueError as exc:
        raise AuditInvalid(str(exc)) from exc
    amounts = {str(i.id): i.amount for i in pitems}
    s = FaSample(
        id=uuid.uuid4(),
        **_ids(ctx),
        population_id=pop.id,
        reference=p.reference.strip(),
        objective=p.objective.strip(),
        method=p.method,
        requested_size=p.size if p.method in ("random", "systematic", "mus") else None,
        size_basis=p.size_basis.strip(),
        seed=seed,
        parameters=js(sel.parameters),
        selected_count=len(sel.item_ids),
        procedure_id=p.procedure_id,
        workpaper_id=p.workpaper_id,
        created_by=ctx.user.id,
    )
    fsvc.sampling_on(db)
    try:
        db.add(s)
        db.flush()
        db.execute(
            FaSampleItem.__table__.insert(),
            [
                {
                    **_ids(ctx),
                    "sample_id": s.id,
                    "population_item_id": uuid.UUID(i),
                    "selection_reason": sel.reasons[i],
                    "book_amount": amounts[i],
                }
                for i in sel.item_ids
            ],
        )
        db.flush()
    finally:
        fsvc.sampling_off(db)
    _log(
        db,
        request,
        ctx,
        "fa.sample.create",
        "fa_samples",
        s.id,
        {"method": p.method, "seed": seed, "selected": len(sel.item_ids), "population_sha256": pop.sha256},
    )
    return _sample_out(db, s, with_items=True)


@router.get(B + "/samples")
def list_samples(ctx: Ctx, db: Db):
    ctx.require("read_dossier")
    return [
        _sample_out(db, s)
        for s in db.scalars(select(FaSample).where(FaSample.engagement_id == ctx.engagement.id).order_by(FaSample.reference))
    ]


@router.get(B + "/samples/{sid}")
def get_sample(sid: uuid.UUID, ctx: Ctx, db: Db):
    ctx.require("read_dossier")
    return _sample_out(db, owned(db, ctx, FaSample, sid, "Échantillon"), with_items=True)


class TestIn(BaseModel):
    result: Literal["pending", "no_exception", "exception"]
    audited_amount: Money | None = None
    comment: str | None = Field(default=None, max_length=4000)


@router.patch(B + "/samples/{sid}/items/{iid}", summary="Enregistrer le résultat du test d'un élément")
def test_item(sid: uuid.UUID, iid: uuid.UUID, p: TestIn, request: Request, ctx: Ctx, db: Db):
    ctx.require("edit_procedures")
    s = owned(db, ctx, FaSample, sid, "Échantillon")
    it = db.get(FaSampleItem, iid)
    if it is None or it.sample_id != s.id:
        raise NotFound("Élément introuvable")
    if p.result == "no_exception":
        it.audited_amount = it.book_amount if p.audited_amount is None else p.audited_amount
        if it.audited_amount != it.book_amount:
            raise AuditInvalid("« Sans anomalie » : le montant audité est égal au montant comptable.")
    elif p.result == "exception":
        if p.audited_amount is None or not (p.comment or "").strip():
            raise AuditInvalid("Anomalie : montant audité et description requis.")
        it.audited_amount = p.audited_amount
    it.result, it.comment = p.result, (p.comment or "").strip() or None
    it.tested_by = ctx.user.id if p.result != "pending" else None
    db.flush()
    db.refresh(it)
    _log(db, request, ctx, "fa.sample.test", "fa_sample_items", it.id, {"sample": s.reference, "result": it.result})
    return row(it, SI_FIELDS)


class ConcludeIn(BaseModel):
    conclusion: str = Field(min_length=3, max_length=4000)


@router.post(B + "/samples/{sid}/conclude", summary="Conclure : anomalie constatée et extrapolée calculées par le moteur")
def conclude_sample(sid: uuid.UUID, p: ConcludeIn, request: Request, ctx: Ctx, db: Db):
    ctx.require("edit_procedures")
    s = owned(db, ctx, FaSample, sid, "Échantillon")
    if s.status == "concluded":
        raise Conflict("Échantillon déjà conclu.")
    items = list(db.scalars(select(FaSampleItem).where(FaSampleItem.sample_id == s.id)))
    pending = sum(1 for i in items if i.result == "pending")
    if pending:
        raise AuditInvalid(f"{pending} élément(s) non testé(s).")
    pr = _projection(s, db.get(FaPopulation, s.population_id), items)
    s.status, s.conclusion, s.concluded_by = "concluded", p.conclusion.strip(), ctx.user.id
    s.actual_misstatement, s.projected_misstatement, s.projection = pr.actual, pr.projected, js(pr.__dict__)
    fsvc.sampling_on(db)
    try:
        db.flush()
    finally:
        fsvc.sampling_off(db)
    _log(
        db,
        request,
        ctx,
        "fa.sample.conclude",
        "fa_samples",
        s.id,
        {"actual": pr.actual, "projected": pr.projected, "method": pr.method},
    )
    return _sample_out(db, s, with_items=True)


@router.post(B + "/samples/{sid}/reopen")
def reopen_sample(sid: uuid.UUID, request: Request, ctx: Ctx, db: Db):
    ctx.require("plan")
    s = owned(db, ctx, FaSample, sid, "Échantillon")
    if s.status != "concluded":
        raise Conflict("Échantillon non conclu.")
    s.status = "testing"
    db.flush()
    _log(db, request, ctx, "fa.sample.reopen", "fa_samples", s.id)
    return _sample_out(db, s, with_items=True)


@router.delete(B + "/samples/{sid}", status_code=status.HTTP_204_NO_CONTENT)
def delete_sample(sid: uuid.UUID, request: Request, ctx: Ctx, db: Db):
    ctx.require("edit_procedures")
    s = owned(db, ctx, FaSample, sid, "Échantillon")
    fsvc.sampling_on(db)
    try:
        db.delete(s)
        db.flush()
    finally:
        fsvc.sampling_off(db)
    _log(db, request, ctx, "fa.sample.delete", "fa_samples", sid)
    return Response(status_code=204)


# ======================================================================== circularisations
C_FIELDS = (
    "id",
    "reference",
    "confirmation_type",
    "third_party",
    "contact",
    "account_number",
    "balance_date",
    "book_balance",
    "request_form",
    "status",
    "sent_on",
    "reminder_dates",
    "received_on",
    "confirmed_amount",
    "difference",
    "reconciliation",
    "alternative_procedures",
    "conclusion",
    "population_item_id",
    "workpaper_id",
    "created_by",
    "closed_by",
    "closed_at",
    "created_at",
)
CType = Literal["receivable", "payable", "bank", "legal", "other"]
CForm = Literal["positive", "negative", "blank"]


class ConfirmationIn(BaseModel):
    reference: str = Field(min_length=1, max_length=40)
    confirmation_type: CType
    third_party: str = Field(min_length=1, max_length=300)
    contact: str | None = Field(default=None, max_length=1000)
    account_number: str | None = Field(default=None, pattern=r"^[0-9]{1,20}$")
    balance_date: date
    book_balance: Money | None = None
    request_form: CForm = "positive"
    workpaper_id: uuid.UUID | None = None


@router.get(B + "/confirmations")
def list_confirmations(ctx: Ctx, db: Db):
    ctx.require("read_dossier")
    return [
        row(c, C_FIELDS)
        for c in db.scalars(
            select(FaConfirmation).where(FaConfirmation.engagement_id == ctx.engagement.id).order_by(FaConfirmation.reference)
        )
    ]


@router.post(B + "/confirmations", status_code=status.HTTP_201_CREATED)
def create_confirmation(p: ConfirmationIn, request: Request, ctx: Ctx, db: Db):
    ctx.require("edit_procedures")
    _check_links(db, ctx, p.workpaper_id)
    c = FaConfirmation(id=uuid.uuid4(), **_ids(ctx), created_by=ctx.user.id, **p.model_dump())
    db.add(c)
    db.flush()
    db.refresh(c)
    _log(db, request, ctx, "fa.confirmation.create", "fa_confirmations", c.id, {"reference": c.reference})
    return row(c, C_FIELDS)


class ConfirmationsFromPopulation(BaseModel):
    population_id: uuid.UUID
    item_ids: list[uuid.UUID] | None = None  # défaut : éléments sélectionnés d'un échantillon (sample_id) ou tous
    sample_id: uuid.UUID | None = None
    confirmation_type: CType
    balance_date: date
    request_form: CForm = "positive"
    reference_prefix: str = Field(default="C", min_length=1, max_length=10)


@router.post(
    B + "/confirmations/from-population",
    status_code=status.HTTP_201_CREATED,
    summary="Préparer une demande par élément (tiers = libellé, solde = montant)",
)
def confirmations_from_population(p: ConfirmationsFromPopulation, request: Request, ctx: Ctx, db: Db):
    ctx.require("edit_procedures")
    owned(db, ctx, FaPopulation, p.population_id, "Population")
    q = select(FaPopulationItem).where(FaPopulationItem.population_id == p.population_id)
    if p.sample_id:
        s = owned(db, ctx, FaSample, p.sample_id, "Échantillon")
        q = q.where(FaPopulationItem.id.in_(select(FaSampleItem.population_item_id).where(FaSampleItem.sample_id == s.id)))
    if p.item_ids:
        q = q.where(FaPopulationItem.id.in_(p.item_ids))
    items = list(db.scalars(q.order_by(FaPopulationItem.line_no)))
    if not items:
        raise AuditInvalid("Aucun élément à circulariser.")
    n0 = db.scalar(select(func.count()).select_from(FaConfirmation).where(FaConfirmation.engagement_id == ctx.engagement.id)) or 0
    out = []
    for k, it in enumerate(items, start=1):
        c = FaConfirmation(
            id=uuid.uuid4(),
            **_ids(ctx),
            reference=f"{p.reference_prefix}{n0 + k:03d}",
            confirmation_type=p.confirmation_type,
            third_party=(it.label or it.reference)[:300],
            account_number=it.account_number,
            balance_date=p.balance_date,
            book_balance=it.amount,
            request_form=p.request_form,
            population_item_id=it.id,
            created_by=ctx.user.id,
        )
        db.add(c)
        out.append(c)
    db.flush()
    _log(db, request, ctx, "fa.confirmation.bulk_create", "fa_populations", p.population_id, {"count": len(out)})
    return [row(c, C_FIELDS) for c in out]


class ConfirmationUpdate(BaseModel):
    third_party: str | None = Field(default=None, min_length=1, max_length=300)
    contact: str | None = Field(default=None, max_length=1000)
    book_balance: Money | None = None
    request_form: CForm | None = None
    status: Literal["prepared", "sent", "received", "no_response", "closed"] | None = None
    sent_on: date | None = None
    add_reminder: date | None = None
    received_on: date | None = None
    confirmed_amount: Money | None = None
    reconciliation: str | None = Field(default=None, max_length=4000)
    alternative_procedures: str | None = Field(default=None, max_length=4000)
    conclusion: str | None = Field(default=None, max_length=4000)
    workpaper_id: uuid.UUID | None = None


@router.patch(B + "/confirmations/{cid}")
def update_confirmation(cid: uuid.UUID, p: ConfirmationUpdate, request: Request, ctx: Ctx, db: Db):
    ctx.require("edit_procedures")
    c = owned(db, ctx, FaConfirmation, cid, "Circularisation")
    _check_links(db, ctx, p.workpaper_id)
    data = p.model_dump(exclude_unset=True)
    reminder = data.pop("add_reminder", None)
    for k, v in data.items():
        setattr(c, k, (v.strip() or None) if isinstance(v, str) else v)
    if reminder:
        if c.status != "sent":
            raise AuditInvalid("Relance : seulement pour une demande envoyée sans réponse.")
        c.reminder_dates = sorted({*c.reminder_dates, reminder})
    db.flush()
    db.refresh(c)
    _log(db, request, ctx, "fa.confirmation.update", "fa_confirmations", c.id, {"status": c.status, "fields": sorted(data)})
    return row(c, C_FIELDS)


@router.delete(B + "/confirmations/{cid}", status_code=status.HTTP_204_NO_CONTENT)
def delete_confirmation(cid: uuid.UUID, request: Request, ctx: Ctx, db: Db):
    ctx.require("edit_procedures")
    db.delete(owned(db, ctx, FaConfirmation, cid, "Circularisation"))
    db.flush()
    _log(db, request, ctx, "fa.confirmation.delete", "fa_confirmations", cid)
    return Response(status_code=204)


@router.get(B + "/confirmations.csv", summary="Liste des demandes (publipostage)")
def export_confirmations(request: Request, ctx: Ctx, db: Db):
    ctx.require("read_dossier")
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["reference", "type", "tiers", "contact", "compte", "date_arrete", "solde_comptable", "forme", "statut"])
    for c in db.scalars(
        select(FaConfirmation).where(FaConfirmation.engagement_id == ctx.engagement.id).order_by(FaConfirmation.reference)
    ):
        w.writerow(
            [
                c.reference,
                c.confirmation_type,
                c.third_party,
                c.contact or "",
                c.account_number or "",
                c.balance_date.isoformat(),
                js(c.book_balance) if c.book_balance is not None else "",
                c.request_form,
                c.status,
            ]
        )
    _log(db, request, ctx, "fa.confirmation.export", "engagements", ctx.engagement.id)
    return Response(
        content=("﻿" + buf.getvalue()).encode("utf-8"),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=circularisations-{ctx.engagement.reference}.csv"},
    )


# ======================================================================== anomalies et ajustements
MS_FIELDS = (
    "id",
    "reference",
    "source_type",
    "source_id",
    "kind",
    "description",
    "status",
    "entity_response",
    "withdrawn_reason",
    "decided_by",
    "decided_at",
    "created_by",
    "created_at",
)


class LineIn(BaseModel):
    account_number: str = Field(pattern=r"^[0-9]{1,20}$")
    label: str | None = Field(default=None, max_length=300)
    debit: Money = Decimal(0)
    credit: Money = Decimal(0)


class MisstatementIn(BaseModel):
    reference: str = Field(min_length=1, max_length=40)
    source_type: Literal["sample", "confirmation", "account_review", "analytical", "other"]
    source_id: uuid.UUID | None = None
    kind: Literal["factual", "judgmental", "projected"]
    description: str = Field(min_length=3, max_length=4000)
    lines: list[LineIn] = Field(min_length=2, max_length=50)


def _ms_out(db: Session, m: FaMisstatement) -> dict:
    lines = db.scalars(select(FaMisstatementLine).where(FaMisstatementLine.misstatement_id == m.id))
    return {**row(m, MS_FIELDS), "lines": [row(ln, ("id", "account_number", "label", "debit", "credit")) for ln in lines]}


def _set_lines(db: Session, ctx: EngagementContext, m: FaMisstatement, lines: list[LineIn]) -> None:
    adj = [fa.AdjLine(x.account_number, x.label, x.debit, x.credit) for x in lines]
    try:
        fa.check_balanced(adj)
    except ValueError as exc:
        raise AuditInvalid(str(exc)) from exc
    db.execute(FaMisstatementLine.__table__.delete().where(FaMisstatementLine.misstatement_id == m.id))
    for x in lines:
        db.add(FaMisstatementLine(id=uuid.uuid4(), **_ids(ctx), misstatement_id=m.id, **x.model_dump()))


@router.get(B + "/misstatements")
def list_misstatements(ctx: Ctx, db: Db):
    ctx.require("read_dossier")
    return [
        _ms_out(db, m)
        for m in db.scalars(
            select(FaMisstatement).where(FaMisstatement.engagement_id == ctx.engagement.id).order_by(FaMisstatement.reference)
        )
    ]


@router.post(B + "/misstatements", status_code=status.HTTP_201_CREATED)
def create_misstatement(p: MisstatementIn, request: Request, ctx: Ctx, db: Db):
    ctx.require("edit_procedures")
    m = FaMisstatement(id=uuid.uuid4(), **_ids(ctx), created_by=ctx.user.id, **p.model_dump(exclude={"lines"}))
    db.add(m)
    db.flush()
    _set_lines(db, ctx, m, p.lines)
    db.flush()
    _log(db, request, ctx, "fa.misstatement.create", "fa_misstatements", m.id, {"reference": m.reference, "kind": m.kind})
    return _ms_out(db, m)


@router.put(B + "/misstatements/{msid}")
def update_misstatement(msid: uuid.UUID, p: MisstatementIn, request: Request, ctx: Ctx, db: Db):
    ctx.require("edit_procedures")
    m = owned(db, ctx, FaMisstatement, msid, "Anomalie")
    if m.status != "proposed":
        raise Conflict("Anomalie décidée : remettez-la au statut « proposée » pour la modifier.")
    for k, v in p.model_dump(exclude={"lines"}).items():
        setattr(m, k, v)
    _set_lines(db, ctx, m, p.lines)
    db.flush()
    _log(db, request, ctx, "fa.misstatement.update", "fa_misstatements", m.id, {"reference": m.reference})
    return _ms_out(db, m)


class DecisionIn(BaseModel):
    status: Literal["proposed", "corrected", "uncorrected", "withdrawn"]
    entity_response: str | None = Field(default=None, max_length=4000)
    withdrawn_reason: str | None = Field(default=None, max_length=4000)


@router.post(B + "/misstatements/{msid}/decision", summary="Correction par l'entité, maintien non corrigé ou retrait")
def decide_misstatement(msid: uuid.UUID, p: DecisionIn, request: Request, ctx: Ctx, db: Db):
    ctx.require("decide_misstatements")
    m = owned(db, ctx, FaMisstatement, msid, "Anomalie")
    if p.status in ("corrected", "uncorrected") and not (p.entity_response or "").strip():
        raise AuditInvalid("Réponse de l'entité requise.")
    if p.status == "withdrawn" and not (p.withdrawn_reason or "").strip():
        raise AuditInvalid("Motif du retrait requis.")
    m.status = p.status
    if p.entity_response is not None:
        m.entity_response = p.entity_response.strip() or None
    if p.withdrawn_reason is not None:
        m.withdrawn_reason = p.withdrawn_reason.strip() or None
    db.flush()
    db.refresh(m)
    _log(db, request, ctx, "fa.misstatement.decision", "fa_misstatements", m.id, {"status": m.status})
    return _ms_out(db, m)


@router.delete(B + "/misstatements/{msid}", status_code=status.HTTP_204_NO_CONTENT)
def delete_misstatement(msid: uuid.UUID, request: Request, ctx: Ctx, db: Db):
    ctx.require("edit_procedures")
    db.delete(owned(db, ctx, FaMisstatement, msid, "Anomalie"))
    db.flush()
    _log(db, request, ctx, "fa.misstatement.delete", "fa_misstatements", msid)
    return Response(status_code=204)


@router.get(B + "/summary", summary="Synthèse des anomalies et effets sur les états")
def misstatement_summary(ctx: Ctx, db: Db):
    ctx.require("read_dossier")
    return fsvc.summary(db, ctx.engagement)


class ConclusionIn(BaseModel):
    text: str = Field(min_length=10, max_length=8000)


@router.put(B + "/conclusion", summary="Conclusion de l'auditeur sur les anomalies non corrigées")
def put_conclusion(p: ConclusionIn, request: Request, ctx: Ctx, db: Db):
    ctx.require("conclude_misstatements")
    c = db.get(FaConclusion, ctx.engagement.id)
    if c is None:
        c = FaConclusion(
            engagement_id=ctx.engagement.id,
            organization_id=ctx.engagement.organization_id,
            uncorrected_conclusion=p.text.strip(),
            updated_by=ctx.user.id,
        )
        db.add(c)
    else:
        c.uncorrected_conclusion, c.updated_by = p.text.strip(), ctx.user.id
    db.flush()
    _log(db, request, ctx, "fa.conclusion.update", "engagements", ctx.engagement.id)
    return fsvc.summary(db, ctx.engagement)


@router.get(B + "/adjusted-balance", summary="Balance ajustée (balance validée + ajustements corrigés), calculée")
def adjusted(ctx: Ctx, db: Db, fmt: Literal["json", "csv"] = "json"):
    ctx.require("read_dossier")
    rows = fsvc.adjusted_balance(db, ctx.engagement)
    if fmt == "json":
        return rows
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["compte", "libelle", "solde_balance", "ajustements", "solde_ajuste"])
    for r in rows:
        w.writerow([r["account"], r["label"] or "", r["balance"], r["adjustments"], r["adjusted"]])
    return Response(
        content=("﻿" + buf.getvalue()).encode("utf-8"),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=balance-ajustee-{ctx.engagement.reference}.csv"},
    )
