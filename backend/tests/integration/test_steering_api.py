"""Pilotage du contrôle de gestion par l'API (à exécuter en CI) — cas de test 2, 3 et 6 du cahier des charges :
écritures natives validées successives → indicateurs qui évoluent → extourne qui les corrige ; budget approuvé par un
autre utilisateur → réalisé tiré des écritures natives → écarts, alertes ; isolation et accès au détail de paie.
Le cas 1 (facture d'achat) attend le module Achats (lot 3B, étape C). Données FICTIVES."""

from __future__ import annotations

from tests.integration.test_ai_api import _analysis

API = "/api/v1"


def _post_entry(client, A, H, V, fy, journal, day, lines):
    e = client.post(f"{A}/entries", headers=H, json={"fiscal_year_id": fy["id"], "journal_id": journal, "entry_date": day, "label": "Op",
                                                     "lines": lines}).json()
    client.post(f"{A}/entries/{e['id']}/transition", headers=H, json={"action": "submit"})
    r = client.post(f"{A}/entries/{e['id']}/transition", headers=V, json={"action": "validate"})
    assert r.status_code == 200, r.text
    return e


def test_steering_cycle(client, make_user):
    owner, org, cid, fy, _a = _analysis(client, make_user)
    H, year = owner.headers, int(fy["start_date"][:4])
    A, S = f"{API}/companies/{cid}/accounting", f"{API}/companies/{cid}/fiscal-years/{fy['id']}/steering"
    val = make_user("st-val")
    client.post(f"{API}/organizations/{org['id']}/members", headers=H, json={"email": val.email, "role": "member"})
    client.post(f"{API}/companies/{cid}/members", headers=H, json={"user_id": str(val.id), "role": "accountant"})
    ctrl = make_user("st-ctrl")
    client.post(f"{API}/organizations/{org['id']}/members", headers=H, json={"email": ctrl.email, "role": "member"})
    client.post(f"{API}/companies/{cid}/members", headers=H, json={"user_id": str(ctrl.id), "role": "controller"})

    client.post(f"{A}/accounts/import-chart", headers=H, json={})
    od = client.post(f"{A}/journals", headers=H, json={"code": "OD", "label": "OD", "journal_type": "general"}).json()

    # ------------------------------------------------ cas 2 : actualisation successive
    wm0 = client.get(f"{S}/watermark", headers=H).json()
    e1 = _post_entry(client, A, H, val.headers, fy, od["id"], f"{year}-01-15",
                     [{"account_number": "601", "debit": "1000"}, {"account_number": "521", "credit": "1000"}])
    f1 = client.get(f"{S}/financial", headers=H, params={"source": "native"}).json()
    assert f1["source"] == "native" and f1["kpis"]["total_charges"] in ("1000.00", "1000")
    assert client.get(f"{S}/watermark", headers=H).json()["token"] != wm0["token"]
    _post_entry(client, A, H, val.headers, fy, od["id"], f"{year}-02-10",
                [{"account_number": "601", "debit": "500"}, {"account_number": "521", "credit": "500"}])
    f2 = client.get(f"{S}/financial", headers=H, params={"source": "native"}).json()
    assert float(f2["kpis"]["total_charges"]) == 1500
    m1 = client.get(f"{S}/financial", headers=H, params={"source": "native", "view": "month", "month": 1}).json()
    assert float(m1["kpis"]["total_charges"]) == 1000
    rv = client.post(f"{A}/entries/{e1['id']}/reverse", headers=H, json={"entry_date": f"{year}-02-28"}).json()
    client.post(f"{A}/entries/{rv['reversal_id']}/transition", headers=H, json={"action": "submit"})
    client.post(f"{A}/entries/{rv['reversal_id']}/transition", headers=val.headers, json={"action": "validate"})
    f3 = client.get(f"{S}/financial", headers=H, params={"source": "native"}).json()
    assert float(f3["kpis"]["total_charges"]) == 500                       # l'extourne corrige l'indicateur
    d = client.get(f"{S}/drilldown", headers=H, params={"source": "native", "kind": "total_charges"}).json()
    assert d["total_lines"] == 3 and all(x["entry_id"] for x in d["lines"])  # chaque montant renvoie à son écriture

    # ------------------------------------------------ cas 3 : budget approuvé par un autre utilisateur
    b = client.post(f"{API}/companies/{cid}/fiscal-years/{fy['id']}/budgets", headers=H, json={"name": "Budget pilotage"}).json()
    client.put(f"{API}/companies/{cid}/budgets/{b['id']}/lines", headers=H,
               json=[{"account_prefix": "601", "label": "Achats", "period": p, "amount": "100.00"} for p in range(1, 13)])
    client.post(f"{API}/companies/{cid}/budgets/{b['id']}/submit", headers=H)
    assert client.post(f"{API}/companies/{cid}/budgets/{b['id']}/approve", headers=ctrl.headers).status_code == 200
    bd = client.get(f"{S}/budget", headers=H, params={"source": "native", "as_of": f"{year}-02-28"}).json()
    k = bd["kpis"]["charges"]
    assert float(k["budget"]) == 1200 and float(k["actual"]) == 500 and float(k["variance"]) == -700
    assert any(a["code"] in ("overrun", "fast_consumption") for a in bd["alerts"])   # février : 500 pour 200 de budget
    assert len(bd["monthly"]["charges"]) == 12

    # ------------------------------------------------ seuils, cas 6 : sécurité
    assert client.put(f"{API}/companies/{cid}/management-alert-settings", headers=val.headers, json={
        "consumption_info_pct": "80", "overrun_warning_pct": "100", "overrun_critical_pct": "110", "pace_gap_points": "15",
        "under_execution_points": "25", "center_variance_pct": "10", "change_pct": "10", "concentration_pct": "30"}).status_code == 403
    assert client.get(f"{S}/drilldown", headers=ctrl.headers, params={"kind": "personnel"}).status_code == 403
    out = make_user("st-out")
    assert client.get(f"{S}/financial", headers=out.headers).status_code in (403, 404)


