"""Profils des référentiels comptables.

Chaque référentiel dispose de son propre profil (moteur de règles distinct). Le CONTENU
normatif — plan de comptes, rubriques des états financiers, règles de rattachement des
comptes — n'est jamais écrit dans le code : il est chargé depuis les textes officiels dans
une version datée et sourcée (``framework_versions``), validé puis publié et figé.

Le profil définit uniquement ce que la plateforme exige d'une version avant publication et
les contrôles propres au référentiel appliqués aux données chargées.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.engines.accounting.reference_loader import ChartRecord, LoadIssue, MappingRecord, StructureRecord

STATEMENT_LABELS = {
    "balance_sheet_assets": "Bilan — actif",
    "balance_sheet_liabilities": "Bilan — passif",
    "income_statement": "Compte de résultat",
    "cash_flow": "Tableau des flux de trésorerie",
    "off_balance": "Engagements hors bilan",
}


@dataclass(frozen=True)
class FrameworkProfile:
    code: str
    name: str
    scope: str
    # états dont les correspondances doivent être chargées avant publication de la version
    required_statements: tuple[str, ...] = ("balance_sheet_assets", "balance_sheet_liabilities", "income_statement")
    notes: tuple[str, ...] = field(default_factory=tuple)

    def validate(self, chart: list[ChartRecord], mappings: list[MappingRecord],
                 structure: list[StructureRecord] | None = None) -> list[LoadIssue]:
        issues: list[LoadIssue] = []
        structure = structure or []
        if not structure:
            issues.append(LoadIssue("error", "STRUCTURE_MISSING",
                                    "La structure des états (lignes, totaux) n'est pas chargée."))
        lines = {(r.statement_type, r.line_code): r for r in structure}
        for st in self.required_statements:
            if structure and not any(r.statement_type == st for r in structure):
                issues.append(LoadIssue("error", "STATEMENT_STRUCTURE_MISSING",
                                        f"Aucune ligne de structure pour l'état « {STATEMENT_LABELS[st]} »."))
        if structure:
            orphans = sorted({f"{m.line_code} ({STATEMENT_LABELS.get(m.statement_type, m.statement_type)})"
                              for m in mappings if (m.statement_type, m.line_code) not in lines
                              or lines[(m.statement_type, m.line_code)].kind != "detail"})
            if orphans:
                issues.append(LoadIssue("error", "MAPPING_LINE_UNKNOWN",
                                        "Correspondances vers des lignes absentes de la structure ou qui ne sont pas des "
                                        f"lignes de détail : {', '.join(orphans[:30])}."))
        if not chart:
            issues.append(LoadIssue("error", "CHART_MISSING", "Le plan de comptes n'est pas chargé."))
        present = {m.statement_type for m in mappings}
        for st in self.required_statements:
            if st not in present:
                issues.append(LoadIssue("error", "STATEMENT_MISSING",
                                        f"Aucune correspondance chargée pour l'état « {STATEMENT_LABELS[st]} »."))
        without_nature = sum(1 for c in chart if c.nature is None)
        if chart and without_nature == len(chart):
            issues.append(LoadIssue("warning", "NATURE_MISSING",
                                    "Aucune nature de compte (actif, passif, charge, produit…) n'est renseignée : "
                                    "le contrôle des à-nouveaux ne pourra pas s'exécuter."))
        return issues


class SyscohadaRevise(FrameworkProfile):
    pass


class Syscebnl(FrameworkProfile):
    pass


PROFILES: dict[str, FrameworkProfile] = {
    "SYSCOHADA_REV": SyscohadaRevise(
        code="SYSCOHADA_REV",
        name="SYSCOHADA révisé",
        scope="Entités à but lucratif relevant de l'Acte uniforme OHADA relatif au droit comptable "
              "et à l'information financière.",
    ),
    "SYSCEBNL": Syscebnl(
        code="SYSCEBNL",
        name="SYSCEBNL",
        scope="Entités à but non lucratif (associations, ONG, fondations, projets de développement…) "
              "relevant du système comptable OHADA des EBNL.",
        notes=("Les rubriques des états financiers des EBNL diffèrent de celles du SYSCOHADA : une version "
               "SYSCEBNL ne réutilise jamais les correspondances d'une version SYSCOHADA.",),
    ),
}


def get_profile(code: str) -> FrameworkProfile:
    try:
        return PROFILES[code]
    except KeyError as exc:
        raise ValueError(f"Référentiel non pris en charge : {code}") from exc
