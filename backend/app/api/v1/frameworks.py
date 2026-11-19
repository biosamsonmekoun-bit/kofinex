"""Référentiels comptables : consultation (tous) et administration des versions (admins plateforme).

Cycle d'une version : brouillon -> chargement du plan de comptes et des correspondances depuis
les fichiers transcrivant le texte officiel -> validation -> publication (figée) -> retrait.
"""

from __future__ import annotations

import csv
import io
import uuid
from dataclasses import asdict
from datetime import UTC, date, datetime
from typing import Literal

from fastapi import APIRouter, Depends, File, Request, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel, Field, HttpUrl, model_validator
from sqlalchemy import delete, func, insert, select, text
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.config import get_settings
from app.core.errors import AppError, Conflict, Forbidden, NotFound
from app.core.security import AuthenticatedUser
from app.engines.accounting.frameworks import STATEMENT_LABELS, get_profile
from app.engines.accounting.reference_loader import (
    CHART_COLUMNS,
    CONCEPT_COLUMNS,
    MAPPING_COLUMNS,
    STRUCTURE_COLUMNS,
    ChartRecord,
    LoadIssue,
    MappingRecord,
    StructureRecord,
    parse_chart,
    parse_concepts,
    parse_mappings,
    parse_structure,
)
from app.engines.financial.library import CONCEPTS
from app.engines.importing import readers
from app.engines.importing.files import FileRejected, sha256_hex, validate_upload
from app.models import (
    AccountingFramework,
    AccountMapping,
    ChartAccount,
    FrameworkConcept,
    FrameworkVersion,
    Profile,
    StatementLineDefinition,
)
from app.services.audit import record_event

router = APIRouter(tags=["Référentiels comptables"])


class ReferenceRejected(AppError):
    status_code = 422
    code = "reference_invalid"


def require_platform_admin(db: Session = Depends(get_db),
                           user: AuthenticatedUser = Depends(get_current_user)) -> AuthenticatedUser:
    if not db.scalar(select(Profile.is_platform_admin).where(Profile.id == user.id)):
        raise Forbidden("Réservé aux administrateurs de la plateforme")
    return user


def _framework(db: Session, code: str) -> AccountingFramework:
    fw = db.scalar(select(AccountingFramework).where(AccountingFramework.code == code))
    if fw is None:
        raise NotFound("Référentiel introuvable")
    return fw


def _version(db: Session, version_id: uuid.UUID) -> FrameworkVersion:
    v = db.get(FrameworkVersion, version_id)
    if v is None:
        raise NotFound("Version introuvable")
    return v


def _version_out(db: Session, v: FrameworkVersion) -> dict:
    counts = db.execute(text("""
        SELECT (SELECT count(*) FROM public.chart_of_accounts WHERE framework_version_id = :v) AS accounts,
               (SELECT count(*) FROM public.account_mappings
                 WHERE framework_version_id = :v AND organization_id IS NULL) AS mappings,
               (SELECT count(*) FROM public.statement_line_definitions WHERE framework_version_id = :v) AS lines,
               (SELECT count(*) FROM public.framework_concepts WHERE framework_version_id = :v) AS concepts
    """), {"v": v.id}).one()
    fw = db.get(AccountingFramework, v.framework_id)
    return {"id": v.id, "framework_code": fw.code, "framework_name": fw.name, "version_label": v.version_label,
            "effective_from": v.effective_from, "effective_to": v.effective_to,
            "source_reference": v.source_reference, "source_url": v.source_url, "status": v.status,
            "published_at": v.published_at, "notes": v.notes, "chart_sha256": v.chart_sha256,
            "mappings_sha256": v.mappings_sha256, "chart_loaded_at": v.chart_loaded_at,
            "mappings_loaded_at": v.mappings_loaded_at, "validation": v.validation,
            "account_count": counts.accounts, "mapping_count": counts.mappings,
            "structure_line_count": counts.lines, "concept_count": counts.concepts,
            "concept_total": len(CONCEPTS), "structure_sha256": v.structure_sha256,
            "concepts_sha256": v.concepts_sha256, "structure_loaded_at": v.structure_loaded_at,
            "concepts_loaded_at": v.concepts_loaded_at}


