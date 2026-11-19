"""Audit interne : carte des risques, plan, constats, suivi, rapport Word (données FICTIVES)."""

import io
from datetime import date
from decimal import Decimal as D

from docx import Document

from app.engines.audit import internal as ia
from app.engines.audit import methodology as meth

SCALE = {"likelihood": [{"score": 1, "label": "Faible"}, {"score": 2, "label": "Forte"}],
         "impact": [{"score": 1, "label": "Faible"}, {"score": 2, "label": "Fort"}], "significant_from": 4}
LEVELS = [{"code": "N2", "label": "Mineur", "rank": 2}, {"code": "N1", "label": "Majeur", "rank": 1}]


def _load(levels: str):
    return meth.parse_rows([["type", "code", "libelle", "parent", "contenu", "ordre"],
                            ["finding_scale", "E", "Échelle", "", '{"levels":' + levels + "}", "1"]])


def test_finding_scale_validation():
    assert not [i for i in _load('[{"code":"A","label":"a","rank":1}]').issues if i.severity == "error"]
    dup = _load('[{"code":"A","label":"a","rank":1},{"code":"B","label":"b","rank":1}]')
    assert any("uniques" in i.message for i in dup.issues)
    assert any(i.severity == "error" for i in _load('[{"code":"A","label":"a","rank":"1"}]').issues)
    assert [lv["code"] for lv in meth.finding_levels([{"item_type": "finding_scale", "content": {"levels": LEVELS}}])] == ["N1", "N2"]


def test_risk_map_cells_unrated_and_invalid():
    risks = [ia.RatedRisk("1", "R1", "Fraude", "ACH", 2, 2), ia.RatedRisk("2", "R2", "Retard", None, 1, 2),
             ia.RatedRisk("3", "R3", "Non coté", None, None, None), ia.RatedRisk("4", "R4", "Hors grille", None, 3, 1)]
    m = ia.risk_map(risks, SCALE)
    cell = {(c["likelihood"], c["impact"]): c for c in m["cells"]}
    assert len(m["cells"]) == 4
    assert [r["code"] for r in cell[(2, 2)]["risks"]] == ["R1"] and cell[(2, 2)]["significant"] is True
    assert cell[(1, 2)]["risks"][0]["score"] == 2 and cell[(1, 2)]["significant"] is False
    assert [r["code"] for r in m["unrated"]] == ["R3"] and m["invalid"][0]["code"] == "R4"


def test_plan_summary():
    items = [{"status": "completed", "budget_days": "10"}, {"status": "planned", "budget_days": 5.5},
             {"status": "cancelled", "budget_days": None, "added_after_approval": True}]
    s = ia.plan_summary(items)
    assert s["budget_days"] == D("15.5") and s["completed_budget_days"] == D("10")
    assert s["completion_rate"] == D("50.0") and s["added_after_approval"] == 1


def test_findings_order_counts_and_follow_up():
    f = [{"reference": "C2", "rating_code": "N2"}, {"reference": "C3", "rating_code": None}, {"reference": "C1", "rating_code": "N1"}]
    assert [x["reference"] for x in ia.order_findings(f, LEVELS)] == ["C1", "C2", "C3"]
    counts = ia.rating_counts(f, sorted(LEVELS, key=lambda lv: lv["rank"]))
    assert [(c["code"], c["count"]) for c in counts] == [("N1", 1), ("N2", 1), (None, 1)]
    today = date(2027, 7, 1)
    acts = [{"status": "planned", "due_date": date(2027, 6, 30)}, {"status": "implemented", "due_date": date(2027, 1, 1)},
            {"status": "verified", "due_date": date(2027, 1, 1)}]
    s = ia.follow_up_summary(acts, today)
    assert s["overdue"] == 1 and s["closed"] == 1


def _snap(**kw):
    base = {"title": "Rapport d'audit des achats (test)", "version": 1, "executive_summary": "Synthèse saisie.",
            "overall_conclusion": "Conclusion saisie par l'auditeur.", "distribution": "Direction générale",
            "engagement": {"reference": "AI-1", "name": "Audit des achats", "company": "Filiale test", "objectives": "Objectif",
                           "scope": None, "period_start": "2027-01-01", "period_end": "2027-06-30"},
            "methodology": {"name": "Méthode test", "version_label": "v1", "source_reference": "FICTIVE"},
            "rating_counts": [{"label": "Majeur", "count": 1}],
            "findings": [{"reference": "C1", "title": "Fournisseurs sans contrôle", "rating_label": "Majeur", "condition": "12 créations",
                          "criteria": "Double validation", "cause": None, "effect": "Fraude possible", "process": "ACH — Achats",
                          "management_response": None, "response_by_name": None, "response_at": None,
                          "recommendations": [{"reference": "R1.1", "text": "Paramétrer la double validation",
                                               "action_plans": [{"description": "Paramétrage", "owner_name": "Resp. achats",
                                                                 "due_date": "2027-06-30", "status": "planned"}]}]}]}
    base.update(kw)
    return base


def test_render_docx_draft_and_issued():
    draft = Document(io.BytesIO(ia.render_docx(_snap(), draft=True)))
    text = "\n".join(p.text for p in draft.paragraphs)
    assert "PROJET" in text and "C1 — Fournisseurs sans contrôle [Majeur]" in text
    assert "non reçue à la date du rapport" in text and "30/06/2027" in text
    assert "PROJET" in draft.sections[0].header.paragraphs[0].text
    issued = Document(io.BytesIO(ia.render_docx(_snap(issued_at="2027-07-15T10:00:00", content_sha256="ab" * 32,
                                                      issued_by_name="Paul (test)"), draft=False)))
    itext = "\n".join(p.text for p in issued.paragraphs)
    assert "PROJET" not in itext and "Émis par Paul (test) le 15/07/2027." in itext
    assert "abababab" in issued.sections[0].footer.paragraphs[0].text
