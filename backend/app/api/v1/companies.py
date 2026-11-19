from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import (
    CompanyContext,
    OrgContext,
    get_company_context,
    get_current_user,
    get_db,
    get_org_context,
    require_org_manager,
)
from app.core.errors import Conflict, NotFound
from app.core.permissions import Permission, permissions_for
from app.core.security import AuthenticatedUser
from app.models import AccountingFramework, AuditLog, Company, CompanyMember, OrganizationMember
from app.schemas.tenancy import (
    AuditLogOut,
    CompanyCreate,
    CompanyMemberCreate,
    CompanyMemberOut,
    CompanyOut,
    CompanyUpdate,
    Page,
)

router = APIRouter(tags=["Entreprises"])


def _company_out(c: Company, role: str | None) -> CompanyOut:
    data = {k: getattr(c, k) for k in CompanyOut.model_fields if hasattr(c, k)}
    data.update(framework_code=c.framework.code, framework_name=c.framework.name,
                my_role=role, my_permissions=permissions_for(role))
    return CompanyOut(**data)


@router.get("/organizations/{org_id}/companies", response_model=list[CompanyOut],
            summary="Entreprises accessibles dans l'organisation")
def list_companies(include_archived: bool = False, ctx: OrgContext = Depends(get_org_context),
                   db: Session = Depends(get_db)):
    stmt = (select(Company, func.authz.company_role(Company.id))
            .where(Company.organization_id == ctx.organization_id)
            .order_by(Company.name))
    if not include_archived:
        stmt = stmt.where(Company.archived_at.is_(None))
    # RLS filtre déjà les entreprises non attribuées aux simples membres
    return [_company_out(c, role) for c, role in db.execute(stmt).all()]


@router.post("/organizations/{org_id}/companies", response_model=CompanyOut,
             status_code=status.HTTP_201_CREATED)
def create_company(payload: CompanyCreate, ctx: OrgContext = Depends(require_org_manager),
                   db: Session = Depends(get_db), user: AuthenticatedUser = Depends(get_current_user)):
    framework = db.scalar(select(AccountingFramework).where(AccountingFramework.code == payload.framework_code))
    if framework is None:
        raise NotFound(f"Référentiel {payload.framework_code} non installé")
    data = payload.model_dump(exclude={"framework_code"})
    data["name"] = data["name"].strip()
    company = Company(organization_id=ctx.organization_id, framework_id=framework.id, created_by=user.id, **data)
    db.add(company)
    db.flush()
    db.refresh(company)
    return _company_out(company, "org_admin")


@router.get("/companies/{company_id}", response_model=CompanyOut)
def get_company(ctx: CompanyContext = Depends(get_company_context), db: Session = Depends(get_db)):
    company = db.get(Company, ctx.company_id)
    if company is None:
        raise NotFound("Entreprise introuvable")
    return _company_out(company, ctx.role.value)


@router.patch("/companies/{company_id}", response_model=CompanyOut)
def update_company(payload: CompanyUpdate, ctx: CompanyContext = Depends(get_company_context),
                   db: Session = Depends(get_db)):
    ctx.require(Permission.COMPANY_UPDATE)
    company = db.get(Company, ctx.company_id)
    if company is None:
        raise NotFound("Entreprise introuvable")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(company, field, value.strip() if isinstance(value, str) else value)
    db.flush()
    db.refresh(company)
    return _company_out(company, ctx.role.value)


@router.post("/companies/{company_id}/archive", response_model=CompanyOut)
def archive_company(ctx: CompanyContext = Depends(get_company_context), db: Session = Depends(get_db)):
    ctx.require(Permission.COMPANY_UPDATE)
    company = db.get(Company, ctx.company_id)
    if company is None:
        raise NotFound("Entreprise introuvable")
    if company.archived_at is not None:
        raise Conflict("Entreprise déjà archivée")
    company.archived_at = datetime.now(UTC)
    db.flush()
    return _company_out(company, ctx.role.value)


@router.post("/companies/{company_id}/restore", response_model=CompanyOut)
def restore_company(ctx: CompanyContext = Depends(get_company_context), db: Session = Depends(get_db)):
    ctx.require(Permission.COMPANY_UPDATE)
    company = db.get(Company, ctx.company_id)
    if company is None:
        raise NotFound("Entreprise introuvable")
    company.archived_at = None
    db.flush()
    return _company_out(company, ctx.role.value)


# ---------------------------------------------------------------- membres
@router.get("/companies/{company_id}/members", response_model=list[CompanyMemberOut])
def list_company_members(ctx: CompanyContext = Depends(get_company_context), db: Session = Depends(get_db)):
    members = db.scalars(select(CompanyMember).where(CompanyMember.company_id == ctx.company_id)).all()
    return [CompanyMemberOut(id=m.id, user_id=m.user_id, email=m.profile.email,
                             full_name=m.profile.full_name, role=m.role) for m in members]


@router.post("/companies/{company_id}/members", response_model=CompanyMemberOut,
             status_code=status.HTTP_201_CREATED,
             summary="Attribuer l'entreprise à un membre de l'organisation")
def add_company_member(payload: CompanyMemberCreate, ctx: CompanyContext = Depends(get_company_context),
                       db: Session = Depends(get_db)):
    ctx.require(Permission.COMPANY_MANAGE_MEMBERS)
    org_member = db.scalar(select(OrganizationMember).where(
        OrganizationMember.organization_id == ctx.organization_id,
        OrganizationMember.user_id == payload.user_id))
    if org_member is None:
        raise NotFound("Cet utilisateur n'est pas membre de l'organisation")
    existing = db.scalar(select(CompanyMember).where(
        CompanyMember.company_id == ctx.company_id, CompanyMember.user_id == payload.user_id))
    if existing:
        existing.role = payload.role
        member = existing
    else:
        member = CompanyMember(organization_id=ctx.organization_id, company_id=ctx.company_id,
                               user_id=payload.user_id, role=payload.role, granted_by=ctx.user.id)
        db.add(member)
    db.flush()
    db.refresh(member)
    return CompanyMemberOut(id=member.id, user_id=member.user_id, email=member.profile.email,
                            full_name=member.profile.full_name, role=member.role)


@router.delete("/companies/{company_id}/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_company_member(member_id: uuid.UUID, ctx: CompanyContext = Depends(get_company_context),
                          db: Session = Depends(get_db)):
    ctx.require(Permission.COMPANY_MANAGE_MEMBERS)
    member = db.get(CompanyMember, member_id)
    if member is None or member.company_id != ctx.company_id:
        raise NotFound("Attribution introuvable")
    db.delete(member)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/companies/{company_id}/audit-logs", response_model=Page[AuditLogOut])
def company_audit_logs(limit: int = 50, offset: int = 0, ctx: CompanyContext = Depends(get_company_context),
                       db: Session = Depends(get_db)):
    ctx.require(Permission.AUDIT_READ)
    limit = max(1, min(limit, 200))
    base = select(AuditLog).where(AuditLog.company_id == ctx.company_id)
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    items = db.scalars(base.order_by(AuditLog.created_at.desc()).limit(limit).offset(max(offset, 0))).all()
    return Page[AuditLogOut](items=[AuditLogOut.model_validate(i) for i in items],
                             total=total, limit=limit, offset=offset)
