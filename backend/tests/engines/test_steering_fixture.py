"""Pré-validation, par les moteurs, du scénario de `tests/integration/test_steering_api.py::test_steering_views`, avec le
référentiel FICTIF des tests d'intégration (plan `CHART_CSV`, structure, correspondances, concepts). Ce test s'exécute
sans base ni API : il vérifie les valeurs attendues par le test d'intégration. Données FICTIVES."""

import csv
import io
from datetime import date
from decimal import Decimal as D

from app.engines.accounting import reference_loader as rl
from app.engines.management import steering as st
from tests.engines import fictitious_framework as ff
from tests.integration.test_imports_api import CHART_CSV


def _framework():
    chart = rl.parse_chart(list(csv.reader(io.StringIO(CHART_CSV.decode()), delimiter=";"))).records
    st_, rules, concepts, _s, _c = ff.load()
    return {c.account_number: (c.label, c.nature) for c in chart}, st_, rules, concepts


Y = 2860
FY = (date(Y, 1, 1), date(Y, 12, 31))


def M(acc, d, dv="0", cv="0", key="e", tp=None):  # noqa: N802
    return st.Movement(acc, d, D(dv), D(cv), key, third_party=tp, third_party_label=tp)


MOVS = [
    M("411", date(Y, 1, 10), "1200", key="vt1", tp="C1"), M("701", date(Y, 1, 10), cv="1200", key="vt1"),
    M("601", date(Y, 2, 5), "500", key="ac1"), M("401", date(Y, 2, 5), cv="500", key="ac1", tp="F1"),
    M("521", date(Y, 3, 3), "1000", key="bq1"), M("411", date(Y, 3, 3), cv="1000", key="bq1", tp="C1"),
    M("401", date(Y, 3, 20), "500", key="bq2", tp="F1"), M("521", date(Y, 3, 20), cv="500", key="bq2"),
]


def test_scenario_du_test_d_integration():
    chart, structure, rules, concepts = _framework()
    cls, reserves = st.classify({m.account for m in MOVS}, chart, structure, rules, concepts)
    assert cls["701"].revenue and cls["411"].partner == "customer" and cls["401"].partner == "supplier" and cls["521"].treasury
    assert any("resultat_activites_ordinaires" in r for r in reserves)       # référentiel fictif : AO / HAO non rattachés
    year = st.pl(st.nets(MOVS, FY), cls)
    assert (year.total_charges, year.total_produits, year.chiffre_affaires) == (D("500"), D("1200"), D("1200"))
    feb = st.pl(st.nets(MOVS, st.period_range(*FY, "month", 2)), cls)
    assert (feb.total_charges, feb.total_produits) == (D("500"), D("0"))
    cum2 = st.pl(st.nets(MOVS, st.period_range(*FY, "cumulative", 2)), cls)
    assert (cum2.total_charges, cum2.total_produits) == (D("500"), D("1200"))
    part = st.pl(st.nets(MOVS, st.period_range(*FY, "custom", custom=(date(Y, 1, 1), date(Y, 1, 15)))), cls)
    assert part.total_produits == D("1200") and part.total_charges == D("0")
    c = st.top_partners(MOVS, cls, FY, "customer")
    assert [(i["key"], i["amount"]) for i in c["items"]] == [("C1", D("1200"))]
    assert [(i["key"], i["amount"]) for i in st.top_partners(MOVS, cls, FY, "customer", basis="invoiced")["items"]] == [("C1", D("1200"))]
    assert [(i["key"], i["amount"]) for i in st.top_partners(MOVS, cls, FY, "supplier", basis="invoiced")["items"]] == [("F1", D("500"))]
    t = st.treasury(MOVS, cls, FY)
    assert (t["opening"], t["receipts"], t["payments"], t["closing"], t["check"]) == (D("0"), D("1000"), D("500"), D("500"), True)
    assert st.payroll(st.nets(MOVS, FY), cls, D("1200"))["total"] == D("0")
