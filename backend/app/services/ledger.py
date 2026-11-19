"""Importation et exploitation du grand livre (complément du lot 3).

Cycle d'un import (le même que pour les balances, `import_jobs.kind = 'ledger'`) :
  pending -> parsing -> awaiting_mapping -> validating -> awaiting_confirmation -> completed
Le grand livre validé devient le grand livre de l'exercice (`fiscal_years.active_ledger_import_job_id`) ; le précédent
passe « superseded » et reste consultable. La base refuse la validation d'un grand livre comportant une ligne en
erreur, déséquilibré, comportant une écriture déséquilibrée ou une date hors de l'exercice (migration 0010).

Sécurité des requêtes : les fragments SQL interpolés sont des constantes du code (noms de colonnes, clauses fixes) ;
toute valeur fournie par l'utilisateur est transmise en paramètre lié.
"""

from __future__ import annotations

import csv
import io
import uuid
from collections import defaultdict
from dataclasses import asdict
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import delete, insert, select, text, update
from sqlalchemy.orm import Session

from app.core.errors import Conflict, NotFound
from app.engines.importing import ledger as lg
from app.engines.importing import readers
from app.engines.importing.files import FileRejected
from app.models import Company, FiscalYear, ImportJob, ImportMapping, LedgerLine, TrialBalanceEntry
from app.services import imports as base
from app.services.imports import ImportRejected

PREVIEW_ROWS = 40
LEDGER_FORMATS = ("xlsx", "xls", "csv")
LINE_FIELDS = (
    "journal_code",
    "journal_label",
    "entry_number",
    "entry_date",
    "document_ref",
    "document_date",
    "account_number",
    "account_label",
    "auxiliary_account",
    "auxiliary_label",
    "label",
    "debit",
    "credit",
    "lettering",
    "lettering_date",
    "validation_date",
    "currency_amount",
    "currency",
)


def _jsonable(v):
    if isinstance(v, Decimal):
        return format(v.normalize(), "f") if v == v.to_integral() else str(v)
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    if isinstance(v, uuid.UUID):
        return str(v)
    return v


def get_job(db: Session, company_id: uuid.UUID, job_id: uuid.UUID) -> ImportJob:
    job = db.get(ImportJob, job_id)
    if job is None or job.company_id != company_id or job.kind != "ledger":
        raise NotFound("Import de grand livre introuvable")
    return job


# ------------------------------------------------------------------ cycle de l'import
def create_ledger_import(
    db: Session, *, company: Company, fiscal_year_id: uuid.UUID, filename: str, data: bytes, user_id: uuid.UUID
) -> ImportJob:
    return base.create_import(
        db,
        company=company,
        fiscal_year_id=fiscal_year_id,
        filename=filename,
        data=data,
        user_id=user_id,
        kind="ledger",
        allowed_formats=LEDGER_FORMATS,
    )


def analyze_ledger(db: Session, job_id: uuid.UUID) -> ImportJob:
    job = db.get(ImportJob, job_id)
    if job is None or job.kind != "ledger":
        raise NotFound("Import de grand livre introuvable")
    if job.status not in ("pending", "parsing", "failed"):
        return job
    job.status = "parsing"
    db.flush()
    try:
        ext = base._extract(db, job)
    except FileRejected as exc:
        return base._fail(db, job, str(exc))
    metas = []
    for sh in ext.sheets:
        header = lg.detect_header_row(sh.rows)
        cm, headers, fmt = lg.suggest_mapping(sh.rows, header) if header is not None else ({}, [], "generic")
        start = max(0, (header or 0) - 3)
        metas.append(
            {
                "name": sh.name,
                "rows": sh.row_count,
                "columns": sh.column_count,
                "header_row": header,
                "header_score": lg.header_score(sh.rows[header]) if header is not None else 0,
                "suggested_mapping": cm,
                "headers": headers,
                "format": fmt,
                "warnings": sh.warnings,
                "notes": ([] if header is not None else ["En-tête non détecté : indiquez la ligne d'en-tête."])
                + (["Fichier des écritures comptables (FEC) reconnu."] if fmt == "fec" else []),
                "preview_start": start,
                "preview": [[readers.jsonable(v) for v in r] for r in sh.rows[start : start + PREVIEW_ROWS]],
            }
        )
    job.sheets = metas
    ex = dict(job.extraction or {})
    ex.update(method=ext.method)
    job.extraction = ex
    best = max(metas, key=lambda m: m["header_score"]) if metas else None
    job.sheet_name = best["name"] if best else None
    job.header_row = best["header_row"] if best else None
    job.column_map = best["suggested_mapping"] if best else None
    job.options = {"decimal_separator": None}
    saved = db.scalar(
        select(ImportMapping).where(
            ImportMapping.company_id == job.company_id, ImportMapping.kind == "ledger", ImportMapping.is_default.is_(True)
        )
    )
    if saved and best and all(isinstance(v, int) and v < max(best["columns"], 1) for v in saved.column_map.values()):
        job.column_map = {k: int(v) for k, v in saved.column_map.items()}
        job.options = saved.options or {}
        job.mapping_id = saved.id
    job.status = "awaiting_mapping"
    db.flush()
    return job


