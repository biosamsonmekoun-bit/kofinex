"""Bibliothèque standard d'indicateurs KOFINEX — version 1.

Ce sont des définitions d'ANALYSE FINANCIÈRE (fonds de roulement, ratios, délais…), exprimées
sur des « concepts » abstraits (capitaux propres, actif circulant…). Elles ne contiennent aucune
règle comptable : le rattachement de chaque concept aux lignes et comptes d'un référentiel
(SYSCOHADA révisé ou SYSCEBNL) est une donnée de la version du référentiel, chargée par un
administrateur à partir des textes officiels (fichier « concepts »).

Les conventions de calcul (durée de référence, bases de calcul, traitement des cas limites) sont
explicites dans chaque formule. Toute modification passe par une nouvelle version de la formule.
"""

from __future__ import annotations

from dataclasses import dataclass

LIBRARY_VERSION = "KOFINEX-STD-1"

# ------------------------------------------------------------------------------ concepts
CONCEPTS: dict[str, tuple[str, str]] = {
    # bilan
    "total_actif": ("Total du bilan", "Total de l'actif net (égal au total du passif)."),
    "actif_immobilise": ("Actif immobilisé net", "Immobilisations nettes d'amortissements et de dépréciations."),
    "stocks": ("Stocks nets", "Stocks et en-cours nets de dépréciations."),
    "creances_clients": ("Créances clients nettes", "Clients et comptes rattachés, nets de dépréciations."),
    "actif_circulant": ("Actif circulant hors trésorerie", "Actif circulant net, à l'exclusion de la trésorerie-actif."),
    "tresorerie_actif": ("Trésorerie-actif", "Disponibilités et placements assimilés à la trésorerie."),
    "capitaux_propres": ("Capitaux propres", "Capitaux propres, y compris le résultat de l'exercice."),
    "dettes_financieres": ("Dettes financières", "Dettes financières et ressources assimilées, hors trésorerie-passif."),
    "ressources_stables": ("Ressources stables", "Capitaux propres et dettes financières et ressources assimilées."),
    "passif_circulant": ("Passif circulant hors trésorerie", "Dettes d'exploitation et hors exploitation à court terme, "
                         "à l'exclusion de la trésorerie-passif."),
    "dettes_fournisseurs": ("Dettes fournisseurs", "Fournisseurs et comptes rattachés."),
    "tresorerie_passif": ("Trésorerie-passif", "Concours bancaires courants et crédits de trésorerie."),
    # compte de résultat — soldes
    "chiffre_affaires": ("Chiffre d'affaires", "Ventes de biens et de services (hors taxes)."),
    "marge_commerciale": ("Marge commerciale", "Ventes de marchandises diminuées du coût d'achat des marchandises vendues."),
    "valeur_ajoutee": ("Valeur ajoutée", "Richesse créée par l'activité, avant charges de personnel."),
    "excedent_brut_exploitation": ("Excédent brut d'exploitation", "Valeur ajoutée diminuée des charges de personnel "
                                   "(et éléments assimilés selon le référentiel)."),
    "resultat_exploitation": ("Résultat d'exploitation", "Résultat de l'activité d'exploitation."),
    "resultat_financier": ("Résultat financier", "Produits financiers diminués des charges financières."),
    "resultat_activites_ordinaires": ("Résultat des activités ordinaires", "Résultat d'exploitation et résultat financier."),
    "resultat_hao": ("Résultat hors activités ordinaires", "Résultat des opérations hors activités ordinaires."),
    "resultat_net": ("Résultat net", "Résultat de l'exercice."),
    # compte de résultat — bases de ratios
    "achats_consommes": ("Achats consommés", "Achats de marchandises et de matières, corrigés de la variation des stocks."),
    "achats_fournisseurs": ("Base du délai fournisseurs", "Achats et services extérieurs réglés aux fournisseurs (HT)."),
    "charges_personnel": ("Charges de personnel", "Rémunérations et charges sociales."),
    # CAF
    "charges_calculees": ("Charges calculées", "Dotations aux amortissements, dépréciations et provisions (charges sans "
                          "décaissement)."),
    "produits_calcules": ("Produits calculés", "Reprises d'amortissements, de dépréciations et de provisions, quote-part des "
                          "subventions d'investissement virée au résultat (produits sans encaissement)."),
    "produits_cessions": ("Produits de cession d'immobilisations", "Prix de cession des immobilisations cédées."),
    "vnc_cessions": ("Valeur comptable des cessions", "Valeur comptable des immobilisations cédées."),
    "produits_encaissables_hors_ebe": ("Produits encaissables après EBE", "Produits encaissables comptabilisés après "
                                       "l'EBE : financiers, hors activités ordinaires (hors cessions), transferts…"),
    "charges_decaissables_hors_ebe": ("Charges décaissables après EBE", "Charges décaissables comptabilisées après l'EBE : "
                                      "financières, hors activités ordinaires (hors valeur des cessions), participation, "
                                      "impôt sur le résultat…"),
}


