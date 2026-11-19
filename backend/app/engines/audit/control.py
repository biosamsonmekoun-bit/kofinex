"""Contrôle interne : critères d'évaluation, synthèse des conclusions, couverture des risques, matrice
risques-contrôles, cohérence des tests, identification des déficiences, indicateurs, structures de rapport.

Règles :
- un contrôle n'est jamais « efficace » parce qu'il est déclaré existant : il faut un test d'efficacité
  opérationnelle revu et concluant (règle IC-SYNTH-1, identique à la fonction SQL public.ic_combine) ;
- aucun seuil n'est fixé ici : les grilles, échelles, tailles d'échantillon et tolérances viennent de la
  méthodologie ou du jugement motivé de l'utilisateur ;
- les indicateurs sont des comptages sur les données enregistrées ; le moteur ne rédige aucune conclusion.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date

from app.engines.audit.methodology import rate

RULE = "IC-SYNTH-1"
CONCLUSIONS = ("effective", "partially_effective", "ineffective", "not_tested", "not_applicable")
CONCLUSION_LABELS = {
    "effective": "Efficace",
    "partially_effective": "Partiellement efficace",
    "ineffective": "Inefficace",
    "not_tested": "Non testé",
    "not_applicable": "Non applicable",
}
DESIGN_LABELS = {
    "effective": "Conception adéquate",
    "partially_effective": "Conception partiellement adéquate",
    "ineffective": "Conception inadéquate",
    "not_tested": "Non testé",
    "not_applicable": "Non applicable",
}
ANSWERS = ("yes", "no", "partial", "na")
DESIGN_CRITERIA = {
    "responds_to_risk": "Répond réellement au risque identifié",
    "well_defined": "Est correctement défini",
    "owner_assigned": "Est attribué à un responsable",
    "frequency_adequate": "Dispose d'une fréquence adaptée",
    "documented": "Est documenté",
    "independent": "Est suffisamment indépendant",
    "prevents_or_detects": "Permet de prévenir ou de détecter le risque",
}
OPERATING_CRITERIA = {
    "performed": "A réellement été exécuté",
    "right_person": "A été exécuté par la bonne personne",
    "right_frequency": "A été réalisé à la bonne fréquence",
    "evidence_produced": "A produit les preuves attendues",
    "supervised": "A été correctement supervisé",
    "anomalies_handled": "A permis de détecter ou prévenir les anomalies",
}
TEST_METHODS = {
    "document_review": "Examen documentaire",
    "observation": "Observation",
    "inquiry": "Entretien",
    "inspection": "Inspection",
    "reconciliation": "Rapprochement",
    "recalculation": "Recalcul",
    "reperformance": "Réexécution",
    "data_analysis": "Analyse de données",
}
EXISTENCE_LABELS = {"existing": "Existant", "expected": "Attendu", "not_formalized": "Non formalisé", "absent": "Absent"}
FREQUENCY_LABELS = {
    "on_occurrence": "À chaque opération",
    "daily": "Quotidienne",
    "weekly": "Hebdomadaire",
    "monthly": "Mensuelle",
    "quarterly": "Trimestrielle",
    "semiannual": "Semestrielle",
    "annual": "Annuelle",
    "ad_hoc": "Ponctuelle",
}
IC_ROLES = {
    "ic_manager": "Responsable du contrôle interne",
    "daf": "Directeur administratif et financier",
    "domain_owner": "Responsable de domaine",
    "process_owner": "Responsable de processus",
    "control_performer": "Exécutant du contrôle",
    "supervisor": "Superviseur",
    "observer": "Observateur",
}
SCOPES = ("overall", "domain", "process", "cycle", "component", "risk", "control")
COVERING = ("existing", "not_formalized")


def criteria(test_type: str) -> dict[str, str]:
    return DESIGN_CRITERIA if test_type == "design" else OPERATING_CRITERIA


# ------------------------------------------------------------------ synthèse des conclusions
def combine(design: str | None, operating: str | None) -> str:
    """Conclusion d'un contrôle à partir des derniers tests revus de conception et d'efficacité."""
    if design is None and operating is None:
        return "not_tested"
    if (design or "not_applicable") == "not_applicable" and (operating or "not_applicable") == "not_applicable":
        return "not_applicable"
    if "ineffective" in (design, operating):
        return "ineffective"
    if operating is None or operating in ("not_tested", "not_applicable"):
        return "not_tested"
    if "partially_effective" in (design, operating):
        return "partially_effective"
    return "effective"


@dataclass(frozen=True)
class TestRow:
    id: str
    control_id: str
    test_type: str
    status: str
    conclusion: str | None
    reviewed_at: object = None  # datetime ou chaîne ISO (ordre)
    period_end: date | None = None
    engagement_id: str | None = None


def control_status(control_ids: list[str], tests: list[TestRow], engagement_id: str | None = None) -> dict[str, dict]:
    """Par contrôle : dernier test revu de chaque type (toutes missions, ou une seule) et conclusion combinée."""
    latest: dict[tuple[str, str], TestRow] = {}
    for t in tests:
        if t.status != "reviewed" or (engagement_id and t.engagement_id != engagement_id):
            continue
        k = (t.control_id, t.test_type)
        cur = latest.get(k)
        if cur is None or (str(t.reviewed_at), t.id) > (str(cur.reviewed_at), cur.id):
            latest[k] = t
    out = {}
    for cid in control_ids:
        d, o = latest.get((cid, "design")), latest.get((cid, "operating"))
        out[cid] = {
            "design": d.conclusion if d else None,
            "operating": o.conclusion if o else None,
            "conclusion": combine(d.conclusion if d else None, o.conclusion if o else None),
            "operating_test_id": o.id if o else None,
            "operating_period_end": o.period_end if o else None,
        }
    return out


# ------------------------------------------------------------------ cohérence d'un test (miroir de la base)
@dataclass
class TestCheck:
    items: int
    pending: int
    compliant: int
    exceptions: int
    not_applicable: int
    answered: int
    missing: list[str]
    negative: list[str]
    blockers: dict[str, list[str]] = field(default_factory=dict)  # conclusion -> raisons qui l'interdisent

    @property
    def allowed(self) -> list[str]:
        return [c for c in CONCLUSIONS if not self.blockers.get(c)]


def check_test(
    *,
    test_type: str,
    answers: dict,
    items: list[str],
    sample_size: int | None,
    tolerable: int | None,
    has_period: bool,
    has_evidence: bool,
    rationale: str | None,
) -> TestCheck:
    """items : résultats des éléments (pending | compliant | exception | not_applicable)."""
    crit = criteria(test_type)
    unknown = [k for k in answers if k not in crit]
    if unknown:
        raise ValueError(f"Critère(s) inconnu(s) : {', '.join(unknown)}.")
    for k, v in answers.items():
        if not isinstance(v, dict) or v.get("answer") not in ANSWERS:
            raise ValueError(f"Réponse invalide pour « {k} » (yes, no, partial, na).")
    c = Counter(items)
    missing = [k for k in crit if k not in answers]
    negative = [k for k, v in answers.items() if v["answer"] in ("no", "partial")]
    chk = TestCheck(
        len(items), c["pending"], c["compliant"], c["exception"], c["not_applicable"], len(answers), missing, negative
    )
    common = []
    if not rationale or len(rationale.strip()) < 3:
        common.append("Justification de la conclusion requise.")
    concluding = []
    if test_type == "operating" and not has_period:
        concluding.append("Période examinée requise.")
    if c["pending"]:
        concluding.append(f"{c['pending']} élément(s) sélectionné(s) non testé(s).")
    if sample_size is not None and len(items) < sample_size:
        concluding.append(f"{len(items)} élément(s) testé(s) pour un échantillon de {sample_size}.")
    eff = []
    if c["exception"] > (tolerable or 0):
        eff.append(f"{c['exception']} exception(s) pour {tolerable or 0} tolérée(s) par les critères d'acceptation.")
    if missing or negative:
        eff.append("Tous les critères doivent être évalués, sans réponse négative ou partielle.")
    if not has_evidence:
        eff.append("Au moins un élément probant rattaché au test.")
    for concl in CONCLUSIONS:
        reasons = list(common)
        if concl in ("effective", "partially_effective", "ineffective"):
            reasons += concluding
        if concl == "effective":
            reasons += eff
        chk.blockers[concl] = reasons
    return chk


# ------------------------------------------------------------------ couverture des risques et matrice
@dataclass(frozen=True)
class ControlRef:
    id: str
    code: str
    title: str
    existence: str
    operational_status: str
    is_key: bool
    owner_name: str | None = None
    frequency: str | None = None
    expected_evidence: str | None = None
    domain_id: str | None = None
    process_id: str | None = None


@dataclass(frozen=True)
class RiskRef:
    id: str
    code: str
    title: str
    status: str = "active"
    domain_id: str | None = None
    process_id: str | None = None
    objective_id: str | None = None


def is_covering(c: ControlRef) -> bool:
    return c.existence in COVERING and c.operational_status == "active"


def risk_indicator(conclusions: list[tuple[str, str]]) -> str:
    """Indicateur factuel de couverture d'un risque à partir de ses contrôles couvrants (couverture, conclusion) :
    uncovered | not_tested | ineffective | partial | effective. Ce n'est pas le niveau de maîtrise, qui reste
    apprécié par l'évaluateur sur l'échelle de la méthodologie."""
    if not conclusions:
        return "uncovered"
    concl = [c for _, c in conclusions]
    if any(cov == "full" and c == "effective" for cov, c in conclusions):
        return "effective"
    if any(c in ("effective", "partially_effective") for c in concl):
        return "partial"
    if any(c == "ineffective" for c in concl):
        return "ineffective"
    return "not_tested"


INDICATOR_LABELS = {
    "uncovered": "Non couvert",
    "not_tested": "Couvert, non testé",
    "ineffective": "Couvert par des contrôles inefficaces",
    "partial": "Partiellement couvert",
    "effective": "Couvert par un contrôle efficace",
}


def matrix(
    risks: list[RiskRef],
    controls: list[ControlRef],
    links: list[dict],
    status: dict[str, dict],
    evidence_counts: dict[str, int] | None = None,
) -> dict:
    """Matrice risques-contrôles. links : {control_id, risk_id, coverage}. status : sortie de control_status.
    Rend une ligne par couple risque × contrôle, les risques non couverts et les contrôles orphelins."""
    evidence_counts = evidence_counts or {}
    ctl = {c.id: c for c in controls}
    by_risk: dict[str, list[dict]] = {}
    linked_controls = set()
    for lk in links:
        if lk["control_id"] in ctl:
            by_risk.setdefault(lk["risk_id"], []).append(lk)
            linked_controls.add(lk["control_id"])
    rows, uncovered = [], []
    for r in risks:
        if r.status != "active":
            continue
        lks = by_risk.get(r.id, [])
        covering = [
            (lk.get("coverage", "full"), status.get(lk["control_id"], {}).get("conclusion", "not_tested"))
            for lk in lks
            if is_covering(ctl[lk["control_id"]])
        ]
        ind = risk_indicator(covering)
        if not covering:
            uncovered.append(
                {
                    "risk_id": r.id,
                    "code": r.code,
                    "title": r.title,
                    "expected_controls": [
                        ctl[lk["control_id"]].code for lk in lks if ctl[lk["control_id"]].existence in ("expected", "absent")
                    ],
                }
            )
        if not lks:
            rows.append({"risk_id": r.id, "risk_code": r.code, "risk_title": r.title, "control_id": None, "indicator": ind})
        for lk in lks:
            c = ctl[lk["control_id"]]
            st = status.get(c.id, {})
            rows.append(
                {
                    "risk_id": r.id,
                    "risk_code": r.code,
                    "risk_title": r.title,
                    "control_id": c.id,
                    "control_code": c.code,
                    "control_title": c.title,
                    "existence": c.existence,
                    "missing": c.existence in ("expected", "absent"),
                    "operational_status": c.operational_status,
                    "is_key": c.is_key,
                    "owner": c.owner_name,
                    "frequency": c.frequency,
                    "expected_evidence": c.expected_evidence,
                    "coverage": lk.get("coverage", "full"),
                    "design": st.get("design"),
                    "operating": st.get("operating"),
                    "conclusion": st.get("conclusion", "not_tested"),
                    "evidence_count": evidence_counts.get(c.id, 0),
                    "indicator": ind,
                }
            )
    orphans = [
        {"control_id": c.id, "code": c.code, "title": c.title}
        for c in controls
        if c.id not in linked_controls and c.operational_status != "retired"
    ]
    return {"rows": rows, "uncovered_risks": uncovered, "orphan_controls": orphans}


def risk_rating(scale: dict | None, likelihood: int | None, impact: int | None) -> dict:
    """Cotation d'un risque sur la grille versionnée (score et caractère significatif selon la grille)."""
    if scale is None:
        return {"score": None, "significant": None}
    return rate(scale, likelihood, impact)


