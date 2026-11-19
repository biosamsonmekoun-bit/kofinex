"""Grand livre par l'API : dépôt d'un fichier des écritures (format FEC), contrôles, validation, consultation,
centralisation, analyses, population d'audit. Référentiel, balance et écritures FICTIFS."""

from __future__ import annotations

import uuid

from tests.integration.test_imports_api import test_framework  # noqa: F401, F811  (fixture partagée)
from tests.integration.test_management_api import _setup

API = "/api/v1"
HEAD = ("JournalCode|JournalLib|EcritureNum|EcritureDate|CompteNum|CompteLib|CompAuxNum|CompAuxLib|PieceRef|PieceDate|"
        "EcritureLib|Debit|Credit|EcritureLet|DateLet|ValidDate|Montantdevise|Idevise")


def _fec(year: int, *, unbalanced: bool = False) -> bytes:
    rows = [
        ("VT", "Ventes", "1", f"{year}0315", "411100", "Clients", "Facture F1", "1200,00", "0,00"),
        ("VT", "Ventes", "1", f"{year}0315", "701100", "Ventes", "Facture F1", "0,00", "1100,00" if unbalanced else "1200,00"),
        ("BQ", "Banque", "2", f"{year}0405", "521100", "Banque", "Règlement F1", "1200,00", "0,00"),
        ("BQ", "Banque", "2", f"{year}0405", "411100", "Clients", "Règlement F1", "0,00", "1200,00"),
    ]
    lines = [HEAD] + ["|".join([j, jl, n, d, a, al, "", "", "P" + n, d, lab, de, cr, "", "", "", "", ""])
                      for j, jl, n, d, a, al, lab, de, cr in rows]
    return ("\n".join(lines) + "\n").encode()


def test_ledger_flow(client, make_user, test_framework):  # noqa: F811
    owner, _ctrl, viewer, cid, fy, year = _setup(client, make_user, test_framework)
    base = f"{API}/companies/{cid}"

    # fichier déséquilibré : contrôles bloquants, validation refusée
    r = client.post(f"{base}/ledger-imports", headers=owner.headers, data={"fiscal_year_id": fy["id"]},
                    files={"file": ("fec.csv", _fec(year, unbalanced=True), "text/csv")})
    assert r.status_code == 202, r.text
    bad = r.json()
    assert bad["status"] == "awaiting_mapping" and bad["sheets"][0]["format"] == "fec"
    r = client.post(f"{base}/ledger-imports/{bad['id']}/configure", headers=owner.headers, json={
        "sheet_name": bad["sheet_name"], "header_row": bad["header_row"], "column_map": bad["column_map"],
        "options": {"decimal_separator": ","}})
    assert r.status_code == 202 and r.json()["controls"]["blocking"], r.text
    assert client.post(f"{base}/ledger-imports/{bad['id']}/confirm", headers=owner.headers, json={}).status_code == 409
    assert client.post(f"{base}/ledger-imports/{bad['id']}/cancel", headers=owner.headers).json()["status"] == "cancelled"

    # fichier correct
    assert client.post(f"{base}/ledger-imports", headers=viewer.headers, data={"fiscal_year_id": fy["id"]},
                       files={"file": ("fec.csv", _fec(year), "text/csv")}).status_code == 403
    job = client.post(f"{base}/ledger-imports", headers=owner.headers, data={"fiscal_year_id": fy["id"]},
                      files={"file": ("fec.csv", _fec(year), "text/csv")}).json()
    job = client.post(f"{base}/ledger-imports/{job['id']}/configure", headers=owner.headers, json={
        "sheet_name": job["sheet_name"], "header_row": job["header_row"], "column_map": job["column_map"],
        "options": {"decimal_separator": ","}}).json()
    codes = {c["code"]: c for c in job["controls"]["results"]}
    assert codes["LEDGER_BALANCED"]["status"] == "passed" and codes["ENTRIES_BALANCED"]["status"] == "passed"
    assert not job["controls"]["blocking"]
    # la balance fictive ne contient pas ces écritures : écart signalé, à accepter
    assert codes["TB_RECONCILIATION"]["status"] == "failed" and job["controls"]["requires_acknowledgment"]
    assert client.post(f"{base}/ledger-imports/{job['id']}/confirm", headers=owner.headers, json={}).status_code == 409
    r = client.post(f"{base}/ledger-imports/{job['id']}/confirm", headers=owner.headers,
                    json={"acknowledge_warnings": True, "save_mapping_as": "FEC (test)"})
    assert r.status_code == 200 and r.json()["status"] == "completed", r.text
    assert any(i["active"] for i in client.get(f"{base}/ledger-imports", headers=viewer.headers).json())

    # exploitation
    gl = f"{base}/fiscal-years/{fy['id']}/ledger"
    lines = client.get(gl, headers=viewer.headers, params={"account": "411100"}).json()
    assert lines["total_count"] == 2 and lines["running_balance"] and lines["items"][-1]["running_balance"] == "0"
    assert client.get(gl, headers=viewer.headers, params={"q": "Facture"}).json()["running_balance"] is False
    assert len(client.get(f"{gl}/entry", headers=viewer.headers, params={"journal": "VT", "number": "1"}).json()) == 2
    accts = {a["account_number"]: a for a in client.get(f"{gl}/accounts", headers=viewer.headers).json()["accounts"]}
    assert accts["521100"]["debit"] == "1200" and accts["521100"]["balance"] == "1200"
    js = {j["journal"]: j for j in client.get(f"{gl}/journals", headers=viewer.headers).json()["journals"]}
    assert js["VT"]["months"][0]["entries"] == 1 and js["BQ"]["debit"] == "1200"
    an = client.get(f"{gl}/analytics", headers=viewer.headers, params={"round_multiple": "100"}).json()
    assert an["round_amounts"]["count"] == 4 and an["benford"]["count"] == 4 and an["numbering_gaps"]
    assert "Journal" in client.get(f"{gl}.csv", headers=viewer.headers).text.split("\n")[0].replace("﻿", "")

    # population d'audit tirée des écritures
    org_id = client.get(f"{base}", headers=owner.headers).json()["organization_id"]
    e = client.post(f"{API}/organizations/{org_id}/engagements", headers=owner.headers, json={
        "company_id": cid, "fiscal_year_id": fy["id"], "engagement_type": "statutory_audit",
        "reference": f"GL-{uuid.uuid4().hex[:5]}", "name": "Audit (test)"}).json()
    client.post(f"{API}/engagements/{e['id']}/independence", headers=owner.headers, json={"statement": "Indépendant (test)."})
    pop = client.post(f"{API}/engagements/{e['id']}/fa/populations/from-ledger", headers=owner.headers,
                      json={"name": "Écritures de ventes", "account_prefixes": ["70"]})
    assert pop.status_code == 201 and pop.json()["item_count"] == 1 and pop.json()["source"] == "ledger", pop.text
    assert client.get(f"{API}/engagements/{e['id']}/ledger/journals", headers=owner.headers).status_code == 200
