"""Référentiel FICTIF pour les tests du moteur financier.

Codes de lignes, intitulés et rattachements inventés pour les tests : ils ne reproduisent
pas les états officiels SYSCOHADA ou SYSCEBNL et ne doivent pas servir de référence.
"""

from __future__ import annotations

from decimal import Decimal as D

from app.engines.accounting.reference_loader import parse_concepts, parse_mappings, parse_structure
from app.engines.accounting.statements import LineDef, MappingRule, TBEntry
from app.engines.financial.library import CONCEPTS

STRUCTURE = [
    ["etat", "code", "libelle", "ordre", "type", "formule", "role", "niveau"],
    ["bilan_actif", "TA_IMMO", "Immobilisations (test)", "10", "detail", "", "", "1"],
    ["bilan_actif", "TA_STK", "Stocks (test)", "20", "detail", "", "", "1"],
    ["bilan_actif", "TA_CLI", "Clients (test)", "30", "detail", "", "", "1"],
    ["bilan_actif", "TA_TRE", "Trésorerie actif (test)", "40", "detail", "", "", "1"],
    ["bilan_actif", "TA_TOT", "Total actif (test)", "90", "total", "TA_IMMO + TA_STK + TA_CLI + TA_TRE", "total_actif", "0"],
    ["bilan_passif", "TP_CAP", "Capital (test)", "10", "detail", "", "", "1"],
    ["bilan_passif", "TP_RES", "Résultat (test)", "20", "detail", "", "resultat_bilan", "1"],
    ["bilan_passif", "TP_CP", "Capitaux propres (test)", "30", "total", "TP_CAP + TP_RES", "", "0"],
    ["bilan_passif", "TP_EMP", "Emprunts (test)", "40", "detail", "", "", "1"],
    ["bilan_passif", "TP_FOU", "Fournisseurs (test)", "50", "detail", "", "", "1"],
    ["bilan_passif", "TP_TRE", "Trésorerie passif (test)", "60", "detail", "", "", "1"],
    ["bilan_passif", "TP_TOT", "Total passif (test)", "90", "total", "TP_CP + TP_EMP + TP_FOU + TP_TRE", "total_passif", "0"],
    ["compte_resultat", "R_VEN", "Ventes (test)", "10", "detail", "", "", "1"],
    ["compte_resultat", "R_ACH", "Achats (test)", "20", "detail", "", "", "1"],
    ["compte_resultat", "R_VST", "Variation de stocks (test)", "25", "detail", "", "", "1"],
    ["compte_resultat", "R_PER", "Personnel (test)", "30", "detail", "", "", "1"],
    ["compte_resultat", "R_EBE", "EBE (test)", "40", "total", "R_VEN - R_ACH - R_VST - R_PER", "", "0"],
    ["compte_resultat", "R_DOT", "Dotations (test)", "50", "detail", "", "", "1"],
    ["compte_resultat", "R_FIN", "Charges financières (test)", "60", "detail", "", "", "1"],
    ["compte_resultat", "R_NET", "Résultat net (test)", "90", "total", "R_EBE - R_DOT - R_FIN", "resultat_compte_resultat", "0"],
]

MAPPINGS = [
    ["etat", "code_rubrique", "libelle_rubrique", "prefixe", "regle", "colonne", "exclusions"],
    ["bilan_actif", "TA_IMMO", "x", "2", "solde_debiteur", "brut", "28"],
    ["bilan_actif", "TA_IMMO", "x", "28", "solde_crediteur", "amortissement", ""],
    ["bilan_actif", "TA_STK", "x", "3", "solde_debiteur", "brut", ""],
    ["bilan_actif", "TA_CLI", "x", "41", "solde_debiteur", "brut", ""],
    ["bilan_actif", "TA_TRE", "x", "5", "solde_debiteur", "brut", ""],
    ["bilan_passif", "TP_CAP", "x", "10", "solde_net_crediteur", "", ""],
    ["bilan_passif", "TP_RES", "x", "6", "solde_net_crediteur", "", ""],
    ["bilan_passif", "TP_RES", "x", "7", "solde_net_crediteur", "", ""],
    ["bilan_passif", "TP_EMP", "x", "16", "solde_net_crediteur", "", ""],
    ["bilan_passif", "TP_FOU", "x", "40", "solde_crediteur", "", ""],
    ["bilan_passif", "TP_TRE", "x", "5", "solde_crediteur", "", ""],
    ["compte_resultat", "R_VEN", "x", "70", "solde_net_crediteur", "", ""],
    ["compte_resultat", "R_ACH", "x", "60", "solde_net_debiteur", "", ""],
    ["compte_resultat", "R_VST", "x", "603", "solde_net_debiteur", "", ""],
    ["compte_resultat", "R_PER", "x", "66", "solde_net_debiteur", "", ""],
    ["compte_resultat", "R_DOT", "x", "68", "solde_net_debiteur", "", ""],
    ["compte_resultat", "R_FIN", "x", "67", "solde_net_debiteur", "", ""],
]

