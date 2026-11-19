"""Contrôles de cohérence d'une balance importée.

Chaque contrôle produit un résultat explicite (réussi, échoué, non exécuté avec la raison).
Gravité :
  * ``error``   : bloque la validation de l'import ;
  * ``warning`` : la validation exige une confirmation explicite de l'utilisateur ;
  * ``info``    : pour information.
Les contrôles qui s'appuient sur le plan de comptes ne s'exécutent qu'avec une version de
référentiel PUBLIÉE ; sinon ils sont signalés « non exécutés ».
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from typing import Literal

from app.engines.importing.balance import ZERO, BalanceLine, ImportOptions, ParseResult, RowIssue

MAX_LISTED = 25
GROUP_LABELS = {"opening": "soldes d'ouverture", "movement": "mouvements", "closing": "soldes de clôture"}


@dataclass
class ChartContext:
    """Plan de comptes d'une version publiée, réduit à ce dont les contrôles ont besoin."""
    version_label: str
    framework_code: str
    natures: dict[str, str | None]     # numéro -> nature (asset, liability, equity, income, expense…)

    def __post_init__(self) -> None:
        self.classes = {n[0] for n in self.natures}
        self._lengths = sorted({len(n) for n in self.natures}, reverse=True)

    def match(self, account: str) -> str | None:
        """Compte du plan le plus spécifique dont ``account`` est un sous-compte (ou lui-même)."""
        for length in self._lengths:
            if length <= len(account) and account[:length] in self.natures:
                return account[:length]
        return None

    def nature(self, account: str) -> str | None:
        m = self.match(account)
        return self.natures.get(m) if m else None


@dataclass
class ControlResult:
    code: str
    title: str
    status: Literal["passed", "failed", "skipped"]
    severity: Literal["error", "warning", "info"]
    message: str
    details: dict = field(default_factory=dict)


@dataclass
class ControlReport:
    results: list[ControlResult]
    totals: dict[str, dict[str, str]]
    line_count: int

    @property
    def blocking(self) -> bool:
        return any(r.status == "failed" and r.severity == "error" for r in self.results)

    @property
    def requires_acknowledgment(self) -> bool:
        return any(r.status == "failed" and r.severity == "warning" for r in self.results)

    def to_dict(self) -> dict:
        return {"results": [asdict(r) for r in self.results], "totals": self.totals,
                "line_count": self.line_count, "blocking": self.blocking,
                "requires_acknowledgment": self.requires_acknowledgment}


def _fmt(d: Decimal) -> str:
    return f"{d:,.2f}".replace(",", " ").replace(".", ",")


