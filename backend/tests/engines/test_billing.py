"""Moteurs du lot 12A : cas de référence calculés à la main (aucun prix réel : montants FICTIFS)."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal as D

import pytest

from app.engines.billing import entitlements as ent
from app.engines.billing import lifecycle as lc
from app.engines.billing import pricing as pr

# ------------------------------------------------------------------ prix


def test_quantize_par_devise():
    assert pr.quantize(D("1500.5"), "XOF") == D("1501")        # demi vers le haut
    assert pr.quantize(D("1500.49"), "XAF") == D("1500")
    assert pr.quantize(D("10.005"), "CDF") == D("10.01")
    assert pr.quantize(D("7"), "GNF") == D("7") and pr.quantize(D("7"), "KMF") == D("7")
    with pytest.raises(pr.PricingError):
        pr.quantize(D("1"), "EUR")
    with pytest.raises(pr.PricingError):
        pr.quantize(1.5, "XOF")                                 # jamais de flottant


def test_check_amount_decimales():
    pr.check_amount(D("15000"), "XOF")
    pr.check_amount(D("12.50"), "CDF")
    for bad, cur in ((D("15000.5"), "XOF"), (D("12.505"), "CDF"), (D("-1"), "XAF")):
        with pytest.raises(pr.PricingError):
            pr.check_amount(bad, cur)


def test_devis_sans_remise():
    q = pr.build_quote([pr.Line("p", "Offre", D("25000")), pr.Line("a", "Option", D("5000"), 3)], "XOF", "month")
    assert [x.amount for x in q.lines] == [D("25000"), D("15000")]
    assert (q.subtotal, q.discount, q.credit, q.total) == (D("40000"), D("0"), D("0"), D("40000"))


def test_devis_remise_pourcentage_arrondie():
    # 33 333 × 15 % = 4 999,95 → 5 000 (XOF sans décimale)
    promo = pr.Promotion("PROMO15", "percent", percent=D("15"))
    q = pr.build_quote([pr.Line("p", "Offre", D("33333"))], "XOF", "year", promo)
    assert q.discount == D("5000") and q.total == D("28333") and q.promotion_code == "PROMO15"


def test_devis_remise_portee_et_fixe():
    lines = [pr.Line("p", "Offre", D("10000")), pr.Line("a", "Option", D("3000"))]
    # remise fixe de 4 000 sur l'option seule : plafonnée au montant de la ligne (3 000)
    promo = pr.Promotion("OPT", "fixed", fixed_amount=D("4000"), fixed_currency="XOF", product_ids=frozenset({"a"}))
    q = pr.build_quote(lines, "XOF", "month", promo)
    assert [x.discount for x in q.lines] == [D("0"), D("3000")] and q.total == D("10000")
    with pytest.raises(pr.PricingError):        # remise fixe définie dans une autre devise
        pr.build_quote(lines, "XAF", "month", promo)
    with pytest.raises(pr.PricingError):        # périodicité hors portée
        pr.build_quote(lines, "XOF", "month", pr.Promotion("AN", "percent", percent=D("10"), interval="year"))


def test_prorata_montee_en_gamme():
    # période de 30 jours payée 30 000 ; montée le 11e jour : 20 jours restants → crédit 20 000
    credit = pr.prorata_credit(D("30000"), date(2027, 1, 1), date(2027, 1, 31), date(2027, 1, 11), "XOF")
    assert credit == D("20000")
    # 31 jours, 10 000, 9 jours restants : 10 000 × 9 / 31 = 2 903,22… → 2 903
    assert pr.prorata_credit(D("10000"), date(2027, 3, 1), date(2027, 4, 1), date(2027, 3, 23), "XOF") == D("2903")
    q = pr.build_quote([pr.Line("p2", "Offre supérieure", D("50000"))], "XOF", "month", credit=credit)
    assert q.credit == D("20000") and q.total == D("30000")
    # crédit supérieur au montant : total nul, jamais négatif
    q = pr.build_quote([pr.Line("p2", "x", D("5000"))], "XOF", "month", credit=D("20000"))
    assert q.credit == D("5000") and q.total == D("0")
    assert pr.prorata_credit(D("12.00"), date(2027, 1, 1), date(2027, 1, 31), date(2027, 2, 1), "CDF") == D("0.00")


# ------------------------------------------------------------------ cycle de vie


def test_transitions_autorisees_et_interdites():
    assert lc.transition(None, "start_trial") == "trialing"
    assert lc.transition("trialing", "payment_verified") == "active"
    assert lc.transition("active", "due_unpaid") == "past_due"
    assert lc.transition("past_due", "grace_ended") == "suspended"
    assert lc.transition("suspended", "payment_verified") == "active"
    assert lc.transition("suspended", "admin_cancel") == "canceled"
    for state, event in (("expired", "payment_verified"), ("canceled", "start_trial"), ("trialing", "due_unpaid"),
                         ("active", "trial_expired"), (None, "payment_verified")):
        with pytest.raises(lc.TransitionError):
            lc.transition(state, event)


def test_etat_effectif_et_acces():
    now = datetime(2027, 2, 1, tzinfo=UTC)
    assert lc.effective_state("trialing", now, now - timedelta(seconds=1), None) == "expired"
    assert lc.effective_state("trialing", now, now + timedelta(days=1), None) == "trialing"
    assert lc.effective_state("trialing", now, now + timedelta(days=1), now) == "canceled"
    assert lc.effective_state("suspended", now, None, now - timedelta(days=1)) == "suspended"
    assert lc.access("past_due", False) == "full"
    assert lc.access("suspended", True) == "read_only"
    assert lc.access("expired", True) == "read_only" and lc.access("expired", False) == "none"
    assert lc.access(None, False) == "none"


# ------------------------------------------------------------------ droits

REQUIRES = {"core": (), "financial_audit": ("audit_core",), "audit_core": (), "ai": ()}
QUOTAS = [ent.Grant("quota", k, 5) for k in ent.QUOTA_KEYS]


def test_validation_offre():
    ok = [ent.Grant("module", "core"), *QUOTAS]
    assert ent.validate_plan(ok, REQUIRES, {"core"}) == []
    issues = ent.validate_plan([ent.Grant("module", "financial_audit"), ent.Grant("quota", "users", 3)], REQUIRES, {"core"})
    assert "Module de base absent : core" in issues
    assert any("dépendance absente (audit_core)" in i for i in issues)
    assert any(i.startswith("Quota non défini : companies") for i in issues)
    assert ent.validate_addon([ent.Grant("quota", "users", None)]) == ["Quota users : incrément positif requis"]


def test_agregation_offre_et_options():
    plan = [ent.Grant("module", "core"), ent.Grant("module", "audit_core"),
            *[g if g.key != "companies" else ent.Grant("quota", "companies", None) for g in QUOTAS]]
    addon_users = [ent.Grant("quota", "users", 2), ent.Grant("quota", "companies", 1)]
    addon_fa = [ent.Grant("module", "financial_audit")]
    e = ent.aggregate(plan, [(addon_users, 3), (addon_fa, 1)], "trialing", False, REQUIRES)
    assert e.access == "full"
    assert e.modules == ["audit_core", "core", "financial_audit"]
    assert e.quotas["users"] == 5 + 2 * 3 and e.quotas["companies"] is None      # illimité reste illimité
    # sans le socle d'audit, l'audit financier n'est pas accordé
    e = ent.aggregate([ent.Grant("module", "core"), *QUOTAS], [(addon_fa, 1)], "active", False, REQUIRES)
    assert e.modules == ["core"]
    # aucun abonnement et aucune donnée : aucun accès
    assert ent.aggregate([], [], None, False, REQUIRES) == ent.Entitlements("none")
    assert ent.aggregate(plan, [], "suspended", True, REQUIRES).access == "read_only"
