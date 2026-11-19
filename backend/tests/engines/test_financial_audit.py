"""Audit financier : cas calculés à la main."""

from decimal import Decimal as D

import pytest

from app.engines.accounting.statements import LineDef, MappingRule, TBEntry
from app.engines.audit import financial as fa


def tb(acc, debit="0", credit="0", label=None):
    d, c = D(debit), D(credit)
    return TBEntry(acc, label, D(0), D(0), d, c, d, c)


def test_materiality_amounts():
    m = fa.materiality(D("12345678"), D("1.5"), D("75"), D("5"))
    assert m.overall == D("185185.17")        # 12 345 678 × 1,5 % = 185 185,17
    assert m.performance == D("138888.88")    # 185 185,17 × 75 % = 138 888,8775
    assert m.trivial == D("9259.26")          # 185 185,17 × 5 % = 9 259,2585
    with pytest.raises(ValueError):
        fa.materiality(D("0"), D("1"), D("50"), D("5"))
    with pytest.raises(ValueError):
        fa.materiality(D("100"), D("0"), D("50"), D("5"))


def test_account_variations_and_cycles():
    cur = [tb("411000", "1500"), tb("401000", credit="800"), tb("521000", "10")]
    prev = [tb("411000", "1000"), tb("401000", credit="800"), tb("601000", "50")]
    rows = {r.account: r for r in fa.account_variations(cur, prev, D("400"))}
    assert rows["411000"].variation == D("500") and rows["411000"].variation_pct == D("50.00")
    assert rows["411000"].above_threshold
    assert rows["401000"].variation == D("0") and not rows["401000"].above_threshold
    assert rows["601000"].balance_n == D("0") and rows["601000"].variation == D("-50")
    assert rows["521000"].variation_pct is None          # N-1 nul
    no_prev = fa.account_variations(cur, None, D("1000"))
    assert [r.account for r in no_prev if r.above_threshold] == ["411000"]
    maps = [("4", "TIERS"), ("41", "CLIENTS"), ("5", "TRESO")]
    assert fa.cycle_for("411000", maps) == "CLIENTS"
    assert fa.cycle_for("401000", maps) == "TIERS"
    assert fa.cycle_for("601000", maps) is None


ITEMS = [fa.PopItem(f"i{k}", D(v)) for k, v in enumerate(["100", "-250", "4000", "50", "600", "0", "1000", "2000"])]


def test_random_and_systematic_are_reproducible():
    a = fa.select_random(ITEMS, 3, seed=42)
    b = fa.select_random(ITEMS, 3, seed=42)
    assert a.item_ids == b.item_ids and len(set(a.item_ids)) == 3
    s = fa.select_systematic(ITEMS, 4, seed=7)
    assert len(set(s.item_ids)) == 4 and s.parameters["interval"] == "2"
    idx = [int(i[1:]) for i in s.item_ids]
    assert all(b - a == 2 for a, b in zip(idx, idx[1:], strict=False))   # pas de 2 éléments
    with pytest.raises(ValueError):
        fa.select_random(ITEMS, 9, seed=1)


def test_mus_selects_large_items_and_respects_interval():
    # Σ|montants| = 8 000 ; taille 4 → intervalle 2 000 : les éléments de 4 000 et 2 000 sont nécessairement touchés
    s = fa.select_mus(ITEMS, 4, seed=3)
    assert s.parameters["interval"] == "2000.00"
    assert "i2" in s.item_ids and "i7" in s.item_ids
    assert s.reasons["i2"] == "key_item"
    assert "i5" not in s.item_ids                           # un montant nul n'est jamais sélectionné
    assert fa.select_mus(ITEMS, 4, seed=3).item_ids == s.item_ids


def test_key_items():
    s = fa.select_key_items(ITEMS, D("1000"))
    assert s.item_ids == ["i2", "i6", "i7"]
    with pytest.raises(ValueError):
        fa.select_key_items(ITEMS, D("10000"))


