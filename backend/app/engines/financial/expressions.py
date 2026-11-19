"""Langage de formules financières.

Syntaxe (sous-ensemble d'expressions Python, analysé puis converti en arbre JSON — jamais
exécuté par ``eval``) :

    nombres            360, 0.5
    opérateurs         + - * /  et parenthèses
    fonctions          abs(x), min(a, b, ...), max(a, b, ...), avg(a, b, ...)
    références         concept("capitaux_propres")      concept lié au référentiel
                       prev_concept("capitaux_propres")  idem, exercice précédent
                       ind("EBE") / prev_ind("EBE")      autre indicateur
                       line("XB") / line("AE", "gross")  ligne d'état (net | gross | depreciation)
                       prev_line("XB")
                       acct("60", "net_debit")           comptes de la balance (règles des correspondances)
                       prev_acct("60", "net_debit")
                       days()                            nombre de jours de l'exercice

L'arbre validé est stocké avec la formule (``expression_ast``) : c'est lui qui est évalué.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Callable
from decimal import Decimal, InvalidOperation, localcontext

MAX_LENGTH = 2000
MAX_DEPTH = 40

REF_FUNCTIONS = {
    "concept": 1, "prev_concept": 1, "ind": 1, "prev_ind": 1,
    "line": (1, 2), "prev_line": (1, 2), "acct": 2, "prev_acct": 2,
}
MATH_FUNCTIONS = {"abs": 1, "min": (2, 20), "max": (2, 20), "avg": (2, 20)}
NULLARY = {"days"}
LINE_COLUMNS = {"net", "gross", "depreciation"}
ACCOUNT_RULES = {"debit_balance", "credit_balance", "net_debit", "net_credit", "debit_movements",
                 "credit_movements"}

_CODE_RE = re.compile(r"^[A-Za-z0-9_]{1,60}$")
_PREFIX_RE = re.compile(r"^[0-9]{1,20}$")


class FormulaSyntaxError(ValueError):
    """Formule invalide (message destiné à l'utilisateur)."""


class MissingInput(Exception):
    def __init__(self, reference: str, reason: str = "donnée absente") -> None:
        super().__init__(f"{reference} : {reason}")
        self.reference = reference
        self.reason = reason


class DivisionByZero(Exception):
    pass


# ------------------------------------------------------------------------------ analyse
def parse(expression: str) -> dict:
    if not expression or not expression.strip():
        raise FormulaSyntaxError("Formule vide.")
    if len(expression) > MAX_LENGTH:
        raise FormulaSyntaxError("Formule trop longue.")
    try:
        tree = ast.parse(expression.strip(), mode="eval")
    except SyntaxError as exc:
        raise FormulaSyntaxError(f"Syntaxe invalide : {exc.msg} (position {exc.offset}).") from exc
    return _convert(tree.body, 0)


def _arity_ok(spec: int | tuple[int, int], n: int) -> bool:
    return spec == n if isinstance(spec, int) else spec[0] <= n <= spec[1]


def _convert(node: ast.AST, depth: int) -> dict:
    if depth > MAX_DEPTH:
        raise FormulaSyntaxError("Formule trop imbriquée.")
    if isinstance(node, ast.Constant) and isinstance(node.value, int | float) and not isinstance(node.value, bool):
        return {"num": repr(node.value) if isinstance(node.value, float) else str(node.value)}
    if isinstance(node, ast.BinOp):
        ops = {ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/"}
        op = ops.get(type(node.op))
        if op is None:
            raise FormulaSyntaxError("Opérateur non autorisé (seuls + - * / sont acceptés).")
        return {"op": op, "l": _convert(node.left, depth + 1), "r": _convert(node.right, depth + 1)}
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub | ast.UAdd):
        inner = _convert(node.operand, depth + 1)
        return {"op": "neg", "x": inner} if isinstance(node.op, ast.USub) else inner
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and not node.keywords:
        name, args = node.func.id, node.args
        if name in NULLARY:
            if args:
                raise FormulaSyntaxError(f"{name}() ne prend pas d'argument.")
            return {"fn": name, "args": []}
        if name in REF_FUNCTIONS:
            if not _arity_ok(REF_FUNCTIONS[name], len(args)):
                raise FormulaSyntaxError(f"Nombre d'arguments incorrect pour {name}().")
            values = []
            for a in args:
                if not (isinstance(a, ast.Constant) and isinstance(a.value, str)):
                    raise FormulaSyntaxError(f"{name}() attend des textes entre guillemets.")
                values.append(a.value)
            _check_reference(name, values)
            return {"fn": name, "args": values}
        if name in MATH_FUNCTIONS:
            if not _arity_ok(MATH_FUNCTIONS[name], len(args)):
                raise FormulaSyntaxError(f"Nombre d'arguments incorrect pour {name}().")
            return {"fn": name, "args": [_convert(a, depth + 1) for a in args]}
        raise FormulaSyntaxError(f"Fonction inconnue : {name}().")
    raise FormulaSyntaxError("Élément non autorisé dans une formule.")


def _check_reference(name: str, values: list[str]) -> None:
    if name in ("acct", "prev_acct"):
        if not _PREFIX_RE.match(values[0]):
            raise FormulaSyntaxError(f"{name}() : racine de compte invalide « {values[0]} ».")
        if values[1] not in ACCOUNT_RULES:
            raise FormulaSyntaxError(f"{name}() : règle inconnue « {values[1]} » ({', '.join(sorted(ACCOUNT_RULES))}).")
        return
    if not _CODE_RE.match(values[0]):
        raise FormulaSyntaxError(f"{name}() : code invalide « {values[0]} ».")
    if name in ("line", "prev_line") and len(values) == 2 and values[1] not in LINE_COLUMNS:
        raise FormulaSyntaxError(f"{name}() : colonne inconnue « {values[1]} » (net, gross, depreciation).")


def references(node: dict) -> set[tuple[str, str]]:
    """Références directes : {("concept", "capitaux_propres"), ("ind", "EBE"), ("line", "XB"), …}."""
    out: set[tuple[str, str]] = set()
    if "fn" in node:
        if node["fn"] in REF_FUNCTIONS:
            out.add((node["fn"], node["args"][0]))
        elif node["fn"] in MATH_FUNCTIONS:
            for a in node["args"]:
                out |= references(a)
    elif "op" in node:
        for k in ("l", "r", "x"):
            if k in node:
                out |= references(node[k])
    return out


def to_text(node: dict) -> str:
    """Forme lisible normalisée (affichage, comparaison de versions)."""
    if "num" in node:
        return node["num"]
    if "fn" in node:
        if node["fn"] in REF_FUNCTIONS:
            return f"{node['fn']}({', '.join(repr(a).replace(chr(39), chr(34)) for a in node['args'])})"
        if node["fn"] in NULLARY:
            return f"{node['fn']}()"
        return f"{node['fn']}({', '.join(to_text(a) for a in node['args'])})"
    if node["op"] == "neg":
        return f"-({to_text(node['x'])})"
    return f"({to_text(node['l'])} {node['op']} {to_text(node['r'])})"


# ------------------------------------------------------------------------------ évaluation
Resolver = Callable[[str, list[str]], Decimal]


def evaluate(node: dict, resolve: Resolver) -> Decimal:
    """Évalue l'arbre. ``resolve(fonction, arguments)`` fournit la valeur d'une référence ou lève
    ``MissingInput``. Lève ``DivisionByZero`` sur une division par zéro."""
    with localcontext() as ctx:
        ctx.prec = 34
        return _eval(node, resolve)


def _eval(node: dict, resolve: Resolver) -> Decimal:
    if "num" in node:
        return Decimal(node["num"])
    if "fn" in node:
        fn, args = node["fn"], node["args"]
        if fn in REF_FUNCTIONS or fn in NULLARY:
            v = resolve(fn, list(args))
            if not isinstance(v, Decimal):
                raise TypeError(f"Référence {fn} : valeur non décimale")
            return v
        values = [_eval(a, resolve) for a in args]
        if fn == "abs":
            return abs(values[0])
        if fn == "min":
            return min(values)
        if fn == "max":
            return max(values)
        if fn == "avg":
            return sum(values, Decimal(0)) / len(values)
    op = node["op"]
    if op == "neg":
        return -_eval(node["x"], resolve)
    left, right = _eval(node["l"], resolve), _eval(node["r"], resolve)
    if op == "+":
        return left + right
    if op == "-":
        return left - right
    if op == "*":
        return left * right
    if right == 0:
        raise DivisionByZero()
    try:
        return left / right
    except InvalidOperation as exc:  # pragma: no cover - garde-fou
        raise DivisionByZero() from exc

