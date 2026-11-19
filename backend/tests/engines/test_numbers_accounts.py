from decimal import Decimal as D

import pytest

from app.engines.importing.accounts import parse_account_cell
from app.engines.importing.numbers import AmountError, infer_decimal_separator, parse_amount


@pytest.mark.parametrize("raw,expected", [
    ("1 234 567,89", D("1234567.89")),
    ("1 234 567,89", D("1234567.89")),
    ("1 234,50", D("1234.50")),
    ("1.234.567,89", D("1234567.89")),
    ("1,234,567.89", D("1234567.89")),
    ("1234567,8", D("1234567.80")),
    ("(1 500,00)", D("-1500.00")),
    ("1 500,00-", D("-1500.00")),
    ("-250", D("-250.00")),
    ("12 500 000 FCFA", D("12500000.00")),
    ("1.234.567", D("1234567.00")),
    ("1 234 567", D("1234567.00")),
    (1234567, D("1234567.00")),
    (0.1 + 0.2, D("0.30")),
    (1800000.5, D("1800000.50")),
    (D("10.005"), D("10.00")),          # arrondi bancaire au centime
    ("0,5", D("0.50")),
])
def test_parse_amount(raw, expected):
    assert parse_amount(raw) == expected


@pytest.mark.parametrize("raw", [None, "", "-", "—", "néant"])
def test_empty_values(raw):
    assert parse_amount(raw) is None


@pytest.mark.parametrize("raw", ["abc", "12a", "1,2,3", "1.2.3,4,5", True, float("nan")])
def test_invalid_values(raw):
    with pytest.raises(AmountError):
        parse_amount(raw)


@pytest.mark.parametrize("raw", ["1.234", "1,234"])
def test_ambiguous_without_hint(raw):
    with pytest.raises(AmountError, match="ambigu"):
        parse_amount(raw)


def test_ambiguous_with_hint():
    assert parse_amount("1.234", decimal_separator=",") == D("1234.00")
    assert parse_amount("1,234", decimal_separator=",") == D("1.23")
    assert parse_amount("1,234", decimal_separator=".") == D("1234.00")


def test_infer_separator():
    assert infer_decimal_separator(["1 234,56", "12,00", "3"]) == ","
    assert infer_decimal_separator(["1,234.56", "12.00"]) == "."
    assert infer_decimal_separator(["1234", "12"]) is None


@pytest.mark.parametrize("raw,number,rest,total", [
    ("411100", "411100", None, False),
    (411100, "411100", None, False),
    (411100.0, "411100", None, False),
    ("4111 00", "411100", None, False),
    ("411.100", "411100", None, False),
    ("'0411", "0411", None, False),
    ("411100 - Clients ordinaires", "411100", "Clients ordinaires", False),
    ("521100 Banque", "521100", "Banque", False),
    ("TOTAL GÉNÉRAL", None, None, True),
    ("Sous-total classe 4", None, None, True),
    ("Classe 4 - Comptes de tiers", None, "Classe 4 - Comptes de tiers", False),
    ("4", None, "4", False),            # trop court pour un compte
    (None, None, None, False),
])
def test_account_cell(raw, number, rest, total):
    cell = parse_account_cell(raw)
    assert (cell.number, cell.label_remainder, cell.is_total) == (number, rest, total)
