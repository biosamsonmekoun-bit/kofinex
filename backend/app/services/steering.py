"""Pilotage du contrôle de gestion : couche de lecture normalisée des sources validées, classification des comptes
d'après le référentiel publié, puis tableaux de bord financier, budgétaire, de trésorerie et de la masse salariale.

Sources (jamais additionnées entre elles) :
- `native`   : écritures natives validées ou extournées (lot 3B) — l'extourne neutralise l'écriture d'origine ;
- `imported` : grand livre importé et validé de l'exercice (lot 3) ; un nouvel import remplace le précédent ;
- `trial_balance` : balance importée — montants annuels seulement (ni mois, ni tiers, ni écritures).
Règle de priorité (`auto`) : écritures natives s'il y en a au moins une validée sur l'exercice, sinon grand livre
importé, sinon balance importée. Le choix est restitué avec chaque réponse.

Les indicateurs sont recalculés à chaque demande à partir de ces sources : aucune copie des écritures, aucune valeur
saisie dans les tableaux de bord. Le « filigrane » des sources (dernière écriture validée, import actif, écritures en
attente) permet à l'interface de ne recharger que lorsqu'une source a changé."""

from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import NotFound
from app.engines.accounting.statements import TBEntry, build_statements
from app.engines.financial.calculator import Calculator, Formula, YearContext
from app.engines.importing import ledger as lg
from app.engines.management import steering as st
from app.models import (
    Budget,
    BudgetKind,
    ChartAccount,
    Company,
    CompanyAccount,
    FiscalYear,
    ImportJob,
    Journal,
    JournalEntry,
    JournalEntryLine,
    LedgerLine,
    ThirdParty,
    TrialBalanceEntry,
)
from app.services import analysis as analysis_svc
from app.services import management as mgmt
from app.services.accounting_setup import AccountingInvalid

POSTED = ("validated", "reversed")
PENDING = ("draft", "submitted", "under_review")
PL_CODES = (
    "CA",
    "MARGE_COMMERCIALE",
    "VALEUR_AJOUTEE",
    "EBE",
    "RESULTAT_EXPLOITATION",
    "RESULTAT_FINANCIER",
    "RAO",
    "RESULTAT_HAO",
    "RESULTAT_NET",
)


# ====================================================================== sources
def watermark(db: Session, fy: FiscalYear) -> dict:
    native = db.execute(
        select(func.count(), func.max(JournalEntry.validated_at)).where(
            JournalEntry.fiscal_year_id == fy.id, JournalEntry.status.in_(POSTED)
        )
    ).one()
    last = db.scalars(
        select(JournalEntry)
        .where(JournalEntry.fiscal_year_id == fy.id, JournalEntry.status.in_(POSTED))
        .order_by(JournalEntry.validated_at.desc())
        .limit(1)
    ).first()
    pending = db.scalar(select(func.count()).where(JournalEntry.fiscal_year_id == fy.id, JournalEntry.status.in_(PENDING)))
    lj = db.get(ImportJob, fy.active_ledger_import_job_id) if fy.active_ledger_import_job_id else None
    tj = db.get(ImportJob, fy.active_import_job_id) if fy.active_import_job_id else None
    inventory = db.scalar(
        select(func.count()).where(
            JournalEntry.fiscal_year_id == fy.id, JournalEntry.status.in_(POSTED), JournalEntry.origin == "inventory"
        )
    )
    return {
        "native_entries": native[0],
        "native_last_validated_at": native[1],
        "native_last_entry": {"id": last.id, "number": last.number, "label": last.label} if last else None,
        "native_pending": pending,
        "native_inventory_entries": inventory,
        "ledger_import_id": lj.id if lj else None,
        "ledger_imported_at": lj.completed_at if lj else None,
        "trial_balance_import_id": tj.id if tj else None,
        "trial_balance_imported_at": tj.completed_at if tj else None,
        "fiscal_year_status": fy.status,
        "token": ":".join(
            str(x)
            for x in (native[0], native[1].isoformat() if native[1] else "", pending, lj.id if lj else "", tj.id if tj else "")
        ),
    }


def resolve_source(wm: dict, requested: str = "auto") -> tuple[str | None, list[str]]:
    notes = []
    avail = {
        "native": wm["native_entries"] > 0,
        "imported": wm["ledger_import_id"] is not None,
        "trial_balance": wm["trial_balance_import_id"] is not None,
    }
    if requested != "auto":
        if requested not in avail:
            raise AccountingInvalid("Source inconnue.")
        if not avail[requested]:
            raise AccountingInvalid("Cette source n'est pas disponible pour l'exercice.")
        src = requested
    else:
        src = next((s for s in ("native", "imported", "trial_balance") if avail[s]), None)
    if src == "native" and avail["imported"]:
        notes.append(
            "Un grand livre importé existe aussi pour cet exercice : il n'est pas additionné aux écritures natives "
            "(source retenue : écritures natives)."
        )
    if src == "imported" and wm["native_pending"]:
        notes.append(f"{wm['native_pending']} écriture(s) native(s) en attente de validation ne sont pas prises en compte.")
    if src == "trial_balance":
        notes.append("Source : balance importée — montants annuels uniquement (pas de vue mensuelle, de tiers ni d'écritures).")
    return src, notes


