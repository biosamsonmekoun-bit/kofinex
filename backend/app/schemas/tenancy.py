from __future__ import annotations

import re
import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

OrgRoleLiteral = Literal["owner", "admin", "member", "viewer"]
CompanyRoleLiteral = Literal["accountant", "controller", "analyst", "auditor", "viewer"]
OrgTypeLiteral = Literal["accounting_firm", "company", "group", "consulting", "audit", "non_profit"]

_SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")
_COUNTRY_RE = re.compile(r"^[A-Z]{2}$")


def _normalize_currency(v: str) -> str:
    v = v.upper()
    if not _CURRENCY_RE.match(v):
        raise ValueError("Code devise ISO 4217 attendu (ex. XOF, XAF, EUR)")
    return v


def _normalize_country(v: str) -> str:
    v = v.upper()
    if not _COUNTRY_RE.match(v):
        raise ValueError("Code pays ISO 3166-1 alpha-2 attendu (ex. CI, SN, CM)")
    return v


Currency = Annotated[str, AfterValidator(_normalize_currency)]
Country = Annotated[str, AfterValidator(_normalize_country)]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------- profils
class ProfileOut(ORM):
    id: uuid.UUID
    email: str
    full_name: str | None
    phone: str | None
    locale: str
    is_platform_admin: bool


class ProfileUpdate(BaseModel):
    full_name: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=40)
    locale: Literal["fr", "en"] | None = None


# ---------------------------------------------------------------- organisations
class OrganizationCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    slug: str | None = Field(default=None, max_length=80)
    org_type: OrgTypeLiteral = "company"
    country_code: Country | None = None
    default_currency: Currency = "XOF"

    @field_validator("slug")
    @classmethod
    def _slug(cls, v: str | None) -> str | None:
        if v is not None and not _SLUG_RE.match(v):
            raise ValueError("Identifiant invalide : minuscules, chiffres et tirets uniquement")
        return v


class OrganizationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    org_type: OrgTypeLiteral | None = None
    country_code: Country | None = None
    default_currency: Currency | None = None


class OrganizationOut(ORM):
    id: uuid.UUID
    name: str
    slug: str
    org_type: str
    country_code: str | None
    default_currency: str
    is_demo: bool
    created_at: datetime
    my_role: OrgRoleLiteral | None = None


# ---------------------------------------------------------------- membres
class MemberInvite(BaseModel):
    email: EmailStr
    role: OrgRoleLiteral = "member"


class MemberRoleUpdate(BaseModel):
    role: OrgRoleLiteral


class MemberOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    email: str
    full_name: str | None
    role: str
    created_at: datetime


class InviteResult(BaseModel):
    member: MemberOut
    invitation_sent: bool


# ---------------------------------------------------------------- entreprises
class CompanyBase(BaseModel):
    legal_name: str | None = Field(default=None, max_length=300)
    legal_form: str | None = Field(default=None, max_length=60)
    registration_number: str | None = Field(default=None, max_length=60)
    tax_id: str | None = Field(default=None, max_length=60)
    country_code: Country | None = None
    activity_sector: str | None = Field(default=None, max_length=200)
    address: str | None = Field(default=None, max_length=500)
    city: str | None = Field(default=None, max_length=120)


class CompanyCreate(CompanyBase):
    name: str = Field(min_length=2, max_length=200)
    framework_code: Literal["SYSCOHADA_REV", "SYSCEBNL"]
    currency: Currency = "XOF"
    fiscal_year_start_month: int = Field(default=1, ge=1, le=12)


class CompanyUpdate(CompanyBase):
    name: str | None = Field(default=None, min_length=2, max_length=200)


class CompanyOut(ORM):
    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    legal_name: str | None
    legal_form: str | None
    registration_number: str | None
    tax_id: str | None
    country_code: str | None
    currency: str
    framework_code: str
    framework_name: str
    activity_sector: str | None
    address: str | None
    city: str | None
    fiscal_year_start_month: int
    is_demo: bool
    archived_at: datetime | None
    created_at: datetime
    my_role: str | None = None
    my_permissions: list[str] = []


class CompanyMemberCreate(BaseModel):
    user_id: uuid.UUID
    role: CompanyRoleLiteral


class CompanyMemberOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    email: str
    full_name: str | None
    role: str


# ---------------------------------------------------------------- exercices
class FiscalYearCreate(BaseModel):
    label: str = Field(min_length=1, max_length=40)
    start_date: date
    end_date: date

    @model_validator(mode="after")
    def _dates(self) -> FiscalYearCreate:
        if self.end_date <= self.start_date:
            raise ValueError("La date de fin doit être postérieure à la date de début")
        months = (self.end_date.year - self.start_date.year) * 12 + self.end_date.month - self.start_date.month
        if months > 18:
            raise ValueError("Un exercice ne peut pas dépasser 18 mois")
        return self


class FiscalYearOut(ORM):
    id: uuid.UUID
    company_id: uuid.UUID
    label: str
    start_date: date
    end_date: date
    status: str
    closed_at: datetime | None
    created_at: datetime
    active_import_job_id: uuid.UUID | None = None
    active_ledger_import_job_id: uuid.UUID | None = None
    framework_version_id: uuid.UUID | None = None


# ---------------------------------------------------------------- référentiels
class FrameworkOut(ORM):
    id: uuid.UUID
    code: str
    name: str
    description: str | None
    published_versions: int = 0


# ---------------------------------------------------------------- audit
class AuditLogOut(ORM):
    id: uuid.UUID
    user_id: uuid.UUID | None
    action: str
    entity_type: str
    entity_id: uuid.UUID | None
    changes: dict | None
    created_at: datetime


class Page[T](BaseModel):
    items: list[T]
    total: int
    limit: int
    offset: int
