"""Balance hiérarchique : un auxiliaire (4011TOY) remonte dans 4011000, puis dans les comptes du référentiel
(4011, 401, classe 4), sans être compté deux fois. Montants FICTIFS calculés à la main."""

from datetime import date
from decimal import Decimal as D

from app.engines.accounting.native_ledger import Posted, trial_balance, with_subtotals

# hiérarchie du référentiel (classes, comptes, subdivisions) : donnée, pas de niveau codé
CHART = {"4": "Comptes de tiers", "40": "Fournisseurs et comptes rattachés", "401": "Fournisseurs",
         "4011": "Fournisseurs – divisionnaire", "6": "Comptes de charges", "601": "Achats de marchandises"}
DAY = date(2026, 3, 1)
LINES = [
    Posted("4011000", DAY, D("0"), D("1000"), third_party="TOY"),        # fournisseur TOYOTA
    Posted("4011000", DAY, D("0"), D("500"), third_party="AUT"),         # autre fournisseur
    Posted("4010000", DAY, D("0"), D("200")),                            # principal, sans tiers
    Posted("6011000", DAY, D("1700"), D("0")),
]


def _rows(tb):
    return [{**r, "third_party": {"code": r["third_party"]} if r["third_party"] else None} for r in tb["rows"]]


def test_balance_generale_sous_totaux_sans_double_comptage():
    tb = trial_balance(LINES)
    out = with_subtotals(_rows(tb), CHART)
    sub = {r["account"]: r for r in out if r["kind"] == "subtotal"}
    # 4011000 = 1 000 + 500 ; 401 = 4010000 + 4011000 = 1 700 ; classe 4 = 1 700 (et non 1 500 + 1 700 + …)
    assert sub["4011"]["closing_credit"] == D("1500") and sub["4011"]["rows"] == 1
    assert sub["401"]["closing_credit"] == D("1700") and sub["401"]["rows"] == 2
    assert sub["40"]["closing_credit"] == D("1700") and sub["4"]["closing_credit"] == D("1700")
    assert sub["601"]["closing_debit"] == D("1700") and sub["6"]["closing_debit"] == D("1700")
    # totaux généraux : lignes de détail seulement, balance équilibrée
    assert tb["totals"]["closing_debit"] == tb["totals"]["closing_credit"] == D("1700")
    details = [r for r in out if r["kind"] == "detail"]
    assert sum((r["closing_credit"] for r in details), D(0)) == D("1700")
    # ordre : détail puis sous-totaux du plus fin au plus large, classe par classe
    assert [(r["kind"][0], r["account"]) for r in out] == [
        ("d", "4010000"), ("d", "4011000"), ("s", "4011"), ("s", "401"), ("s", "40"), ("s", "4"),
        ("d", "6011000"), ("s", "601"), ("s", "6")]
    assert sub["4"]["level"] == 0 and sub["4011"]["level"] == 3


def test_balance_auxiliaire_tiers_regroupes_par_compte():
    tb = trial_balance([p for p in LINES if p.third_party], by_third_party=True)
    out = with_subtotals(_rows(tb), CHART, auxiliary=True)
    sub = {r["account"]: r for r in out if r["kind"] == "subtotal"}
    tiers = [(r["third_party"]["code"], r["closing_credit"]) for r in out if r["kind"] == "detail"]
    assert tiers == [("AUT", D("500")), ("TOY", D("1000"))]            # soldes individuels
    assert sub["4011000"]["closing_credit"] == D("1500") and sub["4011000"]["rows"] == 2
    assert sub["4011"]["closing_credit"] == D("1500") and sub["4"]["closing_credit"] == D("1500")


def test_compte_identique_au_referentiel_sans_sous_total_redondant():
    # compte de l'entreprise 601 identique au compte du référentiel : pas de sous-total 601 qui le répéterait
    tb = trial_balance([Posted("601", DAY, D("10"), D("0")), Posted("4011000", DAY, D("0"), D("10"))])
    out = with_subtotals(_rows(tb), CHART)
    assert [r["account"] for r in out if r["kind"] == "subtotal"] == ["4011", "401", "40", "4", "6"]
