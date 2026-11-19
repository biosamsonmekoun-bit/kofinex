"""Chargement d'un plan de comptes et d'une table de correspondances depuis un fichier.

Formats acceptés : CSV ou XLSX, première ligne = en-têtes (voir docs/REFERENTIELS.md et les
modèles téléchargeables). Le fichier est la transcription d'un texte officiel ; ce module ne
fait que le lire et le valider : il n'ajoute, ne déduit ni ne corrige aucune règle.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Literal

from app.engines.importing.accounts import MAX_LEN

CHART_COLUMNS = {
    "numero": "Numéro du compte (chiffres uniquement)",
    "libelle": "Intitulé officiel du compte",
    "nature": "Optionnel : actif | passif | capitaux_propres | produit | charge | hors_bilan | mixte",
    "sens": "Optionnel : debit | credit | indifferent",
    "imputable": "Optionnel : oui | non (compte de regroupement)",
}
MAPPING_COLUMNS = {
    "etat": "bilan_actif | bilan_passif | compte_resultat | flux_tresorerie | hors_bilan",
    "code_rubrique": "Référence de la rubrique dans l'état officiel",
    "libelle_rubrique": "Intitulé officiel de la rubrique",
    "prefixe": "Racine de compte rattachée à la rubrique",
    "exclusions": "Optionnel : racines exclues, séparées par des espaces ou des virgules",
    "regle": "solde_debiteur | solde_crediteur | solde_net_debiteur | solde_net_crediteur | "
             "mouvements_debit | mouvements_credit",
    "colonne": "Optionnel : brut | amortissement | net (défaut : net)",
    "signe": "Optionnel : 1 ou -1 (défaut : 1)",
    "priorite": "Optionnel : entier, la plus petite valeur l'emporte (défaut : 100)",
    "source": "Optionnel : référence précise du texte (article, tableau, page)",
}

_NATURES = {"actif": "asset", "passif": "liability", "capitaux_propres": "equity", "produit": "income",
            "charge": "expense", "hors_bilan": "off_balance", "mixte": "mixed"}
_SENS = {"debit": "debit", "credit": "credit", "indifferent": "either"}
_STATEMENTS = {"bilan_actif": "balance_sheet_assets", "bilan_passif": "balance_sheet_liabilities",
               "compte_resultat": "income_statement", "flux_tresorerie": "cash_flow", "hors_bilan": "off_balance"}
_RULES = {"solde_debiteur": "debit_balance", "solde_crediteur": "credit_balance",
          "solde_net_debiteur": "net_debit", "solde_net_crediteur": "net_credit",
          "mouvements_debit": "debit_movements", "mouvements_credit": "credit_movements"}
_COLUMNS = {"brut": "gross", "amortissement": "depreciation", "net": "net"}
_YES = {"oui", "o", "yes", "y", "1", "vrai", "true", "x"}
_NO = {"non", "n", "no", "0", "faux", "false"}

MAX_ISSUES = 200


@dataclass
class LoadIssue:
    severity: Literal["error", "warning", "info"]
    code: str
    message: str
    row: int | None = None


@dataclass
class ChartRecord:
    account_number: str
    label: str
    account_class: int
    parent_number: str | None
    nature: str | None
    normal_balance: str | None
    is_postable: bool
    source_row: int


@dataclass
class MappingRecord:
    statement_type: str
    line_code: str
    line_label: str
    account_prefix: str
    excluded_prefixes: list[str]
    balance_rule: str
    amount_column: str
    sign: int
    priority: int
    source_reference: str | None
    source_row: int


@dataclass
class LoadResult[T]:
    records: list[T] = field(default_factory=list)
    issues: list[LoadIssue] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return any(i.severity == "error" for i in self.issues)

    def add(self, issue: LoadIssue) -> None:
        if len(self.issues) < MAX_ISSUES:
            self.issues.append(issue)
        elif len(self.issues) == MAX_ISSUES:
            self.issues.append(LoadIssue("error", "TOO_MANY_ISSUES", "Trop d'anomalies : liste tronquée."))


def _key(text: object) -> str:
    s = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode().lower().strip()
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_")


def _table(rows: list[list[object]], expected: dict[str, str], required: set[str],
           result: LoadResult) -> tuple[dict[str, int], list[tuple[int, list[object]]]] | None:
    if not rows:
        result.add(LoadIssue("error", "EMPTY_FILE", "Fichier vide."))
        return None
    header = {_key(h): j for j, h in enumerate(rows[0]) if h not in (None, "")}
    missing = required - set(header)
    if missing:
        result.add(LoadIssue("error", "MISSING_COLUMNS",
                             f"Colonnes obligatoires absentes : {', '.join(sorted(missing))}. "
                             f"Colonnes attendues : {', '.join(expected)}."))
        return None
    unknown = set(header) - set(expected)
    if unknown:
        result.add(LoadIssue("warning", "UNKNOWN_COLUMNS", f"Colonnes ignorées : {', '.join(sorted(unknown))}."))
    body = [(i + 1, r) for i, r in enumerate(rows[1:], start=1) if any(v not in (None, "") for v in r)]
    return header, body


def _get(row: list[object], header: dict[str, int], name: str) -> str | None:
    j = header.get(name)
    if j is None or j >= len(row) or row[j] is None:
        return None
    v = row[j]
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    text = str(v).strip()
    return text or None


def _digits(text: str | None) -> str | None:
    if text is None:
        return None
    d = re.sub(r"[\s.]", "", text.lstrip("'"))
    return d if re.fullmatch(r"[0-9]+", d) and 1 <= len(d) <= MAX_LEN else None


# ------------------------------------------------------------------------------ plan de comptes
def parse_chart(rows: list[list[object]]) -> LoadResult[ChartRecord]:
    result: LoadResult[ChartRecord] = LoadResult()
    table = _table(rows, CHART_COLUMNS, {"numero", "libelle"}, result)
    if table is None:
        return result
    header, body = table
    seen: dict[str, int] = {}

    for line_no, row in body:
        raw_num = _get(row, header, "numero")
        number = _digits(raw_num)
        label = _get(row, header, "libelle")
        if number is None:
            result.add(LoadIssue("error", "INVALID_NUMBER", f"Numéro de compte invalide : {raw_num!r}.", line_no))
            continue
        if number[0] == "0":
            result.add(LoadIssue("error", "INVALID_CLASS", f"Compte {number} : la classe 0 n'existe pas.", line_no))
            continue
        if not label:
            result.add(LoadIssue("error", "MISSING_LABEL", f"Compte {number} sans intitulé.", line_no))
            continue
        if number in seen:
            result.add(LoadIssue("error", "DUPLICATE", f"Compte {number} déjà présent ligne {seen[number]}.",
                                 line_no))
            continue

        nature_raw = _key(_get(row, header, "nature"))
        nature = _NATURES.get(nature_raw) if nature_raw else None
        if nature_raw and nature is None:
            result.add(LoadIssue("error", "INVALID_NATURE", f"Compte {number} : nature inconnue « {nature_raw} ».",
                                 line_no))
            continue
        sens_raw = _key(_get(row, header, "sens"))
        sens = _SENS.get(sens_raw) if sens_raw else None
        if sens_raw and sens is None:
            result.add(LoadIssue("error", "INVALID_SENS", f"Compte {number} : sens inconnu « {sens_raw} ».", line_no))
            continue
        imp_raw = _key(_get(row, header, "imputable"))
        if imp_raw and imp_raw not in _YES | _NO:
            result.add(LoadIssue("error", "INVALID_POSTABLE", f"Compte {number} : imputable doit valoir oui ou non.",
                                 line_no))
            continue

        seen[number] = line_no
        result.records.append(ChartRecord(
            account_number=number, label=label[:500], account_class=int(number[0]), parent_number=None,
            nature=nature, normal_balance=sens, is_postable=(imp_raw not in _NO) if imp_raw else True,
            source_row=line_no))

    # hiérarchie déduite des racines effectivement présentes dans le fichier
    numbers = set(seen)
    for rec in result.records:
        for length in range(len(rec.account_number) - 1, 0, -1):
            if rec.account_number[:length] in numbers:
                rec.parent_number = rec.account_number[:length]
                break
        if rec.parent_number is None and len(rec.account_number) > 2:
            result.add(LoadIssue("warning", "ORPHAN",
                                 f"Compte {rec.account_number} : aucune racine parente dans le fichier.",
                                 rec.source_row))
    return result


# ------------------------------------------------------------------------------ correspondances
def parse_mappings(rows: list[list[object]], chart_numbers: set[str]) -> LoadResult[MappingRecord]:
    result: LoadResult[MappingRecord] = LoadResult()
    table = _table(rows, MAPPING_COLUMNS, {"etat", "code_rubrique", "libelle_rubrique", "prefixe", "regle"}, result)
    if table is None:
        return result
    header, body = table
    keys: dict[tuple, int] = {}

    def err(code: str, msg: str, line: int) -> None:
        result.add(LoadIssue("error", code, msg, line))

    for line_no, row in body:
        etat = _key(_get(row, header, "etat"))
        st = _STATEMENTS.get(etat)
        code = _get(row, header, "code_rubrique")
        label = _get(row, header, "libelle_rubrique")
        prefix = _digits(_get(row, header, "prefixe"))
        rule = _RULES.get(_key(_get(row, header, "regle")))
        column = _COLUMNS.get(_key(_get(row, header, "colonne")) or "net")
        sign_raw = _get(row, header, "signe") or "1"
        prio_raw = _get(row, header, "priorite") or "100"

        if st is None:
            err("INVALID_STATEMENT", f"État inconnu « {etat} ».", line_no)
            continue
        if not code or not label:
            err("MISSING_LINE", "Code et libellé de rubrique obligatoires.", line_no)
            continue
        if prefix is None:
            err("INVALID_PREFIX", f"Racine de compte invalide : {_get(row, header, 'prefixe')!r}.", line_no)
            continue
        if rule is None:
            err("INVALID_RULE", f"Règle inconnue « {_get(row, header, 'regle')} ».", line_no)
            continue
        if column is None:
            err("INVALID_COLUMN", f"Colonne inconnue « {_get(row, header, 'colonne')} ».", line_no)
            continue
        if sign_raw not in ("1", "-1", "+1"):
            err("INVALID_SIGN", f"Signe invalide « {sign_raw} » (1 ou -1).", line_no)
            continue
        if not re.fullmatch(r"-?[0-9]+", prio_raw):
            err("INVALID_PRIORITY", f"Priorité invalide « {prio_raw} ».", line_no)
            continue

        exclusions_raw = _get(row, header, "exclusions") or ""
        exclusions = [e for e in re.split(r"[\s,;]+", exclusions_raw) if e]
        bad = [e for e in exclusions if _digits(e) is None]
        if bad:
            err("INVALID_EXCLUSION", f"Exclusions invalides : {', '.join(bad)}.", line_no)
            continue
        for e in exclusions:
            if not e.startswith(prefix) or e == prefix:
                result.add(LoadIssue("warning", "EXCLUSION_OUTSIDE",
                                     f"Exclusion {e} sans effet : ce n'est pas une sous-racine de {prefix}.", line_no))

        key = (st, code, prefix, column)
        if key in keys:
            err("DUPLICATE", f"Ligne identique à la ligne {keys[key]} ({code}, {prefix}, {column}).", line_no)
            continue
        keys[key] = line_no

        if chart_numbers and not any(n.startswith(prefix) or prefix.startswith(n) for n in chart_numbers):
            result.add(LoadIssue("warning", "PREFIX_NOT_IN_CHART",
                                 f"Racine {prefix} ne correspond à aucun compte du plan chargé.", line_no))

        result.records.append(MappingRecord(
            statement_type=st, line_code=code[:40], line_label=label[:500], account_prefix=prefix,
            excluded_prefixes=exclusions, balance_rule=rule, amount_column=column, sign=int(sign_raw),
            priority=int(prio_raw), source_reference=_get(row, header, "source"), source_row=line_no))

    _ambiguities(result, chart_numbers)
    return result


def _ambiguities(result: LoadResult[MappingRecord], chart_numbers: set[str]) -> None:
    """Un même compte capté par deux rubriques d'un même état, même colonne, même règle et même
    priorité : la table ne permet pas de décider, ce qui doit être corrigé avant publication."""
    leaves = [n for n in chart_numbers if not any(m != n and m.startswith(n) for m in chart_numbers)]
    groups: dict[tuple, list[MappingRecord]] = {}
    for m in result.records:
        groups.setdefault((m.statement_type, m.amount_column, m.balance_rule, m.priority), []).append(m)
    reported = 0
    for recs in groups.values():
        if len(recs) < 2:
            continue
        for acc in leaves:
            hits = [m for m in recs if acc.startswith(m.account_prefix)
                    and not any(acc.startswith(e) for e in m.excluded_prefixes)]
            # la racine la plus longue l'emporte : ambiguïté seulement à longueur égale
            if len(hits) > 1:
                longest = max(len(m.account_prefix) for m in hits)
                top = [m for m in hits if len(m.account_prefix) == longest]
                if len({m.line_code for m in top}) > 1:
                    result.add(LoadIssue("error", "AMBIGUOUS",
                                         f"Compte {acc} rattaché à plusieurs rubriques "
                                         f"({', '.join(sorted({m.line_code for m in top}))}) sans priorité distincte.",
                                         top[0].source_row))
                    reported += 1
                    if reported >= 50:
                        return


def template_rows(kind: Literal["chart", "mappings"]) -> list[list[str]]:
    """En-têtes seuls (aucun contenu normatif) et ligne de description."""
    cols = CHART_COLUMNS if kind == "chart" else MAPPING_COLUMNS
    return [list(cols)]


# ------------------------------------------------------------------------------ structure des états
STRUCTURE_COLUMNS = {
    "etat": "bilan_actif | bilan_passif | compte_resultat | flux_tresorerie | hors_bilan",
    "code": "Référence de la ligne dans l'état officiel (unique dans la version)",
    "libelle": "Intitulé officiel de la ligne",
    "ordre": "Rang d'affichage dans l'état (entier)",
    "type": "detail (alimentée par les correspondances) | total (formule) | titre",
    "formule": "Lignes de total uniquement : codes additionnés ou soustraits, ex. « AE + AF - AG »",
    "role": "Optionnel : total_actif | total_passif | resultat_bilan | resultat_compte_resultat",
    "niveau": "Optionnel : niveau d'indentation (0 à 4)",
}
CONCEPT_COLUMNS = {
    "concept": "Code du concept de la bibliothèque d'analyse (voir la liste des concepts)",
    "expression": "Expression : line(\"CODE\"), acct(\"racine\", \"regle\"), concept(\"autre\"), + - * /",
    "source": "Optionnel : justification (article, tableau du texte officiel)",
}
_KINDS = {"detail": "detail", "total": "total", "titre": "title"}
_ROLES = {"total_actif", "total_passif", "resultat_bilan", "resultat_compte_resultat"}
_TOTAL_TERM = re.compile(r"\s*([+-]?)\s*([A-Za-z0-9_]{1,40})\s*")


@dataclass
class StructureRecord:
    statement_type: str
    line_code: str
    label: str
    display_order: int
    kind: str
    formula: list[tuple[int, str]]
    formula_text: str | None
    role: str | None
    level: int
    source_row: int


@dataclass
class ConceptRecord:
    concept_code: str
    expression: str
    expression_ast: dict
    source_reference: str | None
    source_row: int


def parse_total_formula(text: str) -> list[tuple[int, str]]:
    terms, pos, first = [], 0, True
    text = text.strip()
    while pos < len(text):
        m = _TOTAL_TERM.match(text, pos)
        if not m or m.end() == pos or (not first and not m.group(1)):
            raise ValueError(f"Formule de total invalide : « {text} » (attendu : CODE + CODE - CODE).")
        terms.append((-1 if m.group(1) == "-" else 1, m.group(2)))
        pos, first = m.end(), False
    if not terms:
        raise ValueError("Formule de total vide.")
    return terms


def parse_structure(rows: list[list[object]]) -> LoadResult[StructureRecord]:
    result: LoadResult[StructureRecord] = LoadResult()
    table = _table(rows, STRUCTURE_COLUMNS, {"etat", "code", "libelle", "ordre", "type"}, result)
    if table is None:
        return result
    header, body = table
    codes: dict[str, tuple[str, int]] = {}
    roles: dict[str, int] = {}

    for line_no, row in body:
        st = _STATEMENTS.get(_key(_get(row, header, "etat")))
        code = _get(row, header, "code")
        label = _get(row, header, "libelle")
        kind = _KINDS.get(_key(_get(row, header, "type")))
        order_raw = _get(row, header, "ordre") or ""
        role = _key(_get(row, header, "role")) or None
        level_raw = _get(row, header, "niveau") or "0"
        formula_text = _get(row, header, "formule")
        if st is None:
            result.add(LoadIssue("error", "INVALID_STATEMENT", f"État inconnu « {_get(row, header, 'etat')} ».", line_no))
            continue
        if not code or not re.fullmatch(r"[A-Za-z0-9_]{1,40}", code):
            result.add(LoadIssue("error", "INVALID_CODE", f"Code de ligne invalide « {code} ».", line_no))
            continue
        if code in codes:
            result.add(LoadIssue("error", "DUPLICATE", f"Code {code} déjà utilisé ligne {codes[code][1]} "
                                 "(les codes doivent être uniques dans la version).", line_no))
            continue
        if not label or kind is None or not re.fullmatch(r"-?[0-9]+", order_raw):
            result.add(LoadIssue("error", "INVALID_LINE", f"Ligne {code} : libellé, type ou ordre invalide.", line_no))
            continue
        if role and role not in _ROLES:
            result.add(LoadIssue("error", "INVALID_ROLE", f"Ligne {code} : rôle inconnu « {role} ».", line_no))
            continue
        if role and role in roles:
            result.add(LoadIssue("error", "DUPLICATE_ROLE", f"Rôle {role} déjà attribué ligne {roles[role]}.", line_no))
            continue
        formula: list[tuple[int, str]] = []
        if kind == "total":
            if not formula_text:
                result.add(LoadIssue("error", "MISSING_FORMULA", f"Ligne de total {code} sans formule.", line_no))
                continue
            try:
                formula = parse_total_formula(formula_text)
            except ValueError as exc:
                result.add(LoadIssue("error", "INVALID_FORMULA", f"Ligne {code} : {exc}", line_no))
                continue
        elif formula_text:
            result.add(LoadIssue("warning", "IGNORED_FORMULA", f"Ligne {code} : formule ignorée (type {kind}).",
                                 line_no))
        codes[code] = (st, line_no)
        if role:
            roles[role] = line_no
        result.records.append(StructureRecord(st, code, label[:500], int(order_raw), kind, formula, formula_text,
                                              role, max(0, min(int(level_raw) if level_raw.isdigit() else 0, 4)),
                                              line_no))

    # références des totaux : même état, existantes, sans cycle
    by_code = {r.line_code: r for r in result.records}
    for r in result.records:
        for _, ref in r.formula:
            target = by_code.get(ref)
            if target is None:
                result.add(LoadIssue("error", "UNKNOWN_REFERENCE", f"Total {r.line_code} : ligne {ref} inexistante.",
                                     r.source_row))
            elif target.statement_type != r.statement_type:
                result.add(LoadIssue("error", "CROSS_STATEMENT", f"Total {r.line_code} : la ligne {ref} appartient à un "
                                     "autre état.", r.source_row))
    _check_cycles({r.line_code: [ref for _, ref in r.formula] for r in result.records}, result, "Totaux")
    for role, st in (("total_actif", "balance_sheet_assets"), ("total_passif", "balance_sheet_liabilities"),
                     ("resultat_bilan", "balance_sheet_liabilities"),
                     ("resultat_compte_resultat", "income_statement")):
        rec = next((r for r in result.records if r.role == role), None)
        if rec is None:
            result.add(LoadIssue("warning", "ROLE_MISSING", f"Rôle « {role} » non attribué : le contrôle de cohérence "
                                 "correspondant ne pourra pas s'exécuter."))
        elif rec.statement_type != st:
            result.add(LoadIssue("error", "ROLE_STATEMENT", f"Le rôle « {role} » doit porter sur une ligne de l'état "
                                 f"{st}.", rec.source_row))
    return result


def _check_cycles(graph: dict[str, list[str]], result: LoadResult, what: str) -> None:
    state: dict[str, int] = {}

    def visit(n: str, path: list[str]) -> None:
        if state.get(n) == 2 or n not in graph:
            return
        if state.get(n) == 1:
            result.add(LoadIssue("error", "CYCLE", f"{what} circulaires : {' -> '.join(path + [n])}."))
            return
        state[n] = 1
        for m in graph[n]:
            visit(m, path + [n])
        state[n] = 2

    for n in graph:
        visit(n, [])


# ------------------------------------------------------------------------------ concepts
def parse_concepts(rows: list[list[object]], line_codes: set[str], known_concepts: set[str]
                   ) -> LoadResult[ConceptRecord]:
    from app.engines.financial.expressions import FormulaSyntaxError, parse, references

    result: LoadResult[ConceptRecord] = LoadResult()
    table = _table(rows, CONCEPT_COLUMNS, {"concept", "expression"}, result)
    if table is None:
        return result
    header, body = table
    seen: dict[str, int] = {}
    graph: dict[str, list[str]] = {}
    for line_no, row in body:
        code = _key(_get(row, header, "concept"))
        expr = _get(row, header, "expression")
        if code not in known_concepts:
            result.add(LoadIssue("error", "UNKNOWN_CONCEPT", f"Concept inconnu « {code} ».", line_no))
            continue
        if code in seen:
            result.add(LoadIssue("error", "DUPLICATE", f"Concept {code} déjà défini ligne {seen[code]}.", line_no))
            continue
        try:
            node = parse(expr or "")
        except FormulaSyntaxError as exc:
            result.add(LoadIssue("error", "INVALID_EXPRESSION", f"{code} : {exc}", line_no))
            continue
        refs = references(node)
        bad = [f"{fn}({arg})" for fn, arg in refs if fn in ("ind", "prev_ind")]
        missing_lines = [arg for fn, arg in refs if fn in ("line", "prev_line") and arg not in line_codes]
        unknown = [arg for fn, arg in refs if fn in ("concept", "prev_concept") and arg not in known_concepts]
        if bad:
            result.add(LoadIssue("error", "INDICATOR_IN_CONCEPT", f"{code} : un concept ne peut pas utiliser d'indicateur "
                                 f"({', '.join(bad)}).", line_no))
            continue
        if missing_lines:
            result.add(LoadIssue("error", "UNKNOWN_LINE", f"{code} : lignes absentes de la structure : "
                                 f"{', '.join(sorted(missing_lines))}.", line_no))
            continue
        if unknown:
            result.add(LoadIssue("error", "UNKNOWN_CONCEPT", f"{code} : concepts inconnus {', '.join(unknown)}.", line_no))
            continue
        seen[code] = line_no
        graph[code] = [arg for fn, arg in refs if fn == "concept"]
        result.records.append(ConceptRecord(code, expr or "", node, _get(row, header, "source"), line_no))
    _check_cycles(graph, result, "Concepts")
    missing = sorted(known_concepts - set(seen))
    if missing:
        result.add(LoadIssue("warning", "CONCEPTS_NOT_BOUND",
                             f"{len(missing)} concept(s) non définis (les indicateurs qui les utilisent ne seront pas "
                             f"calculés) : {', '.join(missing)}."))
    return result
