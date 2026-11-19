"""Comptabilité native — paramétrage : paramètres de l'entreprise, plan comptable de l'entreprise (rattaché au
référentiel publié), tiers, journaux. Les contrôles d'intégrité sont en base (migration 0014) ; ce service prépare
les données, vérifie les références et produit des messages explicites."""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session

from app.core.errors import AppError, Conflict, NotFound
from app.models import (
    AccountingSettings,
    ChartAccount,
    Company,
    CompanyAccount,
    FiscalYear,
    FrameworkVersion,
    Journal,
    JournalEntry,
    JournalEntryLine,
    ThirdParty,
)

THIRD_PARTY_KINDS = ("customer", "supplier", "employee", "tax_authority", "social_body", "other")
JOURNAL_TYPES = ("purchases", "sales", "bank", "cash", "general", "payroll", "fixed_assets", "inventory", "opening")


class AccountingInvalid(AppError):
    status_code = 422
    code = "accounting_invalid"


# ------------------------------------------------------------------ paramètres
def settings(db: Session, company_id: uuid.UUID) -> dict:
    s = db.get(AccountingSettings, company_id)
    return {
        "review_required": bool(s and s.review_required),
        "segregation_required": True if s is None else s.segregation_required,
        "updated_at": s.updated_at if s else None,
    }


def update_settings(
    db: Session, company: Company, user_id: uuid.UUID, *, review_required: bool, segregation_required: bool
) -> dict:
    s = db.get(AccountingSettings, company.id)
    if s is None:
        s = AccountingSettings(company_id=company.id, organization_id=company.organization_id)
        db.add(s)
    s.review_required, s.segregation_required, s.updated_by = review_required, segregation_required, user_id
    s.updated_at = func.now()
    db.flush()
    return settings(db, company.id)


# ------------------------------------------------------------------ plan comptable de l'entreprise
def framework_version(db: Session, company_id: uuid.UUID, on: date | None = None) -> uuid.UUID:
    """Version publiée applicable : à la date donnée, sinon à la fin du dernier exercice de l'entreprise, sinon ce jour."""
    if on is None:
        on = db.scalar(select(func.max(FiscalYear.end_date)).where(FiscalYear.company_id == company_id)) or date.today()
    vid = db.execute(text("SELECT public.applicable_framework_version(:c, :d)"), {"c": company_id, "d": on}).scalar()
    if vid is None:
        raise AccountingInvalid(
            "Aucune version publiée du référentiel de l'entreprise n'est applicable : "
            "le plan comptable ne peut pas être rattaché."
        )
    return vid


def chart_parent(db: Session, version_id: uuid.UUID, account_number: str) -> ChartAccount | None:
    """Compte du référentiel le plus précis dont le numéro est un préfixe du compte de l'entreprise."""
    return db.scalars(
        select(ChartAccount)
        .where(
            ChartAccount.framework_version_id == version_id,
            text(":n LIKE chart_of_accounts.account_number || '%'").bindparams(n=account_number),
        )
        .order_by(func.length(ChartAccount.account_number).desc())
        .limit(1)
    ).first()


def account_out(a: CompanyAccount) -> dict:
    return {
        k: getattr(a, k)
        for k in (
            "id",
            "account_number",
            "label",
            "chart_account_number",
            "framework_version_id",
            "nature",
            "requires_third_party",
            "third_party_kind",
            "lettering_enabled",
            "is_active",
            "created_at",
        )
    }


def list_accounts(
    db: Session, company_id: uuid.UUID, q: str | None = None, active: bool | None = None, limit: int = 500, offset: int = 0
) -> dict:
    stmt = select(CompanyAccount).where(CompanyAccount.company_id == company_id)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(CompanyAccount.account_number.like(f"{q.strip()}%"), CompanyAccount.label.ilike(like)))
    if active is not None:
        stmt = stmt.where(CompanyAccount.is_active.is_(active))
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(stmt.order_by(CompanyAccount.account_number).limit(limit).offset(offset)).all()
    used = set(
        db.scalars(
            select(JournalEntryLine.account_number)
            .where(
                JournalEntryLine.company_id == company_id, JournalEntryLine.account_number.in_([r.account_number for r in rows])
            )
            .distinct()
        )
    )
    return {"total": total, "items": [{**account_out(r), "used": r.account_number in used} for r in rows]}


