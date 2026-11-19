"""Production des états financiers à partir d'une balance validée.

Les trois ingrédients viennent de la version PUBLIÉE du référentiel :
  * la structure des états (lignes, ordre, lignes de total et leurs formules, rôles) ;
  * les correspondances racine de compte -> ligne (règle de solde, colonne, signe, priorité) ;
  * la balance de l'exercice.
Le moteur applique ces données sans y ajouter de règle. Chaque montant conserve la liste des
comptes et des correspondances qui l'ont produit (``trace``).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal

ZERO = Decimal("0.00")
COLUMNS = ("gross", "depreciation", "net")
CORE_STATEMENTS = ("balance_sheet_assets", "balance_sheet_liabilities", "income_statement")
ROLES = {"total_actif": "balance_sheet_assets", "total_passif": "balance_sheet_liabilities",
         "resultat_bilan": "balance_sheet_liabilities", "resultat_compte_resultat": "income_statement"}


@dataclass(frozen=True)
class TBEntry:
    account_number: str
    account_label: str | None
    opening_debit: Decimal
    opening_credit: Decimal
    movement_debit: Decimal
    movement_credit: Decimal
    closing_debit: Decimal
    closing_credit: Decimal

    @property
    def closing_net(self) -> Decimal:
        return self.closing_debit - self.closing_credit


@dataclass(frozen=True)
class LineDef:
    statement_type: str
    code: str
    label: str
    order: int
    kind: str                                  # detail | total | title
    formula: tuple[tuple[int, str], ...] = ()  # lignes de total : ((+1, "AE"), (-1, "AF"), …)
    role: str | None = None
    level: int = 0


@dataclass(frozen=True)
class MappingRule:
    statement_type: str
    line_code: str
    account_prefix: str
    excluded_prefixes: tuple[str, ...]
    balance_rule: str
    amount_column: str
    sign: int
    priority: int


def rule_amount(entry: TBEntry, rule: str) -> Decimal:
    net = entry.closing_net
    if rule == "debit_balance":
        return net if net > 0 else ZERO
    if rule == "credit_balance":
        return -net if net < 0 else ZERO
    if rule == "net_debit":
        return net
    if rule == "net_credit":
        return -net
    if rule == "debit_movements":
        return entry.movement_debit
    if rule == "credit_movements":
        return entry.movement_credit
    raise ValueError(f"Règle inconnue : {rule}")


def account_amount(entries: list[TBEntry], prefix: str, rule: str) -> Decimal:
    return sum((rule_amount(e, rule) for e in entries if e.account_number.startswith(prefix)), ZERO)


@dataclass
class LineResult:
    definition: LineDef
    gross: Decimal | None = None
    depreciation: Decimal | None = None
    net: Decimal | None = None
    trace: list[dict] = field(default_factory=list)

    def value(self, column: str = "net") -> Decimal:
        v = getattr(self, column)
        return v if v is not None else ZERO


@dataclass
class StatementControl:
    code: str
    status: str            # passed | failed | skipped
    severity: str          # critical | warning | info
    message: str
    details: dict = field(default_factory=dict)


@dataclass
class StatementsResult:
    statements: dict[str, list[LineResult]]
    controls: list[StatementControl]
    unmapped: list[dict]

    def line(self, code: str) -> LineResult | None:
        for lines in self.statements.values():
            for ln in lines:
                if ln.definition.code == code:
                    return ln
        return None

    def values(self) -> dict[str, dict[str, Decimal | None]]:
        return {ln.definition.code: {"gross": ln.gross, "depreciation": ln.depreciation, "net": ln.net}
                for lines in self.statements.values() for ln in lines}


class StatementError(ValueError):
    pass


def _select(rules: list[MappingRule], account: str) -> list[MappingRule]:
    """Correspondances applicables à un compte : pour chaque (état, colonne, règle), la racine la
    plus longue l'emporte, puis la priorité la plus basse."""
    groups: dict[tuple[str, str, str], list[MappingRule]] = defaultdict(list)
    for r in rules:
        if account.startswith(r.account_prefix) and not any(account.startswith(x) for x in r.excluded_prefixes):
            groups[(r.statement_type, r.amount_column, r.balance_rule)].append(r)
    chosen = []
    for candidates in groups.values():
        candidates.sort(key=lambda r: (-len(r.account_prefix), r.priority, r.line_code))
        best = candidates[0]
        if len(candidates) > 1:
            second = candidates[1]
            if (len(second.account_prefix), second.priority) == (len(best.account_prefix), best.priority) \
                    and second.line_code != best.line_code:
                raise StatementError(f"Compte {account} : correspondances ambiguës ({best.line_code}, "
                                     f"{second.line_code}).")
        chosen.append(best)
    return chosen


