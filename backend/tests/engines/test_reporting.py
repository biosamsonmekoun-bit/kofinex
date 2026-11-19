"""Moteur de reporting : constructeurs (données reprises sans calcul), avertissements IA, modèles, empreintes,
rendus PDF / Excel / Word relus par leurs bibliothèques, mise en forme française."""

import io
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.engines.reporting import builders as b
from app.engines.reporting import document as d
from app.engines.reporting import render as r

FY = {"label": "2025", "start": "2025-01-01", "end": "2025-12-31"}
ANALYSIS = {
    "id": "a1",
    "completed_at": "2026-01-10T10:00:00",
    "engine_version": "1",
    "source_import_job_id": "j1",
    "controls": {
        "statements": [{"code": "BALANCE_SHEET_EQUILIBRIUM", "status": "passed", "message": "Équilibré"}],
        "cross_checks": [],
    },
    "statements": {
        "balance_sheet": [{"code": "BZ", "label": "Total actif", "level": 0, "net": "5400000.00", "previous": "5100000.00"}]
    },
    "indicators": [
        {"code": "CAF", "name": "CAF", "unit": "amount", "value": "1250000.5", "previous_value": "980000"},
        {"code": "R", "name": "Ratio", "unit": "ratio", "value": None, "message": "Division par zéro"},
    ],
    "alerts": [{"severity": "warning", "title": "Trésorerie négative", "message": "TN < 0"}],
}
REVIEWED = {
    "id": "c1",
    "section": "cash",
    "status": "reviewed",
    "content": "Commentaire relu.",
    "model": "m",
    "prompt_version": "v",
    "reviewed_by_name": "Alice",
    "reviewed_at": "2026-01-11",
}
DRAFT = {**REVIEWED, "id": "c2", "status": "draft", "content": "Brouillon non relu."}
META = {"generated_at": datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc), "generated_by": "Carl", "branding": {}}


def _fin(ai=(), tpl=None):
    return b.financial({"entity": "Société test", "fiscal_year": FY}, ANALYSIS, list(ai), tpl)


def _meta(doc, **kw):
    return {**META, "data_sha256": d.data_digest(doc), **kw}


def test_mise_en_forme_francaise():
    assert d.fmt("1250000.5", "amount") == "1 250 000,50"
    assert d.fmt("-45000", "amount") == "-45 000,00"
    assert d.fmt("87.25", "percent") == "87,3 %" or d.fmt("87.25", "percent") == "87,2 %"
    assert d.fmt(None, "amount") == "—" and d.fmt("2025-12-31", "date") == "31/12/2025" and d.fmt("12", "number") == "12"


def test_rapport_financier_reprend_les_valeurs_sans_calcul():
    doc = _fin([REVIEWED])
    titles = [s["title"] for s in doc["sections"]]
    assert titles == ["Contrôles de l'analyse", "Bilan", "Indicateurs", "Alertes", "Commentaires"]
    bilan = doc["sections"][1]["blocks"][0]["rows"][0]
    assert (bilan["net"], bilan["previous"]) == ("5400000.00", "5100000.00")
    ind = doc["sections"][2]["blocks"][0]["rows"]
    assert ind[1]["value"] == "Division par zéro"  # jamais estimé
    assert doc["notices"] == [] and {s["type"] for s in doc["sources"]} == {"analysis", "trial_balance_import", "ai_report"}


def test_brouillon_ia_signale_en_tete_et_sur_place():
    doc = _fin([DRAFT])
    assert doc["notices"][0]["text"] == b.AI_DRAFT_NOTICE
    blocks = doc["sections"][-1]["blocks"]
    assert any(x["kind"] == "notice" and "non relu" in x["text"] for x in blocks)


def test_modele_titre_textes_et_sections():
    tpl = {
        "name": "Annuel",
        "version": 2,
        "sections": ["statements"],
        "content": {"title": "Rapport annuel 2025", "intro": "Mot du DAF.", "closing": "Document interne."},
    }
    doc = _fin([REVIEWED], tpl)
    assert doc["title"] == "Rapport annuel 2025" and doc["template"] == {"name": "Annuel", "version": 2}
    assert [s["title"] for s in doc["sections"]] == ["Introduction", "Bilan", "Mentions"]


