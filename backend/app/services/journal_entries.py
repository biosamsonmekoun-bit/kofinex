"""Comptabilité native — écritures : saisie en brouillon, lignes, circuit (soumission, revue, validation, rejet,
reprise), extourne et correction, pièces justificatives, historique.

Les règles sont imposées par la base (migration 0014) : équilibre, comptes ouverts et actifs, tiers des comptes
collectifs, séparation préparateur / validateur, numérotation sans trou à la validation, immutabilité des écritures
validées. Le service contrôle d'abord avec le moteur (`engines/accounting/entries.py`) pour renvoyer tous les écarts
d'un coup, verrouille la ligne avant chaque changement de statut et laisse la base trancher."""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import NotFound
from app.engines.accounting import entries as eng
from app.engines.importing.files import FileRejected, validate_upload
from app.models import (
    CompanyAccount,
    FinancialDocument,
    FiscalYear,
    Journal,
    JournalEntry,
    JournalEntryAttachment,
    JournalEntryEvent,
    JournalEntryLine,
    ThirdParty,
)
from app.services.accounting_setup import AccountingInvalid
from app.services.engagements import people
from app.services.storage import DOCUMENTS_BUCKET, get_storage

STATUSES = ("draft", "submitted", "under_review", "validated", "rejected", "reversed")
POSTED = ("validated", "reversed")
# action -> (statuts de départ, statut d'arrivée)
TRANSITIONS = {
    "submit": (("draft",), "submitted"),
    "withdraw": (("submitted",), "draft"),
    "start_review": (("submitted",), "under_review"),
    "validate": (("submitted", "under_review"), "validated"),
    "reject": (("submitted", "under_review"), "rejected"),
    "reopen": (("rejected",), "draft"),
}


# ------------------------------------------------------------------ lecture
def get_entry(db: Session, company_id: uuid.UUID, entry_id: uuid.UUID, lock: bool = False) -> JournalEntry:
    stmt = select(JournalEntry).where(JournalEntry.id == entry_id)
    if lock:
        stmt = stmt.with_for_update()
    e = db.scalars(stmt).first()
    if e is None or e.company_id != company_id:
        raise NotFound("Écriture introuvable")
    return e


def _lines(db: Session, entry_id: uuid.UUID) -> list[JournalEntryLine]:
    return list(
        db.scalars(select(JournalEntryLine).where(JournalEntryLine.entry_id == entry_id).order_by(JournalEntryLine.line_no))
    )


def check(db: Session, company_id: uuid.UUID, lines: list[JournalEntryLine]) -> eng.Check:
    nums = {ln.account_number for ln in lines}
    accs = db.scalars(
        select(CompanyAccount).where(CompanyAccount.company_id == company_id, CompanyAccount.account_number.in_(nums))
    ).all()
    tp_ids = {ln.third_party_id for ln in lines if ln.third_party_id}
    tps = db.scalars(select(ThirdParty).where(ThirdParty.id.in_(tp_ids))).all() if tp_ids else []
    return eng.check_entry(
        [eng.Line(ln.account_number, ln.debit, ln.credit, str(ln.third_party_id) if ln.third_party_id else None) for ln in lines],
        {a.account_number: eng.AccountInfo(a.is_active, a.requires_third_party, a.third_party_kind) for a in accs},
        {str(t.id): t.kind for t in tps},
    )


def entry_out(e: JournalEntry, journal: Journal | None = None) -> dict:
    return {
        "id": e.id,
        "fiscal_year_id": e.fiscal_year_id,
        "journal_id": e.journal_id,
        "journal_code": journal.code if journal else None,
        "entry_date": e.entry_date,
        "piece_ref": e.piece_ref,
        "piece_date": e.piece_date,
        "label": e.label,
        "third_party_id": e.third_party_id,
        "origin": e.origin,
        "source_type": e.source_type,
        "source_id": e.source_id,
        "reverses_entry_id": e.reverses_entry_id,
        "corrects_entry_id": e.corrects_entry_id,
        "reversed_by_entry_id": e.reversed_by_entry_id,
        "status": e.status,
        "number": e.number,
        "total_debit": e.total_debit,
        "total_credit": e.total_credit,
        "line_count": e.line_count,
        "created_by": e.created_by,
        "submitted_at": e.submitted_at,
        "validated_at": e.validated_at,
        "rejection_reason": e.rejection_reason,
        "created_at": e.created_at,
        "updated_at": e.updated_at,
    }