def movements(db: Session, fy: FiscalYear, source: str) -> list[st.Movement]:
    if source == "native":
        rows = db.execute(
            select(JournalEntryLine, JournalEntry, Journal, ThirdParty)
            .join(JournalEntry, JournalEntry.id == JournalEntryLine.entry_id)
            .join(Journal, Journal.id == JournalEntry.journal_id)
            .outerjoin(ThirdParty, ThirdParty.id == JournalEntryLine.third_party_id)
            .where(JournalEntryLine.fiscal_year_id == fy.id, JournalEntry.status.in_(POSTED))
        )
        return [
            st.Movement(
                ln.account_number,
                e.entry_date,
                ln.debit,
                ln.credit,
                str(e.id),
                is_opening=e.origin == "opening",
                journal=j.code,
                number=e.number,
                piece=e.piece_ref,
                label=ln.label or e.label,
                third_party=str(t.id) if t else None,
                third_party_label=f"{t.code} · {t.name}" if t else None,
                line_ref=str(ln.id),
                journal_type=j.journal_type,
            )
            for ln, e, j, t in rows
        ]
    if source == "imported":
        job = db.get(ImportJob, fy.active_ledger_import_job_id)
        oj = set(lg.LedgerOptions.from_dict(job.options).opening_journals)
        rows = db.scalars(select(LedgerLine).where(LedgerLine.import_job_id == job.id, LedgerLine.status == "valid"))
        return [
            st.Movement(
                r.account_number,
                r.entry_date,
                r.debit,
                r.credit,
                f"{r.journal_code or ''}|{r.entry_number or r.document_ref or r.source_row}",
                is_opening=(r.journal_code in oj),
                journal=r.journal_code,
                number=r.entry_number,
                piece=r.document_ref,
                label=r.label,
                third_party=r.auxiliary_account,
                third_party_label=r.auxiliary_label or r.auxiliary_account,
                line_ref=str(r.id),
            )
            for r in rows
            if r.account_number and r.entry_date
        ]
    if source == "trial_balance":
        out = []
        for r in db.scalars(select(TrialBalanceEntry).where(TrialBalanceEntry.import_job_id == fy.active_import_job_id)):
            if r.opening_debit or r.opening_credit:
                out.append(
                    st.Movement(r.account_number, fy.start_date, r.opening_debit, r.opening_credit, "ouverture", is_opening=True)
                )
            out.append(
                st.Movement(r.account_number, fy.end_date, r.movement_debit, r.movement_credit, f"balance|{r.account_number}")
            )
        return out
    return []


# ====================================================================== classification (référentiel)
def classification(db: Session, fy: FiscalYear, accounts: set[str]) -> tuple[dict[str, st.AccountClass], list[str]]:
    """Charge la version publiée du référentiel de l'exercice et délègue la classification au moteur (`steering.classify`)."""
    vid = mgmt.framework_version_id(db, fy)
    if vid is None:
        return {}, ["Aucune version publiée du référentiel pour cet exercice : les comptes ne peuvent pas être classés."]
    chart = {
        n: (lab, nat)
        for n, lab, nat in db.execute(
            select(ChartAccount.account_number, ChartAccount.label, ChartAccount.nature).where(
                ChartAccount.framework_version_id == vid
            )
        )
    }
    structure, rules, concepts = analysis_svc._framework(db, vid)
    labels = {
        a.account_number: a.label for a in db.scalars(select(CompanyAccount).where(CompanyAccount.company_id == fy.company_id))
    }
    return st.classify(accounts, chart, structure, rules, concepts, labels)


def _context(db: Session, company: Company, fy: FiscalYear, source: str = "auto") -> dict:
    wm = watermark(db, fy)
    src, notes = resolve_source(wm, source)
    movs = movements(db, fy, src) if src else []
    cls, reserves = classification(db, fy, {m.account for m in movs})
    return {"wm": wm, "source": src, "notes": notes, "movs": movs, "cls": cls, "reserves": reserves}


def _previous_fy(db: Session, fy: FiscalYear) -> FiscalYear | None:
    return db.scalars(
        select(FiscalYear)
        .where(FiscalYear.company_id == fy.company_id, FiscalYear.end_date < fy.start_date)
        .order_by(FiscalYear.end_date.desc())
        .limit(1)
    ).first()


