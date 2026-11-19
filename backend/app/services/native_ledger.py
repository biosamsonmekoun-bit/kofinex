"""Comptabilité native — grand livre, balances (générale, auxiliaire, avant / après inventaire, définitive,
comparative) et lettrage, calculés à partir des seules écritures natives validées.

Le grand livre importé (`services/ledger.py`, table ledger_lines) n'est ni lu ni modifié ici. Les calculs sont faits
par le moteur déterministe `engines/accounting/native_ledger.py` ; chaque montant renvoie à ses écritures."""

from __future__ import annotations

import csv
import io
import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import NotFound
from app.engines.accounting import entries as eng
from app.engines.accounting import native_ledger as nl
from app.models import CompanyAccount, FiscalYear, Journal, JournalEntry, JournalEntryLine, Lettering, ThirdParty
from app.services.accounting_setup import AccountingInvalid
from app.services.journal_entries import POSTED

SCOPES = ("before_inventory", "after_inventory", "final")


@dataclass
class Filters:
    date_from: date | None = None
    date_to: date | None = None
    account_prefix: str | None = None
    journal_id: uuid.UUID | None = None
    third_party_id: uuid.UUID | None = None
    piece: str | None = None


def _fy(db: Session, company_id: uuid.UUID, fy_id: uuid.UUID) -> FiscalYear:
    fy = db.get(FiscalYear, fy_id)
    if fy is None or fy.company_id != company_id:
        raise NotFound("Exercice introuvable")
    return fy


def posted(db: Session, fy: FiscalYear, f: Filters | None = None) -> list[tuple[nl.Posted, dict]]:
    """Lignes des écritures validées (et extournées) de l'exercice, avec leur provenance."""
    f = f or Filters()
    stmt = (
        select(JournalEntryLine, JournalEntry, Journal.code)
        .join(JournalEntry, JournalEntry.id == JournalEntryLine.entry_id)
        .join(Journal, Journal.id == JournalEntry.journal_id)
        .where(JournalEntryLine.fiscal_year_id == fy.id, JournalEntry.status.in_(POSTED))
    )
    if f.account_prefix:
        stmt = stmt.where(JournalEntryLine.account_number.like(f"{f.account_prefix.strip()}%"))
    if f.journal_id:
        stmt = stmt.where(JournalEntry.journal_id == f.journal_id)
    if f.third_party_id:
        stmt = stmt.where(JournalEntryLine.third_party_id == f.third_party_id)
    if f.piece:
        stmt = stmt.where(JournalEntry.piece_ref.ilike(f"%{f.piece.strip()}%"))
    out = []
    for ln, e, jcode in db.execute(stmt):
        p = nl.Posted(
            ln.account_number,
            e.entry_date,
            ln.debit,
            ln.credit,
            origin=e.origin,
            third_party=str(ln.third_party_id) if ln.third_party_id else None,
            journal=jcode,
            number=e.number,
            sequence=e.sequence_no or 0,
            line_no=ln.line_no,
            ref=ln.id,
        )
        out.append(
            (
                p,
                {
                    "line_id": ln.id,
                    "entry_id": e.id,
                    "number": e.number,
                    "journal": jcode,
                    "piece_ref": e.piece_ref,
                    "entry_label": e.label,
                    "label": ln.label,
                    "lettering_id": ln.lettering_id,
                    "origin": e.origin,
                    "status": e.status,
                    # lecture complète (FEC) : informations de la pièce, de la validation et de la devise
                    "piece_date": e.piece_date,
                    "validated_at": e.validated_at,
                    "journal_id": e.journal_id,
                    "line_no": ln.line_no,
                    "third_party_id": ln.third_party_id,
                    "currency": ln.currency,
                    "currency_amount": ln.currency_amount,
                },
            )
        )
    return out