def build_statements(entries: list[TBEntry], structure: list[LineDef], rules: list[MappingRule]) -> StatementsResult:
    by_statement: dict[str, list[LineDef]] = defaultdict(list)
    for d in sorted(structure, key=lambda d: (d.statement_type, d.order)):
        by_statement[d.statement_type].append(d)
    results: dict[str, dict[str, LineResult]] = {
        st: {d.code: LineResult(d) for d in defs} for st, defs in by_statement.items()}
    explicit_net: set[tuple[str, str]] = set()
    core_rules = [r for r in rules if r.statement_type in results]
    unmapped: list[dict] = []

    for e in entries:
        selected = _select(core_rules, e.account_number)
        if not any(r.statement_type in CORE_STATEMENTS for r in selected):
            if e.closing_net != ZERO or e.movement_debit or e.movement_credit:
                unmapped.append({"account": e.account_number, "label": e.account_label,
                                 "closing_net": str(e.closing_net)})
            continue
        for r in selected:
            amount = rule_amount(e, r.balance_rule) * r.sign
            line = results[r.statement_type].get(r.line_code)
            if line is None:
                raise StatementError(f"Ligne {r.line_code} absente de la structure de l'état {r.statement_type}.")
            if amount == ZERO:
                continue
            current = getattr(line, r.amount_column)
            setattr(line, r.amount_column, (current or ZERO) + amount)
            if r.amount_column == "net":
                explicit_net.add((r.statement_type, r.line_code))
            line.trace.append({"account": e.account_number, "label": e.account_label, "column": r.amount_column,
                               "rule": r.balance_rule, "prefix": r.account_prefix, "sign": r.sign,
                               "amount": str(amount)})

    # net = brut - amortissements pour les lignes alimentées par colonnes
    for st, lines in results.items():
        for code, ln in lines.items():
            if ln.definition.kind == "detail" and (st, code) not in explicit_net and \
                    (ln.gross is not None or ln.depreciation is not None):
                ln.net = (ln.gross or ZERO) - (ln.depreciation or ZERO)

    # lignes de total, dans l'ordre des dépendances
    for st, lines in results.items():
        done: set[str] = {c for c, ln in lines.items() if ln.definition.kind != "total"}
        pending = [c for c, ln in lines.items() if ln.definition.kind == "total"]
        guard = 0
        while pending:
            guard += 1
            if guard > len(lines) + 5:
                raise StatementError(f"Totaux circulaires dans l'état {st} : {', '.join(pending)}.")
            for code in list(pending):
                d = lines[code].definition
                if all(ref in done for _, ref in d.formula):
                    tl = lines[code]
                    for col in COLUMNS:
                        parts = [getattr(lines[ref], col) for _, ref in d.formula]
                        if all(p is None for p in parts):
                            continue
                        setattr(tl, col, sum(((p or ZERO) * s for (s, _), p in zip(d.formula, parts, strict=True)),
                                              ZERO))
                    tl.trace = [{"total_of": [f"{'+' if s > 0 else '-'}{ref}" for s, ref in d.formula]}]
                    done.add(code)
                    pending.remove(code)

    ordered = {st: [lines[d.code] for d in by_statement[st]] for st, lines in results.items()}
    res = StatementsResult(ordered, [], unmapped)
    res.controls = _controls(res, structure)
    return res


def _role_line(res: StatementsResult, structure: list[LineDef], role: str) -> LineResult | None:
    d = next((d for d in structure if d.role == role), None)
    return res.line(d.code) if d else None


def _fmt(d: Decimal) -> str:
    return f"{d:,.2f}".replace(",", " ").replace(".", ",")


def _controls(res: StatementsResult, structure: list[LineDef]) -> list[StatementControl]:
    out: list[StatementControl] = []
    ta, tp = _role_line(res, structure, "total_actif"), _role_line(res, structure, "total_passif")
    if ta is None or tp is None:
        out.append(StatementControl("BALANCE_SHEET_EQUILIBRIUM", "skipped", "critical",
                                    "Rôles « total_actif » / « total_passif » non définis dans la structure."))
    elif ta.value() == tp.value():
        out.append(StatementControl("BALANCE_SHEET_EQUILIBRIUM", "passed", "critical",
                                    f"Total actif = total passif = {_fmt(ta.value())}."))
    else:
        out.append(StatementControl("BALANCE_SHEET_EQUILIBRIUM", "failed", "critical",
                                    f"Total actif {_fmt(ta.value())} ≠ total passif {_fmt(tp.value())} "
                                    f"(écart {_fmt(ta.value() - tp.value())}).",
                                    {"total_actif": str(ta.value()), "total_passif": str(tp.value())}))
    rb, rc = _role_line(res, structure, "resultat_bilan"), _role_line(res, structure, "resultat_compte_resultat")
    if rb is None or rc is None:
        out.append(StatementControl("NET_INCOME_CONSISTENCY", "skipped", "critical",
                                    "Rôles « resultat_bilan » / « resultat_compte_resultat » non définis."))
    elif rb.value() == rc.value():
        out.append(StatementControl("NET_INCOME_CONSISTENCY", "passed", "critical",
                                    f"Résultat du bilan = résultat du compte de résultat = {_fmt(rc.value())}."))
    else:
        out.append(StatementControl("NET_INCOME_CONSISTENCY", "failed", "critical",
                                    f"Résultat au bilan {_fmt(rb.value())} ≠ résultat du compte de résultat "
                                    f"{_fmt(rc.value())}.", {"bilan": str(rb.value()), "compte_resultat": str(rc.value())}))
    if res.unmapped:
        out.append(StatementControl("UNMAPPED_ACCOUNTS", "failed", "warning",
                                    f"{len(res.unmapped)} compte(s) mouvementé(s) ne sont rattachés à aucune ligne du "
                                    "bilan ni du compte de résultat.", {"accounts": res.unmapped[:50]}))
    else:
        out.append(StatementControl("UNMAPPED_ACCOUNTS", "passed", "warning",
                                    "Tous les comptes mouvementés sont rattachés aux états."))
    return out
