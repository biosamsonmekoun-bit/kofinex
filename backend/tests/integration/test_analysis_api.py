"""Moteur financier par l'API : référentiel de test complet (structure, correspondances, concepts),
import d'une balance, analyse, séries, formule propre à l'organisation. Données FICTIVES."""

from __future__ import annotations

import csv
import io
import uuid

from tests.engines import fictitious_framework as ff
from tests.engines import sample_files as sf
from tests.integration.test_imports_api import CHART_CSV

API = "/api/v1"


def _csv(rows) -> bytes:
    buf = io.StringIO()
    csv.writer(buf, delimiter=";").writerows(rows)
    return buf.getvalue().encode()


def _upload(client, admin, vid, kind, content):
    r = client.post(f"{API}/framework-versions/{vid}/{kind}", headers=admin.headers,
                    files={"file": (f"{kind}.csv", content, "text/csv")})
    assert r.status_code == 200, r.text
    return r.json()


def test_analysis_flow(client, make_user):
    admin = make_user("fe-admin")
    admin.make_platform_admin()
    year = 2950 + int(uuid.uuid4().int % 40)
    vid = client.post(f"{API}/frameworks/SYSCOHADA_REV/versions", headers=admin.headers, json={
        "version_label": f"TEST-FE-{year}", "effective_from": f"{year}-01-01", "effective_to": f"{year + 1}-01-01",
        "source_reference": "Référentiel FICTIF pour tests automatisés"}).json()["id"]
    _upload(client, admin, vid, "chart", CHART_CSV)
    r = client.post(f"{API}/framework-versions/{vid}/publish", headers=admin.headers)
    assert r.status_code == 409          # ni structure ni correspondances
    _upload(client, admin, vid, "structure", _csv(ff.STRUCTURE))
    _upload(client, admin, vid, "mappings", _csv(ff.MAPPINGS))
    rep = _upload(client, admin, vid, "concepts", _csv(ff.CONCEPT_ROWS))
    assert any(i["code"] == "CONCEPTS_NOT_BOUND" for i in rep["issues"])
    r = client.post(f"{API}/framework-versions/{vid}/publish", headers=admin.headers)
    assert r.status_code == 200, r.text
    assert len(client.get(f"{API}/framework-versions/{vid}/structure", headers=admin.headers).json()) == 20

    owner = make_user("fe-own")
    org = client.post(f"{API}/organizations", json={"name": "Cabinet Analyse"}, headers=owner.headers).json()
    cid = client.post(f"{API}/organizations/{org['id']}/companies", headers=owner.headers,
                      json={"name": "Société test", "framework_code": "SYSCOHADA_REV"}).json()["id"]
    fy = client.post(f"{API}/companies/{cid}/fiscal-years", headers=owner.headers,
                     json={"label": str(year), "start_date": f"{year}-01-01", "end_date": f"{year}-12-31"}).json()

    # pas de balance : analyse impossible
    r = client.post(f"{API}/companies/{cid}/fiscal-years/{fy['id']}/analyses", headers=owner.headers)
    assert r.status_code == 409

    job = client.post(f"{API}/companies/{cid}/imports", headers=owner.headers,
                      files={"file": ("b.xlsx", sf.xlsx_two_level_header(), "application/octet-stream")},
                      data={"fiscal_year_id": fy["id"]}).json()
    client.post(f"{API}/companies/{cid}/imports/{job['id']}/configure", headers=owner.headers, json={
        "sheet_name": job["sheet_name"], "header_row": job["header_row"], "column_map": job["column_map"]})
    r = client.post(f"{API}/companies/{cid}/imports/{job['id']}/confirm", headers=owner.headers,
                    json={"acknowledge_warnings": True})
    assert r.status_code == 200, r.text

    r = client.post(f"{API}/companies/{cid}/fiscal-years/{fy['id']}/analyses", headers=owner.headers)
    assert r.status_code == 201, r.text
    a = r.json()
    assert a["status"] == "completed"
    ctrl = {c["code"]: c["status"] for c in a["controls"]["statements"]}
    assert ctrl["BALANCE_SHEET_EQUILIBRIUM"] == "passed" and ctrl["NET_INCOME_CONSISTENCY"] == "passed"
    assert {c["code"]: c["status"] for c in a["controls"]["cross_checks"]} == {"FR_BFR_TN": "passed",
                                                                               "CAF_METHODS": "passed"}
    lines = {ln["code"]: ln for ln in a["statements"]["balance_sheet_assets"]}
    assert lines["TA_TOT"]["net"] == "16000000"
    ind = {i["code"]: i for i in a["indicators"]}
    assert ind["FR"]["value"] == "14699999.5" and ind["BFR"]["value"] == "4199999.5"
    assert ind["TN"]["value"] == "10500000"
    assert ind["CAF_ADDITIVE"]["value"] == ind["CAF_SOUSTRACTIVE"]["value"] == "4699999.5"
    assert ind["MARGE_COMMERCIALE"]["status"] == "missing_input"
    assert ind["CROISSANCE_CA"]["status"] == "missing_input"           # pas d'exercice précédent
    assert ind["FR"]["inputs"]["concept(ressources_stables)"] == "14699999.50"

    trace = client.get(f"{API}/companies/{cid}/analyses/{a['id']}/lines/TA_CLI", headers=owner.headers).json()
    assert trace["trace"]["items"][0]["account"] == "411100"

    series = client.get(f"{API}/companies/{cid}/financial-series?codes=CA,FR", headers=owner.headers).json()
    assert [y["label"] for y in series["years"]] == [str(year)]
    assert {s["code"] for s in series["series"]} == {"CA", "FR"}

    # formule propre à l'organisation : vérifiée, versionnée, prise en compte
    bad = client.post(f"{API}/organizations/{org['id']}/financial-formulas", headers=owner.headers, json={
        "code": "RATIO_TEST", "name": "Ratio test", "expression": 'concept("inexistant")', "unit": "ratio",
        "description": "Ratio de test"})
    assert bad.status_code == 422
    ok = client.post(f"{API}/organizations/{org['id']}/financial-formulas", headers=owner.headers, json={
        "code": "RATIO_TEST", "name": "Ratio test", "expression": 'ind("TN") / ind("CA")', "unit": "ratio",
        "rounding_scale": 4, "description": "Trésorerie nette rapportée au CA (test)"})
    assert ok.status_code == 201 and ok.json()["version"] == 1
    v2 = client.post(f"{API}/organizations/{org['id']}/financial-formulas", headers=owner.headers, json={
        "code": "RATIO_TEST", "name": "Ratio test", "expression": 'ind("TN") / ind("CA") * 100', "unit": "percent",
        "description": "Trésorerie nette rapportée au CA, en % (test)"}).json()
    assert v2["version"] == 2
    a2 = client.post(f"{API}/companies/{cid}/fiscal-years/{fy['id']}/analyses", headers=owner.headers).json()
    r2 = next(i for i in a2["indicators"] if i["code"] == "RATIO_TEST")
    assert r2["version"] == 2 and r2["value"] == "161.54" and r2["custom"]
    # l'analyse précédente reste inchangée
    a1 = client.get(f"{API}/companies/{cid}/analyses/{a['id']}", headers=owner.headers).json()
    assert not any(i["code"] == "RATIO_TEST" for i in a1["indicators"])

    outsider = make_user("fe-out")
    assert client.get(f"{API}/companies/{cid}/analyses/{a['id']}", headers=outsider.headers).status_code == 404
