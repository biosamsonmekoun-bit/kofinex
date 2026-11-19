"""Construction des documents à partir des sorties des moteurs existants (aucun calcul, aucun texte inventé).

Les textes rédigés viennent des données enregistrées (constats, conclusions, commentaires relus) ou du modèle de
rapport choisi par l'organisation. Les commentaires IA ne sont repris que s'ils sont relus, ou, sur demande
explicite, comme brouillons signalés en tête du document et à l'endroit du commentaire."""

from __future__ import annotations

from app.engines.reporting import document as d

STATEMENT_LABELS = {
    "balance_sheet": "Bilan",
    "balance_sheet_assets": "Bilan — actif",
    "balance_sheet_liabilities": "Bilan — passif",
    "income_statement": "Compte de résultat",
    "cash_flow": "Tableau des flux de trésorerie",
    "notes": "Notes",
    "off_balance": "Hors bilan",
}
UNIT_TYPE = {"amount": "amount", "ratio": "ratio", "percent": "percent", "days": "number", "times": "ratio"}
UNIT_LABEL = {"amount": "montant", "ratio": "ratio", "percent": "%", "days": "jours", "times": "fois"}
SECTION_LABELS = {
    "executive_summary": "Synthèse",
    "balance_sheet": "Bilan",
    "income_statement": "Compte de résultat",
    "cash": "Trésorerie",
    "ratios": "Ratios",
    "risks": "Points d'attention",
}
CHECK_LABELS = {
    "BALANCE_SHEET_EQUILIBRIUM": "Équilibre du bilan",
    "NET_INCOME_CONSISTENCY": "Résultat bilan = compte de résultat",
    "UNMAPPED_ACCOUNTS": "Comptes non rattachés aux états",
}
CHECK_STATUS = {"passed": "satisfait", "failed": "non satisfait", "skipped": "non applicable"}
FINANCIAL_SECTIONS = ("controls", "statements", "indicators", "alerts", "commentary")
AI_DRAFT_NOTICE = (
    "Ce document contient des commentaires rédigés avec l'IA et NON RELUS : ce sont des brouillons, à vérifier "
    "avant toute diffusion. Ils sont signalés à leur emplacement."
)


def _template(doc: dict, tpl: dict | None) -> tuple[set[str] | None, dict]:
    if not tpl:
        return None, {}
    content = tpl.get("content") or {}
    if content.get("title"):
        doc["title"] = content["title"]
    doc["template"] = {"name": tpl.get("name"), "version": tpl.get("version")}
    enabled = set(tpl.get("sections") or []) or None
    return enabled, content


def _intro(doc: dict, content: dict) -> None:
    if content.get("intro"):
        d.add(d.section(doc, content.get("intro_title") or "Introduction"), d.paragraph(content["intro"]))


def _closing(doc: dict, content: dict) -> None:
    if content.get("closing"):
        d.add(d.section(doc, content.get("closing_title") or "Mentions"), d.paragraph(content["closing"]))


