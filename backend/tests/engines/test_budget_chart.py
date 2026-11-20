"""Phase 3 du correctif du contrôle de gestion : budget relié au plan comptable. Cas calculés à la main, FICTIFS."""

from datetime import date
from decimal import Decimal as D
from types import SimpleNamespace

from app.engines.management.actuals import BalanceRow
from app.engines.management.budget import BudgetLine, track
from app.services.management import INVESTMENT_SIGN, account_issue

FY = date(2026, 1, 1)


def test_rubriques_sans_compte_distinctes_et_hors_totaux():
    lines = [BudgetLine("601", None, "Achats", 0, D("1000")), BudgetLine(None, None, "Aléas", 0, D("300")),
             BudgetLine(None, None, "Missions", 0, D("200"))]
    t = track(lines, chart_natures={"601": "charge"}, balance=[BalanceRow("601100", D("900"), D("0"))],
              cost_entries=[], center_parent={}, fy_start=FY)
    rub = {r.label: r for r in t.rows if r.nature == "rubrique"}
    assert set(rub) == {"Aléas", "Missions"} and rub["Aléas"].budget == D("300") and rub["Aléas"].actual is None
    assert t.totals["charge"] == {"budget": D("1000"), "actual": D("900"), "variance": D("-100.00")}   # rubriques exclues


def test_investissement_reel_sur_mouvements_et_sens():
    # mouvements de l'exercice (hors à-nouveaux) : acquisitions 211 = 500 − 100 = 400 ; emprunts 162 = 1 000 − 200 = 800
    natures = {"211": INVESTMENT_SIGN["asset"], "162": INVESTMENT_SIGN["liability"]}
    movements = [BalanceRow("211000", D("500"), D("100")), BalanceRow("162000", D("200"), D("1000"))]
    t = track([BudgetLine("211", None, "Terrains", 0, D("600")), BudgetLine("162", None, "Emprunts", 0, D("1000"))],
              chart_natures=natures, balance=movements, cost_entries=[], center_parent={}, fy_start=FY)
    rows = {r.label: r for r in t.rows}
    assert rows["Terrains"].actual == D("400") and rows["Emprunts"].actual == D("800")


def test_controle_des_comptes_selon_le_type():
    general = SimpleNamespace(label="Budget de résultat", allowed_prefixes=["6", "7", "8"], allowed_natures=["expense", "income"])
    invest = SimpleNamespace(label="Investissements", allowed_prefixes=["2", "16"], allowed_natures=["asset", "liability"])
    refs = {"601100": {"is_active": True, "nature": "expense"}, "601200": {"is_active": False, "nature": "expense"},
            "211000": {"is_active": True, "nature": "asset"}, "401000": {"is_active": True, "nature": "liability"}}
    assert account_issue("601100", refs, general) is None and account_issue("211000", refs, invest) is None
    assert "absent du plan comptable de référence" in account_issue("609000", refs, general)
    assert "en sommeil" in account_issue("601200", refs, general)
    assert "hors des racines autorisées" in account_issue("211000", refs, general)
    assert "hors des racines autorisées" in account_issue("401000", refs, invest)      # bilan hors 2 et 16