def create_account(
    db: Session,
    company: Company,
    user_id: uuid.UUID,
    *,
    account_number: str,
    label: str,
    requires_third_party: bool = False,
    third_party_kind: str | None = None,
    lettering_enabled: bool = False,
) -> CompanyAccount:
    vid = framework_version(db, company.id)
    parent = chart_parent(db, vid, account_number)
    if parent is None:
        raise AccountingInvalid(f"Le compte {account_number} ne relève d'aucun compte du plan du référentiel publié.")
    if third_party_kind and third_party_kind not in THIRD_PARTY_KINDS:
        raise AccountingInvalid("Type de tiers inconnu.")
    a = CompanyAccount(
        id=uuid.uuid4(),
        organization_id=company.organization_id,
        company_id=company.id,
        account_number=account_number,
        label=label.strip(),
        framework_version_id=vid,
        chart_account_number=parent.account_number,
        requires_third_party=requires_third_party or bool(third_party_kind),
        third_party_kind=third_party_kind,
        lettering_enabled=lettering_enabled,
        created_by=user_id,
    )
    db.add(a)
    db.flush()
    db.refresh(a)
    return a


def import_chart(db: Session, company: Company, user_id: uuid.UUID, classes: list[int] | None = None) -> dict:
    """Ouvre, dans le plan de l'entreprise, les comptes du référentiel publié qui n'ont pas de sous-compte (même numéro,
    même intitulé). Les comptes déjà ouverts sont conservés tels quels ; aucun compte n'est déclaré collectif d'office."""
    vid = framework_version(db, company.id)
    chart = db.scalars(select(ChartAccount).where(ChartAccount.framework_version_id == vid)).all()
    ordered = sorted(chart, key=lambda c: c.account_number)  # un sous-compte suit immédiatement son compte
    leaves = [
        c
        for i, c in enumerate(ordered)
        if i + 1 == len(ordered) or not ordered[i + 1].account_number.startswith(c.account_number)
    ]
    if classes:
        leaves = [c for c in leaves if c.account_class in classes]
    existing = set(db.scalars(select(CompanyAccount.account_number).where(CompanyAccount.company_id == company.id)))
    created = 0
    for c in sorted(leaves, key=lambda x: x.account_number):
        if c.account_number in existing or len(c.account_number) < 2:
            continue
        db.add(
            CompanyAccount(
                id=uuid.uuid4(),
                organization_id=company.organization_id,
                company_id=company.id,
                account_number=c.account_number,
                label=c.label,
                framework_version_id=vid,
                chart_account_number=c.account_number,
                created_by=user_id,
            )
        )
        created += 1
    db.flush()
    v = db.get(FrameworkVersion, vid)
    return {"created": created, "already_open": len(existing), "framework_version": v.version_label if v else None}


def update_account(db: Session, company_id: uuid.UUID, account_id: uuid.UUID, changes: dict) -> CompanyAccount:
    a = db.get(CompanyAccount, account_id)
    if a is None or a.company_id != company_id:
        raise NotFound("Compte introuvable")
    if changes.get("third_party_kind") not in (None, *THIRD_PARTY_KINDS):
        raise AccountingInvalid("Type de tiers inconnu.")
    for k in ("label", "is_active", "requires_third_party", "third_party_kind", "lettering_enabled"):
        if k in changes:
            setattr(a, k, changes[k])
    if a.third_party_kind:
        a.requires_third_party = True
    db.flush()
    db.refresh(a)
    return a


def delete_account(db: Session, company_id: uuid.UUID, account_id: uuid.UUID) -> None:
    a = db.get(CompanyAccount, account_id)
    if a is None or a.company_id != company_id:
        raise NotFound("Compte introuvable")
    if db.scalar(
        select(func.count()).where(JournalEntryLine.company_id == company_id, JournalEntryLine.account_number == a.account_number)
    ):
        raise Conflict(f"Le compte {a.account_number} est mouvementé : désactivez-le plutôt que de le supprimer.")
    db.delete(a)
    db.flush()


# ------------------------------------------------------------------ tiers
TP_FIELDS = (
    "code",
    "name",
    "kind",
    "collective_account_number",
    "tax_id",
    "registration_number",
    "address",
    "city",
    "country_code",
    "email",
    "phone",
    "is_active",
)