# ------------------------------------------------------------------------------ consultation
@router.get("/frameworks", summary="Référentiels comptables disponibles")
def list_frameworks(db: Session = Depends(get_db)):
    rows = db.execute(text("""
        SELECT f.id, f.code, f.name, f.description,
               count(v.id) FILTER (WHERE v.status = 'published') AS published_versions,
               count(v.id) AS versions
          FROM public.accounting_frameworks f
          LEFT JOIN public.framework_versions v ON v.framework_id = f.id
         GROUP BY f.id ORDER BY f.code
    """)).mappings().all()
    out = []
    for r in rows:
        d = dict(r)
        try:
            p = get_profile(r["code"])
            d.update(scope=p.scope, required_statements=[STATEMENT_LABELS[s] for s in p.required_statements],
                     profile_notes=list(p.notes))
        except ValueError:
            d.update(scope=None, required_statements=[], profile_notes=[])
        out.append(d)
    return out


@router.get("/frameworks/{code}/versions")
def list_versions(code: str, db: Session = Depends(get_db)):
    fw = _framework(db, code)
    versions = db.scalars(select(FrameworkVersion).where(FrameworkVersion.framework_id == fw.id)
                          .order_by(FrameworkVersion.effective_from.desc())).all()
    return [_version_out(db, v) for v in versions]


@router.get("/framework-versions/{version_id}")
def get_version(version_id: uuid.UUID, db: Session = Depends(get_db)):
    return _version_out(db, _version(db, version_id))


@router.get("/framework-versions/{version_id}/accounts", summary="Plan de comptes d'une version")
def list_accounts(version_id: uuid.UUID, q: str | None = None, account_class: int | None = None,
                  limit: int = 200, offset: int = 0, db: Session = Depends(get_db)):
    _version(db, version_id)
    stmt = select(ChartAccount).where(ChartAccount.framework_version_id == version_id)
    if account_class is not None:
        stmt = stmt.where(ChartAccount.account_class == account_class)
    if q:
        term = q.strip().replace("%", "").replace("_", "")[:100]
        stmt = stmt.where(ChartAccount.account_number.startswith(term) | ChartAccount.label.ilike(f"%{term}%"))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(ChartAccount.account_number).limit(max(1, min(limit, 1000)))
                      .offset(max(offset, 0))).all()
    return {"total": total, "items": [
        {"account_number": a.account_number, "label": a.label, "account_class": a.account_class,
         "parent_number": a.parent_number, "nature": a.nature, "normal_balance": a.normal_balance,
         "is_postable": a.is_postable} for a in rows]}


@router.get("/framework-versions/{version_id}/mappings", summary="Correspondances comptes -> rubriques")
def list_version_mappings(version_id: uuid.UUID, statement_type: str | None = None, db: Session = Depends(get_db)):
    _version(db, version_id)
    stmt = select(AccountMapping).where(AccountMapping.framework_version_id == version_id,
                                        AccountMapping.organization_id.is_(None))
    if statement_type:
        stmt = stmt.where(AccountMapping.statement_type == statement_type)
    rows = db.scalars(stmt.order_by(AccountMapping.statement_type, AccountMapping.line_code,
                                    AccountMapping.account_prefix)).all()
    return [{"statement_type": m.statement_type, "statement_label": STATEMENT_LABELS.get(m.statement_type),
             "line_code": m.line_code, "line_label": m.line_label, "account_prefix": m.account_prefix,
             "excluded_prefixes": m.excluded_prefixes, "balance_rule": m.balance_rule,
             "amount_column": m.amount_column, "sign": m.sign, "priority": m.priority,
             "source_reference": m.source_reference} for m in rows]


