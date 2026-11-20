"""Plan de trésorerie : scénarios du cahier des charges, calculés à la main. Montants FICTIFS."""

from decimal import Decimal as D

import pytest

from app.engines.management.treasury_plan import (
    CashLine, Rubric, TreasuryError, actuals, compute, percent_of, rollup, rolling, shift, spread, variance,
)

Z = D("0")


def m(*vals):
    """Douze mois : valeurs données pour les premiers mois, zéro ensuite."""
    return [D(str(v)) for v in vals] + [Z] * (12 - len(vals))


RUB = [Rubric("A", "receipts", "Encaissements clients", code="70"),
       Rubric("B", "disbursements", "Décaissements fournisseurs", code="60")]


def test_scenario_de_reference_et_report_du_solde():
    # solde initial 10 000 000 ; janvier : encaissements 15 000 000, décaissements 18 000 000 ; février sans mouvement
    p = compute(RUB, {"A": m(15_000_000), "B": m(18_000_000)}, D("10000000"))
    assert p.net[0] == D("-3000000") and p.closing[0] == D("7000000")
    assert p.opening[1] == D("7000000") and p.closing[1] == D("7000000")        # mois sans mouvement
    assert p.annual == {"receipts": D("15000000"), "disbursements": D("18000000"), "net": D("-3000000"),
                        "opening": D("10000000.00"), "closing": D("7000000.00")}
    assert p.negative_months == [] and p.financing_need == Z


def test_solde_negatif_et_besoin_de_financement():
    p = compute(RUB, {"A": m(1_000, 0, 500), "B": m(0, 4_000, 0)}, D("2000"))
    # 2 000 + 1 000 = 3 000 ; − 4 000 = −1 000 ; + 500 = −500
    assert p.closing[:3] == [D("3000"), D("-1000"), D("-500")]
    assert p.negative_months[:2] == [2, 3] and p.financing_need == D("1000")


def test_sous_rubriques_sans_double_comptage():
    rubs = [Rubric("V", "receipts", "Ventes", code="70"), Rubric("V1", "receipts", "Dépôt", parent_id="V"),
            Rubric("V2", "receipts", "Économat", parent_id="V"), Rubric("P", "disbursements", "Personnel", code="66")]
    p = compute(rubs, {"V1": m(800_000), "V2": m(350_000), "P": m(705_000)}, Z)
    rows = {r["id"]: r for r in p.rows}
    assert rows["V"]["months"][0] == D("1150000") and rows["V"]["has_children"] and rows["V1"]["level"] == 1
    assert p.receipts[0] == D("1150000")                                       # et non 2 300 000
    assert p.annual["receipts"] == D("1150000") and p.closing[0] == D("445000")


def test_prevision_modifiee_et_comparaison_au_realise():
    initial = compute(RUB, {"A": m(100), "B": m(80)}, Z)
    updated = compute(RUB, {"A": m(120), "B": m(80)}, Z)
    assert initial.closing[0] == D("20") and updated.closing[0] == D("40")
    v = variance([D("120"), D("50"), Z], [D("90"), None, D("10")])
    assert v[0] == {"forecast": D("120"), "actual": D("90"), "variance": D("-30"), "rate": D("75.0")}
    assert v[1]["actual"] is None and v[2]["rate"] is None                     # prévision nulle : pas de taux


def test_reel_par_contrepartie_flux_hors_gestion_et_transferts():
    rubs = [Rubric("CLI", "receipts", "Règlements clients", prefixes=("411",)),
            Rubric("EMP", "receipts", "Emprunts reçus", prefixes=("16",)),
            Rubric("FOU", "disbursements", "Règlements fournisseurs", prefixes=("401",)),
            Rubric("BQ", "disbursements", "Frais bancaires", prefixes=("631",))]
    lines = [
        # janvier : règlement client 1 000 net de 10 de frais (banque 990)
        CashLine("e1", "521", 1, D("990"), Z, True), CashLine("e1", "411", 1, Z, D("1000"), False),
        CashLine("e1", "631", 1, D("10"), Z, False),
        # janvier : emprunt reçu 5 000 (flux sans compte de charge ni de produit)
        CashLine("e2", "521", 1, D("5000"), Z, True), CashLine("e2", "162", 1, Z, D("5000"), False),
        # février : règlement fournisseur 700 (et non l'achat 601 du même mois, qui ne touche pas la trésorerie)
        CashLine("e3", "521", 2, Z, D("700"), True), CashLine("e3", "401", 2, D("700"), Z, False),
        # février : virement interne banque → caisse, ignoré
        CashLine("e4", "571", 2, D("300"), Z, True), CashLine("e4", "521", 2, Z, D("300"), True),
        # mars : encaissement sans rubrique (apport 101), « non affecté »
        CashLine("e5", "521", 3, D("2000"), Z, True), CashLine("e5", "101", 3, Z, D("2000"), False),
    ]
    a = actuals(lines, rubs)
    assert a["by_rubric"]["CLI"][0] == D("1000") and a["by_rubric"]["BQ"][0] == D("10")
    assert a["by_rubric"]["EMP"][0] == D("5000") and a["by_rubric"]["FOU"][1] == D("700")
    assert a["unassigned"]["receipts"][2] == D("2000")
    assert a["receipts"][:3] == [D("6000"), Z, D("2000")] and a["disbursements"][:3] == [D("10"), D("700"), Z]
    assert a["cash_change"][:3] == [D("5990"), D("-700"), D("2000")] and a["check"] is True


def test_reel_des_rubriques_parentes():
    rubs = [Rubric("V", "receipts", "Ventes", prefixes=("70",)), Rubric("V1", "receipts", "Dépôt", parent_id="V", prefixes=("7011",))]
    out = rollup(rubs, {"V": m(10), "V1": m(5)})
    assert out["V"][0] == D("15") and out["V1"][0] == D("5")


def test_modalites_de_prevision():
    assert spread(D("5610169")) == [D("467514.08")] * 11 + [D("467514.12")]     # reste sur le dernier mois
    assert sum(spread(D("5610169")), Z) == D("5610169")
    assert percent_of(m(705_000, 850_000), D("19.4"))[:2] == [D("136770.00"), D("164900.00")]
    months, beyond = shift({1: D("100"), 11: D("200"), 12: D("300")}, 1)       # délai de règlement d'un mois
    assert months[1] == D("100") and months[11] == D("200") and beyond == D("300")
    with pytest.raises(TreasuryError):
        shift({1: D("1")}, 13)


def test_prevision_glissante():
    r = rolling(D("1000"), [D("100"), D("-50"), None, None], [D("90"), D("-40"), D("-2000"), None])
    assert [x["basis"] for x in r["months"]] == ["actual", "actual", "forecast", "none"]
    assert r["months"][2]["closing"] == D("-950") and r["negative_months"] == [3]
    assert r["financing_need"] == D("950") and r["complete"] is False          # aucun mois inventé au-delà du plan


def test_montant_negatif_refuse():
    with pytest.raises(TreasuryError):
        compute(RUB, {"A": m(-1)}, Z)
