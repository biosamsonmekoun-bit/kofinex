"""Contrôle de gestion : cas de référence calculés à la main (données FICTIVES de test)."""

from datetime import date
from decimal import Decimal as D

import pytest

from app.engines.management import ManagementError
from app.engines.management.actuals import BalanceRow, CostEntry, fiscal_period, prefix_nature
from app.engines.management.budget import BudgetLine, project_from_actuals, track
from app.engines.management.costing import full_cost, solve_reciprocal
from app.engines.management.cvp import cvp
from app.engines.management.forecast import cagr, linear_trend
from app.engines.management.standards import standard_variances

# plan fictif : natures seulement
NATURES = {"2": "actif", "6": "charge", "60": "charge", "601": "charge", "61": "charge", "62": "charge",
           "63": "charge", "64": "charge", "65": "charge", "66": "charge", "7": "produit", "70": "produit",
           "701": "produit", "702": "produit"}


def bal(**amounts):
    """Balance de clôture : montants positifs = solde débiteur, négatifs = solde créditeur."""
    rows = []
    for acct, v in amounts.items():
        v = D(str(v))
        rows.append(BalanceRow(acct.lstrip("a"), v if v > 0 else D(0), -v if v < 0 else D(0)))
    return rows


# ------------------------------------------------------------------ réalisé et budget
def test_nature_et_refus_des_comptes_de_bilan():
    assert prefix_nature("6011", NATURES) == "charge"
    with pytest.raises(ManagementError, match="actif"):
        prefix_nature("21", NATURES)
    with pytest.raises(ManagementError, match="absente"):
        prefix_nature("9", NATURES)


def test_periode_d_exercice_decale():
    assert fiscal_period(date(2025, 7, 1), date(2025, 7, 15)) == 1
    assert fiscal_period(date(2025, 7, 1), date(2026, 6, 30)) == 12


def test_suivi_budgetaire_ecarts_et_sens():
    b = bal(a601=D("10500"), a62=D("3000"), a701=D("-52000"), a702=D("-1000"))
    lines = [BudgetLine("601", None, "Achats", p, D("1000")) for p in range(1, 13)]          # 12 000
    lines += [BudgetLine("62", None, "Services extérieurs", 0, D("2500")),
              BudgetLine("70", None, "Ventes", 0, D("50000"))]
    t = track(lines, chart_natures=NATURES, balance=b, cost_entries=[], center_parent={}, fy_start=date(2025, 1, 1))
    rows = {r.key[0]: r for r in t.rows}
    achats = rows["601"]
    assert achats.budget == D("12000") and achats.actual == D("10500")
    assert achats.variance == D("-1500.00") and achats.favorable is True and achats.realization_pct == D("87.5")
    assert any("mensuel" in n for n in achats.notes)
    assert rows["62"].variance == D("500.00") and rows["62"].favorable is False
    ventes = rows["70"]
    assert ventes.actual == D("53000") and ventes.favorable is True
    assert t.totals["solde"] == {"budget": D("35500"), "actual": D("39500"), "variance": D("4000.00")}


def test_chevauchement_signale_et_totaux_non_calcules():
    b = bal(a601=D("100"))
    lines = [BudgetLine("60", None, "Achats", 0, D("100")), BudgetLine("601", None, "dont marchandises", 0, D("50"))]
    t = track(lines, chart_natures=NATURES, balance=b, cost_entries=[], center_parent={}, fy_start=date(2025, 1, 1))
    assert t.warnings and t.totals == {}


def test_suivi_par_centre_avec_sous_centres_et_mois():
    entries = [CostEntry("atelier", "601", date(2025, 1, 10), D("400")),
               CostEntry("atelier-a", "601", date(2025, 2, 3), D("100")),
               CostEntry("atelier-a", "62", date(2025, 2, 4), D("50")),
               CostEntry("admin", "601", date(2025, 2, 5), D("999"))]
    parent = {"atelier": None, "atelier-a": "atelier", "admin": None}
    lines = [BudgetLine("601", "atelier", "Matières atelier", 1, D("300")),
             BudgetLine("601", "atelier", "Matières atelier", 2, D("300"))]
    t = track(lines, chart_natures=NATURES, balance=None, cost_entries=entries, center_parent=parent,
              fy_start=date(2025, 1, 1))
    r = t.rows[0]
    assert r.actual == D("500") and r.actual_by_period == {1: D("400"), 2: D("100")}
    assert r.variance == D("-100.00") and r.favorable is True


