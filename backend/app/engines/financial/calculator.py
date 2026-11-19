"""Calcul des indicateurs d'un exercice.

Contexte d'un exercice : valeurs des lignes d'états, balance, nombre de jours. Les concepts sont
évalués à partir de leurs expressions (liées à la version du référentiel), les indicateurs à
partir des formules publiées. Chaque résultat conserve ses entrées exactes.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_EVEN, Decimal

from app.engines.accounting.statements import TBEntry, account_amount
from app.engines.financial.expressions import DivisionByZero, MissingInput, evaluate, parse

ZERO = Decimal(0)


@dataclass
class YearContext:
    label: str
    start: date
    end: date
    lines: dict[str, dict[str, Decimal | None]]     # code -> {gross, depreciation, net}
    entries: list[TBEntry]

    @property
    def days(self) -> Decimal:
        return Decimal((self.end - self.start).days + 1)


@dataclass(frozen=True)
class Formula:
    code: str
    version: int
    ast: dict
    unit: str
    rounding_scale: int = 2
    zero_division_policy: str = "null"
    missing_input_policy: str = "null"
    formula_id: str | None = None


@dataclass
class IndicatorResult:
    code: str
    version: int
    value: Decimal | None
    status: str                       # ok | missing_input | division_by_zero | error
    unit: str
    inputs: dict[str, str | None] = field(default_factory=dict)
    message: str | None = None
    formula_id: str | None = None


@dataclass
class CrossCheck:
    code: str
    title: str
    status: str                       # passed | failed | skipped
    difference: Decimal | None
    message: str


class _Cycle(Exception):
    pass


class Calculator:
    def __init__(self, current: YearContext, previous: YearContext | None, concepts: dict[str, dict],
                 formulas: Iterable[Formula]) -> None:
        self.ctx = {"cur": current, "prev": previous}
        self.concepts = concepts
        self.formulas = {f.code: f for f in formulas}
        self._concept_cache: dict[tuple[str, str], Decimal] = {}
        self._ind_cache: dict[tuple[str, str], IndicatorResult] = {}
        self._stack: list[tuple[str, str, str]] = []

    # -------------------------------------------------------------------- références
    def _resolver(self, period: str, trace: dict[str, str | None] | None, zero_missing: bool):
        def resolve(fn: str, args: list[str]) -> Decimal:
            p = "prev" if fn.startswith("prev_") else period
            base = fn.removeprefix("prev_")
            key = f"{fn}({', '.join(args)})" if args else f"{fn}()"
            try:
                value = self._value(p, base, args)
            except MissingInput:
                if zero_missing:
                    if trace is not None:
                        trace[key] = None
                    return ZERO
                raise
            if trace is not None:
                trace[key] = str(value)
            return value
        return resolve

    def _value(self, period: str, base: str, args: list[str]) -> Decimal:
        ctx = self.ctx[period]
        if ctx is None:
            raise MissingInput(f"{base}({', '.join(args)})", "exercice précédent sans balance validée")
        if base == "days":
            return ctx.days
        if base == "line":
            line = ctx.lines.get(args[0])
            if line is None:
                raise MissingInput(f"line({args[0]})", "ligne inexistante dans la structure des états")
            v = line.get(args[1] if len(args) > 1 else "net")
            return v if v is not None else ZERO
        if base == "acct":
            return account_amount(ctx.entries, args[0], args[1])
        if base == "concept":
            return self.concept(args[0], period)
        if base == "ind":
            r = self.indicator(args[0], period)
            if r.status != "ok" or r.value is None:
                raise MissingInput(f"ind({args[0]})", r.message or "indicateur non calculable")
            return r.value
        raise MissingInput(base, "référence inconnue")

    def concept(self, code: str, period: str = "cur") -> Decimal:
        key = (code, period)
        if key in self._concept_cache:
            return self._concept_cache[key]
        node = self.concepts.get(code)
        if node is None:
            raise MissingInput(f"concept({code})", "concept non défini pour ce référentiel")
        if ("concept", code, period) in self._stack:
            raise MissingInput(f"concept({code})", "définition circulaire")
        self._stack.append(("concept", code, period))
        try:
            v = evaluate(node, self._resolver(period, None, False))
        except DivisionByZero as exc:
            raise MissingInput(f"concept({code})", "division par zéro dans la définition du concept") from exc
        finally:
            self._stack.pop()
        self._concept_cache[key] = v
        return v

    # -------------------------------------------------------------------- indicateurs
    def indicator(self, code: str, period: str = "cur") -> IndicatorResult:
        key = (code, period)
        if key in self._ind_cache:
            return self._ind_cache[key]
        f = self.formulas.get(code)
        if f is None:
            return IndicatorResult(code, 0, None, "error", "", message=f"Indicateur {code} inconnu")
        if ("ind", code, period) in self._stack:
            return IndicatorResult(code, f.version, None, "error", f.unit, message="Dépendance circulaire")
        self._stack.append(("ind", code, period))
        trace: dict[str, str | None] = {}
        try:
            raw = evaluate(f.ast, self._resolver(period, trace, f.missing_input_policy == "zero"))
            value = raw.quantize(Decimal(1).scaleb(-f.rounding_scale), rounding=ROUND_HALF_EVEN)
            result = IndicatorResult(code, f.version, value, "ok", f.unit, trace)
        except MissingInput as exc:
            result = IndicatorResult(code, f.version, None, "missing_input", f.unit, trace, str(exc))
        except DivisionByZero:
            if f.zero_division_policy == "zero":
                result = IndicatorResult(code, f.version, ZERO, "ok", f.unit, trace, "Division par zéro : valeur 0")
            else:
                result = IndicatorResult(code, f.version, None, "division_by_zero", f.unit, trace,
                                         "Dénominateur nul : indicateur non significatif")
        finally:
            self._stack.pop()
        result.formula_id = f.formula_id
        self._ind_cache[key] = result
        return result

    def run(self) -> list[IndicatorResult]:
        return [self.indicator(code) for code in self.formulas]

    def cross_checks(self, checks: Iterable[tuple[str, str, str, str]]) -> list[CrossCheck]:
        out = []
        for code, expr, title, hint in checks:
            try:
                diff = evaluate(parse(expr), self._resolver("cur", None, False)).quantize(Decimal("0.01"))
            except (MissingInput, DivisionByZero) as exc:
                out.append(CrossCheck(code, title, "skipped", None, f"Contrôle non exécuté : {exc}"))
                continue
            if diff == 0:
                out.append(CrossCheck(code, title, "passed", diff, "Égalité vérifiée."))
            else:
                out.append(CrossCheck(code, title, "failed", diff, f"Écart de {diff}. {hint}"))
        return out