def _setup_views(client, make_user):
    """Référentiel FICTIF du test (`_analysis`) : CA = comptes 70, clients = 41, fournisseurs = 40, trésorerie = 5 ;
    il ne rattache pas les concepts AO / HAO (réserve attendue). Valeurs pré-vérifiées par
    `tests/engines/test_steering_fixture.py`."""
    owner, org, cid, fy, _a = _analysis(client, make_user)
    H, year = owner.headers, int(fy["start_date"][:4])
    A = f"{API}/companies/{cid}/accounting"
    val = make_user("sv-val")
    client.post(f"{API}/organizations/{org['id']}/members", headers=H, json={"email": val.email, "role": "member"})
    client.post(f"{API}/companies/{cid}/members", headers=H, json={"user_id": str(val.id), "role": "accountant"})
    client.post(f"{A}/accounts/import-chart", headers=H, json={})
    accs = {a["account_number"]: a for a in client.get(f"{A}/accounts", headers=H).json()["items"]}
    client.patch(f"{A}/accounts/{accs['411']['id']}", headers=H, json={"third_party_kind": "customer"})
    client.patch(f"{A}/accounts/{accs['401']['id']}", headers=H, json={"third_party_kind": "supplier"})
    c1 = client.post(f"{A}/third-parties", headers=H, json={"code": "C1", "name": "Client 1", "kind": "customer",
                                                           "collective_account_number": "411"}).json()
    f1 = client.post(f"{A}/third-parties", headers=H, json={"code": "F1", "name": "Fournisseur 1", "kind": "supplier",
                                                           "collective_account_number": "401"}).json()
    od = client.post(f"{A}/journals", headers=H, json={"code": "OD", "label": "OD", "journal_type": "general"}).json()
    client.post(f"{A}/journals", headers=H, json={"code": "BQ", "label": "Banque", "journal_type": "bank", "counterpart_account_number": "521"})
    for day, lines in (
        (f"{year}-01-10", [{"account_number": "411", "third_party_id": c1["id"], "debit": "1200"}, {"account_number": "701", "credit": "1200"}]),
        (f"{year}-02-05", [{"account_number": "601", "debit": "500"}, {"account_number": "401", "third_party_id": f1["id"], "credit": "500"}]),
        (f"{year}-03-03", [{"account_number": "521", "debit": "1000"}, {"account_number": "411", "third_party_id": c1["id"], "credit": "1000"}]),
        (f"{year}-03-20", [{"account_number": "401", "third_party_id": f1["id"], "debit": "500"}, {"account_number": "521", "credit": "500"}]),
    ):
        _post_entry(client, A, H, val.headers, fy, od["id"], day, lines)
    return owner, org, cid, fy, year, c1, H