def period(fy: FiscalYear, view: str, month: int | None, d_from: date | None, d_to: date | None) -> tuple[date, date]:
    try:
        return st.period_range(fy.start_date, fy.end_date, view, month, (d_from, d_to) if d_from and d_to else None)
    except ValueError as exc:
        raise AccountingInvalid(str(exc)) from exc


# ====================================================================== indicateurs de la bibliothèque sur une période
def library_pl(db: Session, company: Company, fy: FiscalYear, net: dict[str, Decimal], rng: tuple[date, date]) -> dict:
    """Soldes du compte de résultat de la période, calculés par le moteur des états (`build_statements`) et la bibliothèque
    KOFINEX-STD-1 (`Calculator`) à partir d'une balance de période. Seuls les indicateurs du compte de résultat sont
    restitués : les indicateurs de bilan n'ont pas de sens sur une période."""
    vid = mgmt.framework_version_id(db, fy)
    if vid is None:
        return {}
    structure, rules, concepts = analysis_svc._framework(db, vid)
    entries = [
        TBEntry(a, None, Decimal(0), Decimal(0), max(v, Decimal(0)), max(-v, Decimal(0)), max(v, Decimal(0)), max(-v, Decimal(0)))
        for a, v in net.items()
        if v
    ]
    try:
        stm = build_statements(entries, structure, rules)
    except Exception as exc:  # noqa: BLE001 — erreur de correspondance : restituée, pas d'arrêt du tableau de bord
        return {"error": str(exc)}
    formulas = analysis_svc.applicable_formulas(db, company.organization_id, company.framework_id)
    defs = [
        Formula(
            f.code,
            f.version,
            f.expression_ast,
            f.unit,
            f.rounding_scale,
            f.zero_division_policy,
            f.missing_input_policy,
            str(f.id),
        )
        for f in formulas
        if f.code in PL_CODES
    ]
    res = Calculator(YearContext(fy.label, rng[0], rng[1], stm.values(), entries), None, concepts, defs).run()
    names = {f.code: f.name for f in formulas}
    return {
        r.code: {"name": names.get(r.code, r.code), "value": r.value, "status": r.status, "message": r.message, "unit": r.unit}
        for r in res
    }


# ====================================================================== tableau de bord financier
def _pl_out(s: st.PL) -> dict:
    return {
        "produits_ao": s.produits_ao,
        "charges_ao": s.charges_ao,
        "marge_ao": s.marge_ao,
        "produits_hao": s.produits_hao,
        "charges_hao": s.charges_hao,
        "marge_hao": s.marge_hao,
        "marge_totale": s.marge_totale,
        "chiffre_affaires": s.chiffre_affaires,
        "total_produits": s.total_produits,
        "total_charges": s.total_charges,
        "resultat": s.resultat,
        "impot_participation": s.autres_charges,
        "autres_produits": s.autres_produits,
        "personnel": s.personnel,
    }


def _tops(ctx: dict, net: dict, rng, partner_basis: str = "revenue") -> dict:
    cls, movs = ctx["cls"], ctx["movs"]
    out = {
        "produits_ao": st.top_accounts(net, cls, group="AO", nature="income"),
        "charges_ao": st.top_accounts(net, cls, group="AO", nature="expense"),
        "produits_hao": st.top_accounts(net, cls, group="HAO", nature="income"),
        "charges_hao": st.top_accounts(net, cls, group="HAO", nature="expense"),
    }
    if ctx["source"] == "trial_balance":
        na = {"available": False, "reason": "La balance ne comporte ni écritures ni tiers : classement indisponible."}
        out["clients"] = out["fournisseurs"] = na
    else:
        for key, kind in (("clients", "customer"), ("fournisseurs", "supplier")):
            t = st.top_partners(movs, cls, rng, kind, basis=partner_basis)
            has_aux = any(m.third_party for m in movs if (cls.get(m.account) or st.AccountClass()).partner == kind)
            t["available"] = has_aux
            if not has_aux:
                t["reason"] = (
                    "Aucun tiers (compte auxiliaire) sur les comptes "
                    + ("clients" if kind == "customer" else "fournisseurs")
                    + " dans la source : classement indisponible."
                )
            out[key] = t
    return out


