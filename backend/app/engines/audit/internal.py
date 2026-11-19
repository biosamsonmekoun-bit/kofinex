"""Audit interne : carte des risques, synthèse du plan annuel, ordre et statistiques des constats, échéances du
suivi, export Word du rapport.

Aucune échelle n'est fixée ici : la grille de cotation des risques et l'échelle des constats viennent de la
méthodologie. Le rapport ne contient que ce que l'équipe a saisi et validé ; aucun texte n'est rédigé par le moteur.
"""

from __future__ import annotations

import io
from collections import Counter
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.engines.audit.methodology import rate

OPEN_ACTION = ("planned", "in_progress")
ACTION_LABELS = {"planned": "Prévue", "in_progress": "En cours", "implemented": "Mise en œuvre (déclarée)",
                 "verified": "Mise en œuvre vérifiée", "not_implemented": "Non mise en œuvre", "risk_accepted": "Risque accepté"}
PLAN_ITEM_LABELS = {"planned": "Prévue", "in_progress": "En cours", "completed": "Réalisée", "postponed": "Reportée",
                    "cancelled": "Annulée"}


# ------------------------------------------------------------------ carte des risques
@dataclass(frozen=True)
class RatedRisk:
    id: str
    code: str
    title: str
    process_code: str | None
    likelihood: int | None
    impact: int | None


def risk_map(risks: list[RatedRisk], scale: dict) -> dict:
    """Matrice probabilité × impact sur les niveaux de la grille : chaque case liste les risques qui y sont cotés.
    Les risques non cotés sont rendus à part ; une cotation hors grille est une erreur signalée, jamais corrigée."""
    lik = sorted(lv["score"] for lv in scale.get("likelihood", []))
    imp = sorted(lv["score"] for lv in scale.get("impact", []))
    cells: dict[tuple[int, int], list[dict]] = {(a, b): [] for a in lik for b in imp}
    unrated, invalid = [], []
    for r in risks:
        if r.likelihood is None or r.impact is None:
            unrated.append({"id": r.id, "code": r.code, "title": r.title})
            continue
        try:
            sc = rate(scale, r.likelihood, r.impact)
        except ValueError as exc:
            invalid.append({"id": r.id, "code": r.code, "title": r.title, "message": str(exc)})
            continue
        cells[(r.likelihood, r.impact)].append({"id": r.id, "code": r.code, "title": r.title, "process": r.process_code,
                                                "score": sc["score"], "significant": sc["significant"]})
    thr = scale.get("significant_from")
    return {
        "likelihood": [{"score": lv["score"], "label": lv["label"]}
                       for lv in sorted(scale["likelihood"], key=lambda x: x["score"])],
        "impact": [{"score": lv["score"], "label": lv["label"]} for lv in sorted(scale["impact"], key=lambda x: x["score"])],
        "significant_from": thr if isinstance(thr, int) else None,
        "cells": [{"likelihood": a, "impact": b, "score": a * b,
                   "significant": (a * b >= thr) if isinstance(thr, int) else None, "risks": cells[(a, b)]}
                  for a in lik for b in imp],
        "unrated": unrated, "invalid": invalid,
    }


# ------------------------------------------------------------------ plan annuel
def plan_summary(items: list[dict]) -> dict:
    by = Counter(i["status"] for i in items)
    budget = sum((Decimal(str(i["budget_days"])) for i in items if i.get("budget_days") is not None), Decimal(0))
    done = sum((Decimal(str(i["budget_days"])) for i in items if i.get("budget_days") is not None and i["status"] == "completed"),
               Decimal(0))
    active = [i for i in items if i["status"] != "cancelled"]
    return {"items": len(items), "by_status": dict(by), "budget_days": budget, "completed_budget_days": done,
            "added_after_approval": sum(1 for i in items if i.get("added_after_approval")),
            "completion_rate": (Decimal(by.get("completed", 0)) / Decimal(len(active)) * 100).quantize(Decimal("0.1"))
            if active else None}


# ------------------------------------------------------------------ constats et suivi
def order_findings(findings: list[dict], levels: list[dict]) -> list[dict]:
    """Du plus grave (rang de l'échelle) au moins grave, puis par référence ; les constats sans cotation en dernier."""
    rank = {lv["code"]: lv["rank"] for lv in levels}
    return sorted(findings, key=lambda f: (rank.get(f.get("rating_code"), 10**6), f["reference"]))


def rating_counts(findings: list[dict], levels: list[dict]) -> list[dict]:
    c = Counter(f.get("rating_code") for f in findings)
    out = [{"code": lv["code"], "label": lv["label"], "rank": lv["rank"], "count": c.get(lv["code"], 0)} for lv in levels]
    if c.get(None):
        out.append({"code": None, "label": "Non coté", "rank": None, "count": c[None]})
    return out


