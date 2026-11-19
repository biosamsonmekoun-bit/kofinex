"""Audit interne par l'API : plan annuel, cartographie, constats, réponse de l'audité, plan d'action et suivi,
rapport (émission, export Word). Méthodologie et données FICTIVES."""

from __future__ import annotations

import io
import uuid

from docx import Document

API = "/api/v1"
METHOD_CSV = "\n".join([
    "type;code;libelle;parent;contenu;ordre",
    'risk_scale;GRILLE;Grille (test);;{"likelihood":[{"score":1,"label":"Faible"},{"score":2,"label":"Forte"}],'
    '"impact":[{"score":1,"label":"Faible"},{"score":2,"label":"Fort"}],"significant_from":4};1',
    'finding_scale;ECH;Échelle (test);;{"levels":[{"code":"N1","label":"Majeur (test)","rank":1},'
    '{"code":"N2","label":"Mineur (test)","rank":2}]};2',
]).encode()


def test_internal_audit_flow(client, make_user):
    owner, manager, staff, auditee, outsider = (make_user(n) for n in ("ia-own", "ia-man", "ia-sta", "ia-aud", "ia-out"))
    org = client.post(f"{API}/organizations", json={"name": "Direction de l'audit (test)"}, headers=owner.headers).json()
    for u in (manager, staff, auditee):
        client.post(f"{API}/organizations/{org['id']}/members", json={"email": u.email, "role": "member"}, headers=owner.headers)
    cid = client.post(f"{API}/organizations/{org['id']}/companies", headers=owner.headers,
                      json={"name": "Filiale (test)", "framework_code": "SYSCEBNL"}).json()["id"]
    m = client.post(f"{API}/methodologies", headers=owner.headers, json={
        "organization_id": org["id"], "kind": "audit", "name": "Méthode IA test", "version_label": "v1",
        "source_reference": "Méthodologie FICTIVE pour tests"}).json()
    r = client.post(f"{API}/methodologies/{m['id']}/items", headers=owner.headers, files={"file": ("m.csv", METHOD_CSV, "text/csv")})
    assert r.json()["loaded"] == 2, r.text
    assert client.post(f"{API}/methodologies/{m['id']}/publish", headers=owner.headers).status_code == 200

    # cartographie
    proc = client.post(f"{API}/companies/{cid}/processes", headers=owner.headers, json={"code": "ACH", "name": "Achats"}).json()
    risk = client.post(f"{API}/companies/{cid}/risks", headers=owner.headers, json={
        "code": "R1", "title": "Fraude fournisseurs (test)", "process_id": proc["id"], "scale_version_id": m["id"],
        "inherent_likelihood": 2, "inherent_impact": 2}).json()
    rm = client.get(f"{API}/companies/{cid}/risk-map", headers=owner.headers).json()
    cell = next(c for c in rm["map"]["cells"] if c["likelihood"] == 2 and c["impact"] == 2)
    assert [x["code"] for x in cell["risks"]] == ["R1"] and cell["significant"] is True
    assert len(client.get(f"{API}/companies/{cid}/risks/{risk['id']}/history", headers=owner.headers).json()) == 1

    # plan annuel
    assert client.post(f"{API}/organizations/{org['id']}/audit-plans", headers=staff.headers,
                       json={"title": "Plan", "period_start": "2027-01-01", "period_end": "2027-12-31"}).status_code == 403
    plan = client.post(f"{API}/organizations/{org['id']}/audit-plans", headers=owner.headers,
                       json={"title": f"Plan {uuid.uuid4().hex[:4]}", "period_start": "2027-01-01", "period_end": "2027-12-31"}).json()
    plan = client.post(f"{API}/audit-plans/{plan['id']}/items", headers=owner.headers, json={
        "company_id": cid, "process_id": proc["id"], "title": "Audit des achats", "rationale": "Risque R1 coté 2 × 2 (test)",
        "budget_days": "20"}).json()
    item = plan["items"][0]
    r = client.post(f"{API}/audit-plans/{plan['id']}/approve", headers=owner.headers,
                    json={"approval_body": "Comité d'audit (test)", "approval_date": "2026-12-15"})
    assert r.status_code == 200 and r.json()["status"] == "approved", r.text
    assert client.post(f"{API}/audit-plans/{plan['id']}/items", headers=owner.headers, json={
        "company_id": cid, "title": "Paie", "rationale": "Demande de la direction (test)"}).status_code == 422

    # mission rattachée au plan
    e = client.post(f"{API}/organizations/{org['id']}/engagements", headers=owner.headers, json={
        "company_id": cid, "engagement_type": "internal_audit", "reference": f"AI-{uuid.uuid4().hex[:5]}",
        "name": "Audit des achats (test)", "methodology_version_id": m["id"]}).json()
    base = f"{API}/engagements/{e['id']}"
    client.post(f"{base}/independence", headers=owner.headers, json={"statement": "Je suis indépendant (test)."})
    for u, role in ((manager, "manager"), (staff, "staff"), (auditee, "auditee")):
        client.post(f"{base}/members", headers=owner.headers, json={"user_id": str(u.id), "role": role})
    for u in (manager, staff):
        client.post(f"{base}/independence", headers=u.headers, json={"statement": "Je suis indépendant (test)."})
    r = client.patch(f"{API}/audit-plan-items/{item['id']}", headers=owner.headers,
                     json={"engagement_id": e["id"], "status": "in_progress"})
    assert r.status_code == 200, r.text
    assert len(client.get(f"{API}/audit-plan-items/{item['id']}/history", headers=owner.headers).json()) >= 2

    # constat, recommandation, validation, communication
    f_in = {"reference": "C1", "title": "Fournisseurs créés sans contrôle (test)", "condition": "12 créations sans validation",
            "criteria": "Procédure : double validation", "effect": "Fournisseur fictif possible", "rating_code": "N1",
            "process_id": proc["id"]}
    assert client.post(f"{base}/findings", headers=staff.headers, json={**f_in, "rating_code": "N9"}).status_code == 422
    fid = client.post(f"{base}/findings", headers=staff.headers, json=f_in).json()["findings"][0]["id"]
    assert client.post(f"{base}/findings/{fid}/status", headers=manager.headers, json={"action": "validate"}).status_code == 422
    rec = client.post(f"{base}/findings/{fid}/recommendations", headers=staff.headers,
                      json={"reference": "R1.1", "text": "Paramétrer la double validation (test)"}).json()["findings"][0]["recommendations"][0]
    assert client.post(f"{base}/findings/{fid}/status", headers=staff.headers, json={"action": "validate"}).status_code == 403
    assert client.post(f"{base}/findings/{fid}/status", headers=manager.headers, json={"action": "validate"}).status_code == 200
    assert client.get(f"{base}/findings", headers=auditee.headers).json()["findings"] == []
    r = client.post(f"{base}/findings/{fid}/status", headers=manager.headers, json={"action": "communicate", "response_due": "2027-05-15"})
    assert r.status_code == 200, r.text

    # réponse et plan d'action par l'audité, suivi
    seen = client.get(f"{base}/findings", headers=auditee.headers).json()["findings"]
    assert [x["reference"] for x in seen] == ["C1"] and seen[0]["rating_label"] == "Majeur (test)"
    assert client.get(f"{base}/workpapers", headers=auditee.headers).status_code == 403
    r = client.post(f"{base}/findings/{fid}/response", headers=auditee.headers,
                    json={"management_response": "Accord : paramétrage au T2 (test)", "response_by_name": "DAF (test)"})
    assert r.status_code == 200 and r.json()["findings"][0]["management_response"], r.text
    r = client.post(f"{base}/recommendations/{rec['id']}/action-plans", headers=auditee.headers,
                    json={"description": "Paramétrage (test)", "owner_name": "Responsable achats", "due_date": "2027-06-30"})
    assert r.status_code == 201, r.text
    ap = r.json()["findings"][0]["recommendations"][0]["action_plans"][0]
    assert client.post(f"{base}/action-plans/{ap['id']}/updates", headers=auditee.headers,
                       json={"status": "verified", "comment": "Fait"}).status_code == 403
    r = client.post(f"{base}/action-plans/{ap['id']}/updates", headers=auditee.headers,
                    json={"status": "in_progress", "comment": "Demande envoyée à l'éditeur (test)"})
    assert r.status_code == 201 and r.json()["status"] == "in_progress", r.text

    # rapport
    rep = client.post(f"{base}/reports", headers=manager.headers, json={
        "title": "Rapport d'audit des achats (test)", "executive_summary": "Synthèse (test)",
        "overall_conclusion": "Dispositif à renforcer (jugement de l'auditeur, test)"}).json()["reports"][0]
    content = client.get(f"{base}/reports/{rep['id']}/content", headers=manager.headers).json()
    assert content["draft"] and content["findings"][0]["reference"] == "C1"
    assert client.get(f"{base}/reports/{rep['id']}/content", headers=auditee.headers).status_code == 403
    d = client.get(f"{base}/reports/{rep['id']}/docx", headers=manager.headers)
    assert d.status_code == 200 and "PROJET" in "\n".join(p.text for p in Document(io.BytesIO(d.content)).paragraphs)
    assert client.post(f"{base}/reports/{rep['id']}/issue", headers=manager.headers).status_code == 403
    r = client.post(f"{base}/reports/{rep['id']}/issue", headers=owner.headers)
    assert r.status_code == 200, r.text
    issued = r.json()["reports"][0]
    assert issued["status"] == "issued" and len(issued["content_sha256"]) == 64
    assert client.get(f"{base}/reports/{rep['id']}/content", headers=auditee.headers).json()["draft"] is False

    # suivi transversal et cloisonnement
    fu = client.get(f"{API}/organizations/{org['id']}/action-plans", headers=manager.headers).json()
    assert fu["summary"]["total"] == 1 and fu["actions"][0]["finding"]["reference"] == "C1"
    assert client.get(f"{base}/findings", headers=outsider.headers).status_code == 404
    checks = {c["code"]: c["passed"] for c in client.get(f"{base}/supervision", headers=manager.headers).json()["issuance_checks"]}
    assert checks["IA_FINDINGS"] and checks["IA_REPORT"]