def run_controls(parsed: ParseResult, options: ImportOptions, *, chart: ChartContext | None = None,
                 previous_closing: dict[str, Decimal] | None = None) -> ControlReport:
    results: list[ControlResult] = []
    add = results.append

    # ---------------------------------------------------------------- comptes agrégés
    _aggregate_accounts(parsed, options, add)

    lines = parsed.valid
    errors = parsed.errors

    # ---------------------------------------------------------------- lignes illisibles
    if errors:
        add(ControlResult("ROW_ERRORS", "Lignes illisibles", "failed", "error",
                          f"{len(errors)} ligne(s) ne peuvent pas être lues ; corrigez le fichier ou l'association "
                          "des colonnes.",
                          {"rows": [{"row": e.source_row, "issues": [i.message for i in e.issues]}
                                    for e in errors[:MAX_LISTED]], "count": len(errors)}))
    else:
        add(ControlResult("ROW_ERRORS", "Lignes illisibles", "passed", "error", "Toutes les lignes ont été lues."))

    if not lines:
        add(ControlResult("BALANCE_EMPTY", "Balance vide", "failed", "error", "Aucune ligne de compte exploitable."))
        return ControlReport(results, {}, 0)

    # ---------------------------------------------------------------- doublons
    by_account: dict[str, list[int]] = defaultdict(list)
    for line in lines:
        by_account[line.account_number or ""].append(line.source_row)
    dups = {a: r for a, r in by_account.items() if len(r) > 1}
    if dups:
        add(ControlResult("DUPLICATE_ACCOUNT", "Comptes en double", "failed", "error",
                          f"{len(dups)} compte(s) apparaissent plusieurs fois.",
                          {"accounts": [{"account": a, "rows": r} for a, r in list(dups.items())[:MAX_LISTED]]}))
    else:
        add(ControlResult("DUPLICATE_ACCOUNT", "Comptes en double", "passed", "error", "Aucun compte en double."))

    # ---------------------------------------------------------------- équilibres
    totals: dict[str, dict[str, str]] = {}
    for g in ("opening", "movement", "closing"):
        computed_only = g == "closing" and "closing" not in parsed.mapped_groups
        if g not in parsed.mapped_groups and not computed_only:
            add(ControlResult(f"{g.upper()}_BALANCED", f"Équilibre des {GROUP_LABELS[g]}", "skipped", "error",
                              "Colonnes non fournies dans le fichier."))
            continue
        d = sum((getattr(x, f"{g}_debit") or ZERO for x in lines), ZERO)
        c = sum((getattr(x, f"{g}_credit") or ZERO for x in lines), ZERO)
        diff = d - c
        totals[g] = {"debit": str(d), "credit": str(c), "difference": str(diff)}
        title = f"Équilibre des {GROUP_LABELS[g]}"
        if diff == ZERO:
            add(ControlResult(f"{g.upper()}_BALANCED", title, "passed", "error",
                              f"Total débit = total crédit = {_fmt(d)}."))
        elif options.balance_tolerance > ZERO and abs(diff) <= options.balance_tolerance:
            add(ControlResult(f"{g.upper()}_BALANCED", title, "failed", "warning",
                              f"Écart de {_fmt(diff)} dans la tolérance de {_fmt(options.balance_tolerance)}.",
                              {"debit": str(d), "credit": str(c), "difference": str(diff)}))
        else:
            add(ControlResult(f"{g.upper()}_BALANCED", title, "failed", "error",
                              f"Total débit {_fmt(d)} ≠ total crédit {_fmt(c)} (écart {_fmt(diff)}).",
                              {"debit": str(d), "credit": str(c), "difference": str(diff)}))

    # ---------------------------------------------------------------- arithmétique par ligne
    if {"opening", "movement", "closing"} <= parsed.mapped_groups:
        bad = [x for x in lines if x.net("closing") != x.net("opening") + x.net("movement")]
        if bad:
            add(ControlResult("ROW_ARITHMETIC", "Solde = ouverture + mouvements", "failed", "error",
                              f"{len(bad)} compte(s) dont le solde de clôture ne correspond pas à l'ouverture "
                              "augmentée des mouvements. Si les mouvements incluent déjà les à-nouveaux, "
                              "n'associez pas les colonnes d'ouverture.",
                              {"rows": [{"row": x.source_row, "account": x.account_number,
                                         "expected": str(x.net("opening") + x.net("movement")),
                                         "found": str(x.net("closing"))} for x in bad[:MAX_LISTED]],
                               "count": len(bad)}))
        else:
            add(ControlResult("ROW_ARITHMETIC", "Solde = ouverture + mouvements", "passed", "error",
                              "Chaque solde de clôture est égal à l'ouverture augmentée des mouvements."))
    else:
        add(ControlResult("ROW_ARITHMETIC", "Solde = ouverture + mouvements", "skipped", "error",
                          "Contrôle possible uniquement si ouverture, mouvements et clôture sont fournis."))

    # ---------------------------------------------------------------- soldes à double sens
    both = [x for x in lines if (x.closing_debit or ZERO) > 0 and (x.closing_credit or ZERO) > 0]
    if both:
        add(ControlResult("CLOSING_BOTH_SIDES", "Soldes débiteurs et créditeurs simultanés", "failed", "warning",
                          f"{len(both)} compte(s) ont à la fois un solde débiteur et un solde créditeur.",
                          {"accounts": [x.account_number for x in both[:MAX_LISTED]]}))
    else:
        add(ControlResult("CLOSING_BOTH_SIDES", "Soldes débiteurs et créditeurs simultanés", "passed", "warning",
                          "Chaque compte présente un solde unique."))

    # ---------------------------------------------------------------- totaux déclarés
    _declared_totals(parsed, lines, add)

    # ---------------------------------------------------------------- OCR
    low = [x for x in lines if any(i.code == "OCR_LOW_CONFIDENCE" for i in x.issues)]
    if any(x.min_confidence is not None for x in lines):
        if low:
            add(ControlResult("OCR_CONFIDENCE", "Fiabilité de la lecture OCR", "failed", "warning",
                              f"{len(low)} ligne(s) lues avec une confiance faible : comparez-les au document.",
                              {"rows": [x.source_row for x in low[:MAX_LISTED]], "count": len(low)}))
        else:
            add(ControlResult("OCR_CONFIDENCE", "Fiabilité de la lecture OCR", "passed", "warning",
                              "Toutes les lignes ont été lues avec une confiance suffisante."))

    # ---------------------------------------------------------------- plan de comptes
    if chart is None:
        add(ControlResult("CHART_CONTROLS", "Contrôles par le plan de comptes", "skipped", "info",
                          "Aucune version publiée du référentiel n'est applicable à cet exercice : contrôles des "
                          "classes, des comptes inconnus et des à-nouveaux non exécutés."))
    else:
        _chart_controls(lines, chart, add)
        _opening_vs_previous(lines, parsed, chart, previous_closing, add)

    return ControlReport(results, totals, len(lines))


