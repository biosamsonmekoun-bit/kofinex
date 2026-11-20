"""Plan de trésorerie par l'API (phase 4 ; docs/CONTROLE_GESTION.md § 12.5) — données FICTIVES de `_setup_views` :
encaissement client de 1 000 et règlement fournisseur de 500 en mars (banque 521)."""

from __future__ import annotations

from tests.integration.test_steering_api import _setup_views

API = "/api/v1"
D = float


def test_treasury_plan_cycle(client, make_user):
    owner, org, cid, fy, year, _c1, H = _setup_views(client, make_user)
    C = f"{API}/companies/{cid}"
    L = f"{C}/fiscal-years/{fy['id']}/treasury-plans"

    prop = client.get(f"{L}/opening-proposal", headers=H, params={"source": "native"}).json()
    assert prop["available"] and D(prop["opening_balance"]) == 0          # aucun à-nouveau dans le jeu fictif

    r = client.post(L, headers=H, json={"name": "Plan 1", "opening_balance": "2000"})
    assert r.status_code == 201, r.text
    p = r.json()
    assert p["status"] == "draft" and p["currency"] == "XOF"
    assert client.post(L, headers=H, json={"name": "Plan 1"}).status_code == 409
    P = f"{C}/treasury-plans/{p['id']}"

    rub = [
        {"key": "cli", "section": "receipts", "code": "411", "label": "Encaissements clients", "prefixes": ["411"]},
        {"key": "fou", "section": "disbursements", "label": "Fournisseurs", "order": 1},
        {"key": "ach", "parent_key": "fou", "section": "disbursements", "label": "Achats", "prefixes": ["401"]},
        {"key": "frs", "parent_key": "fou", "section": "disbursements", "label": "Frais", "order": 1,
         "method": "percent_of", "base_key": "ach", "rate": "10"},
    ]
    assert client.put(f"{P}/rubrics", headers=H, json={"rubrics": rub + [{**rub[0], "key": "x", "prefixes": ["4A"]}]}
                      ).status_code == 422
    d = client.put(f"{P}/rubrics", headers=H, json={"rubrics": rub}).json()
    ids = {x["label"]: x["id"] for x in d["rubrics"]}
    assert len(ids) == 4

    amounts = [{"rubric_id": ids["Encaissements clients"], "period": 3, "amount": "1000"},
               {"rubric_id": ids["Achats"], "period": 3, "amount": "400"},
               {"rubric_id": ids["Achats"], "period": 4, "amount": "300"}]
    assert client.put(f"{P}/amounts", headers=H, json={"scenario": "initial", "amounts": amounts + [
        {"rubric_id": ids["Fournisseurs"], "period": 1, "amount": "1"}]}).status_code == 422   # rubrique parente
    assert client.put(f"{P}/amounts", headers=H, json={"scenario": "updated", "amounts": amounts}).status_code == 409
    assert client.put(f"{P}/amounts", headers=H, json={"scenario": "initial", "amounts": amounts}).status_code == 200
    c = client.post(f"{P}/rubrics/{ids['Frais']}/calculate", headers=H).json()
    assert [D(x) for x in c["months"][2:4]] == [40, 30]

    v = client.get(f"{P}/view", headers=H, params={"source": "native", "as_of": f"{year}-03-31"}).json()
    t = v["totals"]
    assert D(t["receipts"][2]) == 1000 and D(t["disbursements"][2]) == 440 and D(t["closing"][2]) == 2560
    assert D(t["closing"][3]) == 2230 and D(t["annual"]["disbursements"]) == 770 and D(t["closing"][11]) == 2230
    assert v["closed_months"] == 3 and v["actual"]["check"] is True
    assert D(v["actual"]["receipts"][2]) == 1000 and D(v["actual"]["disbursements"][2]) == 500
    assert v["actual"]["receipts"][3] is None                                   # mois non clos : pas de réalisé
    rows = {x["label"]: x for x in v["rows"]}
    assert D(rows["Fournisseurs"]["months"][2]) == 440 and D(rows["Fournisseurs"]["actual"][2]) == 500
    assert D(rows["Encaissements clients"]["variance"][2]["rate"]) == 100
    assert D(rows["Achats"]["variance"][2]["variance"]) == 100

    for fmt, magic in (("xlsx", b"PK"), ("pdf", b"%PDF")):
        e = client.get(f"{P}/export", headers=H, params={"format": fmt, "source": "native"})
        assert e.status_code == 200 and e.content[:len(magic)] == magic

    # sécurité : extérieur, comptable (saisie sans approbation)
    out = make_user("tp-out")
    assert client.get(P, headers=out.headers).status_code in (403, 404)
    acc = make_user("tp-acc")
    client.post(f"{API}/organizations/{org['id']}/members", headers=H, json={"email": acc.email, "role": "member"})
    client.post(f"{C}/members", headers=H, json={"user_id": str(acc.id), "role": "accountant"})
    p2 = client.post(L, headers=acc.headers, json={"name": "Plan comptable"})
    assert p2.status_code == 201
    assert client.post(f"{C}/treasury-plans/{p2.json()['id']}/approve", headers=acc.headers).status_code == 403

    # approbation : prévision initiale figée, copiée en prévision actualisée
    a = client.post(f"{P}/approve", headers=H).json()
    assert a["status"] == "approved" and a["amounts"]["updated"] == a["amounts"]["initial"]
    assert client.put(f"{P}/amounts", headers=H, json={"scenario": "initial", "amounts": amounts}).status_code == 409
    assert client.put(f"{P}/rubrics", headers=H, json={"rubrics": rub}).status_code == 409
    assert client.patch(P, headers=H, json={"name": "Autre"}).status_code == 409
    assert client.patch(P, headers=H, json={"notes": "Revue de mars"}).status_code == 200
    upd = [{**amounts[0], "period": 4}, *amounts[1:]]
    assert client.put(f"{P}/amounts", headers=H, json={"scenario": "updated", "amounts": upd}).status_code == 200
    vu = client.get(f"{P}/view", headers=H, params={"source": "native", "as_of": f"{year}-03-31"}).json()
    assert vu["scenario"] == "updated" and D(vu["totals"]["receipts"][3]) == 1000 and D(vu["totals"]["receipts"][2]) == 0
    vi = client.get(f"{P}/view", headers=H, params={"source": "native", "scenario": "initial"}).json()
    assert D(vi["totals"]["receipts"][2]) == 1000

    # prévision glissante : solde de départ = 2 000 + réalisé de janvier à mars (+ 500)
    g = client.get(f"{P}/rolling", headers=H, params={"source": "native", "as_of": f"{year}-04-15"}).json()
    assert D(g["start_opening"]) == 2500 and len(g["months"]) == 12 and len(g["labels"]) == 12
    assert g["months"][0]["basis"] == "forecast" and g["months"][-1]["basis"] == "none" and g["complete"] is False

    assert client.post(f"{P}/archive", headers=H).json()["status"] == "archived"
    assert client.put(f"{P}/amounts", headers=H, json={"scenario": "updated", "amounts": upd}).status_code == 409
    assert client.delete(P, headers=H).status_code == 409
