"""Pilotage : périodes (exercice décalé, période équivalente N-1), soldes AO / HAO, Top 10 (part du total de la
catégorie), clients et fournisseurs (règlements exclus, avoirs déduits), trésorerie (transferts internes exclus,
contrôle du solde), masse salariale, prévision à terminaison, alertes à seuils, classements budgétaires.
Cas calculés à la main ; données FICTIVES."""

from datetime import date
from decimal import Decimal as D

from app.engines.management import steering as st

C = st.AccountClass
CLS = {
    "701100": C("income", "AO", revenue=True, label="Ventes A", rubric_label="Ventes de marchandises"),
    "706100": C("income", "AO", revenue=True, label="Services"),
    "758100": C("income", "AO", label="Produits divers"),
    "601100": C("expense", "AO", label="Achats"),
    "661100": C("expense", "AO", personnel=True, label="Salaires"),
    "664100": C("expense", "AO", personnel=True, label="Charges sociales"),
    "821100": C("income", "HAO", label="Cessions"),
    "831100": C("expense", "HAO", label="Charges HAO"),
    "891000": C("expense", "OTHER", label="Impôt sur le résultat"),
    "411100": C("asset", partner="customer", label="Clients"),
    "401100": C("liability", partner="supplier", label="Fournisseurs"),
    "521100": C("asset", treasury=True, label="Banque"),
    "571100": C("asset", treasury=True, label="Caisse"),
    "101000": C("equity", label="Capital"),
}


def M(acc, d, dv="0", cv="0", key="e", tp=None, opening=False, jt=None):  # noqa: N802
    return st.Movement(acc, d, D(dv), D(cv), key, is_opening=opening, third_party=tp, third_party_label=tp, journal_type=jt)


MOVS = [
    M("521100", date(2025, 1, 1), "1000", key="an", opening=True, jt="bank"),
    M("101000", date(2025, 1, 1), cv="1000", key="an", opening=True),
    # ventes : C1 (2 factures, 1 avoir), C2 ; une écriture à deux clients
    M("411100", date(2025, 1, 10), "1200", key="v1", tp="C1"),
    M("701100", date(2025, 1, 10), cv="1200", key="v1"),
    M("411100", date(2025, 2, 10), "800", key="v2", tp="C2"),
    M("706100", date(2025, 2, 10), cv="800", key="v2"),
    M("411100", date(2025, 2, 20), cv="200", key="av", tp="C1"),
    M("701100", date(2025, 2, 20), "200", key="av"),
    M("411100", date(2025, 3, 5), "100", key="mx", tp="C1"),
    M("411100", date(2025, 3, 5), "100", key="mx", tp="C2"),
    M("701100", date(2025, 3, 5), cv="200", key="mx"),
    # règlement client (pas un produit), achat fournisseur F1, paie, HAO, impôt
    M("521100", date(2025, 2, 28), "1000", key="r1", jt="bank"),
    M("411100", date(2025, 2, 28), cv="1000", key="r1", tp="C1"),
    M("601100", date(2025, 1, 15), "500", key="a1"),
    M("401100", date(2025, 1, 15), cv="500", key="a1", tp="F1"),
    M("401100", date(2025, 2, 15), "500", key="p1", tp="F1"),
    M("521100", date(2025, 2, 15), cv="500", key="p1", jt="bank"),
    M("661100", date(2025, 1, 31), "300", key="s1"),
    M("664100", date(2025, 1, 31), "100", key="s1"),
    M("521100", date(2025, 1, 31), cv="400", key="s1", jt="bank"),
    M("821100", date(2025, 3, 1), cv="150", key="h1"),
    M("521100", date(2025, 3, 1), "150", key="h1", jt="bank"),
    M("831100", date(2025, 3, 2), "50", key="h2"),
    M("521100", date(2025, 3, 2), cv="50", key="h2", jt="bank"),
    M("891000", date(2025, 3, 31), "40", key="i1"),
    M("521100", date(2025, 3, 31), cv="40", key="i1", jt="bank"),
    # transfert interne banque -> caisse
    M("571100", date(2025, 2, 1), "100", key="t1", jt="cash"),
    M("521100", date(2025, 2, 1), cv="100", key="t1", jt="bank"),
]
FY = (date(2025, 1, 1), date(2025, 12, 31))


