"""Contrôle interne par l'API : domaine, processus, risque, contrôle, association, programme, exécution, test,
preuve, évaluation, déficience, recommandation, plan de remédiation, suivi et vérification, clôture, tableau de bord,
rapports. Méthodologie et données FICTIVES."""

from __future__ import annotations

import uuid

API = "/api/v1"
METHOD_CSV = "\n".join([
    "type;code;libelle;parent;contenu;ordre",
    'risk_scale;GRILLE;Grille (test);;{"likelihood":[{"score":1,"label":"Faible"},{"score":2,"label":"Forte"}],'
    '"impact":[{"score":1,"label":"Faible"},{"score":2,"label":"Fort"}]};1',
    'control_level_scale;NIV;Maîtrise (test);;{"levels":[{"code":"M1","label":"Maîtrisé (test)","rank":1},'
    '{"code":"M2","label":"Partiel (test)","rank":2}]};2',
    'deficiency_scale;DEF;Déficiences (test);;{"levels":[{"code":"D1","label":"Majeure (test)","rank":1}]};3',
    'finding_scale;CST;Constats (test);;{"levels":[{"code":"N1","label":"Majeur (test)","rank":1}]};4',
    "ic_component;CMP;Composante (test);;;5",
    "ic_principle;PR1;Principe (test);CMP;;6",
]).encode()


