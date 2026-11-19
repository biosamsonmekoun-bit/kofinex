"""API — comptabilité générale native (lot 3B, étapes A et B).

Paramétrage (paramètres, plan comptable de l'entreprise, tiers, journaux), écritures (saisie, circuit, extourne,
pièces), grand livre natif, balances et lettrage. Les routes contrôlent le rôle et délèguent aux services ; la
logique comptable est dans les moteurs et la base (migration 0014)."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Query, Request, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import CompanyContext, get_company_context, get_db
from app.core.config import get_settings
from app.core.permissions import Permission
from app.models import Company, JournalEntryLine
from app.schemas import native_accounting as s
from app.services import accounting_setup as setup
from app.services import journal_entries as entries
from app.services import native_ledger as gl
from app.services.accounting_setup import AccountingInvalid
from app.services.audit import record_event

router = APIRouter(tags=["Comptabilité native"])
Db = Annotated[Session, Depends(get_db)]
Comp = Annotated[CompanyContext, Depends(get_company_context)]
A = "/companies/{company_id}/accounting"


def _company(db: Session, ctx: CompanyContext) -> Company:
    return db.get(Company, ctx.company_id)


def _log(
    db: Session, request: Request, ctx: CompanyContext, action: str, entity_type: str, entity_id, details: dict | None = None
):
    record_event(
        db,
        user_id=ctx.user.id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        organization_id=ctx.organization_id,
        company_id=ctx.company_id,
        details=details or {},
        request=request,
    )


# ======================================================================== paramètres
@router.get(A + "/settings", summary="Paramètres comptables et droits de l'utilisateur")
def get_settings_(ctx: Comp, db: Db):
    return {
        **setup.settings(db, ctx.company_id),
        "permissions": {
            "setup": ctx.can(Permission.ACCOUNTING_SETUP),
            "settings": ctx.can(Permission.ACCOUNTING_SETTINGS),
            "write": ctx.can(Permission.ENTRY_WRITE),
            "validate": ctx.can(Permission.ENTRY_VALIDATE),
            "fec": ctx.can(Permission.FEC_EXPORT),
        },
    }


@router.put(A + "/settings", summary="Étape de revue et séparation des tâches (administrateurs)")
def put_settings(body: s.SettingsIn, request: Request, ctx: Comp, db: Db):
    ctx.require(Permission.ACCOUNTING_SETTINGS)
    out = setup.update_settings(db, _company(db, ctx), ctx.user.id, **body.model_dump())
    _log(db, request, ctx, "accounting.settings", "accounting_settings", None, body.model_dump())
    return out


# ======================================================================== plan comptable
@router.get(A + "/accounts", summary="Plan comptable de l'entreprise")
def list_accounts(
    ctx: Comp,
    db: Db,
    q: str | None = None,
    active: bool | None = None,
    limit: int = Query(500, ge=1, le=5000),
    offset: int = Query(0, ge=0),
):
    return setup.list_accounts(db, ctx.company_id, q, active, limit, offset)


@router.post(A + "/accounts", status_code=status.HTTP_201_CREATED, summary="Ouvrir un compte (rattaché au référentiel publié)")
def create_account(body: s.AccountIn, ctx: Comp, db: Db):
    ctx.require(Permission.ACCOUNTING_SETUP)
    return setup.account_out(setup.create_account(db, _company(db, ctx), ctx.user.id, **body.model_dump()))


@router.post(A + "/accounts/import-chart", summary="Ouvrir les comptes du référentiel publié (comptes sans sous-compte)")
def import_chart(body: s.ChartImportIn, request: Request, ctx: Comp, db: Db):
    ctx.require(Permission.ACCOUNTING_SETUP)
    out = setup.import_chart(db, _company(db, ctx), ctx.user.id, body.classes)
    _log(db, request, ctx, "accounting.chart_imported", "company_accounts", None, out)
    return out


@router.patch(A + "/accounts/{account_id}", summary="Modifier un compte (intitulé, activation, tiers, lettrage)")
def patch_account(account_id: uuid.UUID, body: s.AccountPatch, ctx: Comp, db: Db):
    ctx.require(Permission.ACCOUNTING_SETUP)
    return setup.account_out(setup.update_account(db, ctx.company_id, account_id, body.model_dump(exclude_unset=True)))


@router.delete(A + "/accounts/{account_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Supprimer un compte non mouvementé")
def delete_account(account_id: uuid.UUID, ctx: Comp, db: Db):
    ctx.require(Permission.ACCOUNTING_SETUP)
    setup.delete_account(db, ctx.company_id, account_id)


# ======================================================================== tiers
@router.get(A + "/third-parties", summary="Tiers (clients, fournisseurs, salariés, administrations…)")
def list_third_parties(
    ctx: Comp,
    db: Db,
    q: str | None = None,
    kind: s.ThirdPartyKind | None = None,
    active: bool | None = None,
    limit: int = Query(200, ge=1, le=2000),
    offset: int = Query(0, ge=0),
):
    return setup.list_third_parties(db, ctx.company_id, q, kind, active, limit, offset)


@router.post(A + "/third-parties", status_code=status.HTTP_201_CREATED, summary="Créer un tiers")
def create_third_party(body: s.ThirdPartyIn, ctx: Comp, db: Db):
    ctx.require(Permission.ACCOUNTING_SETUP)
    return setup.tp_out(setup.save_third_party(db, _company(db, ctx), ctx.user.id, body.model_dump()))


@router.patch(A + "/third-parties/{tp_id}", summary="Modifier un tiers")
def patch_third_party(tp_id: uuid.UUID, body: s.ThirdPartyPatch, ctx: Comp, db: Db):
    ctx.require(Permission.ACCOUNTING_SETUP)
    return setup.tp_out(setup.save_third_party(db, _company(db, ctx), ctx.user.id, body.model_dump(exclude_unset=True), tp_id))


# ======================================================================== journaux
@router.get(A + "/journals", summary="Journaux comptables")
def list_journals(ctx: Comp, db: Db, active: bool | None = None):
    return setup.list_journals(db, ctx.company_id, active)


@router.post(A + "/journals", status_code=status.HTTP_201_CREATED, summary="Créer un journal")
def create_journal(body: s.JournalIn, ctx: Comp, db: Db):
    ctx.require(Permission.ACCOUNTING_SETUP)
    data = body.model_dump()
    if data.get("number_prefix") is None:
        data.pop("number_prefix")
    return setup.journal_out(setup.save_journal(db, _company(db, ctx), ctx.user.id, data))


@router.patch(A + "/journals/{journal_id}", summary="Modifier ou désactiver un journal")
def patch_journal(journal_id: uuid.UUID, body: s.JournalPatch, ctx: Comp, db: Db):
    ctx.require(Permission.ACCOUNTING_SETUP)
    return setup.journal_out(
        setup.save_journal(db, _company(db, ctx), ctx.user.id, body.model_dump(exclude_unset=True), journal_id)
    )


@router.delete(A + "/journals/{journal_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Supprimer un journal sans écriture")
def delete_journal(journal_id: uuid.UUID, ctx: Comp, db: Db):
    ctx.require(Permission.ACCOUNTING_SETUP)
    setup.delete_journal(db, ctx.company_id, journal_id)


# ======================================================================== écritures
@router.get(A + "/entries", summary="Écritures (filtres : exercice, statut, journal, provenance, dates, texte)")
def list_entries(
    ctx: Comp,
    db: Db,
    fiscal_year_id: uuid.UUID | None = None,
    status_: list[str] | None = Query(None, alias="status"),
    journal_id: uuid.UUID | None = None,
    origin: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    q: str | None = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    return entries.list_entries(
        db,
        ctx.company_id,
        fiscal_year_id=fiscal_year_id,
        status=status_,
        journal_id=journal_id,
        origin=origin,
        date_from=date_from,
        date_to=date_to,
        q=q,
        limit=limit,
        offset=offset,
    )


def _detail(db: Session, ctx: CompanyContext, entry_id: uuid.UUID) -> dict:
    return entries.detail(
        db, ctx.company_id, entry_id, ctx.user.id, ctx.can(Permission.ENTRY_WRITE), ctx.can(Permission.ENTRY_VALIDATE)
    )


@router.post(A + "/entries/check", summary="Prévisualiser les contrôles d'une écriture sans l'enregistrer")
def check_entry(body: s.EntryIn, ctx: Comp, db: Db):
    try:
        parsed = entries.parse_lines([ln.model_dump() for ln in body.lines])
    except AccountingInvalid as exc:
        return {"balanced": False, "difference": None, "issues": [exc.message]}
    chk = entries.check(db, ctx.company_id, [JournalEntryLine(**p) for p in parsed])
    return {
        "balanced": chk.balanced,
        "difference": chk.difference,
        "total_debit": chk.total_debit,
        "total_credit": chk.total_credit,
        "issues": chk.issues,
    }


@router.post(A + "/entries", status_code=status.HTTP_201_CREATED, summary="Saisir une écriture (brouillon)")
def create_entry(body: s.EntryIn, ctx: Comp, db: Db):
    ctx.require(Permission.ENTRY_WRITE)
    data = body.model_dump()
    data["lines"] = [ln.model_dump() for ln in body.lines]
    e = entries.create_entry(db, _company(db, ctx), ctx.user.id, data)
    return _detail(db, ctx, e.id)


@router.get(A + "/entries/{entry_id}", summary="Écriture : en-tête, lignes, contrôles, pièces, historique, actions possibles")
def get_entry(entry_id: uuid.UUID, ctx: Comp, db: Db):
    return _detail(db, ctx, entry_id)


@router.patch(A + "/entries/{entry_id}", summary="Modifier un brouillon (en-tête et lignes)")
def patch_entry(entry_id: uuid.UUID, body: s.EntryPatch, ctx: Comp, db: Db):
    ctx.require(Permission.ENTRY_WRITE)
    data = body.model_dump(exclude_unset=True)
    if body.lines is not None:
        data["lines"] = [ln.model_dump() for ln in body.lines]
    entries.update_draft(db, ctx.company_id, entry_id, data)
    return _detail(db, ctx, entry_id)


@router.delete(
    A + "/entries/{entry_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Supprimer un brouillon ou une écriture rejetée"
)
def delete_entry(entry_id: uuid.UUID, ctx: Comp, db: Db):
    ctx.require(Permission.ENTRY_WRITE)
    entries.delete_draft(db, ctx.company_id, entry_id)


@router.post(A + "/entries/{entry_id}/transition", summary="Soumettre, retirer, réviser, valider, rejeter ou reprendre")
def transition(entry_id: uuid.UUID, body: s.TransitionIn, request: Request, ctx: Comp, db: Db):
    ctx.require(Permission.ENTRY_VALIDATE if body.action in ("start_review", "validate", "reject") else Permission.ENTRY_WRITE)
    e = entries.transition(db, ctx.company_id, entry_id, body.action, body.reason)
    if body.action in ("validate", "reject"):
        _log(
            db,
            request,
            ctx,
            f"entry.{body.action}d" if body.action == "validate" else "entry.rejected",
            "journal_entries",
            e.id,
            {"number": e.number, "reason": body.reason},
        )
    return _detail(db, ctx, entry_id)


@router.post(A + "/entries/{entry_id}/duplicate", status_code=status.HTTP_201_CREATED, summary="Dupliquer en brouillon")
def duplicate(entry_id: uuid.UUID, ctx: Comp, db: Db):
    ctx.require(Permission.ENTRY_WRITE)
    e = entries.duplicate(db, _company(db, ctx), ctx.user.id, entry_id)
    return _detail(db, ctx, e.id)


@router.post(
    A + "/entries/{entry_id}/reverse",
    status_code=status.HTTP_201_CREATED,
    summary="Extourner une écriture validée (et, si demandé, préparer la correction)",
)
def reverse(entry_id: uuid.UUID, body: s.ReverseIn, request: Request, ctx: Comp, db: Db):
    ctx.require(Permission.ENTRY_WRITE)
    out = entries.reverse(db, _company(db, ctx), ctx.user.id, entry_id, body.entry_date, body.label, body.with_correction)
    _log(
        db,
        request,
        ctx,
        "entry.reversal_prepared",
        "journal_entries",
        entry_id,
        {k: str(v) if v else None for k, v in out.items()},
    )
    return out


@router.post(
    A + "/entries/{entry_id}/attachments", status_code=status.HTTP_201_CREATED, summary="Joindre une pièce justificative"
)
async def attach(entry_id: uuid.UUID, ctx: Comp, db: Db, file: UploadFile = File(...)):
    ctx.require(Permission.ENTRY_WRITE)
    limit = get_settings().max_upload_size_mb * 1024 * 1024
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise AccountingInvalid(f"Fichier trop volumineux (maximum {get_settings().max_upload_size_mb} Mo).")
    return entries.attach(db, _company(db, ctx), ctx.user.id, entry_id, file.filename or "piece", data)


@router.get(A + "/entries/{entry_id}/attachments/{document_id}/url", summary="Lien de téléchargement temporaire d'une pièce")
def attachment_url(entry_id: uuid.UUID, document_id: uuid.UUID, ctx: Comp, db: Db):
    return {"url": entries.attachment_url(db, ctx.company_id, entry_id, document_id)}


@router.delete(
    A + "/entries/{entry_id}/attachments/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Détacher une pièce (écriture non validée)",
)
def detach(entry_id: uuid.UUID, document_id: uuid.UUID, ctx: Comp, db: Db):
    ctx.require(Permission.ENTRY_WRITE)
    entries.detach(db, ctx.company_id, entry_id, document_id)


# ======================================================================== grand livre, balances
def _filters(
    date_from: date | None = None,
    date_to: date | None = None,
    account: str | None = Query(None, pattern=r"^[0-9]{1,20}$"),
    journal_id: uuid.UUID | None = None,
    third_party_id: uuid.UUID | None = None,
    piece: str | None = None,
) -> gl.Filters:
    return gl.Filters(date_from, date_to, account, journal_id, third_party_id, piece)


F = Annotated[gl.Filters, Depends(_filters)]
Scope = Literal["before_inventory", "after_inventory", "final"]


@router.get(A + "/fiscal-years/{fiscal_year_id}/ledger", summary="Grand livre natif (écritures validées, solde progressif)")
def ledger(fiscal_year_id: uuid.UUID, ctx: Comp, db: Db, f: F):
    return gl.ledger(db, ctx.company_id, fiscal_year_id, f)


@router.get(A + "/fiscal-years/{fiscal_year_id}/ledger.csv", summary="Export CSV du grand livre natif")
def ledger_csv(fiscal_year_id: uuid.UUID, ctx: Comp, db: Db, f: F):
    data = gl.ledger(db, ctx.company_id, fiscal_year_id, f)
    return Response(
        gl.ledger_csv(data),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=grand-livre-natif-{data['fiscal_year']['label']}.csv"},
    )


@router.get(
    A + "/fiscal-years/{fiscal_year_id}/balance", summary="Balance générale ou auxiliaire, avant / après inventaire, comparative"
)
def balance(
    fiscal_year_id: uuid.UUID,
    ctx: Comp,
    db: Db,
    f: F,
    scope: Scope = "after_inventory",
    auxiliary: bool = False,
    compare: bool = False,
):
    return gl.balance(db, ctx.company_id, fiscal_year_id, f, scope=scope, auxiliary=auxiliary, compare=compare)


@router.get(A + "/fiscal-years/{fiscal_year_id}/balance.csv", summary="Export CSV de la balance native")
def balance_csv(fiscal_year_id: uuid.UUID, ctx: Comp, db: Db, f: F, scope: Scope = "after_inventory", auxiliary: bool = False):
    data = gl.balance(db, ctx.company_id, fiscal_year_id, f, scope=scope, auxiliary=auxiliary)
    kind = "auxiliaire" if auxiliary else "generale"
    return Response(
        gl.balance_csv(data),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=balance-{kind}-{data['fiscal_year']['label']}.csv"},
    )


# ======================================================================== lettrage
@router.get(A + "/lettering", summary="Lignes validées d'un compte lettrable (non lettrées, lettrées ou toutes)")
def lettering_lines(
    ctx: Comp,
    db: Db,
    account: str = Query(pattern=r"^[0-9]{2,20}$"),
    third_party_id: uuid.UUID | None = None,
    state: Literal["open", "lettered", "all"] = "open",
):
    return gl.lettering_lines(db, ctx.company_id, account, third_party_id, state)


@router.post(A + "/lettering", status_code=status.HTTP_201_CREATED, summary="Lettrer des lignes soldées entre elles")
def letter(body: s.LetterIn, ctx: Comp, db: Db):
    ctx.require(Permission.ENTRY_WRITE)
    return gl.letter(db, _company(db, ctx), ctx.user.id, body.line_ids)


@router.delete(A + "/lettering/{lettering_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Délettrer")
def unletter(lettering_id: uuid.UUID, ctx: Comp, db: Db):
    ctx.require(Permission.ENTRY_WRITE)
    gl.unletter(db, ctx.company_id, lettering_id)