def reliability(ctx: dict, s: st.PL, fy: FiscalYear, lib: dict) -> dict:
    res, wm = list(ctx["reserves"]), ctx["wm"]
    provisional = fy.status != "closed"
    if provisional:
        res.append("Exercice non clôturé : résultats provisoires.")
    if ctx["source"] == "native":
        if wm["native_pending"]:
            res.append(f"{wm['native_pending']} écriture(s) en attente de validation, non prises en compte.")
        if not wm["native_inventory_entries"] and provisional:
            res.append(
                "Aucune écriture de travaux d'inventaire validée (amortissements, provisions, régularisations) : "
                "les résultats en dépendent."
            )
    if s.unclassified:
        res.append(
            f"{len(s.unclassified)} compte(s) de gestion non rattaché(s) aux soldes AO / HAO : "
            f"{', '.join(s.unclassified[:10])}{'…' if len(s.unclassified) > 10 else ''}."
        )
    if s.no_nature:
        res.append(f"{len(s.no_nature)} compte(s) sans nature dans le plan du référentiel : {', '.join(s.no_nature[:10])}.")
    if lib.get("error"):
        res.append(f"Indicateurs de la bibliothèque indisponibles : {lib['error']}")
    lib_rao = (lib.get("RAO") or {}).get("value")
    if lib_rao is not None and Decimal(str(lib_rao)) != s.marge_ao:
        res.append(f"Écart entre la marge AO ({s.marge_ao}) et le RAO des états ({lib_rao}) : vérifier les correspondances.")
    level = (
        "low"
        if (s.unclassified or s.no_nature or ctx["reserves"] or lib.get("error") or ctx["source"] is None)
        else "medium"
        if (provisional or wm["native_pending"] or ctx["source"] == "trial_balance")
        else "high"
    )
    return {"level": level, "provisional": provisional, "reserves": res}


def financial(
    db: Session,
    company: Company,
    fy: FiscalYear,
    *,
    view: str = "year",
    month: int | None = None,
    d_from: date | None = None,
    d_to: date | None = None,
    compare: bool = True,
    source: str = "auto",
    partner_basis: str = "revenue",
) -> dict:
    if partner_basis not in ("revenue", "invoiced"):
        raise AccountingInvalid("Base de classement des tiers inconnue.")
    ctx = _context(db, company, fy, source)
    rng = period(fy, view, month, d_from, d_to)
    base = {
        "company": {"id": company.id, "name": company.name, "currency": company.currency},
        "fiscal_year": {
            "id": fy.id,
            "label": fy.label,
            "start_date": fy.start_date,
            "end_date": fy.end_date,
            "status": fy.status,
        },
        "period": {"view": view, "month": month, "from": rng[0], "to": rng[1]},
        "source": ctx["source"],
        "source_notes": ctx["notes"],
        "watermark": ctx["wm"],
        "computed_at": datetime.now(UTC),
    }
    if ctx["source"] is None:
        return {
            **base,
            "available": False,
            "reason": "Aucune donnée validée pour l'exercice : validez des écritures natives ou "
            "importez et validez le grand livre (ou la balance).",
        }
    net = st.nets(ctx["movs"], rng)
    s = st.pl(net, ctx["cls"])
    lib = library_pl(db, company, fy, net, rng)
    out = {
        **base,
        "available": True,
        "kpis": _pl_out(s),
        "library": lib,
        "tops": _tops(ctx, net, rng, partner_basis),
        "monthly": None
        if ctx["source"] == "trial_balance"
        else st.with_changes(st.monthly(ctx["movs"], ctx["cls"], fy.start_date, fy.end_date)),
        "reliability": reliability(ctx, s, fy, lib),
        "comparison": None,
        "conventions": [
            "Montants nets : produit = crédit − débit, charge = débit − crédit. Les extournes, avoirs et régularisations "
            "(factures à établir, produits constatés d'avance) viennent donc en déduction ; un tableau qui additionne seulement "
            "les crédits des produits et les débits des charges donne des montants bruts plus élevés.",
            "Impôt sur le résultat et participation (y compris l'IMF) : présentés à part (« impôt et participation »), hors "
            "HAO, selon le référentiel ; ils entrent dans le résultat net.",
            "Produits et charges AO : comptes rattachés aux lignes du compte de résultat qui composent le résultat des activités "
            "ordinaires du référentiel ; HAO : lignes du résultat hors activités ordinaires.",
            "Marge AO = produits AO − charges AO ; marge HAO = produits HAO − charges HAO ; marge totale = AO + HAO "
            "(avant participation et impôt sur le résultat).",
            "CA, EBE, résultats : bibliothèque KOFINEX-STD-1 appliquée à la balance de la période. L'EBITDA n'est pas présenté.",
            "Top 10 : pourcentage du total de la catégorie. Clients : chiffre d'affaires des écritures portant sur un seul "
            "client ; fournisseurs : charges des écritures portant sur un seul fournisseur ; règlements et transferts exclus, "
            "avoirs déduits.",
            "À-nouveaux exclus des flux de la période.",
        ],
    }
    if compare:
        prev = _previous_fy(db, fy)
        if prev is None:
            out["comparison"] = {"available": False, "reason": "Aucun exercice précédent."}
        else:
            prng = st.equivalent_range(rng, (fy.start_date, fy.end_date), (prev.start_date, prev.end_date))
            pctx = _context(db, company, prev, "auto")
            if pctx["source"] is None or prng is None:
                out["comparison"] = {
                    "available": False,
                    "reason": f"Aucune donnée validée comparable sur l'exercice {prev.label}.",
                }
            else:
                pnet = st.nets(pctx["movs"], prng)
                ps = st.pl(pnet, pctx["cls"])
                kp, kc = _pl_out(ps), out["kpis"]
                missing = sorted(set(pnet) - set(ctx["cls"]))
                out["comparison"] = {
                    "available": True,
                    "fiscal_year": prev.label,
                    "period": {"from": prng[0], "to": prng[1]},
                    "source": pctx["source"],
                    "kpis": kp,
                    "variations": {k: st.variation(kc[k], kp[k]) for k in kc},
                    "tops": _tops(pctx, pnet, prng, partner_basis),
                    "notes": ([f"{len(missing)} compte(s) de N-1 absent(s) des mouvements de N."] if missing else [])
                    + (["Source différente entre les deux exercices."] if pctx["source"] != ctx["source"] else []),
                }
    return out


