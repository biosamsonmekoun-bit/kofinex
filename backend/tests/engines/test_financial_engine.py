"""Moteur des états et des indicateurs sur un référentiel et des balances FICTIFS."""

from datetime import date
from decimal import Decimal as D

import pytest

from app.engines.accounting.reference_loader import parse_concepts, parse_structure
from app.engines.accounting.statements import StatementError, build_statements
from app.engines.financial.calculator import Calculator, Formula, YearContext
from app.engines.financial.expressions import parse
from app.engines.financial.library import CONCEPTS, CROSS_CHECKS, LIBRARY
from app.engines.financial.multiyear import build_series
from tests.engines import fictitious_framework as ff


@pytest.fixture(scope="module")
def setup():
    return ff.load()


def _statements(setup, balance):
    line_defs, rules, *_ = setup
    return build_statements(balance, line_defs, rules)


def test_statements_amounts_and_controls(setup):
    res = _statements(setup, ff.BALANCE_N)
    immo = res.line("TA_IMMO")
    assert (immo.gross, immo.depreciation, immo.net) == (D("1000000.00"), D("300000.00"), D("700000.00"))
    assert res.line("TA_TOT").net == D("1300000.00") == res.line("TP_TOT").net
    assert res.line("TP_TRE").net == D("20000.00")          # banque créditrice au passif
    assert res.line("TA_TRE").net == D("200000.00")
    assert res.line("R_ACH").net == D("500000.00")           # 603 capté par la racine plus longue
    assert res.line("R_VST").net == D("-10000.00")
    assert res.line("R_EBE").net == D("220000.00")
    assert res.line("R_NET").net == res.line("TP_RES").net == D("100000.00")
    assert {c.code: c.status for c in res.controls} == {
        "BALANCE_SHEET_EQUILIBRIUM": "passed", "NET_INCOME_CONSISTENCY": "passed", "UNMAPPED_ACCOUNTS": "passed"}
    trace = res.line("TA_IMMO").trace
    assert {t["account"] for t in trace} == {"211000", "281000"}


def test_unmapped_and_unbalanced(setup):
    extra = ff.BALANCE_N + ff.tb([("891000", "5000", "0")])
    res = _statements(setup, extra)
    ctrl = {c.code: c for c in res.controls}
    assert ctrl["UNMAPPED_ACCOUNTS"].status == "failed"
    assert res.unmapped[0]["account"] == "891000"


def test_ambiguous_mapping_detected(setup):
    line_defs, rules, *_ = setup
    from app.engines.accounting.statements import MappingRule
    bad = rules + [MappingRule("balance_sheet_assets", "TA_STK", "41", (), "debit_balance", "gross", 1, 100)]
    with pytest.raises(StatementError, match="ambiguës"):
        build_statements(ff.BALANCE_N, line_defs, bad)


def _calc(setup, with_previous=True):
    _, _, concepts, *_ = setup
    cur = _statements(setup, ff.BALANCE_N)
    prev = _statements(setup, ff.BALANCE_N1)
    ycur = YearContext("2025", date(2025, 1, 1), date(2025, 12, 31), cur.values(), ff.BALANCE_N)
    yprev = YearContext("2024", date(2024, 1, 1), date(2024, 12, 31), prev.values(), ff.BALANCE_N1) \
        if with_previous else None
    formulas = [Formula(f.code, f.version, parse(f.expression), f.unit, f.rounding_scale, f.zero_division_policy,
                        f.missing_input_policy) for f in LIBRARY]
    return Calculator(ycur, yprev, concepts, formulas)


