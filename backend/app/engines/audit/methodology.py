"""Lecture et validation d'une méthodologie (audit ou contrôle interne) chargée par l'utilisateur.

KOFINEX ne fournit aucun contenu normatif : assertions, cycles, grilles de cotation, programmes types…
proviennent du fichier chargé, dont la source est obligatoire. Le moteur ne vérifie que la cohérence.

Fichier CSV (séparateur « ; ») : type ; code ; libelle ; parent ; contenu ; ordre
- type : assertion | cycle | risk_scale | procedure_template | ic_component | ic_principle | deficiency_scale | parameter
         | finding_scale | ic_requirement | ic_criterion | control_level_scale
- contenu : JSON facultatif, structuré selon le type :
    risk_scale          {"likelihood": [{"score": 1, "label": "…"}, …], "impact": [{…}], "significant_from": 6}
    deficiency_scale    {"levels": [{"code": "…", "label": "…", "rank": 1}, …]}   (rang facultatif, 1 = le plus grave)
    control_level_scale {"levels": [{"code": "…", "label": "…", "rank": 1}, …]}   (niveaux de maîtrise, rang facultatif)
    ic_requirement / ic_criterion : parent = principe (ou composante) / exigence (ou principe) du même référentiel
    finding_scale       {"levels": [{"code": "…", "label": "…", "rank": 1}, …]}   (rang 1 = le plus grave)
    procedure_template  {"nature": "detail_test", "objective": "…", "steps": ["…"], "cycle": "…", "assertions": ["…"]}
    cycle               {"account_prefixes": ["…"]}
    parameter           {"value": …}
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

ITEM_TYPES = ("assertion", "cycle", "risk_scale", "procedure_template", "ic_component", "ic_principle",
              "deficiency_scale", "parameter", "finding_scale", "ic_requirement", "ic_criterion", "control_level_scale")
IC_TYPES = ("ic_component", "ic_principle", "ic_requirement", "ic_criterion")
PARENT_TYPES = {"ic_principle": ("ic_component",), "ic_requirement": ("ic_principle", "ic_component"),
                "ic_criterion": ("ic_requirement", "ic_principle")}
NATURES = ("control_test", "analytical", "detail_test", "inquiry", "observation", "inspection", "confirmation",
           "recalculation", "other")
CODE_RE = re.compile(r"^[A-Za-z0-9_.-]{1,40}$")
HEADER = ["type", "code", "libelle", "parent", "contenu", "ordre"]


@dataclass
class Issue:
    severity: str          # error | warning
    row: int | None
    message: str


@dataclass
class Item:
    item_type: str
    code: str
    label: str
    parent_code: str | None
    content: dict
    display_order: int
    source_row: int


@dataclass
class LoadReport:
    items: list[Item] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(i.severity == "error" for i in self.issues)


def _levels(content: dict, key: str, row: int, issues: list[Issue], what: str) -> list[int]:
    levels = content.get(key)
    if not isinstance(levels, list) or not levels:
        issues.append(Issue("error", row, f"{what} : liste « {key} » manquante."))
        return []
    scores = []
    for lv in levels:
        if not isinstance(lv, dict) or not isinstance(lv.get("score"), int) or lv["score"] < 1 or not lv.get("label"):
            issues.append(Issue("error", row,
                                f"{what} : chaque niveau de « {key} » demande un score entier ≥ 1 et un libellé."))
            return []
        scores.append(lv["score"])
    if len(set(scores)) != len(scores):
        issues.append(Issue("error", row, f"{what} : scores en double dans « {key} »."))
    return scores


def parse_rows(rows: list[list[str]]) -> LoadReport:
    rep = LoadReport()
    if not rows:
        rep.issues.append(Issue("error", None, "Fichier vide."))
        return rep
    head = [h.strip().lower() for h in rows[0]]
    if head[:4] != HEADER[:4]:
        rep.issues.append(Issue("error", 1, f"En-tête attendu : {';'.join(HEADER)}"))
        return rep
    seen: set[tuple[str, str]] = set()
    for n, raw in enumerate(rows[1:], start=2):
        cells = [c.strip() for c in raw] + [""] * (6 - len(raw))
        if not any(cells):
            continue
        typ, code, label, parent, content_txt, order = cells[:6]
        if typ not in ITEM_TYPES:
            rep.issues.append(Issue("error", n, f"Type inconnu « {typ} »."))
            continue
        if not CODE_RE.match(code):
            rep.issues.append(Issue("error", n, f"Code invalide « {code} » (lettres, chiffres, . _ -, 40 caractères)."))
            continue
        if not label:
            rep.issues.append(Issue("error", n, "Libellé manquant."))
            continue
        if (typ, code) in seen:
            rep.issues.append(Issue("error", n, f"{typ} {code} en double."))
            continue
        seen.add((typ, code))
        try:
            content = json.loads(content_txt) if content_txt else {}
        except json.JSONDecodeError as exc:
            rep.issues.append(Issue("error", n, f"Contenu JSON illisible : {exc.msg}."))
            continue
        if not isinstance(content, dict):
            rep.issues.append(Issue("error", n, "Le contenu doit être un objet JSON."))
            continue
        try:
            order_i = int(order) if order else 0
        except ValueError:
            rep.issues.append(Issue("error", n, f"Ordre invalide « {order} »."))
            continue
        rep.items.append(Item(typ, code, label, parent or None, content, order_i, n))
    _check_references(rep)
    return rep


def _check_references(rep: LoadReport) -> None:
    codes = {t: {i.code for i in rep.items if i.item_type == t} for t in ITEM_TYPES}
    for it in rep.items:
        what = f"{it.item_type} {it.code}"
        if it.item_type == "risk_scale":
            _levels(it.content, "likelihood", it.source_row, rep.issues, what)
            _levels(it.content, "impact", it.source_row, rep.issues, what)
            thr = it.content.get("significant_from")
            if thr is not None and (not isinstance(thr, int) or thr < 1):
                rep.issues.append(Issue("error", it.source_row, f"{what} : « significant_from » doit être un entier ≥ 1."))
        elif it.item_type in ("deficiency_scale", "control_level_scale"):
            levels = it.content.get("levels")
            valid = isinstance(levels, list) and levels and all(
                isinstance(lv, dict) and lv.get("code") and lv.get("label") for lv in levels)
            if not valid:
                rep.issues.append(Issue("error", it.source_row,
                                        f"{what} : « levels » doit lister des niveaux {{code, label}}."))
            else:
                ranks = [lv.get("rank") for lv in levels if "rank" in lv]
                if len({lv["code"] for lv in levels}) != len(levels):
                    rep.issues.append(Issue("error", it.source_row, f"{what} : codes des niveaux uniques."))
                if ranks and (len(ranks) != len(levels) or len(set(ranks)) != len(ranks) or not all(
                        isinstance(r, int) and not isinstance(r, bool) and r >= 1 for r in ranks)):
                    rep.issues.append(Issue("error", it.source_row,
                                            f"{what} : rangs facultatifs, mais alors entiers ≥ 1, uniques, pour chaque niveau."))
        elif it.item_type == "finding_scale":
            levels = it.content.get("levels")
            valid = isinstance(levels, list) and levels and all(
                isinstance(lv, dict) and lv.get("code") and lv.get("label") and isinstance(lv.get("rank"), int)
                and not isinstance(lv.get("rank"), bool) and lv["rank"] >= 1 for lv in levels)
            if not valid:
                rep.issues.append(Issue("error", it.source_row,
                                        f"{what} : « levels » doit lister des niveaux {{code, label, rank}} (rang entier ≥ 1)."))
            elif len({lv["code"] for lv in levels}) != len(levels) or len({lv["rank"] for lv in levels}) != len(levels):
                rep.issues.append(Issue("error", it.source_row, f"{what} : codes et rangs des niveaux uniques."))
        elif it.item_type == "procedure_template":
            nature = it.content.get("nature")
            if nature not in NATURES:
                rep.issues.append(Issue("error", it.source_row,
                                        f"{what} : nature « {nature} » inconnue ({', '.join(NATURES)})."))
            steps = it.content.get("steps", [])
            if not isinstance(steps, list) or not all(isinstance(s, str) and s.strip() for s in steps):
                rep.issues.append(Issue("error", it.source_row, f"{what} : « steps » doit être une liste d'étapes (textes)."))
            cyc = it.content.get("cycle")
            if cyc and cyc not in codes["cycle"]:
                rep.issues.append(Issue("error", it.source_row, f"{what} : cycle « {cyc} » absent de la méthodologie."))
            for a in it.content.get("assertions", []) or []:
                if a not in codes["assertion"]:
                    rep.issues.append(Issue("error", it.source_row, f"{what} : assertion « {a} » absente de la méthodologie."))
        elif it.item_type == "cycle":
            pref = it.content.get("account_prefixes", [])
            if not isinstance(pref, list) or not all(isinstance(p, str) and p.isdigit() for p in pref):
                rep.issues.append(Issue("error", it.source_row,
                                        f"{what} : « account_prefixes » doit lister des racines de comptes."))
        if it.parent_code:
            parent_types = PARENT_TYPES.get(it.item_type, (it.item_type,))
            if not any(it.parent_code in codes[t] for t in parent_types):
                rep.issues.append(Issue("error", it.source_row,
                                        f"{what} : parent « {it.parent_code} » introuvable ({' ou '.join(parent_types)})."))


def publication_issues(items: list[Item], kind: str) -> list[Issue]:
    """Exigences minimales avant publication (cohérence, pas contenu normatif)."""
    issues: list[Issue] = []
    types = {i.item_type for i in items}
    if not items:
        issues.append(Issue("error", None, "Méthodologie vide."))
    if "risk_scale" not in types:
        issues.append(Issue("error", None,
                            "Une grille de cotation des risques (risk_scale) est nécessaire pour coter les risques."))
    if sum(1 for i in items if i.item_type == "risk_scale") > 1:
        issues.append(Issue("error", None, "Une seule grille de cotation des risques par version."))
    if sum(1 for i in items if i.item_type == "finding_scale") > 1:
        issues.append(Issue("error", None, "Une seule échelle de cotation des constats par version."))
    if kind == "audit" and "assertion" not in types:
        issues.append(Issue("warning", None,
                            "Aucune assertion : les risques ne pourront pas être rattachés à des assertions."))
    if kind == "internal_control" and not types & set(IC_TYPES):
        issues.append(Issue("warning", None, "Aucune composante, aucun principe ni exigence (ic_component, ic_principle, "
                                             "ic_requirement)."))
    if sum(1 for i in items if i.item_type == "control_level_scale") > 1:
        issues.append(Issue("error", None, "Une seule échelle de niveau de maîtrise par version."))
    if kind == "internal_control" and "control_level_scale" not in types:
        issues.append(Issue("warning", None, "Aucune échelle de niveau de maîtrise (control_level_scale) : les évaluations "
                                             "du dispositif ne pourront pas être soumises avec cette méthodologie."))
    return issues


def risk_scale(items: list[Item] | list[dict]) -> dict | None:
    for it in items:
        t = it.item_type if isinstance(it, Item) else it.get("item_type")
        if t == "risk_scale":
            return it.content if isinstance(it, Item) else it.get("content")
    return None


def rate(scale: dict, likelihood: int | None, impact: int | None) -> dict:
    """Score = probabilité × impact, sur les niveaux de la grille ; « significatif » si la grille fixe un seuil."""
    if likelihood is None or impact is None:
        return {"score": None, "significant": None}
    lik = {lv["score"] for lv in scale.get("likelihood", [])}
    imp = {lv["score"] for lv in scale.get("impact", [])}
    if likelihood not in lik or impact not in imp:
        raise ValueError(f"Cotation hors grille : probabilité {likelihood} (niveaux {sorted(lik)}), "
                         f"impact {impact} (niveaux {sorted(imp)}).")
    score = likelihood * impact
    thr = scale.get("significant_from")
    return {"score": score, "significant": (score >= thr) if isinstance(thr, int) else None}


def finding_levels(items: list[Item] | list[dict]) -> list[dict]:
    """Niveaux de l'échelle des constats, du plus grave (rang 1) au moins grave ; liste vide si absente."""
    for it in items:
        typ = it["item_type"] if isinstance(it, dict) else it.item_type
        if typ == "finding_scale":
            content = it["content"] if isinstance(it, dict) else it.content
            return sorted(content.get("levels", []), key=lambda lv: lv["rank"])
    return []


def scale_levels(items: list[Item] | list[dict], item_type: str) -> list[dict]:
    """Niveaux d'une échelle (deficiency_scale, control_level_scale, finding_scale), ordonnés par rang s'il existe."""
    for it in items:
        typ = it["item_type"] if isinstance(it, dict) else it.item_type
        if typ == item_type:
            content = it["content"] if isinstance(it, dict) else it.content
            lv = list(content.get("levels", []))
            return sorted(lv, key=lambda x: x.get("rank", 10**6)) if all("rank" in x for x in lv) else lv
    return []