def list_entries(
    db: Session,
    company_id: uuid.UUID,
    *,
    fiscal_year_id: uuid.UUID | None = None,
    status: list[str] | None = None,
    journal_id: uuid.UUID | None = None,
    origin: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    stmt = select(JournalEntry).where(JournalEntry.company_id == company_id)
    if fiscal_year_id:
        stmt = stmt.where(JournalEntry.fiscal_year_id == fiscal_year_id)
    if status:
        stmt = stmt.where(JournalEntry.status.in_(status))
    if journal_id:
        stmt = stmt.where(JournalEntry.journal_id == journal_id)
    if origin:
        stmt = stmt.where(JournalEntry.origin == origin)
    if date_from:
        stmt = stmt.where(JournalEntry.entry_date >= date_from)
    if date_to:
        stmt = stmt.where(JournalEntry.entry_date <= date_to)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(JournalEntry.label.ilike(like), JournalEntry.piece_ref.ilike(like), JournalEntry.number.ilike(like))
        )
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(
        stmt.order_by(JournalEntry.entry_date.desc(), JournalEntry.created_at.desc()).limit(limit).offset(offset)
    ).all()
    journals = {j.id: j for j in db.scalars(select(Journal).where(Journal.company_id == company_id))}
    ppl = people(db, [r.created_by for r in rows])
    return {
        "total": total,
        "items": [{**entry_out(r, journals.get(r.journal_id)), "author": ppl.get(str(r.created_by))} for r in rows],
    }


def detail(
    db: Session,
    company_id: uuid.UUID,
    entry_id: uuid.UUID,
    user_id: uuid.UUID | None = None,
    can_write: bool = False,
    can_validate: bool = False,
) -> dict:
    e = get_entry(db, company_id, entry_id)
    j = db.get(Journal, e.journal_id)
    lines = _lines(db, e.id)
    accs = {
        a.account_number: a
        for a in db.scalars(
            select(CompanyAccount).where(
                CompanyAccount.company_id == company_id, CompanyAccount.account_number.in_({ln.account_number for ln in lines})
            )
        )
    }
    tp_ids = {ln.third_party_id for ln in lines if ln.third_party_id} | ({e.third_party_id} if e.third_party_id else set())
    tps = {t.id: t for t in db.scalars(select(ThirdParty).where(ThirdParty.id.in_(tp_ids)))} if tp_ids else {}
    events = db.scalars(
        select(JournalEntryEvent).where(JournalEntryEvent.entry_id == e.id).order_by(JournalEntryEvent.created_at)
    ).all()
    atts = db.execute(
        select(JournalEntryAttachment, FinancialDocument)
        .join(FinancialDocument, FinancialDocument.id == JournalEntryAttachment.document_id)
        .where(JournalEntryAttachment.entry_id == e.id)
    ).all()
    ppl = people(db, [e.created_by, e.submitted_by, e.reviewed_by, e.validated_by, e.rejected_by, *[ev.actor for ev in events]])
    chk = check(db, company_id, lines) if e.status in ("draft", "rejected") else None
    related = {
        x.id: x
        for x in db.scalars(
            select(JournalEntry).where(
                JournalEntry.id.in_([i for i in (e.reverses_entry_id, e.corrects_entry_id, e.reversed_by_entry_id) if i])
            )
        )
    }

    from app.services.accounting_setup import settings as acc_settings

    st = acc_settings(db, company_id)
    is_author = user_id is not None and user_id == e.created_by
    sep_block = st["segregation_required"] and user_id in (e.created_by, e.submitted_by)
    actions = {
        "edit": can_write and e.status == "draft",
        "delete": can_write and is_author and e.status in ("draft", "rejected"),
        "submit": can_write and e.status == "draft",
        "withdraw": can_write and is_author and e.status == "submitted",
        "start_review": can_validate
        and e.status == "submitted"
        and st["review_required"]
        and not (st["segregation_required"] and is_author),
        "validate": can_validate
        and not sep_block
        and (e.status == "under_review" or (e.status == "submitted" and not st["review_required"])),
        "reject": can_validate and e.status in ("submitted", "under_review"),
        "reopen": can_write and is_author and e.status == "rejected",
        "reverse": can_write and e.status == "validated" and e.origin != "reversal",
        "duplicate": can_write,
    }
    return {
        **entry_out(e, j),
        "journal_label": j.label if j else None,
        "journal_type": j.journal_type if j else None,
        "third_party": _tp_ref(tps.get(e.third_party_id)),
        "people": {
            k: ppl.get(str(getattr(e, k)))
            for k in ("created_by", "submitted_by", "reviewed_by", "validated_by", "rejected_by")
            if getattr(e, k)
        },
        "lines": [
            {
                "id": ln.id,
                "line_no": ln.line_no,
                "account_number": ln.account_number,
                "account_label": accs[ln.account_number].label if ln.account_number in accs else None,
                "third_party": _tp_ref(tps.get(ln.third_party_id)),
                "label": ln.label,
                "debit": ln.debit,
                "credit": ln.credit,
                "cost_center_id": ln.cost_center_id,
                "currency": ln.currency,
                "currency_amount": ln.currency_amount,
                "lettering_id": ln.lettering_id,
            }
            for ln in lines
        ],
        "check": {"balanced": chk.balanced, "difference": chk.difference, "issues": chk.issues} if chk else None,
        "events": [
            {
                "action": ev.action,
                "from_status": ev.from_status,
                "to_status": ev.to_status,
                "reason": ev.reason,
                "at": ev.created_at,
                "actor": ppl.get(str(ev.actor)) if ev.actor else None,
            }
            for ev in events
        ],
        "attachments": [
            {
                "document_id": d.id,
                "filename": d.original_filename,
                "size_bytes": d.size_bytes,
                "mime_type": d.mime_type,
                "attached_at": a.attached_at,
            }
            for a, d in atts
        ],
        "related": {str(k): {"id": v.id, "number": v.number, "status": v.status, "label": v.label} for k, v in related.items()},
        "settings": st,
        "actions": actions,
    }


