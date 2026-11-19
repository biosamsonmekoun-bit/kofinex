"""Contrôle de gestion par l'API : centres, saisies, budget (circuit, suivi), modèle CVP, tableau de bord.
Référentiel et balance FICTIFS (réalisé : 601 = 1 800 000,50 en charges ; 701 = 6 500 000 en produits)."""

from __future__ import annotations

from tests.engines import sample_files as sf
from tests.integration.test_imports_api import test_framework  # noqa: F401, F811  (fixture partagée)

API = "/api/v1"


def _setup(client, make_user, test_framework):  # noqa: F811
    year = test_framework["year"]
    owner, ctrl, viewer = make_user("cg-own"), make_user("cg-ctrl"), make_user("cg-view")
    org = client.post(f"{API}/organizations", json={"name": "Cabinet CG"}, headers=owner.headers).json()
    for u in (ctrl, viewer):
        client.post(f"{API}/organizations/{org['id']}/members", json={"email": u.email, "role": "member"},
                    headers=owner.headers)
    cid = client.post(f"{API}/organizations/{org['id']}/companies", headers=owner.headers,
                      json={"name": "Société CG", "framework_code": "SYSCEBNL"}).json()["id"]
    client.post(f"{API}/companies/{cid}/members", json={"user_id": str(ctrl.id), "role": "controller"},
                headers=owner.headers)
    client.post(f"{API}/companies/{cid}/members", json={"user_id": str(viewer.id), "role": "viewer"},
                headers=owner.headers)
    fy = client.post(f"{API}/companies/{cid}/fiscal-years", headers=owner.headers,
                     json={"label": str(year), "start_date": f"{year}-01-01", "end_date": f"{year}-12-31"}).json()
    job = client.post(f"{API}/companies/{cid}/imports", headers=owner.headers,
                      files={"file": ("b.xlsx", sf.xlsx_two_level_header(), "application/octet-stream")},
                      data={"fiscal_year_id": fy["id"]}).json()
    client.post(f"{API}/companies/{cid}/imports/{job['id']}/configure", headers=owner.headers, json={
        "sheet_name": job["sheet_name"], "header_row": job["header_row"], "column_map": job["column_map"]})
    r = client.post(f"{API}/companies/{cid}/imports/{job['id']}/confirm", headers=owner.headers,
                    json={"acknowledge_warnings": True})
    assert r.status_code == 200, r.text
    return owner, ctrl, viewer, cid, fy, year


