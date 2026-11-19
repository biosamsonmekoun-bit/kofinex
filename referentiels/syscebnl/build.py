"""Génère les fichiers de chargement du référentiel SYSCEBNL (modèle « associations, ordres professionnels,
fondations et assimilés ») pour KOFINEX.

Sources (fournies par l'utilisateur) :
  [JO]   Acte uniforme relatif au système comptable des entités à but non lucratif, Journal officiel OHADA
         (SYCEBNL-2022_fr.pdf, 438 p.) :
           - Partie 2, plan des comptes (pp. 77-105) : texte obtenu par reconnaissance OCR (le PDF ne contient
             pas de texte exploitable), conservé dans ocr_jo/pNNN.txt ;
           - Partie 4, modèles du bilan (p. 346) et du compte de résultat (p. 347) ;
           - Partie 4, section 6, tableau de correspondance bilan (p. 395) et compte de résultat (p. 396),
             lus sur l'image de la page.
  [XL]   Modèle Excel « États financiers des associations… SYCEBNL-1_1 » (../sources/SYCEBNL-1_1_ASSOCIATIONS.xlsx),
         utilisé uniquement pour recouper (plan comptable, formules des postes) : il contient des erreurs.

Les choix d'interprétation sont marqués « [À VALIDER] » dans la colonne source et listés dans RAPPORT.md.
Usage : python build.py
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE_XL = HERE.parent / "sources" / "SYCEBNL-1_1_ASSOCIATIONS.xlsx"
OCR_DIR = HERE / "ocr_jo"
VALIDER = "[À VALIDER]"
TC_B = "[JO] p. 395 tableau de correspondance - bilan"
TC_R = "[JO] p. 396 tableau de correspondance - compte de résultat"

# =====================================================================================
# 1. Structure des états ([JO] pp. 346-347 ; les modèles ne donnent pas les formules des totaux du bilan :
#    elles sont déduites de la présentation, chaque total couvrant les lignes qui le précèdent)
# =====================================================================================
T_SRC = f"{VALIDER} formule déduite de la présentation du modèle"
ACTIF = [
    ("AA", "IMMOBILISATIONS DESTINÉES À LA VENTE PROVENANT DE DONS ET LEGS NON ENCORE REÇUES ET USUFRUIT TEMPORAIRE",
     "total", "AB + AC", None, 0),
    ("AB", "Immobilisations incorporelles", "detail", None, None, 1),
    ("AC", "Immobilisations corporelles et financières", "detail", None, None, 1),
    ("AD", "IMMOBILISATIONS INCORPORELLES", "total", "AE + AF + AG", None, 0),
    ("AE", "Brevets, licences, logiciels et droits similaires", "detail", None, None, 1),
    ("AF", "Autres immobilisations incorporelles", "detail", None, None, 1),
    ("AG", "Avances et acomptes versés sur immobilisations incorporelles", "detail", None, None, 1),
    ("AH", "IMMOBILISATIONS CORPORELLES", "total", "AI + AJ + AK + AL + AM + AN", None, 0),
    ("AI", "Terrains", "detail", None, None, 1),
    ("AJ", "Bâtiments", "detail", None, None, 1),
    ("AK", "Aménagements, agencements et installations", "detail", None, None, 1),
    ("AL", "Matériel, mobilier et actifs biologiques", "detail", None, None, 1),
    ("AM", "Matériel de transport", "detail", None, None, 1),
    ("AN", "Avances et acomptes versés sur immobilisations corporelles", "detail", None, None, 1),
    ("AO", "IMMOBILISATIONS FINANCIÈRES", "total", "AX + AY", None, 0),
    ("AX", "Titres de participation", "detail", None, None, 1),
    ("AY", "Autres immobilisations financières", "detail", None, None, 1),
    ("AZ", "TOTAL ACTIF IMMOBILISÉ", "total", "AA + AD + AH + AO", None, 0),
    ("BA", "Actif circulant HAO", "detail", None, None, 1),
    ("BB", "Stocks et encours", "detail", None, None, 1),
    ("BC", "Fournisseurs débiteurs", "detail", None, None, 1),
    ("BD", "Adhérents, clients-usagers", "detail", None, None, 1),
    ("BE", "Autres créances", "detail", None, None, 1),
    ("BT", "TOTAL ACTIF CIRCULANT", "total", "BA + BB + BC + BD + BE", None, 0),
    ("BU", "Titres de placement", "detail", None, None, 1),
    ("BV", "Valeurs à encaisser", "detail", None, None, 1),
    ("BW", "Banques, établissements financiers, caisses et assimilés", "detail", None, None, 1),
    ("BX", "TOTAL TRÉSORERIE-ACTIF", "total", "BU + BV + BW", None, 0),
    ("BY", "Écart de conversion-Actif", "detail", None, None, 0),
    ("BZ", "TOTAL GÉNÉRAL", "total", "AZ + BT + BX + BY", "total_actif", 0),
]
PASSIF = [
    ("CA", "Dotation non consomptible sans droit de reprise", "detail", None, None, 1),
    ("CB", "Dotation non consomptible avec droit de reprise", "detail", None, None, 1),
    ("CC", "Droit d'entrée", "detail", None, None, 1),
    ("CD", "Dotation consomptible", "detail", None, None, 1),
    ("CE", "Écarts de réévaluation", "detail", None, None, 1),
    ("CF", "Réserves", "detail", None, None, 1),
    ("CG", "Report à nouveau (+ ou -)", "detail", None, None, 1),
    ("CH", "Résultat net de l'exercice (excédent + ou déficit -)", "detail", None, "resultat_bilan", 1),
    ("CI", "Subventions d'investissement", "detail", None, None, 1),
    ("CJ", "Provisions réglementées", "detail", None, None, 1),
    ("CK", "TOTAL FONDS PROPRES ET ASSIMILÉS", "total", "CA + CB + CC + CD + CE + CF + CG + CH + CI + CJ", None, 0),
    ("CW", "Fonds affectés et provenant de dons et legs d'immobilisations", "detail", None, None, 1),
    ("CX", "Fonds reportés", "detail", None, None, 1),
    ("CY", "TOTAL FONDS AFFECTÉS ET REPORTÉS", "total", "CW + CX", None, 0),
    ("CZ", "TOTAL RESSOURCES PROPRES ET ASSIMILÉES", "total", "CK + CY", None, 0),
    ("DA", "Emprunts et dettes financières", "detail", None, None, 1),
    ("DB", "Dettes de location-acquisition", "detail", None, None, 1),
    ("DC", "Provisions pour risques et charges", "detail", None, None, 1),
    ("DD", "TOTAL DETTES FINANCIÈRES ET RESSOURCES ASSIMILÉES", "total", "DA + DB + DC", None, 0),
    ("DE", "TOTAL RESSOURCES STABLES", "total", "CZ + DD", None, 0),
    ("DF", "Dettes circulantes HAO", "detail", None, None, 1),
    ("DG", "Adhérents, clients-usagers créditeurs", "detail", None, None, 1),
    ("DH", "Fournisseurs", "detail", None, None, 1),
    ("DI", "Autres dettes", "detail", None, None, 1),
    ("DV", "TOTAL PASSIF CIRCULANT", "total", "DF + DG + DH + DI", None, 0),
    ("DW", "Banques, établissements financiers et crédits de trésorerie", "detail", None, None, 1),
    ("DX", "TOTAL TRÉSORERIE-PASSIF", "total", "DW", None, 0),
    ("DY", "Écart de conversion-Passif", "detail", None, None, 0),
    ("DZ", "TOTAL GÉNÉRAL", "total", "DE + DV + DX + DY", "total_passif", 0),
]
# Compte de résultat : montants signés (revenus +, charges −), comme pour la version SYSCOHADA de la plateforme ;
# les totaux du modèle (« XA − XB », « TM − TN ») deviennent donc des sommes.
RESULTAT = [
    ("RA", "Cotisations", "detail", None, None, 1),
    ("RB", "Dotations consomptibles transférées au compte de résultat", "detail", None, None, 1),
    ("RC", "Revenus liés à la générosité", "detail", None, None, 1),
    ("RD", "Ventes de marchandises", "detail", None, None, 1),
    ("RE", "Ventes de services et produits finis", "detail", None, None, 1),
    ("RF", "Subventions d'exploitation", "detail", None, None, 1),
    ("RG", "Autres produits et transferts de charges", "detail", None, None, 1),
    ("RH", "Reprises de provisions, dépréciations, subventions et autres reprises", "detail", None, None, 1),
    ("XA", "REVENUS DES ACTIVITÉS ORDINAIRES", "total", "RA + RB + RC + RD + RE + RF + RG + RH", None, 0),
    ("TA", "Achats de biens et services liés à l'activité", "detail", None, None, 1),
    ("TB", "Variation de stocks des achats de biens et services liés à l'activité", "detail", None, None, 1),
    ("TC", "Achats de marchandises et matières premières", "detail", None, None, 1),
    ("TD", "Autres achats", "detail", None, None, 1),
    ("TE", "Variation de stocks de marchandises, de matières premières et autres", "detail", None, None, 1),
    ("TF", "Transports", "detail", None, None, 1),
    ("TG", "Services extérieurs", "detail", None, None, 1),
    ("TH", "Impôts et taxes", "detail", None, None, 1),
    ("TI", "Autres charges", "detail", None, None, 1),
    ("TJ", "Charges de personnel", "detail", None, None, 1),
    ("TK", "Frais financiers et charges assimilées", "detail", None, None, 1),
    ("TL", "Dotations aux amortissements, aux provisions, aux dépréciations et autres", "detail", None, None, 1),
    ("XB", "CHARGES DES ACTIVITÉS ORDINAIRES (somme TA à TL)", "total",
     "TA + TB + TC + TD + TE + TF + TG + TH + TI + TJ + TK + TL", None, 0),
    ("XC", "RÉSULTAT DES ACTIVITÉS ORDINAIRES (XA - XB)", "total", "XA + XB", None, 0),
    ("TM", "Produits H.A.O.", "detail", None, None, 1),
    ("TN", "Charges H.A.O.", "detail", None, None, 1),
    ("XD", "RÉSULTAT H.A.O. (TM - TN)", "total", "TM + TN", None, 0),
    ("XE", "RÉSULTAT NET DE L'EXERCICE (+ excédent, - déficit) (XC + XD)", "total", "XC + XD",
     "resultat_compte_resultat", 0),
]

# =====================================================================================
# 2. Correspondances ([JO] p. 395-396 ; « p » = compte réparti entre plusieurs postes)
# =====================================================================================
D, C, ND, NC = "solde_debiteur", "solde_crediteur", "solde_net_debiteur", "solde_net_crediteur"
A, P, R = "bilan_actif", "bilan_passif", "compte_resultat"
MAP: list[tuple[str, str, list[str], list[str], str, str, str]] = []


def m(etat, poste, prefixes, regle, colonne="net", excl=(), source=""):
    MAP.append((etat, poste, list(prefixes), list(excl), regle, colonne, source))


def actif(poste, brut, amort, brut_excl=(), amort_excl=(), src_brut="", src_amort="", note_brut="", note_amort=""):
    if brut:
        m(A, poste, brut, ND, "brut", brut_excl, f"{TC_B} {poste} brut : « {src_brut} »{note_brut}")
    if amort:
        m(A, poste, amort, NC, "amortissement", amort_excl, f"{TC_B} {poste} amort./dépréc. : « {src_amort} »{note_amort}")


# Brut : solde net débiteur, amortissements : solde net créditeur, sauf grille « soldes débiteurs / créditeurs » :
# un solde de sens inhabituel reste ainsi visible (montant négatif) au lieu de disparaître du bilan.
P_NOTE = f" {VALIDER} compte « p » réparti dans la grille ; affecté en totalité à ce poste"
actif("AB", ["201"], ["280", "2901"], src_brut="201", src_amort="280, 2901")
actif("AC", ["202", "203", "204", "205"], ["2902"], src_brut="202, 203, 204, 205", src_amort="2 902")
actif("AE", ["212", "213", "214", "2193"], ["2812", "2813", "2814", "2912", "2913", "2914"],
      src_brut="212, 213, 214, 2193", src_amort="2812, 2813, 2814, 2912, 2913, 2914, 2919p",
      note_amort=" (2919p affecté au poste AF)")
actif("AF", ["218", "2198"], ["2818", "2918", "2919"], src_brut="218, 2198", src_amort="2818, 2918, 2919p",
      note_amort=P_NOTE)
m(A, "AF", ["2817"], NC, "amortissement", source=f"{VALIDER} compte 2817 « Amortissements des indemnités de "
  "transfert aux joueurs » (plan [JO]) non cité par la grille ; rattaché aux autres immobilisations incorporelles")
actif("AG", ["251"], ["2951"], src_brut="251", src_amort="illisible dans le JO",
      note_amort=f" {VALIDER} 2951 retenu : cellule illisible au JO ; 2951 dans le modèle Excel et symétrique de AN (2952)")
actif("AI", ["22"], ["282", "292"], src_brut="22", src_amort="282, 292")
actif("AJ", ["231", "232", "233", "2391", "2392", "2393", "2396"],
      ["2831", "2832", "2833", "2931", "2932", "2933", "2939"],
      src_brut="231, 232, 233, 2391, 2392, 2393, 2396", src_amort="2831, 2832, 2833, 2931, 2932, 2933, 2939p",
      note_amort=P_NOTE)
actif("AK", ["234", "235", "238", "2394", "2395", "2398"], ["2834", "2835", "2838", "2934", "2935", "2938"],
      src_brut="234, 235, 238, 2394, 2395, 2398", src_amort="2834, 2835, 2838, 2934, 2935, 2938, 2939p",
      note_amort=" (2939p affecté au poste AJ)")
actif("AL", ["24"], ["284", "294"], brut_excl=["245", "2495"], amort_excl=["2845", "2945"],
      src_brut="24 (sauf 245 et 2495)", src_amort="284 (sauf 2845), 294 (sauf 2945, 2949), 2949p",
      note_amort=f" {VALIDER} 2949p (aussi cité en AM) affecté en totalité à AL")
actif("AM", ["245", "2495"], ["2845", "2945"], src_brut="245, 2495", src_amort="2845, 2945, 2949p",
      note_amort=" (2949p affecté au poste AL)")
actif("AN", ["252"], ["2952"], src_brut="252", src_amort="2 952")
actif("AX", ["26"], ["296"], src_brut="26", src_amort="296")
actif("AY", ["27"], ["297"], src_brut="27", src_amort="297")
actif("BA", ["485", "4865"], ["498"], src_brut="485, 4865", src_amort="498")
actif("BB", ["31", "32", "33", "34", "36", "37", "38"], ["39"], src_brut="31, 32, 33, 34, 36, 37, 38", src_amort="39")
m(A, "BB", ["35"], D, "brut", source=f"{VALIDER} compte 35 « Produits et services en cours » (plan [JO]) non cité "
  "par la grille du poste BB ; rattaché aux stocks et encours")
m(A, "BC", ["409"], ND, "brut", source=f"{TC_B} BC brut : « 409 »")
m(A, "BC", ["40"], D, "brut", ["409"], f"{VALIDER} soldes débiteurs des comptes 40 (sauf 409) : non cités par la grille ; "
  "classés en fournisseurs débiteurs (non-compensation), comme pour la version SYSCOHADA")
m(A, "BC", ["490"], C, "amortissement", source=f"{TC_B} BC dépréc. : « 490 »")
m(A, "BD", ["41"], D, "brut", ["419"], f"{TC_B} BD brut : « 41 (sauf 419) » — soldes débiteurs")
m(A, "BD", ["491"], C, "amortissement", source=f"{TC_B} BD dépréc. : « 491 »")
m(A, "BE", ["42", "43", "44", "45", "47"], D, "brut", ["478", "479"],
  f"{TC_B} BE brut : « Soldes débiteurs : 42, 43, 44, 45, 47 (sauf 478) »")
m(A, "BE", ["46"], D, "brut", source=f"{VALIDER} soldes débiteurs du compte 46 « Bailleurs, État et autres organismes, "
  "fonds d'administration » (plan [JO]) : non cités par la grille ; classés en autres créances")
m(A, "BE", ["492", "493", "494", "497"], C, "amortissement", source=f"{TC_B} BE dépréc. : « 492, 493, 494, 497 »")
actif("BU", ["50"], ["590"], src_brut="50", src_amort="590")
actif("BV", ["51"], ["591"], src_brut="51", src_amort="591")
m(A, "BW", ["52", "53"], D, "brut", source=f"{TC_B} BW brut : « Soldes débiteurs : 52, 53, 55, 57 » "
  "(52, 53 : soldes créditeurs au poste DW)")
m(A, "BW", ["55", "57"], ND, "brut", source=f"{TC_B} BW brut : « Soldes débiteurs : 52, 53, 55, 57 » "
  "(55, 57 : non cités au passif, solde net)")
m(A, "BW", ["592", "593", "595"], C, "amortissement", source=f"{TC_B} BW dépréc. : « 592, 593, 595 »")
m(A, "BY", ["478"], ND, "brut", source=f"{TC_B} BY : « 478 »")

for poste, prefixes, excl, src in [
    ("CA", ["101"], [], "101"), ("CB", ["102"], [], "102"), ("CC", ["103"], [], "103"), ("CD", ["104"], [], "104"),
    ("CE", ["106"], [], "106"), ("CF", ["11"], [], "11"), ("CG", ["12"], [], "12"), ("CI", ["14"], [], "14"),
    ("CJ", ["15"], [], "15"), ("CW", ["16"], [], "16"), ("CX", ["17"], [], "17"),
    ("DA", ["181", "182", "183", "185", "186", "188"], [], "181, 182, 183, 185, 186, 188"), ("DB", ["187"], [], "187"),
    ("DC", ["19"], [], "19"), ("DF", ["481", "484", "4861", "488", "4998"], [], "481, 484, 4861, 488, 4998"),
    ("DG", ["419"], [], "419"), ("DI", ["499", "599"], ["4998"], "499 (sauf 4998), 599"), ("DW", ["56"], [], "56"),
    ("DY", ["479"], [], "479"),
]:
    m(P, poste, prefixes, NC, excl=excl, source=f"{TC_B} {poste} : « {src} »")
m(P, "CH", ["13"], NC, source=f"{TC_B} CH : « 13 (131 ou 139) »")
m(P, "CH", ["6", "7", "8"], NC, source=f"{VALIDER} balance avant affectation du résultat : revenus − charges des classes "
  "6 à 8 (résultat de l'exercice, égal au poste XE) ; le contrôle « résultat bilan = compte de résultat » signale tout écart")
m(P, "DG", ["41"], C, excl=["419"], source=f"{VALIDER} soldes créditeurs des comptes 41 (sauf 419) : non cités par la "
  "grille ; classés en adhérents, clients-usagers créditeurs (non-compensation)")
m(P, "DH", ["40"], C, excl=["409"], source=f"{TC_B} DH : « 40 (sauf 409) » — soldes créditeurs (soldes débiteurs : BC)")
m(P, "DI", ["42", "43", "44", "45", "47"], C, excl=["478", "479"],
  source=f"{TC_B} DI : « Soldes créditeurs : 42, 43, 44, 45, 47 (sauf 479) »")
m(P, "DI", ["46"], C, source=f"{VALIDER} soldes créditeurs du compte 46 : non cités par la grille ; classés en autres dettes")
m(P, "DW", ["52", "53"], C, source=f"{TC_B} DW : « Solde créditeurs : 52, 53 »")

for poste, prefixes, src in [
    ("RA", ["701"], "701"), ("RB", ["703"], "703"), ("RC", ["704"], "704"), ("RD", ["7051"], "7051"),
    ("RE", ["7052", "7053"], "7052, 7053"), ("RF", ["71"], "71"),
    ("RG", ["706", "707", "708", "72", "73", "75", "77", "78"], "706, 707, 708, 72, 73 (+/-), 75, 77, 78"),
    ("RH", ["79"], "79"), ("TA", ["601"], "601"), ("TB", ["6031"], "6031"), ("TC", ["602"], "602"),
    ("TD", ["604", "605", "606", "608"], "604, 605, 606, 608"), ("TE", ["6032", "6033", "6034", "6035"], "6032 à 6035"),
    ("TF", ["61"], "61"), ("TG", ["62", "63"], "62, 63"), ("TH", ["64"], "64"), ("TI", ["65"], "65"),
    ("TJ", ["66"], "66"), ("TK", ["67"], "67"), ("TL", ["68", "69"], "68, 69"),
    ("TM", ["82", "84", "86", "88"], "82, 84, 86, 88"), ("TN", ["81", "83", "85", "87"], "81, 83, 85, 87 (+/-)"),
]:
    m(R, poste, prefixes, NC, source=f"{TC_R} {poste} : « {src} » (montant signé : revenu +, charge −)")

# =====================================================================================
# 3. Concepts d'analyse (seuls ceux qui ont un équivalent dans les états EBNL sont liés ; les soldes propres
#    aux entreprises commerciales — marge, valeur ajoutée, EBE… — restent sans liaison : les ratios qui en
#    dépendent sont signalés « donnée manquante » au lieu d'être calculés sur une base inventée)
# =====================================================================================
CONCEPTS = [
    ("total_actif", 'line("BZ")', "[JO] poste BZ"),
    ("actif_immobilise", 'line("AZ")', "[JO] poste AZ (net)"),
    ("stocks", 'line("BB")', "[JO] poste BB (net)"),
    ("creances_clients", 'line("BD")', "[JO] poste BD (net) — adhérents, clients-usagers"),
    ("actif_circulant", 'line("BT") + line("BY")', f"[JO] BT + BY {VALIDER} écart de conversion-actif rattaché au circulant"),
    ("tresorerie_actif", 'line("BX")', "[JO] poste BX"),
    ("capitaux_propres", 'line("CK")', f"[JO] poste CK {VALIDER} fonds propres hors fonds affectés et reportés (CY)"),
    ("dettes_financieres", 'line("DD")', "[JO] poste DD"),
    ("ressources_stables", 'line("DE")', "[JO] poste DE"),
    ("passif_circulant", 'line("DV") + line("DY")', f"[JO] DV + DY {VALIDER} écart de conversion-passif rattaché au circulant"),
    ("dettes_fournisseurs", 'line("DH")', "[JO] poste DH"),
    ("tresorerie_passif", 'line("DX")', "[JO] poste DX"),
    ("chiffre_affaires", 'line("RD") + line("RE")',
     f"[JO] RD + RE {VALIDER} ventes uniquement (cotisations, générosité et subventions exclues)"),
    ("resultat_activites_ordinaires", 'line("XC")', "[JO] poste XC"),
    ("resultat_hao", 'line("XD")', "[JO] poste XD"),
    ("resultat_net", 'line("XE")', "[JO] poste XE"),
    ("achats_consommes", '-(line("TA") + line("TB") + line("TC") + line("TE"))',
     f"[JO] TA, TB, TC, TE (charges présentées en négatif) {VALIDER} hors autres achats (TD)"),
    ("achats_fournisseurs", '-(line("TA") + line("TC") + line("TD") + line("TF") + line("TG"))',
     f"[JO] TA, TC, TD, TF, TG {VALIDER} base du délai fournisseurs"),
    ("charges_personnel", '-line("TJ")', "[JO] poste TJ"),
    ("charges_calculees", 'acct("68", "net_debit") + acct("69", "net_debit") + acct("85", "net_debit")',
     f"[JO] TL (68, 69) et dotations HAO (85) {VALIDER} même périmètre que la version SYSCOHADA"),
    ("produits_calcules", 'acct("79", "net_credit") + acct("86", "net_credit")',
     f"[JO] RH (79) et reprises HAO (86) {VALIDER} RH inclut les reprises de subventions"),
    ("produits_cessions", 'acct("82", "net_credit")', "[JO] plan : 82 produits des cessions d'immobilisations"),
    ("vnc_cessions", 'acct("81", "net_debit")', "[JO] plan : 81 valeurs comptables des cessions d'immobilisations"),
]
UNBOUND = ["marge_commerciale", "valeur_ajoutee", "excedent_brut_exploitation", "resultat_exploitation",
           "resultat_financier", "produits_encaissables_hors_ebe", "charges_decaissables_hors_ebe"]

# =====================================================================================
# 4. Plan de comptes ([JO] OCR, recoupé avec [XL])
# =====================================================================================
LINE_RE = re.compile(r"^\s*[|\[_]*\s*(\d{2,7})(\]?)\s*[|!.\-—:]?\s+(.+?)\s*$")
# comptes du modèle Excel absents du JO, écartés car en contradiction avec la numérotation du JO
XL_REJECT = {
    "6811": "libellé « Voyages et déplacements » : compte 6181 au JO (6811 relèverait des dotations)",
    "8321": "dons en nature HAO non affectés : numérotés 8311 au JO",
    "8325": "dons en nature HAO affectés : numérotés 8315 au JO",
    "8421": "dons en nature HAO vendus : numérotés 8411 au JO",
    "8422": "prestations de services en nature HAO : numérotées 8412 au JO",
}


def clean(label: str) -> str:
    label = re.sub(r"[|_]+", " ", label)
    label = re.sub(r"\s+[a-zA-Z]\s*$", "", label.strip())     # bruit OCR en fin de ligne (« e », « r »)
    label = label.replace("H.A.0.", "H.A.O.").replace("H.A.0O.", "H.A.O.").replace("H.A.0", "H.A.O")
    return " ".join(label.split()).strip(" .")


def nature(num: str) -> str:
    c, g = num[0], num[:2]
    if c == "1":
        return "capitaux_propres" if g in ("10", "11", "12", "13", "14", "15", "16", "17") else "passif"
    if c in "23":
        return "actif"
    if c in "45":
        return "mixte"
    if c == "6":
        return "charge"
    if c == "7":
        return "produit"
    if c == "8":
        return "charge" if g in ("81", "83", "85", "87") else "produit"
    return "hors_bilan"


def read_jo() -> dict[str, tuple[str, int]]:
    jo: dict[str, tuple[str, int]] = {}
    for f in sorted(OCR_DIR.glob("p*.txt")):
        page = int(f.stem[1:])
        for ln in f.read_text(encoding="utf-8").splitlines():
            mt = LINE_RE.match(ln)
            if not mt:
                continue
            num, bracket, label = mt.groups()
            if bracket:                      # « 433] » : le chiffre 1 final lu « ] » par l'OCR
                num += "1"
            if num[0] in "123456789" and num not in jo and len(clean(label)) > 2:
                jo[num] = (clean(label), page)
    return jo


def read_xl() -> dict[str, tuple[str, int]]:
    from openpyxl import load_workbook
    ws = load_workbook(SOURCE_XL, read_only=True, data_only=True)["Plan Comptable"]
    xl: dict[str, tuple[str, int]] = {}
    for i, r in enumerate(ws.iter_rows(values_only=True), start=1):
        num = str(r[5]).strip().rstrip(".") if len(r) > 5 and r[5] is not None else ""
        if num.isdigit() and num not in xl:
            xl[num] = (" ".join(str(r[6] or "").split()), i)
    return xl


def build_chart(report: list[str]) -> list[list[str]]:
    jo, xl = read_jo(), read_xl()
    out = []
    for num in sorted(set(jo) | set(xl)):
        if num in jo:
            label, page = jo[num]
            src = f"[JO] p. {page} (OCR)" + (" ; confirmé par [XL]" if num in xl else f" {VALIDER} absent de [XL]")
            out.append([num, label, nature(num), "", "", src])
        elif num in XL_REJECT:
            report.append(f"- Compte {num} du modèle Excel écarté : {XL_REJECT[num]}.")
        else:
            label, row = xl[num]
            out.append([num, label, nature(num), "", "",
                        f"[XL] ligne {row} {VALIDER} non retrouvé dans la lecture OCR du JO"])
    nums = {r[0] for r in out}
    for r in out:
        n = r[0]
        if len(n) > 2 and not any(n[:k] in nums for k in range(2, len(n))):
            report.append(f"- Compte {n} sans compte parent dans le plan (vérifier la lecture OCR).")
    report.append(f"- Plan : {sum(1 for r in out if 'confirmé' in r[5])} comptes JO confirmés par le modèle Excel, "
                  f"{sum(1 for r in out if 'absent de [XL]' in r[5])} comptes JO absents du modèle Excel, "
                  f"{sum(1 for r in out if r[5].startswith('[XL]'))} comptes du modèle Excel non retrouvés dans l'OCR.")
    return out


def main() -> None:
    report: list[str] = []
    chart = build_chart(report)
    nums = {r[0] for r in chart}
    with open(HERE / "plan_comptes.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["numero", "libelle", "nature", "sens", "imputable", "source"])
        w.writerows(chart)

    rows = []
    for etat, lines in (("bilan_actif", ACTIF), ("bilan_passif", PASSIF), ("compte_resultat", RESULTAT)):
        for order, (code, label, kind, formula, role, level) in enumerate(lines, start=1):
            rows.append([etat, code, label, order * 10, kind, formula or "", role or "", level])
    with open(HERE / "structure.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["etat", "code", "libelle", "ordre", "type", "formule", "role", "niveau"])
        w.writerows(rows)

    labels = {code: label for lines in (ACTIF, PASSIF, RESULTAT) for code, label, *_ in lines}
    with open(HERE / "correspondances.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["etat", "code_rubrique", "libelle_rubrique", "prefixe", "exclusions", "regle", "colonne", "signe",
                    "priorite", "source"])
        for etat, poste, prefixes, excl, regle, colonne, source in MAP:
            for p in prefixes:
                ex = [x for x in excl if x.startswith(p) and x != p]
                w.writerow([etat, poste, labels[poste], p, " ".join(ex), regle, colonne, 1, 100, source])
                if not any(n.startswith(p) for n in nums):
                    report.append(f"- Racine {p} (poste {poste}) absente du plan de comptes.")

    mapped = [p for _, _, prefixes, *_ in MAP for p in prefixes]
    for n, *_ in chart:
        if n[0] in "678" and not any(n.startswith(p) or p.startswith(n) for p in mapped if p not in ("6", "7", "8")):
            report.append(f"- Compte de gestion {n} rattaché à aucun poste du compte de résultat par la grille du JO.")

    with open(HERE / "concepts.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["concept", "expression", "source"])
        w.writerows(CONCEPTS)

    (HERE / "anomalies_sources.txt").write_text("\n".join(report) + "\n", encoding="utf-8")
    print(f"{len(chart)} comptes, {len(rows)} lignes d'états, {sum(len(x[2]) for x in MAP)} correspondances, "
          f"{len(CONCEPTS)} concepts ; {len(report)} remarque(s)")


if __name__ == "__main__":
    main()