def configure_ledger(
    db: Session, job: ImportJob, *, sheet_name: str, header_row: int, column_map: dict[str, int], options: dict
) -> ImportJob:
    if job.status not in ("awaiting_mapping", "awaiting_confirmation", "failed") or not job.sheets:
        raise Conflict("Cet import ne peut pas être reconfiguré dans son état actuel.")
    meta = next((m for m in job.sheets if m["name"] == sheet_name), None)
    if meta is None:
        raise ImportRejected(f"Feuille « {sheet_name} » introuvable dans le fichier.")
    if not 0 <= header_row < max(meta["rows"], 1):
        raise ImportRejected("Ligne d'en-tête hors du tableau.")
    try:
        opts = lg.LedgerOptions.from_dict(options)
        lg.validate_column_map(column_map, opts)
    except (lg.LedgerMappingError, TypeError, ValueError) as exc:
        raise ImportRejected(str(exc)) from exc
    if any(c >= meta["columns"] for c in column_map.values()):
        raise ImportRejected("Une colonne associée n'existe pas dans la feuille.")
    job.sheet_name, job.header_row, job.column_map, job.options = sheet_name, header_row, column_map, asdict(opts)
    job.status, job.failure_reason, job.warnings_acknowledged = "validating", None, False
    db.flush()
    return job


def _tb_rows(db: Session, fy: FiscalYear) -> list[lg.TBRow] | None:
    if fy.active_import_job_id is None:
        return None
    return [
        lg.TBRow(
            r.account_number,
            r.opening_debit - r.opening_credit,
            r.movement_debit,
            r.movement_credit,
            r.closing_debit - r.closing_credit,
        )
        for r in db.scalars(select(TrialBalanceEntry).where(TrialBalanceEntry.import_job_id == fy.active_import_job_id))
    ]


def process_ledger(db: Session, job_id: uuid.UUID) -> ImportJob:
    job = db.get(ImportJob, job_id)
    if job is None or job.kind != "ledger":
        raise NotFound("Import de grand livre introuvable")
    if job.status != "validating":
        return job
    try:
        ext = base._extract(db, job)
    except FileRejected as exc:
        return base._fail(db, job, str(exc))
    sheet = next((s for s in ext.sheets if s.name == job.sheet_name), None)
    if sheet is None:
        return base._fail(db, job, "Feuille introuvable lors du traitement.")
    opts = lg.LedgerOptions.from_dict(job.options)
    try:
        parsed = lg.build_ledger(sheet.rows, job.header_row or 0, {k: int(v) for k, v in (job.column_map or {}).items()}, opts)
    except lg.LedgerMappingError as exc:
        return base._fail(db, job, str(exc))
    fy = db.get(FiscalYear, job.fiscal_year_id)
    complement_summary, complement_of = None, None
    if opts.mode == "complement":
        complement_of = fy.active_ledger_import_job_id
        if complement_of is None or complement_of == job.id:
            return base._fail(db, job, "Import complémentaire : aucun grand livre validé à compléter pour cet exercice.")
        existing = [
            lg.LedgerLine(r.source_row, "valid", **{f: getattr(r, f) for f in LINE_FIELDS}, raw=list(r.raw or []))
            for r in db.scalars(select(LedgerLine).where(LedgerLine.import_job_id == complement_of, LedgerLine.status == "valid"))
        ]
        parsed, complement_summary = lg.complement(existing, parsed)
    report = lg.run_controls(
        parsed,
        fy.start_date,
        fy.end_date,
        opts,
        chart=base._chart_context(db, job.framework_version_id),
        balance=_tb_rows(db, fy),
    )
    db.execute(delete(LedgerLine).where(LedgerLine.import_job_id == job.id))
    payload = [
        dict(
            organization_id=job.organization_id,
            company_id=job.company_id,
            fiscal_year_id=job.fiscal_year_id,
            import_job_id=job.id,
            source_row=ln.source_row,
            status=ln.status,
            **{f: getattr(ln, f) for f in LINE_FIELDS},
            issues=[asdict(i) for i in ln.issues],
            raw=[readers.jsonable(v) for v in ln.raw],
        )
        for ln in parsed.lines
    ]
    for i in range(0, len(payload), 2000):
        db.execute(insert(LedgerLine), payload[i : i + 2000])
    job.controls = report.to_dict()
    if complement_summary is not None:
        job.controls = {**job.controls, "complement": {**complement_summary, "complement_of": str(complement_of)}}
    job.control_totals = report.totals
    job.total_rows, job.valid_rows, job.error_rows = len(parsed.lines), len(parsed.valid), len(parsed.errors)
    job.errors = [{"row": x.source_row, "issues": [i.message for i in x.issues]} for x in parsed.errors[:100]]
    job.status = "awaiting_confirmation"
    db.flush()
    return job