# ====================================================================== détail jusqu'aux écritures
DRILL = (
    "produits_ao",
    "charges_ao",
    "produits_hao",
    "charges_hao",
    "chiffre_affaires",
    "personnel",
    "total_charges",
    "total_produits",
    "account",
    "account_prefix",
    "partner",
    "treasury",
)


def drilldown(
    db: Session,
    company: Company,
    fy: FiscalYear,
    *,
    kind: str,
    key: str | None = None,
    view: str = "year",
    month: int | None = None,
    d_from: date | None = None,
    d_to: date | None = None,
    source: str = "auto",
    limit: int = 200,
    offset: int = 0,
    payroll_detail: bool = False,
) -> dict:
    if kind not in DRILL:
        raise AccountingInvalid("Détail inconnu.")
    ctx = _context(db, company, fy, source)
    rng = period(fy, view, month, d_from, d_to)
    cls = ctx["cls"]

    def keep(m: st.Movement) -> bool:
        c = cls.get(m.account) or st.AccountClass()
        if kind == "account":
            return m.account == key
        if kind == "account_prefix":
            return bool(key) and m.account.startswith(key)
        if kind == "treasury":
            return c.treasury and (key is None or m.account == key)
        if kind == "personnel":
            return c.personnel
        if kind == "chiffre_affaires":
            return c.revenue
        if kind == "total_charges":
            return c.nature == "expense"
        if kind == "total_produits":
            return c.nature == "income"
        grp, nat = kind.split("_")[1].upper(), "income" if kind.startswith("produits") else "expense"
        return c.group == grp and c.nature == nat

    if kind == "partner":
        entry_keys = {m.entry_key for m in ctx["movs"] if m.third_party == key and st.in_range(m, rng)}
        lines = [m for m in ctx["movs"] if m.entry_key in entry_keys and st.in_range(m, rng)]
    elif kind == "treasury":
        lines = [m for m in ctx["movs"] if keep(m) and (m.is_opening or m.entry_date <= rng[1])]
    else:
        lines = [m for m in ctx["movs"] if st.in_range(m, rng) and keep(m)]
    lines.sort(key=lambda m: (m.entry_date, m.journal or "", m.number or "", m.account))
    by_acc: dict[str, dict] = {}
    for m in lines:
        a = by_acc.setdefault(
            m.account,
            {
                "account": m.account,
                "label": (cls.get(m.account) or st.AccountClass()).label,
                "rubric": (cls.get(m.account) or st.AccountClass()).rubric_label,
                "debit": Decimal(0),
                "credit": Decimal(0),
            },
        )
        a["debit"] += m.debit
        a["credit"] += m.credit
    page = lines[offset : offset + limit]
    masked = 0

    def visible(m: st.Movement) -> bool:
        return payroll_detail or not (cls.get(m.account) or st.AccountClass()).personnel

    for m in page:
        masked += not visible(m)
    return {
        "masked_payroll_lines": masked,
        "kind": kind,
        "key": key,
        "source": ctx["source"],
        "period": {"from": rng[0], "to": rng[1]},
        "total_lines": len(lines),
        "accounts": sorted(by_acc.values(), key=lambda a: a["account"]),
        "lines": [
            {
                "date": m.entry_date,
                "journal": m.journal,
                "number": m.number,
                "piece": m.piece,
                "label": m.label if visible(m) else "Ligne de rémunération (accès restreint)",
                "account": m.account,
                "third_party": m.third_party_label if visible(m) else None,
                "debit": m.debit,
                "credit": m.credit,
                "opening": m.is_opening,
                "entry_id": m.entry_key if ctx["source"] == "native" else None,
                "ledger_line_id": m.line_ref if ctx["source"] == "imported" else None,
            }
            for m in page
        ],
    }