def test_projection_ratio_and_mus():
    items = [fa.TestedItem(D("1000"), D("900")), fa.TestedItem(D("500"), D("500")), fa.TestedItem(D("300"), None)]
    p = fa.project("random", D("30000"), items)
    # anomalie 100 sur 1 500 testés → 100 / 1 500 × 30 000 = 2 000
    assert p.actual == D("100") and p.projected == D("2000.00") and p.pending == 1 and p.method == "ratio"
    m = fa.project("mus", D("8000"), [fa.TestedItem(D("500"), D("400")), fa.TestedItem(D("4000"), D("3900"))],
                   interval=D("2000"))
    # 100/500 × 2 000 = 400 ; élément ≥ J : 100 → 500
    assert m.projected == D("500.00") and m.method == "mus_tainting"
    k = fa.project("key_items", D("8000"), [fa.TestedItem(D("4000"), D("3000"))])
    assert k.projected is None and k.actual == D("1000")


def test_adjustment_effects_through_statement_engine():
    structure = [
        LineDef("income_statement", "RA", "Ventes", 1, "detail"),
        LineDef("income_statement", "RB", "Achats", 2, "detail"),
        LineDef("income_statement", "XI", "Résultat net", 3, "total", ((1, "RA"), (-1, "RB")), "resultat_compte_resultat"),
        LineDef("balance_sheet_assets", "BH", "Clients", 1, "detail"),
        LineDef("balance_sheet_assets", "BZ", "Total actif", 2, "total", ((1, "BH"),), "total_actif"),
    ]
    rules = [MappingRule("income_statement", "RA", "70", (), "net_credit", "net", 1, 0),
             MappingRule("income_statement", "RB", "60", (), "net_debit", "net", 1, 0),
             MappingRule("balance_sheet_assets", "BH", "41", (), "debit_balance", "net", 1, 0)]
    entries = [tb("411000", "5000"), tb("701000", credit="8000"), tb("601000", "3000")]
    lines = [fa.AdjLine("701000", None, D("1200"), D("0")), fa.AdjLine("411000", None, D("0"), D("1200"))]
    fa.check_balanced(lines)
    eff = {e.code: e for e in fa.effects(entries, lines, structure, rules)}
    assert eff["XI"].before == D("5000") and eff["XI"].delta == D("-1200")
    assert eff["BZ"].delta == D("-1200") and "RB" not in eff
    adj = {e.account_number: e for e in fa.adjust(entries, lines)}
    assert adj["411000"].closing_net == D("3800") and entries[0].closing_net == D("5000")   # balance d'origine intacte
    with pytest.raises(ValueError):
        fa.check_balanced([fa.AdjLine("701000", None, D("10"), D("0"))])
    with pytest.raises(ValueError):
        fa.check_balanced([fa.AdjLine("701000", None, D("10"), D("10")), fa.AdjLine("411000", None, D("0"), D("0"))])
    assert fa.compare_to_materiality(D("-1200"), D("1000"), D("50")) == "above_overall"
    assert fa.compare_to_materiality(D("40"), D("1000"), D("50")) == "below_trivial"
    assert fa.compare_to_materiality(D("40"), None, None) is None


def test_parse_population_from_rows():
    rows = [["Facture", "Date", "Client", "Compte", "Montant"],
            ["F1", "31/12/2025", "Alpha", "411100", "1 200,50"],
            [None, None, None, None, None],
            ["F2", "2025-12-15", "Beta", 411200.0, "(300,00)"]]
    p = fa.parse_population(rows, 0, {"reference": 0, "date": 1, "label": 2, "account": 3, "amount": 4})
    assert p.ok and [i.amount for i in p.items] == [D("1200.50"), D("-300.00")]
    assert p.items[1].account == "411200" and str(p.items[0].item_date) == "2025-12-31"
    bad = fa.parse_population(rows + [["F3", "x", None, None, "12"]], 0, {"reference": 0, "date": 1, "amount": 4})
    assert not bad.ok and bad.issues[0]["row"] == 5