def confirm_ledger(
    db: Session, job: ImportJob, *, user_id: uuid.UUID, acknowledge_warnings: bool, save_mapping_as: str | None
) -> ImportJob:
    if job.status != "awaiting_confirmation" or not job.controls:
        raise Conflict("L'import n'est pas prêt à être validé.")
    if job.controls.get("blocking"):
        raise Conflict("Des contrôles bloquants ont échoué : corrigez le fichier ou l'association des colonnes.")
    if job.controls.get("requires_acknowledgment") and not acknowledge_warnings:
        raise Conflict("Des avertissements doivent être explicitement acceptés avant la validation.")
    fy = db.get(FiscalYear, job.fiscal_year_id)
    if fy.status != "open":
        raise Conflict("L'exercice est clôturé.")
    comp = (job.controls or {}).get("complement")
    if comp and comp.get("complement_of") != (str(fy.active_ledger_import_job_id) if fy.active_ledger_import_job_id else None):
        raise Conflict("Le grand livre actif a changé depuis la préparation de cet import complémentaire : "
                       "relancez le traitement.")
    now = datetime.now(UTC)
    job.status = "completed"  # la base revérifie lignes, équilibres et dates (migration 0010)
    job.validated_by, job.validated_at, job.completed_at = user_id, now, now
    job.warnings_acknowledged = bool(job.controls.get("requires_acknowledgment"))
    job.acknowledged_by = user_id if job.warnings_acknowledged else None
    db.flush()
    if fy.active_ledger_import_job_id and fy.active_ledger_import_job_id != job.id:
        db.execute(update(ImportJob).where(ImportJob.id == fy.active_ledger_import_job_id).values(status="superseded"))
    fy.active_ledger_import_job_id = job.id
    if save_mapping_as:
        db.execute(
            update(ImportMapping)
            .where(ImportMapping.company_id == job.company_id, ImportMapping.kind == "ledger")
            .values(is_default=False)
        )
        m = ImportMapping(
            organization_id=job.organization_id,
            company_id=job.company_id,
            name=save_mapping_as[:120],
            source_format=job.source_format,
            column_map=job.column_map,
            options=job.options or {},
            is_default=True,
            kind="ledger",
            created_by=user_id,
        )
        db.add(m)
        db.flush()
        job.mapping_id = m.id
    db.flush()
    return job


def cancel_ledger(db: Session, job: ImportJob) -> ImportJob:
    if job.status in ("completed", "superseded", "cancelled"):
        raise Conflict("Import déjà validé ou annulé.")
    db.execute(delete(LedgerLine).where(LedgerLine.import_job_id == job.id))
    job.status = "cancelled"
    db.flush()
    return job


def job_summary(job: ImportJob) -> dict:
    return {
        **{k: _jsonable(v) if not isinstance(v, (dict, list)) else v for k, v in base.job_summary(job).items()},
        "kind": job.kind,
        "field_labels": lg.FIELD_LABELS,
        "fields": lg.FIELDS,
    }