def _tp_ref(t: ThirdParty | None) -> dict | None:
    return {"id": t.id, "code": t.code, "name": t.name, "kind": t.kind} if t else None


# ------------------------------------------------------------------ saisie
def _fy(db: Session, company_id: uuid.UUID, fy_id: uuid.UUID) -> FiscalYear:
    fy = db.get(FiscalYear, fy_id)
    if fy is None or fy.company_id != company_id:
        raise NotFound("Exercice introuvable")
    return fy


def parse_lines(raw: list[dict]) -> list[dict]:
    out = []
    for i, r in enumerate(raw, 1):
        try:
            debit, credit = eng.money(r.get("debit")), eng.money(r.get("credit"))
            cur_amount = eng.money(r["currency_amount"]) if r.get("currency_amount") not in (None, "") else None
        except eng.AmountError as exc:
            raise AccountingInvalid(f"Ligne {i} : {exc}") from exc
        account = str(r.get("account_number") or "").strip()
        if not account:
            raise AccountingInvalid(f"Ligne {i} : compte obligatoire.")
        out.append(
            {
                "line_no": i,
                "account_number": account,
                "third_party_id": r.get("third_party_id"),
                "label": (r.get("label") or None),
                "debit": debit,
                "credit": credit,
                "cost_center_id": r.get("cost_center_id"),
                "currency": r.get("currency") or None,
                "currency_amount": cur_amount,
            }
        )
    return out


def _write_lines(db: Session, e: JournalEntry, raw: list[dict]) -> None:
    parsed = parse_lines(raw)
    unknown = {p["account_number"] for p in parsed} - set(
        db.scalars(
            select(CompanyAccount.account_number).where(
                CompanyAccount.company_id == e.company_id,
                CompanyAccount.account_number.in_({p["account_number"] for p in parsed}),
            )
        )
    )
    if unknown:
        raise AccountingInvalid(f"Compte(s) non ouvert(s) dans le plan de l'entreprise : {', '.join(sorted(unknown))}.")
    for ln in _lines(db, e.id):
        db.delete(ln)
    db.flush()
    for p in parsed:
        db.add(
            JournalEntryLine(
                id=uuid.uuid4(),
                organization_id=e.organization_id,
                company_id=e.company_id,
                fiscal_year_id=e.fiscal_year_id,
                entry_id=e.id,
                **p,
            )
        )
    db.flush()