def _labels(db: Session, company_id: uuid.UUID) -> tuple[dict, dict, dict]:
    accs = {a.account_number: a.label for a in db.scalars(select(CompanyAccount).where(CompanyAccount.company_id == company_id))}
    tps = {
        str(t.id): {"id": t.id, "code": t.code, "name": t.name}
        for t in db.scalars(select(ThirdParty).where(ThirdParty.company_id == company_id))
    }
    lets = {lt.id: lt.code for lt in db.scalars(select(Lettering).where(Lettering.company_id == company_id))}
    return accs, tps, lets


# ------------------------------------------------------------------ grand livre
def ledger(db: Session, company_id: uuid.UUID, fy_id: uuid.UUID, f: Filters) -> dict:
    fy = _fy(db, company_id, fy_id)
    rows = posted(db, fy, f)
    meta = {id(p): m for p, m in rows}
    accs, tps, lets = _labels(db, company_id)
    out = []
    for a in nl.ledger([p for p, _ in rows], f.date_from, f.date_to):
        lines = []
        for r in a["rows"]:
            p, m = r["line"], meta[id(r["line"])]
            lines.append(
                {
                    "entry_date": p.entry_date,
                    "journal": m["journal"],
                    "number": m["number"],
                    "entry_id": m["entry_id"],
                    "line_id": m["line_id"],
                    "piece_ref": m["piece_ref"],
                    "label": m["label"] or m["entry_label"],
                    "third_party": tps.get(p.third_party),
                    "debit": p.debit,
                    "credit": p.credit,
                    "balance": r["balance"],
                    "lettering": lets.get(m["lettering_id"]),
                    "origin": m["origin"],
                }
            )
        out.append(
            {
                "account": a["account"],
                "label": accs.get(a["account"]),
                "opening": a["opening"],
                "debit": a["debit"],
                "credit": a["credit"],
                "closing": a["closing"],
                "lines": lines,
            }
        )
    totals = {"debit": sum((a["debit"] for a in out), Decimal(0)), "credit": sum((a["credit"] for a in out), Decimal(0))}
    return {
        "fiscal_year": {"id": fy.id, "label": fy.label, "status": fy.status},
        "accounts": out,
        "totals": totals,
        "source": "native_entries",
        "note": "Écritures natives validées uniquement (les grands livres importés sont distincts).",
    }


# ------------------------------------------------------------------ balances
def _previous_fy(db: Session, fy: FiscalYear) -> FiscalYear | None:
    return db.scalars(
        select(FiscalYear)
        .where(FiscalYear.company_id == fy.company_id, FiscalYear.end_date < fy.start_date)
        .order_by(FiscalYear.end_date.desc())
        .limit(1)
    ).first()


def balance(
    db: Session,
    company_id: uuid.UUID,
    fy_id: uuid.UUID,
    f: Filters,
    *,
    scope: str = "after_inventory",
    auxiliary: bool = False,
    compare: bool = False,
) -> dict:
    if scope not in SCOPES:
        raise AccountingInvalid("Type de balance inconnu.")
    fy = _fy(db, company_id, fy_id)
    if scope == "final" and fy.status != "closed":
        raise AccountingInvalid("La balance définitive n'existe qu'après la clôture de l'exercice.")
    lines = nl.filter_scope([p for p, _ in posted(db, fy, f)], scope)
    if auxiliary:
        lines = [p for p in lines if p.third_party]
    tb = nl.trial_balance(lines, f.date_from, f.date_to, by_third_party=auxiliary)
    accs, tps, _ = _labels(db, company_id)
    rows = [
        {**r, "label": accs.get(r["account"]), "third_party": tps.get(r["third_party"]) if r["third_party"] else None}
        for r in tb["rows"]
    ]
    out = {
        "fiscal_year": {"id": fy.id, "label": fy.label, "status": fy.status},
        "scope": scope,
        "auxiliary": auxiliary,
        "rows": rows,
        "totals": tb["totals"],
        "checks": tb["checks"],
        "balanced": tb["balanced"],
        "entries_count": db.scalar(
            select(func.count()).where(JournalEntry.fiscal_year_id == fy.id, JournalEntry.status.in_(POSTED))
        ),
        "pending_count": db.scalar(
            select(func.count()).where(
                JournalEntry.fiscal_year_id == fy.id, JournalEntry.status.in_(("draft", "submitted", "under_review"))
            )
        ),
        "comparative": None,
    }
    if compare:
        prev = _previous_fy(db, fy)
        if prev is None:
            out["comparative"] = {"available": False, "reason": "Aucun exercice précédent pour cette entreprise."}
        else:
            prev_lines = nl.filter_scope(
                [p for p, _ in posted(db, prev, Filters(account_prefix=f.account_prefix, journal_id=f.journal_id))], scope
            )
            prev_tb = nl.trial_balance(prev_lines)
            if not prev_tb["rows"]:
                out["comparative"] = {
                    "available": False,
                    "reason": f"Aucune écriture native validée sur l'exercice {prev.label}.",
                }
            else:
                out["comparative"] = {
                    "available": True,
                    "previous_label": prev.label,
                    "rows": [{**r, "label": accs.get(r["account"])} for r in nl.comparative(tb["rows"], prev_tb["rows"])],
                }
    return out


