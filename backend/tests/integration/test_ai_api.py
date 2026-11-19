"""IA par l'API : indisponibilité sans configuration (aucune réponse simulée), activation par l'organisation,
assistant financier sur une analyse terminée avec contrôle des chiffres, commentaire relu, suggestions d'audit
acceptées ou rejetées, provenance des objets créés, accès. Le fournisseur est remplacé par un double de test : c'est
le seul endroit où une réponse du modèle est fabriquée. Données FICTIVES."""

from __future__ import annotations

import json
import uuid

import pytest

from app.engines.ai import provider
from app.services import ai as ai_svc
from tests.engines import fictitious_framework as ff
from tests.engines import sample_files as sf
from tests.integration.test_analysis_api import _csv, _upload
from tests.integration.test_imports_api import CHART_CSV

API = "/api/v1"
METHOD_CSV = "\n".join(
    [
        "type;code;libelle;parent;contenu;ordre",
        'cycle;ACH;Achats (test);;{"account_prefixes":["40"]};1',
        "assertion;EXH;Exhaustivité (test);;;2",
        'procedure_template;PT1;Revue des factures (test);;{"nature":"detail_test","objective":"Tester l\'exhaustivité","steps":["a"]};3',
        'finding_scale;CST;Constats (test);;{"levels":[{"code":"N1","label":"Majeur (test)","rank":1}]};4',
    ]
).encode()


def _context(messages) -> dict:
    last = messages[-1]["content"]
    return json.loads(last.split("CONTEXTE (données calculées par KOFINEX) :\n", 1)[1].split("\n\nDEMANDE :", 1)[0])


def fake_complete(cfg, system, messages, transport=None):
    ctx = _context(messages)
    if "Tâche : proposer des risques" in system:
        body = {
            "suggestions": [
                {
                    "code": "R-IA-1",
                    "title": "Fractionnement des commandes",
                    "rationale": "Cartographie : risque R1 des achats",
                    "cycle_code": "ACH",
                    "assertion_codes": ["EXH"],
                    "sources": [],
                },
                {"code": "R-IA-2", "title": "Source inventée", "rationale": "x x x", "sources": ["F9999"]},
            ]
        }
        return provider.Completion(json.dumps(body), "modele-test", 100, 20)
    if "programmes types" in system:
        return provider.Completion(
            json.dumps(
                {"suggestions": [{"template_code": "PT1", "risk_codes": ["R-IA-1"], "rationale": "Répond au risque R-IA-1"}]}
            ),
            "modele-test",
            50,
            10,
        )
    f = ctx["facts"][0]
    return provider.Completion(f"{f['label']} : {f['value']} [{f['ref']}]. Hausse de 123 456 789.", "modele-test", 80, 15)


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setattr(ai_svc, "provider_config", lambda: provider.ProviderConfig("anthropic", "cle-test", "modele-test"))
    monkeypatch.setattr(ai_svc.provider, "complete", fake_complete)


def _analysis(client, make_user):
    admin = make_user("ai-admin")
    admin.make_platform_admin()
    year = 2850 + int(uuid.uuid4().int % 40)
    vid = client.post(
        f"{API}/frameworks/SYSCOHADA_REV/versions",
        headers=admin.headers,
        json={
            "version_label": f"TEST-AI-{year}",
            "effective_from": f"{year}-01-01",
            "effective_to": f"{year + 1}-01-01",
            "source_reference": "Référentiel FICTIF pour tests automatisés",
        },
    ).json()["id"]
    for kind, content in (
        ("chart", CHART_CSV),
        ("structure", _csv(ff.STRUCTURE)),
        ("mappings", _csv(ff.MAPPINGS)),
        ("concepts", _csv(ff.CONCEPT_ROWS)),
    ):
        _upload(client, admin, vid, kind, content)
    assert client.post(f"{API}/framework-versions/{vid}/publish", headers=admin.headers).status_code == 200
    owner = make_user("ai-own")
    org = client.post(f"{API}/organizations", json={"name": "Groupe IA (test)"}, headers=owner.headers).json()
    cid = client.post(
        f"{API}/organizations/{org['id']}/companies",
        headers=owner.headers,
        json={"name": "Société IA (test)", "framework_code": "SYSCOHADA_REV"},
    ).json()["id"]
    fy = client.post(
        f"{API}/companies/{cid}/fiscal-years",
        headers=owner.headers,
        json={"label": str(year), "start_date": f"{year}-01-01", "end_date": f"{year}-12-31"},
    ).json()
    job = client.post(
        f"{API}/companies/{cid}/imports",
        headers=owner.headers,
        files={"file": ("b.xlsx", sf.xlsx_two_level_header(), "application/octet-stream")},
        data={"fiscal_year_id": fy["id"]},
    ).json()
    client.post(
        f"{API}/companies/{cid}/imports/{job['id']}/configure",
        headers=owner.headers,
        json={"sheet_name": job["sheet_name"], "header_row": job["header_row"], "column_map": job["column_map"]},
    )
    client.post(f"{API}/companies/{cid}/imports/{job['id']}/confirm", headers=owner.headers, json={"acknowledge_warnings": True})
    a = client.post(f"{API}/companies/{cid}/fiscal-years/{fy['id']}/analyses", headers=owner.headers).json()
    return owner, org, cid, fy, a


