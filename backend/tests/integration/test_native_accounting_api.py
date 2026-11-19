"""Comptabilité native par l'API, cycle des étapes A et B : paramétrage (plan comptable, tiers, journaux) → saisie →
contrôles → soumission → validation par une autre personne → grand livre → balances → lettrage → extourne.
Les étapes inventaire, états financiers et clôture (C à E) ne sont pas encore développées. Données FICTIVES."""

from __future__ import annotations

from tests.integration.test_ai_api import _analysis

API = "/api/v1"


def test_native_accounting_cycle(client, make_user):
    owner, org, cid, fy, _a = _analysis(client, make_user)
    A = f"{API}/companies/{cid}/accounting"
    H = owner.headers
    year = int(fy["start_date"][:4])
    validator = make_user("na-val")
    r = client.post(f"{API}/organizations/{org['id']}/members", headers=H, json={"email": validator.email, "role": "member"})
    assert r.status_code in (200, 201), r.text
    r = client.post(f"{API}/companies/{cid}/members", headers=H, json={"user_id": str(validator.id), "role": "accountant"})
    assert r.status_code == 201, r.text

    # ------------------------------------------------ paramétrage
    r = client.post(f"{A}/accounts/import-chart", headers=H, json={})
    assert r.status_code == 200 and r.json()["created"] >= 5, r.text
    accs = {a["account_number"]: a for a in client.get(f"{A}/accounts", headers=H).json()["items"]}
    client.patch(f"{A}/accounts/{accs['411']['id']}", headers=H, json={"third_party_kind": "customer", "lettering_enabled": True})
    assert client.post(f"{A}/accounts", headers=H, json={"account_number": "999100", "label": "Hors plan"}).status_code == 422
    tp = client.post(
        f"{A}/third-parties",
        headers=H,
        json={"code": "C1", "name": "Client 1", "kind": "customer", "collective_account_number": "411"},
    ).json()
    vt = client.post(f"{A}/journals", headers=H, json={"code": "VT", "label": "Ventes", "journal_type": "sales"}).json()
    bq = client.post(
        f"{A}/journals",
        headers=H,
        json={"code": "BQ", "label": "Banque", "journal_type": "bank", "counterpart_account_number": "521"},
    ).json()
    assert vt["number_prefix"] == "VT-"

    # ------------------------------------------------ saisie et contrôles
    body = {
        "fiscal_year_id": fy["id"],
        "journal_id": vt["id"],
        "entry_date": f"{year}-03-15",
        "piece_ref": "F12",
        "label": "Facture F12",
        "lines": [{"account_number": "411", "debit": "1200.00"}, {"account_number": "701", "credit": "1100.00"}],
    }
    pre = client.post(f"{A}/entries/check", headers=H, json=body).json()
    assert not pre["balanced"] and any("Tiers" in i or "tiers" in i for i in pre["issues"])
    assert (
        client.post(f"{A}/entries", headers=H, json={**body, "lines": [{"account_number": "411", "debit": 12.5}]}).status_code
        == 422
    )
    e = client.post(f"{A}/entries", headers=H, json=body).json()
    assert e["status"] == "draft" and not e["check"]["balanced"]
    r = client.post(f"{A}/entries/{e['id']}/transition", headers=H, json={"action": "submit"})
    assert r.status_code == 422
    body["lines"] = [
        {"account_number": "411", "third_party_id": tp["id"], "debit": "1200.00"},
        {"account_number": "701", "credit": "1200.00"},
    ]
    e = client.patch(f"{A}/entries/{e['id']}", headers=H, json={"lines": body["lines"]}).json()
    assert e["check"]["balanced"] and e["check"]["issues"] == []
    e = client.post(f"{A}/entries/{e['id']}/transition", headers=H, json={"action": "submit"}).json()
    assert e["status"] == "submitted" and e["actions"]["validate"] is False  # séparation des tâches

    # ------------------------------------------------ validation par une autre personne
    assert client.post(f"{A}/entries/{e['id']}/transition", headers=H, json={"action": "validate"}).status_code == 403
    v = client.post(f"{A}/entries/{e['id']}/transition", headers=validator.headers, json={"action": "validate"})
    assert v.status_code == 200 and v.json()["number"] == "VT-000001", v.text
    assert client.patch(f"{A}/entries/{e['id']}", headers=H, json={"label": "X"}).status_code == 422

    # règlement, validé
    p = client.post(
        f"{A}/entries",
        headers=H,
        json={
            "fiscal_year_id": fy["id"],
            "journal_id": bq["id"],
            "entry_date": f"{year}-04-05",
            "label": "Règlement F12",
            "lines": [
                {"account_number": "521", "debit": "1200"},
                {"account_number": "411", "third_party_id": tp["id"], "credit": "1200"},
            ],
        },
    ).json()
    client.post(f"{A}/entries/{p['id']}/transition", headers=H, json={"action": "submit"})
    assert (
        client.post(f"{A}/entries/{p['id']}/transition", headers=validator.headers, json={"action": "validate"}).json()["number"]
        == "BQ-000001"
    )

    # ------------------------------------------------ grand livre et balances
    gl = client.get(f"{A}/fiscal-years/{fy['id']}/ledger", headers=H, params={"account": "411"}).json()
    rows = gl["accounts"][0]["lines"]
    assert [ln["balance"] for ln in rows] == ["1200.00", "0.00"] or [float(ln["balance"]) for ln in rows] == [1200, 0]
    bal = client.get(f"{A}/fiscal-years/{fy['id']}/balance", headers=H).json()
    assert bal["balanced"] and bal["entries_count"] == 2
    aux = client.get(f"{A}/fiscal-years/{fy['id']}/balance", headers=H, params={"auxiliary": "true"}).json()
    assert aux["rows"][0]["third_party"]["code"] == "C1"
    assert client.get(f"{A}/fiscal-years/{fy['id']}/balance", headers=H, params={"scope": "final"}).status_code == 422
    assert client.get(f"{A}/fiscal-years/{fy['id']}/balance.csv", headers=H).status_code == 200

    # ------------------------------------------------ lettrage
    open_lines = client.get(f"{A}/lettering", headers=H, params={"account": "411", "third_party_id": tp["id"]}).json()["items"]
    assert len(open_lines) == 2
    lt = client.post(f"{A}/lettering", headers=H, json={"line_ids": [x["line_id"] for x in open_lines]})
    assert lt.status_code == 201 and lt.json()["code"] == "A", lt.text
    assert client.delete(f"{A}/lettering/{lt.json()['lettering_id']}", headers=H).status_code == 204

    # ------------------------------------------------ extourne et correction
    rv = client.post(
        f"{A}/entries/{e['id']}/reverse", headers=H, json={"entry_date": f"{year}-03-31", "with_correction": True}
    ).json()
    client.post(f"{A}/entries/{rv['reversal_id']}/transition", headers=H, json={"action": "submit"})
    client.post(f"{A}/entries/{rv['reversal_id']}/transition", headers=validator.headers, json={"action": "validate"})
    assert client.get(f"{A}/entries/{e['id']}", headers=H).json()["status"] == "reversed"
    assert client.get(f"{A}/entries/{rv['correction_id']}", headers=H).json()["origin"] == "correction"

    # ------------------------------------------------ accès
    outsider = make_user("na-out")
    assert client.get(f"{A}/entries", headers=outsider.headers).status_code in (403, 404)
