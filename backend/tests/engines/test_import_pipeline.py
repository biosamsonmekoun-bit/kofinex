"""De bout en bout : fichier -> lecture -> détection -> balance -> contrôles."""

from decimal import Decimal as D

import pytest

from app.engines.importing import readers
from app.engines.importing.balance import ImportOptions, build_balance
from app.engines.importing.controls import run_controls
from app.engines.importing.detection import detect_header_row, suggest_mapping
from app.engines.importing.files import FileRejected, validate_upload
from tests.engines import sample_files as sf

SIX = {"opening_debit", "opening_credit", "movement_debit", "movement_credit", "closing_debit", "closing_credit"}


def _status(report, code):
    return next(r for r in report.results if r.code == code).status


def _pipeline(sheet, options=None, column_map=None):
    header = detect_header_row(sheet.rows)
    assert header is not None
    mapping = column_map or suggest_mapping(sheet.rows, header).column_map
    parsed = build_balance(sheet.rows, header, mapping, options or ImportOptions(),
                           confidence=sheet.confidence, row_pages=sheet.row_pages)
    return header, mapping, parsed, run_controls(parsed, options or ImportOptions())


# ------------------------------------------------------------------------- validation des fichiers
def test_validate_upload():
    v = validate_upload("balance.xlsx", sf.xlsx_two_level_header(), max_bytes=10_000_000,
                        allowed_extensions=["xlsx", "csv", "pdf"])
    assert v.format == "xlsx" and len(v.sha256) == 64
    with pytest.raises(FileRejected, match="Format non accepté"):
        validate_upload("x.exe", b"MZ", max_bytes=100, allowed_extensions=["xlsx"])
    with pytest.raises(FileRejected, match="pas un classeur"):
        validate_upload("faux.xlsx", b"%PDF-1.4 ...", max_bytes=100, allowed_extensions=["xlsx"])
    with pytest.raises(FileRejected, match="pas un PDF"):
        validate_upload("faux.pdf", b"PK\x03\x04", max_bytes=100, allowed_extensions=["pdf"])
    with pytest.raises(FileRejected, match="volumineux"):
        validate_upload("a.csv", b"x" * 200, max_bytes=100, allowed_extensions=["csv"])
    with pytest.raises(FileRejected, match="binaires"):
        validate_upload("a.csv", b"a;b\x00c", max_bytes=100, allowed_extensions=["csv"])


# ------------------------------------------------------------------------- Excel
def test_xlsx_two_level_header_full_pipeline():
    ext = readers.extract("xlsx", sf.xlsx_two_level_header())
    assert [s.name for s in ext.sheets] == ["Balance 2025", "Notes"]
    header, mapping, parsed, report = _pipeline(ext.sheets[0])
    assert header == 3
    assert set(mapping) == SIX | {"account_number", "account_label"}
    assert mapping["opening_debit"] == 2 and mapping["closing_credit"] == 7
    assert len(parsed.valid) == 6 and not parsed.errors
    supplier = next(x for x in parsed.valid if x.account_number == "401100")
    assert supplier.closing_credit == D("1300000.50") and supplier.movement_credit == D("1800000.50")
    assert report.totals["closing"] == {"debit": "17800000.50", "credit": "17800000.50", "difference": "0.00"}
    for code in ("OPENING_BALANCED", "MOVEMENT_BALANCED", "CLOSING_BALANCED", "ROW_ARITHMETIC",
                 "DECLARED_TOTALS", "DUPLICATE_ACCOUNT", "AGGREGATE_ACCOUNTS"):
        assert _status(report, code) == "passed", code
    assert not report.blocking
    # ligne de titre « Classe 1 - … » ignorée, total général reconnu
    assert {x.status for x in parsed.lines} == {"valid", "skipped", "total"}