# ------------------------------------------------------------------ exploitation
class LedgerFilters:
    def __init__(
        self,
        *,
        account: str | None = None,
        account_prefix: str | None = None,
        journal: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        q: str | None = None,
        min_amount: Decimal | None = None,
        max_amount: Decimal | None = None,
        lettered: bool | None = None,
        auxiliary: str | None = None,
    ):
        self.account, self.account_prefix, self.journal = account, account_prefix, journal
        self.date_from, self.date_to, self.q = date_from, date_to, (q or "").strip()[:100] or None
        self.min_amount, self.max_amount, self.lettered, self.auxiliary = min_amount, max_amount, lettered, auxiliary

    def sql(self, params: dict) -> str:
        w = ["import_job_id = :job", "status = 'valid'"]
        if self.account:
            w.append("account_number = :account")
            params["account"] = self.account
        if self.account_prefix:
            w.append("account_number LIKE :prefix")
            params["prefix"] = self.account_prefix.replace("%", "").replace("_", "") + "%"
        if self.journal:
            w.append("journal_code = :journal")
            params["journal"] = self.journal
        if self.auxiliary:
            w.append("auxiliary_account = :aux")
            params["aux"] = self.auxiliary
        if self.date_from:
            w.append("entry_date >= :dfrom")
            params["dfrom"] = self.date_from
        if self.date_to:
            w.append("entry_date <= :dto")
            params["dto"] = self.date_to
        if self.q:
            w.append("(label ILIKE :q OR document_ref ILIKE :q OR entry_number = :qexact OR auxiliary_label ILIKE :q)")
            params["q"] = "%" + self.q.replace("\\", "").replace("%", "").replace("_", "") + "%"
            params["qexact"] = self.q
        if self.min_amount is not None:
            w.append("(debit + credit) >= :amin")
            params["amin"] = self.min_amount
        if self.max_amount is not None:
            w.append("(debit + credit) <= :amax")
            params["amax"] = self.max_amount
        if self.lettered is not None:
            w.append("lettering IS NOT NULL" if self.lettered else "lettering IS NULL")
        return " AND ".join(w)

    @property
    def running_allowed(self) -> bool:
        """Solde progressif : significatif pour un compte, éventuellement borné dans le temps, sans autre filtre."""
        return bool(self.account) and not any(
            (self.journal, self.q, self.min_amount, self.max_amount, self.lettered is not None, self.auxiliary)
        )


def require_ledger(fy: FiscalYear) -> uuid.UUID:
    if fy.active_ledger_import_job_id is None:
        raise Conflict(f"Aucun grand livre validé pour l'exercice {fy.label} : importez et validez le grand livre.")
    return fy.active_ledger_import_job_id


ORDER = "entry_date, coalesce(journal_code, ''), coalesce(entry_number, ''), source_row"


def lines(db: Session, fy: FiscalYear, f: LedgerFilters, limit: int, offset: int) -> dict:
    job = require_ledger(fy)
    p: dict = {"job": job}
    where = f.sql(p)
    agg = db.execute(
        text(f"SELECT count(*), coalesce(sum(debit),0), coalesce(sum(credit),0) FROM ledger_lines WHERE {where}"), p
    ).one()
    opening = None
    running_sql = "NULL::numeric"
    if f.running_allowed:
        running_sql = f"sum(debit - credit) OVER (ORDER BY {ORDER} ROWS UNBOUNDED PRECEDING)"
        if f.date_from:
            opening = db.execute(
                text(
                    "SELECT coalesce(sum(debit - credit), 0) FROM ledger_lines WHERE import_job_id = :job "
                    "AND status = 'valid' AND account_number = :account AND entry_date < :dfrom"
                ),
                {"job": job, "account": f.account, "dfrom": f.date_from},
            ).scalar()
        else:
            opening = Decimal(0)
    rows = db.execute(
        text(
            f"SELECT id, source_row, {', '.join(LINE_FIELDS)}, {running_sql} AS running FROM ledger_lines "
            f"WHERE {where} ORDER BY {ORDER} LIMIT :lim OFFSET :off"
        ),
        {**p, "lim": limit, "off": offset},
    ).mappings()
    items = []
    for r in rows:
        d = {k: _jsonable(v) for k, v in r.items() if k != "running"}
        d["running_balance"] = _jsonable(r["running"] + opening) if r["running"] is not None and opening is not None else None
        items.append(d)
    return {
        "import_job_id": str(job),
        "total_count": agg[0],
        "totals": {"debit": _jsonable(agg[1]), "credit": _jsonable(agg[2]), "net": _jsonable(agg[1] - agg[2])},
        "opening_balance": _jsonable(opening) if opening is not None else None,
        "running_balance": f.running_allowed,
        "items": items,
    }


