"""Vérifie un jeu de fichiers de référentiel avec les chargeurs de la plateforme, puis établit les
états financiers et les indicateurs sur une balance de contrôle.

Usage : python verifier.py <dossier du référentiel> <code référentiel> [balance_N.csv [balance_N-1.csv]]
Les balances CSV ont les colonnes : compte;libelle;ouv_debit;ouv_credit;mvt_debit;mvt_credit;solde_debit;solde_credit
"""

import csv
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from app.engines.accounting.frameworks import get_profile  # noqa: E402
from app.engines.accounting.reference_loader import parse_chart, parse_concepts, parse_mappings, parse_structure  # noqa: E402
from app.engines.accounting.statements import LineDef, MappingRule, TBEntry, build_statements  # noqa: E402
from app.engines.financial.calculator import Calculator, Formula, YearContext  # noqa: E402
from app.engines.financial.expressions import parse  # noqa: E402
from app.engines.financial.library import CONCEPTS, CROSS_CHECKS, LIBRARY  # noqa: E402


def rows(path: Path) -> list[list[str]]:
    return list(csv.reader(open(path, encoding="utf-8"), delimiter=";"))


def balance(path: str) -> list[TBEntry]:
    z = lambda v: Decimal(v or 0)  # noqa: E731
    return [TBEntry(r["compte"], r["libelle"], z(r["ouv_debit"]), z(r["ouv_credit"]), z(r["mvt_debit"]),
                    z(r["mvt_credit"]), z(r["solde_debit"]), z(r["solde_credit"]))
            for r in csv.DictReader(open(path, encoding="utf-8"), delimiter=";")]


def report(title, result):
    errs = [i for i in result.issues if i.severity == "error"]
    warns = [i for i in result.issues if i.severity == "warning"]
    print(f"== {title} : {len(result.records)} enregistrements, {len(errs)} erreur(s), {len(warns)} avertissement(s)")
    for i in (errs + warns)[:25]:
        print(f"   [{i.severity}] {i.code} ligne {i.row}: {i.message}")
    return result


def main():
    folder, code = Path(sys.argv[1]), sys.argv[2]
    chart = report("Plan de comptes", parse_chart(rows(folder / "plan_comptes.csv")))
    numbers = {r.account_number for r in chart.records}
    mappings = report("Correspondances", parse_mappings(rows(folder / "correspondances.csv"), numbers))
    structure = report("Structure", parse_structure(rows(folder / "structure.csv")))
    concepts = report("Concepts", parse_concepts(rows(folder / "concepts.csv"), {r.line_code for r in structure.records},
                                                 set(CONCEPTS)))
    issues = get_profile(code).validate(chart.records, mappings.records, structure.records)
    print("== Publication :", "OK" if not any(i.severity == "error" for i in issues) else "REFUSÉE")
    for i in issues:
        print(f"   [{i.severity}] {i.code}: {i.message}")
    if len(sys.argv) < 4:
        return
    defs = [LineDef(r.statement_type, r.line_code, r.label, r.display_order, r.kind, tuple(r.formula), r.role, r.level)
            for r in structure.records]
    rules = [MappingRule(x.statement_type, x.line_code, x.account_prefix, tuple(x.excluded_prefixes), x.balance_rule,
                         x.amount_column, x.sign, x.priority) for x in mappings.records]
    cur = balance(sys.argv[3])
    st = build_statements(cur, defs, rules)
    prev_entries = balance(sys.argv[4]) if len(sys.argv) > 4 else None
    prev = build_statements(prev_entries, defs, rules) if prev_entries else None
    print("\n== Contrôles des états")
    for c in st.controls:
        print(f"   {c.code}: {c.status} — {c.message}")
        if c.status == "failed" and c.code == "UNMAPPED_ACCOUNTS":
            for a in c.details["accounts"][:30]:
                print("      ", a)
    print("\n== États (net N | N-1)")
    pv = prev.values() if prev else {}
    for stype, lines in st.statements.items():
        print(f"-- {stype}")
        for ln in lines:
            n = ln.net if ln.net is not None else Decimal(0)
            p = (pv.get(ln.definition.code, {}).get("net") or Decimal(0)) if prev else ""
            g = f" brut {ln.gross:,.0f} amort {ln.depreciation or 0:,.0f}" if ln.gross is not None else ""
            ps = f"{p:>18,.0f}" if prev else ""
            print(f"   {ln.definition.code:3} {ln.definition.label[:58]:58} {n:>18,.0f} {ps}{g}")
    concepts_ast = {c.concept_code: c.expression_ast for c in concepts.records}
    formulas = [Formula(f.code, f.version, parse(f.expression), f.unit, f.rounding_scale, f.zero_division_policy,
                        f.missing_input_policy) for f in LIBRARY]
    ycur = YearContext("N", date(2025, 1, 1), date(2025, 12, 31), st.values(), cur)
    yprev = YearContext("N-1", date(2024, 1, 1), date(2024, 12, 31), prev.values(), prev_entries) if prev else None
    calc = Calculator(ycur, yprev, concepts_ast, formulas)
    print("\n== Indicateurs")
    for r in calc.run():
        print(f"   {r.code:28} {str(r.value):>20} {r.status} {r.message or ''}")
    print("\n== Contrôles croisés")
    for c in calc.cross_checks(CROSS_CHECKS):
        print(f"   {c.code}: {c.status} — {c.message}")


if __name__ == "__main__":
    main()
