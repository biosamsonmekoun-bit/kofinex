"""Socle d'audit par l'API : méthodologie FICTIVE, mission, équipe, risques, programme, feuille, signatures,
élément probant, notes de revue, émission."""

from __future__ import annotations

import json
import uuid

API = "/api/v1"
SCALE = {"likelihood": [{"score": 1, "label": "Faible"}, {"score": 2, "label": "Élevé"}],
         "impact": [{"score": 1, "label": "Faible"}, {"score": 2, "label": "Élevé"}], "significant_from": 4}


def _csv() -> bytes:
    lines = ["type;code;libelle;parent;contenu;ordre", "assertion;EX;Existence (test);;;1",
             f"risk_scale;GRILLE;Grille (test);;{json.dumps(SCALE)};",
             'procedure_template;T1;Inspection (test);;{"nature": "inspection", "steps": ["Étape (test)"], "assertions": ["EX"]};1']
    return "\n".join(lines).encode()


def test_engagement_flow(client, make_user):
    owner, partner, staff, senior = make_user("au-own"), make_user("au-par"), make_user("au-sta"), make_user("au-sen")
    org = client.post(f"{API}/organizations", json={"name": "Cabinet Audit"}, headers=owner.headers).json()
    for u in (partner, staff, senior):
        client.post(f"{API}/organizations/{org['id']}/members", json={"email": u.email, "role": "member"},
                    headers=owner.headers)
    cid = client.post(f"{API}/organizations/{org['id']}/companies", headers=owner.headers,
                      json={"name": "Client audité", "framework_code": "SYSCOHADA_REV"}).json()["id"]

    m = client.post(f"{API}/methodologies", headers=owner.headers, json={
        "organization_id": org["id"], "kind": "audit", "name": "Méthode test", "version_label": "v1",
        "source_reference": "Méthodologie FICTIVE pour tests"}).json()
    r = client.post(f"{API}/methodologies/{m['id']}/items", headers=owner.headers,
                    files={"file": ("m.csv", _csv(), "text/csv")})
    assert r.status_code == 200 and r.json()["loaded"] == 3, r.text
    assert client.post(f"{API}/methodologies/{m['id']}/publish", headers=owner.headers).status_code == 200

    ref = f"AUD-{uuid.uuid4().hex[:6]}"
    e = client.post(f"{API}/organizations/{org['id']}/engagements", headers=owner.headers, json={
        "company_id": cid, "engagement_type": "ic_assessment", "reference": ref, "name": "Audit test",
        "methodology_version_id": m["id"]}).json()
    eid = e["id"]
    assert e["my_role"] == "manager" and e["capabilities"] == ["confirm_independence"]
    base = f"{API}/engagements/{eid}"
    assert client.get(f"{base}/workpapers", headers=owner.headers).status_code == 403
    client.post(f"{base}/independence", headers=owner.headers, json={"statement": "Je suis indépendant (test)."})
    for u, role in ((partner, "partner"), (staff, "staff"), (senior, "in_charge")):
        assert client.post(f"{base}/members", headers=owner.headers, json={"user_id": str(u.id), "role": role}).status_code == 201
        client.post(f"{base}/independence", headers=u.headers, json={"statement": "Je suis indépendant (test)."})
    assert client.post(f"{base}/status", headers=owner.headers, json={"to": "fieldwork"}).status_code == 200

    r = client.post(f"{base}/risks", headers=senior.headers, json={"code": "R1", "title": "Risque test", "assertion_codes": ["EX"],
                                                                    "likelihood": 3, "impact": 1})
    assert r.status_code == 422                      # hors grille
    risk = client.post(f"{base}/risks", headers=senior.headers, json={"code": "R1", "title": "Risque test",
                                                                       "assertion_codes": ["EX"], "likelihood": 2, "impact": 2}).json()
    assert risk["score"] == 4 and risk["scale_significant"] is True
    pg = client.post(f"{base}/programs", headers=senior.headers, json={"code": "P1", "title": "Programme test"}).json()
    r = client.post(f"{base}/procedures/from-templates", headers=senior.headers,
                    json={"program_id": pg["id"], "template_codes": ["T1"]})
    assert r.json()["created"] == ["T1"]
    proc = client.get(f"{base}/programs", headers=staff.headers).json()[0]["procedures"][0]
    client.patch(f"{base}/procedures/{proc['id']}", headers=senior.headers, json={
        **{k: proc[k] for k in ("program_id", "code", "title", "objective", "nature", "steps", "assertion_codes")},
        "status": "done", "risk_ids": [risk["id"]]})

    wp = client.post(f"{base}/workpapers", headers=staff.headers, json={
        "reference": "A-1", "title": "Feuille test", "procedure_id": proc["id"], "work_performed": "Travaux (test)",
        "conclusion": "Conclusion (test)"}).json()
    ev = client.post(f"{base}/evidence", headers=staff.headers, files={"file": ("piece.pdf", b"%PDF-1.7\n%test", "application/pdf")},
                     data={"title": "Pièce justificative (test)"})
    assert ev.status_code == 201, ev.text
    assert client.post(f"{base}/evidence/{ev.json()['id']}/links", headers=staff.headers,
                       json={"object_type": "workpaper", "object_id": wp["id"]}).status_code == 201
    bad = client.post(f"{base}/evidence", headers=staff.headers, files={"file": ("x.exe", b"MZ", "application/octet-stream")},
                      data={"title": "x"})
    assert bad.status_code == 422

    wps = f"{base}/workpapers/{wp['id']}"
    assert client.post(f"{wps}/sign", headers=staff.headers, json={"role": "preparer"}).json()["status"] == "prepared"
    assert client.post(f"{wps}/sign", headers=staff.headers, json={"role": "reviewer"}).status_code == 403
    assert client.post(f"{wps}/sign", headers=senior.headers, json={"role": "reviewer"}).json()["status"] == "reviewed"
    note = client.post(f"{base}/review-notes", headers=owner.headers,
                       json={"object_type": "workpaper", "object_id": wp["id"], "body": "Compléter (test)."}).json()
    r = client.post(f"{wps}/sign", headers=owner.headers, json={"role": "approver"})
    assert r.status_code == 422 and "notes de revue" in r.json()["error"]["message"]
    client.post(f"{base}/review-notes/{note['id']}", headers=staff.headers, json={"action": "answer", "response": "Fait (test)."})
    client.post(f"{base}/review-notes/{note['id']}", headers=owner.headers, json={"action": "close"})
    assert client.post(f"{wps}/sign", headers=owner.headers, json={"role": "approver"}).json()["status"] == "approved"

    for to in ("review", "reporting"):
        assert client.post(f"{base}/status", headers=owner.headers, json={"to": to}).status_code == 200
    sup = client.get(f"{base}/supervision", headers=partner.headers).json()
    assert {c["code"]: c["passed"] for c in sup["issuance_checks"]}["PARTNER_APPROVAL"] is False
    assert client.post(f"{base}/status", headers=partner.headers, json={"to": "issued"}).status_code == 409
    client.post(f"{base}/sign", headers=partner.headers, json={"role": "approver"})
    r = client.post(f"{base}/status", headers=partner.headers, json={"to": "issued"})
    assert r.status_code == 200 and r.json()["status"] == "issued", r.text
    assert client.patch(wps, headers=staff.headers, json={"reference": "A-1", "title": "modifiée"}).status_code == 403
