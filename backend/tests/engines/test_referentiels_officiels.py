"""Fichiers de chargement des référentiels (dossier referentiels/) : publication possible et couverture du plan.

La balance utilisée ici est FICTIVE (montants tirés au hasard, de façon déterministe) : elle sert uniquement à
vérifier que chaque compte du plan est repris une fois et une seule dans les états."""

import csv
import random
from decimal import Decimal
from pathlib import Path

import pytest

from app.engines.accounting.frameworks import get_profile
from app.engines.accounting.reference_loader import parse_chart, parse_concepts, parse_mappings, parse_structure
from app.engines.financial.library import CONCEPTS as LIBRARY_CONCEPTS
from app.engines.accounting.statements import LineDef, MappingRule, TBEntry, build_statements

ROOT = Path(__file__).resolve().parents[3] / "referentiels"

# comptes que la grille officielle ne rattache à aucun poste (listés dans RAPPORT.md, « points à valider »)
HORS_GRILLE = {
    "syscohada_revise": {"186", "187", "188", "2394", "2395", "2398", "585", "588"},
    "syscebnl": {"702", "7054", "7055", "585", "588"},
}
CONCEPT_NAMES = set(LIBRARY_CONCEPTS)
CODES = {"syscohada_revise": "SYSCOHADA_REV", "syscebnl": "SYSCEBNL"}


def _rows(folder, name):
    return list(csv.reader(open(folder / name, encoding="utf-8"), delimiter=";"))


def _load(folder):
    chart = parse_chart(_rows(folder, "plan_comptes.csv"))
    maps = parse_mappings(_rows(folder, "correspondances.csv"), set())
    struct = parse_structure(_rows(folder, "structure.csv"))
    concepts = parse_concepts(_rows(folder, "concepts.csv"), {r.line_code for r in struct.records}, CONCEPT_NAMES)
    return chart, maps, struct, concepts


@pytest.mark.parametrize("name", sorted(CODES))
def test_publication_possible(name):
    chart, maps, struct, concepts = _load(ROOT / name)
    for r in (chart, maps, struct, concepts):
        assert not [i for i in r.issues if i.severity == "error"]
    issues = get_profile(CODES[name]).validate(chart.records, maps.records, struct.records)
    assert not [i for i in issues if i.severity == "error"]


def _natural_debit(n, rnd):
    if n[0] in "45" and n[:2] not in ("49", "59"):
        return rnd.random() < 0.5
    if n[:2] in ("28", "29", "39", "49", "59"):
        return False
    if n[0] == "1":
        return n[:3] in ("109", "129", "139")
    return n[0] in "236" or n[:2] in ("81", "83", "85", "87", "89")


@pytest.mark.parametrize("name", sorted(CODES))
def test_couverture_du_plan(name):
    chart, maps, struct, _ = _load(ROOT / name)
    nums = sorted(r.account_number for r in chart.records)
    leaves = [n for n in nums if n[0] in "12345678" and n[:2] != "13" and n not in HORS_GRILLE[name]
              and not any(o != n and o.startswith(n) for o in nums)
              and not any(n.startswith(h) for h in HORS_GRILLE[name])]
    rnd = random.Random(11)
    entries, total = [], Decimal(0)
    for n in leaves:
        amt, debit = Decimal(rnd.randint(1, 999) * 1000), _natural_debit(n, rnd)
        total += amt if debit else -amt
        entries.append(TBEntry(n, n, 0, 0, 0, 0, amt if debit else Decimal(0), Decimal(0) if debit else amt))
    entries.append(TBEntry("5299999", "équilibrage", 0, 0, 0, 0, max(-total, Decimal(0)), max(total, Decimal(0))))
    defs = [LineDef(r.statement_type, r.line_code, r.label, r.display_order, r.kind, tuple(r.formula), r.role, r.level)
            for r in struct.records]
    rules = [MappingRule(x.statement_type, x.line_code, x.account_prefix, tuple(x.excluded_prefixes), x.balance_rule,
                         x.amount_column, x.sign, x.priority) for x in maps.records]
    st = build_statements(entries, defs, rules)
    status = {c.code: c.status for c in st.controls}
    assert status == {"BALANCE_SHEET_EQUILIBRIUM": "passed", "NET_INCOME_CONSISTENCY": "passed",
                      "UNMAPPED_ACCOUNTS": "passed"}, [c.message for c in st.controls]