# ====================================================================== trésorerie, masse salariale
def treasury(
    db: Session,
    company: Company,
    fy: FiscalYear,
    *,
    view: str = "year",
    month: int | None = None,
    d_from: date | None = None,
    d_to: date | None = None,
    source: str = "auto",
) -> dict:
    ctx = _context(db, company, fy, source)
    rng = period(fy, view, month, d_from, d_to)
    base = {
        "source": ctx["source"],
        "source_notes": ctx["notes"],
        "watermark": ctx["wm"],
        "period": {"from": rng[0], "to": rng[1]},
        "currency": company.currency,
        "computed_at": datetime.now(UTC),
    }
    if ctx["source"] is None:
        return {**base, "available": False, "reason": "Aucune donnée validée pour l'exercice."}
    if not any(c.treasury for c in ctx["cls"].values()):
        return {
            **base,
            "available": False,
            "reason": "Aucun compte de trésorerie identifié (concepts de trésorerie du référentiel).",
        }
    t = st.treasury(ctx["movs"], ctx["cls"], rng)
    # banque / caisse : d'après le compte de trésorerie déclaré sur les journaux de banque et de caisse de l'entreprise
    # (et non d'après le journal de chaque mouvement, qui peut être un journal d'opérations diverses)
    kinds = {
        j.counterpart_account_number: j.journal_type
        for j in db.scalars(select(Journal).where(Journal.company_id == company.id, Journal.journal_type.in_(("bank", "cash"))))
        if j.counterpart_account_number
    }
    by_kind: dict[str, dict] = {}
    for a in t["accounts"]:
        a["kind"] = kinds.get(a["account"])
        k = by_kind.setdefault(a["kind"] or "unknown", {"opening": Decimal(0), "closing": Decimal(0)})
        k["opening"] += a["opening"]
        k["closing"] += a["closing"]
    t["by_kind"] = by_kind
    notes = []
    if t["by_kind"].get("unknown"):
        notes.append(
            "Banque et caisse sont distinguées par le compte de trésorerie déclaré sur les journaux de banque et de caisse ; "
            "les autres comptes de trésorerie sont présentés comme « non distingués »."
        )
    if ctx["source"] == "trial_balance":
        notes.append(
            "Balance : encaissements et décaissements = mouvements débit et crédit annuels des comptes de trésorerie, "
            "transferts internes non identifiables."
        )
    return {
        **base,
        "available": True,
        **t,
        "notes": notes,
        "forecast": {"available": False, "reason": "Aucune donnée prévisionnelle de trésorerie n'est enregistrée dans KOFINEX."},
        "conventions": [
            "Solde final = solde initial + encaissements − décaissements (contrôle affiché).",
            "Comptes de trésorerie : lignes des concepts trésorerie-actif et trésorerie-passif du référentiel.",
            "Écriture dont toutes les lignes portent sur la trésorerie : transfert interne, exclu des flux.",
        ],
    }


def payroll(
    db: Session,
    company: Company,
    fy: FiscalYear,
    *,
    view: str = "year",
    month: int | None = None,
    d_from: date | None = None,
    d_to: date | None = None,
    source: str = "auto",
) -> dict:
    ctx = _context(db, company, fy, source)
    rng = period(fy, view, month, d_from, d_to)
    base = {
        "source": ctx["source"],
        "source_notes": ctx["notes"],
        "watermark": ctx["wm"],
        "period": {"from": rng[0], "to": rng[1]},
        "currency": company.currency,
        "computed_at": datetime.now(UTC),
    }
    if ctx["source"] is None:
        return {**base, "available": False, "reason": "Aucune donnée validée pour l'exercice."}
    net = st.nets(ctx["movs"], rng)
    s = st.pl(net, ctx["cls"])
    p = st.payroll(net, ctx["cls"], s.chiffre_affaires or None)
    series = (
        None
        if ctx["source"] == "trial_balance"
        else [
            {
                "period": m["period"],
                "year": m["year"],
                "month": m["month"],
                "personnel": m["personnel"],
                "chiffre_affaires": m["chiffre_affaires"],
            }
            for m in st.monthly(ctx["movs"], ctx["cls"], fy.start_date, fy.end_date)
        ]
    )
    return {
        **base,
        "available": True,
        **p,
        "monthly": series,
        "individual": {
            "available": False,
            "reason": "Aucune donnée de paie détaillée par salarié dans KOFINEX (module Paie à venir) : "
            "seuls les montants agrégés par compte sont présentés.",
        },
        "headcount": {"available": False, "reason": "Effectif non disponible (aucune donnée RH)."},
        "conventions": [
            "Masse salariale = comptes rattachés au concept « charges de personnel » du référentiel.",
            "Brut, net, charges patronales et salariales : présentés par compte comptable ; leur distinction fine "
            "dépend du plan de comptes de l'entreprise.",
        ],
    }


