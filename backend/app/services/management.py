"""Contrôle de gestion : chargement des données (balance, plan, saisies) et appel des moteurs."""

from __future__ import annotations

import dataclasses
import hashlib
import json
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.engines.management import ManagementError, q2
from app.engines.management.actuals import BalanceRow, CostEntry, balance_amount, prefix_nature  # noqa: F401
from app.services import ledger as ledger_svc
from app.engines.management.budget import BudgetLine, Tracking, project_from_actuals, track
from app.engines.management.costing import FullCostResult, full_cost
from app.engines.management.cvp import cvp
from app.engines.management.forecast import cagr, linear_trend
from app.engines.management.standards import standard_variances
from app.models import (
    Budget,
    BudgetLineRow,
    ChartAccount,
    Company,
    CostCenter,
    CostEntryRow,
    CostingModel,
    FiscalYear,
    ImportJob,
    TrialBalanceEntry,
)


class ManagementInvalid(AppError):
    status_code = 422
    code = "management_invalid"


def engine_call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except ManagementError as exc:
        raise ManagementInvalid(str(exc)) from exc


# ------------------------------------------------------------------ sérialisation
def jsonable(v):
    """Decimal → texte exact (jamais de flottant), dates ISO, dataclasses et propriétés utiles."""
    if isinstance(v, Decimal):
        return format(v.normalize(), "f")
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, uuid.UUID):
        return str(v)
    if dataclasses.is_dataclass(v):
        return {f.name: jsonable(getattr(v, f.name)) for f in dataclasses.fields(v)}
    if isinstance(v, dict):
        return {str(k): jsonable(x) for k, x in v.items()}
    if isinstance(v, (list, tuple, set)):
        return [jsonable(x) for x in v]
    return v


