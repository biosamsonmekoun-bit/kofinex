"""Reporting par l'API : rapport financier en PDF, Excel et Word sur une analyse terminée (même empreinte de données
quel que soit le format), document figé et lien de téléchargement, modèle publié appliqué, contrôles d'accès, refus
d'exporter un rapport d'audit non émis. Données FICTIVES."""

from __future__ import annotations

import uuid

from tests.integration.test_ai_api import _analysis

API = "/api/v1"


def test_reporting_flow(client, make_user):
    owner, org, cid, fy, a = _analysis(client, make_user)
    outsider = make_user("rp-out")
    D = f"{API}/companies/{cid}/documents"

    # rapport financier dans les trois formats
    out = {}
    for fmt in ("pdf", "xlsx", "docx"):
        r = client.post(
            D, headers=owner.headers, json={"document_type": "financial_report", "format": fmt, "fiscal_year_id": fy["id"]}
        )
        assert r.status_code == 201, r.text
        out[fmt] = r.json()
        assert out[fmt]["status"] == "ready" and len(out[fmt]["sha256"]) == 64 and out[fmt]["contains_ai_drafts"] is False
    assert len({o["data_sha256"] for o in out.values()}) == 1  # mêmes données, trois formats
    assert len({o["sha256"] for o in out.values()}) == 3
    doc = client.get(f"{API}/documents/{out['pdf']['id']}", headers=owner.headers).json()
    assert doc["content_snapshot"]["title"].startswith("Rapport financier") and doc["source_refs"][0]["type"] == "analysis"
    dl = client.get(f"{API}/documents/{out['pdf']['id']}/download", headers=owner.headers).json()
    assert dl["url"] and dl["sha256"] == out["pdf"]["sha256"]
    assert len(client.get(D, headers=owner.headers).json()) == 3
    assert client.get(f"{API}/documents/{out['pdf']['id']}", headers=outsider.headers).status_code == 404

    # sans analyse terminée : refus
    fy2 = client.post(
        f"{API}/companies/{cid}/fiscal-years",
        headers=owner.headers,
        json={"label": "Vide", "start_date": "2999-01-01", "end_date": "2999-12-31"},
    ).json()
    r = client.post(
        D, headers=owner.headers, json={"document_type": "financial_report", "format": "pdf", "fiscal_year_id": fy2["id"]}
    )
    assert r.status_code == 422

    # modèle : brouillon refusé, version publiée appliquée puis figée
    T = f"{API}/organizations/{org['id']}/report-templates"
    t = client.post(
        T,
        headers=owner.headers,
        json={
            "name": "Rapport annuel (test)",
            "document_type": "financial_report",
            "sections": ["statements", "indicators"],
            "title": "Rapport annuel (test)",
            "intro": "Mot de la direction (test).",
            "primary_color": "#2563EB",
        },
    ).json()
    assert (
        client.post(
            T, headers=owner.headers, json={"name": "x", "document_type": "financial_report", "sections": ["inventee"]}
        ).status_code
        == 422
    )
    r = client.post(
        D,
        headers=owner.headers,
        json={"document_type": "financial_report", "format": "pdf", "fiscal_year_id": fy["id"], "template_id": t["id"]},
    )
    assert r.status_code == 422  # brouillon
    assert client.post(f"{T}/{t['id']}/publish", headers=owner.headers).json()["status"] == "published"
    r = client.post(
        D,
        headers=owner.headers,
        json={"document_type": "financial_report", "format": "docx", "fiscal_year_id": fy["id"], "template_id": t["id"]},
    ).json()
    assert r["title"] == "Rapport annuel (test)" and r["template_version"] == 1
    assert r["data_sha256"] != out["pdf"]["data_sha256"]  # sections et textes différents
    assert (
        client.patch(f"{T}/{t['id']}", headers=owner.headers, json={"name": "Modifié", "document_type": "financial_report"}).status_code
        == 409
    )
    v2 = client.post(f"{T}/{t['id']}/new-version", headers=owner.headers).json()
    assert v2["version"] == 2 and v2["status"] == "draft"

    # mission : rapport d'audit interne non émis
    e = client.post(
        f"{API}/organizations/{org['id']}/engagements",
        headers=owner.headers,
        json={
            "company_id": cid,
            "engagement_type": "internal_audit",
            "reference": f"IA-{uuid.uuid4().hex[:5]}",
            "name": "Audit (test)",
        },
    ).json()
    client.post(
        f"{API}/engagements/{e['id']}/independence", headers=owner.headers, json={"statement": "Je suis indépendant (test)."}
    )
    r = client.post(
        f"{API}/engagements/{e['id']}/documents",
        headers=owner.headers,
        json={"document_type": "internal_audit_report", "format": "pdf"},
    )
    assert r.status_code == 422, r.text
    r = client.post(
        f"{API}/engagements/{e['id']}/documents", headers=owner.headers, json={"document_type": "fa_summary", "format": "pdf"}
    )
    assert r.status_code == 422
    assert client.get(f"{API}/engagements/{e['id']}/documents", headers=outsider.headers).status_code in (403, 404)