def test_unbalanced_and_wrong_total_are_blocking():
    ext = readers.extract("xlsx", sf.xlsx_two_level_header())
    rows = [list(r) for r in ext.sheets[0].rows]
    bank = next(r for r in rows if r and r[0] == 521100)
    bank[7] = 1000.0   # crédit de clôture parasite
    _, _, parsed, report = _pipeline(readers.Sheet("x", rows, "xlsx"))
    assert _status(report, "CLOSING_BALANCED") == "failed"
    assert _status(report, "ROW_ARITHMETIC") == "failed"
    assert _status(report, "DECLARED_TOTALS") == "failed"
    assert _status(report, "CLOSING_BOTH_SIDES") == "failed"
    assert report.blocking


def test_duplicate_and_aggregate_accounts():
    ext = readers.extract("xlsx", sf.xlsx_two_level_header(with_totals=False))
    rows = [list(r) for r in ext.sheets[0].rows]
    clients = next(r for r in rows if r and r[0] == 411100)
    # compte de regroupement « 411 » = total de son unique sous-compte
    rows.append([411, "Clients (regroupement)", *clients[2:]])
    _, mapping, parsed, report = _pipeline(readers.Sheet("x", rows, "xlsx"))
    assert _status(report, "AGGREGATE_ACCOUNTS") == "failed" and report.blocking

    opts = ImportOptions(exclude_aggregate_accounts=True)
    parsed = build_balance(rows, 3, mapping, opts)
    report = run_controls(parsed, opts)
    assert _status(report, "AGGREGATE_ACCOUNTS") == "passed"
    assert _status(report, "CLOSING_BALANCED") == "passed"

    rows.pop()
    rows.append(list(clients))
    parsed = build_balance(rows, 3, mapping, ImportOptions())
    assert _status(run_controls(parsed, ImportOptions()), "DUPLICATE_ACCOUNT") == "failed"


def test_signed_balance_and_computed_closing():
    rows = [["Compte", "Libellé", "Solde"], ["521100", "Banque", "1 000,00"], ["401100", "Fournisseur", "-1 000,00"]]
    parsed = build_balance(rows, 0, {"account_number": 0, "account_label": 1, "closing_balance": 2}, ImportOptions())
    bank, sup = parsed.valid
    assert (bank.closing_debit, bank.closing_credit) == (D("1000.00"), D("0.00"))
    assert (sup.closing_debit, sup.closing_credit) == (D("0.00"), D("1000.00"))
    inverted = build_balance(rows, 0, {"account_number": 0, "closing_balance": 2},
                             ImportOptions(signed_balance_convention="credit_positive"))
    assert inverted.valid[0].closing_credit == D("1000.00")

    rows = [["Compte", "AN Débit", "AN Crédit", "Mvt Débit", "Mvt Crédit"], ["411100", "100", "", "50", "30"]]
    parsed = build_balance(rows, 0, {"account_number": 0, "opening_debit": 1, "opening_credit": 2,
                                     "movement_debit": 3, "movement_credit": 4}, ImportOptions())
    line = parsed.valid[0]
    assert line.closing_debit == D("120.00") and line.closing_computed


def test_negative_amounts():
    rows = [["Compte", "Débit", "Crédit"], ["411100", "-50", ""], ["401100", "", "50"]]
    m = {"account_number": 0, "closing_debit": 1, "closing_credit": 2}
    assert build_balance(rows, 0, m, ImportOptions()).errors[0].issues[0].code == "NEGATIVE_AMOUNT"
    moved = build_balance(rows, 0, m, ImportOptions(negative_amounts="move_to_other_side"))
    assert moved.valid[0].closing_credit == D("50.00")


def test_amounts_without_account_are_errors():
    rows = [["Compte", "Débit", "Crédit"], ["", "500", ""], ["Titre de section", None, None]]
    parsed = build_balance(rows, 0, {"account_number": 0, "closing_debit": 1, "closing_credit": 2}, ImportOptions())
    assert [x.status for x in parsed.lines] == ["error", "skipped"]