# ------------------------------------------------------------------ rapport financier
def financial(meta: dict, analysis: dict, ai_reports: list[dict], tpl: dict | None = None) -> dict:
    """meta : entity, fiscal_year (label, start, end), previous_label ; analysis : `services.analysis.analysis_detail`."""
    fy = meta["fiscal_year"]
    doc = d.new(
        "financial_report",
        f"Rapport financier — exercice {fy['label']}",
        entity=meta["entity"],
        period=f"du {d.fmt_date(fy['start'])} au {d.fmt_date(fy['end'])}",
    )
    enabled, content = _template(doc, tpl)

    def on(k: str) -> bool:
        return enabled is None or k in enabled

    prev = meta.get("previous_label") or "N-1"
    if any(r["status"] == "draft" for r in ai_reports):
        doc["notices"].append(d.notice(AI_DRAFT_NOTICE))
    _intro(doc, content)
    ctl = analysis.get("controls") or {}
    checks = [*(ctl.get("statements") or []), *(ctl.get("cross_checks") or [])] if isinstance(ctl, dict) else []
    if on("controls") and checks:
        rows = [
            {
                "check": CHECK_LABELS.get(c.get("code"), c.get("code")),
                "status": CHECK_STATUS.get(c.get("status"), c.get("status")),
                "message": c.get("message"),
            }
            for c in checks
            if isinstance(c, dict)
        ]
        d.add(
            d.section(doc, "Contrôles de l'analyse"),
            d.table([("check", "Contrôle", "text"), ("status", "Résultat", "text"), ("message", "Détail", "text")], rows),
        )
    if on("statements"):
        for stype, lines in (analysis.get("statements") or {}).items():
            b = d.section(doc, STATEMENT_LABELS.get(stype, stype))
            rows = [
                {
                    "code": ln.get("code"),
                    "label": (" " * min(int(ln.get("level") or 0), 3)) + (ln.get("label") or ""),
                    "net": ln.get("net"),
                    "previous": ln.get("previous"),
                }
                for ln in lines
            ]
            d.add(
                b,
                d.table(
                    [
                        ("code", "Réf.", "text"),
                        ("label", "Libellé", "text"),
                        ("net", fy["label"], "amount"),
                        ("previous", prev, "amount"),
                    ],
                    rows,
                ),
            )
    if on("indicators") and analysis.get("indicators"):
        b = d.section(doc, "Indicateurs")
        rows = []
        for ind in analysis["indicators"]:
            rows.append(
                {
                    "name": f"{ind.get('name')} ({ind.get('code')})",
                    "unit": UNIT_LABEL.get(ind.get("unit"), ind.get("unit")),
                    "value": d.fmt(ind.get("value"), UNIT_TYPE.get(ind.get("unit"), "number"))
                    if ind.get("value") is not None
                    else (ind.get("message") or "non calculé"),
                    "previous": d.fmt(ind.get("previous_value"), UNIT_TYPE.get(ind.get("unit"), "number"))
                    if ind.get("previous_value") is not None
                    else "",
                }
            )
        d.add(
            b,
            d.table(
                [
                    ("name", "Indicateur", "text"),
                    ("unit", "Unité", "text"),
                    ("value", fy["label"], "text"),
                    ("previous", prev, "text"),
                ],
                rows,
            ),
            d.paragraph(
                "Indicateurs calculés par la bibliothèque de formules versionnée de KOFINEX ; « non calculé » signale une "
                "donnée manquante ou une division par zéro, jamais une estimation.",
                style="note",
            ),
        )
    if on("alerts") and analysis.get("alerts"):
        b = d.section(doc, "Alertes")
        d.add(
            b,
            d.table(
                [("severity", "Niveau", "text"), ("title", "Alerte", "text"), ("message", "Détail", "text")], analysis["alerts"]
            ),
        )
    if on("commentary") and ai_reports:
        b = d.section(doc, "Commentaires")
        for r in ai_reports:
            d.add(b, d.paragraph(SECTION_LABELS.get(r["section"], r["section"]), style="heading"))
            if r["status"] == "draft":
                d.add(b, d.notice("Brouillon IA non relu — à vérifier avant diffusion."))
            else:
                d.add(
                    b,
                    d.paragraph(
                        f"Commentaire rédigé avec l'IA ({r.get('model')}), relu par {r.get('reviewed_by_name') or '—'} "
                        f"le {d.fmt_date(r.get('reviewed_at'))}.",
                        style="note",
                    ),
                )
            d.add(b, d.paragraph(r["content"]))
    _closing(doc, content)
    doc["sources"] = [
        {
            "type": "analysis",
            "id": str(analysis["id"]),
            "label": f"Analyse terminée le {d.fmt_date(analysis.get('completed_at'))}",
            "engine_version": analysis.get("engine_version"),
        },
        {
            "type": "trial_balance_import",
            "id": str(analysis.get("source_import_job_id")),
            "label": "Balance validée de l'exercice",
        },
    ]
    doc["sources"] += [
        {
            "type": "ai_report",
            "id": str(r["id"]),
            "label": f"Commentaire IA ({r['status']})",
            "model": r.get("model"),
            "prompt_version": r.get("prompt_version"),
        }
        for r in ai_reports
    ]
    return doc


