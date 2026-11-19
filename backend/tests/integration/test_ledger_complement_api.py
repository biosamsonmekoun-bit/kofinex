"""Cas de test 4 (pilotage) : import d'un grand livre, puis d'un fichier complémentaire (doublons écartés, lignes
nouvelles ajoutées, rien n'est additionné deux fois), refus d'une écriture modifiée en complément, puis fichier correctif
(remplacement), traçabilité des imports et actualisation des tableaux de bord. Données FICTIVES. À exécuter en CI."""

from __future__ import annotations

from tests.integration.test_imports_api import test_framework  # noqa: F401, F811  (fixture partagée)
from tests.integration.test_ledger_api import HEAD
from tests.integration.test_management_api import _setup

API = "/api/v1"


def _file(year: int, rows) -> bytes:
    lines = [HEAD] + ["|".join([j, j, n, f"{year}{md}", a, a, "", "", "P" + n, f"{year}{md}", lab, de, cr, "", "", "", "", ""])
                      for j, n, md, a, lab, de, cr in rows]
    return ("\n".join(lines) + "\n").encode()


BASE = [("VT", "1", "0315", "411100", "Facture F1", "1200,00", "0,00"), ("VT", "1", "0315", "701100", "Facture F1", "0,00", "1200,00"),
        ("BQ", "2", "0405", "521100", "Règlement F1", "1200,00", "0,00"), ("BQ", "2", "0405", "411100", "Règlement F1", "0,00", "1200,00")]
NEW = [("VT", "3", "0510", "411100", "Facture F2", "300,00", "0,00"), ("VT", "3", "0510", "701100", "Facture F2", "0,00", "300,00")]
MODIFIED = [("VT", "1", "0315", "411100", "Facture F1", "1300,00", "0,00"), ("VT", "1", "0315", "701100", "Facture F1", "0,00", "1300,00")]


def _import(client, base, h, fy, content, mode="replace"):
    job = client.post(f"{base}/ledger-imports", headers=h, data={"fiscal_year_id": fy["id"]},
                      files={"file": ("gl.csv", content, "text/csv")}).json()
    return client.post(f"{base}/ledger-imports/{job['id']}/configure", headers=h, json={
        "sheet_name": job["sheet_name"], "header_row": job["header_row"], "column_map": job["column_map"],
        "options": {"decimal_separator": ",", "mode": mode}}).json()


def _confirm(client, base, h, job):
    return client.post(f"{base}/ledger-imports/{job['id']}/confirm", headers=h, json={"acknowledge_warnings": True})


def test_ledger_complement_and_correction(client, make_user, test_framework):  # noqa: F811
    owner, _ctrl, viewer, cid, fy, year = _setup(client, make_user, test_framework)
    base, H = f"{API}/companies/{cid}", owner.headers
    S = f"{base}/fiscal-years/{fy['id']}/steering"

    # complément sans grand livre actif : refusé
    j0 = _import(client, base, H, fy, _file(year, NEW), mode="complement")
    assert j0["status"] == "failed" and "aucun grand livre" in (j0.get("failure_reason") or "").lower()

    # 1. grand livre initial
    j1 = _import(client, base, H, fy, _file(year, BASE))
    assert _confirm(client, base, H, j1).status_code == 200
    wm1 = client.get(f"{S}/watermark", headers=H).json()["token"]
    f1 = client.get(f"{S}/financial", headers=H, params={"source": "imported"}).json()
    assert float(f1["kpis"]["total_produits"]) == 1200

    # 2. fichier complémentaire : reprend mars et avril (doublons) et ajoute mai
    j2 = _import(client, base, H, fy, _file(year, BASE + NEW), mode="complement")
    comp = j2["controls"]["complement"]
    assert (comp["carried"], comp["duplicates"], comp["added"], comp["conflicts"]) == (4, 4, 2, 0), j2["controls"]
    assert comp["added_months"] == [f"{year}-05"] and not j2["controls"]["blocking"]
    assert _confirm(client, base, H, j2).status_code == 200
    f2 = client.get(f"{S}/financial", headers=H, params={"source": "imported"}).json()
    assert float(f2["kpis"]["total_produits"]) == 1500                         # 1 200 + 300, pas 2 700
    assert client.get(f"{S}/watermark", headers=H).json()["token"] != wm1     # tableaux de bord à actualiser
    lines = client.get(f"{base}/fiscal-years/{fy['id']}/ledger", headers=H, params={"account": "701100"}).json()
    assert lines["total_count"] == 2

    # 3. écriture modifiée présentée en complément : refusée (bloquant)
    j3 = _import(client, base, H, fy, _file(year, MODIFIED), mode="complement")
    assert j3["controls"]["complement"]["conflicts"] == 2 and j3["controls"]["blocking"]
    assert _confirm(client, base, H, j3).status_code == 409
    client.post(f"{base}/ledger-imports/{j3['id']}/cancel", headers=H)

    # 4. fichier correctif complet (remplacement)
    j4 = _import(client, base, H, fy, _file(year, MODIFIED + BASE[2:] + NEW))
    assert _confirm(client, base, H, j4).status_code == 200
    f4 = client.get(f"{S}/financial", headers=H, params={"source": "imported"}).json()
    assert float(f4["kpis"]["total_produits"]) == 1600                         # 1 300 + 300

    # traçabilité : historique des imports, un seul actif
    jobs = {j["id"]: j for j in client.get(f"{base}/ledger-imports", headers=viewer.headers).json()}
    assert jobs[j1["id"]]["status"] == jobs[j2["id"]]["status"] == "superseded" and jobs[j4["id"]]["active"]
    assert jobs[j3["id"]]["status"] == "cancelled" and sum(1 for j in jobs.values() if j["active"]) == 1
