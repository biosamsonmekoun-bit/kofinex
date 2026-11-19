"""Comptabilité native : montants, équilibre, extourne, lettrage, grand livre (soldes progressifs), balances
(générale, auxiliaire, avant / après inventaire, comparative). Cas calculés à la main. Données FICTIVES."""

from datetime import date
from decimal import Decimal as D

import pytest

from app.engines.accounting import entries as en
from app.engines.accounting import native_ledger as nl


# ----------------------------------------------------------------- montants
def test_montants_decimaux_stricts():
    assert en.money("1 200,50") == D("1200.50") and en.money(None) == D("0.00") and en.money(12) == D("12.00")
    for bad in (1.1, "-5", "1.005", "abc", "NaN"):
        with pytest.raises(en.AmountError):
            en.money(bad)


# ----------------------------------------------------------------- équilibre et contrôles
ACC = {
    "411100": en.AccountInfo(requires_third_party=True, third_party_kind="customer"),
    "701100": en.AccountInfo(),
    "601100": en.AccountInfo(active=False),
}


def test_ecriture_equilibree():
    c = en.check_entry(
        [en.Line("411100", D("1200"), third_party="C1"), en.Line("701100", credit=D("1200"))], ACC, {"C1": "customer"}
    )
    assert c.ok and c.balanced and c.difference == 0


def test_ecriture_desequilibree_et_anomalies():
    c = en.check_entry(
        [
            en.Line("411100", D("1200")),
            en.Line("701100", credit=D("1100")),
            en.Line("601100", D("5"), D("5")),
            en.Line("999", D("1")),
        ],
        ACC,
        {},
    )
    assert not c.balanced and c.difference == D("101")
    joined = " ".join(c.issues)
    for part in ("tiers obligatoire", "pas les deux", "désactivé", "non ouvert", "déséquilibrée"):
        assert part in joined


def test_tiers_de_type_incompatible_et_ligne_unique():
    c = en.check_entry([en.Line("411100", D("10"), third_party="F1"), en.Line("701100", credit=D("10"))], ACC, {"F1": "supplier"})
    assert any("type incompatible" in i for i in c.issues)
    assert any("deux lignes" in i for i in en.check_entry([en.Line("701100", credit=D("1"))]).issues)


# ----------------------------------------------------------------- extourne et lettrage
def test_extourne_inverse_chaque_ligne():
    lines = [
        en.Line("411100", D("1200"), third_party="C1"),
        en.Line("701100", credit=D("1000")),
        en.Line("443100", credit=D("200")),
    ]
    rev = en.reversal_lines(lines)
    assert [(r.account, r.debit, r.credit, r.third_party) for r in rev] == [
        ("411100", D("0.00"), D("1200"), "C1"),
        ("701100", D("1000"), D("0.00"), None),
        ("443100", D("200"), D("0.00"), None),
    ]
    assert en.check_entry(rev).balanced


def test_codes_et_controle_du_lettrage():
    assert [en.lettering_code(n) for n in (1, 2, 26, 27, 28, 52, 53, 702, 703)] == [
        "A",
        "B",
        "Z",
        "AA",
        "AB",
        "AZ",
        "BA",
        "ZZ",
        "AAA",
    ]
    ok = en.lettering_check(
        [
            en.Line("411100", D("1200"), third_party="C1"),
            en.Line("411100", credit=D("700"), third_party="C1"),
            en.Line("411100", credit=D("500"), third_party="C1"),
        ]
    )
    assert ok.ok
    ko = en.lettering_check(
        [en.Line("411100", D("1200"), third_party="C1"), en.Line("411100", credit=D("1000"), third_party="C2")]
    )
    assert len(ko.issues) == 2


# ----------------------------------------------------------------- grand livre et balances
def P(acc, d, dv="0", cv="0", origin="manual", tp=None, j="VT", seq=1, n=1):  # noqa: N802
    return nl.Posted(acc, d, D(dv), D(cv), origin=origin, third_party=tp, journal=j, sequence=seq, line_no=n)


LINES = [
    P("521100", date(2025, 1, 1), "500", origin="opening", j="AN"),
    P("101000", date(2025, 1, 1), cv="500", origin="opening", j="AN", n=2),
    P("411100", date(2025, 3, 15), "1200", tp="C1"),
    P("701100", date(2025, 3, 15), cv="1200", n=2),
    P("521100", date(2025, 4, 5), "1200", j="BQ"),
    P("411100", date(2025, 4, 5), cv="1200", tp="C1", j="BQ", n=2),
    P("411100", date(2025, 5, 2), "300", tp="C2", seq=2),
    P("701100", date(2025, 5, 2), cv="300", seq=2, n=2),
    P("681100", date(2025, 12, 31), "100", origin="inventory", j="OD"),
    P("281100", date(2025, 12, 31), cv="100", origin="inventory", j="OD", n=2),
]


def test_grand_livre_solde_progressif():
    gl = {a["account"]: a for a in nl.ledger(LINES)}
    bank = gl["521100"]
    assert bank["opening"] == D("500") and [r["balance"] for r in bank["rows"]] == [D("1700")] and bank["closing"] == D("1700")
    cust = gl["411100"]
    assert [r["balance"] for r in cust["rows"]] == [D("1200"), D("0"), D("300")] and cust["debit"] == D("1500")


def test_grand_livre_periode_et_ouverture():
    gl = {a["account"]: a for a in nl.ledger(LINES, date(2025, 4, 1), date(2025, 4, 30))}
    assert gl["411100"]["opening"] == D("1200") and gl["411100"]["closing"] == D("0")
    assert "701100" in gl and gl["701100"]["rows"] == [] and gl["701100"]["opening"] == D("-1200")


def test_balance_generale_equilibree():
    b = nl.trial_balance(LINES)
    assert b["balanced"]
    t = b["totals"]
    assert (t["opening_debit"], t["opening_credit"]) == (D("500"), D("500"))
    assert (t["debit"], t["credit"]) == (D("2800"), D("2800"))
    row = {r["account"]: r for r in b["rows"]}
    assert (row["411100"]["closing_debit"], row["701100"]["closing_credit"]) == (D("300"), D("1500"))


def test_balance_avant_et_apres_inventaire():
    avant = {r["account"] for r in nl.trial_balance(nl.filter_scope(LINES, "before_inventory"))["rows"]}
    apres = {r["account"] for r in nl.trial_balance(nl.filter_scope(LINES, "after_inventory"))["rows"]}
    assert "681100" not in avant and {"681100", "281100"} <= apres


def test_balance_auxiliaire_par_tiers():
    b = nl.trial_balance([p for p in LINES if p.account == "411100"], by_third_party=True)
    assert [(r["third_party"], r["closing_debit"]) for r in b["rows"]] == [("C1", D("0")), ("C2", D("300"))]


def test_balance_comparative():
    cur = nl.trial_balance(LINES)["rows"]
    prev = nl.trial_balance([P("521100", date(2024, 6, 1), "500", j="BQ"), P("101000", date(2024, 6, 1), cv="500", n=2)])["rows"]
    comp = {r["account"]: r for r in nl.comparative(cur, prev)}
    assert (
        comp["521100"]["current"] == D("1700")
        and comp["521100"]["previous"] == D("500")
        and comp["521100"]["change"] == D("1200")
    )
    assert comp["701100"]["previous"] == D("0")


def test_balance_reproductible():
    assert nl.trial_balance(list(reversed(LINES))) == nl.trial_balance(LINES)