# ------------------------------------------------------------------ suivi budgétaire
def budget(meta: dict, tracking: dict, tpl: dict | None = None) -> dict:
    b0 = meta["budget"]
    doc = d.new(
        "budget_report",
        f"Suivi budgétaire — {b0['name']} (version {b0['version']})",
        entity=meta["entity"],
        period=f"exercice {tracking.get('fiscal_year')}",
    )
    _, content = _template(doc, tpl)
    _intro(doc, content)
    b = d.section(doc, "Budget, réalisé et écarts")
    rows = [
        {
            "label": r.get("label"),
            "account": r.get("account_prefix"),
            "nature": r.get("nature"),
            "budget": r.get("budget"),
            "actual": r.get("actual"),
            "variance": r.get("variance"),
            "pct": r.get("realization_pct"),
            "favorable": {True: "favorable", False: "défavorable"}.get(r.get("favorable"), ""),
        }
        for r in tracking.get("rows", [])
    ]
    d.add(
        b,
        d.table(
            [
                ("label", "Ligne", "text"),
                ("account", "Comptes", "text"),
                ("nature", "Nature", "text"),
                ("budget", "Budget", "amount"),
                ("actual", "Réalisé", "amount"),
                ("variance", "Écart", "amount"),
                ("pct", "Réalisation", "percent"),
                ("favorable", "Sens", "text"),
            ],
            rows,
        ),
    )
    tot = tracking.get("totals") or {}
    if tot:
        d.add(
            b,
            d.table(
                [
                    ("nature", "Total", "text"),
                    ("budget", "Budget", "amount"),
                    ("actual", "Réalisé", "amount"),
                    ("variance", "Écart", "amount"),
                ],
                [{"nature": k, **(v if isinstance(v, dict) else {})} for k, v in tot.items()],
                title="Totaux",
            ),
        )
    if tracking.get("warnings"):
        d.add(b, *[d.notice(w, "info") for w in tracking["warnings"]])
    d.add(d.section(doc, "Conventions"), *[d.paragraph(c) for c in tracking.get("conventions", [])])
    _closing(doc, content)
    doc["sources"] = [
        {
            "type": "budget",
            "id": str(b0["id"]),
            "label": f"Budget approuvé le {d.fmt_date(b0.get('approved_at'))}",
            "version": b0["version"],
        },
        {"type": "trial_balance_import", "id": str(tracking.get("balance_import_job_id")), "label": "Balance validée"},
    ]
    if tracking.get("ledger_import_job_id"):
        doc["sources"].append(
            {"type": "ledger_import", "id": str(tracking["ledger_import_job_id"]), "label": "Grand livre validé"}
        )
    return doc


# ------------------------------------------------------------------ contrôle interne (structure du lot 9)
def internal_control(meta: dict, report: dict, tpl: dict | None = None) -> dict:
    doc = d.new("ic_report", report["title"], subtype=report["kind"], entity=meta["entity"], period=meta.get("period"))
    _, content = _template(doc, tpl)
    flt = {k: v for k, v in (report.get("filters") or {}).items() if v}
    if flt:
        doc["subtitle"] = "Filtres : " + ", ".join(f"{k} = {v}" for k, v in flt.items())
    _intro(doc, content)
    for s in report["sections"]:
        b = d.section(doc, s["title"])
        if not s["rows"]:
            d.add(b, d.paragraph("Aucune donnée enregistrée.", style="note"))
            continue
        cols = [(c["key"], c["label"], "text") for c in s["columns"]]
        d.add(b, d.table(cols, s["rows"]))
    d.add(
        d.section(doc, "Règle d'établissement"),
        d.paragraph(
            f"Conclusions établies sur les tests revus et les évaluations approuvées uniquement (règle {report.get('rule')})."
        ),
    )
    _closing(doc, content)
    doc["sources"] = [{"type": "ic_data", "id": None, "label": f"{k} : {v}"} for k, v in (report.get("sources") or {}).items()]
    return doc