CONCEPT_ROWS = [
    ["concept", "expression"],
    ["total_actif", 'line("TA_TOT")'], ["actif_immobilise", 'line("TA_IMMO")'], ["stocks", 'line("TA_STK")'],
    ["creances_clients", 'line("TA_CLI")'], ["actif_circulant", 'line("TA_STK") + line("TA_CLI")'],
    ["tresorerie_actif", 'line("TA_TRE")'], ["capitaux_propres", 'line("TP_CP")'],
    ["dettes_financieres", 'line("TP_EMP")'], ["ressources_stables", 'concept("capitaux_propres") + concept("dettes_financieres")'],
    ["passif_circulant", 'line("TP_FOU")'], ["dettes_fournisseurs", 'line("TP_FOU")'], ["tresorerie_passif", 'line("TP_TRE")'],
    ["chiffre_affaires", 'line("R_VEN")'], ["valeur_ajoutee", 'line("R_VEN") - line("R_ACH") - line("R_VST")'],
    ["excedent_brut_exploitation", 'line("R_EBE")'], ["resultat_net", 'line("R_NET")'],
    ["achats_consommes", 'line("R_ACH") + line("R_VST")'], ["achats_fournisseurs", 'line("R_ACH")'],
    ["charges_personnel", 'line("R_PER")'], ["charges_calculees", 'line("R_DOT")'], ["produits_calcules", "0"],
    ["produits_cessions", "0"], ["vnc_cessions", "0"], ["produits_encaissables_hors_ebe", "0"],
    ["charges_decaissables_hors_ebe", 'line("R_FIN")'],
]


def tb(rows: list[tuple[str, str, str]]) -> list[TBEntry]:
    """(compte, solde débiteur, solde créditeur) — mouvements et ouverture non utilisés ici."""
    z = D("0.00")
    return [TBEntry(a, f"Compte test {a}", z, z, z, z, D(d), D(c)) for a, d, c in rows]


# Balance équilibrée N (fictive) : total débit = total crédit = 2 090 000
BALANCE_N = tb([
    ("211000", "1000000", "0"), ("281000", "0", "300000"), ("311000", "150000", "0"), ("411000", "250000", "0"),
    ("521000", "200000", "0"), ("101000", "0", "600000"), ("162000", "0", "400000"), ("401000", "0", "180000"),
    ("561000", "0", "20000"),
    ("601000", "500000", "0"), ("603000", "0", "10000"),
    ("661000", "200000", "0"), ("681000", "100000", "0"), ("671000", "20000", "0"), ("701000", "0", "910000"),
])
# Exercice précédent (fictif)
BALANCE_N1 = tb([
    ("211000", "1000000", "0"), ("281000", "0", "200000"), ("311000", "140000", "0"), ("411000", "200000", "0"),
    ("521000", "120000", "0"), ("101000", "0", "600000"), ("162000", "0", "500000"), ("401000", "0", "160000"),
    ("601000", "450000", "0"), ("661000", "190000", "0"), ("681000", "100000", "0"), ("671000", "30000", "0"),
    ("701000", "0", "770000"),
])


def load():
    structure = parse_structure(STRUCTURE)
    assert not structure.has_errors, structure.issues
    codes = {r.line_code for r in structure.records}
    mappings = parse_mappings(MAPPINGS, set())
    assert not mappings.has_errors, mappings.issues
    concepts = parse_concepts(CONCEPT_ROWS, codes, set(CONCEPTS))
    assert not concepts.has_errors, concepts.issues
    line_defs = [LineDef(r.statement_type, r.line_code, r.label, r.display_order, r.kind, tuple(r.formula), r.role,
                         r.level) for r in structure.records]
    rules = [MappingRule(m.statement_type, m.line_code, m.account_prefix, tuple(m.excluded_prefixes), m.balance_rule,
                         m.amount_column, m.sign, m.priority) for m in mappings.records]
    return line_defs, rules, {c.concept_code: c.expression_ast for c in concepts.records}, structure, concepts