def test_ai_unavailable_without_configuration(client, make_user, monkeypatch):
    monkeypatch.setattr(ai_svc, "provider_config", lambda: provider.ProviderConfig("none", "", ""))
    owner = make_user("ai-none")
    st = client.get(f"{API}/ai/status", headers=owner.headers).json()
    assert st["configured"] is False and st["reason"] and "cle" not in json.dumps(st)


def test_ai_flow(client, make_user, configured):
    owner, org, cid, fy, a = _analysis(client, make_user)
    manager, staff, auditee, outsider = (make_user(n) for n in ("ai-mgr", "ai-sta", "ai-aud", "ai-out"))
    for u in (manager, staff, auditee):
        client.post(f"{API}/organizations/{org['id']}/members", json={"email": u.email, "role": "member"}, headers=owner.headers)
    C = f"{API}/companies/{cid}/ai"

    # désactivée par défaut ; activation réservée aux administrateurs, motivée
    assert client.post(f"{C}/conversations", headers=owner.headers, json={"fiscal_year_id": fy["id"]}).status_code == 409
    S = f"{API}/organizations/{org['id']}/ai-settings"
    assert client.put(S, headers=staff.headers, json={"enabled": True, "allowed_uses": ["finance_assistant"]}).status_code == 403
    assert client.put(S, headers=owner.headers, json={"enabled": True, "allowed_uses": ["finance_assistant"]}).status_code == 400
    r = client.put(
        S,
        headers=owner.headers,
        json={
            "enabled": True,
            "acceptance_note": "Accord de la direction (test)",
            "allowed_uses": ["finance_assistant", "analysis_commentary", "audit_risks", "audit_procedures"],
        },
    )
    assert r.status_code == 200 and r.json()["enabled"] is True, r.text

    # assistant financier : contexte calculé conservé, chiffre non traçable signalé
    conv = client.post(f"{C}/conversations", headers=owner.headers, json={"fiscal_year_id": fy["id"]}).json()
    r = client.post(
        f"{C}/conversations/{conv['id']}/messages", headers=owner.headers, json={"content": "Commente la trésorerie."}
    )
    assert r.status_code == 201, r.text
    q, ans = r.json()
    assert q["role"] == "user" and ans["role"] == "assistant" and ans["context_snapshot"]["facts"]
    assert ans["validation"]["status"] == "warning" and ans["validation"]["untraceable"][0]["value"] == "123456789"
    assert ans["prompt_version"] == "KOFINEX-AI-1" and ans["model"] == "modele-test"
    assert client.get(f"{C}/conversations/{conv['id']}", headers=staff.headers).status_code == 404  # privée

    # commentaire d'analyse : brouillon, relu par un humain
    rep = client.post(
        f"{API}/companies/{cid}/analyses/{a['id']}/ai-reports", headers=owner.headers, json={"section": "cash"}
    ).json()
    assert rep["status"] == "draft" and rep["validation"]["status"] == "warning"
    R = f"{API}/companies/{cid}/ai-reports/{rep['id']}/review"
    assert client.post(R, headers=owner.headers, json={"decision": "rejected"}).status_code == 400
    assert client.post(R, headers=owner.headers, json={"decision": "reviewed", "note": "Relu"}).json()["status"] == "reviewed"

    # mission : suggestions de risques et de procédures
    m = client.post(
        f"{API}/methodologies",
        headers=owner.headers,
        json={
            "organization_id": org["id"],
            "kind": "audit",
            "name": "Méthode IA test",
            "version_label": "v1",
            "source_reference": "Méthodologie FICTIVE pour tests",
        },
    ).json()
    client.post(f"{API}/methodologies/{m['id']}/items", headers=owner.headers, files={"file": ("m.csv", METHOD_CSV, "text/csv")})
    client.post(f"{API}/methodologies/{m['id']}/publish", headers=owner.headers)
    e = client.post(
        f"{API}/organizations/{org['id']}/engagements",
        headers=owner.headers,
        json={
            "company_id": cid,
            "engagement_type": "internal_audit",
            "reference": f"IA-{uuid.uuid4().hex[:5]}",
            "name": "Audit (test)",
            "methodology_version_id": m["id"],
            "fiscal_year_id": fy["id"],
        },
    ).json()
    base = f"{API}/engagements/{e['id']}"
    for u, role in ((manager, "manager"), (staff, "staff"), (auditee, "auditee")):
        client.post(f"{base}/members", headers=owner.headers, json={"user_id": str(u.id), "role": role})
    for u in (owner, manager, staff):
        client.post(f"{base}/independence", headers=u.headers, json={"statement": "Je suis indépendant (test)."})
    G = f"{base}/ai/suggestions"
    assert client.post(G, headers=staff.headers, json={"kind": "engagement_risk"}).status_code == 403  # planification
    r = client.post(G, headers=manager.headers, json={"kind": "engagement_risk", "request": "Risques du cycle achats"})
    assert r.status_code == 201, r.text
    assert len(r.json()["created"]) == 1 and "F9999" in r.json()["discarded"][0]
    lst = client.get(G, headers=staff.headers).json()
    sug = lst["items"][0]
    assert sug["status"] == "pending" and sug["kind"] == "engagement_risk"
    assert next(k for k in lst["kinds"] if k["kind"] == "anomaly_explanation")["available"] is False  # usage non activé
    r = client.post(f"{G}/{sug['id']}/accept", headers=manager.headers, json={"edits": {"title": "Fractionnement (relu)"}})
    assert r.status_code == 200 and r.json()["created_object_type"] == "engagement_risks", r.text
    risk = next(x for x in client.get(f"{base}/risks", headers=staff.headers).json()["risks"] if x["code"] == "R-IA-1")
    assert risk["origin"] == "ai_suggestion" and risk["title"] == "Fractionnement (relu)" and risk["likelihood"] is None
    assert client.post(f"{G}/{sug['id']}/reject", headers=manager.headers, json={"note": "Revirement"}).status_code == 409

    pg = client.post(f"{base}/programs", headers=manager.headers, json={"code": "P1", "title": "Achats (test)"}).json()
    sid = client.post(G, headers=manager.headers, json={"kind": "procedure"}).json()["created"][0]
    assert client.post(f"{G}/{sid}/accept", headers=manager.headers, json={}).status_code == 422  # programme requis
    r = client.post(f"{G}/{sid}/accept", headers=manager.headers, json={"program_id": pg["id"]})
    assert r.status_code == 200, r.text
    proc = client.get(f"{base}/programs", headers=staff.headers).json()[0]["procedures"][0]
    assert (
        proc["code"] == "PT1"
        and proc["origin"] == "ai_suggestion"
        and proc["assigned_to"] is None
        and proc["status"] == "not_started"
    )

    sid = client.post(G, headers=manager.headers, json={"kind": "engagement_risk"}).json()["created"]
    assert sid == []  # R-IA-1 existe désormais : proposition écartée
    # accès
    assert client.get(G, headers=auditee.headers).status_code == 403
    assert client.get(G, headers=outsider.headers).status_code in (403, 404)
    assert client.get(f"{API}/organizations/{org['id']}/ai-settings", headers=outsider.headers).status_code in (403, 404)