# ------------------------------------------------------------------ rapport d'audit interne émis (contenu figé du lot 8)
ACTION_LABELS = {
    "planned": "prévue",
    "in_progress": "en cours",
    "implemented": "mise en œuvre (déclarée)",
    "verified": "vérifiée",
    "not_implemented": "non mise en œuvre",
    "risk_accepted": "risque accepté",
}


def internal_audit(report: dict, tpl: dict | None = None) -> dict:
    snap = report["snapshot"]
    e = snap["engagement"]
    doc = d.new(
        "internal_audit_report",
        snap["title"],
        entity=e.get("company"),
        period=f"du {d.fmt_date(e.get('period_start'))} au {d.fmt_date(e.get('period_end'))}" if e.get("period_start") else None,
        subtitle=(
            f"Mission {e['reference']} — {e['name']} · rapport émis le {d.fmt_date(snap.get('issued_at'))}, "
            f"version {snap['version']}"
        ),
    )
    _, content = _template(doc, tpl)
    _intro(doc, content)
    b = d.section(doc, "Mission")
    d.add(
        b,
        d.fields(
            [
                ("Entité auditée", e.get("company")),
                ("Mission", f"{e['reference']} — {e['name']}"),
                (
                    "Méthodologie",
                    f"{snap['methodology']['name']} {snap['methodology']['version_label']}" if snap.get("methodology") else None,
                ),
                ("Émis par", snap.get("issued_by_name")),
                ("Date d'émission", d.fmt_date(snap.get("issued_at"))),
            ]
        ),
    )
    for title, text in (
        ("Synthèse", snap.get("executive_summary")),
        ("Objectifs", e.get("objectives")),
        ("Périmètre", e.get("scope")),
        ("Conclusion générale", snap.get("overall_conclusion")),
    ):
        if text:
            d.add(d.section(doc, title), *[d.paragraph(p) for p in str(text).split("\n")])
    if snap.get("rating_counts"):
        d.add(
            d.section(doc, "Constats par niveau"),
            d.table([("label", "Niveau", "text"), ("count", "Nombre", "number")], snap["rating_counts"]),
        )
    b = d.section(doc, "Constats et recommandations")
    if not snap["findings"]:
        d.add(b, d.paragraph("Aucun constat."))
    for f in snap["findings"]:
        d.add(
            b,
            d.paragraph(
                f"{f['reference']} — {f['title']}" + (f" [{f['rating_label']}]" if f.get("rating_label") else ""), style="heading"
            ),
            d.fields(
                [
                    ("Constat", f.get("condition")),
                    ("Référentiel", f.get("criteria")),
                    ("Cause", f.get("cause")),
                    ("Conséquence", f.get("effect")),
                    ("Processus", f.get("process")),
                ]
            ),
        )
        for rec in f["recommendations"]:
            d.add(b, d.fields([(f"Recommandation {rec['reference']}", rec["text"])]))
            if rec["action_plans"]:
                d.add(
                    b,
                    d.table(
                        [
                            ("description", "Plan d'action", "text"),
                            ("owner_name", "Responsable", "text"),
                            ("due_date", "Échéance", "date"),
                            ("status", "Statut à l'émission", "text"),
                        ],
                        [{**a, "status": ACTION_LABELS.get(a["status"], a["status"])} for a in rec["action_plans"]],
                    ),
                )
        d.add(
            b,
            d.fields(
                [
                    (
                        "Réponse de la direction",
                        f"{f['management_response']} ({f.get('response_by_name')}, {d.fmt_date(f.get('response_at'))})"
                        if f.get("management_response")
                        else "non reçue à la date du rapport",
                    )
                ]
            ),
        )
    if snap.get("distribution"):
        d.add(d.section(doc, "Diffusion"), d.paragraph(snap["distribution"]))
    _closing(doc, content)
    doc["sources"] = [
        {
            "type": "audit_report",
            "id": str(report["id"]),
            "label": f"Rapport émis, version {snap['version']}",
            "content_sha256": report["content_sha256"],
        }
    ]
    return doc


