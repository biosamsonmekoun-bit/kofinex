"""Essai complet sur une balance réelle : import (lecture, détection, contrôles) puis états financiers.
Usage : python essai_balance.py <fichier.xlsx|xlsm> <dossier référentiel> [feuille]"""

import csv
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from app.engines.accounting.reference_loader import parse_chart, parse_mappings, parse_structure  # noqa: E402
from app.engines.accounting.statements import LineDef, MappingRule, TBEntry, build_statements  # noqa: E402
from app.engines.importing import readers  # noqa: E402
from app.engines.importing.balance import ImportOptions, build_balance  # noqa: E402
from app.engines.importing.controls import ChartContext, run_controls  # noqa: E402
from app.engines.importing.detection import detect_header_row, suggest_mapping  # noqa: E402


def rows(p):
    return list(csv.reader(open(p, encoding="utf-8"), delimiter=";"))


path, folder = sys.argv[1], Path(sys.argv[2])
ext = readers.read_xlsx(open(path, "rb").read())
chart = parse_chart(rows(folder / "plan_comptes.csv")).records
ctx = ChartContext("essai", "SYSCOHADA_REV", {r.account_number: r.nature for r in chart})
structure = parse_structure(rows(folder / "structure.csv")).records
mappings = parse_mappings(rows(folder / "correspondances.csv"), set()).records
defs = [LineDef(r.statement_type, r.line_code, r.label, r.display_order, r.kind, tuple(r.formula), r.role, r.level)
        for r in structure]
rules = [MappingRule(x.statement_type, x.line_code, x.account_prefix, tuple(x.excluded_prefixes), x.balance_rule,
                     x.amount_column, x.sign, x.priority) for x in mappings]
for sh in ext.sheets:
    if len(sys.argv) > 3 and sh.name != sys.argv[3]:
        continue
    h = detect_header_row(sh.rows)
    if h is None:
        print("==", sh.name, ": pas d'en-tête détecté")
        continue
    sug = suggest_mapping(sh.rows, h)
    print(f"\n== Feuille « {sh.name} » : en-tête ligne {h + 1} {sug.headers}\n   association : {sug.column_map} {sug.notes}")
    opts = ImportOptions()
    parsed = build_balance(sh.rows, h, sug.column_map, opts)
    rep = run_controls(parsed, opts, chart=ctx)
    print(f"   {len(parsed.valid)} comptes, {len(parsed.errors)} ligne(s) en erreur ; totaux {rep.totals}")
    for r in rep.results:
        if r.status != "passed":
            print(f"   [{r.status}/{r.severity}] {r.code} : {r.message[:200]}")
            if r.code in ("UNKNOWN_ACCOUNTS", "ROW_ERRORS", "DUPLICATE_ACCOUNT", "AGGREGATE_ACCOUNTS", "DECLARED_TOTALS"):
                print("      ", str(r.details)[:400])
    entries = [TBEntry(x.account_number, x.account_label, x.opening_debit or Decimal(0), x.opening_credit or Decimal(0),
                       x.movement_debit or Decimal(0), x.movement_credit or Decimal(0), x.closing_debit or Decimal(0),
                       x.closing_credit or Decimal(0)) for x in parsed.valid]
    st = build_statements(entries, defs, rules)
    for c in st.controls:
        print(f"   ÉTATS {c.code}: {c.status} — {c.message}")
        if c.status == "failed" and c.code == "UNMAPPED_ACCOUNTS":
            print("      ", c.details["accounts"][:20])
    for code in ("AZ", "BK", "BT", "BZ", "CP", "DD", "DP", "DT", "DZ", "XB", "XC", "XD", "XI"):
        ln = st.line(code)
        print(f"      {code} {ln.definition.label[:50]:50} {ln.value():>18,.2f}")