HEADER = ("journal_id", "entry_date", "piece_ref", "piece_date", "label", "third_party_id")


def create_entry(
    db: Session,
    company,
    user_id: uuid.UUID,
    data: dict,
    *,
    origin: str = "manual",
    reverses: uuid.UUID | None = None,
    corrects: uuid.UUID | None = None,
) -> JournalEntry:
    fy = _fy(db, company.id, data["fiscal_year_id"])
    if fy.status != "open":
        raise AccountingInvalid("Exercice clôturé : saisie impossible.")
    if not (fy.start_date <= data["entry_date"] <= fy.end_date):
        raise AccountingInvalid(
            f"La date doit être comprise dans l'exercice {fy.label} ({fy.start_date:%d/%m/%Y} – {fy.end_date:%d/%m/%Y})."
        )
    e = JournalEntry(
        id=uuid.uuid4(),
        organization_id=company.organization_id,
        company_id=company.id,
        fiscal_year_id=fy.id,
        origin=origin,
        reverses_entry_id=reverses,
        corrects_entry_id=corrects,
        created_by=user_id,
        **{k: data.get(k) for k in HEADER},
    )
    db.add(e)
    db.flush()
    _write_lines(db, e, data.get("lines") or [])
    db.refresh(e)
    return e


def update_draft(db: Session, company_id: uuid.UUID, entry_id: uuid.UUID, data: dict) -> JournalEntry:
    e = get_entry(db, company_id, entry_id, lock=True)
    if e.status != "draft":
        raise AccountingInvalid("Seule une écriture en brouillon peut être modifiée.")
    fy = db.get(FiscalYear, e.fiscal_year_id)
    if "entry_date" in data and not (fy.start_date <= data["entry_date"] <= fy.end_date):
        raise AccountingInvalid(f"La date doit être comprise dans l'exercice {fy.label}.")
    for k in HEADER:
        if k in data:
            setattr(e, k, data[k])
    db.flush()
    if "lines" in data:
        _write_lines(db, e, data["lines"])
    db.refresh(e)
    return e


def duplicate(db: Session, company, user_id: uuid.UUID, entry_id: uuid.UUID) -> JournalEntry:
    src = get_entry(db, company.id, entry_id)
    fy = db.get(FiscalYear, src.fiscal_year_id)
    if fy.status != "open":
        raise AccountingInvalid("Exercice clôturé : la copie doit être saisie dans un exercice ouvert.")
    data = {k: getattr(src, k) for k in HEADER} | {"fiscal_year_id": src.fiscal_year_id, "label": f"{src.label} (copie)"}
    data["lines"] = [_line_dict(ln) for ln in _lines(db, src.id)]
    return create_entry(db, company, user_id, data)


def _line_dict(ln: JournalEntryLine, swap: bool = False) -> dict:
    return {
        "account_number": ln.account_number,
        "third_party_id": ln.third_party_id,
        "label": ln.label,
        "debit": ln.credit if swap else ln.debit,
        "credit": ln.debit if swap else ln.credit,
        "cost_center_id": ln.cost_center_id,
        "currency": ln.currency,
        "currency_amount": ln.currency_amount,
    }


def delete_draft(db: Session, company_id: uuid.UUID, entry_id: uuid.UUID) -> None:
    e = get_entry(db, company_id, entry_id, lock=True)
    db.delete(e)
    db.flush()


def transition(db: Session, company_id: uuid.UUID, entry_id: uuid.UUID, action: str, reason: str | None = None) -> JournalEntry:
    """Changement de statut, ligne verrouillée : deux validations simultanées ne peuvent pas aboutir toutes les deux."""
    if action not in TRANSITIONS:
        raise AccountingInvalid("Action inconnue.")
    sources, target = TRANSITIONS[action]
    e = get_entry(db, company_id, entry_id, lock=True)
    if e.status not in sources:
        raise AccountingInvalid(f"Action impossible : l'écriture est « {e.status} ».")
    if action == "submit":
        chk = check(db, company_id, _lines(db, e.id))
        if not chk.ok:
            raise AccountingInvalid("Écriture non conforme : " + " ".join(chk.issues), details={"issues": chk.issues})
    if action == "reject":
        if not reason or len(reason.strip()) < 5:
            raise AccountingInvalid("Motif de rejet obligatoire (5 caractères au moins).")
        e.rejection_reason = reason.strip()
    e.status = target
    db.flush()
    db.refresh(e)
    return e