# ------------------------------------------------------------------ synthèse des anomalies (audit financier)
POSITION = {
    "below_trivial": "sous le seuil de signification négligeable",
    "below_overall": "sous le seuil de signification",
    "above_overall": "au-dessus du seuil de signification",
}
MS_STATUS = {"proposed": "proposée", "corrected": "corrigée", "uncorrected": "non corrigée", "withdrawn": "retirée"}
MS_KIND = {"factual": "factuelle", "judgmental": "de jugement", "projected": "extrapolée"}


def fa_summary(meta: dict, summary: dict, materiality: dict, tpl: dict | None = None) -> dict:
    e = meta["engagement"]
    doc = d.new(
        "fa_summary",
        f"Synthèse des anomalies — {e['reference']}",
        entity=meta["entity"],
        period=meta.get("period"),
        subtitle=e.get("name"),
    )
    _, content = _template(doc, tpl)
    doc["notices"].append(
        d.notice(
            "Document de travail de l'équipe d'audit : il récapitule des données approuvées ; il n'exprime "
            "aucune opinion. Les comparaisons aux seuils sont arithmétiques.",
            "info",
        )
    )
    _intro(doc, content)
    m = summary.get("materiality") or {}
    d.add(
        d.section(doc, "Seuils approuvés"),
        d.fields(
            [
                ("Version", m.get("version")),
                ("Seuil de signification", d.fmt(m.get("overall"), "amount")),
                ("Seuil de planification", d.fmt(m.get("performance"), "amount")),
                ("Seuil des anomalies négligeables", d.fmt(m.get("trivial"), "amount")),
                ("Base", materiality.get("benchmark_label")),
                ("Justification", materiality.get("basis")),
                ("Approuvés le", d.fmt_date(materiality.get("approved_at"))),
            ]
        ),
    )
    b = d.section(doc, "Anomalies")
    items = [
        {
            **i,
            "kind": MS_KIND.get(i["kind"], i["kind"]),
            "status": MS_STATUS.get(i["status"], i["status"]),
            "position": POSITION.get(i.get("position") or "", ""),
        }
        for i in summary.get("items", [])
        if i["status"] != "withdrawn"
    ]
    d.add(
        b,
        d.table(
            [
                ("reference", "Réf.", "text"),
                ("description", "Description", "text"),
                ("kind", "Nature", "text"),
                ("status", "Statut", "text"),
                ("amount", "Montant", "amount"),
                ("effect_result", "Effet sur le résultat", "amount"),
                ("position", "Position", "text"),
            ],
            items,
        )
        if items
        else d.paragraph("Aucune anomalie relevée."),
    )
    rows = []
    for key, label in (("corrected", "Corrigées"), ("uncorrected", "Non corrigées"), ("proposed", "En attente de décision")):
        a = summary.get(key) or {}
        rows.append(
            {
                "group": label,
                "count": a.get("count"),
                "effect_result": a.get("effect_result"),
                "position": POSITION.get(a.get("position") or "", ""),
            }
        )
    d.add(
        b,
        d.table(
            [
                ("group", "Anomalies", "text"),
                ("count", "Nombre", "number"),
                ("effect_result", "Effet cumulé sur le résultat", "amount"),
                ("position", "Position", "text"),
            ],
            rows,
            title="Cumuls",
        ),
    )
    eff = (summary.get("uncorrected") or {}).get("effects") or []
    if eff:
        d.add(
            d.section(doc, "Effet des anomalies non corrigées sur les états"),
            d.table(
                [
                    ("label", "Poste", "text"),
                    ("before", "Avant", "amount"),
                    ("after", "Après", "amount"),
                    ("delta", "Écart", "amount"),
                ],
                eff,
            ),
        )
    concl = summary.get("conclusion") or {}
    d.add(
        d.section(doc, "Conclusion de l'équipe sur les anomalies non corrigées"),
        d.paragraph(concl.get("text") or "Non encore rédigée par l'équipe d'audit."),
    )
    _closing(doc, content)
    doc["sources"] = [
        {"type": "materiality", "id": str(materiality["id"]), "label": f"Seuils approuvés, version {m.get('version')}"},
        {"type": "engagement", "id": str(e["id"]), "label": f"Mission {e['reference']}"},
    ]
    return doc
