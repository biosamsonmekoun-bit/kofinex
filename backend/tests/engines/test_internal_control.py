"""Contrôle interne : cotation, synthèse des conclusions, cohérence des tests, couverture, déficiences, indicateurs,
rapports, modèles et méthodologie (données FICTIVES)."""

from datetime import date

import pytest

from app.engines.audit import control as ic
from app.engines.audit import ic_templates as tpl
from app.engines.audit import methodology as meth

SCALE = {"likelihood": [{"score": s, "label": f"P{s}"} for s in (1, 2, 3)],
         "impact": [{"score": s, "label": f"I{s}"} for s in (1, 2, 3)]}
ALL_YES_OP = {k: {"answer": "yes"} for k in ic.OPERATING_CRITERIA}


def test_cotation_des_risques_sur_la_grille():
    assert ic.risk_rating(SCALE, 3, 2)["score"] == 6
    assert ic.risk_rating(SCALE, None, None)["score"] is None
    assert ic.risk_rating(None, 2, 2)["score"] is None          # pas de grille : aucune cotation inventée
    with pytest.raises(ValueError):
        ic.risk_rating(SCALE, 4, 1)


@pytest.mark.parametrize("design,operating,expected", [
    (None, None, "not_tested"),
    ("effective", None, "not_tested"),                 # la conception seule ne rend jamais un contrôle efficace
    ("effective", "effective", "effective"),
    (None, "effective", "effective"),
    ("partially_effective", "effective", "partially_effective"),
    ("effective", "partially_effective", "partially_effective"),
    ("ineffective", "effective", "ineffective"),
    ("effective", "ineffective", "ineffective"),
    ("not_applicable", None, "not_applicable"),
    ("not_applicable", "not_applicable", "not_applicable"),
    ("effective", "not_tested", "not_tested"),
    ("effective", "not_applicable", "not_tested"),
])
def test_synthese_identique_a_la_regle_sql(design, operating, expected):
    assert ic.combine(design, operating) == expected


def test_niveau_de_maitrise_dernier_test_revu_par_type():
    tests = [
        ic.TestRow("t1", "c1", "operating", "reviewed", "ineffective", "2026-01-10", engagement_id="e1"),
        ic.TestRow("t2", "c1", "operating", "reviewed", "effective", "2026-06-10", engagement_id="e2"),
        ic.TestRow("t3", "c1", "design", "reviewed", "effective", "2026-05-01", engagement_id="e2"),
        ic.TestRow("t4", "c2", "operating", "prepared", "effective", None, engagement_id="e2"),   # non revu : ignoré
    ]
    st = ic.control_status(["c1", "c2", "c3"], tests)
    assert st["c1"]["conclusion"] == "effective" and st["c1"]["operating_test_id"] == "t2"
    assert st["c2"]["conclusion"] == "not_tested"
    assert st["c3"]["conclusion"] == "not_tested"
    # historique conservé : la mission e1 seule conclut à l'inefficacité
    assert ic.control_status(["c1"], tests, engagement_id="e1")["c1"]["conclusion"] == "ineffective"


def test_evaluation_de_la_conception():
    answers = {k: {"answer": "yes"} for k in ic.DESIGN_CRITERIA}
    chk = ic.check_test(test_type="design", answers=answers, items=[], sample_size=None, tolerable=None, has_period=False,
                        has_evidence=True, rationale="Conception adaptée")
    assert "effective" in chk.allowed
    answers["independent"] = {"answer": "no"}
    chk = ic.check_test(test_type="design", answers=answers, items=[], sample_size=None, tolerable=None, has_period=False,
                        has_evidence=True, rationale="Manque d'indépendance")
    assert "effective" not in chk.allowed and "partially_effective" in chk.allowed and chk.negative == ["independent"]
    with pytest.raises(ValueError):
        ic.check_test(test_type="design", answers={"inconnu": {"answer": "yes"}}, items=[], sample_size=None, tolerable=None,
                      has_period=False, has_evidence=True, rationale="x")


def test_evaluation_de_l_efficacite_operationnelle():
    base = dict(test_type="operating", answers=ALL_YES_OP, sample_size=3, tolerable=0, has_period=True, has_evidence=True,
                rationale="Conforme")
    ok = ic.check_test(items=["compliant"] * 3, **base)
    assert "effective" in ok.allowed
    pending = ic.check_test(items=["compliant", "pending", "compliant"], **base)
    assert {"effective", "partially_effective", "ineffective"}.isdisjoint(pending.allowed)
    assert "not_tested" in pending.allowed
    short = ic.check_test(items=["compliant"] * 2, **base)
    assert "effective" not in short.allowed
    exc = ic.check_test(items=["compliant", "compliant", "exception"], **base)
    assert "effective" not in exc.allowed and "ineffective" in exc.allowed
    tolerated = ic.check_test(items=["compliant", "compliant", "exception"], **{**base, "tolerable": 1})
    assert "effective" in tolerated.allowed
    no_ev = ic.check_test(items=["compliant"] * 3, **{**base, "has_evidence": False})
    assert "effective" not in no_ev.allowed
    no_period = ic.check_test(items=["compliant"] * 3, **{**base, "has_period": False})
    assert "effective" not in no_period.allowed
    no_reason = ic.check_test(items=["compliant"] * 3, **{**base, "rationale": ""})
    assert no_reason.allowed == []                    # non applicable et non testé exigent aussi une justification