def balance_csv(data: dict) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    aux = data["auxiliary"]
    w.writerow(
        [
            "Compte",
            "Intitulé",
            *(["Tiers"] if aux else []),
            "Ouverture débit",
            "Ouverture crédit",
            "Mouvements débit",
            "Mouvements crédit",
            "Solde débiteur",
            "Solde créditeur",
        ]
    )
    for r in data["rows"]:
        w.writerow(
            [
                r["account"],
                r["label"] or "",
                *([r["third_party"]["code"] if r["third_party"] else ""] if aux else []),
                *(str(r[k]) for k in ("opening_debit", "opening_credit", "debit", "credit", "closing_debit", "closing_credit")),
            ]
        )
    t = data["totals"]
    w.writerow(
        [
            "Totaux",
            "",
            *([""] if aux else []),
            *(str(t[k]) for k in ("opening_debit", "opening_credit", "debit", "credit", "closing_debit", "closing_credit")),
        ]
    )
    return ("﻿" + buf.getvalue()).encode("utf-8")


def ledger_csv(data: dict) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["Compte", "Date", "Journal", "Numéro", "Pièce", "Libellé", "Tiers", "Débit", "Crédit", "Solde", "Lettrage"])
    for a in data["accounts"]:
        w.writerow([a["account"], "", "", "", "", f"Solde d'ouverture — {a['label'] or ''}", "", "", "", str(a["opening"]), ""])
        for ln in a["lines"]:
            w.writerow(
                [
                    a["account"],
                    ln["entry_date"].isoformat(),
                    ln["journal"],
                    ln["number"],
                    ln["piece_ref"] or "",
                    ln["label"] or "",
                    ln["third_party"]["code"] if ln["third_party"] else "",
                    str(ln["debit"]),
                    str(ln["credit"]),
                    str(ln["balance"]),
                    ln["lettering"] or "",
                ]
            )
    return ("﻿" + buf.getvalue()).encode("utf-8")


