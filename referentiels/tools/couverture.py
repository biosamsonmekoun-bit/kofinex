"""Test de couverture d'un référentiel : balance FICTIVE (données de test, non comptables) où chaque compte
terminal des classes 1 à 8 porte un solde, débiteur ou créditeur selon un tirage déterministe.
Vérifie que chaque compte est rattaché une seule fois, que le bilan s'équilibre et que le résultat du bilan
égale celui du compte de résultat. Usage : python couverture.py <dossier référentiel>"""
import csv, random, sys
from decimal import Decimal
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
from app.engines.accounting.reference_loader import parse_chart, parse_mappings, parse_structure  # noqa: E402
from app.engines.accounting.statements import LineDef, MappingRule, TBEntry, build_statements  # noqa: E402

folder = Path(sys.argv[1])
rows = lambda p: list(csv.reader(open(folder / p, encoding="utf-8"), delimiter=";"))  # noqa: E731
chart = parse_chart(rows("plan_comptes.csv")).records
nums = sorted(r.account_number for r in chart)
leaves = [n for n in nums if n[0] in "12345678" and not any(o != n and o.startswith(n) for o in nums)]
rnd = random.Random(7)
entries, total = [], Decimal(0)
for n in leaves:
    amt = Decimal(rnd.randint(1, 999)) * 1000
    if n[:2] == "13":
        continue                                         # résultat : nul avant affectation (balance avant clôture)
    if n[0] in "45" and n[:2] not in ("49", "59"):
        debit = rnd.random() < 0.5                       # comptes de tiers et de trésorerie : deux sens possibles
    elif n[:2] in ("28", "29", "39", "49", "59"):
        debit = False                                    # amortissements et dépréciations
    elif n[0] == "1":
        debit = n[:3] in ("109", "129", "139")           # déficits, capital non appelé
    else:
        debit = n[0] in "236" or (n[0] == "8" and n[:2] in ("81", "83", "85", "87", "89"))
    total += amt if debit else -amt
    entries.append(TBEntry(n, n, 0, 0, 0, 0, amt if debit else Decimal(0), Decimal(0) if debit else amt))
# équilibrage sur un compte de trésorerie (5211 ou premier compte 52 terminal)
bal = next(n for n in leaves if n.startswith("52"))
e = next(x for x in entries if x.account_number == bal)
entries.remove(e)
net = total - (e.closing_debit - e.closing_credit)
entries.append(TBEntry(bal, bal, 0, 0, 0, 0, max(-net, Decimal(0)), max(net, Decimal(0))))
structure = parse_structure(rows("structure.csv")).records
mappings = parse_mappings(rows("correspondances.csv"), set()).records
defs = [LineDef(r.statement_type, r.line_code, r.label, r.display_order, r.kind, tuple(r.formula), r.role, r.level)
        for r in structure]
rules = [MappingRule(x.statement_type, x.line_code, x.account_prefix, tuple(x.excluded_prefixes), x.balance_rule,
                     x.amount_column, x.sign, x.priority) for x in mappings]
st = build_statements(entries, defs, rules)
cr = [r for r in rules if r.statement_type == "income_statement"]
hors_cr = [e.account_number for e in entries if e.account_number[0] in "678"
           and not any(e.account_number.startswith(r.account_prefix) for r in cr)]
print("Comptes de gestion absents du compte de résultat :", hors_cr or "aucun")
print(f"{len(entries)} comptes terminaux")
for c in st.controls:
    print(c.code, c.status, "—", c.message)
    if c.status == "failed" and "accounts" in (c.details or {}):
        print("   ", [a["account"] for a in c.details["accounts"]])

# diagnostic : compte par compte, contribution actif − passif = solde net (débiteur +)
from collections import defaultdict  # noqa: E402
contrib = defaultdict(Decimal)
cr_contrib = defaultdict(Decimal)
for stt, lines in st.statements.items():
    for ln in lines:
        if ln.definition.kind != "detail":
            continue
        for t in ln.trace:
            a = Decimal(t["amount"])
            if stt == "balance_sheet_assets":
                contrib[t["account"]] += a if t["column"] != "depreciation" else -a
            elif stt == "balance_sheet_liabilities":
                contrib[t["account"]] -= a
            else:
                cr_contrib[t["account"]] += a
ecarts = [(e.account_number, e.closing_net, contrib[e.account_number]) for e in entries
          if e.account_number[0] in "12345" and contrib[e.account_number] != e.closing_net]
print("Comptes de bilan mal repris :", [(a, str(n), str(c)) for a, n, c in ecarts][:40] or "aucun")
res_line = next(r.line_code for r in rules if r.account_prefix == "6" and r.statement_type == "balance_sheet_liabilities")
ch = defaultdict(Decimal)
for t in st.line(res_line).trace:
    ch[t["account"]] += Decimal(t["amount"])
diff = [(a, str(ch[a]), str(cr_contrib[a])) for a in set(ch) | set(cr_contrib) if ch[a] != cr_contrib[a]]
print("Comptes de gestion repris différemment au bilan et au compte de résultat :", diff[:30] or "aucun")
