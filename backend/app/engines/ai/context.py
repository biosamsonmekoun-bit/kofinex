"""Contextes transmis au modèle : uniquement des données structurées, déjà calculées par les moteurs de KOFINEX et
autorisées pour l'utilisateur (la lecture passe par la RLS). Chaque valeur chiffrée devient un « fait » numéroté
([F1], [F2]…) que le modèle doit citer. Le contexte exact est conservé avec la réponse."""

from __future__ import annotations

import json
from dataclasses import dataclass, field

MAX_STATEMENT_LINES = 150
MAX_LIST = 40


@dataclass
class Fact:
    ref: str
    label: str
    value: str | None
    unit: str | None = None
    period: str | None = None
    source: str | None = None

    def as_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v is not None}


@dataclass
class Context:
    purpose: str
    title: str
    facts: list[Fact] = field(default_factory=list)
    data: dict = field(default_factory=dict)

    def add(self, label: str, value, *, unit: str | None = None, period: str | None = None, source: str | None = None) -> str:
        ref = f"F{len(self.facts) + 1}"
        self.facts.append(Fact(ref, label, None if value is None else str(value), unit, period, source))
        return ref

    @property
    def refs(self) -> set[str]:
        return {f.ref for f in self.facts} | set(self.data.get("refs", []))

    def snapshot(self) -> dict:
        return {"purpose": self.purpose, "title": self.title, "facts": [f.as_dict() for f in self.facts], "data": self.data}

    def to_prompt(self) -> str:
        return json.dumps(self.snapshot(), ensure_ascii=False, indent=1, default=str)


# ------------------------------------------------------------------ finance
def finance(company: dict, fiscal_year: dict, analysis: dict, previous_label: str | None = None) -> Context:
    """Analyse financière terminée (états, indicateurs, alertes) : sortie de `services.analysis.analysis_detail`."""
    ctx = Context("finance", f"{company.get('name')} — exercice {fiscal_year.get('label')}")
    period, prev = fiscal_year.get("label"), previous_label or "N-1"
    ctx.data["entity"] = {"name": company.get("name"), "framework": company.get("framework"), "currency": company.get("currency")}
    ctx.data["fiscal_year"] = {
        "label": fiscal_year.get("label"),
        "start": str(fiscal_year.get("start_date")),
        "end": str(fiscal_year.get("end_date")),
    }
    for ind in analysis.get("indicators", []):
        if ind.get("status") not in (None, "ok") and ind.get("value") is None:
            ctx.data.setdefault("indicators_not_computed", []).append(
                {"code": ind.get("code"), "name": ind.get("name"), "status": ind.get("status"), "message": ind.get("message")}
            )
            continue
        ctx.add(
            f"{ind.get('name')} ({ind.get('code')})", ind.get("value"), unit=ind.get("unit"), period=period, source="indicateur"
        )
        if ind.get("previous_value") is not None:
            ctx.add(
                f"{ind.get('name')} ({ind.get('code')})",
                ind.get("previous_value"),
                unit=ind.get("unit"),
                period=prev,
                source="indicateur",
            )
    n = 0
    for stype, lines in (analysis.get("statements") or {}).items():
        for ln in lines:
            if ln.get("net") is None or n >= MAX_STATEMENT_LINES or (ln.get("level") or 0) > 1:
                continue
            n += 1
            ctx.add(f"{stype} — {ln.get('label')} ({ln.get('code')})", ln.get("net"), unit="amount", period=period, source="état")
            if ln.get("previous") is not None:
                ctx.add(
                    f"{stype} — {ln.get('label')} ({ln.get('code')})",
                    ln.get("previous"),
                    unit="amount",
                    period=prev,
                    source="état",
                )
    ctx.data["alerts"] = [
        {"severity": a.get("severity"), "title": a.get("title"), "message": a.get("message")}
        for a in (analysis.get("alerts") or [])[:MAX_LIST]
    ]
    ctx.data["controls"] = analysis.get("controls")
    return ctx


# ------------------------------------------------------------------ audit
def _engagement(e: dict) -> dict:
    return {k: e.get(k) for k in ("reference", "name", "engagement_type", "objectives", "scope", "period_start", "period_end")}


