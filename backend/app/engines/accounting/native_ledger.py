"""Grand livre et balances calculés à partir des écritures natives validées.

Fonctions pures et déterministes (tri explicite, Decimal). Conventions :
- solde d'ouverture d'une période = écritures d'à-nouveaux de l'exercice + mouvements antérieurs au début de la période ;
- solde = débit − crédit ; solde de clôture présenté au débit s'il est positif, au crédit sinon ;
- balance « avant inventaire » : sans les écritures de travaux d'inventaire ;
  « après inventaire » : toutes les écritures validées."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

ZERO = Decimal("0.00")


@dataclass(frozen=True)
class Posted:
    """Ligne d'une écriture validée (ou extournée : elle reste comptabilisée, son extourne la neutralise)."""

    account: str
    entry_date: date
    debit: Decimal
    credit: Decimal
    origin: str = "manual"
    third_party: str | None = None
    journal: str | None = None
    number: str | None = None
    sequence: int = 0
    line_no: int = 0
    ref: object = None


def split_sides(balance: Decimal) -> tuple[Decimal, Decimal]:
    return (balance, ZERO) if balance > 0 else (ZERO, -balance)


def is_opening(p: Posted, period_from: date | None) -> bool:
    return p.origin == "opening" or (period_from is not None and p.entry_date < period_from)


def in_period(p: Posted, period_from: date | None, period_to: date | None) -> bool:
    return (period_from is None or p.entry_date >= period_from) and (period_to is None or p.entry_date <= period_to)


def _sort_key(p: Posted):
    return (p.entry_date, p.journal or "", p.sequence, p.line_no)


def ledger(lines: list[Posted], period_from: date | None = None, period_to: date | None = None) -> list[dict]:
    """Grand livre par compte : solde d'ouverture, lignes de la période avec solde progressif, totaux, solde final."""
    accounts: dict[str, dict] = {}
    for p in sorted(lines, key=_sort_key):
        a = accounts.setdefault(p.account, {"account": p.account, "opening": ZERO, "lines": [], "debit": ZERO, "credit": ZERO})
        if is_opening(p, period_from):
            a["opening"] += p.debit - p.credit
        elif in_period(p, period_from, period_to):
            a["lines"].append(p)
    out = []
    for acc in sorted(accounts):
        a = accounts[acc]
        running = a["opening"]
        rows = []
        for p in a["lines"]:
            running += p.debit - p.credit
            a["debit"] += p.debit
            a["credit"] += p.credit
            rows.append({"line": p, "balance": running})
        if not rows and a["opening"] == 0:
            continue
        out.append(
            {
                "account": acc,
                "opening": a["opening"],
                "rows": rows,
                "debit": a["debit"],
                "credit": a["credit"],
                "closing": running,
            }
        )
    return out


def trial_balance(
    lines: list[Posted], period_from: date | None = None, period_to: date | None = None, by_third_party: bool = False
) -> dict:
    """Balance : par compte (ou par compte et tiers), soldes d'ouverture, mouvements de la période, soldes de clôture,
    totaux et contrôle d'équilibre de chaque colonne."""
    rows: dict[tuple, dict] = {}
    for p in lines:
        opening = is_opening(p, period_from)
        if not opening and not in_period(p, period_from, period_to):
            continue
        key = (p.account, p.third_party if by_third_party else None)
        r = rows.setdefault(key, {"account": p.account, "third_party": key[1], "opening": ZERO, "debit": ZERO, "credit": ZERO})
        if opening:
            r["opening"] += p.debit - p.credit
        else:
            r["debit"] += p.debit
            r["credit"] += p.credit
    out = []
    tot = {k: ZERO for k in ("opening_debit", "opening_credit", "debit", "credit", "closing_debit", "closing_credit")}
    for key in sorted(rows, key=lambda k: (k[0], k[1] or "")):
        r = rows[key]
        od, oc = split_sides(r["opening"])
        cd, cc = split_sides(r["opening"] + r["debit"] - r["credit"])
        row = {
            "account": r["account"],
            "third_party": r["third_party"],
            "opening_debit": od,
            "opening_credit": oc,
            "debit": r["debit"],
            "credit": r["credit"],
            "closing_debit": cd,
            "closing_credit": cc,
        }
        if not any(row[k] for k in tot):
            continue
        for k in tot:
            tot[k] += row[k]
        out.append(row)
    checks = {
        "opening_balanced": tot["opening_debit"] == tot["opening_credit"],
        "movements_balanced": tot["debit"] == tot["credit"],
        "closing_balanced": tot["closing_debit"] == tot["closing_credit"],
    }
    return {"rows": out, "totals": tot, "checks": checks, "balanced": all(checks.values())}


def comparative(current: list[dict], previous: list[dict]) -> list[dict]:
    """Balance comparative : solde de clôture N et N-1 par compte (débit − crédit), écart."""

    def net(rows):
        out: dict[str, Decimal] = {}
        for r in rows:
            out[r["account"]] = out.get(r["account"], ZERO) + r["closing_debit"] - r["closing_credit"]
        return out

    n, p = net(current), net(previous)
    return [
        {"account": a, "current": n.get(a, ZERO), "previous": p.get(a, ZERO), "change": n.get(a, ZERO) - p.get(a, ZERO)}
        for a in sorted(set(n) | set(p))
    ]


def filter_scope(lines: list[Posted], scope: str) -> list[Posted]:
    if scope == "before_inventory":
        return [p for p in lines if p.origin != "inventory"]
    if scope in ("after_inventory", "final"):
        return list(lines)
    raise ValueError(f"Type de balance inconnu : {scope}")