def test_indicators(setup):
    calc = _calc(setup)
    r = {x.code: x for x in calc.run()}
    expected = {
        "CA": "910000.00", "VALEUR_AJOUTEE": "420000.00", "EBE": "220000.00", "RESULTAT_NET": "100000.00",
        "CAF_ADDITIVE": "200000.00", "CAF_SOUSTRACTIVE": "200000.00",
        "FR": "400000.00", "BFR": "220000.00", "TN": "180000.00",
        "LIQUIDITE_GENERALE": "3.0000", "LIQUIDITE_REDUITE": "2.2500", "LIQUIDITE_IMMEDIATE": "1.0000",
        "AUTONOMIE_FINANCIERE": "53.85", "ENDETTEMENT": "0.5714", "CAPACITE_REMBOURSEMENT": "2.00",
        "ROE": "14.29", "ROA": "7.69", "MARGE_NETTE": "10.99", "TAUX_EBE": "24.18", "TAUX_VALEUR_AJOUTEE": "46.15",
        "PART_CHARGES_PERSONNEL_VA": "47.62", "ROTATION_STOCKS": "111.7", "DELAI_CLIENTS": "100.3",
        "DELAI_FOURNISSEURS": "131.4", "BFR_JOURS_CA": "88.2", "ROTATION_ACTIF": "0.7000",
        "CROISSANCE_CA": "18.18",
    }
    for code, value in expected.items():
        assert r[code].status == "ok", (code, r[code].message)
        assert r[code].value == D(value), (code, r[code].value)
    # concepts non liés dans le référentiel de test : jamais inventés
    assert r["MARGE_COMMERCIALE"].status == "missing_input"
    assert "concept non défini" in r["MARGE_COMMERCIALE"].message
    # résultat N-1 nul : croissance non significative
    assert r["CROISSANCE_RESULTAT_NET"].status == "division_by_zero" and r["CROISSANCE_RESULTAT_NET"].value is None
    # traçabilité : entrées exactes
    assert r["FR"].inputs == {"concept(ressources_stables)": "1100000.00", "concept(actif_immobilise)": "700000.00"}


def test_cross_checks(setup):
    checks = {c.code: c for c in _calc(setup).cross_checks(CROSS_CHECKS)}
    assert checks["FR_BFR_TN"].status == "passed"
    assert checks["CAF_METHODS"].status == "passed"


def test_without_previous_year(setup):
    r = {x.code: x for x in _calc(setup, with_previous=False).run()}
    assert r["CROISSANCE_CA"].status == "missing_input"
    assert "exercice précédent" in r["CROISSANCE_CA"].message
    assert r["CA"].status == "ok"


def test_library_is_valid():
    codes = {f.code for f in LIBRARY}
    assert len(codes) == len(LIBRARY)
    from app.engines.financial.expressions import references
    for f in LIBRARY:
        for fn, arg in references(parse(f.expression)):
            if fn in ("concept", "prev_concept"):
                assert arg in CONCEPTS, (f.code, arg)
            if fn in ("ind", "prev_ind"):
                assert arg in codes, (f.code, arg)


def test_structure_loader_errors():
    rows = [["etat", "code", "libelle", "ordre", "type", "formule", "role"],
            ["bilan_actif", "A1", "x", "1", "detail", "", ""],
            ["bilan_actif", "A1", "doublon", "2", "detail", "", ""],
            ["bilan_actif", "T1", "x", "3", "total", "A1 + ZZ", "total_actif"],
            ["bilan_actif", "T2", "x", "4", "total", "T3", ""],
            ["bilan_actif", "T3", "x", "5", "total", "T2", ""],
            ["bilan_passif", "P1", "x", "1", "total", "A1", "total_passif"],
            ["bilan_actif", "T4", "x", "6", "total", "", ""],
            ["compte_resultat", "R1", "x", "1", "detail", "", "role_inconnu"]]
    codes = {i.code for i in parse_structure(rows).issues}
    assert {"DUPLICATE", "UNKNOWN_REFERENCE", "CYCLE", "CROSS_STATEMENT", "MISSING_FORMULA", "INVALID_ROLE"} <= codes


def test_concept_loader_errors():
    rows = [["concept", "expression"], ["inexistant", "1"], ["stocks", 'line("ZZ")'], ["total_actif", 'ind("CA")'],
            ["capitaux_propres", 'concept("ressources_stables")'], ["ressources_stables", 'concept("capitaux_propres")'],
            ["chiffre_affaires", 'line("A1") +']]
    codes = [i.code for i in parse_concepts(rows, {"A1"}, set(CONCEPTS)).issues]
    assert {"UNKNOWN_CONCEPT", "UNKNOWN_LINE", "INDICATOR_IN_CONCEPT", "CYCLE", "INVALID_EXPRESSION",
            "CONCEPTS_NOT_BOUND"} <= set(codes)


def test_multiyear_series():
    s = build_series("CA", "amount", [("2023", D("800000"), "ok"), ("2024", D("770000"), "ok"),
                                      ("2025", D("910000"), "ok")])
    assert [p.variation for p in s.points] == [None, D("-30000"), D("140000")]
    assert [p.variation_pct for p in s.points] == [None, D("-3.75"), D("18.18")]
    assert s.cagr_pct == D("6.65")             # (910/800)^(1/2) - 1
    s2 = build_series("RN", "amount", [("2024", D("-10"), "ok"), ("2025", None, "missing_input"), ("2026", D("5"), "ok")])
    assert s2.cagr_pct is None and s2.points[2].variation is None