def export_csv(db: Session, fy: FiscalYear, f: LedgerFilters) -> bytes:
    job = require_ledger(fy)
    p: dict = {"job": job}
    rows = db.execute(text(f"SELECT {', '.join(LINE_FIELDS)} FROM ledger_lines WHERE {f.sql(p)} ORDER BY {ORDER}"), p)
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow([lg.FIELD_LABELS.get(x, x) for x in LINE_FIELDS])
    for r in rows:
        w.writerow(
            ["" if v is None else str(_jsonable(v)).replace(".", ",") if isinstance(v, Decimal) else _jsonable(v) for v in r]
        )
    return ("﻿" + buf.getvalue()).encode("utf-8")


def entry(db: Session, fy: FiscalYear, journal: str | None, number: str) -> list[dict]:
    job = require_ledger(fy)
    rows = db.execute(
        text(
            f"SELECT source_row, {', '.join(LINE_FIELDS)} FROM ledger_lines WHERE import_job_id = :job "
            "AND status = 'valid' AND coalesce(journal_code, '') = :j AND entry_number = :n ORDER BY source_row"
        ),
        {"job": job, "j": journal or "", "n": number},
    ).mappings()
    return [{k: _jsonable(v) for k, v in r.items()} for r in rows]


def accounts(db: Session, fy: FiscalYear, prefix: str | None) -> dict:
    """Totaux par compte du grand livre, rapprochés de la balance validée (mêmes règles que le contrôle d'import)."""
    job = require_ledger(fy)
    jobrow = db.get(ImportJob, job)
    oj = list(lg.LedgerOptions.from_dict(jobrow.options).opening_journals)
    p = {"job": job, "oj": oj or ["\x00"], "prefix": (prefix or "") + "%"}
    rows = (
        db.execute(
            text("""
        SELECT account_number, max(account_label) AS label, count(*) AS lines,
               coalesce(sum(debit - credit) FILTER (WHERE journal_code = ANY(:oj)), 0) AS opening,
               coalesce(sum(debit) FILTER (WHERE journal_code IS NULL OR NOT journal_code = ANY(:oj)), 0) AS debit,
               coalesce(sum(credit) FILTER (WHERE journal_code IS NULL OR NOT journal_code = ANY(:oj)), 0) AS credit
          FROM ledger_lines WHERE import_job_id = :job AND status = 'valid' AND account_number LIKE :prefix
         GROUP BY account_number ORDER BY account_number"""),
            p,
        )
        .mappings()
        .all()
    )
    tb = {r.account: r for r in (_tb_rows(db, fy) or [])}
    out = []
    for r in rows:
        b = tb.get(r["account_number"])
        net = r["opening"] + r["debit"] - r["credit"]
        d = {
            "account_number": r["account_number"],
            "label": r["label"],
            "lines": r["lines"],
            "opening": _jsonable(r["opening"]),
            "debit": _jsonable(r["debit"]),
            "credit": _jsonable(r["credit"]),
            "balance": _jsonable(net),
            "tb": None,
        }
        if b is not None:
            gap_mv = (r["debit"] - b.movement_debit, r["credit"] - b.movement_credit)
            d["tb"] = {
                "movement_debit": _jsonable(b.movement_debit),
                "movement_credit": _jsonable(b.movement_credit),
                "opening": _jsonable(b.opening_net),
                "closing": _jsonable(b.closing_net),
                "movement_gap": gap_mv != (0, 0),
                "opening_gap": bool(oj) and r["opening"] != b.opening_net,
            }
        out.append(d)
    in_ledger = {r["account_number"] for r in rows}
    missing = sorted(a for a in set(tb) - in_ledger if a.startswith(prefix or ""))
    return {
        "accounts": out,
        "opening_journals": oj,
        "balance_available": bool(tb),
        "balance_accounts_without_lines": [a for a in missing if tb[a].movement_debit or tb[a].movement_credit],
    }


