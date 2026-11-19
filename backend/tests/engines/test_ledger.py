"""Grand livre : détection des colonnes, lecture, contrôles, rapprochement avec la balance (données FICTIVES)."""

from datetime import date
from decimal import Decimal as D

import pytest

from app.engines.importing import ledger as lg
from app.engines.importing.controls import ChartContext

FEC = [["JournalCode", "JournalLib", "EcritureNum", "EcritureDate", "CompteNum", "CompteLib", "CompAuxNum", "CompAuxLib",
        "PieceRef", "PieceDate", "EcritureLib", "Debit", "Credit", "EcritureLet", "DateLet", "ValidDate", "Montantdevise", "Idevise"],
       ["AN", "A nouveaux", "1", "20250101", "411000", "Clients", "", "", "AN1", "20250101", "Report", "1000,00", "0,00", "", "", "", "", ""],
       ["AN", "A nouveaux", "1", "20250101", "101000", "Capital", "", "", "AN1", "20250101", "Report", "0,00", "1000,00", "", "", "", "", ""],
       ["VT", "Ventes", "2", "20250315", "411000", "Clients", "C001", "Alpha", "F12", "20250315", "Facture F12", "1200,00", "0,00", "A", "", "", "", ""],
       ["VT", "Ventes", "2", "20250315", "701000", "Ventes", "", "", "F12", "20250315", "Facture F12", "0,00", "1200,00", "", "", "", "", ""],
       ["BQ", "Banque", "3", "20250405", "521000", "Banque", "", "", "R5", "20250405", "Règlement F12", "1200,00", "0,00", "", "", "", "", ""],
       ["BQ", "Banque", "3", "20250405", "411000", "Clients", "C001", "Alpha", "R5", "20250405", "Règlement F12", "0,00", "1200,00", "A", "", "", "", ""]]


def test_fec_headers_are_recognised():
    assert lg.detect_header_row(FEC) == 0
    cm, headers, fmt = lg.suggest_mapping(FEC, 0)
    assert fmt == "fec" and cm["entry_number"] == 2 and cm["debit"] == 11 and cm["auxiliary_account"] == 6


def test_generic_headers_mapping():
    rows = [["Société test"], [], ["Journal", "Date", "N° pièce", "Compte", "Libellé du compte", "Libellé", "Débit", "Crédit"]]
    assert lg.detect_header_row(rows) == 2
    cm, _, fmt = lg.suggest_mapping(rows, 2)
    assert fmt == "generic"
    assert cm == {"journal_code": 0, "entry_date": 1, "document_ref": 2, "account_number": 3, "account_label": 4,
                  "label": 5, "debit": 6, "credit": 7}


def _parse(rows=FEC, **opts):
    cm, _, _ = lg.suggest_mapping(rows, 0)
    return lg.build_ledger(rows, 0, cm, lg.LedgerOptions(decimal_separator=",", **opts))


def test_build_and_controls_pass():
    p = _parse(opening_journals=["AN"])
    assert len(p.valid) == 6 and p.entry_key_basis == "entry_number"
    assert p.valid[2].entry_date == date(2025, 3, 15) and p.valid[2].debit == D("1200.00") and p.valid[2].lettering == "A"
    tb = [lg.TBRow("411000", D("1000"), D("1200"), D("1200"), D("1000")), lg.TBRow("101000", D("-1000"), D(0), D(0), D("-1000")),
          lg.TBRow("701000", D(0), D(0), D("1200"), D("-1200")), lg.TBRow("521000", D(0), D("1200"), D(0), D("1200"))]
    chart = ChartContext("v-test", "TEST", {"101": "equity", "411": "asset", "521": "asset", "701": "income"})
    rep = lg.run_controls(p, date(2025, 1, 1), date(2025, 12, 31), lg.LedgerOptions(opening_journals=["AN"]), chart=chart, balance=tb)
    status = {r.code: r.status for r in rep.results}
    assert status == {"LINES_READABLE": "passed", "DATES_IN_YEAR": "passed", "LEDGER_BALANCED": "passed",
                      "ENTRIES_BALANCED": "passed", "ACCOUNTS_IN_CHART": "passed", "TB_RECONCILIATION": "passed"}
    assert not rep.blocking and not rep.requires_acknowledgment


def test_blocking_and_warning_controls():
    rows = [r[:] for r in FEC]
    rows[4][12] = "1100,00"                        # écriture 2 déséquilibrée → grand livre aussi
    rows[5][3] = "20260105"                        # hors exercice
    rows.append(["OD", "", "4", "31/12/2025", "6X1", "", "", "", "", "", "", "abc", "0", "", "", "", "", ""])
    p = _parse(rows)
    tb = [lg.TBRow("411000", D(0), D("2200"), D("1200"), D("1000"))]
    rep = lg.run_controls(p, date(2025, 1, 1), date(2025, 12, 31), lg.LedgerOptions(), chart=None, balance=tb)
    r = {x.code: x for x in rep.results}
    assert r["LINES_READABLE"].status == "failed" and r["LINES_READABLE"].details["rows"][0]["row"] == 8
    assert r["DATES_IN_YEAR"].status == "failed" and r["LEDGER_BALANCED"].status == "failed"
    assert r["ENTRIES_BALANCED"].details["entries"][0]["difference"] == "100.00"
    assert r["TB_RECONCILIATION"].status == "failed" and r["TB_RECONCILIATION"].severity == "warning"
    assert rep.blocking


def test_single_amount_column_conventions():
    rows = [["Date", "Compte", "Montant", "Sens"], ["01/02/2025", "601000", "250", "D"], ["01/02/2025", "401000", "250", "Crédit"]]
    cm = {"entry_date": 0, "account_number": 1, "amount": 2, "direction": 3}
    p = lg.build_ledger(rows, 0, cm, lg.LedgerOptions())
    assert [(x.debit, x.credit) for x in p.valid] == [(D("250.00"), D(0)), (D(0), D("250.00"))]
    signed = [["Date", "Compte", "Montant"], ["01/02/2025", "601000", "-80"]]
    with pytest.raises(lg.LedgerMappingError):
        lg.build_ledger(signed, 0, {"entry_date": 0, "account_number": 1, "amount": 2}, lg.LedgerOptions())
    p2 = lg.build_ledger(signed, 0, {"entry_date": 0, "account_number": 1, "amount": 2}, lg.LedgerOptions(amount_sign="credit_positive"))
    assert (p2.valid[0].debit, p2.valid[0].credit) == (D("80.00"), D(0))
    with pytest.raises(lg.LedgerMappingError):
        lg.validate_column_map({"entry_date": 0, "account_number": 1, "debit": 2}, lg.LedgerOptions())


def test_analytics_helpers():
    assert lg.numbering_gaps(["1", "2", "5", "x", "6", "9"]) == [(3, 4), (7, 8)]
    exp = lg.benford_expected()
    assert exp[1] == D("30.10") and exp[9] == D("4.58")
    assert lg.first_digit(D("0.045")) == 4 and lg.first_digit(D("1200.00")) == 1 and lg.first_digit(D("0")) is None
    assert lg.is_weekend(date(2025, 3, 15)) and lg.weekday_label(date(2025, 3, 15)) == "samedi"
    assert lg.fiscal_period(date(2025, 7, 1), date(2026, 2, 10)) == 8
