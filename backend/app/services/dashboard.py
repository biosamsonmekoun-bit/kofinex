"""Tableau de bord financier d'un exercice : rassemble des données déjà validées et calculées.

- Indicateurs (chiffre d'affaires, résultat net, trésorerie nette, EBE…) : dernière analyse **terminée** de l'exercice.
- Charges et produits (totaux et répartition) : balance validée de l'exercice ; sur une sous-période, grand livre validé.
- Évolution mensuelle : grand livre validé de l'exercice (sans grand livre, la série n'existe pas et le tableau le dit).
- Alertes : imports en attente de validation, alertes de l'analyse, état de la dernière analyse.
- Activités : derniers événements du journal d'audit de l'entreprise visibles par l'utilisateur (RLS)."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.engines.financial import dashboard as dash
from app.models import AuditLog, ChartAccount, Company, FinancialAnalysis, FiscalYear, ImportJob, TrialBalanceEntry
from app.services import analysis as analysis_svc
from app.services import ledger as ledger_svc
from app.services.engagements import people

KPI_CODES = {"revenue": "CA", "net_income": "RESULTAT_NET", "cash": "TN"}
TABLE_CODES = ("MARGE_COMMERCIALE", "EBE", "RESULTAT_EXPLOITATION", "RESULTAT_NET", "CAF_ADDITIVE")
PENDING_IMPORTS = ("pending", "parsing", "awaiting_mapping", "validating", "awaiting_confirmation")
ACTIVITY_LABELS = {
    "import.validated": "Validation de la balance",
    "ledger.imported": "Validation du grand livre",
    "ledger.exported": "Export du grand livre",
    "analysis.run": "Analyse financière lancée",
    "report.generate": "Génération d'un document",
    "report.download": "Téléchargement d'un document",
    "budget.create": "Création d'un budget",
    "budget.update": "Mise à jour d'un budget",
    "budget.lines_replaced": "Saisie des lignes budgétaires",
    "budget.new_version": "Nouvelle version de budget",
    "fiscal_year.closed": "Clôture de l'exercice",
    "fiscal_year.reopened": "Réouverture de l'exercice",
    "document.uploaded": "Dépôt d'un document",
    "cost_entry.create": "Saisie analytique",
    "costing_model.compute": "Calcul de coûts",
    "entry.validated": "Validation d'une écriture",
    "entry.rejected": "Rejet d'une écriture",
    "entry.reversal_prepared": "Préparation d'une extourne",
    "accounting.chart_imported": "Ouverture du plan comptable",
    "ai.commentary": "Commentaire IA demandé",
    "ai.commentary.review": "Relecture d'un commentaire IA",
}


def periods(fy: FiscalYear) -> list[dict]:
    """Périodes proposées : exercice complet, semestres, trimestres (si l'exercice compte 12 mois), puis chaque mois."""
    months = dash.fiscal_months(fy.start_date.year, fy.start_date.month, fy.end_date.year, fy.end_date.month)
    n = len(months)

    def label(a: int, b: int) -> str:
        ya, ma = months[a - 1][1], months[a - 1][2]
        yb, mb = months[b - 1][1], months[b - 1][2]
        return (
            f"{dash.MONTHS_FR[ma - 1]} – {dash.MONTHS_FR[mb - 1]} {yb}"
            if ya == yb
            else f"{dash.MONTHS_FR[ma - 1]} {ya} – {dash.MONTHS_FR[mb - 1]} {yb}"
        )

    out = [{"key": "year", "label": f"Exercice {fy.label}", "from": 1, "to": n}]
    if n == 12:
        out += [
            {"key": "s1", "label": f"S1 · {label(1, 6)}", "from": 1, "to": 6},
            {"key": "s2", "label": f"S2 · {label(7, 12)}", "from": 7, "to": 12},
        ]
        out += [
            {"key": f"t{q}", "label": f"T{q} · {label(3 * q - 2, 3 * q)}", "from": 3 * q - 2, "to": 3 * q} for q in range(1, 5)
        ]
    out += [{"key": f"m{p}", "label": f"{dash.MONTHS_FR[m - 1]} {y}", "from": p, "to": p} for p, y, m in months]
    return out


def _chart(db: Session, version_id) -> dash.Chart | None:
    if version_id is None:
        return None
    rows = db.execute(
        select(ChartAccount.account_number, ChartAccount.label, ChartAccount.nature).where(
            ChartAccount.framework_version_id == version_id
        )
    ).all()
    return dash.Chart({n: (lbl, nat) for n, lbl, nat in rows}) if rows else None


def _ind(detail: dict | None, code: str) -> dict | None:
    if not detail:
        return None
    return next((i for i in detail["indicators"] if i["code"] == code), None)


def _kpi(detail: dict | None, code: str) -> dict:
    i = _ind(detail, code)
    if i is None:
        return {
            "code": code,
            "available": False,
            "reason": "Aucune analyse terminée" if not detail else "Indicateur absent de l'analyse",
        }
    return {
        "code": code,
        "name": i["name"],
        "available": i["value"] is not None,
        "value": i["value"],
        "previous": i["previous_value"],
        "variation": dash.variation(i["value"], i["previous_value"]),
        "unit": i["unit"],
        "status": i["status"],
        "message": i["message"],
    }


def build(db: Session, company: Company, fy: FiscalYear, period_key: str = "year") -> dict:
    plist = periods(fy)
    period = next((p for p in plist if p["key"] == period_key), plist[0])
    full_year = period["key"] == "year"
    a = db.scalars(
        select(FinancialAnalysis)
        .where(
            FinancialAnalysis.fiscal_year_id == fy.id,
            FinancialAnalysis.status == "completed",
            FinancialAnalysis.analysis_type == "annual",
        )
        .order_by(FinancialAnalysis.completed_at.desc())
    ).first()
    detail = analysis_svc.analysis_detail(db, a) if a else None
    prev_fy = db.get(FiscalYear, a.previous_fiscal_year_id) if a and a.previous_fiscal_year_id else None

    tb_job = db.get(ImportJob, fy.active_import_job_id) if fy.active_import_job_id else None
    lg_job = db.get(ImportJob, fy.active_ledger_import_job_id) if fy.active_ledger_import_job_id else None
    chart = _chart(db, a.framework_version_id if a else (tb_job.framework_version_id if tb_job else None))

    # ---------------------------------------------------------------- charges et produits
    source, balances, note = None, {}, None
    if chart is not None:
        if lg_job is not None and (not full_year or tb_job is None):
            series = ledger_svc.monthly_net(db, fy)
            balances = {
                acc: sum((v for p, v in by.items() if period["from"] <= p <= period["to"]), Decimal(0))
                for acc, by in series.items()
            }
            source = "ledger"
        elif tb_job is not None and full_year:
            for acc, cd, cc in db.execute(
                select(TrialBalanceEntry.account_number, TrialBalanceEntry.closing_debit, TrialBalanceEntry.closing_credit).where(
                    TrialBalanceEntry.import_job_id == tb_job.id
                )
            ):
                balances[acc] = balances.get(acc, Decimal(0)) + (cd or 0) - (cc or 0)
            source = "trial_balance"
        elif not full_year:
            note = "Le détail d'une sous-période nécessite le grand livre validé de l'exercice."
    else:
        note = "Aucune balance validée rattachée à un plan de comptes publié."
    expenses = dash.breakdown(balances, chart, "expense") if source else None
    income = dash.breakdown(balances, chart, "income") if source else None

    # ---------------------------------------------------------------- évolution mensuelle
    monthly = {
        "available": False,
        "reason": "Importez et validez le grand livre de l'exercice pour suivre l'évolution mensuelle.",
    }
    if lg_job is not None and chart is not None:
        months = [
            m
            for m in dash.fiscal_months(fy.start_date.year, fy.start_date.month, fy.end_date.year, fy.end_date.month)
            if period["from"] <= m[0] <= period["to"]
        ]
        monthly = {"available": True, "months": dash.monthly(ledger_svc.monthly_net(db, fy), chart, months)}

    # ---------------------------------------------------------------- alertes
    pending = db.scalars(
        select(ImportJob).where(
            ImportJob.company_id == company.id, ImportJob.fiscal_year_id == fy.id, ImportJob.status.in_(PENDING_IMPORTS)
        )
    ).all()
    open_alerts = [x for x in (detail or {}).get("alerts", []) if x.get("status") in (None, "open")]
    alerts = [
        {
            "key": "imports",
            "title": "Imports en attente",
            "detail": f"{len(pending)} import(s) à valider" if pending else "Aucun import en attente",
            "state": "todo" if pending else "done",
            "count": len(pending),
        },
        {
            "key": "analysis_alerts",
            "title": "Alertes de l'analyse",
            "detail": (f"{len(open_alerts)} alerte(s) à examiner" if open_alerts else "Aucune alerte ouverte")
            if detail
            else "Analyse non disponible",
            "state": ("progress" if open_alerts else "done") if detail else "none",
            "count": len(open_alerts),
            "items": [{"severity": x["severity"], "title": x["title"]} for x in open_alerts[:5]],
        },
        {
            "key": "last_analysis",
            "title": "Dernière analyse financière",
            "detail": f"Analyse terminée le {a.completed_at:%d/%m/%Y}" if a else "Aucune analyse terminée pour cet exercice",
            "state": "done" if a else "todo",
            "count": 0,
        },
    ]

    # ---------------------------------------------------------------- activités (journal, selon la RLS)
    logs = list(
        db.scalars(
            select(AuditLog)
            .where(AuditLog.company_id == company.id, AuditLog.action.like("%.%"))
            .order_by(AuditLog.created_at.desc())
            .limit(5)
        )
    )
    ppl = people(db, [x.user_id for x in logs if x.user_id])
    activities = [
        {
            "id": x.id,
            "action": x.action,
            "label": ACTIVITY_LABELS.get(x.action, x.action),
            "entity_type": x.entity_type,
            "at": x.created_at,
            "user": ppl.get(str(x.user_id)),
        }
        for x in logs
    ]

    return {
        "company": {"id": company.id, "name": company.name, "currency": company.currency, "is_demo": company.is_demo},
        "fiscal_year": {"id": fy.id, "label": fy.label, "start_date": fy.start_date, "end_date": fy.end_date},
        "previous_label": prev_fy.label if prev_fy else None,
        "period": period,
        "periods": plist,
        "analysis": {"id": a.id, "completed_at": a.completed_at} if a else None,
        "kpis": {k: _kpi(detail, c) for k, c in KPI_CODES.items()},
        "expenses": expenses,
        "income": income,
        "breakdown_source": source,
        "breakdown_note": note,
        "indicators": [_kpi(detail, c) for c in TABLE_CODES],
        "monthly": monthly,
        "alerts": alerts,
        "activities": activities,
        "sources": {"trial_balance_import_id": tb_job.id if tb_job else None, "ledger_import_id": lg_job.id if lg_job else None},
    }