def test_prevision_par_hypotheses():
    b = bal(a601=D("10000"), a70=D("-50000"))
    lines = project_from_actuals(b, [("601", "Achats", D("5")), ("70", "Ventes", D("-2.5"))], NATURES, "equal")
    achats = [x for x in lines if x.account_prefix == "601"]
    assert len(achats) == 12 and sum(x.amount for x in achats) == D("10500.00")
    assert achats[0].amount == D("875.00")
    ventes = [x for x in lines if x.account_prefix == "70"]
    assert sum(x.amount for x in ventes) == D("48750.00")
    assert ventes[-1].amount == D("48750.00") - D("4062.50") * 11


# ------------------------------------------------------------------ coûts complets
def test_prestations_reciproques_exactes():
    t = solve_reciprocal({"A1": D("9500"), "A2": D("3000")},
                         {"A1": {"A2": D("20"), "M1": D("40"), "M2": D("40")},
                          "A2": {"A1": D("10"), "M1": D("50"), "M2": D("40")}})
    assert t == {"A1": D("10000"), "A2": D("5000")}


def _params():
    return {
        "centers": [
            {"code": "A1", "name": "Entretien", "kind": "auxiliary"},
            {"code": "A2", "name": "Gestion du personnel", "kind": "auxiliary"},
            {"code": "M1", "name": "Usinage", "kind": "main",
             "allocation": {"type": "work_unit", "unit": "heure-machine", "volume": "1000"}},
            {"code": "M2", "name": "Montage", "kind": "main",
             "allocation": {"type": "work_unit", "unit": "unité montée", "volume": "600"}},
        ],
        "objects": [{"code": "P1", "name": "Produit 1", "quantity": "100", "sold_quantity": "80", "revenue": "40000"},
                    {"code": "P2", "name": "Produit 2", "quantity": "50", "revenue": "30000"}],
        "charges": [{"prefix": "601", "keys": {"P1": "75", "P2": "25"}},
                    {"prefix": "61", "keys": {"A1": "100"}}, {"prefix": "62", "keys": {"A2": "100"}},
                    {"prefix": "63", "keys": {"M1": "100"}}, {"prefix": "64", "keys": {"M2": "100"}}],
        "secondary": [{"from": "A1", "keys": {"A2": "20", "M1": "40", "M2": "40"}},
                      {"from": "A2", "keys": {"A1": "10", "M1": "50", "M2": "40"}}],
        "usage": [{"object": "P1", "center": "M1", "quantity": "600"}, {"object": "P1", "center": "M2", "quantity": "400"},
                  {"object": "P2", "center": "M1", "quantity": "400"}, {"object": "P2", "center": "M2", "quantity": "150"}],
    }


BAL_COSTS = bal(a601=8000, a61=9500, a62=3000, a63=20000, a64=12000, a65=1000, a701=-70000)


def test_cout_complet_cas_de_reference():
    r = full_cost(_params(), BAL_COSTS, NATURES)
    centers = {c["code"]: c for c in r.centers}
    assert centers["M1"]["total"] == D("26500") and centers["M1"]["cost_per_unit"] == D("26.5")
    assert centers["M2"]["total"] == D("18000") and centers["M2"]["cost_per_unit"] == D("30")
    objs = {o.code: o for o in r.objects}
    p1, p2 = objs["P1"], objs["P2"]
    assert p1.cost == D("33900") and p1.unit_cost == D("339") and p1.cost_of_sales == D("27120")
    assert p1.margin == D("12880")
    assert p2.cost == D("17100") and p2.margin == D("12900")
    assert r.imputation_differences == {"M1": D("0"), "M2": D("1500")}
    assert r.analytical_result == D("24280")
    assert r.total_incorporated == D("52500") and r.check_difference == 0
    assert r.non_incorporated == D("1000")          # compte 65 non repris


