"""Plan de trésorerie (phase 4 du correctif du contrôle de gestion ; docs/CONTROLE_GESTION.md § 12.5).

Prévision : rubriques et montants saisis ou calculés (pourcentage d'une autre rubrique, budget décalé d'un délai).
Réalisé : mouvements réels de trésorerie de la source retenue par le pilotage (écritures natives validées, grand livre
importé), affectés aux rubriques par le compte de contrepartie — aucune seconde saisie, aucune échéance simulée.
Les soldes, totaux et écarts sont recalculés à chaque demande par le moteur (Decimal) ; rien n'est stocké."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.errors import Conflict, NotFound
from app.engines.management import treasury_plan as tp
from app.engines.management.steering import fiscal_months
from app.models import Budget, BudgetLineRow, Company, FiscalYear, TreasuryAmount, TreasuryPlan, TreasuryRubric
from app.services.management import ManagementInvalid, jsonable

# Modèle de départ proposé (intitulés du cahier des charges et du classeur de référence, sans compte associé) :
# une proposition modifiable, pas une norme. [À VALIDER]
TEMPLATE = {
    "receipts": ["Ventes de marchandises", "Prestations de services", "Encaissements clients", "Produits financiers encaissés",
                 "Subventions reçues", "Apports", "Emprunts reçus", "Autres encaissements"],
    "disbursements": ["Achats de marchandises", "Achats de matières premières", "Achats de prestations", "Charges externes",
                      "Charges de personnel", "Impôts et taxes", "Charges financières", "Investissements",
                      "Remboursements d'emprunts", "Règlements fournisseurs", "Autres décaissements"],
}
SCENARIOS = ("initial", "updated")


# ------------------------------------------------------------------ accès
def plan(db: Session, company_id: uuid.UUID, plan_id: uuid.UUID) -> TreasuryPlan:
    p = db.get(TreasuryPlan, plan_id)
    if p is None or p.company_id != company_id:
        raise NotFound("Plan de trésorerie introuvable")
    return p


def rubrics(db: Session, p: TreasuryPlan) -> list[TreasuryRubric]:
    return list(db.scalars(select(TreasuryRubric).where(TreasuryRubric.plan_id == p.id)
                           .order_by(TreasuryRubric.section, TreasuryRubric.display_order, TreasuryRubric.label)))


def amounts(db: Session, p: TreasuryPlan, scenario: str) -> dict[str, list[Decimal]]:
    out: dict[str, list[Decimal]] = {}
    for a in db.scalars(select(TreasuryAmount).where(TreasuryAmount.plan_id == p.id, TreasuryAmount.scenario == scenario)):
        out.setdefault(str(a.rubric_id), [tp.ZERO] * 12)[a.period - 1] = a.amount
    return out


def _engine_rubrics(rs: list[TreasuryRubric]) -> list[tp.Rubric]:
    return [tp.Rubric(str(r.id), r.section, r.label, str(r.parent_id) if r.parent_id else None, r.code, r.display_order,
                      tuple(r.account_prefixes or ())) for r in rs]


def _draft(p: TreasuryPlan) -> None:
    if p.status != "draft":
        raise Conflict("Plan approuvé ou archivé : structure et prévision initiale figées.")


# ------------------------------------------------------------------ création et paramétrage
def create(db: Session, company: Company, fy: FiscalYear, user_id: uuid.UUID, *, name: str, opening_balance: Decimal,
           template: bool) -> TreasuryPlan:
    if db.scalar(select(TreasuryPlan.id).where(TreasuryPlan.fiscal_year_id == fy.id, TreasuryPlan.name == name)):
        raise Conflict(f"Un plan « {name} » existe déjà pour cet exercice.")
    p = TreasuryPlan(id=uuid.uuid4(), organization_id=company.organization_id, company_id=company.id, fiscal_year_id=fy.id,
                     name=name, currency=company.currency or "XOF", opening_balance=opening_balance, opening_source="manual",
                     created_by=user_id)
    db.add(p)
    db.flush()
    if template:
        for section, labels in TEMPLATE.items():
            for i, label in enumerate(labels):
                db.add(TreasuryRubric(id=uuid.uuid4(), organization_id=p.organization_id, company_id=p.company_id,
                                      plan_id=p.id, section=section, label=label, display_order=i, account_prefixes=[]))
        db.flush()
    return p


def update(db: Session, p: TreasuryPlan, *, name: str | None, notes: str | None, opening_balance: Decimal | None,
           opening_source: str | None) -> TreasuryPlan:
    if name is not None or opening_balance is not None:
        _draft(p)
    if name is not None:
        p.name = name
    if opening_balance is not None:
        p.opening_balance = opening_balance
        p.opening_source = opening_source or "manual"
    if notes is not None:
        p.notes = notes or None
    db.flush()
    return p


def replace_rubrics(db: Session, p: TreasuryPlan, items: list[dict]) -> None:
    """Remplace la structure d'un brouillon. `items` : clé locale, clé du parent, section, code, intitulé, ordre, comptes
    associés, modalité (et clé de la rubrique de base, taux, budget, délai). Les montants des rubriques supprimées le sont
    aussi (prévision initiale d'un brouillon)."""
    _draft(p)
    keys = [it["key"] for it in items]
    if len(set(keys)) != len(keys):
        raise ManagementInvalid("Clés de rubriques en double.")
    known = set(keys)
    for it in items:
        for ref in ("parent_key", "base_key"):
            if it.get(ref) and it[ref] not in known:
                raise ManagementInvalid(f"Rubrique « {it['label']} » : référence inconnue ({it[ref]}).")
    existing = {str(r.id) for r in rubrics(db, p)}
    db.execute(delete(TreasuryAmount).where(TreasuryAmount.plan_id == p.id))
    db.execute(delete(TreasuryRubric).where(TreasuryRubric.plan_id == p.id))
    db.flush()
    ids = {k: (uuid.UUID(k) if k in existing else uuid.uuid4()) for k in keys}
    pending = list(items)
    # parents d'abord (contrôle de la base : parent existant), puis rubriques de base renseignées en second passage
    for it in sorted(pending, key=lambda x: x.get("parent_key") is not None):
        db.add(TreasuryRubric(
            id=ids[it["key"]], organization_id=p.organization_id, company_id=p.company_id, plan_id=p.id,
            parent_id=ids[it["parent_key"]] if it.get("parent_key") else None, section=it["section"], code=it.get("code"),
            label=it["label"], display_order=it.get("order", 0), account_prefixes=it.get("prefixes", []),
            method="manual", delay_months=it.get("delay_months", 0), cost_center_id=it.get("cost_center_id")))
        db.flush()
    for it in pending:
        if it.get("method", "manual") != "manual":
            r = db.get(TreasuryRubric, ids[it["key"]])
            r.method, r.rate, r.budget_id = it["method"], it.get("rate"), it.get("budget_id")
            r.base_rubric_id = ids[it["base_key"]] if it.get("base_key") else None
    db.flush()


def set_amounts(db: Session, p: TreasuryPlan, scenario: str, entries: list[tuple[uuid.UUID, int, Decimal]],
                rubric_ids: set[uuid.UUID] | None = None) -> None:
    """Remplace les montants d'un scénario (toutes rubriques, ou seulement `rubric_ids`)."""
    if scenario == "initial":
        _draft(p)
    elif p.status != "approved":
        raise Conflict("La prévision actualisée se saisit une fois le plan approuvé.")
    leaf = {r.id for r in rubrics(db, p)} - {r.parent_id for r in rubrics(db, p) if r.parent_id}
    for rid, period, amount in entries:
        if rid not in leaf:
            raise ManagementInvalid("Montant sur une rubrique inconnue ou qui a des sous-rubriques.")
        if not 1 <= period <= 12 or amount < 0:
            raise ManagementInvalid("Mois de 1 à 12 et montant positif ou nul (le sens vient de la section).")
    stmt = delete(TreasuryAmount).where(TreasuryAmount.plan_id == p.id, TreasuryAmount.scenario == scenario)
    if rubric_ids is not None:
        stmt = stmt.where(TreasuryAmount.rubric_id.in_(rubric_ids))
    db.execute(stmt)
    for rid, period, amount in entries:
        if amount:
            db.add(TreasuryAmount(id=uuid.uuid4(), organization_id=p.organization_id, company_id=p.company_id, plan_id=p.id,
                                  rubric_id=rid, scenario=scenario, period=period, amount=amount))
    db.flush()


def calculate(db: Session, p: TreasuryPlan, rubric_id: uuid.UUID, scenario: str) -> dict:
    """Applique la modalité de prévision d'une rubrique : pourcentage d'une autre rubrique (taux saisi), ou budget décalé
    du délai saisi (règle de calendrier). Les montants calculés remplacent ceux du scénario pour cette rubrique."""
    r = db.get(TreasuryRubric, rubric_id)
    if r is None or r.plan_id != p.id:
        raise NotFound("Rubrique introuvable")
    if r.method == "percent_of":
        rs = rubrics(db, p)
        plan_now = tp.compute(_engine_rubrics(rs), amounts(db, p, scenario), Decimal(0))
        base = next(x["months"] for x in plan_now.rows if x["id"] == str(r.base_rubric_id))
        months, beyond, basis = tp.percent_of(base, r.rate), Decimal(0), f"{r.rate} % de la rubrique de base"
    elif r.method == "from_budget":
        prefixes = tuple(r.account_prefixes or ())
        if not prefixes:
            raise ManagementInvalid("Budget décalé : indiquez les comptes associés de la rubrique "
                                    "(comptes budgétés à reprendre).")
        b = db.get(Budget, r.budget_id)
        by_period: dict[int, Decimal] = {}
        for ln in db.scalars(select(BudgetLineRow).where(BudgetLineRow.budget_id == b.id)):
            if ln.account_number and ln.account_number.startswith(prefixes):
                by_period[ln.period] = by_period.get(ln.period, Decimal(0)) + ln.amount
        try:
            months, beyond = tp.shift(by_period, r.delay_months)
        except tp.TreasuryError as exc:
            raise ManagementInvalid(str(exc)) from exc
        basis = f"budget « {b.name} » v{b.version}, délai de {r.delay_months} mois"
    else:
        raise ManagementInvalid("Rubrique en saisie manuelle : rien à calculer.")
    if any(v < 0 for v in months):
        raise ManagementInvalid("Calcul : montant négatif (vérifier la rubrique de base ou le budget).")
    set_amounts(db, p, scenario, [(r.id, i + 1, v) for i, v in enumerate(months)], {r.id})
    return {"rubric_id": r.id, "months": months, "beyond_fiscal_year": beyond, "basis": basis}


def transition(db: Session, p: TreasuryPlan, to: str) -> TreasuryPlan:
    allowed = {("draft", "approved"), ("draft", "archived"), ("approved", "archived")}
    if (p.status, to) not in allowed:
        raise Conflict(f"Transition impossible : {p.status} → {to}")
    p.status = to
    db.flush()
    db.refresh(p)
    return p


# ------------------------------------------------------------------ réalisé (source du pilotage)
def _cash_lines(db: Session, company: Company, fy: FiscalYear, source: str) -> tuple[list[tp.CashLine], dict]:
    from app.services import steering

    ctx = steering._context(db, company, fy, source)          # même source et même classement que la trésorerie réalisée
    rank = {(y, m): p for p, y, m in fiscal_months(fy.start_date, fy.end_date)}
    out = []
    for mv in ctx["movs"]:
        p = rank.get((mv.entry_date.year, mv.entry_date.month))
        if mv.is_opening or p is None or not (fy.start_date <= mv.entry_date <= fy.end_date):
            continue
        c = ctx["cls"].get(mv.account)
        out.append(tp.CashLine(mv.entry_key, mv.account, p, mv.debit, mv.credit, bool(c and c.treasury)))
    return out, ctx


def opening_proposal(db: Session, company: Company, fy: FiscalYear, source: str = "auto") -> dict:
    """Solde de trésorerie au début de l'exercice d'après la comptabilité (à-nouveaux et mouvements antérieurs)."""
    from app.services import steering

    t = steering.treasury(db, company, fy, source=source)
    if not t.get("available", True) or "opening" not in t:
        return {"available": False, "reason": t.get("reason", "Trésorerie réalisée indisponible."), "source": t.get("source")}
    return jsonable({"available": True, "opening_balance": t["opening"], "source": t["source"],
                     "accounts": [{"account": a["account"], "opening": a["opening"]} for a in t["accounts"]]})


# ------------------------------------------------------------------ vue calculée
def _months_label(fy: FiscalYear) -> list[str]:
    names = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]
    return [f"{names[m - 1]} {str(y)[2:]}" for _p, y, m in fiscal_months(fy.start_date, fy.end_date)][:12]


