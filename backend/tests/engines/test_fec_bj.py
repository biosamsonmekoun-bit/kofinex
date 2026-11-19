"""Tests du moteur FEC DGI Bénin (arrêté n° 1085 du 23 avril 2020). Données FICTIVES."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from app.engines.accounting import fec_bj as f

UTC = timezone.utc
D = Decimal


def _ln(n, *, entry="e1", seq=1, jr="VT", acc="411100", debit="0", credit="0", at=(2025, 3, 1, 9), **kw):
    base = dict(
        entry_id=entry, line_id=f"{entry}-{n}", journal_code=jr, journal_label="Ventes", number=f"{jr}-{seq:06d}",
        sequence_no=seq, entry_date=date(2025, 3, 1), line_no=n, account=acc, account_label="Clients",
        debit=D(debit), credit=D(credit), validated_at=datetime(*at, tzinfo=UTC), piece_ref="F001",
        piece_date=date(2025, 3, 1), entry_label="Facture F001", chart_account=acc[:4], chart_label=None,
    )
    base.update(kw)
    return f.FecLine(**base)


def _sale(entry="e1", seq=1, at=(2025, 3, 1, 9), **kw):
    return [_ln(1, entry=entry, seq=seq, at=at, acc="411100", debit="1180", **kw),
            _ln(2, entry=entry, seq=seq, at=at, acc="701100", credit="1180", account_label="Ventes de marchandises", **kw)]


def _ctx(lines, **kw):
    fy_entries = {ln.entry_id: f.FyEntry(ln.entry_id, ln.journal_code, ln.sequence_no, ln.origin, ln.validated_at) for ln in lines}
    base = dict(ifu="3201900000001", country_code="BJ", framework_code="SYSCOHADA_REV", fy_start=date(2025, 1, 1),
                fy_end=date(2025, 12, 31), fy_closed=True, period_start=date(2025, 1, 1), period_end=date(2025, 12, 31),
                has_previous_fy=False, imported_ledger_active=False, fy_entries=list(fy_entries.values()))
    base.update(kw)
    return f.FecContext(**base)


OPTS = f.FecOptions(file_format="txt", encoding="iso-8859-15", record_separator="crlf")


def _codes(res):
    return {a.code for a in res.anomalies}


# ----------------------------------------------------------------------------------------- structure (art. 4 et 5)
def test_ordre_des_18_champs_et_champs_de_tresorerie():
    assert f.FIELDS == ("CodeJournal", "LibJournal", "NumEcriture", "DateEcriture", "NumCompte", "LibCompte", "NumCompteAux",
                        "LibCompteAux", "RefPiece", "DatePiece", "LibEcriture", "MontDebit", "MontCredit", "LetEcriture",
                        "DateLetEcriture", "DateValid", "MontDevise", "CodeDevise")
    assert [s.order for s in f.FIELD_SPECS] == list(range(1, 19))
    assert f.CASH_FIELDS == ("Date Règlement", "Mode Règlement", "NatOp")
    assert replace(OPTS, accounting_type="cash").fields == f.FIELDS + f.CASH_FIELDS
    assert len(f.row(_sale()[0], OPTS)) == 18 and len(f.row(_sale()[0], replace(OPTS, accounting_type="cash"))) == 21


def test_valeurs_obligatoires_selon_l_article_5():
    mandatory = {s.name for s in f.FIELD_SPECS if s.mandatory}
    assert mandatory == {"CodeJournal", "LibJournal", "NumEcriture", "DateEcriture", "NumCompte", "LibCompte", "RefPiece",
                         "DatePiece", "LibEcriture", "MontDebit", "MontCredit", "DateValid"}
    assert {s.name: s.mandatory for s in f.CASH_FIELD_SPECS} == {"Date Règlement": True, "Mode Règlement": True, "NatOp": False}


def test_formats_dates_et_montants():
    assert f.fmt_date(date(2025, 1, 5)) == "20250105"
    assert f.fmt_amount(D("1234567.5")) == "1234567,50"  # virgule décimale, aucun séparateur de milliers
    assert f.fmt_amount(D("0")) == "0,00"
    assert f.fmt_amount(D("-12")) == "-12,00"  # signe en premier caractère
    with pytest.raises(TypeError):
        f.fmt_amount(12.5)  # type: ignore[arg-type]


def test_date_de_validation_a_l_heure_du_benin():
    ln = _ln(1, debit="1", at=(2025, 12, 31, 23, 30))
    assert f.row(ln, OPTS)[15] == "20260101"  # 23 h 30 UTC = 0 h 30 à Porto-Novo


def test_fichier_plat_tabulation_sans_en_tete_et_fins_de_ligne():
    lines = _sale()
    for key, eol in (("crlf", b"\r\n"), ("lf", b"\n"), ("cr", b"\r")):
        (part,) = f.render(lines, replace(OPTS, record_separator=key), "3201900000001", date(2025, 12, 31))
        recs = part.content.split(eol)
        assert recs[-1] == b"" and len(recs) == 3  # une ligne par ligne d'écriture, chacune terminée ; pas d'en-tête
        assert recs[0].split(b"\t")[0] == b"VT" and len(recs[0].split(b"\t")) == 18
        assert not recs[0].startswith(b"CodeJournal")
    assert f.SEPARATORS == {"tab": "\t"}
    assert f.FecOptions(file_format="txt", encoding="ascii", record_separator="lf", field_separator="pipe").validate()


def test_encodage_iso_8859_15_et_ascii():
    lines = [replace(ln, entry_label="Facture réglée") for ln in _sale()]
    (part,) = f.render(lines, OPTS, "3201900000001", date(2025, 12, 31))
    assert "réglée".encode("iso8859_15") in part.content
    res = f.check(lines, _ctx(lines), replace(OPTS, encoding="ascii"))
    assert "ENCODING" in _codes(res) and res.fatal  # aucune translittération : la génération est refusée


def test_nom_du_fichier_et_fractionnement():
    assert f.filename("3201900000001", date(2025, 12, 31), "txt") == "FEC_3201900000001_20251231.txt"
    lines = _sale("e1", 1) + _sale("e2", 2, at=(2025, 3, 2, 9)) + [_ln(1, entry="e3", seq=3, debit="5", at=(2025, 3, 3, 9))]
    single = f.render(lines, OPTS, "3201900000001", date(2025, 12, 31))
    parts = f.render(lines, replace(OPTS, max_lines_per_file=2), "3201900000001", date(2025, 12, 31))
    assert [p.filename for p in single] == ["FEC_3201900000001_20251231.txt"]
    assert [p.filename for p in parts] == [f"FEC_3201900000001_20251231_{i}.txt" for i in (1, 2, 3)]
    assert [p.line_count for p in parts] == [2, 2, 1]
    assert b"".join(p.content for p in parts) == single[0].content
    assert f.global_sha256(parts) == hashlib.sha256(single[0].content).hexdigest()


def test_ordre_chronologique_de_validation():
    late, early = _sale("late", 1, at=(2025, 3, 5, 9)), _sale("early", 2, at=(2025, 3, 2, 9))
    assert [ln.entry_id for ln in f.ordered(late + early)] == ["early", "early", "late", "late"]


# ------------------------------------------------------------------------------------------------------- contrôles
def test_fichier_sans_anomalie_jamais_declare_conforme_tant_que_des_points_restent():
    lines = _sale()
    res = f.check(lines, _ctx(lines), OPTS)
    assert res.blocking == 0, res.anomalies
    assert f.UNCONFIRMED and not f.SPEC_CONFIRMED and res.compliance == "spec_pending"


def test_ecritures_de_report_libelle_rang_et_presence():
    rep = [replace(ln, origin="opening", journal_code="AN", number="AN-000001", line_label="Report clients") for ln in _sale("r", 1)]
    assert f.row(rep[0], OPTS)[10] == "REPORT"
    ok = rep + _sale("s", 1, at=(2025, 3, 2, 9))
    assert not {"REPORT_NOT_FIRST", "REPORT_NOT_FIRST_IN_FILE"} & _codes(f.check(ok, _ctx(ok, has_previous_fy=True)))
    late = [replace(ln, validated_at=datetime(2025, 4, 1, tzinfo=UTC)) for ln in rep] + _sale("s", 1, at=(2025, 3, 2, 9))
    assert "REPORT_NOT_FIRST_IN_FILE" in _codes(f.check(late, _ctx(late, has_previous_fy=True)))
    same_journal = [replace(ln, journal_code="VT", sequence_no=2, number="VT-000002") for ln in rep] + _sale("s", 1)
    assert "REPORT_NOT_FIRST" in _codes(f.check(same_journal, _ctx(same_journal)))
    none = _sale()
    assert "REPORT_MISSING" in _codes(f.check(none, _ctx(none, has_previous_fy=True)))
    assert "REPORT_MISSING" not in _codes(f.check(none, _ctx(none, has_previous_fy=False)))


def test_numerotation_continue_et_doublons():
    lines = _sale("a", 1) + _sale("c", 3, at=(2025, 3, 3, 9))
    res = f.check(lines, _ctx(lines))
    gap = next(a for a in res.anomalies if a.code == "NUMBER_GAP")
    assert gap.severity == "blocking" and "[2]" in gap.description
    dup = _sale("a", 1) + _sale("b", 1, at=(2025, 3, 3, 9))
    assert "NUMBER_DUPLICATE" in _codes(f.check(dup, _ctx(dup)))
    twice = _sale() + [_sale()[0]]
    assert "DUPLICATE_LINE" in _codes(f.check(twice, _ctx(twice)))


def test_champs_obligatoires_absents_bloquants():
    lines = [replace(ln, piece_date=None, piece_ref="") for ln in _sale()]
    res = f.check(lines, _ctx(lines), OPTS)
    assert {"PIECE_DATE_MISSING", "PIECE_REF_MISSING", "MANDATORY_EMPTY"} <= _codes(res)
    assert all(a.severity == "blocking" for a in res.anomalies if a.code.startswith("PIECE_"))
    assert res.compliance == "non_compliant" and res.entry_counts()["eligible"] == 0


def test_comptes_syscohada_et_nomenclature():
    bad = [replace(_sale()[0], account="AB1100"), _sale()[1]]
    assert "ACCOUNT_INVALID" in _codes(f.check(bad, _ctx(bad)))
    unlinked = [replace(_sale()[0], chart_account=None), _sale()[1]]
    assert "ACCOUNT_INVALID" in _codes(f.check(unlinked, _ctx(unlinked)))
    renamed = [replace(_sale()[0], account="4111", chart_account="4111", account_label="Mes clients", chart_label="Clients"),
               _sale()[1]]
    an = next(a for a in f.check(renamed, _ctx(renamed)).anomalies if a.code == "ACCOUNT_LABEL_NOMENCLATURE")
    assert an.severity == "warning"


def test_sources_ecritures_non_validees_et_grand_livre_importe():
    lines = _sale()
    pend = f.check(lines, _ctx(lines, pending={"draft": 2, "submitted": 1}))
    assert next(a for a in pend.anomalies if a.code == "PENDING_ENTRIES").severity == "warning"
    only_imported = f.check([], _ctx([], imported_ledger_active=True))
    assert "SOURCE_IMPORTED_ONLY" in _codes(only_imported) and only_imported.fatal
    both = f.check(lines, _ctx(lines, imported_ledger_active=True))
    assert "IMPORTED_NOT_INCLUDED" in _codes(both) and both.blocking == 0


def test_comptabilite_de_tresorerie_champs_non_tenus():
    lines = _sale()
    opts = replace(OPTS, accounting_type="cash")
    res = f.check(lines, _ctx(lines), opts)
    assert "CASH_DATA_UNAVAILABLE" in _codes(res) and res.compliance == "non_compliant" and not res.fatal
    (part,) = f.render(lines, opts, "3201900000001", date(2025, 12, 31))
    first = part.content.split(b"\r\n")[0].split(b"\t")
    assert len(first) == 21 and first[18:] == [b"", b"", b""]  # jamais de donnée inventée


def test_separateur_dans_une_zone_et_ifu():
    lines = [replace(_sale()[0], line_label="Client\tA"), _sale()[1]]
    res = f.check(lines, _ctx(lines), OPTS)
    assert "SEPARATOR_IN_VALUE" in _codes(res) and res.fatal
    assert "IFU_MISSING" in _codes(f.check(_sale(), _ctx(_sale(), ifu=None)))
    assert "IFU_FORMAT" in _codes(f.check(_sale(), _ctx(_sale(), ifu="32 019")))


def test_equilibre_et_montants():
    lines = [_sale()[0], replace(_sale()[1], credit=D("1000"))]
    assert "ENTRY_UNBALANCED" in _codes(f.check(lines, _ctx(lines)))
    both = [replace(_sale()[0], credit=D("1"))]
    assert "AMOUNT_INVALID" in _codes(f.check(both, _ctx(both)))


def test_devise_et_lettrage():
    lines = [replace(_sale()[0], currency="EUR", currency_amount=D("1.80"), lettering_code="AA", lettering_date=date(2025, 4, 1)),
             _sale()[1]]
    r = f.row(lines[0], OPTS)
    assert (r[13], r[14], r[16], r[17]) == ("AA", "20250401", "1,80", "EUR")  # LetEcriture, DateLetEcriture, MontDevise, CodeDevise
    assert f.check(lines, _ctx(lines), OPTS).blocking == 0
    half = [replace(_sale()[0], currency="EUR"), _sale()[1]]
    assert "CURRENCY_INCOMPLETE" in _codes(f.check(half, _ctx(half)))


def test_documentation_article_7():
    lines = _sale()
    parts = f.render(lines, OPTS, "3201900000001", date(2025, 12, 31))
    meta = {"filename": parts[0].filename, "parts": [{"filename": p.filename, "line_count": p.line_count,
            "size_bytes": len(p.content), "sha256": p.sha256} for p in parts], "sha256": f.global_sha256(parts)}
    doc = f.documentation(OPTS, meta).decode("utf-8")
    for needle in ("Jeu de caractères", "ISO 8859-15", "Séparateur des champs", "Tabulation", "Séparateur des enregistrements",
                   "CR LF", "18. CodeDevise", "1. CodeJournal", "Points réglementaires restant à confirmer", parts[0].sha256):
        assert needle in doc, needle


def test_rendu_deterministe():
    lines = _sale() + _sale("e2", 2, at=(2025, 3, 2, 9))
    a = f.render(lines, OPTS, "3201900000001", date(2025, 12, 31))
    b = f.render(list(reversed(lines)), OPTS, "3201900000001", date(2025, 12, 31))
    assert a[0].content == b[0].content and a[0].sha256 == b[0].sha256
