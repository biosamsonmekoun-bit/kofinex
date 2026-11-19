"""Parcours d'import complet par l'API (traitement « inline », stockage local).

Référentiel et balances FICTIFS : aucune règle comptable officielle n'est utilisée.
"""

from __future__ import annotations


import pytest

from tests.engines import sample_files as sf
from tests.integration.years import free_year

API = "/api/v1"

CHART_CSV = "\n".join([
    "numero;libelle;nature;sens",
    "1;Classe test 1;;", "10;Racine test 10;capitaux_propres;credit", "101;Compte test 101;capitaux_propres;credit",
    "4;Classe test 4;;", "40;Racine test 40;passif;credit", "401;Compte test 401;passif;credit",
    "41;Racine test 41;actif;debit", "411;Compte test 411;actif;debit",
    "5;Classe test 5;;", "52;Racine test 52;actif;debit", "521;Compte test 521;actif;debit",
    "6;Classe test 6;;", "601;Compte test 601;charge;debit",
    "7;Classe test 7;;", "701;Compte test 701;produit;credit",
]).encode()

MAPPINGS_CSV = "\n".join([
    "etat;code_rubrique;libelle_rubrique;prefixe;regle",
    "bilan_actif;TA1;Rubrique test actif 1;41;solde_debiteur",
    "bilan_actif;TA2;Rubrique test actif 2;52;solde_debiteur",
    "bilan_passif;TP1;Rubrique test passif 1;10;solde_crediteur",
    "bilan_passif;TP2;Rubrique test passif 2;40;solde_crediteur",
    "compte_resultat;TR1;Rubrique test charges;60;solde_net_debiteur",
    "compte_resultat;TR2;Rubrique test produits;70;solde_net_crediteur",
]).encode()


# structure FICTIVE : une ligne de détail par rubrique de MAPPINGS_CSV, un total par état
STRUCTURE_CSV = "\n".join([
    "etat;code;libelle;ordre;type;formule;role;niveau",
    "bilan_actif;TA1;Rubrique test actif 1;10;detail;;;1",
    "bilan_actif;TA2;Rubrique test actif 2;20;detail;;;1",
    "bilan_actif;TA_TOT;Total actif (test);90;total;TA1 + TA2;total_actif;0",
    "bilan_passif;TP1;Rubrique test passif 1;10;detail;;;1",
    "bilan_passif;TP2;Rubrique test passif 2;20;detail;;;1",
    "bilan_passif;TP_TOT;Total passif (test);90;total;TP1 + TP2;total_passif;0",
    "compte_resultat;TR1;Rubrique test charges;10;detail;;;1",
    "compte_resultat;TR2;Rubrique test produits;20;detail;;;1",
    "compte_resultat;TR_NET;Résultat (test);90;total;TR2 - TR1;resultat_compte_resultat;0",
]).encode()


@pytest.fixture
def test_framework(client, make_user):
    """Référentiel de test publié (le code doit correspondre à un profil : on utilise SYSCEBNL sur une
    période lointaine pour ne pas interférer avec de vraies versions)."""
    admin = make_user("pfadmin")
    client.get(f"{API}/me", headers=admin.headers)
    admin.make_platform_admin()
    year = free_year("SYSCEBNL", 2100, 2900)
    r = client.post(f"{API}/frameworks/SYSCEBNL/versions", headers=admin.headers, json={
        "version_label": f"TEST-{year}", "effective_from": f"{year}-01-01", "effective_to": f"{year + 1}-01-01",
        "source_reference": "Référentiel FICTIF pour tests automatisés"})
    assert r.status_code == 201, r.text
    vid = r.json()["id"]
    assert client.post(f"{API}/framework-versions/{vid}/publish", headers=admin.headers).status_code == 409
    r = client.post(f"{API}/framework-versions/{vid}/chart", headers=admin.headers,
                    files={"file": ("plan.csv", CHART_CSV, "text/csv")})
    assert r.status_code == 200 and r.json()["loaded"] == 15, r.text
    r = client.post(f"{API}/framework-versions/{vid}/structure", headers=admin.headers,
                    files={"file": ("structure.csv", STRUCTURE_CSV, "text/csv")})
    assert r.status_code == 200 and r.json()["loaded"] == 9, r.text
    r = client.post(f"{API}/framework-versions/{vid}/mappings", headers=admin.headers,
                    files={"file": ("corr.csv", MAPPINGS_CSV, "text/csv")})
    assert r.status_code == 200, r.text
    r = client.post(f"{API}/framework-versions/{vid}/publish", headers=admin.headers)
    assert r.status_code == 200 and r.json()["status"] == "published", r.text
    # figée
    r = client.post(f"{API}/framework-versions/{vid}/chart", headers=admin.headers,
                    files={"file": ("plan.csv", CHART_CSV, "text/csv")})
    assert r.status_code == 409
    return {"version_id": vid, "year": year, "admin": admin}


def test_reference_admin_restricted(client, make_user):
    u = make_user("notadmin")
    r = client.post(f"{API}/frameworks/SYSCOHADA_REV/versions", headers=u.headers, json={
        "version_label": "X", "effective_from": "2030-01-01", "source_reference": "Référence de test"})
    assert r.status_code == 403
    assert client.get(f"{API}/frameworks", headers=u.headers).status_code == 200
    r = client.get(f"{API}/framework-templates/chart.csv", headers=u.headers)
    assert r.status_code == 200 and "numero;libelle" in r.text


