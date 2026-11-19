"""Import complémentaire du grand livre : reprise du grand livre actif, doublons écartés ligne à ligne, écritures
modifiées refusées (fichier correctif = remplacement), renumérotation, contrôle des périodes. Données FICTIVES."""

from datetime import date
from decimal import Decimal as D

from app.engines.importing import ledger as lg


def L(row, num, acc, d, dv="0", cv="0", lab="Op", jn="VT", status="valid"):  # noqa: N802
    return lg.LedgerLine(row, status, journal_code=jn, entry_number=num, entry_date=d, account_number=acc,
                         label=lab, debit=D(dv), credit=D(cv))


ACTIVE = [L(1, "1", "411", date(2025, 1, 5), "100"), L(2, "1", "701", date(2025, 1, 5), cv="100"),
          L(3, "2", "411", date(2025, 2, 5), "50"), L(4, "2", "701", date(2025, 2, 5), cv="50")]


def test_complement_sans_double_comptage():
    new = lg.LedgerParse([
        # fichier de janvier à mars : janvier et février déjà importés (libellé en casse différente), mars nouveau
        L(1, "1", "411", date(2025, 1, 5), "100", lab="op"), L(2, "1", "701", date(2025, 1, 5), cv="100", lab=" OP "),
        L(3, "2", "411", date(2025, 2, 5), "50"), L(4, "2", "701", date(2025, 2, 5), cv="50"),
        L(5, "3", "411", date(2025, 3, 5), "70"), L(6, "3", "701", date(2025, 3, 5), cv="70"),
        L(7, None, "411", None, status="error"),
    ], "entry_number")
    out, s = lg.complement(ACTIVE, new)
    assert (s["carried"], s["duplicates"], s["added"], s["conflicts"]) == (4, 4, 2, 0)
    assert s["added_months"] == ["2025-03"] and s["overlapping_months"] == []
    valid = out.valid
    assert len(valid) == 6 and sum((x.debit for x in valid), D(0)) == D("220")      # 100 + 50 + 70 : rien n'est additionné deux fois
    assert sorted(x.source_row for x in out.lines) == list(range(1, 12))            # rangs uniques
    assert {i.code for x in out.lines for i in x.issues} == {"DUPLICATE_OF_ACTIVE"}


def test_ecriture_modifiee_refusee():
    new = lg.LedgerParse([L(1, "2", "411", date(2025, 2, 5), "55"), L(2, "2", "701", date(2025, 2, 5), cv="55")], "entry_number")
    out, s = lg.complement(ACTIVE, new)
    assert s["conflicts"] == 2 and s["added"] == 0
    assert all(x.status == "error" and x.issues[-1].code == "ENTRY_CONFLICT" for x in out.lines[4:])


def test_doublons_comptes_ligne_a_ligne():
    active = [L(1, None, "601", date(2025, 1, 1), "10", jn="OD"), L(2, None, "601", date(2025, 1, 1), "10", jn="OD")]
    new = lg.LedgerParse([L(i, None, "601", date(2025, 1, 1), "10", jn="OD") for i in (1, 2, 3)], "none")
    _, s = lg.complement(active, new)
    assert (s["duplicates"], s["added"]) == (2, 1)                                  # deux déjà importées, une nouvelle


def test_option_mode():
    assert lg.LedgerOptions.from_dict({}).mode == "replace" and lg.LedgerOptions.from_dict({"mode": "complement"}).mode == "complement"
