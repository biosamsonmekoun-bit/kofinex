"""Classification des comptes par le référentiel SYSCOHADA révisé réellement fourni (dossier `referentiels/`) :
AO, HAO, autres (participation, impôt), chiffre d'affaires, personnel, trésorerie, clients, fournisseurs.
Vérifie que rien n'est codé en dur : tout vient de la structure, des concepts et des correspondances du référentiel."""

import csv
from decimal import Decimal as D
from pathlib import Path

import pytest

from app.engines.accounting import reference_loader as rl
from app.engines.accounting.statements import LineDef, MappingRule
from app.engines.financial.library import CONCEPTS
from app.engines.management import steering as st

REF = Path(__file__).resolve().parents[3] / "referentiels" / "syscohada_revise"


def _rows(name):
    with open(REF / name, encoding="utf-8") as f:
        return [r for r in csv.reader(f, delimiter=";")]


@pytest.fixture(scope="module")
def ref():
    if not (REF / "structure.csv").exists():
        pytest.skip("Référentiel SYSCOHADA absent")
    chart = rl.parse_chart(_rows("plan_comptes.csv")).records
    structure = rl.parse_structure(_rows("structure.csv")).records
    mappings = rl.parse_mappings(_rows("correspondances.csv"), {c.account_number for c in chart}).records
    concepts = rl.parse_concepts(_rows("concepts.csv"), {s.line_code for s in structure}, set(CONCEPTS)).records
    return ({c.account_number: (c.label, c.nature) for c in chart},
            [LineDef(s.statement_type, s.line_code, s.label, s.display_order, s.kind, tuple(s.formula), s.role, s.level) for s in structure],
            [MappingRule(m.statement_type, m.line_code, m.account_prefix, tuple(m.excluded_prefixes), m.balance_rule, m.amount_column,
                         m.sign, m.priority) for m in mappings],
            {c.concept_code: c.expression_ast for c in concepts})


def test_classification_syscohada(ref):
    chart, structure, rules, concepts = ref
    accs = {"601100", "605100", "661100", "681100", "671100", "701100", "706100", "758100", "821000", "831000", "841000",
            "891000", "871000", "521100", "571100", "411100", "401100", "101300", "476000"}
    cls, reserves = st.classify(accs, chart, structure, rules, concepts)
    g = {a: cls[a].group for a in accs}
    assert {g[a] for a in ("601100", "605100", "661100", "681100", "671100", "701100", "706100", "758100")} == {"AO"}
    assert {g[a] for a in ("821000", "831000", "841000")} == {"HAO"}
    assert g["891000"] == "OTHER" and g["871000"] == "OTHER"          # impôt sur le résultat, participation
    assert g["101300"] is None and g["521100"] is None
    assert cls["701100"].revenue and cls["706100"].revenue and not cls["758100"].revenue
    assert cls["661100"].personnel and not cls["601100"].personnel
    assert cls["521100"].treasury and cls["571100"].treasury and not cls["411100"].treasury
    assert cls["411100"].partner == "customer" and cls["401100"].partner == "supplier"
    assert cls["601100"].nature == "expense" and cls["701100"].nature == "income"
    assert cls["476000"].revenue is False                               # produits constatés d'avance : pas du CA
    missing = [r for r in reserves if "non rattaché" in r]
    assert not [r for r in missing if any(k in r for k in ("activites_ordinaires", "resultat_hao", "chiffre_affaires"))]


def test_marge_ao_egale_rao_des_etats(ref):

    from app.engines.accounting.statements import TBEntry, build_statements

    chart, structure, rules, concepts = ref
    net = {"601100": D("400"), "661100": D("300"), "701100": D("-1500"), "821000": D("-200"), "831000": D("50"), "891000": D("100")}
    cls, _ = st.classify(set(net), chart, structure, rules, concepts)
    s = st.pl(net, cls)
    tb = [TBEntry(a, None, D(0), D(0), max(v, D(0)), max(-v, D(0)), max(v, D(0)), max(-v, D(0))) for a, v in net.items()]
    lines = build_statements(tb, structure, rules).values()
    assert s.marge_ao == D("800") and s.marge_hao == D("150") and s.resultat == D("850")
    assert lines["XG"]["net"] == s.marge_ao and lines["XH"]["net"] == s.marge_hao and lines["XI"]["net"] == s.resultat
