"""Parcours complet : organisations, membres, entreprises, permissions, exercices."""

from __future__ import annotations

import uuid

API = "/api/v1"


def _create_org(client, user, name="Cabinet Test"):
    r = client.post(f"{API}/organizations", json={"name": name, "org_type": "accounting_firm"},
                    headers=user.headers)
    assert r.status_code == 201, r.text
    return r.json()


def _create_company(client, user, org_id, name="Client SA", framework="SYSCOHADA_REV"):
    r = client.post(f"{API}/organizations/{org_id}/companies",
                    json={"name": name, "framework_code": framework, "country_code": "ci"}, headers=user.headers)
    assert r.status_code == 201, r.text
    return r.json()


def _add_member(client, owner, org_id, user, role="member"):
    r = client.post(f"{API}/organizations/{org_id}/members", json={"email": user.email, "role": role},
                    headers=owner.headers)
    assert r.status_code == 201, r.text
    assert r.json()["invitation_sent"] is False
    return r.json()["member"]


# --------------------------------------------------------------------- auth
def test_requires_authentication(client):
    assert client.get(f"{API}/organizations").status_code == 401
    r = client.get(f"{API}/organizations", headers={"Authorization": "Bearer abc.def.ghi"})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthorized"


def test_expired_token_rejected(client, make_user):
    u = make_user("expired")
    tok = u.token(exp=1)
    assert client.get(f"{API}/me", headers={"Authorization": f"Bearer {tok}"}).status_code == 401


def test_profile_created_by_trigger_and_editable(client, make_user):
    u = make_user("profile")
    r = client.get(f"{API}/me", headers=u.headers)
    assert r.status_code == 200 and r.json()["email"] == u.email
    r = client.patch(f"{API}/me", json={"full_name": "Awa Koné", "locale": "fr"}, headers=u.headers)
    assert r.status_code == 200 and r.json()["full_name"] == "Awa Koné"
    assert r.json()["is_platform_admin"] is False


# --------------------------------------------------------------------- organisations
def test_create_org_makes_owner_and_isolates_tenants(client, make_user):
    alice, bob = make_user("alice"), make_user("bob")
    org = _create_org(client, alice, "Cabinet Kouassi & Associés")
    assert org["my_role"] == "owner"
    assert org["slug"].startswith("cabinet-kouassi-associes")

    assert [o["id"] for o in client.get(f"{API}/organizations", headers=alice.headers).json()] == [org["id"]]
    assert client.get(f"{API}/organizations", headers=bob.headers).json() == []
    # ressource d'un autre tenant : 404 (pas de fuite d'existence)
    assert client.get(f"{API}/organizations/{org['id']}", headers=bob.headers).status_code == 404
    assert client.get(f"{API}/organizations/{org['id']}/members", headers=bob.headers).status_code == 404
    r = client.post(f"{API}/organizations/{org['id']}/companies",
                    json={"name": "Intrus", "framework_code": "SYSCOHADA_REV"}, headers=bob.headers)
    assert r.status_code == 404


def test_duplicate_explicit_slug_conflict(client, make_user):
    a, b = make_user("slug-a"), make_user("slug-b")
    slug = f"cabinet-{uuid.uuid4().hex[:6]}"
    assert client.post(f"{API}/organizations", json={"name": "A", "slug": slug}, headers=a.headers).status_code == 422
    assert client.post(f"{API}/organizations", json={"name": "Cabinet A", "slug": slug},
                       headers=a.headers).status_code == 201
    r = client.post(f"{API}/organizations", json={"name": "Cabinet B", "slug": slug}, headers=b.headers)
    assert r.status_code == 409


def test_validation_errors(client, make_user):
    u = make_user("valid")
    r = client.post(f"{API}/organizations", json={"name": "Org", "default_currency": "FCFA"}, headers=u.headers)
    assert r.status_code == 422


# --------------------------------------------------------------------- membres & rôles
def test_member_roles_and_escalation(client, make_user):
    owner, admin, member = make_user("own"), make_user("adm"), make_user("mem")
    org = _create_org(client, owner)
    admin_m = _add_member(client, owner, org["id"], admin, "admin")
    member_m = _add_member(client, owner, org["id"], member, "member")

    # un admin ne nomme pas de propriétaire et ne se promeut pas
    r = client.patch(f"{API}/organizations/{org['id']}/members/{member_m['id']}", json={"role": "owner"},
                     headers=admin.headers)
    assert r.status_code == 403
    r = client.patch(f"{API}/organizations/{org['id']}/members/{admin_m['id']}", json={"role": "owner"},
                     headers=admin.headers)
    assert r.status_code == 403
    # un membre ne gère pas les membres
    r = client.patch(f"{API}/organizations/{org['id']}/members/{admin_m['id']}", json={"role": "viewer"},
                     headers=member.headers)
    assert r.status_code == 403
    # le dernier propriétaire ne peut pas être rétrogradé
    owner_m = next(m for m in client.get(f"{API}/organizations/{org['id']}/members", headers=owner.headers).json()
                   if m["user_id"] == str(owner.id))
    r = client.patch(f"{API}/organizations/{org['id']}/members/{owner_m['id']}", json={"role": "admin"},
                     headers=owner.headers)
    assert r.status_code == 422
    assert "propriétaire" in r.json()["error"]["message"]
    # déjà membre
    r = client.post(f"{API}/organizations/{org['id']}/members", json={"email": member.email, "role": "viewer"},
                    headers=owner.headers)
    assert r.status_code == 409
    # un membre peut quitter l'organisation
    assert client.delete(f"{API}/organizations/{org['id']}/members/{member_m['id']}",
                         headers=member.headers).status_code == 204
    assert client.get(f"{API}/organizations/{org['id']}", headers=member.headers).status_code == 404