CTL = [ic.ControlRef("c1", "C1", "Approbation", "existing", "active", True),
       ic.ControlRef("c2", "C2", "Revue fichier", "expected", "active", False),
       ic.ControlRef("c3", "C3", "Rapprochement", "existing", "active", False),
       ic.ControlRef("c4", "C4", "Ancien", "existing", "retired", False)]
RSK = [ic.RiskRef("r1", "R1", "Commande non autorisée"), ic.RiskRef("r2", "R2", "Fournisseur fictif"),
       ic.RiskRef("r3", "R3", "Sans contrôle"), ic.RiskRef("r4", "R4", "Retiré", status="retired")]
LINKS = [{"control_id": "c1", "risk_id": "r1", "coverage": "full"}, {"control_id": "c3", "risk_id": "r1", "coverage": "partial"},
         {"control_id": "c2", "risk_id": "r2", "coverage": "full"}]


def test_matrice_et_couverture():
    st = {"c1": {"conclusion": "effective"}, "c2": {"conclusion": "not_tested"}, "c3": {"conclusion": "partially_effective"},
          "c4": {"conclusion": "not_tested"}}
    m = ic.matrix(RSK, CTL, LINKS, st, {"c1": 2})
    assert {r["risk_code"] for r in m["rows"]} == {"R1", "R2", "R3"}
    r1 = [r for r in m["rows"] if r["risk_code"] == "R1"]
    assert len(r1) == 2 and all(r["indicator"] == "effective" for r in r1)
    assert next(r for r in r1 if r["control_code"] == "C1")["evidence_count"] == 2
    # R2 : seul un contrôle attendu (manquant) ; R3 : aucun contrôle
    assert {u["code"] for u in m["uncovered_risks"]} == {"R2", "R3"}
    assert next(u for u in m["uncovered_risks"] if u["code"] == "R2")["expected_controls"] == ["C2"]
    assert next(r for r in m["rows"] if r["risk_code"] == "R2")["missing"] is True
    assert [o["code"] for o in m["orphan_controls"]] == []
    assert ic.risk_indicator([("partial", "effective")]) == "partial"
    assert ic.risk_indicator([("full", "ineffective")]) == "ineffective"
    assert ic.risk_indicator([("full", "not_tested")]) == "not_tested"


def test_identification_des_deficiences():
    st = {"c1": {"conclusion": "ineffective"}, "c2": {"conclusion": "not_tested"}, "c3": {"conclusion": "partially_effective"}}
    m = ic.matrix(RSK, CTL, LINKS, st)
    cands = ic.deficiency_candidates(CTL, st, {"c3"}, m["uncovered_risks"])
    kinds = {(c["type"], c.get("code")) for c in cands}
    assert ("test_result", "C1") in kinds                 # inefficace, contrôle clé
    assert ("missing_control", "C2") in kinds
    assert ("test_result", "C3") not in kinds             # une déficience le vise déjà
    assert ("uncovered_risk", "R3") in kinds
    assert all(c.get("code") != "C4" for c in cands)       # retiré


def test_etapes_du_cycle_des_deficiences():
    assert ic.lifecycle_stage("draft", False, []) == "draft"
    assert ic.lifecycle_stage("communicated", False, []) == "communicated"
    assert ic.lifecycle_stage("communicated", True, []) == "responded"
    assert ic.lifecycle_stage("communicated", True, ["planned"]) == "action_planned"
    assert ic.lifecycle_stage("communicated", True, ["in_progress", "planned"]) == "implementation"
    assert ic.lifecycle_stage("communicated", True, ["implemented", "planned"]) == "implementation"
    assert ic.lifecycle_stage("communicated", True, ["implemented"]) == "verification"
    assert ic.lifecycle_stage("communicated", True, ["verified"]) == "verification"
    assert ic.lifecycle_stage("closed", True, ["verified"]) == "closed"