# ------------------------------------------------------------------ déficiences
def deficiency_candidates(
    controls: list[ControlRef], status: dict[str, dict], deficient_control_ids: set[str], uncovered: list[dict]
) -> list[dict]:
    """Points à examiner pour une éventuelle déficience (le jugement et la rédaction restent humains) :
    contrôle inefficace ou partiellement efficace, contrôle attendu absent, risque non couvert — sauf si une
    déficience vise déjà le contrôle."""
    out = []
    for c in controls:
        if c.id in deficient_control_ids or c.operational_status == "retired":
            continue
        concl = status.get(c.id, {}).get("conclusion")
        if concl in ("ineffective", "partially_effective"):
            out.append(
                {
                    "type": "test_result",
                    "control_id": c.id,
                    "code": c.code,
                    "title": c.title,
                    "detail": CONCLUSION_LABELS[concl] + (" (contrôle clé)" if c.is_key else ""),
                }
            )
        elif c.existence in ("absent", "expected"):
            out.append(
                {
                    "type": "missing_control",
                    "control_id": c.id,
                    "code": c.code,
                    "title": c.title,
                    "detail": EXISTENCE_LABELS[c.existence],
                }
            )
    for r in uncovered:
        out.append(
            {
                "type": "uncovered_risk",
                "risk_id": r["risk_id"],
                "code": r["code"],
                "title": r["title"],
                "detail": "Aucun contrôle existant ne couvre ce risque",
            }
        )
    return out