def test_steering_views(client, make_user):
    """Cas 5 (mois, cumul, exercice, période incomplète ; comparaison sans exercice précédent), Top 10 des tiers (deux
    bases), trésorerie, masse salariale, analyse, détail d'un tiers, suivi budgétaire par source."""
    owner, org, cid, fy, year, c1, H = _setup_views(client, make_user)
    S = f"{API}/companies/{cid}/fiscal-years/{fy['id']}/steering"
    D = lambda v: float(v)  # noqa: E731 — comparaison de chaînes décimales

    y = client.get(S + "/financial", headers=H, params={"source": "native"}).json()
    assert D(y["kpis"]["total_charges"]) == 500 and D(y["kpis"]["total_produits"]) == 1200 and D(y["kpis"]["chiffre_affaires"]) == 1200
    assert y["comparison"]["available"] is False                                  # aucun exercice précédent
    assert any("resultat_activites_ordinaires" in r for r in y["reliability"]["reserves"])
    assert [(i["label"], D(i["amount"])) for i in y["tops"]["clients"]["items"]] == [("C1 · Client 1", 1200)]
    assert len(y["monthly"]) == 12
    inv = client.get(S + "/financial", headers=H, params={"source": "native", "partner_basis": "invoiced"}).json()
    assert D(inv["tops"]["fournisseurs"]["items"][0]["amount"]) == 500 and inv["tops"]["fournisseurs"]["basis"] == "invoiced"
    feb = client.get(S + "/financial", headers=H, params={"source": "native", "view": "month", "month": 2}).json()
    assert D(feb["kpis"]["total_charges"]) == 500 and D(feb["kpis"]["total_produits"]) == 0
    cum = client.get(S + "/financial", headers=H, params={"source": "native", "view": "cumulative", "month": 2}).json()
    assert D(cum["kpis"]["total_produits"]) == 1200 and cum["period"]["from"] == f"{year}-01-01"
    part = client.get(S + "/financial", headers=H, params={"source": "native", "view": "custom", "date_from": f"{year}-01-01",
                                                           "date_to": f"{year}-01-15"}).json()
    assert D(part["kpis"]["total_produits"]) == 1200 and D(part["kpis"]["total_charges"]) == 0
    assert client.get(S + "/financial", headers=H, params={"view": "month"}).status_code == 422   # mois manquant

    t = client.get(S + "/treasury", headers=H, params={"source": "native"}).json()
    assert (D(t["receipts"]), D(t["payments"]), D(t["closing"]), t["check"]) == (1000, 500, 500, True)
    assert t["accounts"][0]["kind"] == "bank" and "bank" in t["by_kind"]       # d'après le journal de banque, mouvements en OD
    p = client.get(S + "/payroll", headers=H, params={"source": "native"}).json()
    assert p["available"] and D(p["total"]) == 0 and p["individual"]["available"] is False
    a = client.get(S + "/analysis", headers=H, params={"source": "native"}).json()
    assert a["available"] and any(i["indicator"] == "qualite" for i in a["items"])
    d = client.get(S + "/drilldown", headers=H, params={"source": "native", "kind": "partner", "key": c1["id"]}).json()
    assert d["total_lines"] == 4                                                  # facture et règlement de C1
    assert client.get(S + "/drilldown", headers=H, params={"kind": "inconnu"}).status_code == 422

    b = client.post(f"{API}/companies/{cid}/fiscal-years/{fy['id']}/budgets", headers=H, json={"name": "B"}).json()
    client.put(f"{API}/companies/{cid}/budgets/{b['id']}/lines", headers=H, json=[{"account_prefix": "601", "label": "Achats", "period": 0, "amount": "600.00"}])
    tr = client.get(f"{API}/companies/{cid}/budgets/{b['id']}/tracking", headers=H, params={"source": "native"}).json()
    assert tr["source"] == "native" and D(tr["rows"][0]["actual"]) == 500
    legacy = client.get(f"{API}/companies/{cid}/budgets/{b['id']}/tracking", headers=H).json()
    assert legacy["source"] == "trial_balance"                                    # sans paramètre : comportement du lot 5


