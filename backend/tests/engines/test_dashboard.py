"""Tableau de bord : regroupements selon le plan publié (nature et libellés), parts, variations, série mensuelle."""

from decimal import Decimal as D

from app.engines.financial import dashboard as dash

CHART = dash.Chart({
    "60": ("ACHATS ET VARIATIONS DE STOCKS", "expense"), "62": ("SERVICES EXTERIEURS", "expense"),
    "64": ("IMPOTS ET TAXES", "expense"), "66": ("CHARGES DE PERSONNEL", "expense"), "67": ("FRAIS FINANCIERS", "expense"),
    "701": ("VENTES DE MARCHANDISES", "income"), "706": ("SERVICES VENDUS", "income"), "75": ("AUTRES PRODUITS", "income"),
    "52": ("BANQUES", "asset"),
})


def test_nature_et_rubrique_depuis_le_plan():
    assert CHART.nature("601100") == "expense" and CHART.nature("706000") == "income" and CHART.nature("999") is None
    assert CHART.group("661000") == ("66", "CHARGES DE PERSONNEL")
    assert CHART.group("701200") == ("701", "VENTES DE MARCHANDISES")          # pas de rubrique « 70 » dans le plan


def test_repartition_des_charges_avec_autres():
    bal = {"601": D("320"), "622": D("172"), "641": D("50"), "661": D("401"), "671": D("56"), "521": D("1000"), "999": D("5")}
    r = dash.breakdown(bal, CHART, "expense")
    assert r["total"] == D("999")
    assert [(g["key"], g["amount"], g["share"]) for g in r["groups"]] == [
        ("66", D("401"), D("40.1")), ("60", D("320"), D("32.0")), ("62", D("172"), D("17.2")), ("autres", D("106"), D("10.6"))]
    assert r["groups"][-1]["includes"] == ["67", "64"] and r["unclassified_accounts"] == 1


def test_produits_au_credit():
    r = dash.breakdown({"701": D("-583"), "706": D("-247"), "758": D("-170")}, CHART, "income")
    assert r["total"] == D("1000") and r["groups"][0] == {"key": "701", "label": "VENTES DE MARCHANDISES", "amount": D("583"), "share": D("58.3")}


def test_variation_convention_de_la_bibliotheque():
    assert dash.variation("112.5", "100") == D("12.5")
    assert dash.variation("-50", "-100") == D("50.0")                            # base |N-1|
    assert dash.variation("10", "0") is None and dash.variation("10", None) is None


def test_serie_mensuelle_et_mois_de_l_exercice():
    months = dash.fiscal_months(2024, 7, 2025, 6)
    assert len(months) == 12 and months[0] == (1, 2024, 7) and months[-1] == (12, 2025, 6)
    series = {"701": {1: D("-100"), 2: D("-120")}, "601": {1: D("60")}, "521": {1: D("999")}}
    out = dash.monthly(series, CHART, months[:2])
    assert out == [{"period": 1, "label": "Juil.", "year": 2024, "income": D("100"), "expense": D("60")},
                   {"period": 2, "label": "Août", "year": 2024, "income": D("120"), "expense": D("0")}]