FINDING_STAGES = ("draft", "validated", "communicated", "responded", "action_planned", "implementation", "verification", "closed")
STAGE_LABELS = {
    "draft": "Brouillon",
    "validated": "Validée",
    "communicated": "Communiquée",
    "responded": "Réponse reçue",
    "action_planned": "Plan d'action",
    "implementation": "Mise en œuvre",
    "verification": "Vérification",
    "closed": "Clôturée",
}


def lifecycle_stage(status: str, has_response: bool, plan_statuses: list[str]) -> str:
    """Étape du cycle Brouillon → … → Clôture d'une déficience, à partir de son statut et de ses plans d'action."""
    if status in ("draft", "validated", "closed"):
        return status
    if not plan_statuses:
        return "responded" if has_response else "communicated"
    if all(s in ("verified", "risk_accepted") for s in plan_statuses):
        return "verification"
    if any(s == "implemented" for s in plan_statuses):
        return (
            "verification" if all(s in ("implemented", "verified", "risk_accepted") for s in plan_statuses) else "implementation"
        )
    if any(s == "in_progress" for s in plan_statuses):
        return "implementation"
    return "action_planned"


# ------------------------------------------------------------------ tableau de bord
def dashboard(
    *,
    domains: list[dict],
    processes: list[dict],
    risks: list[RiskRef],
    controls: list[ControlRef],
    status: dict[str, dict],
    links: list[dict],
    deficiencies: list[dict],
    action_plans: list[dict],
    deficiency_levels: list[dict],
    assessed_domain_ids: set[str],
    today: date,
) -> dict:
    """Indicateurs calculés sur les données réelles (déjà filtrées par l'appelant).
    deficiencies : {status, rating_code} ; action_plans : {status, due_date} ; deficiency_levels : échelle de la méthodologie."""
    active_controls = [c for c in controls if c.operational_status != "retired"]
    existing = [c for c in active_controls if c.existence in COVERING]
    concl = Counter(status.get(c.id, {}).get("conclusion", "not_tested") for c in existing)
    tested = sum(v for k, v in concl.items() if k != "not_tested")
    concluded = concl["effective"] + concl["partially_effective"] + concl["ineffective"]
    m = matrix(risks, controls, links, status)
    by_level = Counter(d.get("rating_code") for d in deficiencies if d.get("status") in ("validated", "communicated"))
    levels = [
        {"code": lv["code"], "label": lv["label"], "rank": lv.get("rank"), "open": by_level.get(lv["code"], 0)}
        for lv in deficiency_levels
    ]
    top_rank = min((lv["rank"] for lv in levels if lv["rank"] is not None), default=None)
    overdue = sum(1 for a in action_plans if a["status"] in ("planned", "in_progress") and a["due_date"] < today)
    done = sum(1 for a in action_plans if a["status"] in ("verified",))
    implemented = sum(1 for a in action_plans if a["status"] in ("implemented", "verified"))
    return {
        "rule": RULE,
        "domains": len(domains),
        "domains_assessed": len(assessed_domain_ids),
        "processes": len(processes),
        "risks": sum(1 for r in risks if r.status == "active"),
        "controls_existing": len(existing),
        "controls_missing": sum(1 for c in active_controls if c.existence in ("expected", "absent")),
        "controls_tested": tested,
        "effective": concl["effective"],
        "partially_effective": concl["partially_effective"],
        "ineffective": concl["ineffective"],
        "not_tested": concl["not_tested"],
        "not_applicable": concl["not_applicable"],
        # taux sur les contrôles ayant une conclusion d'efficacité (non testés et non applicables exclus)
        "effective_rate": (round(concl["effective"] / concluded * 100, 1) if concluded else None),
        "uncovered_risks": len(m["uncovered_risks"]),
        "deficiency_levels": levels,
        "deficiencies_top_level": (sum(lv["open"] for lv in levels if lv["rank"] == top_rank) if top_rank is not None else None),
        "deficiencies_open": sum(1 for d in deficiencies if d.get("status") in ("validated", "communicated")),
        "action_plans": len(action_plans),
        "action_plans_overdue": overdue,
        "implementation_rate": (round(implemented / len(action_plans) * 100, 1) if action_plans else None),
        "verified_rate": (round(done / len(action_plans) * 100, 1) if action_plans else None),
    }