def journals(db: Session, fy: FiscalYear) -> dict:
    """Centralisation : par journal et par mois de l'exercice, nombre d'écritures et totaux."""
    job = require_ledger(fy)
    rows = (
        db.execute(
            text("""
        SELECT coalesce(journal_code, '') AS journal, max(journal_label) AS label,
               date_trunc('month', entry_date)::date AS month,
               count(DISTINCT coalesce(entry_number, document_ref, source_row::text)) AS entries, count(*) AS lines,
               sum(debit) AS debit, sum(credit) AS credit
          FROM ledger_lines WHERE import_job_id = :job AND status = 'valid'
         GROUP BY 1, 3 ORDER BY 1, 3"""),
            {"job": job},
        )
        .mappings()
        .all()
    )
    by: dict[str, dict] = {}
    for r in rows:
        j = by.setdefault(
            r["journal"],
            {"journal": r["journal"], "label": r["label"], "months": [], "debit": Decimal(0), "credit": Decimal(0), "lines": 0},
        )
        j["months"].append(
            {
                "period": lg.fiscal_period(fy.start_date, r["month"]),
                "month": r["month"].isoformat(),
                "entries": r["entries"],
                "lines": r["lines"],
                "debit": _jsonable(r["debit"]),
                "credit": _jsonable(r["credit"]),
            }
        )
        j["debit"] += r["debit"]
        j["credit"] += r["credit"]
        j["lines"] += r["lines"]
    return {"journals": [{**j, "debit": _jsonable(j["debit"]), "credit": _jsonable(j["credit"])} for j in by.values()]}


def monthly_net(db: Session, fy: FiscalYear, prefixes: list[str] | None = None) -> dict[str, dict[int, Decimal]]:
    """Mouvements nets (débit − crédit) par compte et par mois de l'exercice, hors journaux d'à-nouveaux désignés."""
    job = fy.active_ledger_import_job_id
    if job is None:
        return {}
    oj = list(lg.LedgerOptions.from_dict(db.get(ImportJob, job).options).opening_journals)
    rows = db.execute(
        text("""
        SELECT account_number, date_trunc('month', entry_date)::date AS month, sum(debit - credit) AS net
          FROM ledger_lines WHERE import_job_id = :job AND status = 'valid'
           AND (journal_code IS NULL OR NOT journal_code = ANY(:oj))
         GROUP BY 1, 2"""),
        {"job": job, "oj": oj or ["\x00"]},
    ).all()
    out: dict[str, dict[int, Decimal]] = defaultdict(dict)
    for acc, month, net in rows:
        if prefixes and not any(acc.startswith(p) for p in prefixes):
            continue
        out[acc][lg.fiscal_period(fy.start_date, month)] = net
    return dict(out)