def _aggregate_accounts(parsed: ParseResult, options: ImportOptions, add) -> None:
    lines = parsed.valid
    numbers = sorted({x.account_number for x in lines if x.account_number})
    by_num = {x.account_number: x for x in lines}
    aggregates: list[BalanceLine] = []
    # liste triée : les sous-comptes d'un compte le suivent immédiatement
    for i, a in enumerate(numbers):
        j = i + 1
        leaves: list[str] = []
        while j < len(numbers) and numbers[j].startswith(a):
            n = numbers[j]
            if not (j + 1 < len(numbers) and numbers[j + 1].startswith(n)):
                leaves.append(n)
            j += 1
        if not leaves:
            continue
        leaf_net = sum((by_num[n].net("closing") for n in leaves), ZERO)
        if by_num[a].net("closing") == leaf_net:
            aggregates.append(by_num[a])
    if not aggregates:
        add(ControlResult("AGGREGATE_ACCOUNTS", "Comptes de regroupement", "passed", "warning",
                          "Aucun compte de regroupement détecté (pas de double comptage)."))
        return
    if options.exclude_aggregate_accounts:
        for x in aggregates:
            x.status = "skipped"
            x.issues.append(RowIssue("AGGREGATE_EXCLUDED", "Compte de regroupement exclu (total de ses sous-comptes).",
                                     severity="info"))
        add(ControlResult("AGGREGATE_ACCOUNTS", "Comptes de regroupement", "passed", "warning",
                          f"{len(aggregates)} compte(s) de regroupement exclus du calcul.",
                          {"accounts": [x.account_number for x in aggregates[:MAX_LISTED]]}))
    else:
        add(ControlResult("AGGREGATE_ACCOUNTS", "Comptes de regroupement", "failed", "error",
                          f"{len(aggregates)} compte(s) totalisent leurs sous-comptes : "
                          "ils seraient comptés deux fois. "
                          "Activez l'option « exclure les comptes de regroupement ».",
                          {"accounts": [x.account_number for x in aggregates[:MAX_LISTED]]}))


_CLASS_RE = re.compile(r"(?i)classe\s*([0-9])")


def _declared_totals(parsed: ParseResult, lines: list[BalanceLine], add) -> None:
    if not parsed.declared_totals:
        add(ControlResult("DECLARED_TOTALS", "Totaux figurant dans le fichier", "skipped", "error",
                          "Le fichier ne comporte pas de ligne de total."))
        return
    mismatches = []
    checked = 0
    general = None
    for t in parsed.declared_totals:
        m = _CLASS_RE.search(t.label)
        scope = [x for x in lines if x.account_number and x.account_number.startswith(m.group(1))] if m else None
        if scope is None:
            general = t
            continue
        checked += 1
        mismatches += _compare_total(t, scope, f"classe {m.group(1)}")
    if general is not None:          # dernier total non rattaché à une classe = total général
        checked += 1
        mismatches += _compare_total(general, lines, "total général")
    if mismatches:
        add(ControlResult("DECLARED_TOTALS", "Totaux figurant dans le fichier", "failed", "error",
                          f"{len(mismatches)} total(aux) du fichier diffèrent des montants recalculés "
                          "(ligne manquante, illisible ou mal associée).", {"mismatches": mismatches[:MAX_LISTED]}))
    else:
        add(ControlResult("DECLARED_TOTALS", "Totaux figurant dans le fichier", "passed", "error",
                          f"{checked} total(aux) du fichier concordent avec les montants recalculés."))