@router.get("/framework-templates/{kind}.csv", summary="Modèle de fichier (en-têtes seuls)")
def template(kind: Literal["chart", "mappings", "structure", "concepts"]):
    cols = {"chart": CHART_COLUMNS, "mappings": MAPPING_COLUMNS, "structure": STRUCTURE_COLUMNS,
            "concepts": CONCEPT_COLUMNS}[kind]
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(list(cols))
    return Response(content="﻿" + buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="modele-{kind}.csv"'})


# ------------------------------------------------------------------------------ administration
class VersionCreate(BaseModel):
    version_label: str = Field(min_length=1, max_length=60)
    effective_from: date
    effective_to: date | None = None
    source_reference: str = Field(min_length=10, max_length=1000,
                                  description="Référence précise du texte officiel (acte, date, publication)")
    source_url: HttpUrl | None = None
    notes: str | None = Field(default=None, max_length=4000)

    @model_validator(mode="after")
    def _dates(self) -> VersionCreate:
        if self.effective_to and self.effective_to <= self.effective_from:
            raise ValueError("La date de fin doit être postérieure à la date d'entrée en vigueur")
        return self


@router.post("/frameworks/{code}/versions", status_code=status.HTTP_201_CREATED)
def create_version(code: str, body: VersionCreate, request: Request, db: Session = Depends(get_db),
                   admin: AuthenticatedUser = Depends(require_platform_admin)):
    fw = _framework(db, code)
    get_profile(code)
    v = FrameworkVersion(framework_id=fw.id, version_label=body.version_label.strip(),
                         effective_from=body.effective_from, effective_to=body.effective_to,
                         source_reference=body.source_reference.strip(),
                         source_url=str(body.source_url) if body.source_url else None, notes=body.notes,
                         created_by=admin.id)
    db.add(v)
    db.flush()
    db.refresh(v)
    return _version_out(db, v)


def _draft(db: Session, version_id: uuid.UUID) -> FrameworkVersion:
    v = _version(db, version_id)
    if v.status != "draft":
        raise Conflict("Seule une version brouillon peut être modifiée.")
    return v


async def _read_rows(file: UploadFile) -> tuple[list[list[object]], str]:
    s = get_settings()
    data = await file.read(s.max_upload_size_mb * 1024 * 1024 + 1)
    try:
        vf = validate_upload(file.filename or "", data, max_bytes=s.max_upload_size_mb * 1024 * 1024,
                             allowed_extensions=["csv", "xlsx"])
        ext = readers.extract(vf.format, data)
    except FileRejected as exc:
        raise ReferenceRejected(str(exc)) from exc
    sheet = ext.sheets[0]
    return sheet.rows, sha256_hex(data)


def _report(issues: list[LoadIssue]) -> dict:
    return {"errors": sum(1 for i in issues if i.severity == "error"),
            "warnings": sum(1 for i in issues if i.severity == "warning"),
            "issues": [asdict(i) for i in issues]}


@router.post("/framework-versions/{version_id}/chart", summary="Charger le plan de comptes (remplace l'existant)")
async def upload_chart(version_id: uuid.UUID, request: Request, file: UploadFile = File(...),
                       db: Session = Depends(get_db), admin: AuthenticatedUser = Depends(require_platform_admin)):
    v = _draft(db, version_id)
    rows, digest = await _read_rows(file)
    result = parse_chart(rows)
    if result.has_errors:
        raise ReferenceRejected("Plan de comptes refusé : corrigez les anomalies listées.",
                                details=_report(result.issues))
    db.execute(delete(AccountMapping).where(AccountMapping.framework_version_id == v.id,
                                            AccountMapping.organization_id.is_(None)))
    db.execute(delete(ChartAccount).where(ChartAccount.framework_version_id == v.id))
    payload = [dict(framework_version_id=v.id, account_number=r.account_number, label=r.label,
                    account_class=r.account_class, parent_number=r.parent_number, nature=r.nature,
                    normal_balance=r.normal_balance, is_postable=r.is_postable, source_row=r.source_row)
               for r in result.records]
    for i in range(0, len(payload), 1000):
        db.execute(insert(ChartAccount), payload[i:i + 1000])
    v.chart_sha256, v.chart_loaded_at = digest, datetime.now(UTC)
    v.mappings_sha256 = v.mappings_loaded_at = None
    v.validation = None
    record_event(db, user_id=admin.id, action="framework.chart_loaded", entity_type="framework_versions",
                 entity_id=v.id, details={"accounts": len(payload), "sha256": digest, "filename": file.filename},
                 request=request)
    return {"loaded": len(payload), "mappings_cleared": True, **_report(result.issues)}


@router.post("/framework-versions/{version_id}/mappings",
             summary="Charger la table de correspondances comptes -> rubriques (remplace l'existante)")
async def upload_mappings(version_id: uuid.UUID, request: Request, file: UploadFile = File(...),
                          db: Session = Depends(get_db), admin: AuthenticatedUser = Depends(require_platform_admin)):
    v = _draft(db, version_id)
    chart = set(db.scalars(select(ChartAccount.account_number)
                           .where(ChartAccount.framework_version_id == v.id)).all())
    if not chart:
        raise Conflict("Chargez d'abord le plan de comptes de cette version.")
    rows, digest = await _read_rows(file)
    result = parse_mappings(rows, chart)
    if result.has_errors:
        raise ReferenceRejected("Correspondances refusées : corrigez les anomalies listées.",
                                details=_report(result.issues))
    db.execute(delete(AccountMapping).where(AccountMapping.framework_version_id == v.id,
                                            AccountMapping.organization_id.is_(None)))
    payload = [dict(framework_version_id=v.id, organization_id=None, statement_type=m.statement_type,
                    line_code=m.line_code, line_label=m.line_label, account_prefix=m.account_prefix,
                    excluded_prefixes=m.excluded_prefixes, balance_rule=m.balance_rule,
                    amount_column=m.amount_column, sign=m.sign, priority=m.priority,
                    source_reference=m.source_reference, source_row=m.source_row) for m in result.records]
    for i in range(0, len(payload), 1000):
        db.execute(insert(AccountMapping), payload[i:i + 1000])
    v.mappings_sha256, v.mappings_loaded_at = digest, datetime.now(UTC)
    v.validation = None
    record_event(db, user_id=admin.id, action="framework.mappings_loaded", entity_type="framework_versions",
                 entity_id=v.id, details={"mappings": len(payload), "sha256": digest, "filename": file.filename},
                 request=request)
    return {"loaded": len(payload), **_report(result.issues)}


def _validate(db: Session, v: FrameworkVersion) -> dict:
    fw = db.get(AccountingFramework, v.framework_id)
    chart = [ChartRecord(a.account_number, a.label, a.account_class, a.parent_number, a.nature, a.normal_balance,
                         a.is_postable, a.source_row or 0)
             for a in db.scalars(select(ChartAccount).where(ChartAccount.framework_version_id == v.id)).all()]
    mappings = [MappingRecord(m.statement_type, m.line_code, m.line_label, m.account_prefix,
                              list(m.excluded_prefixes or []), m.balance_rule, m.amount_column, m.sign, m.priority,
                              m.source_reference, m.source_row or 0)
                for m in db.scalars(select(AccountMapping).where(AccountMapping.framework_version_id == v.id,
                                                                 AccountMapping.organization_id.is_(None))).all()]
    structure = [StructureRecord(d.statement_type, d.line_code, d.label, d.display_order, d.kind,
                                 [tuple(x) for x in (d.total_formula or [])], d.total_formula_text, d.role, d.level,
                                 d.source_row or 0)
                 for d in db.scalars(select(StatementLineDefinition)
                                     .where(StatementLineDefinition.framework_version_id == v.id)).all()]
    concepts = db.scalar(select(func.count()).select_from(FrameworkConcept)
                         .where(FrameworkConcept.framework_version_id == v.id)) or 0
    issues = get_profile(fw.code).validate(chart, mappings, structure)
    if concepts < len(CONCEPTS):
        issues.append(LoadIssue("warning", "CONCEPTS_INCOMPLETE",
                                f"{len(CONCEPTS) - concepts} concept(s) d'analyse non liés : les indicateurs qui les "
                                "utilisent seront signalés « non calculables »."))
    report = {**_report(issues), "validated_at": datetime.now(UTC).isoformat(),
              "accounts": len(chart), "mappings": len(mappings), "structure_lines": len(structure),
              "concepts": concepts}
    return report


@router.post("/framework-versions/{version_id}/validate", summary="Vérifier qu'une version est publiable")
def validate_version(version_id: uuid.UUID, db: Session = Depends(get_db),
                     admin: AuthenticatedUser = Depends(require_platform_admin)):
    v = _draft(db, version_id)
    v.validation = _validate(db, v)
    db.flush()
    return _version_out(db, v)


@router.post("/framework-versions/{version_id}/publish",
             summary="Publier la version : elle devient applicable et définitivement figée")
def publish_version(version_id: uuid.UUID, request: Request, db: Session = Depends(get_db),
                    admin: AuthenticatedUser = Depends(require_platform_admin)):
    v = _draft(db, version_id)
    report = _validate(db, v)
    v.validation = report
    if report["errors"]:
        db.flush()
        raise Conflict("La version comporte des anomalies bloquantes : publication refusée.", details=report)
    v.status, v.published_at, v.published_by = "published", datetime.now(UTC), admin.id
    db.flush()   # contrainte d'exclusion : chevauchement de périodes -> 409
    record_event(db, user_id=admin.id, action="framework.published", entity_type="framework_versions",
                 entity_id=v.id, details={"chart_sha256": v.chart_sha256, "mappings_sha256": v.mappings_sha256},
                 request=request)
    return _version_out(db, v)


class DeprecateRequest(BaseModel):
    effective_to: date | None = None


@router.post("/framework-versions/{version_id}/deprecate", summary="Retirer une version publiée")
def deprecate_version(version_id: uuid.UUID, body: DeprecateRequest, request: Request, db: Session = Depends(get_db),
                      admin: AuthenticatedUser = Depends(require_platform_admin)):
    v = _version(db, version_id)
    if v.status != "published":
        raise Conflict("Seule une version publiée peut être retirée.")
    if body.effective_to:
        if body.effective_to <= v.effective_from:
            raise Conflict("Date de fin antérieure à l'entrée en vigueur.")
        v.effective_to = body.effective_to
    v.status = "deprecated"
    db.flush()
    record_event(db, user_id=admin.id, action="framework.deprecated", entity_type="framework_versions",
                 entity_id=v.id, request=request)
    return _version_out(db, v)


@router.delete("/framework-versions/{version_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_version(version_id: uuid.UUID, db: Session = Depends(get_db),
                   admin: AuthenticatedUser = Depends(require_platform_admin)):
    v = _draft(db, version_id)
    for model in (FrameworkConcept, StatementLineDefinition, AccountMapping, ChartAccount):
        db.execute(delete(model).where(model.framework_version_id == v.id))
    db.delete(v)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ------------------------------------------------------------------------------ structure des états et concepts
@router.get("/financial-concepts", tags=["Moteur financier"], summary="Concepts d'analyse à lier à chaque référentiel")
def list_concepts():
    return [{"code": c, "label": label, "definition": d} for c, (label, d) in CONCEPTS.items()]


@router.get("/framework-versions/{version_id}/structure", summary="Structure des états financiers")
def get_structure(version_id: uuid.UUID, db: Session = Depends(get_db)):
    _version(db, version_id)
    rows = db.scalars(select(StatementLineDefinition).where(StatementLineDefinition.framework_version_id == version_id)
                      .order_by(StatementLineDefinition.statement_type, StatementLineDefinition.display_order)).all()
    return [{"statement_type": r.statement_type, "statement_label": STATEMENT_LABELS.get(r.statement_type),
             "code": r.line_code, "label": r.label, "order": r.display_order, "kind": r.kind,
             "formula": r.total_formula_text, "role": r.role, "level": r.level} for r in rows]


@router.get("/framework-versions/{version_id}/concepts", summary="Concepts d'analyse liés à la version")
def get_concepts(version_id: uuid.UUID, db: Session = Depends(get_db)):
    _version(db, version_id)
    bound = {c.concept_code: c for c in db.scalars(select(FrameworkConcept)
                                                    .where(FrameworkConcept.framework_version_id == version_id)).all()}
    return [{"code": code, "label": label, "definition": d,
             "expression": bound[code].expression if code in bound else None,
             "source_reference": bound[code].source_reference if code in bound else None}
            for code, (label, d) in CONCEPTS.items()]


@router.post("/framework-versions/{version_id}/structure",
             summary="Charger la structure des états (remplace l'existante et efface les concepts)")
async def upload_structure(version_id: uuid.UUID, request: Request, file: UploadFile = File(...),
                           db: Session = Depends(get_db), admin: AuthenticatedUser = Depends(require_platform_admin)):
    v = _draft(db, version_id)
    rows, digest = await _read_rows(file)
    result = parse_structure(rows)
    if result.has_errors:
        raise ReferenceRejected("Structure refusée : corrigez les anomalies listées.", details=_report(result.issues))
    db.execute(delete(FrameworkConcept).where(FrameworkConcept.framework_version_id == v.id))
    db.execute(delete(StatementLineDefinition).where(StatementLineDefinition.framework_version_id == v.id))
    payload = [dict(framework_version_id=v.id, statement_type=r.statement_type, line_code=r.line_code, label=r.label,
                    display_order=r.display_order, kind=r.kind,
                    total_formula=[list(t) for t in r.formula] if r.kind == "total" else None,
                    total_formula_text=r.formula_text if r.kind == "total" else None, role=r.role, level=r.level,
                    source_row=r.source_row) for r in result.records]
    if payload:
        db.execute(insert(StatementLineDefinition), payload)
    v.structure_sha256, v.structure_loaded_at = digest, datetime.now(UTC)
    v.concepts_sha256 = v.concepts_loaded_at = None
    v.validation = None
    record_event(db, user_id=admin.id, action="framework.structure_loaded", entity_type="framework_versions",
                 entity_id=v.id, details={"lines": len(payload), "sha256": digest, "filename": file.filename},
                 request=request)
    return {"loaded": len(payload), "concepts_cleared": True, **_report(result.issues)}


@router.post("/framework-versions/{version_id}/concepts", summary="Charger les concepts d'analyse (remplace l'existant)")
async def upload_concepts(version_id: uuid.UUID, request: Request, file: UploadFile = File(...),
                          db: Session = Depends(get_db), admin: AuthenticatedUser = Depends(require_platform_admin)):
    v = _draft(db, version_id)
    codes = set(db.scalars(select(StatementLineDefinition.line_code)
                           .where(StatementLineDefinition.framework_version_id == v.id)).all())
    if not codes:
        raise Conflict("Chargez d'abord la structure des états de cette version.")
    rows, digest = await _read_rows(file)
    result = parse_concepts(rows, codes, set(CONCEPTS))
    if result.has_errors:
        raise ReferenceRejected("Concepts refusés : corrigez les anomalies listées.", details=_report(result.issues))
    db.execute(delete(FrameworkConcept).where(FrameworkConcept.framework_version_id == v.id))
    payload = [dict(framework_version_id=v.id, concept_code=c.concept_code, expression=c.expression,
                    expression_ast=c.expression_ast, source_reference=c.source_reference, source_row=c.source_row)
               for c in result.records]
    if payload:
        db.execute(insert(FrameworkConcept), payload)
    v.concepts_sha256, v.concepts_loaded_at = digest, datetime.now(UTC)
    v.validation = None
    record_event(db, user_id=admin.id, action="framework.concepts_loaded", entity_type="framework_versions",
                 entity_id=v.id, details={"concepts": len(payload), "sha256": digest, "filename": file.filename},
                 request=request)
    return {"loaded": len(payload), **_report(result.issues)}
