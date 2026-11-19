"""Tableau de bord par l'API : indicateurs issus de l'analyse terminée, charges et produits issus de la balance validée,
série mensuelle absente sans grand livre (état explicite), périodes de l'exercice, contrôle d'accès. Données FICTIVES."""

from __future__ import annotations

from tests.integration.test_ai_api import _analysis

API = "/api/v1"


def test_dashboard(client, make_user):
    owner, org, cid, fy, a = _analysis(client, make_user)
    url = f"{API}/companies/{cid}/fiscal-years/{fy['id']}/dashboard"
    r = client.get(url, headers=owner.headers)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["analysis"]["id"] == a["id"]
    assert d["kpis"]["revenue"]["code"] == "CA" and d["kpis"]["revenue"]["available"] in (True, False)
    assert [i["code"] for i in d["indicators"]] == [
        "MARGE_COMMERCIALE",
        "EBE",
        "RESULTAT_EXPLOITATION",
        "RESULTAT_NET",
        "CAF_ADDITIVE",
    ]
    assert d["breakdown_source"] == "trial_balance" and d["expenses"]["groups"]
    assert d["monthly"]["available"] is False and "grand livre" in d["monthly"]["reason"]
    assert [p["key"] for p in d["periods"][:3]] == ["year", "s1", "s2"]
    # une sous-période sans grand livre : pas de répartition inventée
    s1 = client.get(url, params={"period": "s1"}, headers=owner.headers).json()
    assert s1["expenses"] is None and "grand livre" in s1["breakdown_note"]
    # hors de l'organisation : refusé
    assert client.get(url, headers=make_user("db-out").headers).status_code in (403, 404)
