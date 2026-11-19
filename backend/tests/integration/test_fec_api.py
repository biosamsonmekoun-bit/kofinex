"""FEC DGI Bénin par l'API : contrôle préalable (anomalies bloquantes : IFU, date de pièce), écritures non validées
exclues, génération définitive refusée tant qu'une anomalie bloque, fichier de travail, génération sans anomalie (« points
à confirmer », jamais « conforme »), contenu (tabulation, 18 champs, sans en-tête), fractionnement _1.._n, historique et
versions, téléchargements journalisés, traçabilité, droits et cloisonnement. Données FICTIVES. À exécuter en CI."""

from __future__ import annotations

from tests.integration.test_ai_api import _analysis

API = "/api/v1"
OPTS = {"file_format": "txt", "encoding": "iso-8859-15", "record_separator": "crlf"}


def _entry(client, A, H, val, fy, journal, day, piece, piece_date, lines):
    e = client.post(
        f"{A}/entries",
        headers=H,
        json={
            "fiscal_year_id": fy["id"],
            "journal_id": journal["id"],
            "entry_date": day,
            "piece_ref": piece,
            "piece_date": piece_date,
            "label": f"Facture {piece}",
            "lines": lines,
        },
    ).json()
    assert client.post(f"{A}/entries/{e['id']}/transition", headers=H, json={"action": "submit"}).status_code == 200
    if val is not None:
        r = client.post(f"{A}/entries/{e['id']}/transition", headers=val.headers, json={"action": "validate"})
        assert r.status_code == 200, r.text
    return e


def test_fec_benin_cycle(client, make_user):
    owner, org, cid, fy, _a = _analysis(client, make_user)
    A, H = f"{API}/companies/{cid}/accounting", owner.headers
    F = f"{A}/fec"
    year = int(fy["start_date"][:4])
    validator, ctrl, outsider = make_user("fec-val"), make_user("fec-ctrl"), make_user("fec-out")
    for u, role in ((validator, "accountant"), (ctrl, "controller")):
        client.post(f"{API}/organizations/{org['id']}/members", headers=H, json={"email": u.email, "role": "member"})
        assert (
            client.post(f"{API}/companies/{cid}/members", headers=H, json={"user_id": str(u.id), "role": role}).status_code == 201
        )
    assert client.post(f"{A}/accounts/import-chart", headers=H, json={}).status_code == 200
    vt = client.post(f"{A}/journals", headers=H, json={"code": "VT", "label": "Ventes", "journal_type": "sales"}).json()
    sale = [{"account_number": "521", "debit": "1180.00"}, {"account_number": "701", "credit": "1180.00"}]

    _entry(client, A, H, validator, fy, vt, f"{year}-03-01", "F1", f"{year}-03-01", sale)
    _entry(client, A, H, validator, fy, vt, f"{year}-03-02", "F2", None, sale)  # date de pièce absente (champ 10 obligatoire)
    _entry(client, A, H, None, fy, vt, f"{year}-03-03", "F3", f"{year}-03-03", sale)  # soumise, non validée

    # droits
    assert client.get(f"{F}/dashboard", headers=ctrl.headers, params={"fiscal_year_id": fy["id"]}).status_code == 403
    assert client.get(f"{F}/dashboard", headers=outsider.headers, params={"fiscal_year_id": fy["id"]}).status_code in (403, 404)
    assert client.get(f"{A}/settings", headers=H).json()["permissions"]["fec"] is True

    # tableau de bord et contrôle préalable
    d = client.get(f"{F}/dashboard", headers=H, params={"fiscal_year_id": fy["id"]}).json()
    assert (d["entries_total"], d["entries_validated"], d["entries_eligible"]) == (3, 2, 1) and d["last_export"] is None
    body = {"fiscal_year_id": fy["id"], **OPTS}
    c = client.post(f"{F}/check", headers=H, json=body).json()
    codes = {a["code"] for a in c["anomalies"]}
    assert {"IFU_MISSING", "PIECE_DATE_MISSING", "PENDING_ENTRIES"} <= codes and not c["can_generate_working"]
    assert client.post(f"{F}/check", headers=H, json={**body, "record_separator": "tab"}).status_code == 422
    assert client.post(f"{F}/check", headers=H, json={**body, "field_separator": "pipe"}).status_code == 422

    # IFU renseigné : définitive refusée (date de pièce), fichier de travail accepté et déclaré non conforme
    assert (
        client.patch(f"{API}/companies/{cid}", headers=H, json={"tax_id": "3201900000001", "country_code": "BJ"}).status_code
        == 200
    )
    r = client.post(f"{F}/exports", headers=H, json={**body, "kind": "final"})
    assert r.status_code == 409, r.text
    w = client.post(f"{F}/exports", headers=H, json={**body, "kind": "working"})
    assert w.status_code == 201, w.text
    w = w.json()
    end = fy["end_date"].replace("-", "")
    assert w["compliance"] == "non_compliant" and w["filename"] == f"FEC_3201900000001_{end}.txt" and w["version_no"] == 1

    # période sans l'écriture incomplète : génération définitive possible, « points à confirmer » (jamais « conforme »)
    ok = client.post(
        f"{F}/exports",
        headers=H,
        json={**body, "kind": "final", "period_start": f"{year}-03-01", "period_end": f"{year}-03-01", "max_lines_per_file": 1},
    )
    assert ok.status_code == 201, ok.text
    ok = ok.json()
    assert ok["compliance"] == "spec_pending" and ok["version_no"] == 2 and ok["line_count"] == 2
    assert [p["filename"] for p in ok["parts"]] == [f"FEC_3201900000001_{end}_1.txt", f"FEC_3201900000001_{end}_2.txt"]

    # téléchargement : fichier scindé (partie obligatoire), contenu, documentation, anomalies
    assert client.get(f"{F}/exports/{ok['id']}/file", headers=H).status_code == 422
    f1 = client.get(f"{F}/exports/{ok['id']}/file", headers=H, params={"part": 1})
    assert f1.status_code == 200 and f"FEC_3201900000001_{end}_1.txt" in f1.headers["content-disposition"]
    rec = f1.content.split(b"\r\n")
    assert len(rec) == 2 and rec[1] == b"" and len(rec[0].split(b"\t")) == 18 and not rec[0].startswith(b"CodeJournal")
    assert rec[0].split(b"\t")[10] == b"Facture F1" and rec[0].split(b"\t")[11] in (b"1180,00", b"0,00")
    doc = client.get(f"{F}/exports/{ok['id']}/documentation", headers=H)
    assert doc.status_code == 200 and "Tabulation" in doc.text and "CodeDevise" in doc.text
    assert client.get(f"{F}/exports/{w['id']}/anomalies.csv", headers=H).text.count("PIECE_DATE_MISSING") >= 1
    tr = client.get(f"{F}/exports/{ok['id']}/trace", headers=H, params={"row": 1}).json()
    assert tr["entry_id"] and tr["entry_line_id"]

    # historique : deux versions conservées ; contrôleur et autre organisation n'y ont pas accès
    hist = client.get(f"{F}/exports", headers=H, params={"fiscal_year_id": fy["id"]}).json()
    assert [h["version_no"] for h in hist] == [2, 1]
    assert client.get(f"{F}/exports/{ok['id']}/file", headers=ctrl.headers, params={"part": 1}).status_code == 403
    assert client.get(f"{F}/exports", headers=outsider.headers).status_code in (403, 404)
    d = client.get(f"{F}/dashboard", headers=H, params={"fiscal_year_id": fy["id"]}).json()
    assert d["last_export"]["version_no"] == 2
