"""Lot 12A par l'API : catalogue (administration, publication figée, lecture publique), compte de facturation,
essai, droits, usages, aperçu chiffré, résiliation et retrait. Offres, prix et codes FICTIFS."""

from __future__ import annotations

import uuid

API = "/api/v1"
A = f"{API}/admin/billing"
QUOTAS = {"users": 5, "companies": 2, "engagements": 10, "storage_mb": 500, "imports_per_period": 20,
          "reports_per_period": 20, "ai_tokens_per_period": None}


def _code(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8].upper()}"


def _published_plan(client, admin, *, trial_days=30) -> dict:
    p = client.post(f"{A}/products", headers=admin.headers, json={"code": _code("TESTPLAN"), "kind": "plan",
                                                                   "name": "Offre de test"})
    assert p.status_code == 201, p.text
    pid = p.json()["id"]
    v = client.post(f"{A}/products/{pid}/versions", headers=admin.headers, json={"label": "v1", "trial_days": trial_days})
    assert v.status_code == 201, v.text
    vid = v.json()["id"]
    r = client.put(f"{A}/versions/{vid}/prices", headers=admin.headers, json={"prices": [
        {"billing_interval": "month", "currency": "XOF", "amount": "15000"},
        {"billing_interval": "year", "currency": "XOF", "amount": "150000"},
        {"billing_interval": "month", "currency": "CDF", "amount": "12.50"}]})
    assert r.status_code == 200, r.text
    r = client.put(f"{A}/versions/{vid}/entitlements", headers=admin.headers,
                   json={"modules": ["core", "accounting_import", "audit_core"], "quotas": QUOTAS})
    assert r.status_code == 200, r.text
    r = client.post(f"{A}/versions/{vid}/publish", headers=admin.headers)
    assert r.status_code == 200 and r.json()["status"] == "published", r.text
    return {"product_id": pid, "version_id": vid, "code": p.json()["code"]}


def test_catalog_administration(client, make_user):
    admin, owner = make_user("bl-adm"), make_user("bl-own")
    admin.make_platform_admin()
    client.get(f"{API}/me", headers=owner.headers)
    assert client.get(f"{A}/products", headers=owner.headers).status_code == 403
    assert client.post(f"{A}/products", headers=owner.headers,
                       json={"code": "PIRATE", "kind": "plan", "name": "x"}).status_code == 403
    assert {m["key"] for m in client.get(f"{A}/modules", headers=admin.headers).json()} >= {"core", "financial_audit"}

    pid = client.post(f"{A}/products", headers=admin.headers,
                      json={"code": _code("TESTDRAFT"), "kind": "plan", "name": "Brouillon"}).json()["id"]
    vid = client.post(f"{A}/products/{pid}/versions", headers=admin.headers, json={"label": "v1", "trial_days": 30}).json()["id"]
    # montant à décimales en XOF refusé par le moteur avant la base
    r = client.put(f"{A}/versions/{vid}/prices", headers=admin.headers,
                   json={"prices": [{"billing_interval": "month", "currency": "XOF", "amount": "100.50"}]})
    assert r.status_code == 422 and "XOF" in r.json()["error"]["message"], r.text
    # anomalies listées avant publication : prix, module de base, dépendance, quotas
    client.put(f"{A}/versions/{vid}/entitlements", headers=admin.headers, json={"modules": ["financial_audit"], "quotas": {}})
    issues = client.post(f"{A}/versions/{vid}/validate", headers=admin.headers).json()["issues"]
    assert "Aucun prix saisi" in issues and "Module de base absent : core" in issues
    assert any("audit_core" in i for i in issues) and any(i.startswith("Quota non défini") for i in issues)
    r = client.post(f"{A}/versions/{vid}/publish", headers=admin.headers)
    assert r.status_code == 409 and r.json()["error"]["details"]["issues"], r.text
    assert client.delete(f"{A}/versions/{vid}", headers=admin.headers).status_code == 204

    plan = _published_plan(client, admin)
    # version publiée figée
    r = client.put(f"{A}/versions/{plan['version_id']}/prices", headers=admin.headers,
                   json={"prices": [{"billing_interval": "month", "currency": "XOF", "amount": "1"}]})
    assert r.status_code == 409, r.text
    # nouvelle version copiée, publiée : la précédente est retirée
    v2 = client.post(f"{A}/products/{plan['product_id']}/versions", headers=admin.headers,
                     json={"label": "v2", "trial_days": 30, "copy_from": plan["version_id"]}).json()
    assert v2["version_no"] == 2 and len(v2["prices"]) == 3 and v2["quotas"]["ai_tokens_per_period"] is None
    assert client.post(f"{A}/versions/{v2['id']}/publish", headers=admin.headers).status_code == 200
    assert client.get(f"{A}/versions/{plan['version_id']}", headers=admin.headers).json()["status"] == "retired"

    # catalogue public, sans jeton : seule la version publiée, montants en texte exact
    cat = client.get(f"{API}/billing/catalog")
    assert cat.status_code == 200, cat.text
    mine = [p for p in cat.json()["plans"] if p["code"] == plan["code"]]
    assert len(mine) == 1 and mine[0]["label"] == "v2"
    assert {(x["currency"], x["amount"]) for x in mine[0]["prices"]} >= {("XOF", "15000"), ("CDF", "12.5")}
    assert cat.json()["countries"]["CM"] == "XAF" and len(cat.json()["countries"]) == 17

    # promotions et paramètres
    promo = client.post(f"{A}/promotions", headers=admin.headers, json={
        "code": _code("PROMO").replace("_", "-"), "label": "Test", "discount_type": "percent", "percent": "10",
        "duration": "once"})
    assert promo.status_code == 201, promo.text
    r = client.patch(f"{A}/promotions/{promo.json()['id']}", headers=admin.headers, json={"status": "disabled"})
    assert r.status_code == 200 and r.json()["status"] == "disabled"
    s = client.get(f"{A}/settings", headers=admin.headers).json()
    assert s["grace_days"] == 7 and s["seller_country"] == "BJ"
    assert client.put(f"{A}/settings", headers=owner.headers, json={"grace_days": 1}).status_code == 403