# ====================================================================== suivi budgétaire alimenté par la source choisie
def budget_actuals(db: Session, company: Company, fy: FiscalYear, source: str = "auto"):
    """(balance annuelle, mouvements mensuels, source, notes) pour le moteur budgétaire du lot 5, depuis la source retenue."""
    ctx = _context(db, company, fy, source)
    if ctx["source"] in (None, "trial_balance"):
        return None, None, ctx
    from app.engines.management.actuals import BalanceRow

    rng = (fy.start_date, fy.end_date)
    net = st.nets(ctx["movs"], rng)
    balance = [BalanceRow(a, max(v, Decimal(0)), max(-v, Decimal(0))) for a, v in net.items()]
    months = st.fiscal_months(fy.start_date, fy.end_date)
    monthly: dict[str, dict[int, Decimal]] = {}
    for p, y, m in months:
        a, b = st.month_bounds(y, m)
        for acc, v in st.nets(ctx["movs"], (max(a, fy.start_date), min(b, fy.end_date))).items():
            monthly.setdefault(acc, {})[p] = v
    return balance, monthly, ctx


def elapsed_months(fy: FiscalYear, as_of: date | None = None) -> tuple[int, int]:
    months = st.fiscal_months(fy.start_date, fy.end_date)
    d = min(as_of or date.today(), fy.end_date)
    return sum(1 for _, y, m in months if date(y, m, 1) <= d), len(months)


def reference_budget(db: Session, fy: FiscalYear, budget_id: uuid.UUID | None) -> Budget | None:
    # tableau de bord budgétaire : budgets lus en charges et produits ; un budget d'investissement (réalisé sur les
    # mouvements des comptes de bilan, migration 0020) se suit dans la gestion budgétaire
    pl_kinds = select(BudgetKind.key).where(BudgetKind.actual_basis == "balance")
    if budget_id:
        b = db.get(Budget, budget_id)
        if b is None or b.fiscal_year_id != fy.id:
            raise NotFound("Budget introuvable")
        if b.budget_kind not in set(db.scalars(pl_kinds)):
            raise AccountingInvalid("Le tableau de bord budgétaire porte sur les budgets de charges et de produits : "
                                    "un budget d'investissement se suit dans la gestion budgétaire.")
        return b
    cands = list(
        db.scalars(select(Budget).where(Budget.fiscal_year_id == fy.id, Budget.status != "archived", Budget.scenario == "budget",
                                        Budget.budget_kind.in_(pl_kinds)))
    )
    order = {"approved": 3, "submitted": 2, "draft": 1}
    return sorted(cands, key=lambda b: (order.get(b.status, 0), b.version), reverse=True)[0] if cands else None


def _chain(db: Session, b: Budget) -> list[Budget]:
    chain, cur = [b], b
    while cur.source_budget_id:
        cur = db.get(Budget, cur.source_budget_id)
        if cur is None or cur.fiscal_year_id != b.fiscal_year_id:
            break
        chain.append(cur)
    return list(reversed(chain))