def tp_out(t: ThirdParty) -> dict:
    return {"id": t.id, **{k: getattr(t, k) for k in TP_FIELDS}, "created_at": t.created_at}


def list_third_parties(
    db: Session,
    company_id: uuid.UUID,
    q: str | None = None,
    kind: str | None = None,
    active: bool | None = None,
    limit: int = 200,
    offset: int = 0,
) -> dict:
    stmt = select(ThirdParty).where(ThirdParty.company_id == company_id)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(ThirdParty.code.ilike(like), ThirdParty.name.ilike(like), ThirdParty.tax_id.ilike(like)))
    if kind:
        stmt = stmt.where(ThirdParty.kind == kind)
    if active is not None:
        stmt = stmt.where(ThirdParty.is_active.is_(active))
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(stmt.order_by(ThirdParty.code).limit(limit).offset(offset)).all()
    return {"total": total, "items": [tp_out(t) for t in rows]}


def save_third_party(db: Session, company: Company, user_id: uuid.UUID, data: dict, tp_id: uuid.UUID | None = None) -> ThirdParty:
    if data.get("kind") is not None and data["kind"] not in THIRD_PARTY_KINDS:
        raise AccountingInvalid("Type de tiers inconnu.")
    if tp_id is None:
        t = ThirdParty(id=uuid.uuid4(), organization_id=company.organization_id, company_id=company.id, created_by=user_id)
        db.add(t)
    else:
        t = db.get(ThirdParty, tp_id)
        if t is None or t.company_id != company.id:
            raise NotFound("Tiers introuvable")
    for k in TP_FIELDS:
        if k in data:
            setattr(t, k, data[k])
    db.flush()
    db.refresh(t)
    return t


# ------------------------------------------------------------------ journaux
J_FIELDS = ("code", "label", "journal_type", "number_prefix", "counterpart_account_number", "allowed_users", "is_active")


def journal_out(j: Journal, counts: dict | None = None) -> dict:
    return {
        "id": j.id,
        **{k: getattr(j, k) for k in J_FIELDS},
        "entries": (counts or {}).get(j.id, 0),
        "created_at": j.created_at,
    }


def list_journals(db: Session, company_id: uuid.UUID, active: bool | None = None) -> list[dict]:
    stmt = select(Journal).where(Journal.company_id == company_id)
    if active is not None:
        stmt = stmt.where(Journal.is_active.is_(active))
    rows = db.scalars(stmt.order_by(Journal.code)).all()
    counts = dict(
        db.execute(
            select(JournalEntry.journal_id, func.count())
            .where(JournalEntry.company_id == company_id)
            .group_by(JournalEntry.journal_id)
        ).all()
    )
    return [journal_out(j, counts) for j in rows]


def save_journal(db: Session, company: Company, user_id: uuid.UUID, data: dict, journal_id: uuid.UUID | None = None) -> Journal:
    if data.get("journal_type") is not None and data["journal_type"] not in JOURNAL_TYPES:
        raise AccountingInvalid("Type de journal inconnu.")
    if journal_id is None:
        data.setdefault("number_prefix", f"{data.get('code', '')}-")
        j = Journal(id=uuid.uuid4(), organization_id=company.organization_id, company_id=company.id, created_by=user_id)
        db.add(j)
    else:
        j = db.get(Journal, journal_id)
        if j is None or j.company_id != company.id:
            raise NotFound("Journal introuvable")
    for k in J_FIELDS:
        if k in data:
            setattr(j, k, data[k])
    if j.journal_type in ("bank", "cash") and j.counterpart_account_number is None and journal_id is None:
        raise AccountingInvalid("Journal de banque ou de caisse : indiquez son compte de trésorerie.")
    db.flush()
    db.refresh(j)
    return j


def delete_journal(db: Session, company_id: uuid.UUID, journal_id: uuid.UUID) -> None:
    j = db.get(Journal, journal_id)
    if j is None or j.company_id != company_id:
        raise NotFound("Journal introuvable")
    if db.scalar(select(func.count()).where(JournalEntry.journal_id == j.id)):
        raise Conflict(f"Le journal {j.code} contient des écritures : désactivez-le plutôt que de le supprimer.")
    db.delete(j)
    db.flush()
