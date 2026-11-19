from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import OrgContext, get_current_user, get_db, get_org_context, require_org_manager, require_org_owner
from app.core.config import get_settings
from app.core.errors import Conflict, Forbidden, NotFound
from app.core.permissions import OrgRole, can_assign_org_role
from app.core.security import AuthenticatedUser
from app.db.session import service_session
from app.models import AuditLog, Organization, OrganizationMember, Profile
from app.schemas.tenancy import (
    AuditLogOut,
    InviteResult,
    MemberInvite,
    MemberOut,
    MemberRoleUpdate,
    OrganizationCreate,
    OrganizationOut,
    OrganizationUpdate,
    Page,
)
from app.services.audit import record_event
from app.services.slugs import slugify
from app.services.supabase_admin import invite_user_by_email

router = APIRouter(prefix="/organizations", tags=["Organisations"])


def _org_out(org: Organization, role: str | None) -> OrganizationOut:
    out = OrganizationOut.model_validate(org)
    out.my_role = role  # type: ignore[assignment]
    return out


def _member_out(m: OrganizationMember) -> MemberOut:
    return MemberOut(id=m.id, user_id=m.user_id, email=m.profile.email, full_name=m.profile.full_name,
                     role=m.role, created_at=m.created_at)


@router.get("", response_model=list[OrganizationOut], summary="Organisations de l'utilisateur")
def list_organizations(db: Session = Depends(get_db), user: AuthenticatedUser = Depends(get_current_user)):
    rows = db.execute(
        select(Organization, OrganizationMember.role)
        .join(OrganizationMember, OrganizationMember.organization_id == Organization.id)
        .where(OrganizationMember.user_id == user.id, Organization.archived_at.is_(None))
        .order_by(Organization.name)
    ).all()
    return [_org_out(org, role) for org, role in rows]


@router.post("", response_model=OrganizationOut, status_code=status.HTTP_201_CREATED,
             summary="Créer une organisation (le créateur en devient propriétaire)")
def create_organization(payload: OrganizationCreate, db: Session = Depends(get_db),
                        user: AuthenticatedUser = Depends(get_current_user)):
    base_slug = payload.slug or slugify(payload.name)
    for attempt in range(10):
        slug = base_slug if attempt == 0 else f"{base_slug}-{uuid.uuid4().hex[:4]}"
        org = Organization(name=payload.name.strip(), slug=slug, org_type=payload.org_type,
                           country_code=payload.country_code, default_currency=payload.default_currency,
                           created_by=user.id)
        try:
            with db.begin_nested():
                db.add(org)
                db.flush()
            break
        except IntegrityError as exc:
            if payload.slug:  # identifiant imposé par l'utilisateur : on ne le modifie pas
                raise Conflict("Cet identifiant d'organisation est déjà utilisé") from exc
    else:
        raise Conflict("Impossible de générer un identifiant unique, précisez-en un")
    db.refresh(org)
    return _org_out(org, OrgRole.OWNER.value)


@router.get("/{org_id}", response_model=OrganizationOut)
def get_organization(ctx: OrgContext = Depends(get_org_context), db: Session = Depends(get_db)):
    org = db.get(Organization, ctx.organization_id)
    if org is None:
        raise NotFound("Organisation introuvable")
    return _org_out(org, ctx.role.value)


@router.patch("/{org_id}", response_model=OrganizationOut)
def update_organization(payload: OrganizationUpdate, ctx: OrgContext = Depends(require_org_manager),
                        db: Session = Depends(get_db)):
    org = db.get(Organization, ctx.organization_id)
    if org is None:
        raise NotFound("Organisation introuvable")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(org, field, value)
    db.flush()
    db.refresh(org)
    return _org_out(org, ctx.role.value)


class DeleteConfirmation(BaseModel):
    confirm_slug: str


@router.delete("/{org_id}", status_code=status.HTTP_204_NO_CONTENT,
               summary="Supprimer définitivement l'organisation et toutes ses données")
def delete_organization(body: DeleteConfirmation, ctx: OrgContext = Depends(require_org_owner),
                        db: Session = Depends(get_db)):
    org = db.get(Organization, ctx.organization_id)
    if org is None:
        raise NotFound("Organisation introuvable")
    if body.confirm_slug != org.slug:
        raise Conflict("Confirmation incorrecte : saisissez l'identifiant exact de l'organisation")
    db.delete(org)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ----------------------------------------------------------------------- membres
@router.get("/{org_id}/members", response_model=list[MemberOut])
def list_members(ctx: OrgContext = Depends(get_org_context), db: Session = Depends(get_db)):
    members = db.scalars(
        select(OrganizationMember).where(OrganizationMember.organization_id == ctx.organization_id)
        .order_by(OrganizationMember.created_at)
    ).all()
    return [_member_out(m) for m in members]