def _compare_total(t, scope: list[BalanceLine], label: str) -> list[dict]:
    out = []
    for f, declared in t.values.items():
        if f.endswith("_balance"):
            g = f.removesuffix("_balance")
            computed = sum((x.net(g) for x in scope), ZERO)
        else:
            computed = sum((getattr(x, f) or ZERO for x in scope), ZERO)
        if computed != declared:
            out.append({"row": t.source_row, "scope": label, "field": f,
                        "declared": str(declared), "computed": str(computed)})
    return out


def _chart_controls(lines: list[BalanceLine], chart: ChartContext, add) -> None:
    bad_class = [x for x in lines if x.account_number and x.account_number[0] not in chart.classes]
    if bad_class:
        add(ControlResult("ACCOUNT_CLASS", "Classes de comptes", "failed", "error",
                          f"{len(bad_class)} compte(s) n'appartiennent à aucune classe du référentiel "
                          f"{chart.framework_code} {chart.version_label}.",
                          {"accounts": [x.account_number for x in bad_class[:MAX_LISTED]]}))
    else:
        add(ControlResult("ACCOUNT_CLASS", "Classes de comptes", "passed", "error",
                          f"Tous les comptes relèvent des classes du référentiel {chart.version_label}."))
    unknown = [x for x in lines if x.account_number and x.account_number[0] in chart.classes
               and chart.match(x.account_number) is None]
    if unknown:
        add(ControlResult("UNKNOWN_ACCOUNTS", "Comptes absents du plan", "failed", "warning",
                          f"{len(unknown)} compte(s) ne se rattachent à aucun compte du plan {chart.version_label} : "
                          "ils ne pourront pas être classés dans les états financiers.",
                          {"accounts": [{"account": x.account_number, "label": x.account_label}
                                        for x in unknown[:MAX_LISTED]], "count": len(unknown)}))
    else:
        add(ControlResult("UNKNOWN_ACCOUNTS", "Comptes absents du plan", "passed", "warning",
                          "Tous les comptes se rattachent au plan de comptes."))


_BALANCE_SHEET_NATURES = {"asset", "liability", "equity", "mixed"}   # mixed : tiers, trésorerie


def _opening_vs_previous(lines: list[BalanceLine], parsed: ParseResult, chart: ChartContext,
                         previous: dict[str, Decimal] | None, add) -> None:
    title = "À-nouveaux = clôture de l'exercice précédent"
    if "opening" not in parsed.mapped_groups:
        add(ControlResult("OPENING_VS_PREVIOUS", title, "skipped", "warning", "Soldes d'ouverture non fournis."))
        return
    if previous is None:
        add(ControlResult("OPENING_VS_PREVIOUS", title, "skipped", "warning",
                          "Pas de balance validée pour l'exercice précédent."))
        return
    current = {x.account_number: x.net("opening") for x in lines if x.account_number}
    accounts = {a for a in set(current) | set(previous) if chart.nature(a) in _BALANCE_SHEET_NATURES}
    if not accounts:
        add(ControlResult("OPENING_VS_PREVIOUS", title, "skipped", "warning",
                          "La nature des comptes (bilan / gestion) n'est pas renseignée dans le plan publié."))
        return
    diffs = [{"account": a, "previous_closing": str(previous.get(a, ZERO)), "opening": str(current.get(a, ZERO))}
             for a in sorted(accounts) if previous.get(a, ZERO) != current.get(a, ZERO)]
    if diffs:
        add(ControlResult("OPENING_VS_PREVIOUS", title, "failed", "warning",
                          f"{len(diffs)} compte(s) de bilan dont l'ouverture diffère de la clôture précédente.",
                          {"accounts": diffs[:MAX_LISTED], "count": len(diffs)}))
    else:
        add(ControlResult("OPENING_VS_PREVIOUS", title, "passed", "warning",
                          f"Les à-nouveaux des {len(accounts)} comptes de bilan concordent."))
