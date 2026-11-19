"""Schémas d'entrée de la comptabilité native (lot 3B). Les montants sont transmis en chaînes décimales (jamais en
nombre flottant) et convertis en Decimal par le moteur ; la base refait tous les contrôles."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

ThirdPartyKind = Literal["customer", "supplier", "employee", "tax_authority", "social_body", "other"]
JournalType = Literal["purchases", "sales", "bank", "cash", "general", "payroll", "fixed_assets", "inventory", "opening"]
Amount = str | int | None


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SettingsIn(_In):
    review_required: bool
    segregation_required: bool


class AccountIn(_In):
    account_number: str = Field(pattern=r"^[1-9][0-9]{1,19}$")
    label: str = Field(min_length=1, max_length=200)
    requires_third_party: bool = False
    third_party_kind: ThirdPartyKind | None = None
    lettering_enabled: bool = False


class AccountPatch(_In):
    label: str | None = Field(None, min_length=1, max_length=200)
    is_active: bool | None = None
    requires_third_party: bool | None = None
    third_party_kind: ThirdPartyKind | None = None
    lettering_enabled: bool | None = None


class ChartImportIn(_In):
    classes: list[int] | None = Field(None, description="Classes du plan à ouvrir (1 à 9) ; toutes si absent")

    @field_validator("classes")
    @classmethod
    def _classes(cls, v):
        if v and any(c < 1 or c > 9 for c in v):
            raise ValueError("Classes 1 à 9")
        return v


class ThirdPartyIn(_In):
    code: str = Field(pattern=r"^[A-Za-z0-9._-]{1,30}$")
    name: str = Field(min_length=1, max_length=200)
    kind: ThirdPartyKind
    collective_account_number: str | None = None
    tax_id: str | None = Field(None, max_length=50)
    registration_number: str | None = Field(None, max_length=50)
    address: str | None = Field(None, max_length=300)
    city: str | None = Field(None, max_length=100)
    country_code: str | None = Field(None, pattern=r"^[A-Z]{2}$")
    email: str | None = Field(None, max_length=200)
    phone: str | None = Field(None, max_length=50)
    is_active: bool = True


class ThirdPartyPatch(ThirdPartyIn):
    code: str | None = Field(None, pattern=r"^[A-Za-z0-9._-]{1,30}$")
    name: str | None = Field(None, min_length=1, max_length=200)
    kind: ThirdPartyKind | None = None
    is_active: bool | None = None


class JournalIn(_In):
    code: str = Field(pattern=r"^[A-Z0-9]{1,8}$")
    label: str = Field(min_length=1, max_length=120)
    journal_type: JournalType
    number_prefix: str | None = Field(None, pattern=r"^[A-Z0-9_-]{0,12}$")
    counterpart_account_number: str | None = None
    allowed_users: list[uuid.UUID] | None = None
    is_active: bool = True


class JournalPatch(_In):
    code: str | None = Field(None, pattern=r"^[A-Z0-9]{1,8}$")
    label: str | None = Field(None, min_length=1, max_length=120)
    journal_type: JournalType | None = None
    number_prefix: str | None = Field(None, pattern=r"^[A-Z0-9_-]{0,12}$")
    counterpart_account_number: str | None = None
    allowed_users: list[uuid.UUID] | None = None
    is_active: bool | None = None


class LineIn(_In):
    account_number: str = Field(min_length=2, max_length=20)
    third_party_id: uuid.UUID | None = None
    label: str | None = Field(None, max_length=200)
    debit: Amount = None
    credit: Amount = None
    cost_center_id: uuid.UUID | None = None
    currency: str | None = Field(None, pattern=r"^[A-Z]{3}$")
    currency_amount: Amount = None


class EntryIn(_In):
    fiscal_year_id: uuid.UUID
    journal_id: uuid.UUID
    entry_date: date
    piece_ref: str | None = Field(None, max_length=60)
    piece_date: date | None = None
    label: str = Field(min_length=1, max_length=200)
    third_party_id: uuid.UUID | None = None
    lines: list[LineIn] = Field(default_factory=list, max_length=500)


class EntryPatch(_In):
    journal_id: uuid.UUID | None = None
    entry_date: date | None = None
    piece_ref: str | None = Field(None, max_length=60)
    piece_date: date | None = None
    label: str | None = Field(None, min_length=1, max_length=200)
    third_party_id: uuid.UUID | None = None
    lines: list[LineIn] | None = Field(None, max_length=500)


class TransitionIn(_In):
    action: Literal["submit", "withdraw", "start_review", "validate", "reject", "reopen"]
    reason: str | None = Field(None, max_length=1000)


class ReverseIn(_In):
    entry_date: date
    label: str | None = Field(None, max_length=200)
    with_correction: bool = False


class LetterIn(_In):
    line_ids: list[uuid.UUID] = Field(min_length=2, max_length=500)