def test_subscription_flow(client, make_user):
    admin, owner, manager, member, outsider = (make_user(n) for n in ("bs-adm", "bs-own", "bs-man", "bs-mem", "bs-out"))
    admin.make_platform_admin()
    plan = _published_plan(client, admin)
    promo_code = _code("BIENVENUE").replace("_", "-")
    assert client.post(f"{A}/promotions", headers=admin.headers, json={
        "code": promo_code, "label": "Test", "discount_type": "percent", "percent": "15", "duration": "once"}).status_code == 201

    org = client.post(f"{API}/organizations", json={"name": "Cabinet abonné (test)"}, headers=owner.headers).json()
    base = f"{API}/organizations/{org['id']}"
    client.post(f"{base}/members", json={"email": manager.email, "role": "admin"}, headers=owner.headers)
    client.post(f"{base}/members", json={"email": member.email, "role": "member"}, headers=owner.headers)

    # avant l'essai : aucun droit, aucune donnée
    e = client.get(f"{base}/entitlements", headers=member.headers).json()
    assert e["access"] == "none" and e["display_only"] is True
    assert client.get(f"{base}/subscription", headers=owner.headers).json() == {"subscription": None}
    r = client.post(f"{base}/subscription/trial", headers=owner.headers, json={"version_id": plan["version_id"]})
    assert r.status_code == 422 and "facturation" in r.json()["error"]["message"], r.text

    # compte de facturation : propriétaire seul
    ifu = uuid.uuid4().hex[:10].upper()     # identité de facturation propre à chaque passage (un essai par identité)
    acct = {"legal_name": "Cabinet SARL", "tax_id": f" ifu {ifu} ", "address": "Cotonou", "country_code": "bj",
            "billing_email": "compta@cabinet.test"}
    assert client.put(f"{base}/billing-account", headers=manager.headers, json=acct).status_code == 403
    r = client.put(f"{base}/billing-account", headers=owner.headers, json={**acct, "country_code": "FR"})
    assert r.status_code == 422 and "FR" in r.json()["error"]["message"], r.text
    a = client.put(f"{base}/billing-account", headers=owner.headers, json=acct).json()["account"]
    assert a["tax_id"] == f"IFU{ifu}" and a["currency"] == "XOF" and a["country_code"] == "BJ"
    assert client.get(f"{base}/billing-account", headers=manager.headers).status_code == 200
    assert client.get(f"{base}/billing-account", headers=member.headers).status_code == 403
    assert client.get(f"{base}/billing-account", headers=outsider.headers).status_code == 404

    # aperçu chiffré : calculé par le serveur, remise appliquée, sans taxe
    q = client.post(f"{base}/subscription/quote", headers=manager.headers,
                    json={"version_id": plan["version_id"], "billing_interval": "month", "promotion_code": promo_code.lower()})
    assert q.status_code == 200, q.text
    q = q.json()
    assert (q["currency"], q["subtotal"], q["discount"], q["total"]) == ("XOF", "15000", "2250", "12750")
    assert q["taxes"] is None and q["notes"]
    r = client.post(f"{base}/subscription/quote", headers=owner.headers,
                    json={"version_id": plan["version_id"], "billing_interval": "month", "promotion_code": "INCONNU"})
    assert r.status_code == 422
    assert client.post(f"{base}/subscription/quote", headers=member.headers,
                       json={"version_id": plan["version_id"]}).status_code == 403

    # essai : propriétaire seul, 30 jours
    assert client.post(f"{base}/subscription/trial", headers=manager.headers,
                       json={"version_id": plan["version_id"]}).status_code == 403
    r = client.post(f"{base}/subscription/trial", headers=owner.headers, json={"version_id": plan["version_id"]})
    assert r.status_code == 201, r.text
    sub = r.json()["subscription"]
    assert sub["status"] == "trialing" and sub["currency"] == "XOF" and sub["plan"]["code"] == plan["code"]
    assert sub["can_cancel"] is True and sub["can_reactivate"] is False
    r = client.post(f"{base}/subscription/trial", headers=owner.headers, json={"version_id": plan["version_id"]})
    assert r.status_code == 409 and "déjà" in r.json()["error"]["message"], r.text

    # droits : lisibles par tout membre, pour l'affichage
    e = client.get(f"{base}/entitlements", headers=member.headers).json()
    assert e["access"] == "full" and e["modules"] == ["accounting_import", "audit_core", "core"]
    assert e["quotas"]["users"] == 5 and e["quotas"]["ai_tokens_per_period"] is None
    assert client.get(f"{base}/entitlements", headers=outsider.headers).status_code == 404

    # usages mesurés sur les tables existantes
    u = client.get(f"{base}/usage", headers=manager.headers).json()
    used = {x["key"]: x for x in u["quotas"]}
    assert used["users"]["used"] == 3 and used["users"]["limit"] == 5
    assert used["ai_tokens_per_period"]["unlimited"] is True and used["companies"]["used"] == 0
    assert client.get(f"{base}/usage", headers=member.headers).status_code == 403

    # résiliation en fin d'essai, puis retrait
    assert client.post(f"{base}/subscription/cancel", headers=manager.headers, json={}).status_code == 403
    r = client.post(f"{base}/subscription/cancel", headers=owner.headers, json={"reason": "Test"})
    assert r.status_code == 200, r.text
    s = r.json()["subscription"]
    assert s["cancel_at"] == s["trial_end"] and s["can_reactivate"] is True
    assert client.post(f"{base}/subscription/cancel", headers=owner.headers, json={}).status_code == 422
    r = client.post(f"{base}/subscription/reactivate", headers=owner.headers)
    assert r.status_code == 200 and r.json()["subscription"]["cancel_at"] is None
    assert client.post(f"{base}/subscription/reactivate", headers=owner.headers).status_code == 422

    # anti-abus : le même propriétaire n'obtient pas un second essai dans une autre organisation
    org2 = client.post(f"{API}/organizations", json={"name": "Seconde (test)"}, headers=owner.headers).json()
    base2 = f"{API}/organizations/{org2['id']}"
    client.put(f"{base2}/billing-account", headers=owner.headers, json={**acct, "tax_id": f"AUTRE-{ifu}"})
    r = client.post(f"{base2}/subscription/trial", headers=owner.headers, json={"version_id": plan["version_id"]})
    assert r.status_code == 409 and "essai" in r.json()["error"]["message"], r.text

    # journal : actions métier tracées
    from sqlalchemy import text

    from app.db.session import engine
    with engine.connect() as conn:
        actions = set(conn.execute(text("SELECT action FROM public.audit_logs WHERE organization_id = :o"),
                                   {"o": org["id"]}).scalars())
    assert {"billing.account_updated", "subscription.trial_started", "subscription.cancel_requested",
            "subscription.reactivated"} <= actions