def test_periodes_et_exercice_decale():
    assert st.period_range(*FY, "month", 2) == (date(2025, 2, 1), date(2025, 2, 28))
    assert st.period_range(*FY, "cumulative", 3) == (date(2025, 1, 1), date(2025, 3, 31))
    fy2 = (date(2024, 7, 1), date(2025, 6, 30))
    assert st.period_range(*fy2, "month", 1) == (date(2024, 7, 1), date(2024, 7, 31))
    prev2 = (date(2023, 7, 1), date(2024, 6, 30))
    assert st.equivalent_range((date(2024, 7, 1), date(2025, 2, 28)), fy2, prev2) == (date(2023, 7, 1), date(2024, 2, 29))
    assert st.equivalent_range(fy2, fy2, prev2) == prev2


def test_soldes_ao_hao_et_resultat():
    s = st.pl(st.nets(MOVS, FY), CLS)
    assert (s.produits_ao, s.charges_ao, s.marge_ao) == (D("2000"), D("900"), D("1100"))
    assert (s.produits_hao, s.charges_hao, s.marge_hao, s.marge_totale) == (D("150"), D("50"), D("100"), D("1200"))
    assert s.chiffre_affaires == D("2000") and s.personnel == D("400")
    assert (s.total_produits, s.total_charges, s.resultat) == (D("2150"), D("990"), D("1160"))


def test_a_nouveaux_exclus_des_flux():
    assert "101000" not in st.nets(MOVS, FY)


def test_top_part_du_total_de_categorie():
    t = st.top_accounts(st.nets(MOVS, FY), CLS, group="AO", nature="income", n=1)
    assert t["total"] == D("2000") and t["count"] == 2
    assert t["items"] == [
        {
            "key": "701100",
            "label": "Ventes A",
            "rubric": "Ventes de marchandises",
            "amount": D("1200"),
            "rank": 1,
            "share": D("60.0"),
        }
    ]


def test_top_clients_reglements_exclus_avoirs_deduits():
    t = st.top_partners(MOVS, CLS, FY, "customer")
    assert [(i["key"], i["amount"]) for i in t["items"]] == [("C1", D("1000")), ("C2", D("800"))]
    assert (
        t["total"] == D("2000")
        and t["unattributed"] == D("200")
        and t["multi_partner_entries"] == 1
        and t["coverage"] == D("90.0")
    )
    f = st.top_partners(MOVS, CLS, FY, "supplier")
    assert [(i["key"], i["amount"], i["share"]) for i in f["items"]] == [
        ("F1", D("500"), D("50.5"))
    ]  # part du total des charges (990)


def test_tresorerie_transferts_internes_et_controle():
    t = st.treasury(MOVS, CLS, FY)
    assert (t["opening"], t["receipts"], t["payments"]) == (D("1000"), D("1150"), D("990"))
    assert t["closing"] == D("1160") and t["check"] and t["internal_transfers"] == D("100")
    by = {a["account"]: a for a in t["accounts"]}
    assert by["571100"]["closing"] == D("100") and by["521100"]["closing"] == D("1060")
    cats = {c["label"]: c["amount"] for c in t["receipts_by_category"]}
    assert cats["Règlements clients"] == D("1000")


def test_masse_salariale():
    p = st.payroll(st.nets(MOVS, FY), CLS, D("2000"))
    assert p["total"] == D("400") and p["ratio_to_revenue"] == D("20.0") and p["items"][0]["account"] == "661100"


ROWS = [
    {
        "label": "Achats",
        "nature": "charge",
        "account_prefix": "60",
        "budget": "1000",
        "actual": "1150",
        "variance": "150",
        "realization_pct": "115.0",
        "budget_by_period": {"0": "1000"},
        "actual_by_period": {"1": "500", "2": "650"},
    },
    {
        "label": "Services",
        "nature": "charge",
        "account_prefix": "62",
        "budget": "1200",
        "actual": "600",
        "variance": "-600",
        "realization_pct": "50.0",
        "budget_by_period": {str(p): "100" for p in range(1, 13)},
        "actual_by_period": {"1": "300", "2": "300"},
    },
    {
        "label": "Ventes",
        "nature": "produit",
        "account_prefix": "70",
        "budget": "12000",
        "actual": "500",
        "variance": "-11500",
        "realization_pct": "4.2",
        "budget_by_period": {"0": "12000"},
        "actual_by_period": {"1": "200", "2": "300"},
    },
]


def test_prevision_a_terminaison():
    f = st.forecast(ROWS[1], 2, 12)
    assert (f["actual_to_date"], f["remaining_budget"], f["trend"]) == (D("600"), D("1600.00"), D("3600.00"))
    assert st.forecast({**ROWS[0], "actual_by_period": None}, 2, 12) == {"remaining_budget": None, "trend": None}


