"""Socle d'audit : méthodologie (données FICTIVES de test), circuits, supervision, éléments probants."""

import io
import json
import zipfile

import pytest

from app.engines.audit.evidence import safe_filename, validate_evidence
from app.engines.audit.methodology import parse_rows, publication_issues, rate, risk_scale
from app.engines.audit.workflow import capabilities, next_statuses, reviewer_allowed, supervise
from app.engines.importing.files import FileRejected

SCALE = json.dumps({"likelihood": [{"score": 1, "label": "Faible"}, {"score": 2, "label": "Moyen"}, {"score": 3, "label": "Élevé"}],
                    "impact": [{"score": 1, "label": "Faible"}, {"score": 2, "label": "Moyen"}, {"score": 3, "label": "Élevé"}],
                    "significant_from": 6})
ROWS = [
    ["type", "code", "libelle", "parent", "contenu", "ordre"],
    ["assertion", "EX", "Existence (test)", "", "", "1"],
    ["assertion", "EH", "Exhaustivité (test)", "", "", "2"],
    ["cycle", "VEN", "Ventes (test)", "", json.dumps({"account_prefixes": ["70", "41"]}), "1"],
    ["risk_scale", "GRILLE", "Grille (test)", "", SCALE, ""],
    ["procedure_template", "VEN-01", "Rapprochement (test)", "",
     json.dumps({"nature": "detail_test", "objective": "Test", "steps": ["Étape 1"], "cycle": "VEN", "assertions": ["EX"]}), ""],
]


def test_methodologie_valide_et_cotation():
    rep = parse_rows(ROWS)
    assert rep.ok, rep.issues
    assert len(rep.items) == 5
    assert not [i for i in publication_issues(rep.items, "audit") if i.severity == "error"]
    scale = risk_scale(rep.items)
    assert rate(scale, 3, 2) == {"score": 6, "significant": True}
    assert rate(scale, 1, 2) == {"score": 2, "significant": False}
    with pytest.raises(ValueError, match="hors grille"):
        rate(scale, 4, 1)


def test_methodologie_references_et_contenu_controles():
    rows = [ROWS[0], ["procedure_template", "X", "x", "", json.dumps({"nature": "magie", "cycle": "ABS", "assertions": ["ZZ"]}), ""],
            ["assertion", "EX", "x", "", "", ""], ["assertion", "EX", "doublon", "", "", ""],
            ["risk_scale", "G", "g", "", '{"likelihood": [{"score": 0}]}', ""], ["inconnu", "Y", "y", "", "", ""],
            ["cycle", "C1", "c", "PARENT", "{pas du json", ""]]
    msgs = " | ".join(i.message for i in parse_rows(rows).issues)
    for expected in ("nature « magie »", "cycle « ABS »", "assertion « ZZ »", "en double", "score entier", "Type inconnu",
                     "JSON illisible"):
        assert expected in msgs, msgs
    assert any("grille de cotation" in i.message for i in publication_issues([], "audit"))


def test_circuits_et_capacites():
    assert next_statuses("planning", "manager") == ["fieldwork"]
    assert next_statuses("planning", "in_charge") == []
    assert next_statuses("reporting", "partner") == ["review", "issued"]
    assert capabilities("staff", False, "fieldwork") == ["confirm_independence"]
    assert "sign_reviewer" not in capabilities("staff", True, "fieldwork")
    # mission émise : lecture et suivi des plans d'action uniquement (lot 8)
    # lot 9 : la clôture d'un constat remédié reste possible après l'émission (suivi)
    assert capabilities("manager", True, "issued") == ["read_dossier", "read_findings", "follow_up", "verify_actions",
                                                       "close_findings"]
    assert capabilities("auditee", False, "issued") == ["read_findings", "follow_up"]
    assert capabilities("auditee", False, "fieldwork") == ["read_findings", "respond_findings", "follow_up"]
    assert reviewer_allowed("staff", "in_charge") and not reviewer_allowed("in_charge", "in_charge")
    assert reviewer_allowed("in_charge", "manager") and not reviewer_allowed("staff", "quality_reviewer")


def test_supervision_et_conditions_d_emission():
    s = supervise(workpapers=[{"status": "approved"}, {"status": "prepared"}], procedures=[{"status": "done"}],
                  notes=[{"status": "answered"}], risks=[{"id": "r1", "code": "R1", "title": "t", "is_significant": True},
                                                       {"id": "r2", "code": "R2", "title": "t", "is_significant": False}],
                  coverage={"r1": 1}, members=[{"role": "manager", "independent": True, "name": "M"},
                                               {"role": "quality_reviewer", "independent": False, "name": "Q"}],
                  engagement_signoffs=[])
    checks = {c.code: c.passed for c in s.issuance_checks}
    assert checks == {"WORKPAPERS_APPROVED": False, "REVIEW_NOTES_CLOSED": False, "RISKS_COVERED": False,
                      "PROCEDURES_DONE": True, "INDEPENDENCE": False, "QUALITY_REVIEW": False, "PARTNER_APPROVAL": False}
    assert [r["code"] for r in s.risks_uncovered] == ["R2"] and s.significant_uncovered == 0
    assert not s.ready_to_issue


def _docx(macro=False):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("[Content_Types].xml", "<Types/>")
        zf.writestr("word/document.xml", "<w:document/>")
        if macro:
            zf.writestr("word/vbaProject.bin", b"\x00")
    return buf.getvalue()


def test_validation_des_elements_probants():
    assert validate_evidence("facture.pdf", b"%PDF-1.7\n...").mime_type == "application/pdf"
    assert validate_evidence("note.docx", _docx()).extension == "docx"
    assert len(validate_evidence("releve.csv", "compte;montant\n411;10\n".encode()).sha256) == 64
    for name, data, msg in [("x.docx", _docx(macro=True), "macros"), ("x.pdf", b"MZ\x90", "PDF"),
                            ("x.exe", b"MZ", "non accepté"), ("x.png", b"%PDF", "PNG"), ("x.txt", b"a\x00b", "binaires"),
                            ("x.pdf", b"", "vide")]:
        with pytest.raises(FileRejected, match=msg):
            validate_evidence(name, data)
    assert safe_filename("../../etc/pass wd.pdf") == "pass wd.pdf"
    assert safe_filename("C:\\docs\\relevé.pdf") == "relevé.pdf"