def test_empreinte_des_donnees_independante_du_format_et_de_la_date():
    a, c = _fin([REVIEWED]), _fin([REVIEWED])
    c["template"] = {"name": "x", "version": 1}
    assert d.data_digest(a) == d.data_digest(c)
    assert d.data_digest(a) != d.data_digest(_fin([DRAFT]))


@pytest.mark.parametrize("fmt", ["pdf", "xlsx", "docx"])
def test_rendus_relisibles_et_deterministes(fmt):
    doc = _fin([DRAFT])
    meta = _meta(doc)
    data = r.render(doc, fmt, meta)
    assert data == r.render(doc, fmt, meta)
    if fmt == "pdf":
        from pypdf import PdfReader

        text = "".join(p.extract_text() for p in PdfReader(io.BytesIO(data)).pages).replace("\xa0", " ")
        assert "ATTENTION" in text and meta["data_sha256"][:16] in text and "5 400 000,00" in text
    elif fmt == "xlsx":
        from openpyxl import load_workbook

        wb = load_workbook(io.BytesIO(data))
        assert wb.sheetnames[0] == "Synthèse" and wb.sheetnames[-1] == "Sources"
        bilan = wb[next(n for n in wb.sheetnames if "Bilan" in n)]
        assert [c.value for c in bilan[2]] == ["BZ", "Total actif", 5400000, 5100000]  # nombres, pas du texte
        assert any(meta["data_sha256"] in str(c.value) for row in wb["Sources"].iter_rows() for c in row)
    else:
        import docx

        w = docx.Document(io.BytesIO(data))
        assert w.paragraphs[0].text == doc["title"] and len(w.tables) == 4
        assert meta["data_sha256"][:16] in w.sections[0].footer.paragraphs[0].text


def test_couleur_du_modele_appliquee():
    doc = _fin()
    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(r.render(doc, "xlsx", _meta(doc, branding={"primary_color": "#2563EB"}))))
    assert wb[wb.sheetnames[1]]["A1"].fill.fgColor.rgb.endswith("2563EB")


def test_suivi_budgetaire():
    tr = {
        "fiscal_year": "2025",
        "balance_import_job_id": "j1",
        "ledger_import_job_id": None,
        "warnings": ["Ligne sans réalisé"],
        "conventions": ["Écart = réalisé − budget."],
        "totals": {"charge": {"budget": "100", "actual": "90", "variance": "-10"}},
        "rows": [
            {
                "label": "Achats",
                "account_prefix": "60",
                "nature": "charge",
                "budget": "100",
                "actual": "90",
                "variance": "-10",
                "realization_pct": "90.0",
                "favorable": True,
            }
        ],
    }
    doc = b.budget({"entity": "S", "budget": {"id": "b1", "name": "Budget", "version": 1, "approved_at": "2025-01-05"}}, tr)
    rows = doc["sections"][0]["blocks"][0]["rows"]
    assert rows[0]["variance"] == "-10" and rows[0]["favorable"] == "favorable"
    assert doc["sources"][0] == {"type": "budget", "id": "b1", "label": "Budget approuvé le 05/01/2025", "version": 1}


def test_rapport_de_controle_interne_reprend_la_structure_du_lot_9():
    rep = {
        "kind": "matrix",
        "title": "Matrice risques-contrôles",
        "rule": "IC-SYNTH-1",
        "filters": {"domain_id": None},
        "sources": {"risks": 2},
        "sections": [
            {"key": "matrix", "title": "Matrice", "columns": [{"key": "risk", "label": "Risque"}], "rows": [{"risk": "R1"}]},
            {"key": "uncovered", "title": "Non couverts", "columns": [], "rows": []},
        ],
    }
    doc = b.internal_control({"entity": "S"}, rep)
    assert doc["subtype"] == "matrix" and doc["sections"][1]["blocks"][0]["text"] == "Aucune donnée enregistrée."