def test_budget_import_and_thresholds(client, make_user):
    owner, org, cid, fy, _a = _analysis(client, make_user)
    H = owner.headers
    b = client.post(f"{API}/companies/{cid}/fiscal-years/{fy['id']}/budgets", headers=H, json={"name": "Import"}).json()
    url = f"{API}/companies/{cid}/budgets/{b['id']}/lines/import"
    good = "compte;libelle;M1;M2\n601;Achats;100;200\n701;Ventes;1000;1000\n".encode()
    r = client.post(url, headers=H, params={"dry_run": "true"}, files={"file": ("budget.csv", good, "text/csv")}).json()
    assert r["imported"] is False and r["errors"] == [] and r["lines"] == 4
    assert client.get(f"{API}/companies/{cid}/budgets/{b['id']}", headers=H).json().get("lines") in ([], None)
    r = client.post(url, headers=H, files={"file": ("budget.csv", good, "text/csv")}).json()
    assert r["imported"] is True and float(r["total"]) == 2300
    bad = "compte;centre;libelle;periode;montant\n601;XX;Achats;1;10\n6Z1;;Mauvais;1;10\n".encode()
    r = client.post(url, headers=H, files={"file": ("bad.csv", bad, "text/csv")}).json()
    assert r["imported"] is False and len(r["errors"]) == 2                       # centre inconnu, racine non numérique
    assert client.post(url, headers=H, files={"file": ("x.pdf", b"%PDF-1.4", "application/pdf")}).status_code == 422
    client.post(f"{API}/companies/{cid}/budgets/{b['id']}/submit", headers=H)
    assert client.post(url, headers=H, files={"file": ("budget.csv", good, "text/csv")}).status_code in (409, 422)   # plus en brouillon

    ctrl = make_user("bi-ctrl")
    client.post(f"{API}/organizations/{org['id']}/members", headers=H, json={"email": ctrl.email, "role": "member"})
    client.post(f"{API}/companies/{cid}/members", headers=H, json={"user_id": str(ctrl.id), "role": "controller"})
    T = f"{API}/companies/{cid}/management-alert-settings"
    assert client.get(T, headers=H).json()["customized"] is False
    body = {"consumption_info_pct": "70", "overrun_warning_pct": "100", "overrun_critical_pct": "120", "pace_gap_points": "10",
            "under_execution_points": "20", "center_variance_pct": "5", "change_pct": "15", "concentration_pct": "40"}
    assert client.put(T, headers=ctrl.headers, json={**body, "overrun_critical_pct": "90"}).status_code == 422   # incohérent
    r = client.put(T, headers=ctrl.headers, json=body).json()
    assert r["customized"] is True and float(r["overrun_critical_pct"]) == 120