def test_budget_flow(client, make_user, test_framework):  # noqa: F811
    owner, ctrl, viewer, cid, fy, year = _setup(client, make_user, test_framework)
    base = f"{API}/companies/{cid}"

    r = client.post(f"{base}/cost-centers", headers=viewer.headers,
                    json={"code": "ADM", "name": "Administration", "center_type": "structure"})
    assert r.status_code == 403
    center = client.post(f"{base}/cost-centers", headers=ctrl.headers,
                         json={"code": "adm", "name": "Administration", "center_type": "structure"}).json()
    assert center["code"] == "ADM"
    r = client.post(f"{base}/fiscal-years/{fy['id']}/cost-entries", headers=ctrl.headers, json={
        "cost_center_id": center["id"], "account_number": "601", "entry_date": f"{year}-02-15",
        "amount": "1200.00", "cost_nature": "indirect"})
    assert r.status_code == 201, r.text

    b = client.post(f"{base}/fiscal-years/{fy['id']}/budgets", headers=ctrl.headers,
                    json={"name": "Budget initial"}).json()
    r = client.put(f"{base}/budgets/{b['id']}/lines", headers=ctrl.headers,
                   json=[{"account_prefix": "41", "label": "Clients", "period": 0, "amount": "1"}])
    assert r.status_code == 422                                   # compte de bilan refusé
    r = client.put(f"{base}/budgets/{b['id']}/lines", headers=ctrl.headers, json=[
        {"account_prefix": "601", "label": "Achats", "period": 0, "amount": "2000000"},
        {"account_prefix": "701", "label": "Ventes", "period": 0, "amount": "6000000"},
        *[{"account_prefix": "601", "cost_center_id": center["id"], "label": "Achats administration", "period": p,
           "amount": "100"} for p in range(1, 13)]])
    assert r.status_code == 200, r.text

    t = client.get(f"{base}/budgets/{b['id']}/tracking", headers=viewer.headers).json()
    rows = {(x["account_prefix"], x["cost_center_id"]): x for x in t["rows"]}
    achats = rows[("601", None)]
    assert achats["actual"] == "1800000.5" and achats["variance"] == "-199999.5" and achats["favorable"] is True
    assert rows[("701", None)]["actual"] == "6500000" and rows[("701", None)]["favorable"] is True
    adm = rows[("601", center["id"])]
    assert adm["actual"] == "1200" and adm["actual_by_period"] == {"2": "1200"}
    assert t["totals"]["solde"]["actual"] == "4699999.5"

    # circuit : soumission, auto-approbation refusée, approbation par le propriétaire, gel
    assert client.post(f"{base}/budgets/{b['id']}/submit", headers=ctrl.headers).status_code == 200
    r = client.post(f"{base}/budgets/{b['id']}/approve", headers=ctrl.headers)
    assert r.status_code in (400, 409, 422), r.text
    r = client.post(f"{base}/budgets/{b['id']}/approve", headers=owner.headers)
    assert r.status_code == 200 and r.json()["status"] == "approved", r.text
    r = client.put(f"{base}/budgets/{b['id']}/lines", headers=ctrl.headers, json=[])
    assert r.status_code == 409
    v2 = client.post(f"{base}/budgets/{b['id']}/new-version", headers=ctrl.headers).json()
    assert v2["version"] == 2 and v2["status"] == "draft" and v2["total_lines"] == 14

    # prévision par hypothèses
    fc = client.post(f"{base}/fiscal-years/{fy['id']}/budgets", headers=ctrl.headers,
                     json={"name": "Prévision", "scenario": "forecast"}).json()
    r = client.post(f"{base}/budgets/{fc['id']}/project", headers=ctrl.headers, json={
        "source_fiscal_year_id": fy["id"], "spread": "annual",
        "items": [{"prefix": "701", "label": "Ventes", "rate_pct": "10"}]})
    assert r.status_code == 200, r.text
    assert r.json()["lines"][0]["amount"] == "7150000"


def test_cvp_model_and_dashboard(client, make_user, test_framework):  # noqa: F811
    owner, ctrl, viewer, cid, fy, _ = _setup(client, make_user, test_framework)
    base = f"{API}/companies/{cid}"
    m = client.post(f"{base}/fiscal-years/{fy['id']}/costing-models", headers=ctrl.headers, json={
        "name": "Seuil", "model_type": "cvp",
        "parameters": {"revenue_prefixes": ["701"], "charges": [{"prefix": "601", "variable_pct": "100"}]}}).json()
    r = client.post(f"{base}/costing-models/{m['id']}/compute", headers=ctrl.headers)
    assert r.status_code == 200, r.text
    res = r.json()["results"]
    assert res["contribution_margin"] == "4699999.5" and res["fixed_costs"] == "0"
    assert r.json()["results_current"] is True
    r = client.post(f"{base}/costing-models/{m['id']}/validate", headers=owner.headers)
    assert r.status_code == 200 and r.json()["status"] == "validated"
    r = client.put(f"{base}/costing-models/{m['id']}/parameters", headers=ctrl.headers, json={})
    assert r.status_code == 409

    d = client.get(f"{base}/fiscal-years/{fy['id']}/management-dashboard", headers=viewer.headers)
    assert d.status_code == 200, d.text
    assert d.json()["cvp"]["model_id"] == m["id"]
