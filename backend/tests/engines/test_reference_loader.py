"""Chargeur de référentiels : uniquement des données FICTIVES de test (aucune règle officielle)."""

from app.engines.accounting.frameworks import get_profile
from app.engines.accounting.reference_loader import parse_chart, parse_mappings

CHART = [
    ["Numéro", "Libellé", "Nature", "Sens", "Imputable", "Commentaire"],
    ["1", "Classe test 1", "", "", "non", ""],
    ["10", "Racine test 10", "capitaux_propres", "credit", "non", ""],
    ["101", "Compte test 101", "capitaux_propres", "credit", "oui", ""],
    ["4", "Classe test 4", "", "", "non", ""],
    ["41", "Racine test 41", "actif", "debit", "", ""],
    ["411", "Compte test 411", "actif", "debit", "", ""],
    ["7", "Classe test 7", "", "", "non", ""],
    ["701", "Compte test 701", "produit", "credit", "", ""],
]


def test_chart_ok_with_hierarchy():
    res = parse_chart(CHART)
    assert not res.has_errors
    by = {r.account_number: r for r in res.records}
    assert by["411"].parent_number == "41" and by["41"].parent_number == "4"
    assert by["701"].parent_number == "7"
    assert by["101"].nature == "equity" and by["411"].normal_balance == "debit"
    assert by["10"].is_postable is False and by["411"].is_postable is True
    assert {i.code for i in res.issues} == {"UNKNOWN_COLUMNS"}


def test_chart_errors():
    rows = [["numero", "libelle", "nature"],
            ["10", "A", ""], ["10", "Doublon", ""], ["0123", "Classe 0", ""], ["4A1", "Lettres", ""],
            ["411", "", ""], ["412", "Nature fausse", "bizarre"], ["41234", "Orphelin", ""]]
    res = parse_chart(rows)
    codes = sorted(i.code for i in res.issues)
    assert codes == ["DUPLICATE", "INVALID_CLASS", "INVALID_NATURE", "INVALID_NUMBER", "MISSING_LABEL", "ORPHAN"]
    assert [r.account_number for r in res.records] == ["10", "41234"]


def test_chart_missing_columns():
    res = parse_chart([["compte", "intitule"], ["10", "x"]])
    assert res.has_errors and res.issues[0].code == "MISSING_COLUMNS"


MAP_HEADER = ["etat", "code_rubrique", "libelle_rubrique", "prefixe", "exclusions", "regle", "colonne", "signe",
              "priorite", "source"]


def test_mappings_ok_and_ambiguity():
    chart = {r.account_number for r in parse_chart(CHART).records}
    rows = [MAP_HEADER,
            ["bilan_actif", "T1", "Rubrique test 1", "41", "", "solde_debiteur", "net", "1", "", "Test p.1"],
            ["bilan_passif", "T2", "Rubrique test 2", "10", "", "solde_crediteur", "", "", "", ""],
            ["compte_resultat", "T3", "Rubrique test 3", "70", "", "solde_net_crediteur", "", "", "", ""]]
    res = parse_mappings(rows, chart)
    assert not res.has_errors, res.issues
    assert res.records[0].statement_type == "balance_sheet_assets" and res.records[0].balance_rule == "debit_balance"
    assert {i.code for i in res.issues} == {"PREFIX_NOT_IN_CHART"} or not res.issues

    ambiguous = rows + [["bilan_actif", "T9", "Rubrique test 9", "41", "", "solde_debiteur", "net", "1", "", ""]]
    assert any(i.code == "AMBIGUOUS" for i in parse_mappings(ambiguous, chart).issues)
    # une racine plus longue l'emporte : pas d'ambiguïté
    specific = rows + [["bilan_actif", "T9", "Rubrique test 9", "411", "", "solde_debiteur", "net", "1", "", ""]]
    assert not any(i.code == "AMBIGUOUS" for i in parse_mappings(specific, chart).issues)
    # exclusion : pas d'ambiguïté non plus
    excluded = rows[:1] + [rows[1][:4] + ["411"] + rows[1][5:]] + rows[2:] + \
        [["bilan_actif", "T9", "Rubrique test 9", "411", "", "solde_debiteur", "net", "1", "", ""]]
    assert not any(i.code == "AMBIGUOUS" for i in parse_mappings(excluded, chart).issues)


def test_mappings_errors():
    rows = [MAP_HEADER,
            ["bilan", "X", "x", "41", "", "solde_debiteur", "", "", "", ""],
            ["bilan_actif", "X", "x", "4A", "", "solde_debiteur", "", "", "", ""],
            ["bilan_actif", "X", "x", "41", "", "solde", "", "", "", ""],
            ["bilan_actif", "X", "x", "41", "", "solde_debiteur", "", "2", "", ""],
            ["bilan_actif", "X", "x", "41", "5", "solde_debiteur", "", "", "", ""]]
    codes = [i.code for i in parse_mappings(rows, set()).issues]
    assert codes == ["INVALID_STATEMENT", "INVALID_PREFIX", "INVALID_RULE", "INVALID_SIGN", "EXCLUSION_OUTSIDE"]


def test_profiles_require_core_statements():
    chart = parse_chart(CHART).records
    syscebnl = get_profile("SYSCEBNL")
    issues = syscebnl.validate(chart, [])
    assert sum(1 for i in issues if i.code == "STATEMENT_MISSING") == 3
    codes = {i.code for i in get_profile("SYSCOHADA_REV").validate([], [])}
    assert {"CHART_MISSING", "STRUCTURE_MISSING"} <= codes