def test_rapport_d_audit_interne_emis():
    snap = {
        "title": "Rapport",
        "version": 1,
        "issued_at": "2026-03-01",
        "issued_by_name": "Paul",
        "overall_conclusion": "Conclusion.",
        "engagement": {"reference": "M1", "name": "Achats", "company": "S", "objectives": None, "scope": None},
        "rating_counts": [{"label": "Majeur", "count": 1}],
        "findings": [
            {
                "reference": "C1",
                "title": "Constat",
                "condition": "x",
                "criteria": "y",
                "rating_label": "Majeur",
                "recommendations": [
                    {
                        "reference": "R1",
                        "text": "Faire",
                        "action_plans": [
                            {"description": "Plan", "owner_name": "DAF", "due_date": "2026-06-30", "status": "planned"}
                        ],
                    }
                ],
                "management_response": None,
            }
        ],
    }
    doc = b.internal_audit({"id": "r1", "snapshot": snap, "content_sha256": "c" * 64})
    assert doc["sources"][0]["content_sha256"] == "c" * 64
    assert any(s["title"] == "Conclusion générale" for s in doc["sections"])


def test_synthese_des_anomalies_sans_opinion():
    summ = {
        "materiality": {"overall": "10000", "performance": "5000", "trivial": "500", "version": 1},
        "items": [
            {
                "reference": "A1",
                "kind": "factual",
                "status": "uncorrected",
                "description": "Cut-off",
                "amount": "12000",
                "effect_result": "-12000",
                "position": "above_overall",
            },
            {"reference": "A2", "kind": "factual", "status": "withdrawn", "description": "x", "amount": "1"},
        ],
        "corrected": {"count": 0},
        "uncorrected": {"count": 1, "effect_result": "-12000", "position": "above_overall", "effects": []},
        "proposed": {"count": 0},
        "conclusion": None,
    }
    doc = b.fa_summary(
        {"engagement": {"id": "e1", "reference": "CAC-1", "name": "Audit"}, "entity": "S"},
        summ,
        {"id": "m1", "benchmark_label": "Total actif", "basis": "Méthode", "approved_at": "2026-01-01"},
    )
    assert "aucune opinion" in doc["notices"][0]["text"]
    items = doc["sections"][1]["blocks"][0]["rows"]
    assert [i["reference"] for i in items] == ["A1"] and items[0]["position"] == "au-dessus du seuil de signification"
    assert doc["sections"][-1]["blocks"][0]["text"] == "Non encore rédigée par l'équipe d'audit."


def test_pdf_caracteres_hors_jeu_remplaces_et_echappes():
    assert r._pdf_text("a → b <c> & d e") == "a -&gt; b &lt;c&gt; &amp; d e"


def test_noms_de_feuilles_uniques_et_valides():
    used: set[str] = set()
    names = [r._sheet_name("1 Bilan: actif/passif [N]" * 3, used), r._sheet_name("1 Bilan: actif/passif [N]" * 3, used)]
    assert len(set(names)) == 2 and all(len(n) <= 31 and not set(n) & set("[]:*?/\\") for n in names)


def test_type_de_colonne_controle():
    with pytest.raises(ValueError):
        d.table([("a", "A", "monnaie")], [])
    assert d.table([("a", "A", "amount")], [{"a": Decimal("1.5")}])["rows"] == [{"a": "1.5"}]


@pytest.mark.parametrize("fmt", ["xlsx", "docx"])
def test_archive_ooxml_datee_de_la_generation_et_non_de_l_horloge(fmt):
    """Régression : openpyxl / python-docx datent les entrées de l'archive (et openpyxl la date de modification) à
    l'heure de l'enregistrement ; deux rendus à quelques secondes d'écart différaient."""
    import io
    import zipfile

    doc = _fin([DRAFT])
    meta = _meta(doc)
    at = meta["generated_at"].replace(tzinfo=None)
    z = zipfile.ZipFile(io.BytesIO(r.render(doc, fmt, meta)))
    assert {i.date_time for i in z.infolist()} == {at.timetuple()[:6]}
    core = z.read("docProps/core.xml").decode()
    assert core.count(at.strftime("%Y-%m-%dT%H:%M:%S")) == 2  # created et modified
