"""Audit financier par l'API : seuils, cycles, revue des comptes, population, échantillon UM, tests, circularisation,
anomalie et synthèse. Méthodologie, référentiel et balance FICTIFS."""

from __future__ import annotations

import uuid
from decimal import Decimal

from tests.integration.test_imports_api import test_framework  # noqa: F401, F811  (fixture partagée)
from tests.integration.test_management_api import _setup

API = "/api/v1"
METHOD_CSV = "\n".join(["type;code;libelle;parent;contenu;ordre", "assertion;EX;Existence (test);;;1",
                        'cycle;VENTES;Ventes-clients (test);;{"account_prefixes": ["41", "70"]};1',
                        "cycle;ACHATS;Achats-fournisseurs (test);;;2"]).encode()


def test_financial_audit_flow(client, make_user, test_framework):  # noqa: F811
    owner, _ctrl, _viewer, cid, fy, _year = _setup(client, make_user, test_framework)
    org_id = client.get(f"{API}/companies/{cid}", headers=owner.headers).json()["organization_id"]
    partner, staff = make_user("fa-par"), make_user("fa-sta")
    for u in (partner, staff):
        client.post(f"{API}/organizations/{org_id}/members", json={"email": u.email, "role": "member"}, headers=owner.headers)
    m = client.post(f"{API}/methodologies", headers=owner.headers, json={
        "organization_id": org_id, "kind": "audit", "name": "Méthode FA test", "version_label": "v1",
        "source_reference": "Méthodologie FICTIVE pour tests"}).json()
    assert client.post(f"{API}/methodologies/{m['id']}/items", headers=owner.headers,
                       files={"file": ("m.csv", METHOD_CSV, "text/csv")}).json()["loaded"] == 3
    assert client.post(f"{API}/methodologies/{m['id']}/publish", headers=owner.headers).status_code == 200
    e = client.post(f"{API}/organizations/{org_id}/engagements", headers=owner.headers, json={
        "company_id": cid, "fiscal_year_id": fy["id"], "engagement_type": "statutory_audit",
        "reference": f"FA-{uuid.uuid4().hex[:6]}", "name": "Audit FA test", "methodology_version_id": m["id"]}).json()
    base = f"{API}/engagements/{e['id']}"
    client.post(f"{base}/independence", headers=owner.headers, json={"statement": "Je suis indépendant (test)."})
    for u, role in ((partner, "partner"), (staff, "staff")):
        client.post(f"{base}/members", headers=owner.headers, json={"user_id": str(u.id), "role": role})
        client.post(f"{base}/independence", headers=u.headers, json={"statement": "Je suis indépendant (test)."})
    fa = f"{base}/fa"

    # seuils : 6 500 000 × 1 % = 65 000 ; 50 % → 32 500 ; 5 % → 3 250
    mat_in = {"benchmark_label": "Produits (test)", "benchmark_source": "manual", "benchmark_amount": "6500000",
              "overall_pct": "1", "performance_pct": "50", "trivial_pct": "5", "basis": "Pourcentages FICTIFS (test)"}
    assert client.post(f"{fa}/materiality", headers=staff.headers, json=mat_in).status_code == 403
    mat = client.post(f"{fa}/materiality", headers=owner.headers, json=mat_in).json()
    assert (mat["overall_amount"], mat["performance_amount"], mat["trivial_amount"]) == ("65000", "32500", "3250")
    assert client.post(f"{fa}/materiality/{mat['id']}/approve", headers=staff.headers).status_code == 403
    assert client.post(f"{fa}/materiality/{mat['id']}/approve", headers=owner.headers).json()["status"] == "approved"
    lines = client.get(f"{fa}/materiality/benchmarks", headers=staff.headers).json()
    assert any(x["code"] == "TR2" for x in lines)

    # cycles et revue des comptes
    r = client.put(f"{fa}/cycles", headers=owner.headers, json=[{"account_prefix": "9", "cycle_code": "INCONNU"}])
    assert r.status_code == 422
    client.put(f"{fa}/cycles", headers=owner.headers, json=[{"account_prefix": "41", "cycle_code": "VENTES"},
                                                            {"account_prefix": "70", "cycle_code": "VENTES"},
                                                            {"account_prefix": "40", "cycle_code": "ACHATS"}])
    created = client.post(f"{fa}/account-reviews/refresh", headers=staff.headers).json()["created"]
    acc = client.get(f"{fa}/account-reviews", headers=staff.headers).json()
    assert created == len(acc["accounts"]) > 0
    a411 = next(a for a in acc["accounts"] if a["account_number"].startswith("411"))
    assert a411["cycle_code"] == "VENTES" and a411["threshold_used"] == "32500"
    r = client.patch(f"{fa}/account-reviews/{a411['id']}", headers=staff.headers,
                     json={"explanation": "Variation expliquée (test)", "conclusion": "Solde justifié (test)", "status": "reviewed"})
    assert r.status_code == 200 and r.json()["status"] == "reviewed", r.text

    # population, échantillon en unités monétaires, tests, conclusion
    pop = client.post(f"{fa}/populations/from-balance", headers=staff.headers,
                      json={"name": "Comptes de tiers", "account_prefixes": ["40", "41"]}).json()
    assert pop["item_count"] == 2
    s = client.post(f"{fa}/samples", headers=staff.headers, json={
        "population_id": pop["id"], "reference": "E1", "objective": "Existence (test)", "method": "mus", "size": 2,
        "size_basis": "Taille FICTIVE fixée pour le test"}).json()
    assert s["selected_count"] >= 1 and s["seed"] is not None
    assert client.post(f"{fa}/populations/from-balance", headers=staff.headers,
                       json={"name": "x", "account_prefixes": ["99"]}).status_code == 422
    first, *rest = s["items"]
    book = Decimal(first["book_amount"])
    r = client.patch(f"{fa}/samples/{s['id']}/items/{first['id']}", headers=staff.headers,
                     json={"result": "exception", "audited_amount": str(book - 100), "comment": "Écart (test)"})
    assert r.status_code == 200 and r.json()["misstatement"] == "100", r.text
    assert client.post(f"{fa}/samples/{s['id']}/conclude", headers=staff.headers,
                       json={"conclusion": "x" * 5}).status_code == (422 if rest else 200)
    for it in rest:
        client.patch(f"{fa}/samples/{s['id']}/items/{it['id']}", headers=staff.headers, json={"result": "no_exception"})
    if rest:
        r = client.post(f"{fa}/samples/{s['id']}/conclude", headers=staff.headers, json={"conclusion": "Anomalie à proposer"})
        assert r.status_code == 200, r.text
    concluded = client.get(f"{fa}/samples/{s['id']}", headers=staff.headers).json()
    assert concluded["status"] == "concluded" and concluded["actual_misstatement"] == "100"

    # circularisation de l'élément testé
    conf = client.post(f"{fa}/confirmations/from-population", headers=staff.headers, json={
        "population_id": pop["id"], "item_ids": [first["population_item_id"]], "confirmation_type": "receivable",
        "balance_date": "2100-12-31"}).json()[0]
    cbase = f"{fa}/confirmations/{conf['id']}"
    assert client.patch(cbase, headers=staff.headers, json={"status": "sent"}).status_code == 422
    client.patch(cbase, headers=staff.headers, json={"status": "sent", "sent_on": "2101-01-10"})
    client.patch(cbase, headers=staff.headers, json={"status": "received", "received_on": "2101-01-20",
                                                     "confirmed_amount": str(book - 100)})
    assert client.patch(cbase, headers=staff.headers, json={"status": "closed", "conclusion": "OK"}).status_code == 422
    r = client.patch(cbase, headers=staff.headers, json={"status": "closed", "conclusion": "Écart expliqué (test)",
                                                         "reconciliation": "Avoir non comptabilisé (test)"})
    assert r.status_code == 200 and r.json()["difference"] == "100", r.text
    assert "reference;type;tiers" in client.get(f"{fa}/confirmations.csv", headers=staff.headers).text

    # anomalie, décision, synthèse
    assert client.post(f"{fa}/misstatements", headers=staff.headers, json={
        "reference": "AJ0", "source_type": "confirmation", "source_id": conf["id"], "kind": "factual", "description": "x" * 5,
        "lines": [{"account_number": "701", "debit": "100"}, {"account_number": "411", "credit": "90"}]}).status_code == 422
    ms = client.post(f"{fa}/misstatements", headers=staff.headers, json={
        "reference": "AJ1", "source_type": "confirmation", "source_id": conf["id"], "kind": "factual",
        "description": "Avoir non comptabilisé (test)",
        "lines": [{"account_number": "701100", "debit": "100"}, {"account_number": a411["account_number"], "credit": "100"}]}).json()
    assert client.post(f"{fa}/misstatements/{ms['id']}/decision", headers=staff.headers,
                       json={"status": "uncorrected", "entity_response": "Non corrigé"}).status_code == 403
    r = client.post(f"{fa}/misstatements/{ms['id']}/decision", headers=owner.headers,
                    json={"status": "uncorrected", "entity_response": "La direction ne corrige pas (test)"})
    assert r.status_code == 200, r.text
    summ = client.get(f"{fa}/summary", headers=staff.headers).json()
    assert summ["uncorrected"]["count"] == 1
    if summ["framework_available"]:
        assert summ["uncorrected"]["effect_result"] == "-100" and summ["uncorrected"]["position"] == "below_trivial"
    assert client.put(f"{fa}/conclusion", headers=staff.headers, json={"text": "Conclusion (test) x"}).status_code == 403
    assert client.put(f"{fa}/conclusion", headers=partner.headers,
                      json={"text": "Anomalies non corrigées non significatives (test)"}).status_code == 200
    adj = client.get(f"{fa}/adjusted-balance", headers=staff.headers).json()
    assert all(r["adjustments"] == "0" for r in adj)           # aucune anomalie corrigée
    checks = {c["code"]: c["passed"] for c in client.get(fa, headers=staff.headers).json()["checks"]}
    assert checks["FA_MATERIALITY"] and checks["FA_SAMPLES"] and checks["FA_UNCORRECTED"] and not checks["FA_ACCOUNTS"]