def audit_risks(
    engagement: dict,
    registry_risks: list[dict],
    engagement_risks: list[dict],
    cycles: list[dict],
    assertions: list[dict],
    finance_ctx: Context | None = None,
) -> Context:
    ctx = Context("engagement_risk", f"Risques — mission {engagement.get('reference')}")
    ctx.data["engagement"] = _engagement(engagement)
    ctx.data["registry_risks"] = [
        {"code": r.get("code"), "title": r.get("title"), "description": r.get("description"), "process": r.get("process")}
        for r in registry_risks[:MAX_LIST]
    ]
    ctx.data["existing_engagement_risks"] = [{"code": r.get("code"), "title": r.get("title")} for r in engagement_risks]
    ctx.data["cycles"] = [{"code": c.get("code"), "label": c.get("label")} for c in cycles]
    ctx.data["assertions"] = [{"code": a.get("code"), "label": a.get("label")} for a in assertions]
    if finance_ctx:
        ctx.facts = list(finance_ctx.facts)
        ctx.data["alerts"] = finance_ctx.data.get("alerts", [])
    return ctx


def audit_procedures(engagement: dict, templates: list[dict], engagement_risks: list[dict], existing_codes: list[str]) -> Context:
    ctx = Context("procedure", f"Procédures — mission {engagement.get('reference')}")
    ctx.data["engagement"] = _engagement(engagement)
    ctx.data["procedure_templates"] = [
        {"code": t.get("code"), "label": t.get("label"), **(t.get("content") or {})}
        for t in templates
        if t.get("code") not in existing_codes
    ]
    ctx.data["engagement_risks"] = [
        {
            "code": r.get("code"),
            "title": r.get("title"),
            "description": r.get("description"),
            "cycle_code": r.get("cycle_code"),
            "assertion_codes": r.get("assertion_codes"),
            "likelihood": r.get("likelihood"),
            "impact": r.get("impact"),
            "is_significant": r.get("is_significant"),
        }
        for r in engagement_risks
    ]
    return ctx


def finding_draft(engagement: dict, source: dict, levels: list[dict]) -> Context:
    """source : feuille de travail, test de contrôle ou exécution, avec ses résultats enregistrés."""
    ctx = Context("finding_draft", f"Projet de constat — mission {engagement.get('reference')}")
    ctx.data["engagement"] = _engagement(engagement)
    ctx.data["source"] = source
    ctx.data["rating_levels_for_information"] = [{"code": lv.get("code"), "label": lv.get("label")} for lv in levels]
    ctx.data["refs"] = ["S1"]
    return ctx


def synthesis_draft(engagement: dict, findings: list[dict]) -> Context:
    ctx = Context("synthesis_draft", f"Projet de synthèse — mission {engagement.get('reference')}")
    ctx.data["engagement"] = _engagement(engagement)
    refs = []
    items = []
    for i, f in enumerate(findings, 1):
        ref = f"C{i}"
        refs.append(ref)
        items.append(
            {
                "ref": ref,
                "reference": f.get("reference"),
                "title": f.get("title"),
                "condition": f.get("condition"),
                "criteria": f.get("criteria"),
                "cause": f.get("cause"),
                "effect": f.get("effect"),
                "rating": f.get("rating_label"),
                "recommendations": f.get("recommendations", []),
                "management_response": f.get("management_response"),
            }
        )
    ctx.data["validated_findings"] = items
    ctx.data["refs"] = refs
    return ctx


def anomalies(engagement: dict, fiscal_year: dict, analytics: dict) -> Context:
    """Résultats des analyses déterministes du grand livre (services.ledger.analytics) : l'IA explique et classe,
    elle ne détecte rien."""
    ctx = Context("anomaly_explanation", f"Analyses du grand livre — {fiscal_year.get('label')}")
    ctx.data["engagement"] = _engagement(engagement)
    ctx.data["fiscal_year"] = {
        "label": fiscal_year.get("label"),
        "start": str(fiscal_year.get("start_date")),
        "end": str(fiscal_year.get("end_date")),
    }
    tests = {}
    for key, val in analytics.items():
        if isinstance(val, list):
            ref = ctx.add(f"Analyse « {key} » : éléments relevés", len(val), unit="count", source="analyse du grand livre")
            tests[key] = {"ref": ref, "items": val[:MAX_LIST]}
        elif isinstance(val, dict):
            ref = (
                ctx.add(f"Analyse « {key} » : éléments relevés", val["count"], unit="count", source="analyse du grand livre")
                if val.get("count") is not None
                else None
            )
            tests[key] = {"ref": ref, "summary": {k: (v[:MAX_LIST] if isinstance(v, list) else v) for k, v in val.items()}}
        else:
            tests[key] = {"value": val}
    ctx.data["tests"] = tests
    return ctx