def test_alertes_budgetaires_a_seuils():
    alerts = st.budget_alerts(ROWS, 6, 12, st.Thresholds())
    codes = {(a["label"], a["code"], a["level"]) for a in alerts}
    assert ("Achats", "overrun", "critical") in codes
    assert ("Ventes", "revenue_shortfall", "warning") in codes
    strict = st.budget_alerts(ROWS, 6, 12, st.Thresholds(overrun_critical_pct=D(120)))
    assert ("Achats", "overrun", "warning") in {(a["label"], a["code"], a["level"]) for a in strict}


def test_classements_et_tableau_mensuel():
    tops = st.budget_tops(ROWS)
    assert [r["label"] for r in tops["overruns"]] == ["Achats"] and [r["label"] for r in tops["savings"]] == ["Services"]
    mo = st.budget_monthly(ROWS, st.fiscal_months(*FY), "charge")
    assert mo[0]["budget"] == D("183.33") and mo[0]["actual"] == D("800") and mo[0]["favorable"] is False


# ----------------------------------------------------------------- import d'un budget (Excel / CSV)
def test_import_budget_en_colonnes_et_en_lignes():
    from app.engines.management.budget import parse_budget_sheet

    lines, errors = parse_budget_sheet([["Compte", "Centre", "Libellé", "M1", "M2", "Annuel"],
                                        ["601", "", "Achats", "100", "200", None], ["", "ADM", "Frais", "1 000,50", "", ""]])
    assert errors == [] and [(x["account_prefix"], x["cost_center_code"], x["period"], x["amount"]) for x in lines] == [
        ("601", None, 1, D("100.00")), ("601", None, 2, D("200.00")), (None, "ADM", 1, D("1000.50"))]
    lines, errors = parse_budget_sheet([["compte", "libelle", "periode", "montant"], ["70", "Ventes", 0, "12000"],
                                        ["62", "Services", "x", "5"], ["6X", "Mauvais", 1, "5"], ["60", "Précis", 1, "1.005"]])
    assert [x["account_prefix"] for x in lines] == ["70"] and len(errors) == 3
    assert parse_budget_sheet([["a", "b"]])[1] and parse_budget_sheet([])[1] == ["Fichier vide."]


# ----------------------------------------------------------------- écarts avec le modèle Excel de référence
def test_montants_nets_extourne_de_facture_a_etablir():
    # facture à établir de 1 000 extournée par une OD au débit du compte de produit : le net est nul, le brut serait 1 000
    movs = [M("701100", date(2025, 1, 31), cv="1000", key="fae"), M("411100", date(2025, 1, 31), "1000", key="fae", tp="C1"),
            M("701100", date(2025, 2, 1), "1000", key="ext"), M("411100", date(2025, 2, 1), cv="1000", key="ext", tp="C1")]
    s = st.pl(st.nets(movs, FY), CLS)
    assert s.produits_ao == D("0") and s.chiffre_affaires == D("0")


def test_impot_hors_hao():
    s = st.pl(st.nets(MOVS, FY), CLS)
    assert s.autres_charges == D("40") and s.marge_hao == D("100")      # 891 : impôt, hors HAO


def test_classement_des_tiers_sur_montants_factures():
    t = st.top_partners(MOVS, CLS, FY, "customer", basis="invoiced")
    # débits des comptes clients : C1 1 200 + 100 ; C2 800 + 100 ; règlements (crédits) et avoir exclus
    assert t["basis"] == "invoiced" and [(i["key"], i["amount"]) for i in t["items"]] == [("C1", D("1300")), ("C2", D("900"))]
    f = st.top_partners(MOVS, CLS, FY, "supplier", basis="invoiced")
    assert [(i["key"], i["amount"]) for i in f["items"]] == [("F1", D("500"))]   # le règlement (débit) n'est pas compté
    assert st.top_partners(MOVS, CLS, FY, "customer")["basis"] == "revenue"


def test_cumul_budgetaire_et_ecart_mensuel_en_decimal():
    months = [{"budget": D("100"), "actual": D("80")}, {"budget": D("100"), "actual": D("150")}, {"budget": D("100"), "actual": None}]
    c = st.cumulate(months, "charge")
    assert [(x["budget"], x["actual"], x["variance"], x["rate"], x["favorable"]) for x in c] == [
        (D("100"), D("80"), D("-20"), D("80.0"), True), (D("200"), D("230"), D("30"), D("115.0"), False), (D("300"), None, None, None, None)]
    assert [x["resultat_change"] for x in st.with_changes([{"resultat": D("10")}, {"resultat": D("4.5")}])] == [None, D("-5.5")]