def budget_dashboard(
    db: Session,
    company: Company,
    fy: FiscalYear,
    *,
    budget_id: uuid.UUID | None = None,
    source: str = "auto",
    thresholds: st.Thresholds | None = None,
    as_of: date | None = None,
) -> dict:
    b = reference_budget(db, fy, budget_id)
    wm = watermark(db, fy)
    if b is None:
        return {"available": False, "reason": "Aucun budget pour cet exercice.", "watermark": wm}
    t = mgmt.tracking(db, b, fy, source=source)
    rows = t["rows"]
    elapsed, total = elapsed_months(fy, as_of)
    th = thresholds or st.Thresholds()
    for r in rows:
        r["forecast"] = st.forecast(r, elapsed, total)
    chain = _chain(db, b)
    budgets_total = {}
    natures = mgmt.chart_natures(db, fy)
    for x in chain:
        lines = mgmt.budget_lines(db, x)
        budgets_total[x.id] = {"charge": Decimal(0), "produit": Decimal(0)}
        for ln in lines:
            if ln.account_number and not ln.cost_center_id:
                try:
                    nat = mgmt.prefix_nature(ln.account_number, natures)
                except Exception:  # noqa: BLE001, S112 — racine sans nature de gestion : déjà signalée par le suivi
                    continue
                budgets_total[x.id][nat] += ln.amount
    approved = [x for x in chain if x.status in ("approved", "archived")]
    totals = t["totals"]

    def kpi(nature: str) -> dict:
        rs = [r for r in rows if r["nature"] == nature and not r.get("cost_center_id")]
        if not rs:
            return {"available": False}
        actual = None if any(r["actual"] is None for r in rs) else sum((Decimal(str(r["actual"])) for r in rs), Decimal(0))
        budget = sum((Decimal(str(r["budget"])) for r in rs), Decimal(0))
        fc = [r["forecast"] for r in rs]
        pat = None if any(f.get("remaining_budget") is None for f in fc) else sum((f["remaining_budget"] for f in fc), Decimal(0))
        trend = None if any(f.get("trend") is None for f in fc) else sum((f["trend"] for f in fc), Decimal(0))
        return {
            "available": True,
            "initial": budgets_total[chain[0].id][nature] if chain else None,
            "revised": budgets_total[b.id][nature] if b.version > 1 else None,
            "approved": budgets_total[approved[-1].id][nature] if approved else None,
            "budget": budget,
            "actual": actual,
            "variance": (actual - budget) if actual is not None else None,
            "execution_rate": st.pct(actual, budget),
            "available_budget": (budget - actual) if actual is not None else None,
            "forecast_remaining_budget": pat,
            "forecast_trend": trend,
            "forecast_variance": (pat - budget) if pat is not None else None,
            "commitments": None,
        }

    centers = [r for r in rows if r.get("cost_center_id")]
    months = st.fiscal_months(fy.start_date, fy.end_date)
    return {
        "available": True,
        "watermark": wm,
        "computed_at": datetime.now(UTC),
        "source": t.get("source"),
        "source_notes": t.get("source_notes", []),
        "budget": {
            "id": b.id,
            "name": b.name,
            "version": b.version,
            "status": b.status,
            "versions": [{"id": x.id, "version": x.version, "status": x.status, "name": x.name} for x in chain],
        },
        "elapsed_months": elapsed,
        "total_months": total,
        "kpis": {
            "charges": kpi("charge"),
            "produits": kpi("produit"),
            "analytical_actual": sum((Decimal(str(r["actual"])) for r in centers if r["actual"] is not None), Decimal(0))
            if centers
            else None,
            "solde": totals.get("solde"),
        },
        "monthly": {
            "charges": st.budget_monthly(rows, months, "charge"),
            "produits": st.budget_monthly(rows, months, "produit"),
            "charges_cumulative": st.cumulate(st.budget_monthly(rows, months, "charge"), "charge"),
            "produits_cumulative": st.cumulate(st.budget_monthly(rows, months, "produit"), "produit"),
        },
        "alerts": st.budget_alerts(rows, elapsed, total, th),
        "tops": st.budget_tops(rows),
        "rows": rows,
        "warnings": t["warnings"],
        "thresholds": {k: getattr(th, k) for k in th.__dataclass_fields__},
        "commitments": {
            "available": False,
            "reason": "Les engagements (commandes) ne sont pas encore suivis dans KOFINEX : "
            "budget disponible = budget − réalisé.",
        },
        "conventions": t["conventions"]
        + [
            "Taux d'exécution = réalisé / budget × 100 ; non calculé si le budget est nul.",
            "Prévision à terminaison « budget restant » = réalisé cumulé + budget des mois restants ; "
            "« tendance » = réalisé cumulé / "
            "mois écoulés × mois de l'exercice. Ce sont des extrapolations, pas des montants comptabilisés.",
            "Tableau mensuel : un budget annuel (sans ventilation) est réparti également sur les mois pour la lecture.",
        ],
    }


def thresholds_for(db: Session, company_id: uuid.UUID) -> st.Thresholds:
    from app.models import ManagementAlertSettings

    s = db.get(ManagementAlertSettings, company_id)
    if s is None:
        return st.Thresholds()
    return replace(st.Thresholds(), **{k: getattr(s, k) for k in st.Thresholds.__dataclass_fields__})


def analysis(
    db: Session,
    company: Company,
    fy: FiscalYear,
    *,
    view: str = "year",
    month: int | None = None,
    d_from: date | None = None,
    d_to: date | None = None,
    source: str = "auto",
) -> dict:
    """Analyse et aide à la décision : points d'attention factuels à partir des tableaux de bord calculés."""
    th = thresholds_for(db, company.id)
    fin = financial(db, company, fy, view=view, month=month, d_from=d_from, d_to=d_to, compare=True, source=source)
    if not fin.get("available"):
        return {"available": False, "reason": fin.get("reason"), "watermark": fin["watermark"]}
    bud = budget_dashboard(db, company, fy, source=source, thresholds=th)
    tre = treasury(db, company, fy, view=view, month=month, d_from=d_from, d_to=d_to, source=source)
    items = st.insights(fin, bud.get("alerts") or [] if bud.get("available") else [], tre, None, th)
    return {
        "available": True,
        "watermark": fin["watermark"],
        "period": fin["period"],
        "source": fin["source"],
        "computed_at": datetime.now(UTC),
        "items": items,
        "reliability": fin["reliability"],
        "thresholds": {k: getattr(th, k) for k in th.__dataclass_fields__},
        "note": "Constats calculés à partir des indicateurs ; aucune cause n'est présumée. Les propositions de l'IA, si elle est "
        "activée, restent des propositions à examiner.",
    }