# ------------------------------------------------------------------------------ formules
@dataclass(frozen=True)
class FormulaDef:
    code: str
    name: str
    category: str              # sig | caf | structure | liquidity | solvency | profitability | activity | growth
    expression: str
    unit: str                  # amount | ratio | percent | days | times | years
    description: str
    convention_notes: str = ""
    version: int = 1
    rounding_scale: int = 2
    zero_division_policy: str = "null"
    missing_input_policy: str = "null"


def _c(code: str) -> str:
    return f'concept("{code}")'


def _amount(code: str, name: str, concept: str, category: str = "sig", desc: str = "") -> FormulaDef:
    return FormulaDef(code, name, category, _c(concept), "amount", desc or CONCEPTS[concept][1])


def _pct(code: str, name: str, num: str, den: str, category: str, desc: str, notes: str = "") -> FormulaDef:
    return FormulaDef(code, name, category, f"{num} / {den} * 100", "percent", desc, notes)


def _growth(code: str, name: str, base: str) -> FormulaDef:
    return FormulaDef(code, name, "growth", f'(ind("{base}") - prev_ind("{base}")) / abs(prev_ind("{base}")) * 100',
                      "percent", f"Variation de {name.lower().replace('croissance ', '')} par rapport à l'exercice précédent.",
                      "Base : valeur absolue de l'exercice précédent (évite une inversion de signe si elle est négative). "
                      "Non calculé si l'exercice précédent n'a pas de balance validée ou si sa valeur est nulle.")


DAYS_NOTE = ("Durée de référence : nombre réel de jours de l'exercice (days()), ce qui rend comparables les exercices "
             "de durée inhabituelle.")

