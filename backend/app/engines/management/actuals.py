"""Réalisé tiré de la balance validée et des saisies analytiques.

Conventions (explicites, restituées à l'utilisateur) :
- la nature d'une racine de compte (charge / produit) est lue dans le plan de comptes de la version
  de référentiel de l'exercice ; une racine absente du plan ou de nature bilancielle est refusée ;
- réalisé d'une charge = solde débiteur net (débit − crédit) des comptes de la racine ;
  réalisé d'un produit = solde créditeur net (crédit − débit) ;
- les saisies analytiques (`cost_entries`) sont des coûts, rattachés à un centre et à une date :
  elles seules permettent un réalisé mensuel tant que le grand livre n'est pas importé.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.engines.management import ZERO, ManagementError

PL_NATURES = {"charge", "produit"}


@dataclass(frozen=True)
class BalanceRow:
    account: str
    closing_debit: Decimal
    closing_credit: Decimal

    @property
    def net_debit(self) -> Decimal:
        return self.closing_debit - self.closing_credit


@dataclass(frozen=True)
class CostEntry:
    cost_center_id: str
    account: str | None
    entry_date: date
    amount: Decimal


def prefix_nature(prefix: str, chart_natures: dict[str, str | None]) -> str:
    """Nature de la racine : celle du compte du plan portant exactement ce numéro, sinon celle de la
    racine parente la plus longue présente dans le plan."""
    for k in range(len(prefix), 0, -1):
        n = chart_natures.get(prefix[:k])
        if n:
            if n not in PL_NATURES:
                raise ManagementError(f"Racine {prefix} : compte de nature « {n} ». Seuls les comptes de charges "
                                      "et de produits peuvent être budgétés et suivis en réalisé.")
            return n
    raise ManagementError(f"Racine {prefix} absente du plan de comptes de l'exercice.")


def balance_amount(rows: Iterable[BalanceRow], prefix: str, nature: str,
                   exclusions: Iterable[str] = ()) -> Decimal:
    ex = tuple(exclusions)
    total = sum((r.net_debit for r in rows if r.account.startswith(prefix)
                 and not any(r.account.startswith(x) for x in ex)), ZERO)
    return total if nature == "charge" else -total


def fiscal_period(fy_start: date, d: date) -> int:
    """Rang du mois dans l'exercice (1 = premier mois), quelle que soit la date de début."""
    return (d.year - fy_start.year) * 12 + d.month - fy_start.month + 1


def descendants(center_id: str, parent_of: dict[str, str | None]) -> set[str]:
    out = {center_id}
    changed = True
    while changed:
        changed = False
        for c, p in parent_of.items():
            if p in out and c not in out:
                out.add(c)
                changed = True
    return out


def cost_entries_by_period(entries: Iterable[CostEntry], centers: set[str], prefix: str | None,
                           fy_start: date) -> dict[int, Decimal]:
    out: dict[int, Decimal] = {}
    for e in entries:
        if e.cost_center_id not in centers:
            continue
        if prefix and not (e.account or "").startswith(prefix):
            continue
        p = fiscal_period(fy_start, e.entry_date)
        out[p] = out.get(p, ZERO) + e.amount
    return out
