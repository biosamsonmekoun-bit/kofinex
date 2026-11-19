from decimal import Decimal as D

import pytest

from app.engines.financial.expressions import (
    DivisionByZero,
    FormulaSyntaxError,
    MissingInput,
    evaluate,
    parse,
    references,
    to_text,
)

VALUES = {("concept", "a"): D("10"), ("concept", "b"): D("4"), ("ind", "X"): D("2.5"), ("line", "XB"): D("1000")}


def resolve(fn, args):
    if fn == "days":
        return D(365)
    key = (fn, args[0])
    if key not in VALUES:
        raise MissingInput(f"{fn}({args[0]})")
    return VALUES[key]


@pytest.mark.parametrize("expr,expected", [
    ('concept("a") - concept("b")', D("6")),
    ('concept("a") / concept("b")', D("2.5")),
    ('-concept("a") + 3 * ind("X")', D("-2.5")),
    ('line("XB") / 3', D("333.3333333333333333333333333333333")),  # 34 chiffres significatifs
    ('0.1 + 0.2', D("0.3")),                 # pas d'erreur binaire
    ('abs(concept("b") - concept("a"))', D("6")),
    ('min(concept("a"), concept("b"), 7)', D("4")),
    ('max(concept("a"), ind("X"))', D("10")),
    ('avg(concept("a"), concept("b"))', D("7")),
    ('concept("b") / line("XB") * days()', D("1.46")),
])
def test_evaluate(expr, expected):
    assert evaluate(parse(expr), resolve) == expected


def test_division_by_zero():
    with pytest.raises(DivisionByZero):
        evaluate(parse('concept("a") / (concept("b") - 4)'), resolve)


def test_missing_input():
    with pytest.raises(MissingInput) as e:
        evaluate(parse('concept("a") + concept("inconnu")'), resolve)
    assert e.value.reference == "concept(inconnu)"


@pytest.mark.parametrize("expr,msg", [
    ("", "vide"),
    ("__import__('os')", "inconnue"),
    ("open('x')", "inconnue"),
    ("concept(a)", "guillemets"),
    ('concept("a") ** 2', "Opérateur"),
    ('concept("a") if 1 else 2', "non autorisé"),
    ('acct("6A", "net_debit")', "racine"),
    ('acct("60", "solde")', "règle"),
    ('line("XB", "brut")', "colonne"),
    ('concept("a", "b")', "arguments"),
    ('days(1)', "argument"),
    ('min(1)', "arguments"),
    ('concept("a").real', "non autorisé"),
    ('[1,2]', "non autorisé"),
    ('concept("a") +', "Syntaxe"),
    ('max(concept(b="x"), 1)', "Élément"),
])
def test_rejected(expr, msg):
    with pytest.raises(FormulaSyntaxError, match=msg):
        parse(expr)


def test_references_and_text():
    node = parse('(concept("ressources_stables") - concept("actif_immobilise")) / ind("CA") * days()')
    assert references(node) == {("concept", "ressources_stables"), ("concept", "actif_immobilise"), ("ind", "CA")}
    assert to_text(node) == '(((concept("ressources_stables") - concept("actif_immobilise")) / ind("CA")) * days())'
    assert parse(to_text(node)) == node