LIBRARY: tuple[FormulaDef, ...] = (
    # ------------------------------------------------------------------ SIG
    _amount("CA", "Chiffre d'affaires", "chiffre_affaires"),
    _amount("MARGE_COMMERCIALE", "Marge commerciale", "marge_commerciale"),
    _amount("VALEUR_AJOUTEE", "Valeur ajoutée", "valeur_ajoutee"),
    _amount("EBE", "Excédent brut d'exploitation", "excedent_brut_exploitation"),
    _amount("RESULTAT_EXPLOITATION", "Résultat d'exploitation", "resultat_exploitation"),
    _amount("RESULTAT_FINANCIER", "Résultat financier", "resultat_financier"),
    _amount("RAO", "Résultat des activités ordinaires", "resultat_activites_ordinaires"),
    _amount("RESULTAT_HAO", "Résultat hors activités ordinaires", "resultat_hao"),
    _amount("RESULTAT_NET", "Résultat net", "resultat_net"),
    # ------------------------------------------------------------------ CAF
    FormulaDef("CAF_ADDITIVE", "CAF (méthode additive)", "caf",
               f'{_c("resultat_net")} + {_c("charges_calculees")} - {_c("produits_calcules")} '
               f'- {_c("produits_cessions")} + {_c("vnc_cessions")}', "amount",
               "Capacité d'autofinancement à partir du résultat net : résultat + charges calculées − produits calculés "
               "− produits de cession + valeur comptable des cessions.",
               "Doit être égale à la CAF calculée par la méthode soustractive ; un écart est signalé."),
    FormulaDef("CAF_SOUSTRACTIVE", "CAF (méthode soustractive)", "caf",
               f'{_c("excedent_brut_exploitation")} + {_c("produits_encaissables_hors_ebe")} '
               f'- {_c("charges_decaissables_hors_ebe")}', "amount",
               "Capacité d'autofinancement à partir de l'EBE : EBE + produits encaissables − charges décaissables "
               "comptabilisés après l'EBE."),
    # ------------------------------------------------------------------ équilibre financier
    FormulaDef("FR", "Fonds de roulement", "structure", f'{_c("ressources_stables")} - {_c("actif_immobilise")}',
               "amount", "Excédent des ressources stables sur les emplois stables (approche fonctionnelle, valeurs nettes)."),
    FormulaDef("BFR", "Besoin en fonds de roulement", "structure",
               f'{_c("actif_circulant")} - {_c("passif_circulant")}', "amount",
               "Actif circulant hors trésorerie diminué du passif circulant hors trésorerie."),
    FormulaDef("TN", "Trésorerie nette", "structure", f'{_c("tresorerie_actif")} - {_c("tresorerie_passif")}',
               "amount", "Trésorerie-actif diminuée de la trésorerie-passif.",
               "Doit être égale à FR − BFR ; un écart est signalé."),
    FormulaDef("BFR_JOURS_CA", "BFR en jours de chiffre d'affaires", "activity", 'ind("BFR") / ind("CA") * days()',
               "days", "Nombre de jours de chiffre d'affaires immobilisés dans le cycle d'exploitation.",
               DAYS_NOTE + " CA hors taxes.", rounding_scale=1),
    FormulaDef("COUVERTURE_EMPLOIS_STABLES", "Couverture des emplois stables", "structure",
               f'{_c("ressources_stables")} / {_c("actif_immobilise")}', "ratio",
               "Ressources stables rapportées à l'actif immobilisé net (> 1 : FR positif).", rounding_scale=4),
    # ------------------------------------------------------------------ liquidité
    FormulaDef("LIQUIDITE_GENERALE", "Liquidité générale", "liquidity",
               f'({_c("actif_circulant")} + {_c("tresorerie_actif")}) / '
               f'({_c("passif_circulant")} + {_c("tresorerie_passif")})', "ratio",
               "Actif à court terme (circulant et trésorerie) rapporté au passif à court terme.", rounding_scale=4),
    FormulaDef("LIQUIDITE_REDUITE", "Liquidité réduite", "liquidity",
               f'({_c("actif_circulant")} - {_c("stocks")} + {_c("tresorerie_actif")}) / '
               f'({_c("passif_circulant")} + {_c("tresorerie_passif")})', "ratio",
               "Liquidité générale hors stocks.", rounding_scale=4),
    FormulaDef("LIQUIDITE_IMMEDIATE", "Liquidité immédiate", "liquidity",
               f'{_c("tresorerie_actif")} / ({_c("passif_circulant")} + {_c("tresorerie_passif")})', "ratio",
               "Trésorerie-actif rapportée au passif à court terme.", rounding_scale=4),
    # ------------------------------------------------------------------ solvabilité
    _pct("AUTONOMIE_FINANCIERE", "Autonomie financière", _c("capitaux_propres"), _c("total_actif"), "solvency",
         "Part des capitaux propres dans le total du bilan.", "Base : total du bilan (et non total des dettes)."),
    FormulaDef("ENDETTEMENT", "Endettement financier (gearing)", "solvency",
               f'{_c("dettes_financieres")} / {_c("capitaux_propres")}', "ratio",
               "Dettes financières rapportées aux capitaux propres.",
               "Non significatif si les capitaux propres sont négatifs.", rounding_scale=4),
    FormulaDef("CAPACITE_REMBOURSEMENT", "Capacité de remboursement", "solvency",
               f'{_c("dettes_financieres")} / ind("CAF_ADDITIVE")', "years",
               "Nombre d'années de CAF nécessaires pour rembourser les dettes financières.",
               "CAF retenue : méthode additive. Non significatif si la CAF est négative.", rounding_scale=2),
    # ------------------------------------------------------------------ rentabilité
    _pct("ROE", "Rentabilité des capitaux propres (ROE)", _c("resultat_net"), _c("capitaux_propres"), "profitability",
         "Résultat net rapporté aux capitaux propres.",
         "Capitaux propres de clôture, résultat de l'exercice inclus. Non significatif si les capitaux propres sont "
         "négatifs."),
    _pct("ROA", "Rentabilité de l'actif (ROA)", _c("resultat_net"), _c("total_actif"), "profitability",
         "Résultat net rapporté au total du bilan.", "Total du bilan de clôture."),
    _pct("MARGE_NETTE", "Marge nette", _c("resultat_net"), _c("chiffre_affaires"), "profitability",
         "Résultat net rapporté au chiffre d'affaires."),
    _pct("TAUX_EBE", "Taux de marge brute d'exploitation", _c("excedent_brut_exploitation"), _c("chiffre_affaires"),
         "profitability", "EBE rapporté au chiffre d'affaires."),
    _pct("TAUX_VALEUR_AJOUTEE", "Taux de valeur ajoutée", _c("valeur_ajoutee"), _c("chiffre_affaires"),
         "profitability", "Valeur ajoutée rapportée au chiffre d'affaires."),
    _pct("TAUX_RESULTAT_EXPLOITATION", "Marge d'exploitation", _c("resultat_exploitation"), _c("chiffre_affaires"),
         "profitability", "Résultat d'exploitation rapporté au chiffre d'affaires."),
    _pct("PART_CHARGES_PERSONNEL_VA", "Charges de personnel / valeur ajoutée", _c("charges_personnel"),
         _c("valeur_ajoutee"), "profitability", "Part de la valeur ajoutée absorbée par les charges de personnel."),
    # ------------------------------------------------------------------ activité
    FormulaDef("ROTATION_STOCKS", "Rotation des stocks", "activity", f'{_c("stocks")} / {_c("achats_consommes")} * days()',
               "days", "Durée moyenne de présence des stocks, en jours d'achats consommés.",
               DAYS_NOTE + " Stock de clôture (et non stock moyen).", rounding_scale=1),
    FormulaDef("DELAI_CLIENTS", "Délai de recouvrement clients", "activity",
               f'{_c("creances_clients")} / {_c("chiffre_affaires")} * days()', "days",
               "Durée moyenne du crédit accordé aux clients.",
               DAYS_NOTE + " Créances de clôture rapportées au CA hors taxes : si les créances incluent la TVA, le délai "
               "est majoré d'autant.", rounding_scale=1),
    FormulaDef("DELAI_FOURNISSEURS", "Délai de paiement fournisseurs", "activity",
               f'{_c("dettes_fournisseurs")} / {_c("achats_fournisseurs")} * days()', "days",
               "Durée moyenne du crédit obtenu des fournisseurs.",
               DAYS_NOTE + " Dettes de clôture rapportées aux achats hors taxes : si les dettes incluent la TVA, le délai "
               "est majoré d'autant.", rounding_scale=1),
    FormulaDef("ROTATION_ACTIF", "Rotation de l'actif", "activity", f'{_c("chiffre_affaires")} / {_c("total_actif")}',
               "times", "Chiffre d'affaires rapporté au total du bilan.", rounding_scale=4),
    # ------------------------------------------------------------------ croissance (pluriannuel)
    _growth("CROISSANCE_CA", "Croissance du chiffre d'affaires", "CA"),
    _growth("CROISSANCE_VA", "Croissance de la valeur ajoutée", "VALEUR_AJOUTEE"),
    _growth("CROISSANCE_EBE", "Croissance de l'EBE", "EBE"),
    _growth("CROISSANCE_RESULTAT_NET", "Croissance du résultat net", "RESULTAT_NET"),
)