def is_overdue(status: str, due: date, today: date) -> bool:
    return status in OPEN_ACTION and due < today


def follow_up_summary(actions: list[dict], today: date) -> dict:
    by = Counter(a["status"] for a in actions)
    return {"total": len(actions), "by_status": dict(by),
            "overdue": sum(1 for a in actions if is_overdue(a["status"], a["due_date"], today)),
            "closed": by.get("verified", 0) + by.get("risk_accepted", 0)}


# ------------------------------------------------------------------ rapport Word
def _fr_date(v: object) -> str:
    if not v:
        return ""
    s = str(v)[:10]
    y, m, d = s.split("-")
    return f"{d}/{m}/{y}"


def render_docx(snap: dict, draft: bool) -> bytes:
    """Rapport au format Word, à partir du contenu assemblé (figé si le rapport est émis). Un projet porte la mention
    « PROJET » en tête et en pied de chaque page."""
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Pt

    doc = Document()
    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(10.5)
    sec = doc.sections[0]
    mention = "PROJET — document de travail non émis" if draft else f"Rapport émis le {_fr_date(snap.get('issued_at'))}"
    sec.header.paragraphs[0].text = f"{snap['engagement']['reference']} — {mention}"
    sec.footer.paragraphs[0].text = (f"Version {snap['version']}"
                                     + (f" · empreinte {snap['content_sha256'][:16]}…" if snap.get("content_sha256") else ""))

    e = snap["engagement"]
    t = doc.add_heading(snap["title"], level=0)
    t.alignment = WD_ALIGN_PARAGRAPH.LEFT
    if draft:
        p = doc.add_paragraph()
        r = p.add_run("PROJET")
        r.bold = True
    doc.add_paragraph(f"Entité auditée : {e['company']}")
    doc.add_paragraph(f"Mission : {e['reference']} — {e['name']}")
    if e.get("period_start") or e.get("period_end"):
        doc.add_paragraph(f"Période couverte : du {_fr_date(e.get('period_start'))} au {_fr_date(e.get('period_end'))}")
    if snap.get("methodology"):
        m = snap["methodology"]
        doc.add_paragraph(f"Méthodologie : {m['name']} {m['version_label']} (source : {m['source_reference']})")

    def section(title: str, text: str | None) -> None:
        if text:
            doc.add_heading(title, level=1)
            for para in str(text).split("\n"):
                if para.strip():
                    doc.add_paragraph(para.strip())

    section("Synthèse", snap.get("executive_summary"))
    section("Objectifs", e.get("objectives"))
    section("Périmètre", e.get("scope"))
    section("Conclusion générale", snap.get("overall_conclusion"))

    if snap.get("rating_counts"):
        doc.add_heading("Constats par niveau", level=1)
        tbl = doc.add_table(rows=1, cols=2)
        tbl.style = "Table Grid"
        tbl.rows[0].cells[0].text, tbl.rows[0].cells[1].text = "Niveau", "Nombre"
        for rc in snap["rating_counts"]:
            row = tbl.add_row().cells
            row[0].text, row[1].text = rc["label"], str(rc["count"])

    doc.add_heading("Constats et recommandations", level=1)
    if not snap["findings"]:
        doc.add_paragraph("Aucun constat.")
    for f in snap["findings"]:
        rating = f" [{f['rating_label']}]" if f.get("rating_label") else ""
        doc.add_heading(f"{f['reference']} — {f['title']}{rating}", level=2)
        for label, key in (("Constat", "condition"), ("Référentiel", "criteria"), ("Cause", "cause"), ("Conséquence", "effect")):
            if f.get(key):
                p = doc.add_paragraph()
                p.add_run(f"{label} : ").bold = True
                p.add_run(f[key])
        if f.get("process"):
            doc.add_paragraph(f"Processus : {f['process']}")
        for rec in f["recommendations"]:
            p = doc.add_paragraph()
            p.add_run(f"Recommandation {rec['reference']} : ").bold = True
            p.add_run(rec["text"])
            for a in rec["action_plans"]:
                doc.add_paragraph(f"Plan d'action : {a['description']} — responsable : {a['owner_name']} — échéance : "
                                  f"{_fr_date(a['due_date'])} — {ACTION_LABELS.get(a['status'], a['status'])}",
                                  style="List Bullet")
        p = doc.add_paragraph()
        p.add_run("Réponse de la direction : ").bold = True
        if f.get("management_response"):
            p.add_run(f"{f['management_response']} ({f['response_by_name']}, {_fr_date(f.get('response_at'))})")
        else:
            p.add_run("non reçue à la date du rapport.")

    if snap.get("distribution"):
        section("Diffusion", snap["distribution"])
    if not draft:
        doc.add_paragraph(f"Émis par {snap.get('issued_by_name', '')} le {_fr_date(snap.get('issued_at'))}.")
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()
