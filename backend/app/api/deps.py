"""Dépendances FastAPI : authentification, session RLS, contrôle d'accès."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from functools import lru_cache

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import Forbidden, NotFound, Unauthorized
from app.core.permissions import ORG_MANAGERS, CompanyRole, OrgRole, Permission, company_role_allows
from app.core.security import AuthError, AuthenticatedUser, TokenVerifier
from app.db.session import user_session

_bearer = HTTPBearer(auto_error=False)


@lru_cache
def get_verifier() -> TokenVerifier:
    s = get_settings()
    return TokenVerifier(
        audience=s.supabase_jwt_audience,
        hs256_secret=s.supabase_jwt_secret,
        jwks_url=s.supabase_jwks_url,
        issuer=f"{s.supabase_url.rstrip('/')}/auth/v1",
    )


def get_current_user(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> AuthenticatedUser:
    if creds is None or creds.scheme.lower() != "bearer":
        raise Unauthorized("Authentification requise")
    try:
        user = get_verifier().verify(creds.credentials)
    except AuthError as exc:
        raise Unauthorized(str(exc)) from exc
    request.state.user_id = str(user.id)
    return user


def get_db(request: Request, user: AuthenticatedUser = Depends(get_current_user)) -> Iterator[Session]:
    """Session transactionnelle soumise à RLS avec l'identité de l'appelant."""
    with user_session(user, request_id=getattr(request.state, "request_id", None)) as session:
        yield session


# ------------------------------------------------------------------ organisation
@dataclass(frozen=True)
class OrgContext:
    organization_id: uuid.UUID
    role: OrgRole
    user: AuthenticatedUser

    @property
    def is_manager(self) -> bool:
        return self.role in ORG_MANAGERS


def get_org_context(
    org_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(get_current_user),
) -> OrgContext:
    role = db.execute(text("SELECT authz.org_role(:org)"), {"org": org_id}).scalar_one_or_none()
    if role is None:
        # 404 plutôt que 403 : ne pas révéler l'existence d'une organisation tierce
        raise NotFound("Organisation introuvable")
    return OrgContext(organization_id=org_id, role=OrgRole(role), user=user)


def require_org_manager(ctx: OrgContext = Depends(get_org_context)) -> OrgContext:
    if not ctx.is_manager:
        raise Forbidden("Réservé aux propriétaires et administrateurs de l'organisation")
    return ctx


def require_org_owner(ctx: OrgContext = Depends(get_org_context)) -> OrgContext:
    if ctx.role != OrgRole.OWNER:
        raise Forbidden("Réservé au propriétaire de l'organisation")
    return ctx


# ------------------------------------------------------------------ entreprise
@dataclass(frozen=True)
class CompanyContext:
    company_id: uuid.UUID
    organization_id: uuid.UUID
    role: CompanyRole
    user: AuthenticatedUser

    def can(self, permission: Permission) -> bool:
        return company_role_allows(self.role, permission)

    def require(self, permission: Permission) -> None:
        if not self.can(permission):
            raise Forbidden("Votre rôle sur cette entreprise ne permet pas cette action",
                            details={"permission": permission.value, "role": self.role.value})


def get_company_context(
    company_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(get_current_user),
) -> CompanyContext:
    row = db.execute(
        text("SELECT c.organization_id, authz.company_role(c.id) AS role "
             "FROM public.companies c WHERE c.id = :id"),
        {"id": company_id},
    ).one_or_none()
    if row is None or row.role is None:
        raise NotFound("Entreprise introuvable")
    return CompanyContext(company_id=company_id, organization_id=row.organization_id,
                          role=CompanyRole(row.role), user=user)