# Contrôles croisés entre indicateurs (écart attendu nul)
CROSS_CHECKS: tuple[tuple[str, str, str, str], ...] = (
    ("FR_BFR_TN", 'ind("FR") - ind("BFR") - ind("TN")', "FR − BFR = trésorerie nette",
     "Les concepts liés au référentiel ne couvrent pas l'intégralité du bilan (ou le classent deux fois)."),
    ("CAF_METHODS", 'ind("CAF_ADDITIVE") - ind("CAF_SOUSTRACTIVE")', "CAF additive = CAF soustractive",
     "Les concepts de la CAF ne couvrent pas tous les éléments entre l'EBE et le résultat net."),
)


def library_rows() -> list[dict]:
    """Lignes à insérer dans ``financial_formulas`` (bibliothèque standard, publiée)."""
    from app.engines.financial.expressions import parse

    return [{
        "organization_id": None, "framework_id": None, "code": f.code, "version": f.version, "name": f.name,
        "category": f.category, "expression": f.expression, "expression_ast": parse(f.expression), "unit": f.unit,
        "rounding_scale": f.rounding_scale, "zero_division_policy": f.zero_division_policy,
        "missing_input_policy": f.missing_input_policy, "description": f.description,
        "convention_notes": f.convention_notes or None, "source_reference": LIBRARY_VERSION, "status": "published",
        "library_version": LIBRARY_VERSION,
    } for f in LIBRARY]