def view(db: Session, company: Company, p: TreasuryPlan, *, scenario: str | None = None, source: str = "auto",
         as_of: date | None = None) -> dict:
    fy = db.get(FiscalYear, p.fiscal_year_id)
    scenario = scenario or ("updated" if p.status != "draft" else "initial")
    if scenario not in SCENARIOS:
        raise ManagementInvalid("Scénario : initial ou updated.")
    rs = rubrics(db, p)
    er = _engine_rubrics(rs)
    try:
        plan_ = tp.compute(er, amounts(db, p, scenario), p.opening_balance)
    except tp.TreasuryError as exc:
        raise ManagementInvalid(str(exc)) from exc
    # réalisé jusqu'au mois de `as_of` inclus (par défaut aujourd'hui) ; au-delà : « — »
    as_of = as_of or date.today()
    closed = sum(1 for _p, y, m in fiscal_months(fy.start_date, fy.end_date) if (y, m) <= (as_of.year, as_of.month))
    lines, ctx = _cash_lines(db, company, fy, source)
    act = tp.actuals(lines, er)
    by = tp.rollup(er, act["by_rubric"])

    def cut(series: list[Decimal]) -> list[Decimal | None]:
        return [v if i < closed else None for i, v in enumerate(series)]

    rows = []
    for row in plan_.rows:
        a = cut(by.get(row["id"], [tp.ZERO] * 12))
        rows.append({**row, "actual": a, "variance": tp.variance(row["months"], a),
                     "actual_total": sum((v for v in a if v is not None), tp.ZERO)})
    actual_net = cut([act["receipts"][i] - act["disbursements"][i] for i in range(12)])
    return jsonable({
        "plan": out(p), "scenario": scenario, "months": _months_label(fy), "as_of": as_of, "closed_months": closed,
        "rows": rows,
        "totals": {"receipts": plan_.receipts, "disbursements": plan_.disbursements, "net": plan_.net,
                   "opening": plan_.opening, "closing": plan_.closing, "annual": plan_.annual},
        "negative_months": plan_.negative_months, "financing_need": plan_.financing_need,
        "actual": {"source": ctx["source"], "source_notes": ctx["notes"], "receipts": cut(act["receipts"]),
                   "disbursements": cut(act["disbursements"]), "net": actual_net,
                   "unassigned": {k: cut(v) for k, v in act["unassigned"].items()}, "check": act["check"],
                   "variance_receipts": tp.variance(plan_.receipts, cut(act["receipts"])),
                   "variance_disbursements": tp.variance(plan_.disbursements, cut(act["disbursements"]))},
        "conventions": [
            "Flux net = encaissements (A) − décaissements (B) ; solde de fin = solde de début + flux net ; "
            "le solde de début d'un mois est le solde de fin du mois précédent.",
            "Réalisé : mouvements réels de trésorerie (hors transferts internes), affectés aux rubriques par le compte "
            "de contrepartie ; une charge n'est pas un décaissement tant qu'elle n'est pas réglée.",
            "Écart = réalisé − prévision ; taux de réalisation = réalisé / prévision × 100.",
        ],
    })