def test_tolerance_turns_small_gap_into_warning():
    rows = [["Compte", "Débit", "Crédit"], ["411100", "100,00", ""], ["701100", "", "99,99"]]
    m = {"account_number": 0, "closing_debit": 1, "closing_credit": 2}
    strict = run_controls(build_balance(rows, 0, m, ImportOptions()), ImportOptions())
    assert strict.blocking
    opts = ImportOptions(balance_tolerance=D("0.05"))
    tolerant = run_controls(build_balance(rows, 0, m, opts), opts)
    assert not tolerant.blocking and tolerant.requires_acknowledgment


def test_mapping_validation():
    from app.engines.importing.balance import MappingError
    with pytest.raises(MappingError, match="numéro de compte"):
        build_balance([["a"]], 0, {"closing_debit": 1, "closing_credit": 2}, ImportOptions())
    with pytest.raises(MappingError, match="débit ET crédit"):
        build_balance([["a"]], 0, {"account_number": 0, "closing_debit": 1}, ImportOptions())
    with pytest.raises(MappingError, match="plusieurs champs"):
        build_balance([["a"]], 0, {"account_number": 0, "closing_debit": 0, "closing_credit": 1}, ImportOptions())


# ------------------------------------------------------------------------- CSV
def test_csv_french_cp1252():
    ext = readers.extract("csv", sf.csv_french_cp1252())
    sheet = ext.sheets[0]
    assert sheet.rows[0][1] == "Libellé"           # accents décodés depuis Windows-1252
    header, mapping, parsed, report = _pipeline(sheet)
    assert mapping == {"account_number": 0, "account_label": 1, "closing_debit": 2, "closing_credit": 3}
    assert parsed.decimal_separator == ","
    assert _status(report, "CLOSING_BALANCED") == "passed"
    assert _status(report, "DECLARED_TOTALS") == "passed"
    assert _status(report, "OPENING_BALANCED") == "skipped"


# ------------------------------------------------------------------------- PDF
def test_pdf_text():
    ext = readers.extract("pdf", sf.pdf_text())
    assert ext.method == "pdf_text" and ext.page_count == 1
    _, mapping, parsed, report = _pipeline(ext.sheets[0])
    assert {"movement_debit", "movement_credit", "closing_debit", "closing_credit"} <= set(mapping)
    assert len(parsed.valid) == 6, [(x.source_row, x.raw, x.issues) for x in parsed.lines]
    assert _status(report, "CLOSING_BALANCED") == "passed"
    assert _status(report, "MOVEMENT_BALANCED") == "passed"


def test_pdf_scanned_uses_ocr():
    ext = readers.extract("pdf", sf.pdf_scanned())
    assert ext.method == "pdf_ocr" and ext.ocr_pages == [1]
    sheet = ext.sheets[0]
    assert sheet.confidence is not None
    _, _, parsed, report = _pipeline(sheet)
    accounts = {x.account_number for x in parsed.valid}
    assert accounts == {r[0] for r in sf.ROWS}, [(x.raw, x.issues) for x in parsed.lines]
    assert _status(report, "CLOSING_BALANCED") == "passed"
    assert any(r.code == "OCR_CONFIDENCE" for r in report.results)


def test_soldes_reperes_par_exercice():
    """Balance N-1 : « Solde N-2 » = ouverture, « Solde N-1 » = clôture, « Mouvement N-1 » = mouvements
    (régression : le repère « N-1 » faisait prendre la clôture et les mouvements pour l'ouverture)."""
    from app.engines.importing.detection import suggest_mapping
    rows = [["N° CPTE", "INTITULES", "SOLDE N-2 DEBITEUR", "SOLDE N-2 CREDITEUR", "MOUVEMENT N-1 DEBIT",
             "MOUVEMENT N-1 CREDIT", "SOLDE N-1 DEBITEUR", "SOLDE N-1 CREDITEUR", "SOLDE N-1"]]
    m = suggest_mapping(rows, 0).column_map
    assert m == {"account_number": 0, "account_label": 1, "opening_debit": 2, "opening_credit": 3,
                 "movement_debit": 4, "movement_credit": 5, "closing_debit": 6, "closing_credit": 7}
