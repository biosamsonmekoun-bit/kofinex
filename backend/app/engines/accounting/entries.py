"""Écritures natives : contrôles d'une écriture, extourne, codes de lettrage.

Fonctions pures, en Decimal (jamais de float). Elles servent au contrôle préalable côté serveur et à l'affichage des
écarts ; la base de données refait les mêmes contrôles et reste l'autorité (migration 0014)."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

ZERO = Decimal("0.00")
CENT = Decimal("0.01")


class AmountError(ValueError):
    pass


def money(value) -> Decimal:
    """Montant saisi -> Decimal à deux décimales exactement, positif ou nul. Refuse les flottants et les fractions de centime."""
    if isinstance(value, float):
        raise AmountError("Montant transmis en virgule flottante : utiliser une chaîne décimale")
    if value is None or value == "":
        return ZERO
    try:
        d = Decimal(str(value).replace(" ", "").replace(" ", "").replace(",", "."))
    except InvalidOperation as exc:
        raise AmountError(f"Montant illisible : {value!r}") from exc
    if not d.is_finite():
        raise AmountError(f"Montant illisible : {value!r}")
    if d < 0:
        raise AmountError("Montant négatif : saisir au débit ou au crédit")
    if d != d.quantize(CENT):
        raise AmountError(f"Montant {d} : au plus deux décimales")
    return d.quantize(CENT)


@dataclass(frozen=True)
class Line:
    account: str
    debit: Decimal = ZERO
    credit: Decimal = ZERO
    third_party: str | None = None
    label: str | None = None


@dataclass(frozen=True)
class AccountInfo:
    active: bool = True
    requires_third_party: bool = False
    third_party_kind: str | None = None


@dataclass
class Check:
    total_debit: Decimal
    total_credit: Decimal
    issues: list[str] = field(default_factory=list)

    @property
    def difference(self) -> Decimal:
        return self.total_debit - self.total_credit

    @property
    def balanced(self) -> bool:
        return self.total_debit == self.total_credit

    @property
    def ok(self) -> bool:
        return not self.issues


def check_entry(
    lines: list[Line], accounts: dict[str, AccountInfo] | None = None, third_party_kinds: dict[str, str] | None = None
) -> Check:
    """Contrôles d'une écriture avant soumission : au moins deux lignes, un seul sens par ligne, montants positifs,
    équilibre débit = crédit, comptes ouverts et actifs, tiers sur les comptes collectifs et du bon type."""
    td = sum((ln.debit for ln in lines), ZERO)
    tc = sum((ln.credit for ln in lines), ZERO)
    chk = Check(td, tc)
    if len(lines) < 2:
        chk.issues.append("Au moins deux lignes sont nécessaires.")
    for i, ln in enumerate(lines, 1):
        if (ln.debit > 0) == (ln.credit > 0):
            chk.issues.append(f"Ligne {i} : un montant au débit ou au crédit, pas les deux ni aucun.")
        if ln.debit < 0 or ln.credit < 0:
            chk.issues.append(f"Ligne {i} : montant négatif.")
        if accounts is not None:
            info = accounts.get(ln.account)
            if info is None:
                chk.issues.append(f"Ligne {i} : compte {ln.account} non ouvert dans le plan de l'entreprise.")
                continue
            if not info.active:
                chk.issues.append(f"Ligne {i} : compte {ln.account} désactivé.")
            if info.requires_third_party and not ln.third_party:
                chk.issues.append(f"Ligne {i} : tiers obligatoire sur le compte collectif {ln.account}.")
            if ln.third_party and info.third_party_kind and third_party_kinds is not None:
                kind = third_party_kinds.get(ln.third_party)
                if kind is not None and kind != info.third_party_kind:
                    chk.issues.append(f"Ligne {i} : tiers d'un type incompatible avec le compte {ln.account}.")
    if not chk.balanced:
        chk.issues.append(f"Écriture déséquilibrée : débit {td}, crédit {tc}, écart {td - tc}.")
    if td == 0 and lines:
        chk.issues.append("Écriture à montant nul.")
    return chk


def reversal_lines(lines: list[Line]) -> list[Line]:
    """Extourne : mêmes comptes, tiers et montants, sens inversé (contrepassation)."""
    return [Line(ln.account, debit=ln.credit, credit=ln.debit, third_party=ln.third_party, label=ln.label) for ln in lines]


def lettering_code(n: int) -> str:
    """Codes de lettrage successifs : 1 -> A, 26 -> Z, 27 -> AA, 28 -> AB…"""
    if n < 1:
        raise ValueError("Rang de lettrage à partir de 1")
    out = ""
    while n:
        n, r = divmod(n - 1, 26)
        out = chr(65 + r) + out
    return out


def lettering_check(lines: list[Line]) -> Check:
    """Lettrage complet : au moins deux lignes, même compte et même tiers, débit = crédit."""
    td = sum((ln.debit for ln in lines), ZERO)
    tc = sum((ln.credit for ln in lines), ZERO)
    chk = Check(td, tc)
    if len(lines) < 2:
        chk.issues.append("Sélectionnez au moins deux lignes.")
    if len({(ln.account, ln.third_party) for ln in lines}) > 1:
        chk.issues.append("Les lignes lettrées ensemble portent le même compte et le même tiers.")
    if td != tc:
        chk.issues.append(f"Sélection non soldée : débit {td}, crédit {tc}, écart {td - tc}.")
    return chk
