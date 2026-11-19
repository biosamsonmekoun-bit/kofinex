"""Lecture stricte des réponses structurées du modèle : JSON attendu, champs bornés, références et codes vérifiés
contre le contexte. Une proposition non conforme est écartée et la raison est conservée ; rien n'est complété."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from app.engines.ai import numbers
from app.engines.ai.context import Context

MAX_ITEMS = {"engagement_risk": 8, "procedure": 10, "finding_draft": 3, "synthesis_draft": 1, "anomaly_explanation": 15}
_FIELDS = {
    "engagement_risk": {"code": (1, 40), "title": (3, 300), "description": (0, 4000), "rationale": (3, 4000)},
    "procedure": {"template_code": (1, 40), "rationale": (3, 4000)},
    "finding_draft": {
        "title": (3, 300),
        "condition": (3, 8000),
        "criteria": (3, 8000),
        "cause": (0, 8000),
        "effect": (0, 8000),
        "recommendation": (0, 4000),
    },
    "synthesis_draft": {"title": (3, 300), "text": (3, 20000)},
    "anomaly_explanation": {"test": (1, 80), "explanation": (3, 4000), "what_to_examine": (0, 4000)},
}
_REQUIRED = {
    "engagement_risk": ("code", "title", "rationale"),
    "procedure": ("template_code", "rationale"),
    "finding_draft": ("title", "condition", "criteria"),
    "synthesis_draft": ("title", "text"),
    "anomaly_explanation": ("test", "explanation"),
}


class ParseError(ValueError):
    pass


@dataclass
class Parsed:
    payload: dict
    sources: list[str]
    validation: dict
    issues: list[str] = field(default_factory=list)


def extract_json(text: str) -> dict:
    t = (text or "").strip()
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", t, re.S)
    if fence:
        t = fence.group(1)
    start, end = t.find("{"), t.rfind("}")
    if start < 0 or end <= start:
        raise ParseError("Réponse du modèle sans objet JSON.")
    try:
        data = json.loads(t[start : end + 1])
    except json.JSONDecodeError as exc:
        raise ParseError(f"JSON invalide dans la réponse du modèle ({exc.msg}).") from exc
    if not isinstance(data, dict) or not isinstance(data.get("suggestions"), list):
        raise ParseError("Réponse du modèle : liste « suggestions » attendue.")
    return data


def _str(v) -> str | None:
    if v is None:
        return None
    if not isinstance(v, str):
        return None
    v = v.strip()
    return v or None


def suggestions(kind: str, text: str, ctx: Context) -> tuple[list[Parsed], list[str]]:
    """Propositions retenues et raisons des propositions écartées."""
    data = extract_json(text)
    kept: list[Parsed] = []
    rejected: list[str] = []
    refs = ctx.refs
    templates = {t["code"] for t in ctx.data.get("procedure_templates", [])}
    risk_codes = {r["code"] for r in ctx.data.get("engagement_risks", [])}
    cycles = {c["code"] for c in ctx.data.get("cycles", [])}
    assertions = {a["code"] for a in ctx.data.get("assertions", [])}
    existing = {r["code"] for r in ctx.data.get("existing_engagement_risks", [])}
    tests = set(ctx.data.get("tests", {}))
    for i, raw in enumerate(data["suggestions"][: MAX_ITEMS[kind]], 1):
        why = f"Proposition {i}"
        if not isinstance(raw, dict):
            rejected.append(f"{why} : objet attendu.")
            continue
        payload: dict = {}
        bad = None
        for name, (lo, hi) in _FIELDS[kind].items():
            v = _str(raw.get(name))
            if v is None:
                if name in _REQUIRED[kind]:
                    bad = f"{why} : champ « {name} » manquant."
                    break
                continue
            if not lo <= len(v) <= hi:
                bad = f"{why} : champ « {name} » hors des longueurs admises."
                break
            payload[name] = v
        if bad:
            rejected.append(bad)
            continue
        src = [s for s in raw.get("sources") or [] if isinstance(s, str)]
        unknown = [s for s in src if s not in refs]
        if unknown:
            rejected.append(f"{why} : références absentes du contexte ({', '.join(unknown)}).")
            continue
        if kind == "engagement_risk":
            if payload["code"] in existing:
                rejected.append(f"{why} : risque « {payload['code']} » déjà présent dans la mission.")
                continue
            cyc = _str(raw.get("cycle_code"))
            if cyc and cyc not in cycles:
                rejected.append(f"{why} : cycle « {cyc} » absent de la méthodologie.")
                continue
            ass = [a for a in raw.get("assertion_codes") or [] if isinstance(a, str)]
            if any(a not in assertions for a in ass):
                rejected.append(f"{why} : assertion absente de la méthodologie.")
                continue
            payload.update(cycle_code=cyc, assertion_codes=ass)
        elif kind == "procedure":
            if payload["template_code"] not in templates:
                rejected.append(f"{why} : programme type « {payload['template_code']} » absent de la méthodologie.")
                continue
            rc = [c for c in raw.get("risk_codes") or [] if isinstance(c, str)]
            if any(c not in risk_codes for c in rc):
                rejected.append(f"{why} : risque cité absent de la mission.")
                continue
            payload["risk_codes"] = rc
        elif kind == "anomaly_explanation":
            if payload["test"] not in tests:
                rejected.append(f"{why} : test « {payload['test']} » absent des analyses.")
                continue
            rank = raw.get("rank")
            payload["rank"] = rank if isinstance(rank, int) and 1 <= rank <= 100 else i
        prose = " ".join(v for k, v in payload.items() if isinstance(v, str) and k not in ("code", "template_code", "test"))
        kept.append(Parsed(payload, src, numbers.check(prose, ctx.snapshot())))
    return kept, rejected