def test_indicateurs_du_tableau_de_bord():
    st = {"c1": {"conclusion": "effective"}, "c2": {"conclusion": "not_tested"}, "c3": {"conclusion": "ineffective"},
          "c4": {"conclusion": "not_tested"}}
    levels = [{"code": "D1", "label": "Majeure", "rank": 1}, {"code": "D2", "label": "Mineure", "rank": 2}]
    k = ic.dashboard(domains=[{}, {}], processes=[{}] * 5, risks=RSK, controls=CTL, status=st, links=LINKS,
                     deficiencies=[{"status": "communicated", "rating_code": "D1"}, {"status": "validated", "rating_code": "D2"},
                                   {"status": "closed", "rating_code": "D1"}, {"status": "draft", "rating_code": "D1"}],
                     action_plans=[{"status": "planned", "due_date": date(2026, 1, 1)},
                                   {"status": "verified", "due_date": date(2026, 1, 1)},
                                   {"status": "implemented", "due_date": date(2027, 1, 1)},
                                   {"status": "in_progress", "due_date": date(2027, 1, 1)}],
                     deficiency_levels=levels, assessed_domain_ids={"d1"}, today=date(2026, 6, 1))
    assert (k["domains"], k["domains_assessed"], k["processes"], k["risks"]) == (2, 1, 5, 3)
    assert (k["controls_existing"], k["controls_missing"], k["controls_tested"]) == (2, 1, 2)
    assert (k["effective"], k["ineffective"], k["effective_rate"]) == (1, 1, 50.0)
    assert k["uncovered_risks"] == 2
    assert k["deficiencies_top_level"] == 1 and k["deficiencies_open"] == 2      # clos et brouillon exclus
    assert k["action_plans_overdue"] == 1
    assert (k["implementation_rate"], k["verified_rate"]) == (50.0, 25.0)
    empty = ic.dashboard(domains=[], processes=[], risks=[], controls=[], status={}, links=[], deficiencies=[],
                         action_plans=[], deficiency_levels=[], assessed_domain_ids=set(), today=date(2026, 6, 1))
    assert empty["effective_rate"] is None and empty["implementation_rate"] is None   # pas de taux sans données


def test_structure_de_rapport_et_csv():
    sec = ic.section("controls", "Contrôles", [("code", "Code"), ("conclusion", "Conclusion")],
                     [{"code": "C1", "conclusion": "Efficace", "extra": "x"}, {"code": "C2", "conclusion": None}])
    rep = ic.report("ineffective_controls", title_suffix="Achats", filters={}, generated_at="2026-11-18T00:00:00Z",
                    sections=[sec], sources={"reviewed_tests": 1})
    assert rep["title"] == "État des contrôles inefficaces — Achats" and rep["rule"] == ic.RULE
    assert ic.csv_rows(sec) == [["Code", "Conclusion"], ["C1", "Efficace"], ["C2", ""]]
    with pytest.raises(ValueError):
        ic.report("inconnu", title_suffix=None, filters={}, generated_at="", sections=[], sources={})


def test_modeles_de_domaines():
    assert len(tpl.ACCOUNTING) == 8 and len(tpl.ORGANIZATIONAL) == 9
    ach = tpl.TEMPLATES["ACH"]
    assert ach.processes[0] == "Expression des besoins" and len(ach.processes) == 12
    assert tpl.process_codes(ach)[0] == ("ACH-01", "Expression des besoins")
    assert len({t.code for t in tpl.ACCOUNTING + tpl.ORGANIZATIONAL}) == 17


def test_methodologie_referentiels_et_echelles():
    rows = [["type", "code", "libelle", "parent", "contenu", "ordre"],
            ["ic_component", "CMP", "Composante", "", "", "1"],
            ["ic_principle", "P1", "Principe", "CMP", "", "2"],
            ["ic_requirement", "EX1", "Exigence", "P1", "", "3"],
            ["ic_criterion", "CR1", "Critère", "EX1", "", "4"],
            ["control_level_scale", "NIV", "Maîtrise", "", '{"levels":[{"code":"M1","label":"A","rank":1},'
                                                            '{"code":"M2","label":"B","rank":2}]}', "5"],
            ["deficiency_scale", "DEF", "Déficiences", "", '{"levels":[{"code":"D1","label":"Majeure"}]}', "6"]]
    rep = meth.parse_rows(rows)
    assert rep.ok, rep.issues
    assert [lv["code"] for lv in meth.scale_levels(rep.items, "control_level_scale")] == ["M1", "M2"]
    bad = meth.parse_rows(rows[:1] + [["ic_criterion", "CR9", "Critère orphelin", "ZZ", "", "1"],
                                      ["control_level_scale", "N", "x", "", '{"levels":[{"code":"A","label":"a","rank":1},'
                                                                            '{"code":"B","label":"b"}]}', "2"]])
    assert not bad.ok and len(bad.issues) == 2
    warn = meth.publication_issues([i for i in rep.items if i.item_type != "control_level_scale"], "internal_control")
    assert any("control_level_scale" in i.message for i in warn)