def params_hash(params: dict) -> str:
    return hashlib.sha256(json.dumps(params, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


# ------------------------------------------------------------------ données de l'exercice
def framework_version_id(db: Session, fy: FiscalYear) -> uuid.UUID | None:
    if fy.framework_version_id:
        return fy.framework_version_id
    if fy.active_import_job_id:
        job = db.get(ImportJob, fy.active_import_job_id)
        if job and job.framework_version_id:
            return job.framework_version_id
    return db.execute(text("SELECT public.applicable_framework_version(:c, :d)"),
                      {"c": fy.company_id, "d": fy.end_date}).scalar()


CHART_NATURE = {"expense": "charge", "income": "produit"}


def chart_natures(db: Session, fy: FiscalYear) -> dict[str, str | None]:
    vid = framework_version_id(db, fy)
    if vid is None:
        raise ManagementInvalid("Aucune version publiée du référentiel pour cet exercice : la nature des comptes "
                                "(charge / produit) ne peut pas être déterminée.")
    # Le plan de comptes enregistre « expense » / « income » ; les moteurs du lot 5 raisonnent en « charge » / « produit ».
    return {a: CHART_NATURE.get(n, n) for a, n in db.execute(select(ChartAccount.account_number, ChartAccount.nature)
                                                             .where(ChartAccount.framework_version_id == vid)).all()}


def balance_rows(db: Session, fy: FiscalYear) -> list[BalanceRow] | None:
    if fy.active_import_job_id is None:
        return None
    return [BalanceRow(r.account_number, r.closing_debit, r.closing_credit)
            for r in db.scalars(select(TrialBalanceEntry)
                                .where(TrialBalanceEntry.import_job_id == fy.active_import_job_id))]


def require_balance(db: Session, fy: FiscalYear) -> list[BalanceRow]:
    rows = balance_rows(db, fy)
    if rows is None:
        raise ManagementInvalid(f"Aucune balance validée pour l'exercice {fy.label} : importez et validez la balance.")
    return rows


# ------------------------------------------------------------------ budgets
def budget_lines(db: Session, budget: Budget) -> list[BudgetLineRow]:
    return list(db.scalars(select(BudgetLineRow).where(BudgetLineRow.budget_id == budget.id)
                           .order_by(BudgetLineRow.account_number, BudgetLineRow.label, BudgetLineRow.period)))


def tracking(db: Session, budget: Budget, fy: FiscalYear, source: str | None = None) -> dict:
    """Suivi budgétaire. `source` (facultatif) : réalisé tiré de la couche de pilotage (écritures natives, grand livre
    importé — `services/steering.py`) ; par défaut, comportement du lot 5 (balance importée et grand livre importé)."""
    lines = budget_lines(db, budget)
    balance, ledger_monthly, src, src_notes = balance_rows(db, fy), None, "trial_balance", []
    if fy.active_ledger_import_job_id:
        ledger_monthly = ledger_svc.monthly_net(db, fy)
    if source is not None:
        from app.services import steering

        b2, m2, ctx = steering.budget_actuals(db, db.get(Company, budget.company_id), fy, source)
        src, src_notes = ctx["source"], ctx["notes"]
        if b2 is not None:
            balance, ledger_monthly = b2, m2
    centers = list(db.scalars(select(CostCenter).where(CostCenter.company_id == budget.company_id)))
    entries = [CostEntry(str(e.cost_center_id), e.account_number, e.entry_date, e.amount)
               for e in db.scalars(select(CostEntryRow).where(CostEntryRow.fiscal_year_id == fy.id))]
    t: Tracking = engine_call(
        track, [BudgetLine(ln.account_number, str(ln.cost_center_id) if ln.cost_center_id else None, ln.label,
                           ln.period, ln.amount) for ln in lines],
        chart_natures=chart_natures(db, fy), balance=balance, cost_entries=entries,
        center_parent={str(c.id): str(c.parent_id) if c.parent_id else None for c in centers},
        fy_start=fy.start_date, center_names={str(c.id): f"{c.code} — {c.name}" for c in centers},
        ledger_monthly=ledger_monthly)
    return {
        "source": src, "source_notes": src_notes,
        "budget_id": budget.id, "fiscal_year": fy.label, "balance_import_job_id": fy.active_import_job_id,
        "ledger_import_job_id": fy.active_ledger_import_job_id,
        "rows": [{**jsonable(r), "account_prefix": r.key[0], "cost_center_id": r.key[1]} for r in t.rows],
        "totals": jsonable(t.totals), "warnings": t.warnings,
        "conventions": [
            "Réalisé d'une charge = solde débiteur net des comptes de la racine ; d'un produit = solde créditeur net.",
            "Écart = réalisé − budget. Charge : favorable si le réalisé est inférieur au budget ; "
            "produit : favorable s'il est supérieur.",
            "Lignes par centre : réalisé = saisies analytiques du centre et de ses sous-centres.",
        ],
    }


def projected_lines(db: Session, source_fy: FiscalYear, items: list[tuple[str, str, Decimal]], spread: str,
                    target_fy: FiscalYear) -> list[BudgetLine]:
    natures = chart_natures(db, target_fy)
    return engine_call(project_from_actuals, require_balance(db, source_fy), items, natures, spread)


# ------------------------------------------------------------------ modèles de coûts
def compute_model(db: Session, model: CostingModel, fy: FiscalYear) -> dict:
    params = model.parameters or {}
    if model.model_type == "standard_cost":
        res = engine_call(standard_variances, params)
        out = jsonable(res)
    else:
        bal = require_balance(db, fy)
        natures = chart_natures(db, fy)
        if model.model_type == "full_cost":
            r: FullCostResult = engine_call(full_cost, params, bal, natures)
            # calcul exact (34 chiffres) ; restitution : montants au centime, coûts unitaires à 6 décimales
            c2 = lambda v: None if v is None else q2(v)  # noqa: E731
            u6 = lambda v: None if v is None else v.quantize(Decimal("0.000001"))  # noqa: E731
            centers = []
            for c in r.centers:
                c = dict(c)
                for k in ("primary", "total", "imputed"):
                    if k in c:
                        c[k] = c2(c[k])
                if "cost_per_unit" in c:
                    c["cost_per_unit"] = u6(c["cost_per_unit"])
                centers.append(c)
            out = {
                "charges": jsonable([{**c, "amount": c2(c["amount"])} for c in r.charges]),
                "total_balance_charges": jsonable(q2(r.total_balance_charges)),
                "incorporated_from_balance": jsonable(q2(r.incorporated_from_balance)),
                "supplementary": jsonable(q2(r.supplementary)),
                "non_incorporated": jsonable(q2(r.non_incorporated)),
                "total_incorporated": jsonable(q2(r.total_incorporated)),
                "centers": jsonable(centers),
                "objects": [{"code": o.code, "name": o.name, "quantity": jsonable(o.quantity),
                             "sold_quantity": jsonable(o.sold_quantity), "direct": jsonable(c2(o.direct)),
                             "indirect": jsonable(c2(o.indirect)), "cost": jsonable(c2(o.cost)),
                             "unit_cost": jsonable(u6(o.unit_cost)), "cost_of_sales": jsonable(c2(o.cost_of_sales)),
                             "revenue": jsonable(c2(o.revenue)), "margin": jsonable(c2(o.margin)),
                             "unsold_cost": jsonable(c2(o.cost - o.cost_of_sales) if o.cost_of_sales is not None else None),
                             "detail": jsonable([{**d, "amount": c2(d["amount"])} for d in o.detail])}
                            for o in r.objects],
                "imputation_differences": jsonable({k: c2(v) for k, v in r.imputation_differences.items()}),
                "imputation_differences_total": jsonable(q2(sum(r.imputation_differences.values(), Decimal(0)))),
                "analytical_result": jsonable(c2(r.analytical_result)),
                "check_difference": jsonable(r.check_difference),
                "check_passed": abs(r.check_difference) < Decimal("0.000001"),
                "rounding_note": "Montants arrondis au centime pour la restitution ; calcul conduit à 34 chiffres.",
            }
        else:
            out = jsonable(engine_call(cvp, params, bal, natures, fy.start_date, fy.end_date))
    out["_meta"] = {"parameters_sha256": params_hash(params), "balance_import_job_id": jsonable(fy.active_import_job_id)}
    return out


def results_are_current(model: CostingModel, fy: FiscalYear) -> bool:
    meta = (model.results or {}).get("_meta") or {}
    if meta.get("parameters_sha256") != params_hash(model.parameters or {}):
        return False
    if model.model_type != "standard_cost" and meta.get("balance_import_job_id") != jsonable(fy.active_import_job_id):
        return False
    return True


# ------------------------------------------------------------------ projections
def account_series(db: Session, company: Company, prefix: str, horizon: int) -> dict:
    years = [fy for fy in db.scalars(select(FiscalYear).where(FiscalYear.company_id == company.id)
                                     .order_by(FiscalYear.end_date)) if fy.active_import_job_id]
    if not years:
        raise ManagementInvalid("Aucun exercice avec balance validée.")
    natures = chart_natures(db, years[-1])
    nature = engine_call(prefix_nature, prefix, natures)
    points = [{"fiscal_year_id": fy.id, "label": fy.label,
               "value": balance_amount(require_balance(db, fy), prefix, nature)} for fy in years]
    values = [p["value"] for p in points]
    methods = {}
    for name, fn in (("linear_trend", linear_trend), ("cagr", cagr)):
        try:
            res = fn(values, horizon)
            res["projections"] = [q2(v) for v in res["projections"]]   # restitution au centime
            methods[name] = jsonable(res)
        except ManagementError as exc:
            methods[name] = {"unavailable": str(exc)}
    return {"prefix": prefix, "nature": nature, "points": jsonable(points), "horizon": horizon, "methods": methods,
            "notes": ["Projection statistique par extrapolation des réalisés : ce n'est pas une prévision validée.",
                      "Exercices de durées différentes : les montants ne sont pas ramenés à 12 mois."]}


# ------------------------------------------------------------------ tableau de bord
def _latest_model(db: Session, fy: FiscalYear, model_type: str) -> CostingModel | None:
    models = [m for m in db.scalars(select(CostingModel).where(CostingModel.fiscal_year_id == fy.id,
                                                               CostingModel.model_type == model_type))
              if m.results]
    if not models:
        return None
    # priorité au modèle validé, puis au calcul le plus récent
    return sorted(models, key=lambda m: (m.status == "validated", m.computed_at or m.created_at), reverse=True)[0]


def _model_head(m: CostingModel, fy: FiscalYear) -> dict:
    return {"model_id": m.id, "name": m.name, "version": m.version, "status": m.status,
            "computed_at": jsonable(m.computed_at), "results_current": results_are_current(m, fy)}


def dashboard(db: Session, fy: FiscalYear) -> dict:
    out: dict = {"fiscal_year": {"id": fy.id, "label": fy.label, "start_date": jsonable(fy.start_date),
                                 "end_date": jsonable(fy.end_date)},
                 "has_balance": fy.active_import_job_id is not None, "budget": None, "forecast": None,
                 "cost_centers": None, "full_cost": None, "cvp": None, "standard_cost": None, "notes": []}

    budgets = list(db.scalars(select(Budget).where(Budget.fiscal_year_id == fy.id, Budget.status != "archived")))
    order = {"approved": 3, "submitted": 2, "draft": 1}
    for scenario, key in (("budget", "budget"), ("forecast", "forecast")):
        cands = [b for b in budgets if b.scenario == scenario]
        if not cands:
            continue
        ref = sorted(cands, key=lambda b: (order.get(b.status, 0), b.version), reverse=True)[0]
        try:
            t = tracking(db, ref, fy)
        except ManagementInvalid as exc:
            out["notes"].append(f"{ref.name} : {exc.message}")
            continue
        rows = [r for r in t["rows"] if r["variance"] is not None]
        worst = sorted([r for r in rows if r["favorable"] is False],
                       key=lambda r: abs(Decimal(r["variance"])), reverse=True)[:5]
        out[key] = {"budget_id": ref.id, "name": ref.name, "version": ref.version, "status": ref.status,
                    "totals": t["totals"], "lines": len(t["rows"]), "warnings": t["warnings"],
                    "unfavorable": [{k: r[k] for k in ("label", "account_prefix", "cost_center_id", "nature", "budget",
                                                       "actual", "variance", "realization_pct")} for r in worst],
                    "favorable_count": sum(1 for r in rows if r["favorable"] is True),
                    "unfavorable_count": sum(1 for r in rows if r["favorable"] is False)}

    centers = {c.id: c for c in db.scalars(select(CostCenter).where(CostCenter.company_id == fy.company_id))}
    entries = list(db.scalars(select(CostEntryRow).where(CostEntryRow.fiscal_year_id == fy.id)))
    if entries:
        by_center: dict = {}
        by_month: dict[int, Decimal] = {}
        for e in entries:
            c = centers.get(e.cost_center_id)
            k = str(e.cost_center_id)
            by_center.setdefault(k, {"cost_center_id": k, "label": f"{c.code} — {c.name}" if c else k,
                                     "amount": Decimal(0)})["amount"] += e.amount
            p = (e.entry_date.year - fy.start_date.year) * 12 + e.entry_date.month - fy.start_date.month + 1
            by_month[p] = by_month.get(p, Decimal(0)) + e.amount
        out["cost_centers"] = {"by_center": jsonable(sorted(by_center.values(), key=lambda x: -x["amount"])),
                               "by_period": jsonable([{"period": p, "amount": by_month.get(p, Decimal(0))}
                                                      for p in range(1, 13)]),
                               "total": jsonable(sum((e.amount for e in entries), Decimal(0)))}

    m = _latest_model(db, fy, "full_cost")
    if m:
        r = m.results
        out["full_cost"] = {**_model_head(m, fy), "analytical_result": r.get("analytical_result"),
                            "total_incorporated": r.get("total_incorporated"),
                            "imputation_differences": r.get("imputation_differences"),
                            "objects": [{k: o.get(k) for k in ("code", "name", "revenue", "cost", "unit_cost",
                                                               "cost_of_sales", "margin")} for o in r.get("objects", [])]}
    m = _latest_model(db, fy, "cvp")
    if m:
        r = m.results
        out["cvp"] = {**_model_head(m, fy), **{k: r.get(k) for k in (
            "revenue", "variable_costs", "contribution_margin", "contribution_rate_pct", "fixed_costs", "result",
            "breakeven", "breakeven_days", "breakeven_date", "safety_margin", "safety_index_pct",
            "operating_leverage", "unclassified_charges")}}
    m = _latest_model(db, fy, "standard_cost")
    if m:
        out["standard_cost"] = {**_model_head(m, fy), "totals": m.results.get("totals"),
                                "actual_output": m.results.get("actual_output")}
    return out