def reverse(
    db: Session,
    company,
    user_id: uuid.UUID,
    entry_id: uuid.UUID,
    entry_date: date,
    label: str | None = None,
    with_correction: bool = False,
) -> dict:
    """Extourne (contrepassation) d'une écriture validée, en brouillon ; avec `with_correction`, une écriture de
    correction en brouillon reprend aussi les lignes d'origine, à modifier avant soumission."""
    src = get_entry(db, company.id, entry_id)
    if src.status != "validated":
        raise AccountingInvalid("Seule une écriture validée peut être extournée.")
    lines = _lines(db, src.id)
    base = {k: getattr(src, k) for k in HEADER} | {"fiscal_year_id": src.fiscal_year_id, "entry_date": entry_date}
    rev = create_entry(
        db,
        company,
        user_id,
        base
        | {"label": label or f"Extourne de {src.number} — {src.label}", "lines": [_line_dict(ln, swap=True) for ln in lines]},
        origin="reversal",
        reverses=src.id,
    )
    out = {"reversal_id": rev.id, "correction_id": None}
    if with_correction:
        cor = create_entry(
            db,
            company,
            user_id,
            base | {"label": f"Correction de {src.number} — {src.label}", "lines": [_line_dict(ln) for ln in lines]},
            origin="correction",
            corrects=src.id,
        )
        out["correction_id"] = cor.id
    return out


# ------------------------------------------------------------------ pièces justificatives
def attach(db: Session, company, user_id: uuid.UUID, entry_id: uuid.UUID, filename: str, data: bytes) -> dict:
    e = get_entry(db, company.id, entry_id)
    if e.status in POSTED:
        raise AccountingInvalid("Écriture validée : ajoutez la pièce avant la validation.")
    s = get_settings()
    try:
        vf = validate_upload(
            filename, data, max_bytes=s.max_upload_size_mb * 1024 * 1024, allowed_extensions=s.allowed_upload_extensions
        )
    except FileRejected as exc:
        raise AccountingInvalid(str(exc)) from exc
    doc_id = uuid.uuid4()
    path = f"{company.organization_id}/{company.id}/{doc_id}.{vf.extension}"
    safe = filename.replace("/", "_").replace("\\", "_")[:255]
    db.add(
        FinancialDocument(
            id=doc_id,
            organization_id=company.organization_id,
            company_id=company.id,
            fiscal_year_id=e.fiscal_year_id,
            document_type="accounting_voucher",
            original_filename=safe,
            storage_path=path,
            mime_type=vf.mime_type,
            size_bytes=vf.size_bytes,
            sha256=vf.sha256,
            uploaded_by=user_id,
        )
    )
    db.flush()
    db.add(
        JournalEntryAttachment(
            entry_id=e.id, document_id=doc_id, organization_id=company.organization_id, company_id=company.id, attached_by=user_id
        )
    )
    db.flush()  # la base refuse avant l'envoi du fichier si la pièce ne peut pas être rattachée
    get_storage().upload(DOCUMENTS_BUCKET, path, data, vf.mime_type)
    return {"document_id": doc_id, "filename": safe, "sha256": vf.sha256}


def attachment_url(db: Session, company_id: uuid.UUID, entry_id: uuid.UUID, document_id: uuid.UUID) -> str:
    get_entry(db, company_id, entry_id)
    a = db.get(JournalEntryAttachment, (entry_id, document_id))
    doc = db.get(FinancialDocument, document_id)
    if a is None or doc is None:
        raise NotFound("Pièce introuvable")
    return get_storage().signed_url(DOCUMENTS_BUCKET, doc.storage_path, download_name=doc.original_filename)


def detach(db: Session, company_id: uuid.UUID, entry_id: uuid.UUID, document_id: uuid.UUID) -> None:
    get_entry(db, company_id, entry_id)
    a = db.get(JournalEntryAttachment, (entry_id, document_id))
    if a is None:
        raise NotFound("Pièce introuvable")
    db.delete(a)
    db.flush()