@router.post("/{org_id}/members", response_model=InviteResult, status_code=status.HTTP_201_CREATED,
             summary="Ajouter un membre (invitation par e-mail si le compte n'existe pas)")
def invite_member(payload: MemberInvite, request: Request, ctx: OrgContext = Depends(require_org_manager),
                  db: Session = Depends(get_db)):
    if not can_assign_org_role(ctx.role, payload.role):
        raise Forbidden("Seul un propriétaire peut attribuer le rôle « propriétaire »")

    email = payload.email.lower()
    # Recherche hors RLS, strictement limitée à la correspondance exacte de l'e-mail.
    with service_session() as svc:
        user_id = svc.scalar(select(Profile.id).where(func.lower(Profile.email) == email))

    invitation_sent = False
    if user_id is None:
        redirect = f"{get_settings().cors_origins[0]}/auth/callback"
        user_id = invite_user_by_email(email, redirect_to=redirect)
        invitation_sent = True

    exists = db.scalar(select(OrganizationMember.id).where(
        OrganizationMember.organization_id == ctx.organization_id, OrganizationMember.user_id == user_id))
    if exists:
        raise Conflict("Cet utilisateur est déjà membre de l'organisation")

    member = OrganizationMember(organization_id=ctx.organization_id, user_id=user_id,
                                role=payload.role, invited_by=ctx.user.id)
    db.add(member)
    db.flush()
    db.refresh(member)
    if invitation_sent:
        record_event(db, user_id=ctx.user.id, action="member.invitation_sent", entity_type="organization_members",
                     entity_id=member.id, organization_id=ctx.organization_id,
                     details={"email": email, "role": payload.role}, request=request)
    return InviteResult(member=_member_out(member), invitation_sent=invitation_sent)


def _get_member(db: Session, ctx: OrgContext, member_id: uuid.UUID) -> OrganizationMember:
    member = db.get(OrganizationMember, member_id)
    if member is None or member.organization_id != ctx.organization_id:
        raise NotFound("Membre introuvable")
    return member


@router.patch("/{org_id}/members/{member_id}", response_model=MemberOut)
def update_member_role(member_id: uuid.UUID, payload: MemberRoleUpdate,
                       ctx: OrgContext = Depends(require_org_manager), db: Session = Depends(get_db)):
    member = _get_member(db, ctx, member_id)
    if not can_assign_org_role(ctx.role, payload.role, current_role=member.role):
        raise Forbidden("Seul un propriétaire peut modifier le rôle d'un propriétaire ou nommer un propriétaire")
    member.role = payload.role
    db.flush()  # le trigger refuse la rétrogradation du dernier propriétaire
    return _member_out(member)


@router.delete("/{org_id}/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(member_id: uuid.UUID, ctx: OrgContext = Depends(get_org_context), db: Session = Depends(get_db)):
    member = _get_member(db, ctx, member_id)
    is_self = member.user_id == ctx.user.id
    if not is_self:
        if not ctx.is_manager:
            raise Forbidden("Réservé aux propriétaires et administrateurs de l'organisation")
        if member.role == OrgRole.OWNER and ctx.role != OrgRole.OWNER:
            raise Forbidden("Seul un propriétaire peut retirer un propriétaire")
    db.delete(member)
    db.flush()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ----------------------------------------------------------------------- audit
@router.get("/{org_id}/audit-logs", response_model=Page[AuditLogOut])
def org_audit_logs(limit: int = 50, offset: int = 0, ctx: OrgContext = Depends(require_org_manager),
                   db: Session = Depends(get_db)):
    limit = max(1, min(limit, 200))
    base = select(AuditLog).where(AuditLog.organization_id == ctx.organization_id)
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    items = db.scalars(base.order_by(AuditLog.created_at.desc()).limit(limit).offset(max(offset, 0))).all()
    return Page[AuditLogOut](items=[AuditLogOut.model_validate(i) for i in items],
                             total=total, limit=limit, offset=offset)


@router.get("/{org_id}/permissions", summary="Rôle de l'utilisateur dans l'organisation")
def my_org_permissions(ctx: OrgContext = Depends(get_org_context), db: Session = Depends(get_db)):
    can_create_company = bool(db.execute(
        text("SELECT authz.has_org_role(:o, ARRAY['owner','admin'])"), {"o": ctx.organization_id}).scalar())
    return {"role": ctx.role.value, "can_manage": ctx.is_manager, "can_create_company": can_create_company,
            "can_delete": ctx.role == OrgRole.OWNER}
