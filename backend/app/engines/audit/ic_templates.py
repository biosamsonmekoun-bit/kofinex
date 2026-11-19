"""Modèles de structure du contrôle interne : domaines, cycles et processus proposés à l'instanciation.

Contenu repris de la spécification fonctionnelle du lot 9 (structure initiale configurable). Ce sont des
intitulés d'organisation, pas des exigences normatives : aucun risque, contrôle, seuil ni critère n'est fourni.
L'utilisateur choisit les domaines utiles à son entité ; tout est ensuite modifiable, désactivable et complétable.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DomainTemplate:
    code: str
    name: str
    category: str  # accounting_financial | organizational
    processes: tuple[str, ...]


ACCOUNTING: tuple[DomainTemplate, ...] = (
    DomainTemplate(
        "ACH",
        "Achats et fournisseurs",
        "accounting_financial",
        (
            "Expression des besoins",
            "Demandes d'achat",
            "Validation des demandes",
            "Sélection des fournisseurs",
            "Commandes",
            "Réception des biens et services",
            "Contrôle des factures",
            "Comptabilisation des factures",
            "Gestion des avances et acomptes",
            "Règlement des fournisseurs",
            "Suivi des dettes fournisseurs",
            "Gestion du fichier fournisseurs",
        ),
    ),
    DomainTemplate(
        "VEN",
        "Ventes et clients",
        "accounting_financial",
        (
            "Réception des commandes clients",
            "Validation des commandes",
            "Autorisation des ventes",
            "Livraison",
            "Facturation",
            "Comptabilisation des ventes",
            "Encaissement",
            "Gestion des créances",
            "Suivi des impayés",
            "Avoirs et remises",
            "Gestion du fichier clients",
        ),
    ),
    DomainTemplate(
        "TRE",
        "Trésorerie et banques",
        "accounting_financial",
        (
            "Encaissements",
            "Décaissements",
            "Gestion de caisse",
            "Gestion des comptes bancaires",
            "Rapprochements bancaires",
            "Autorisation des paiements",
            "Gestion des chèques et virements",
            "Suivi des flux de trésorerie",
            "Prévisions de trésorerie",
            "Séparation des fonctions",
        ),
    ),
    DomainTemplate(
        "STK",
        "Stocks",
        "accounting_financial",
        (
            "Réception des marchandises",
            "Entrées et sorties",
            "Transferts entre magasins",
            "Gestion des magasins",
            "Inventaires physiques",
            "Valorisation des stocks",
            "Gestion des pertes et dépréciations",
            "Gestion des écarts d'inventaire",
            "Sécurisation des accès",
        ),
    ),
    DomainTemplate(
        "IMM",
        "Immobilisations",
        "accounting_financial",
        (
            "Demandes d'investissement",
            "Autorisation des acquisitions",
            "Acquisition des immobilisations",
            "Réception et mise en service",
            "Identification et codification",
            "Tenue du registre des immobilisations",
            "Calcul des amortissements",
            "Inventaire physique",
            "Transfert des immobilisations",
            "Cession et mise au rebut",
        ),
    ),
    DomainTemplate(
        "PAI",
        "Personnel et paie",
        "accounting_financial",
        (
            "Recrutement",
            "Constitution des dossiers du personnel",
            "Gestion des contrats",
            "Gestion des présences et absences",
            "Établissement de la paie",
            "Validation des bulletins",
            "Paiement des salaires",
            "Gestion des avances et prêts",
            "Déclarations sociales",
            "Gestion des départs",
        ),
    ),
    DomainTemplate(
        "FIS",
        "Fiscal et social",
        "accounting_financial",
        (
            "Identification des obligations",
            "Calcul des impôts et taxes",
            "TVA",
            "Retenues à la source",
            "AIB et autres obligations applicables",
            "Déclarations fiscales",
            "Paiement des impôts",
            "Déclarations sociales",
            "Respect des échéances",
            "Archivage des justificatifs",
        ),
    ),
    DomainTemplate(
        "CLO",
        "Clôture et production comptable",
        "accounting_financial",
        (
            "Organisation de la clôture",
            "Contrôle des écritures",
            "Justification des comptes",
            "Rapprochements comptables",
            "Travaux d'inventaire",
            "Cut-off",
            "Provisions et dépréciations",
            "Amortissements",
            "Contrôle des états financiers",
            "Production des états financiers",
            "Respect du référentiel comptable (SYSCOHADA ou SYSCEBNL)",
        ),
    ),
)

ORGANIZATIONAL: tuple[DomainTemplate, ...] = (
    DomainTemplate("GOU", "Direction générale et gouvernance", "organizational", ()),
    DomainTemplate("RHA", "Ressources humaines et administration", "organizational", ()),
    DomainTemplate("COM", "Commercial et marketing", "organizational", ()),
    DomainTemplate("APL", "Approvisionnement et logistique", "organizational", ()),
    DomainTemplate("PRO", "Production et exploitation", "organizational", ()),
    DomainTemplate("SIN", "Systèmes d'information", "organizational", ()),
    DomainTemplate("PRJ", "Gestion des projets et programmes", "organizational", ()),
    DomainTemplate("SUB", "Gestion des subventions et financements", "organizational", ()),
    DomainTemplate("JUR", "Gestion juridique et conformité", "organizational", ()),
)

TEMPLATES: dict[str, DomainTemplate] = {t.code: t for t in ACCOUNTING + ORGANIZATIONAL}


def process_codes(template: DomainTemplate, prefix: str | None = None) -> list[tuple[str, str]]:
    """Codes des processus d'un modèle : {préfixe}-01, -02… (le préfixe par défaut est le code du domaine)."""
    p = prefix or template.code
    return [(f"{p}-{i:02d}", name) for i, name in enumerate(template.processes, start=1)]


def catalogue() -> list[dict]:
    return [
        {"code": t.code, "name": t.name, "category": t.category, "processes": list(t.processes)}
        for t in ACCOUNTING + ORGANIZATIONAL
    ]