def rolling(db: Session, company: Company, p: TreasuryPlan, *, as_of: date | None = None, source: str = "auto") -> dict:
    """Prévision glissante sur douze mois à partir du mois de `as_of` : solde de départ = solde initial du plan +
    réalisé des mois clos ; mois de l'exercice : prévision actualisée (initiale pour un brouillon) ; mois suivants :
    plan approuvé de l'exercice suivant s'il existe, sinon aucune valeur."""
    fy = db.get(FiscalYear, p.fiscal_year_id)
    as_of = as_of or date.today()
    v = view(db, company, p, source=source, as_of=as_of)
    months_fy = fiscal_months(fy.start_date, fy.end_date)
    start = next((i for i, (_p, y, m) in enumerate(months_fy) if (y, m) >= (as_of.year, as_of.month)), len(months_fy))
    past_actual = [Decimal(str(x)) for x in v["actual"]["net"][:start] if x is not None]
    opening = p.opening_balance + sum(past_actual, Decimal(0))
    forecast_net = [Decimal(str(x)) for x in v["totals"]["net"]][start:12]
    labels = v["months"][start:12]
    nxt = db.scalar(select(FiscalYear).where(FiscalYear.company_id == fy.company_id, FiscalYear.start_date > fy.end_date)
                    .order_by(FiscalYear.start_date))
    next_plan = None
    if nxt is not None:
        next_plan = db.scalar(select(TreasuryPlan).where(TreasuryPlan.fiscal_year_id == nxt.id, TreasuryPlan.status == "approved")
                              .order_by(TreasuryPlan.approved_at.desc()))
    while len(forecast_net) < 12:
        k = len(forecast_net) - (12 - start)
        if next_plan is not None:
            nv = view(db, company, next_plan, scenario="updated", source=source, as_of=nxt.start_date)
            forecast_net += [Decimal(str(x)) for x in nv["totals"]["net"]][: 12 - len(forecast_net)]
            labels += nv["months"][: 12 - len(labels)]
            next_plan = None
            continue
        forecast_net.append(None)
        labels.append(f"+{k + 1}")
    r = tp.rolling(opening, [None] * 12, forecast_net)
    return jsonable({"plan": out(p), "as_of": as_of, "start_opening": opening, "labels": labels, **r,
                     "notes": ["Solde de départ : solde initial du plan + réalisé des mois clos de l'exercice.",
                               *([] if r["complete"] else
                                 ["Au-delà du dernier plan approuvé : aucune prévision (aucune valeur inventée)."])]})


