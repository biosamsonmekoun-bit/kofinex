"""Phase 2 du correctif du contrôle de gestion, par l'API : plan comptable (principal, divisionnaire), plan tiers
(auxiliaire alphanumérique rattaché à un collectif, obligatoire), recherche, mise en sommeil, suppression d'un compte
utilisé refusée, balance générale et auxiliaire avec sous-totaux sans double comptage. Données FICTIVES."""

from __future__ import annotations

from decimal import Decimal

from tests.integration.test_ai_api import _analysis

API = "/api/v1"


def _post_validated(client, A, H, validator, fy, journal, date, label, lines):
    e = client.post(f"{A}/entries", headers=H, json={"fiscal_year_id": fy["id"], "journal_id": journal, "entry_date": date,
                                                       "label": label, "lines": lines})
    assert e.status_code == 201, e.text
    e = e.json()
    assert client.post(f"{A}/entries/{e['id']}/transition", headers=H, json={"action": "submit"}).status_code == 200
    r = client.post(f"{A}/entries/{e['id']}/transition", headers=validator.headers, json={"action": "validate"})
    assert r.status_code == 200, r.text


def test_plan_tiers_et_balance_hierarchique(client, make_user):
    owner, org, cid, fy, _a = _analysis(client, make_user)
    A, H = f"{API}/companies/{cid}/accounting", owner.headers
    year = int(fy["start_date"][:4])
    validator = make_user("pt-val")
    client.post(f"{API}/organizations/{org['id']}/members", headers=H, json={"email": validator.email, "role": "member"})
    client.post(f"{API}/companies/{cid}/members", headers=H, json={"user_id": str(validator.id), "role": "accountant"})
    assert client.post(f"{A}/accounts/import-chart", headers=H, json={}).status_code == 200

    # plan comptable : principal 4010000 et divisionnaire 4011000 (collectifs fournisseurs), sous le 401 du référentiel
    for num, label in (("4010000", "Fournisseurs"), ("4011000", "Fournisseurs – divisionnaire 4011")):
        r = client.post(f"{A}/accounts", headers=H, json={"account_number": num, "label": label, "requires_third_party": True,
                                                            "third_party_kind": "supplier"})
        assert r.status_code == 201, r.text
    r = client.post(f"{A}/accounts", headers=H, json={"account_number": "4111000", "label": "Clients – divisionnaire",
                                                        "requires_third_party": True, "third_party_kind": "customer"})
    assert r.status_code == 201, r.text
    # un auxiliaire alphanumérique n'est pas un compte du plan (il est un tiers)
    assert client.post(f"{A}/accounts", headers=H, json={"account_number": "4011TOY", "label": "x"}).status_code == 422

    # plan tiers : rattachement obligatoire, compatible, code alphanumérique
    r = client.post(f"{A}/third-parties", headers=H, json={"code": "4011TOY", "name": "Fournisseur TOYOTA", "kind": "supplier"})
    assert r.status_code == 422, r.text
    r = client.post(f"{A}/third-parties", headers=H, json={"code": "4111TOY", "name": "Client TOYOTA", "kind": "customer",
                                                             "collective_account_number": "4011000"})
    assert r.status_code == 422 and "collectif" in r.json()["error"]["message"], r.text
    toy = client.post(f"{A}/third-parties", headers=H, json={"code": "4011TOY", "name": "Fournisseur TOYOTA", "kind": "supplier",
                                                               "collective_account_number": "4011000"})
    assert toy.status_code == 201, toy.text
    toy = toy.json()
    assert toy["category"] == "suppliers" and toy["attached"] is True
    aut = client.post(f"{A}/third-parties", headers=H, json={"code": "4011AUT", "name": "Autre fournisseur", "kind": "supplier",
                                                               "collective_account_number": "4011000"}).json()
    cli = client.post(f"{A}/third-parties", headers=H, json={"code": "4111TOY", "name": "Client TOYOTA", "kind": "customer",
                                                               "collective_account_number": "4111000"}).json()
    r = client.patch(f"{A}/third-parties/{toy['id']}", headers=H, json={"collective_account_number": None})
    assert r.status_code == 422 and "obligatoire" in r.json()["error"]["message"], r.text

    # recherche par code et par intitulé, catégories
    tp = client.get(f"{A}/third-parties", headers=H, params={"q": "toyota"}).json()
    assert {t["code"] for t in tp["items"]} == {"4011TOY", "4111TOY"}
    tp = client.get(f"{A}/third-parties", headers=H, params={"category": "suppliers"}).json()
    assert {t["code"] for t in tp["items"]} == {"4011TOY", "4011AUT"}
    assert tp["categories"] == {"customers": 1, "suppliers": 2, "employees": 0, "others": 0} and tp["unattached"] == 0
    assert {a["account_number"] for a in client.get(f"{A}/accounts", headers=H, params={"q": "4011"}).json()["items"]} == {"4011000"}

    # écritures : 1 000 TOYOTA + 500 autre sur 4011000, 200 sur 4010000 (avec tiers), contrepartie achats
    ha = client.post(f"{A}/journals", headers=H, json={"code": "HA", "label": "Achats", "journal_type": "purchases"}).json()
    _post_validated(client, A, H, validator, fy, ha["id"], f"{year}-03-01", "Factures", [
        {"account_number": "601", "debit": "1700.00"},
        {"account_number": "4011000", "third_party_id": toy["id"], "credit": "1000.00"},
        {"account_number": "4011000", "third_party_id": aut["id"], "credit": "500.00"},
        {"account_number": "4010000", "third_party_id": aut["id"], "credit": "200.00"}])

    # balance générale avec sous-totaux du référentiel : 401 = 1 700 (4010000 + 4011000), classe 4 = 1 700, pas plus
    b = client.get(f"{A}/fiscal-years/{fy['id']}/balance", headers=H, params={"subtotals": "true"}).json()
    sub = {r["account"]: r for r in b["hierarchy"] if r["kind"] == "subtotal"}
    det = {r["account"]: r for r in b["hierarchy"] if r["kind"] == "detail"}
    assert Decimal(det["4011000"]["closing_credit"]) == Decimal("1500")
    assert Decimal(sub["401"]["closing_credit"]) == Decimal("1700") and sub["401"]["rows"] == 2
    assert Decimal(sub["4"]["closing_credit"]) == Decimal("1700") and sub["4"]["label"]
    assert Decimal(b["totals"]["closing_credit"]) == Decimal(b["totals"]["closing_debit"]) == Decimal("1700")
    assert client.get(f"{A}/fiscal-years/{fy['id']}/balance", headers=H).json()["hierarchy"] is None   # option

    # balance auxiliaire : soldes individuels, regroupés par compte collectif
    b = client.get(f"{A}/fiscal-years/{fy['id']}/balance", headers=H, params={"auxiliary": "true", "subtotals": "true"}).json()
    det = [(r["account"], r["third_party"]["code"], Decimal(r["closing_credit"])) for r in b["hierarchy"] if r["kind"] == "detail"]
    assert det == [("4010000", "4011AUT", Decimal("200")), ("4011000", "4011AUT", Decimal("500")),
                   ("4011000", "4011TOY", Decimal("1000"))]
    sub = {r["account"]: r for r in b["hierarchy"] if r["kind"] == "subtotal"}
    assert Decimal(sub["4011000"]["closing_credit"]) == Decimal("1500") and Decimal(sub["401"]["closing_credit"]) == Decimal("1700")
    csv = client.get(f"{A}/fiscal-years/{fy['id']}/balance.csv", headers=H, params={"subtotals": "true"}).text
    assert "Total 401;" in csv and "Total 4;" in csv

    # grand livre : compte divisionnaire, principal (racine) et auxiliaire (tiers)
    gl = client.get(f"{A}/fiscal-years/{fy['id']}/ledger", headers=H, params={"account": "401"}).json()
    assert {a["account"] for a in gl["accounts"]} >= {"4010000", "4011000"}
    gl = client.get(f"{A}/fiscal-years/{fy['id']}/ledger", headers=H, params={"third_party_id": toy["id"]}).json()
    assert sum(len(a["lines"]) for a in gl["accounts"]) == 1

    # mise en sommeil, suppression d'un compte utilisé refusée
    accs = {a["account_number"]: a for a in client.get(f"{A}/accounts", headers=H).json()["items"]}
    assert client.delete(f"{A}/accounts/{accs['4011000']['id']}", headers=H).status_code in (409, 422)
    r = client.patch(f"{A}/accounts/{accs['4011000']['id']}", headers=H, json={"is_active": False})
    assert r.status_code == 200 and r.json()["is_active"] is False
    r = client.post(f"{A}/third-parties", headers=H, json={"code": "4011NEW", "name": "Nouveau", "kind": "supplier",
                                                             "collective_account_number": "4011000"})
    assert r.status_code == 422 and "sommeil" in r.json()["error"]["message"], r.text
    r = client.patch(f"{A}/third-parties/{cli['id']}", headers=H, json={"is_active": False})
    assert r.status_code == 200 and r.json()["is_active"] is False