def test_internal_control_flow(client, make_user):
    owner, icm, dom, perf, sup, manager, staff, auditee, outsider = (make_user(n) for n in (
        "ic-own", "ic-man", "ic-dom", "ic-perf", "ic-sup", "ic-mgr", "ic-sta", "ic-aud", "ic-out"))
    org = client.post(f"{API}/organizations", json={"name": "Groupe CI (test)"}, headers=owner.headers).json()
    for u in (icm, dom, perf, sup, manager, staff, auditee):
        client.post(f"{API}/organizations/{org['id']}/members", json={"email": u.email, "role": "member"}, headers=owner.headers)
    cid = client.post(f"{API}/organizations/{org['id']}/companies", headers=owner.headers,
                      json={"name": "Filiale CI (test)", "framework_code": "SYSCOHADA"}).json()["id"]
    C = f"{API}/companies/{cid}/ic"
    m = client.post(f"{API}/methodologies", headers=owner.headers, json={
        "organization_id": org["id"], "kind": "internal_control", "name": "Cadre CI test", "version_label": "v1",
        "source_reference": "Référentiel FICTIF pour tests", "framework_category": "internal_methodology"}).json()
    r = client.post(f"{API}/methodologies/{m['id']}/items", headers=owner.headers, files={"file": ("m.csv", METHOD_CSV, "text/csv")})
    assert r.json()["loaded"] == 6, r.text
    assert client.post(f"{API}/methodologies/{m['id']}/publish", headers=owner.headers).status_code == 200

    # rôles ; isolation
    assert client.get(f"{C}/access", headers=outsider.headers).status_code == 404
    for u, role in ((icm, "ic_manager"), (perf, "control_performer"), (sup, "supervisor")):
        assert client.post(f"{C}/members", headers=owner.headers, json={"user_id": str(u.id), "role": role}).status_code == 201
    assert client.get(f"{C}/access", headers=icm.headers).json()["is_admin"] is True

    # domaine (modèle) et processus
    assert client.post(f"{C}/domains/from-templates", headers=dom.headers, json={"codes": ["ACH"]}).status_code == 404
    r = client.post(f"{C}/domains/from-templates", headers=icm.headers, json={"codes": ["ACH"], "with_processes": True})
    assert r.status_code == 201 and r.json()["created"][0]["processes"] == 12, r.text
    domain = next(d for d in client.get(f"{C}/domains", headers=icm.headers).json() if d["code"] == "ACH")
    client.post(f"{C}/members", headers=icm.headers, json={"user_id": str(dom.id), "role": "domain_owner", "domain_id": domain["id"]})
    proc = client.post(f"{C}/processes", headers=dom.headers, json={"code": "ACH-X", "name": "Commandes urgentes (test)",
                                                                   "domain_id": domain["id"]}).json()
    assert proc["domain_id"] == domain["id"]

    # risque et contrôle
    assert client.post(f"{C}/risks", headers=dom.headers, json={"code": "R1", "title": "x", "process_id": proc["id"],
                                                             "scale_version_id": m["id"], "inherent_likelihood": 3,
                                                             "inherent_impact": 1}).status_code == 422
    risk = client.post(f"{C}/risks", headers=dom.headers, json={
        "code": "R1", "title": "Commande non autorisée (test)", "process_id": proc["id"], "causes": "Délégation absente",
        "consequences": "Engagement non maîtrisé", "scale_version_id": m["id"], "inherent_likelihood": 2, "inherent_impact": 2,
        "control_level_code": "M2"}).json()
    assert risk["inherent_score"] == 4 and risk["control_level_label"] == "Partiel (test)"
    assert client.post(f"{C}/controls", headers=dom.headers, json={"code": "C1", "title": "x", "owner_name": "DA",
                                                                "process_id": proc["id"]}).status_code == 422
    ctl = client.post(f"{C}/controls", headers=dom.headers, json={
        "code": "C1", "title": "Approbation des commandes (test)", "owner_name": "Directeur des achats", "process_id": proc["id"],
        "performer_user_id": str(perf.id), "supervisor_user_id": str(sup.id), "frequency": "monthly", "nature": "preventive",
        "automation": "manual", "is_key": True}).json()
    assert ctl["conclusion"] == "not_tested"
    assert client.post(f"{C}/controls/{ctl['id']}/risks", headers=dom.headers, json={"risk_id": risk["id"]}).status_code == 201
    mx = client.get(f"{C}/matrix", headers=icm.headers).json()
    assert any(r["control_code"] == "C1" and r["risk_code"] == "R1" for r in mx["rows"])

    # exécutions supervisées
    x = client.post(f"{C}/controls/{ctl['id']}/executions", headers=perf.headers,
                    data={"occurrence_label": "Revue de janvier (test)", "occurrence_date": "2026-01-31", "outcome": "performed"},
                    files={"file": ("bc.pdf", b"%PDF-1.7\n%test", "application/pdf")})
    assert x.status_code == 201 and len(x.json()["evidence_sha256"]) == 64, x.text
    xid = x.json()["id"]
    assert client.post(f"{C}/executions/{xid}/supervise", headers=perf.headers, json={"decision": "approved"}).status_code == 403
    assert client.post(f"{C}/executions/{xid}/supervise", headers=sup.headers, json={"decision": "approved"}).status_code == 200

    # mission d'évaluation, programme, test
    e = client.post(f"{API}/organizations/{org['id']}/engagements", headers=icm.headers, json={
        "company_id": cid, "engagement_type": "ic_assessment", "reference": f"CI-{uuid.uuid4().hex[:5]}",
        "name": "Évaluation 2026 (test)", "methodology_version_id": m["id"], "period_start": "2026-01-01",
        "period_end": "2026-06-30"}).json()
    base = f"{API}/engagements/{e['id']}"
    for u, role in ((manager, "manager"), (staff, "staff"), (auditee, "auditee")):
        client.post(f"{base}/members", headers=icm.headers, json={"user_id": str(u.id), "role": role})
    for u in (icm, manager, staff):
        client.post(f"{base}/independence", headers=u.headers, json={"statement": "Je suis indépendant (test)."})
    r = client.post(f"{base}/ic/program", headers=manager.headers, json={
        "code": "PRG", "title": "Achats (test)", "control_ids": [ctl["id"]], "test_types": ["operating"],
        "period_start": "2026-01-01", "period_end": "2026-06-30"})
    assert r.status_code == 201 and r.json()["tests"] == 1, r.text
    test = client.get(f"{base}/ic/tests", headers=staff.headers).json()[0]
    T = f"{base}/ic/tests/{test['id']}"
    assert client.post(f"{T}/select", headers=staff.headers, json={"source": "executions", "method": "random"}).status_code == 422
    r = client.post(f"{T}/select", headers=staff.headers, json={"source": "executions", "method": "all"})
    assert r.status_code == 200 and len(r.json()["items"]) == 1 and r.json()["population_size"] == 1, r.text
    item = r.json()["items"][0]
    assert client.patch(f"{base}/ic/test-items/{item['id']}", headers=staff.headers, json={"result": "compliant"}).status_code == 200
    answers = {k: {"answer": "yes"} for k in ("performed", "right_person", "right_frequency", "evidence_produced", "supervised",
                                              "anomalies_handled")}
    client.patch(T, headers=staff.headers, json={"reference": test["reference"], "test_type": "operating",
                                                 "test_methods": ["inspection"], "test_procedure": "Inspecter les revues",
                                                 "period_start": "2026-01-01", "period_end": "2026-06-30",
                                                 "tolerable_exceptions": 0, "operating_answers": answers,
                                                 "conclusion": "effective", "conclusion_rationale": "Revue conforme (test)"})
    assert client.post(f"{T}/status", headers=staff.headers, json={"action": "prepare"}).status_code == 422   # sans preuve
    ev = client.post(f"{base}/evidence", headers=staff.headers, files={"file": ("piece.pdf", b"%PDF-1.7\n%t", "application/pdf")},
                     data={"title": "Bon signé (test)"}).json()
    assert client.post(f"{base}/evidence/{ev['id']}/links", headers=staff.headers,
                       json={"object_type": "control_test_item", "object_id": item["id"]}).status_code == 201
    assert client.post(f"{T}/status", headers=staff.headers, json={"action": "prepare"}).status_code == 200
    assert client.post(f"{T}/status", headers=staff.headers, json={"action": "review"}).status_code == 403
    assert client.post(f"{T}/status", headers=manager.headers, json={"action": "review"}).json()["status"] == "reviewed"
    assert client.get(f"{C}/controls/{ctl['id']}", headers=dom.headers).json()["conclusion"] == "effective"

    # évaluation
    a = client.post(f"{base}/ic/assessments", headers=staff.headers, json={
        "reference": "EV-1", "scope_type": "domain", "domain_id": domain["id"], "as_of_date": "2026-06-30"}).json()
    assert a["preview"]["effective"] == 1
    client.patch(f"{base}/ic/assessments/{a['id']}", headers=staff.headers, json={
        "reference": "EV-1", "scope_type": "domain", "domain_id": domain["id"], "as_of_date": "2026-06-30", "rating_code": "M1",
        "conclusion": "Domaine maîtrisé sur le périmètre testé (test)"})
    assert client.post(f"{base}/ic/assessments/{a['id']}/status", headers=staff.headers, json={"action": "submit"}).status_code == 200
    r = client.post(f"{base}/ic/assessments/{a['id']}/status", headers=manager.headers, json={"action": "approve"})
    assert r.status_code == 200 and r.json()["status"] == "approved" and r.json()["basis"]["rule"] == "IC-SYNTH-1", r.text

    # déficience, recommandation, plan de remédiation, suivi, vérification, clôture
    fin = {"reference": "D1", "title": "Commandes urgentes non approuvées (test)", "condition": "2 commandes sans visa",
           "criteria": "Délégation de signature", "kind": "ic_deficiency", "control_id": ctl["id"], "risk_id": risk["id"],
           "rating_code": "D1"}
    assert client.post(f"{base}/findings", headers=staff.headers, json={**fin, "control_id": None}).status_code == 422
    fid = client.post(f"{base}/findings", headers=staff.headers, json=fin).json()["findings"][0]["id"]
    rec = client.post(f"{base}/findings/{fid}/recommendations", headers=staff.headers,
                      json={"reference": "REC1", "text": "Étendre la délégation (test)"}).json()["findings"][0]["recommendations"][0]
    assert client.post(f"{base}/findings/{fid}/status", headers=manager.headers, json={"action": "validate"}).status_code == 200
    assert client.post(f"{base}/findings/{fid}/status", headers=manager.headers, json={"action": "communicate"}).status_code == 200
    client.post(f"{base}/findings/{fid}/response", headers=auditee.headers, json={"management_response": "Accord (test)"})
    ap = client.post(f"{base}/recommendations/{rec['id']}/action-plans", headers=auditee.headers, json={
        "description": "Note de délégation (test)", "owner_name": "DAF", "due_date": "2026-12-31"}).json()
    ap = ap["findings"][0]["recommendations"][0]["action_plans"][0]
    assert client.post(f"{base}/findings/{fid}/status", headers=manager.headers,
                       json={"action": "close", "reason": "Clôture"}).status_code == 422
    client.post(f"{base}/action-plans/{ap['id']}/updates", headers=auditee.headers, json={"status": "implemented", "comment": "Signée"})
    client.post(f"{base}/action-plans/{ap['id']}/updates", headers=manager.headers, json={"status": "verified", "comment": "Vue"})
    deficiencies = client.get(f"{C}/deficiencies", headers=icm.headers).json()
    assert deficiencies[0]["stage"] == "verification"
    assert client.post(f"{base}/findings/{fid}/status", headers=manager.headers,
                       json={"action": "close", "reason": "Remédiation vérifiée (test)"}).status_code == 200
    assert client.get(f"{C}/deficiencies", headers=icm.headers).json()[0]["stage"] == "closed"

    # pilotage
    dash = client.get(f"{C}/dashboard", headers=icm.headers).json()
    assert dash["controls_existing"] == 1 and dash["effective"] == 1 and dash["effective_rate"] == 100.0
    assert dash["domains_assessed"] == 1 and dash["action_plans"] == 1
    rep = client.get(f"{C}/reports/matrix", headers=icm.headers).json()
    assert rep["sections"][0]["rows"] and rep["sources"]["reviewed_tests"] == 1
    assert client.get(f"{C}/reports/deficiencies/deficiencies.csv", headers=icm.headers).status_code == 200
    assert client.get(f"{C}/controls", headers=outsider.headers).status_code == 404