# ------------------------------------------------------------------ lettrage
def lettering_lines(
    db: Session, company_id: uuid.UUID, account_number: str, third_party_id: uuid.UUID | None, state: str = "open"
) -> dict:
    acc = db.scalars(
        select(CompanyAccount).where(CompanyAccount.company_id == company_id, CompanyAccount.account_number == account_number)
    ).first()
    if acc is None:
        raise NotFound("Compte introuvable")
    stmt = (
        select(JournalEntryLine, JournalEntry, Journal.code)
        .join(JournalEntry, JournalEntry.id == JournalEntryLine.entry_id)
        .join(Journal, Journal.id == JournalEntry.journal_id)
        .where(
            JournalEntryLine.company_id == company_id,
            JournalEntryLine.account_number == account_number,
            JournalEntry.status.in_(POSTED),
        )
    )
    stmt = (
        stmt.where(JournalEntryLine.third_party_id == third_party_id)
        if third_party_id
        else stmt.where(JournalEntryLine.third_party_id.is_(None))
    )
    if state == "open":
        stmt = stmt.where(JournalEntryLine.lettering_id.is_(None))
    elif state == "lettered":
        stmt = stmt.where(JournalEntryLine.lettering_id.is_not(None))
    lets = {
        lt.id: lt.code
        for lt in db.scalars(
            select(Lettering).where(Lettering.company_id == company_id, Lettering.account_number == account_number)
        )
    }
    fys = {f.id: f for f in db.scalars(select(FiscalYear).where(FiscalYear.company_id == company_id))}
    items = [
        {
            "line_id": ln.id,
            "entry_id": e.id,
            "entry_date": e.entry_date,
            "journal": j,
            "number": e.number,
            "piece_ref": e.piece_ref,
            "label": ln.label or e.label,
            "debit": ln.debit,
            "credit": ln.credit,
            "lettering_id": ln.lettering_id,
            "lettering": lets.get(ln.lettering_id),
            "fiscal_year_open": fys[e.fiscal_year_id].status == "open",
        }
        for ln, e, j in db.execute(stmt.order_by(JournalEntry.entry_date, JournalEntryLine.line_no))
    ]
    bal = sum((i["debit"] - i["credit"] for i in items), Decimal(0))
    return {
        "account": {"number": acc.account_number, "label": acc.label, "lettering_enabled": acc.lettering_enabled},
        "items": items,
        "balance": bal,
    }


def letter(db: Session, company, user_id: uuid.UUID, line_ids: list[uuid.UUID]) -> dict:
    lines = db.scalars(
        select(JournalEntryLine)
        .where(JournalEntryLine.id.in_(line_ids), JournalEntryLine.company_id == company.id)
        .with_for_update()
    ).all()
    if len(lines) != len(set(line_ids)):
        raise NotFound("Ligne introuvable")
    chk = eng.lettering_check(
        [eng.Line(ln.account_number, ln.debit, ln.credit, str(ln.third_party_id) if ln.third_party_id else None) for ln in lines]
    )
    if not chk.ok:
        raise AccountingInvalid(" ".join(chk.issues), details={"issues": chk.issues})
    if any(ln.lettering_id for ln in lines):
        raise AccountingInvalid("Une des lignes est déjà lettrée.")
    first = lines[0]
    for attempt in range(5):
        n = db.scalar(
            select(func.count()).where(Lettering.company_id == company.id, Lettering.account_number == first.account_number)
        )
        code = eng.lettering_code(n + 1 + attempt)
        lt = Lettering(
            id=uuid.uuid4(),
            organization_id=company.organization_id,
            company_id=company.id,
            account_number=first.account_number,
            third_party_id=first.third_party_id,
            code=code,
            amount=chk.total_debit,
            created_by=user_id,
        )
        sp = db.begin_nested()
        try:
            db.add(lt)
            db.flush()
            sp.commit()
            break
        except IntegrityError:
            sp.rollback()
    else:
        raise AccountingInvalid("Code de lettrage indisponible : réessayez.")
    for ln in lines:
        ln.lettering_id = lt.id
    db.flush()
    db.connection().exec_driver_sql(
        "SET CONSTRAINTS journal_entry_lines_lettering_check IMMEDIATE"
    )  # contrôle d'équilibre immédiat
    return {"lettering_id": lt.id, "code": lt.code, "amount": lt.amount}


def unletter(db: Session, company_id: uuid.UUID, lettering_id: uuid.UUID) -> None:
    lt = db.get(Lettering, lettering_id)
    if lt is None or lt.company_id != company_id:
        raise NotFound("Lettrage introuvable")
    db.delete(lt)
    db.flush()