# ------------------------------------------------------------------ sortie et exports
def out(p: TreasuryPlan) -> dict:
    return {k: getattr(p, k) for k in ("id", "fiscal_year_id", "name", "currency", "opening_balance", "opening_source", "status",
                                       "notes", "approved_by", "approved_at", "created_by", "created_at")}


def rubric_out(r: TreasuryRubric) -> dict:
    return {"id": r.id, "parent_id": r.parent_id, "section": r.section, "code": r.code, "label": r.label,
            "order": r.display_order, "prefixes": list(r.account_prefixes or []),
            "method": r.method, "base_rubric_id": r.base_rubric_id, "rate": r.rate,
            "budget_id": r.budget_id, "delay_months": r.delay_months, "cost_center_id": r.cost_center_id}


def document(db: Session, company: Company, p: TreasuryPlan, scenario: str | None, source: str,
             author: str | None = None) -> tuple[dict, dict]:
    """Document neutre du lot 11 (rendu Excel et PDF par `engines/reporting/render`)."""
    from app.engines.reporting import document as d

    v = view(db, company, p, scenario=scenario, source=source)
    fy = db.get(FiscalYear, p.fiscal_year_id)
    doc = d.new("treasury_plan", f"Plan de trésorerie — {p.name}", entity=company.name, period=fy.label,
                subtitle=f"Prévision {'actualisée' if v['scenario'] == 'updated' else 'initiale'} · {p.currency}")
    cols = [("code", "Comptes", "text"), ("label", "Intitulés", "text"),
            *[(f"m{i}", lbl, "amount") for i, lbl in enumerate(v["months"])], ("total", "Total", "amount")]

    def line(code, label, months, total):
        return {"code": code or "", "label": label, **{f"m{i}": x for i, x in enumerate(months)}, "total": total}

    rows = []
    for section, title, key in (("receipts", "A. ENCAISSEMENTS", "receipts"),
                                ("disbursements", "B. DÉCAISSEMENTS", "disbursements")):
        rows.append(line("", title, [None] * 12, None))
        for r in v["rows"]:
            if r["section"] == section:
                rows.append(line(r["code"], ("    " if r["level"] else "") + r["label"], r["months"], r["total"]))
        rows.append(line("", f"Total {title[0]}", v["totals"][key], v["totals"]["annual"][key]))
    t = v["totals"]
    rows += [line("", "Solde au début du mois", t["opening"], None), line("", "Flux net (A − B)", t["net"], t["annual"]["net"]),
             line("", "Solde à la fin du mois", t["closing"], None)]
    blocks = d.section(doc, "Plan mensuel")
    d.add(blocks, d.table(cols, rows))
    if v["negative_months"]:
        doc["notices"].append(d.notice(f"Solde négatif prévu ({len(v['negative_months'])} mois) ; besoin de financement : "
                                       f"{d.fmt_number(v['financing_need'])} {p.currency}."))
    meta = {"generated_at": datetime.now(UTC), "generated_by": author, "data_sha256": d.data_digest(doc)}
    return doc, meta