def test_cout_complet_refus_des_parametres_incoherents():
    p = _params()
    p["charges"][0]["keys"] = {"P1": "70", "P2": "25"}
    with pytest.raises(ManagementError, match="95"):
        full_cost(p, BAL_COSTS, NATURES)
    p = _params()
    p["charges"].append({"prefix": "6", "keys": {"M1": "100"}})
    with pytest.raises(ManagementError, match="chevauchent"):
        full_cost(p, BAL_COSTS, NATURES)
    p = _params()
    p["secondary"] = [{"from": "A1", "keys": {"A2": "100"}}, {"from": "A2", "keys": {"A1": "100"}}]
    with pytest.raises(ManagementError, match="solution unique"):
        full_cost(p, BAL_COSTS, NATURES)


# ------------------------------------------------------------------ coût-volume-profit
def test_seuil_de_rentabilite():
    b = bal(a70=-100000, a60=40000, a62=20000, a66=30000, a65=500)
    r = cvp({"revenue_prefixes": ["70"], "charges": [
        {"prefix": "60", "variable_pct": "100"}, {"prefix": "62", "variable_pct": "50"},
        {"prefix": "66", "variable_pct": "0"}]}, b, NATURES, date(2025, 1, 1), date(2025, 12, 31))
    assert r["contribution_margin"] == D("50000") and r["contribution_rate_pct"] == D("50")
    assert r["fixed_costs"] == D("40000") and r["result"] == D("10000")
    assert r["breakeven"] == D("80000") and r["breakeven_days"] == D("292")
    assert r["breakeven_date"] == date(2025, 10, 19)
    assert r["safety_index_pct"] == D("20") and r["operating_leverage"] == D("5")
    assert r["unclassified_charges"] == D("500")


# ------------------------------------------------------------------ coûts préétablis
def test_ecarts_quantite_prix():
    r = standard_variances({"actual_output": "1000", "elements": [
        {"label": "Matière", "standard_quantity_per_unit": "2", "standard_unit_cost": "5",
         "actual_quantity": "2100", "actual_unit_cost": "4.8"}]})
    e = r["elements"][0]
    assert e["quantity_variance"] == D("500") and e["price_variance"] == D("-420.0") and e["total_variance"] == D("80.0")


# ------------------------------------------------------------------ projections
def test_tendance_et_tcam():
    t = linear_trend([D(100), D(110), D(120), D(130)], 2)
    assert t["slope"] == D(10) and t["intercept"] == D(90) and t["r2"] == D(1)
    assert t["projections"] == [D(140), D(150)]
    c = cagr([D(100), D(110), D(121)], 1)
    assert c["rate_pct"].quantize(D("0.0001")) == D("10.0000")
    with pytest.raises(ManagementError):
        linear_trend([D(1), D(2)], 1)


def test_realise_mensuel_issu_du_grand_livre():
    b = bal(a601=D("10500"), a701=D("-52000"))
    lines = [BudgetLine("601", None, "Achats", p, D("1000")) for p in range(1, 13)]
    lines += [BudgetLine("70", None, "Ventes", 1, D("4000"))]
    ledger = {"601100": {1: D("800"), 2: D("9700")}, "701000": {1: D("-50000"), 3: D("-1000")}}   # débit − crédit
    t = track(lines, chart_natures=NATURES, balance=b, cost_entries=[], center_parent={}, fy_start=date(2025, 1, 1),
              ledger_monthly=ledger)
    rows = {r.key[0]: r for r in t.rows}
    assert rows["601"].actual == D("10500") and rows["601"].actual_by_period == {1: D("800"), 2: D("9700")}
    assert not any("diffère" in n for n in rows["601"].notes)
    ventes = rows["70"]
    assert ventes.actual_by_period == {1: D("50000"), 3: D("1000")}             # produits : crédit net en positif
    assert any("diffère" in n and "-1000" in n for n in ventes.notes)          # 51 000 (grand livre) − 52 000 (balance)