def analytics(db: Session, fy: FiscalYear, *, round_multiple: Decimal | None, benford_min: Decimal) -> dict:
    """Analyses de données sur les écritures : constats factuels à examiner, sans conclusion ni seuil d'alerte."""
    job = require_ledger(fy)
    p = {"job": job}
    w = "import_job_id = :job AND status = 'valid'"
    weekend = (
        db.execute(
            text(f"""
        SELECT coalesce(journal_code,'') AS journal, entry_number, entry_date, count(*) AS lines, sum(debit) AS debit
          FROM ledger_lines WHERE {w} AND extract(isodow FROM entry_date) IN (6, 7)
         GROUP BY 1, 2, 3 ORDER BY 3 LIMIT 200"""),
            p,
        )
        .mappings()
        .all()
    )
    weekend_total = db.execute(
        text(
            f"SELECT count(DISTINCT (coalesce(journal_code,''), coalesce(entry_number, source_row::text))) "
            f"FROM ledger_lines WHERE {w} AND extract(isodow FROM entry_date) IN (6, 7)"
        ),
        p,
    ).scalar()
    dup = (
        db.execute(
            text(f"""
        SELECT account_number, entry_date, debit, credit, coalesce(label, '') AS label, count(*) AS occurrences,
               count(DISTINCT (coalesce(journal_code,''), coalesce(entry_number, source_row::text))) AS entries
          FROM ledger_lines WHERE {w}
         GROUP BY 1, 2, 3, 4, 5 HAVING count(DISTINCT (coalesce(journal_code,''), coalesce(entry_number, source_row::text))) > 1
         ORDER BY (debit + credit) DESC LIMIT 200"""),
            p,
        )
        .mappings()
        .all()
    )
    nolabel = db.execute(text(f"SELECT count(*) FROM ledger_lines WHERE {w} AND (label IS NULL OR trim(label) = '')"), p).scalar()
    late = db.execute(
        text(f"SELECT count(*) FROM ledger_lines WHERE {w} AND validation_date > :end"), {**p, "end": fy.end_date}
    ).scalar()
    has_validation = db.execute(text(f"SELECT count(*) FROM ledger_lines WHERE {w} AND validation_date IS NOT NULL"), p).scalar()
    numbers: dict[str, list[str]] = defaultdict(list)
    for j, n in db.execute(
        text(f"SELECT DISTINCT coalesce(journal_code,''), entry_number FROM ledger_lines WHERE {w} AND entry_number IS NOT NULL"),
        p,
    ):
        numbers[j].append(n)
    gaps = [
        {
            "journal": j,
            "gaps": [{"from": a, "to": b} for a, b in lg.numbering_gaps(ns)][:50],
            "numeric": sum(1 for n in ns if n.isdigit()),
            "total": len(ns),
        }
        for j, ns in sorted(numbers.items())
    ]
    rounds = None
    if round_multiple is not None and round_multiple > 0:
        rr = (
            db.execute(
                text(f"""
            SELECT coalesce(journal_code,'') AS journal, entry_number, entry_date, account_number, label, debit, credit
              FROM ledger_lines WHERE {w} AND (debit + credit) >= :m AND mod(debit + credit, :m) = 0
             ORDER BY (debit + credit) DESC LIMIT 200"""),
                {**p, "m": round_multiple},
            )
            .mappings()
            .all()
        )
        cnt = db.execute(
            text(f"SELECT count(*) FROM ledger_lines WHERE {w} AND (debit + credit) >= :m AND mod(debit + credit, :m) = 0"),
            {**p, "m": round_multiple},
        ).scalar()
        rounds = {
            "multiple": _jsonable(round_multiple),
            "count": cnt,
            "lines": [{k: _jsonable(v) for k, v in r.items()} for r in rr],
        }
    digits = defaultdict(int)
    for (amt,) in db.execute(
        text(f"SELECT debit + credit FROM ledger_lines WHERE {w} AND (debit + credit) >= :bmin AND (debit + credit) > 0"),
        {**p, "bmin": benford_min},
    ):
        d = lg.first_digit(amt)
        if d:
            digits[d] += 1
    n = sum(digits.values())
    exp = lg.benford_expected()
    benford = {
        "min_amount": _jsonable(benford_min),
        "count": n,
        "digits": [
            {
                "digit": d,
                "observed": digits[d],
                "observed_pct": _jsonable((Decimal(digits[d]) / n * 100).quantize(Decimal("0.01"))) if n else None,
                "expected_pct": _jsonable(exp[d]),
            }
            for d in range(1, 10)
        ],
    }
    return {
        "weekend_entries": {
            "count": weekend_total,
            "entries": [
                {**{k: _jsonable(v) for k, v in r.items()}, "weekday": lg.weekday_label(r["entry_date"])} for r in weekend
            ],
        },
        "possible_duplicates": [{k: _jsonable(v) for k, v in r.items()} for r in dup],
        "lines_without_label": nolabel,
        "validated_after_year_end": late if has_validation else None,
        "numbering_gaps": gaps,
        "round_amounts": rounds,
        "benford": benford,
        "notes": [
            "Ces analyses signalent des écritures à examiner ; elles ne qualifient pas une anomalie.",
            "Doublons possibles : même compte, même date, mêmes montants et même libellé dans des écritures distinctes.",
            "Trous de numérotation : seuls les numéros d'écriture entièrement numériques sont analysés, par journal.",
            "Loi de Benford : fréquence attendue du premier chiffre, log10(1 + 1/d) ; aucune conformité n'est conclue.",
        ],
    }
