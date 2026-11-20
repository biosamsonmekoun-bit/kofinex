"""Phase 3 du correctif du contrôle de gestion, par l'API : budget relié au plan comptable.

Entreprise alimentée par import (pas de plan comptable ouvert) : le plan de référence est le référentiel publié.
Sélection d'un compte avec intitulé, classe et parent repris automatiquement ; rubriques (plusieurs comptes, ou aucun) ;
mode de prévision ; douze mois et total annuel calculés par le serveur ; refus explicites (compte absent, compte de
bilan hors budget d'investissement) ; import contrôlé dès la simulation ; nouvelle version (type, rubriques, modes) ;
prévision par hypothèses (mode « calculé ») ; budget d'investissement hors tableau de bord budgétaire. Données FICTIVES."""

from __future__ import annotations

from decimal import Decimal

from tests.integration.test_ai_api import _analysis

API = "/api/v1"


def test_budget_relie_au_plan(client, make_user):
    owner, org, cid, fy, _a = _analysis(client, make_user)
    C, H = f"{API}/companies/{cid}", owner.headers

    kinds = {k["key"]: k for k in client.get(f"{C}/budget-kinds", headers=H).json()}
    assert kinds["investments"]["allowed_prefixes"] == ["2", "16"] and kinds["general"]["status"] == "to_validate"

    # comptes sélectionnables : référentiel publié (pas de plan ouvert), intitulé, classe et parent repris
    acc = client.get(f"{C}/fiscal-years/{fy['id']}/budget-accounts", headers=H, params={"kind": "general"}).json()
    assert acc["source"] == "framework"
    items = {a["account_number"]: a for a in acc["items"]}
    assert items["601"]["label"] == "Compte test 601" and items["601"]["account_class"] == 6 and items["601"]["parent"] == "6"
    assert "411" not in items and "101" not in items              # comptes de bilan exclus d'un budget de résultat
    found = client.get(f"{C}/fiscal-years/{fy['id']}/budget-accounts", headers=H, params={"q": "test 70"}).json()
    assert [a["account_number"] for a in found["items"]] == ["701"]            # recherche par intitulé
    found = client.get(f"{C}/fiscal-years/{fy['id']}/budget-accounts", headers=H, params={"q": "60"}).json()
    assert [a["account_number"] for a in found["items"]] == ["601"]            # recherche par numéro

    b = client.post(f"{C}/fiscal-years/{fy['id']}/budgets", headers=H, json={"name": "Budget relié"})
    assert b.status_code == 201 and b.json()["budget_kind"] == "general", b.text
    bid = b.json()["id"]

    # refus explicites
    r = client.put(f"{API}/companies/{cid}/budgets/{bid}/lines", headers=H,
                   json=[{"account_prefix": "609", "period": 0, "amount": "10"}])
    assert r.status_code == 422 and "absent du plan comptable de référence" in r.json()["error"]["message"], r.text
    r = client.put(f"{C}/budgets/{bid}/lines", headers=H, json=[{"account_prefix": "411", "period": 0, "amount": "10"}])
    assert r.status_code == 422 and "hors des racines autorisées" in r.json()["error"]["message"], r.text

    # saisie : intitulé repris du compte, rubriques (deux comptes ; une ligne sans compte), mois et mode de prévision
    months = [{"account_prefix": "601", "rubric": "Achats", "period": m, "amount": "1000.00"} for m in range(1, 13)]
    lines = [*months,
             {"account_prefix": "701", "rubric": "Chiffre d'affaires", "period": 0, "amount": "50000", "forecast_mode": "calculated"},
             {"rubric": "Achats", "label": "Provision pour aléas", "period": 0, "amount": "2500.50"}]
    r = client.put(f"{C}/budgets/{bid}/lines", headers=H, json=lines)
    assert r.status_code == 200, r.text
    g = {(x["rubric"], x["account_number"]): x for x in r.json()["grouped"]}
    achats = g[("Achats", "601")]
    assert achats["label"] == "Compte test 601" and achats["account_label"] == "Compte test 601" and achats["account_class"] == 6
    assert Decimal(achats["total"]) == Decimal("12000") and all(Decimal(m) == Decimal("1000") for m in achats["months"])
    assert Decimal(g[("Achats", None)]["total"]) == Decimal("2500.50") and g[("Achats", None)]["account_number"] is None
    assert g[("Chiffre d'affaires", "701")]["forecast_mode"] == "calculated"
    assert [x["rubric"] for x in r.json()["grouped"]][:2] == ["Achats", "Achats"]   # ordre de première apparition

    # un même compte dans deux rubriques : refusé (pas de doublon de compte)
    r = client.put(f"{C}/budgets/{bid}/lines", headers=H, json=[
        {"account_prefix": "601", "rubric": "A", "period": 0, "amount": "1"},
        {"account_prefix": "601", "rubric": "B", "period": 0, "amount": "1"}])
    assert r.status_code == 422 and "déjà rattaché à la rubrique" in r.json()["error"]["message"], r.text

    # import : compte invalide détecté dès la simulation
    csv = "compte;libelle;periode;montant\n601;Achats;0;100\n999;Inconnu;0;5\n".encode()
    r = client.post(f"{C}/budgets/{bid}/lines/import", headers=H, params={"dry_run": "true"},
                    files={"file": ("budget.csv", csv, "text/csv")})
    assert r.status_code == 200 and r.json()["imported"] is False, r.text
    assert any("999" in e and "absent du plan comptable de référence" in e for e in r.json()["errors"])

    # suivi : réalisé de la balance validée, budget de résultat
    t = client.get(f"{C}/budgets/{bid}/tracking", headers=H)
    assert t.status_code == 200 and t.json()["budget_kind"] == "general", t.text

    # nouvelle version : type, rubriques et modes copiés
    client.post(f"{C}/budgets/{bid}/transition", headers=H, json={"action": "submit"})
    nv = client.post(f"{C}/budgets/{bid}/new-version", headers=H)
    assert nv.status_code == 201, nv.text
    nv = client.get(f"{C}/budgets/{nv.json()['id']}", headers=H).json()
    assert nv["budget_kind"] == "general" and {x["rubric"] for x in nv["grouped"]} == {"Achats", "Chiffre d'affaires"}
    assert any(x["forecast_mode"] == "calculated" for x in nv["grouped"])

    # prévision par hypothèses : lignes en mode « calculé », comptes contrôlés
    pv = client.post(f"{C}/fiscal-years/{fy['id']}/budgets", headers=H, json={"name": "Prévision", "scenario": "forecast"}).json()
    r = client.post(f"{C}/budgets/{pv['id']}/project", headers=H, json={
        "source_fiscal_year_id": fy["id"], "items": [{"prefix": "601", "label": "Achats", "rate_pct": "10"}]})
    assert r.status_code == 200 and {ln["forecast_mode"] for ln in r.json()["lines"]} == {"calculated"}, r.text
    r = client.post(f"{C}/budgets/{pv['id']}/project", headers=H, json={
        "source_fiscal_year_id": fy["id"], "items": [{"prefix": "411", "label": "Clients", "rate_pct": "10"}], "replace": True})
    assert r.status_code == 422, r.text

    # budget d'investissement : classe 2 et 16 seulement ; hors tableau de bord budgétaire
    inv = client.post(f"{C}/fiscal-years/{fy['id']}/budgets", headers=H, json={"name": "Investissements",
                                                                             "budget_kind": "investments"}).json()
    assert inv["budget_kind"] == "investments"
    r = client.put(f"{C}/budgets/{inv['id']}/lines", headers=H, json=[{"account_prefix": "601", "period": 0, "amount": "1"}])
    assert r.status_code == 422 and "hors des racines autorisées" in r.json()["error"]["message"], r.text
    assert client.get(f"{C}/fiscal-years/{fy['id']}/budget-accounts", headers=H,
                      params={"kind": "investments"}).json()["items"] == []       # aucun compte 2 ou 16 dans ce référentiel
    r = client.get(f"{C}/fiscal-years/{fy['id']}/steering/budget", headers=H, params={"budget_id": inv["id"]})
    assert r.status_code == 422 and "investissement" in r.json()["error"]["message"], r.text
    r = client.post(f"{C}/budgets/{inv['id']}/project", headers=H, json={
        "source_fiscal_year_id": fy["id"], "items": [{"prefix": "601", "label": "x", "rate_pct": "0"}]})
    assert r.status_code == 422 and "réservée aux budgets de charges et de produits" in r.json()["error"]["message"]
    assert client.post(f"{C}/fiscal-years/{fy['id']}/budgets", headers=H,
                       json={"name": "X", "budget_kind": "inconnu"}).status_code == 422