# ------------------------------------------------------------------ rapports (structures pour le lot 11)
REPORT_KINDS = {
    "assessment": "Rapport d'évaluation du contrôle interne",
    "domain": "Rapport par domaine",
    "process": "Rapport par processus",
    "cycle": "Rapport par cycle comptable",
    "risk_map": "Cartographie des risques",
    "matrix": "Matrice risques-contrôles",
    "ineffective_controls": "État des contrôles inefficaces",
    "deficiencies": "Rapport des déficiences",
    "remediation": "Suivi des plans de remédiation",
}


def section(key: str, title: str, columns: list[tuple[str, str]], rows: list[dict]) -> dict:
    return {
        "key": key,
        "title": title,
        "columns": [{"key": k, "label": lbl} for k, lbl in columns],
        "rows": [{k: r.get(k) for k, _ in columns} for r in rows],
    }


def report(kind: str, *, title_suffix: str | None, filters: dict, generated_at: str, sections: list[dict], sources: dict) -> dict:
    """Structure neutre d'un rapport (titre, filtres, sections tabulaires, sources), réutilisable par les exports
    PDF, Excel et Word du lot 11. Aucune phrase n'est générée : les textes sont ceux enregistrés."""
    if kind not in REPORT_KINDS:
        raise ValueError(f"Rapport inconnu « {kind} ».")
    title = REPORT_KINDS[kind] + (f" — {title_suffix}" if title_suffix else "")
    return {
        "kind": kind,
        "title": title,
        "generated_at": generated_at,
        "filters": filters,
        "rule": RULE,
        "sections": sections,
        "sources": sources,
    }


def csv_rows(sec: dict) -> list[list[str]]:
    head = [c["label"] for c in sec["columns"]]
    body = [["" if r.get(c["key"]) is None else str(r.get(c["key"])) for c in sec["columns"]] for r in sec["rows"]]
    return [head, *body]
