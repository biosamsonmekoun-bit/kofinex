"""Analyse financière d'un exercice : états financiers, indicateurs N et N-1, contrôles.

Une analyse est un instantané figé et traçable : version du référentiel, import de balance,
formules (code + version), entrées exactes de chaque indicateur. Relancer une analyse en crée
une nouvelle ; les précédentes restent consultables.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import asdict
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import insert, or_, select
from sqlalchemy.orm import Session

from app.core.errors import Conflict, NotFound
from app.engines.accounting.statements import LineDef, MappingRule, StatementError, StatementsResult, TBEntry, \
    build_statements
from app.engines.financial.calculator import Calculator, Formula, IndicatorResult, YearContext
from app.engines.financial.library import CONCEPTS, CROSS_CHECKS
from app.engines.financial.multiyear import build_series
from app.models import (
    AccountMapping,
    Company,
    FinancialAlert,
    FinancialAnalysis,
    FinancialFormula,
    FinancialIndicator,
    FinancialStatement,
    FinancialStatementLine,
    FiscalYear,
    FrameworkConcept,
    FrameworkVersion,
    StatementLineDefinition,
    TrialBalanceEntry,
)

ENGINE_VERSION = "KOFINEX-ENGINE-1"
MAX_TRACE = 400


class AnalysisUnavailable(Conflict):
    code = "analysis_unavailable"


# ------------------------------------------------------------------------------ chargement
def _entries(db: Session, import_job_id: uuid.UUID) -> list[TBEntry]:
    rows = db.scalars(select(TrialBalanceEntry).where(TrialBalanceEntry.import_job_id == import_job_id)).all()
    return [TBEntry(r.account_number, r.account_label, r.opening_debit, r.opening_credit, r.movement_debit,
                    r.movement_credit, r.closing_debit, r.closing_credit) for r in rows]


def _framework(db: Session, version_id: uuid.UUID) -> tuple[list[LineDef], list[MappingRule], dict[str, dict]]:
    structure = [LineDef(d.statement_type, d.line_code, d.label, d.display_order, d.kind,
                         tuple((int(s), c) for s, c in (d.total_formula or [])), d.role, d.level)
                 for d in db.scalars(select(StatementLineDefinition)
                                     .where(StatementLineDefinition.framework_version_id == version_id)).all()]
    rules = [MappingRule(m.statement_type, m.line_code, m.account_prefix, tuple(m.excluded_prefixes or []),
                         m.balance_rule, m.amount_column, m.sign, m.priority)
             for m in db.scalars(select(AccountMapping).where(AccountMapping.framework_version_id == version_id,
                                                               AccountMapping.organization_id.is_(None))).all()]
    concepts = {c.concept_code: c.expression_ast for c in db.scalars(
        select(FrameworkConcept).where(FrameworkConcept.framework_version_id == version_id)).all()}
    return structure, rules, concepts


def applicable_formulas(db: Session, organization_id: uuid.UUID, framework_id: uuid.UUID) -> list[FinancialFormula]:
    """Formules publiées applicables : bibliothèque standard + formules du tenant. Pour un même code,
    la formule du tenant prime, puis la version la plus récente."""
    rows = db.scalars(select(FinancialFormula).where(
        FinancialFormula.status == "published",
        or_(FinancialFormula.organization_id.is_(None), FinancialFormula.organization_id == organization_id),
        or_(FinancialFormula.framework_id.is_(None), FinancialFormula.framework_id == framework_id),
    )).all()
    best: dict[str, FinancialFormula] = {}
    for f in rows:
        cur = best.get(f.code)
        key = (f.organization_id is not None, f.framework_id is not None, f.version)
        if cur is None or key > (cur.organization_id is not None, cur.framework_id is not None, cur.version):
            best[f.code] = f
    return sorted(best.values(), key=lambda f: f.code)


def _previous_fy(db: Session, fy: FiscalYear) -> FiscalYear | None:
    return db.scalar(select(FiscalYear).where(FiscalYear.company_id == fy.company_id, FiscalYear.end_date < fy.start_date)
                     .order_by(FiscalYear.end_date.desc()).limit(1))


# ------------------------------------------------------------------------------ exécution
def run_analysis(db: Session, *, company: Company, fy: FiscalYear, user_id: uuid.UUID) -> FinancialAnalysis:
    if fy.active_import_job_id is None:
        raise AnalysisUnavailable("Aucune balance validée pour cet exercice : importez et validez la balance d'abord.")
    version_id = fy.framework_version_id
    version = db.get(FrameworkVersion, version_id) if version_id else None
    if version is None or version.status not in ("published", "deprecated"):
        raise AnalysisUnavailable("Aucune version publiée du référentiel n'est rattachée à cet exercice : les états "
                                  "financiers ne peuvent pas être établis.")
    structure, rules, concepts = _framework(db, version.id)
    if not structure:
        raise AnalysisUnavailable("La version du référentiel ne comporte pas de structure des états financiers.")

    prev_fy = _previous_fy(db, fy)
    prev_import = prev_fy.active_import_job_id if prev_fy else None
    cur_entries = _entries(db, fy.active_import_job_id)
    prev_entries = _entries(db, prev_import) if prev_import else None

    analysis = FinancialAnalysis(
        id=uuid.uuid4(), organization_id=company.organization_id, company_id=company.id, fiscal_year_id=fy.id,
        analysis_type="annual", compared_fiscal_year_ids=[prev_fy.id] if prev_import else [],
        parameters={"previous_year_basis": "même version du référentiel que l'exercice analysé (pro forma)"},
        engine_version=ENGINE_VERSION, status="running", started_by=user_id, framework_version_id=version.id,
        source_import_job_id=fy.active_import_job_id, previous_fiscal_year_id=prev_fy.id if prev_import else None,
        previous_import_job_id=prev_import)
    db.add(analysis)
    db.flush()

    try:
        cur_st = build_statements(cur_entries, structure, rules)
        prev_st = build_statements(prev_entries, structure, rules) if prev_entries is not None else None
    except StatementError as exc:
        analysis.status, analysis.failure_reason, analysis.completed_at = "failed", str(exc), datetime.now(UTC)
        db.flush()
        return analysis

    _save_statements(db, analysis, fy, version.id, cur_st, prev_st, user_id)

    formulas = applicable_formulas(db, company.organization_id, company.framework_id)
    defs = [Formula(f.code, f.version, f.expression_ast, f.unit, f.rounding_scale, f.zero_division_policy,
                    f.missing_input_policy, str(f.id)) for f in formulas]
    ycur = YearContext(fy.label, fy.start_date, fy.end_date, cur_st.values(), cur_entries)
    yprev = YearContext(prev_fy.label, prev_fy.start_date, prev_fy.end_date, prev_st.values(), prev_entries) \
        if prev_st is not None else None
    calc = Calculator(ycur, yprev, concepts, defs)
    results = calc.run()
    # valeurs N-1 (pour comparaison) : même méthode, sans N-2
    prev_results = {r.code: r for r in Calculator(yprev, None, concepts, defs).run()} if yprev else {}
    checks = calc.cross_checks(CROSS_CHECKS)

    ind_ids = _save_indicators(db, analysis, results, prev_results)
    _save_alerts(db, analysis, fy, cur_st, checks, ind_ids)

    statuses = defaultdict(int)
    for r in results:
        statuses[r.status] += 1
    analysis.controls = {"statements": [asdict(c) for c in cur_st.controls],
                         "cross_checks": [{**asdict(c), "difference": str(c.difference) if c.difference is not None
                                           else None} for c in checks]}
    analysis.summary = {"indicators": dict(statuses), "formulas": len(defs),
                        "concepts_bound": sorted(concepts), "concepts_missing": sorted(set(CONCEPTS) - set(concepts)),
                        "unmapped_accounts": len(cur_st.unmapped), "has_previous_year": yprev is not None}
    analysis.status, analysis.completed_at = "completed", datetime.now(UTC)
    db.flush()
    return analysis


def _save_statements(db: Session, analysis: FinancialAnalysis, fy: FiscalYear, version_id: uuid.UUID,
                     cur: StatementsResult, prev: StatementsResult | None, user_id: uuid.UUID) -> None:
    prev_values = prev.values() if prev else {}
    for st, lines in cur.statements.items():
        sid = uuid.uuid4()
        db.add(FinancialStatement(id=sid, organization_id=analysis.organization_id, company_id=analysis.company_id,
                                  fiscal_year_id=fy.id, framework_version_id=version_id, statement_type=st,
                                  source_import_job_id=analysis.source_import_job_id, status="draft",
                                  engine_version=ENGINE_VERSION,
                                  control_results=[asdict(c) for c in cur.controls], generated_by=user_id,
                                  analysis_id=analysis.id))
        db.flush()
        payload = []
        for ln in lines:
            d = ln.definition
            pv = prev_values.get(d.code, {}).get("net") if prev else None
            payload.append(dict(
                organization_id=analysis.organization_id, statement_id=sid, line_code=d.code, label=d.label,
                display_order=d.order, is_total=d.kind == "total", amount_gross=ln.gross,
                amount_depreciation=ln.depreciation, amount_net=ln.net, amount_previous=pv,
                computation_trace={"items": ln.trace[:MAX_TRACE], "truncated": len(ln.trace) > MAX_TRACE},
                kind=d.kind, role=d.role, level=d.level))
        if payload:
            db.execute(insert(FinancialStatementLine), payload)


def _save_indicators(db: Session, analysis: FinancialAnalysis, results: list[IndicatorResult],
                     prev: dict[str, IndicatorResult]) -> dict[str, uuid.UUID]:
    ids: dict[str, uuid.UUID] = {}
    payload = []
    for r in results:
        iid = uuid.uuid4()
        ids[r.code] = iid
        p = prev.get(r.code)
        payload.append(dict(id=iid, organization_id=analysis.organization_id, analysis_id=analysis.id,
                            formula_id=uuid.UUID(r.formula_id), formula_code=r.code, formula_version=r.version,
                            value=r.value, status=r.status, unit=r.unit, inputs=r.inputs, message=r.message,
                            previous_value=p.value if p else None, previous_status=p.status if p else None))
    if payload:
        db.execute(insert(FinancialIndicator), payload)
    return ids


def _save_alerts(db: Session, analysis: FinancialAnalysis, fy: FiscalYear, st: StatementsResult, checks,
                 ind_ids: dict[str, uuid.UUID]) -> None:
    alerts = []
    for c in st.controls:
        if c.status == "failed":
            alerts.append(dict(severity="critical" if c.severity == "critical" else "warning", rule_code=c.code,
                               title="Contrôle des états financiers", message=c.message, evidence=c.details,
                               indicator_id=None))
    for c in checks:
        if c.status == "failed":
            alerts.append(dict(severity="warning", rule_code=c.code, title=c.title, message=c.message,
                               evidence={"difference": str(c.difference)},
                               indicator_id=ind_ids.get("TN" if c.code == "FR_BFR_TN" else "CAF_ADDITIVE")))
    for a in alerts:
        db.add(FinancialAlert(organization_id=analysis.organization_id, company_id=analysis.company_id,
                              fiscal_year_id=fy.id, analysis_id=analysis.id, **a))
    db.flush()


# ------------------------------------------------------------------------------ lecture
def _dec(v: Decimal | None) -> str | None:
    return None if v is None else format(v.normalize(), "f")


def analysis_detail(db: Session, analysis: FinancialAnalysis) -> dict:
    statements = db.scalars(select(FinancialStatement).where(FinancialStatement.analysis_id == analysis.id)).all()
    out_st = {}
    for s in statements:
        lines = db.scalars(select(FinancialStatementLine).where(FinancialStatementLine.statement_id == s.id)
                           .order_by(FinancialStatementLine.display_order)).all()
        out_st[s.statement_type] = [{
            "code": ln.line_code, "label": ln.label, "kind": ln.kind, "role": ln.role, "level": ln.level,
            "gross": _dec(ln.amount_gross), "depreciation": _dec(ln.amount_depreciation), "net": _dec(ln.amount_net),
            "previous": _dec(ln.amount_previous),
            "accounts": len((ln.computation_trace or {}).get("items", [])) if isinstance(ln.computation_trace, dict) else 0,
        } for ln in lines]
    formulas = {f.id: f for f in db.scalars(select(FinancialFormula).where(FinancialFormula.id.in_(
        select(FinancialIndicator.formula_id).where(FinancialIndicator.analysis_id == analysis.id)))).all()}
    indicators = []
    for i in db.scalars(select(FinancialIndicator).where(FinancialIndicator.analysis_id == analysis.id)).all():
        f = formulas.get(i.formula_id)
        indicators.append({
            "code": i.formula_code, "version": i.formula_version, "name": f.name if f else i.formula_code,
            "category": f.category if f else "custom", "unit": i.unit, "value": _dec(i.value), "status": i.status,
            "message": i.message, "previous_value": _dec(i.previous_value), "previous_status": i.previous_status,
            "inputs": i.inputs, "expression": f.expression if f else None,
            "description": f.description if f else None, "convention_notes": f.convention_notes if f else None,
            "custom": bool(f and f.organization_id),
        })
    alerts = db.scalars(select(FinancialAlert).where(FinancialAlert.analysis_id == analysis.id)).all()
    return {
        "id": analysis.id, "fiscal_year_id": analysis.fiscal_year_id, "status": analysis.status,
        "failure_reason": analysis.failure_reason, "engine_version": analysis.engine_version,
        "framework_version_id": analysis.framework_version_id, "source_import_job_id": analysis.source_import_job_id,
        "previous_fiscal_year_id": analysis.previous_fiscal_year_id, "started_at": analysis.started_at,
        "completed_at": analysis.completed_at, "parameters": analysis.parameters, "controls": analysis.controls,
        "summary": analysis.summary, "statements": out_st, "indicators": indicators,
        "alerts": [{"severity": a.severity, "rule_code": a.rule_code, "title": a.title, "message": a.message,
                    "evidence": a.evidence, "status": a.status} for a in alerts],
    }


def line_trace(db: Session, analysis: FinancialAnalysis, line_code: str) -> dict:
    row = db.execute(select(FinancialStatementLine).join(
        FinancialStatement, FinancialStatement.id == FinancialStatementLine.statement_id).where(
        FinancialStatement.analysis_id == analysis.id, FinancialStatementLine.line_code == line_code)).scalar()
    if row is None:
        raise NotFound("Ligne introuvable dans cette analyse")
    return {"code": row.line_code, "label": row.label, "trace": row.computation_trace}


def series(db: Session, company: Company, codes: list[str]) -> dict:
    years = db.scalars(select(FiscalYear).where(FiscalYear.company_id == company.id)
                       .order_by(FiscalYear.start_date)).all()
    latest: dict[uuid.UUID, FinancialAnalysis] = {}
    for fy in years:
        a = db.scalar(select(FinancialAnalysis).where(FinancialAnalysis.fiscal_year_id == fy.id,
                                                      FinancialAnalysis.status == "completed")
                      .order_by(FinancialAnalysis.completed_at.desc()).limit(1))
        if a:
            latest[fy.id] = a
    analysed = [fy for fy in years if fy.id in latest]
    values: dict[str, dict[uuid.UUID, FinancialIndicator]] = defaultdict(dict)
    if latest:
        q = select(FinancialIndicator).where(FinancialIndicator.analysis_id.in_([a.id for a in latest.values()]))
        if codes:
            q = q.where(FinancialIndicator.formula_code.in_(codes))
        by_analysis = {a.id: fy_id for fy_id, a in latest.items()}
        for i in db.scalars(q).all():
            values[i.formula_code][by_analysis[i.analysis_id]] = i
    names = {f.code: (f.name, f.category) for f in applicable_formulas(db, company.organization_id,
                                                                        company.framework_id)}
    out = []
    for code in sorted(values, key=lambda c: (names.get(c, ("", "z"))[1], c)):
        by_fy = values[code]
        unit = next(iter(by_fy.values())).unit
        s = build_series(code, unit, [(fy.label, by_fy[fy.id].value if fy.id in by_fy else None,
                                       by_fy[fy.id].status if fy.id in by_fy else "absent") for fy in analysed])
        out.append({"code": code, "name": names.get(code, (code, ""))[0], "category": names.get(code, ("", "custom"))[1],
                    "unit": unit, "cagr_pct": _dec(s.cagr_pct),
                    "points": [{"label": p.label, "value": _dec(p.value), "status": p.status,
                                "variation": _dec(p.variation), "variation_pct": _dec(p.variation_pct)}
                               for p in s.points]})
    return {"years": [{"id": fy.id, "label": fy.label, "analysis_id": latest[fy.id].id,
                       "completed_at": latest[fy.id].completed_at} for fy in analysed], "series": out}