def test_full_import_flow(client, make_user, test_framework):
    year = test_framework["year"]
    owner, acc, viewer = make_user("i-own"), make_user("i-acc"), make_user("i-view")
    org = client.post(f"{API}/organizations", json={"name": "Cabinet Import"}, headers=owner.headers).json()
    for u in (acc, viewer):
        client.post(f"{API}/organizations/{org['id']}/members", json={"email": u.email, "role": "member"},
                    headers=owner.headers)
    comp = client.post(f"{API}/organizations/{org['id']}/companies",
                       json={"name": "EBNL test", "framework_code": "SYSCEBNL"}, headers=owner.headers).json()
    cid = comp["id"]
    client.post(f"{API}/companies/{cid}/members", json={"user_id": str(acc.id), "role": "accountant"},
                headers=owner.headers)
    client.post(f"{API}/companies/{cid}/members", json={"user_id": str(viewer.id), "role": "viewer"},
                headers=owner.headers)
    fy = client.post(f"{API}/companies/{cid}/fiscal-years", headers=acc.headers,
                     json={"label": str(year), "start_date": f"{year}-01-01", "end_date": f"{year}-12-31"}).json()

    xlsx = ("balance.xlsx", sf.xlsx_two_level_header(), "application/octet-stream")
    r = client.post(f"{API}/companies/{cid}/imports", headers=viewer.headers, files={"file": xlsx},
                    data={"fiscal_year_id": fy["id"]})
    assert r.status_code == 403
    r = client.post(f"{API}/companies/{cid}/imports", headers=acc.headers,
                    files={"file": ("virus.exe", b"MZ...", "application/octet-stream")},
                    data={"fiscal_year_id": fy["id"]})
    assert r.status_code == 422

    r = client.post(f"{API}/companies/{cid}/imports", headers=acc.headers, files={"file": xlsx},
                    data={"fiscal_year_id": fy["id"]})
    assert r.status_code == 202, r.text
    job = r.json()
    assert job["status"] == "awaiting_mapping"
    assert job["framework_version_id"] == test_framework["version_id"]
    assert job["sheet_name"] == "Balance 2025" and job["header_row"] == 3
    assert len(job["sheets"]) == 2

    base = f"{API}/companies/{cid}/imports/{job['id']}"
    r = client.post(f"{base}/configure", headers=acc.headers, json={
        "sheet_name": job["sheet_name"], "header_row": job["header_row"], "column_map": job["column_map"]})
    assert r.status_code == 202, r.text
    job = r.json()
    assert job["status"] == "awaiting_confirmation"
    codes = {c["code"]: c["status"] for c in job["controls"]["results"]}
    assert codes["CLOSING_BALANCED"] == "passed" and codes["ACCOUNT_CLASS"] == "passed"
    assert codes["UNKNOWN_ACCOUNTS"] == "passed" and not job["controls"]["blocking"]

    rows = client.get(f"{base}/rows?status_filter=valid", headers=viewer.headers).json()
    assert rows["total"] == 6
    r = client.post(f"{base}/confirm", headers=acc.headers, json={"save_mapping_as": "Export test"})
    assert r.status_code == 200 and r.json()["status"] == "completed", r.text

    tb = client.get(f"{API}/companies/{cid}/fiscal-years/{fy['id']}/trial-balance", headers=viewer.headers).json()
    assert tb["total_count"] == 6
    assert tb["totals"]["closing_debit"] == tb["totals"]["closing_credit"] == "17800000.50"
    tb4 = client.get(f"{API}/companies/{cid}/fiscal-years/{fy['id']}/trial-balance?account_class=4",
                     headers=viewer.headers).json()
    assert {i["account_number"] for i in tb4["items"]} == {"401100", "411100"}

    # second import : signalé comme doublon, puis remplace le premier
    r = client.post(f"{API}/companies/{cid}/imports", headers=acc.headers, files={"file": xlsx},
                    data={"fiscal_year_id": fy["id"]})
    job2 = r.json()
    assert job2["extraction"]["duplicate_of_document"] == job["document_id"]
    assert job2["mapping_id"] is not None          # modèle d'association enregistré réappliqué
    r = client.post(f"{API}/companies/{cid}/imports/{job2['id']}/configure", headers=acc.headers, json={
        "sheet_name": job2["sheet_name"], "header_row": job2["header_row"], "column_map": job2["column_map"]})
    client.post(f"{API}/companies/{cid}/imports/{job2['id']}/confirm", headers=acc.headers, json={})
    history = {j["id"]: j["status"] for j in client.get(f"{API}/companies/{cid}/imports", headers=acc.headers).json()}
    assert history[job["id"]] == "superseded" and history[job2["id"]] == "completed"

    # balance déséquilibrée : validation refusée
    bad = sf.csv_french_cp1252().replace(b"10 500 000,00", b"10 400 000,00")
    r = client.post(f"{API}/companies/{cid}/imports", headers=acc.headers,
                    files={"file": ("bal.csv", bad, "text/csv")}, data={"fiscal_year_id": fy["id"]})
    j3 = r.json()
    r = client.post(f"{API}/companies/{cid}/imports/{j3['id']}/configure", headers=acc.headers, json={
        "sheet_name": j3["sheet_name"], "header_row": j3["header_row"], "column_map": j3["column_map"]})
    assert r.json()["controls"]["blocking"]
    r = client.post(f"{API}/companies/{cid}/imports/{j3['id']}/confirm", headers=acc.headers, json={})
    assert r.status_code == 409

    # exercice clôturé : plus d'import
    client.post(f"{API}/companies/{cid}/fiscal-years/{fy['id']}/close", headers=acc.headers,
                json={"confirm_label": fy["label"]})
    r = client.post(f"{API}/companies/{cid}/imports", headers=acc.headers, files={"file": xlsx},
                    data={"fiscal_year_id": fy["id"]})
    assert r.status_code == 409

    # autre tenant
    outsider = make_user("i-out")
    assert client.get(base, headers=outsider.headers).status_code == 404