def test_invitation_unavailable_without_service_key(client, make_user):
    owner = make_user("inv")
    org = _create_org(client, owner)
    r = client.post(f"{API}/organizations/{org['id']}/members",
                    json={"email": f"inconnu.{uuid.uuid4().hex[:6]}@kofinex.test"}, headers=owner.headers)
    assert r.status_code == 503   # pas de faux succès : l'invitation n'est pas simulée


# --------------------------------------------------------------------- entreprises
def test_company_visibility_by_assignment(client, make_user):
    owner, member = make_user("c-own"), make_user("c-mem")
    org = _create_org(client, owner)
    _add_member(client, owner, org["id"], member, "member")
    c1 = _create_company(client, owner, org["id"], "Industrie SA")
    _create_company(client, owner, org["id"], "Association X", "SYSCEBNL")

    assert len(client.get(f"{API}/organizations/{org['id']}/companies", headers=owner.headers).json()) == 2
    assert client.get(f"{API}/organizations/{org['id']}/companies", headers=member.headers).json() == []
    assert client.get(f"{API}/companies/{c1['id']}", headers=member.headers).status_code == 404
    # un membre ne crée pas d'entreprise
    r = client.post(f"{API}/organizations/{org['id']}/companies",
                    json={"name": "Nouvelle", "framework_code": "SYSCOHADA_REV"}, headers=member.headers)
    assert r.status_code == 403

    r = client.post(f"{API}/companies/{c1['id']}/members", json={"user_id": str(member.id), "role": "viewer"},
                    headers=owner.headers)
    assert r.status_code == 201
    listed = client.get(f"{API}/organizations/{org['id']}/companies", headers=member.headers).json()
    assert [c["id"] for c in listed] == [c1["id"]]
    assert listed[0]["my_role"] == "viewer" and listed[0]["my_permissions"] == ["company.read"]
    assert client.patch(f"{API}/companies/{c1['id']}", json={"name": "Renommée"},
                        headers=member.headers).status_code == 403


def test_company_rejects_cross_org_member(client, make_user):
    owner, outsider = make_user("x-own"), make_user("x-out")
    org = _create_org(client, owner)
    c = _create_company(client, owner, org["id"])
    client.get(f"{API}/me", headers=outsider.headers)
    r = client.post(f"{API}/companies/{c['id']}/members", json={"user_id": str(outsider.id), "role": "viewer"},
                    headers=owner.headers)
    assert r.status_code == 404


# --------------------------------------------------------------------- exercices
def test_fiscal_year_lifecycle(client, make_user):
    owner, acc, viewer = make_user("f-own"), make_user("f-acc"), make_user("f-view")
    org = _create_org(client, owner)
    for u in (acc, viewer):
        _add_member(client, owner, org["id"], u, "member")
    c = _create_company(client, owner, org["id"])
    client.post(f"{API}/companies/{c['id']}/members", json={"user_id": str(acc.id), "role": "accountant"},
                headers=owner.headers)
    client.post(f"{API}/companies/{c['id']}/members", json={"user_id": str(viewer.id), "role": "viewer"},
                headers=owner.headers)
    base = f"{API}/companies/{c['id']}/fiscal-years"

    fy = {"label": "2025", "start_date": "2025-01-01", "end_date": "2025-12-31"}
    assert client.post(base, json=fy, headers=viewer.headers).status_code == 403
    r = client.post(base, json=fy, headers=acc.headers)
    assert r.status_code == 201, r.text
    fy_id = r.json()["id"]

    r = client.post(base, json={"label": "2025-bis", "start_date": "2025-07-01", "end_date": "2026-06-30"},
                    headers=acc.headers)
    assert r.status_code == 409 and r.json()["error"]["code"] == "overlap"
    r = client.post(base, json={"label": "Long", "start_date": "2027-01-01", "end_date": "2028-12-31"},
                    headers=acc.headers)
    assert r.status_code == 422

    assert client.post(f"{base}/{fy_id}/close", json={"confirm_label": "2024"}, headers=acc.headers).status_code == 409
    r = client.post(f"{base}/{fy_id}/close", json={"confirm_label": "2025"}, headers=acc.headers)
    assert r.status_code == 200 and r.json()["status"] == "closed"

    assert client.post(f"{base}/{fy_id}/reopen", json={"reason": "Correction d'écritures d'inventaire"},
                       headers=acc.headers).status_code == 403
    assert client.post(f"{base}/{fy_id}/reopen", json={"reason": "court"}, headers=owner.headers).status_code == 422
    r = client.post(f"{base}/{fy_id}/reopen", json={"reason": "Correction d'écritures d'inventaire"},
                    headers=owner.headers)
    assert r.status_code == 200 and r.json()["status"] == "open"

    logs = client.get(f"{API}/companies/{c['id']}/audit-logs", headers=acc.headers).json()
    actions = {i["action"] for i in logs["items"]}
    assert {"fiscal_year.closed", "fiscal_year.reopened"} <= actions
    assert client.get(f"{API}/companies/{c['id']}/audit-logs", headers=viewer.headers).status_code == 403


def test_delete_organization_requires_owner_and_confirmation(client, make_user):
    owner, admin = make_user("d-own"), make_user("d-adm")
    org = _create_org(client, owner)
    _add_member(client, owner, org["id"], admin, "admin")
    url = f"{API}/organizations/{org['id']}"
    assert client.request("DELETE", url, json={"confirm_slug": org["slug"]}, headers=admin.headers).status_code == 403
    assert client.request("DELETE", url, json={"confirm_slug": "mauvais"}, headers=owner.headers).status_code == 409
    assert client.request("DELETE", url, json={"confirm_slug": org["slug"]}, headers=owner.headers).status_code == 204
    assert client.get(url, headers=owner.headers).status_code == 404
