"""Génère les fichiers de chargement du référentiel SYSCOHADA révisé pour KOFINEX.

Sources (fournies par l'utilisateur, conservées dans ../sources/) :
  [PC]  PLAN_COMPTABLE_SYSCOHADA.xlsx, feuille « PC-SYSCOHADA REVISE » (liste des comptes)
  [TP]  DSF_20_SYSCOHADA.xlsm, feuilles « Bilan de passage » et « Compte de résultat de passage »
        (grille Postes / Comptes : « numéros de comptes à incorporer dans les postes »)
  [CAF] DSF_20_SYSCOHADA.xlsm, feuille « CAFG » (capacité d'autofinancement globale)
  [MAN] « Manuel de formation sur le processus de montage des états financiers selon le SYSCOHADA
        révisé » (cas pratique : bilan et compte de résultat, pp. 37-38 du PDF)

Chaque ligne produite indique sa source. Les choix d'interprétation sont listés dans RAPPORT.md
(section « Points à valider ») et marqués « [À VALIDER] » dans la colonne source.

Usage : python build.py  (écrit plan_comptes.csv, structure.csv, correspondances.csv, concepts.csv)
"""

from __future__ import annotations

import collections
import csv
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE_PC = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE.parent / "sources" / "PLAN_COMPTABLE_SYSCOHADA.xlsx"

TP_B = "[TP] Bilan de passage"
TP_R = "[TP] Compte de résultat de passage"
VALIDER = "[À VALIDER]"

# =====================================================================================
# 1. Structure des états (codes et intitulés : [TP] ; totaux : intitulés de [TP] et cas pratique [MAN])
# =====================================================================================
# (état, code, libellé, type, formule, rôle, niveau)
ACTIF = [
    ("AD", "IMMOBILISATIONS INCORPORELLES", "total", "AE + AF + AG + AH", None, 0),
    ("AE", "Frais de développement et de prospection", "detail", None, None, 1),
    ("AF", "Brevets, licences, logiciels et droits similaires", "detail", None, None, 1),
    ("AG", "Fonds commercial et droit au bail", "detail", None, None, 1),
    ("AH", "Autres immobilisations incorporelles", "detail", None, None, 1),
    ("AI", "IMMOBILISATIONS CORPORELLES", "total", "AJ + AK + AL + AM + AN", None, 0),
    ("AJ", "Terrains", "detail", None, None, 1),
    ("AK", "Bâtiments", "detail", None, None, 1),
    ("AL", "Aménagements, agencements et installations", "detail", None, None, 1),
    ("AM", "Matériel, mobilier et actifs biologiques", "detail", None, None, 1),
    ("AN", "Matériel de transport", "detail", None, None, 1),
    ("AP", "AVANCES ET ACOMPTES VERSÉS SUR IMMOBILISATIONS", "detail", None, None, 0),
    ("AQ", "IMMOBILISATIONS FINANCIÈRES", "total", "AR + AS", None, 0),
    ("AR", "Titres de participation", "detail", None, None, 1),
    ("AS", "Autres immobilisations financières", "detail", None, None, 1),
    ("AZ", "TOTAL ACTIF IMMOBILISÉ", "total", "AD + AI + AP + AQ", None, 0),
    ("BA", "ACTIF CIRCULANT HAO", "detail", None, None, 0),
    ("BB", "STOCKS ET ENCOURS", "detail", None, None, 0),
    ("BG", "CRÉANCES ET EMPLOIS ASSIMILÉS", "total", "BH + BI + BJ", None, 0),
    ("BH", "Fournisseurs, avances versées", "detail", None, None, 1),
    ("BI", "Clients", "detail", None, None, 1),
    ("BJ", "Autres créances", "detail", None, None, 1),
    ("BK", "TOTAL ACTIF CIRCULANT", "total", "BA + BB + BG", None, 0),
    ("BQ", "Titres de placement", "detail", None, None, 1),
    ("BR", "Valeurs à encaisser", "detail", None, None, 1),
    ("BS", "Banques, chèques postaux, caisse et assimilés", "detail", None, None, 1),
    ("BT", "TOTAL TRÉSORERIE-ACTIF", "total", "BQ + BR + BS", None, 0),
    ("BU", "Écart de conversion-Actif", "detail", None, None, 0),
    ("BZ", "TOTAL GÉNÉRAL", "total", "AZ + BK + BT + BU", "total_actif", 0),
]
PASSIF = [
    ("CA", "Capital", "detail", None, None, 1),
    ("CB", "Apporteurs capital non appelé (-)", "detail", None, None, 1),
    ("CD", "Primes liées au capital social", "detail", None, None, 1),
    ("CE", "Écarts de réévaluation", "detail", None, None, 1),
    ("CF", "Réserves indisponibles", "detail", None, None, 1),
    ("CG", "Réserves libres", "detail", None, None, 1),
    ("CH", "Report à nouveau (+ ou -)", "detail", None, None, 1),
    ("CJ", "Résultat net de l'exercice (bénéfice + ou perte -)", "detail", None, "resultat_bilan", 1),
    ("CL", "Subventions d'investissement", "detail", None, None, 1),
    ("CM", "Provisions réglementées", "detail", None, None, 1),
    ("CP", "TOTAL CAPITAUX PROPRES ET RESSOURCES ASSIMILÉES", "total",
     "CA + CB + CD + CE + CF + CG + CH + CJ + CL + CM", None, 0),
    ("DA", "Emprunts et dettes financières diverses", "detail", None, None, 1),
    ("DB", "Dettes de location-acquisition", "detail", None, None, 1),
    ("DC", "Provisions pour risques et charges", "detail", None, None, 1),
    ("DD", "TOTAL DETTES FINANCIÈRES ET RESSOURCES ASSIMILÉES", "total", "DA + DB + DC", None, 0),
    ("DF", "TOTAL RESSOURCES STABLES", "total", "CP + DD", None, 0),
    ("DH", "Dettes circulantes HAO", "detail", None, None, 1),
    ("DI", "Clients, avances reçues", "detail", None, None, 1),
    ("DJ", "Fournisseurs d'exploitation", "detail", None, None, 1),
    ("DK", "Dettes fiscales et sociales", "detail", None, None, 1),
    ("DM", "Autres dettes", "detail", None, None, 1),
    ("DN", "Provisions pour risques à court terme", "detail", None, None, 1),
    ("DP", "TOTAL PASSIF CIRCULANT", "total", "DH + DI + DJ + DK + DM + DN", None, 0),
    ("DQ", "Banques, crédits d'escompte", "detail", None, None, 1),
    ("DR", "Banques, établissements financiers et crédits de trésorerie", "detail", None, None, 1),
    ("DT", "TOTAL TRÉSORERIE-PASSIF", "total", "DQ + DR", None, 0),
    ("DV", "Écart de conversion-Passif", "detail", None, None, 0),
    ("DZ", "TOTAL GÉNÉRAL", "total", "DF + DP + DT + DV", "total_passif", 0),
]
RESULTAT = [
    ("TA", "Ventes de marchandises", "detail", None, None, 1),
    ("RA", "Achats de marchandises", "detail", None, None, 1),
    ("RB", "Variation de stocks de marchandises", "detail", None, None, 1),
    ("XA", "MARGE COMMERCIALE (somme TA à RB)", "total", "TA + RA + RB", None, 0),
    ("TB", "Ventes de produits fabriqués", "detail", None, None, 1),
    ("TC", "Travaux, services vendus", "detail", None, None, 1),
    ("TD", "Produits accessoires", "detail", None, None, 1),
    ("XB", "CHIFFRE D'AFFAIRES (A + B + C + D)", "total", "TA + TB + TC + TD", None, 0),
    ("TE", "Production stockée (ou déstockage)", "detail", None, None, 1),
    ("TF", "Production immobilisée", "detail", None, None, 1),
    ("TG", "Subventions d'exploitation", "detail", None, None, 1),
    ("TH", "Autres produits", "detail", None, None, 1),
    ("TI", "Transferts de charges d'exploitation", "detail", None, None, 1),
    ("RC", "Achats de matières premières et fournitures liées", "detail", None, None, 1),
    ("RD", "Variation de stocks de matières premières et fournitures liées", "detail", None, None, 1),
    ("RE", "Autres achats", "detail", None, None, 1),
    ("RF", "Variation de stocks d'autres approvisionnements", "detail", None, None, 1),
    ("RG", "Transports", "detail", None, None, 1),
    ("RH", "Services extérieurs", "detail", None, None, 1),
    ("RI", "Impôts et taxes", "detail", None, None, 1),
    ("RJ", "Autres charges", "detail", None, None, 1),
    ("XC", "VALEUR AJOUTÉE (XB + RA + RB) + (somme TE à RJ)", "total",
     "XB + RA + RB + TE + TF + TG + TH + TI + RC + RD + RE + RF + RG + RH + RI + RJ", None, 0),
    ("RK", "Charges de personnel", "detail", None, None, 1),
    ("XD", "EXCÉDENT BRUT D'EXPLOITATION (XC + RK)", "total", "XC + RK", None, 0),
    ("TJ", "Reprises d'amortissements, provisions et dépréciations", "detail", None, None, 1),
    ("RL", "Dotations aux amortissements, aux provisions et dépréciations", "detail", None, None, 1),
    ("XE", "RÉSULTAT D'EXPLOITATION (XD + TJ + RL)", "total", "XD + TJ + RL", None, 0),
    ("TK", "Revenus financiers et assimilés", "detail", None, None, 1),
    ("TL", "Reprises de provisions et dépréciations financières", "detail", None, None, 1),
    ("TM", "Transferts de charges financières", "detail", None, None, 1),
    ("RM", "Frais financiers et charges assimilées", "detail", None, None, 1),
    ("RN", "Dotations aux provisions et aux dépréciations financières", "detail", None, None, 1),
    ("XF", "RÉSULTAT FINANCIER (somme TK à RN)", "total", "TK + TL + TM + RM + RN", None, 0),
    ("XG", "RÉSULTAT DES ACTIVITÉS ORDINAIRES (XE + XF)", "total", "XE + XF", None, 0),
    ("TN", "Produits des cessions d'immobilisations", "detail", None, None, 1),
    ("TO", "Autres produits HAO", "detail", None, None, 1),
    ("RO", "Valeurs comptables des cessions d'immobilisations", "detail", None, None, 1),
    ("RP", "Autres charges HAO", "detail", None, None, 1),
    ("XH", "RÉSULTAT HORS ACTIVITÉS ORDINAIRES (somme TN à RP)", "total", "TN + TO + RO + RP", None, 0),
    ("RQ", "Participation des travailleurs", "detail", None, None, 1),
    ("RS", "Impôts sur le résultat", "detail", None, None, 1),
    ("XI", "RÉSULTAT NET (XG + XH + RQ + RS)", "total", "XG + XH + RQ + RS", "resultat_compte_resultat", 0),
]

# =====================================================================================
# 2. Correspondances (texte de [TP] ; « p » = compte réparti entre plusieurs postes)
# =====================================================================================
# (état, poste, racines, exclusions, règle, colonne, source)
D, C, ND, NC = "solde_debiteur", "solde_crediteur", "solde_net_debiteur", "solde_net_crediteur"
A, P, R = "bilan_actif", "bilan_passif", "compte_resultat"
MAP: list[tuple[str, str, list[str], list[str], str, str, str]] = []


def m(etat, poste, prefixes, regle, colonne="net", excl=(), source=""):
    MAP.append((etat, poste, list(prefixes), list(excl), regle, colonne, source))


# ---- actif : brut = soldes débiteurs ; amortissements / dépréciations = soldes créditeurs
def actif(poste, brut, amort, brut_excl=(), amort_excl=(), src_brut="", src_amort="", note_brut="", note_amort=""):
    if brut:
        m(A, poste, brut, ND, "brut", brut_excl, f"{TP_B} {poste} brut : « {src_brut} »{note_brut}")
    if amort:
        m(A, poste, amort, NC, "amortissement", amort_excl, f"{TP_B} {poste} amort./dépréc. : « {src_amort} »{note_amort}")


# Brut : solde net débiteur, amortissements : solde net créditeur, sauf grille « soldes débiteurs / créditeurs » :
# un solde de sens inhabituel reste ainsi visible (montant négatif) au lieu de disparaître du bilan.
P_NOTE = f" {VALIDER} compte « p » réparti dans la grille ; affecté en totalité à ce poste"
actif("AE", ["211", "2181", "2191"], ["2811", "2911"], src_brut="211,2181,2191",
      src_amort="2811,2818p,2911,2918p,2919p", note_amort=" (2818p, 2918p, 2919p affectés au poste AH)")
actif("AF", ["212", "213", "214", "2193"], ["2812", "2813", "2814", "2912", "2913", "2914"],
      src_brut="212,213,214,2193", src_amort="2812,2813,2814,2912,2913,2914,2919p",
      note_amort=" (2919p affecté au poste AH)")
actif("AG", ["215", "216"], ["2815", "2816", "2915", "2916"], src_brut="215,216", src_amort="2815,2816,2915,2916")
actif("AH", ["217", "218", "2198"], ["2817", "2818", "2917", "2918", "2919"], brut_excl=["2181"],
      src_brut="217,218, (sauf 2181), 2198", src_amort="2817,2818p,2917,2918p,2919p", note_amort=P_NOTE)
actif("AJ", ["22"], ["282", "292"], src_brut="22", src_amort="282, 292")
actif("AK", ["231", "232", "233", "237", "2391"], ["2831", "2832", "2833", "2837", "2931", "2932", "2933", "2937"],
      src_brut="231,232,233,237,2391", src_amort="2831,2832,2833,2837,2931,2932,2933,2937p", note_amort=P_NOTE)
actif("AL", ["234", "235", "238", "2392", "2393"], ["2834", "2835", "2838", "2934", "2935", "2938", "2939"],
      src_brut="234,235,238,2392,2393", src_amort="2834,2835,2838,2924,2935,2938,2939p",
      note_amort=f" {VALIDER} « 2924 » lu comme 2934 (2924 relève des terrains, poste AJ) ; 2939p affecté en totalité")
actif("AM", ["24"], ["284", "294", "2949"], brut_excl=["245", "2495"], amort_excl=["2845", "2945"],
      src_brut="24 (sauf 245 et 2495)", src_amort="284 (sauf 2845), 294 (sauf 2945,2949), 2949p",
      note_amort=f" {VALIDER} 2949p (aussi cité en AN) affecté en totalité à AM")
actif("AN", ["245", "2495"], ["2845", "2945"], src_brut="245,2495", src_amort="2845,2945,2949p",
      note_amort=" (2949p affecté au poste AM)")
actif("AP", ["251", "252"], ["2951", "2952"], src_brut="251,252", src_amort="2951,2952")
actif("AR", ["26"], ["296"], src_brut="26", src_amort="296")
actif("AS", ["27"], ["297"], src_brut="27", src_amort="297")
actif("BA", ["485", "488"], ["498"], src_brut="485,488", src_amort="498")
actif("BB", ["31", "32", "33", "34", "35", "36", "37", "38"], ["39"], src_brut="31,32,33,34,35,36,37,38", src_amort="39")
m(A, "BH", ["409"], ND, "brut", source=f"{TP_B} BH brut : « 409 »")
m(A, "BH", ["40"], D, "brut", ["409"], f"{VALIDER} soldes débiteurs des comptes 40 (sauf 409) : non cités par la grille ; "
  "classés en avances fournisseurs (non-compensation, comme la DSF fournie)")
m(A, "BH", ["490"], C, "amortissement", source=f"{TP_B} BH dépréc. : « 490 »")
m(A, "BI", ["41"], D, "brut", ["419"], f"{TP_B} BI brut : « 41 (sauf 419) » — soldes débiteurs")
m(A, "BI", ["491"], C, "amortissement", source=f"{TP_B} BI dépréc. : « 491 »")
m(A, "BJ", ["185", "42", "43", "44", "45", "46", "47"], D, "brut", ["478", "479"],
  f"{TP_B} BJ brut : « Soldes débiteurs : 185,42,43,44,45,46,47 (sauf 478) »")
m(A, "BJ", ["492", "493", "494", "495", "496", "497"], C, "amortissement", source=f"{TP_B} BJ dépréc. : « 492,493,494,495,496,497 »")
actif("BQ", ["50"], ["590"], src_brut="50", src_amort="590")
actif("BR", ["51"], ["591"], src_brut="51", src_amort="591")
m(A, "BS", ["52", "53"], D, "brut",
  source=f"{TP_B} BS brut : « Soldes débiteurs : 52,53,54,55,57,581,582 » (52, 53 : soldes créditeurs au poste DR)")
m(A, "BS", ["54", "55", "57", "581", "582"], ND, "brut",
  source=f"{TP_B} BS brut : « Soldes débiteurs : 52,53,54,55,57,581,582 » (54, 55, 57, 581, 582 : non cités au passif, solde net)")
m(A, "BS", ["592", "593", "594"], C, "amortissement", source=f"{TP_B} BS dépréc. : « 592,593,594 »")
m(A, "BU", ["478"], ND, "brut", source=f"{TP_B} BU : « 478 »")

# ---- passif : soldes nets créditeurs, sauf mention « solde créditeur »
for poste, prefixes, excl, src in [
    ("CA", ["101", "102", "103", "104"], [], "101 à 104"), ("CB", ["109"], [], "109"), ("CD", ["105"], [], "105"),
    ("CE", ["106"], [], "106"), ("CF", ["111", "112", "113"], [], "111,112,113"), ("CG", ["118"], [], "118"),
    ("CH", ["12"], [], "12 (121 ou 129)"), ("CL", ["14"], [], "14"), ("CM", ["15"], [], "15"),
    ("DA", ["16", "181", "182", "183", "184"], [], "16,181,182,183,184"), ("DB", ["17"], [], "17"),
    ("DC", ["19"], [], "19"), ("DH", ["481", "482", "484", "4998"], [], "481,482,484,4998"),
    ("DI", ["419"], [], "419"), ("DN", ["499", "599"], ["4998"], "499 (sauf 4998), 599"),
    ("DQ", ["564", "565"], [], "564,565"), ("DV", ["479"], [], "479"),
]:
    m(P, poste, prefixes, NC, excl=excl, source=f"{TP_B} {poste} : « {src} »")
m(P, "CJ", ["13"], NC, source=f"{TP_B} CJ : « 13 (131 ou 139) »")
m(P, "CJ", ["6", "7", "8"], NC, source=f"{VALIDER} balance avant affectation du résultat : produits − charges des classes "
  "6 à 8 (résultat de l'exercice, égal au poste XI) ; le contrôle « résultat bilan = compte de résultat » signale tout écart")
m(P, "DI", ["41"], C, excl=["419"], source=f"{VALIDER} soldes créditeurs des comptes 41 (sauf 419) : non cités par la grille ; "
  "classés en avances reçues (non-compensation, comme la DSF fournie)")
m(P, "DJ", ["40"], C, excl=["409"], source=f"{TP_B} DJ : « 40 (sauf 409) » — soldes créditeurs (soldes débiteurs : poste BH)")
m(P, "DK", ["42", "43", "44"], C, source=f"{TP_B} DK : « Solde créditeur : 42,43,44 »")
m(P, "DM", ["185", "45", "46", "47"], C, excl=["478", "479"], source=f"{TP_B} DM : « Solde créditeur : 185,45,46,47 (sauf 479) »")
m(P, "DR", ["52", "53"], C, source=f"{TP_B} DR : « Solde créditeur : 52,53,561,566 » (soldes débiteurs : poste BS)")
m(P, "DR", ["561", "566"], NC, source=f"{TP_B} DR : « Solde créditeur : 52,53,561,566 » (561, 566 : non cités à l'actif, solde net)")

# ---- compte de résultat : présentation signée (produits +, charges −), cf. [MAN] et intitulés des totaux
for poste, prefixes, src in [
    ("TA", ["701"], "701"), ("RA", ["601"], "601"), ("RB", ["6031"], "6031"), ("TB", ["702", "703", "704"], "702,703,704"),
    ("TC", ["705", "706"], "705,706"), ("TD", ["707"], "707"), ("TE", ["73"], "73"), ("TF", ["72"], "72"),
    ("TG", ["71"], "71"), ("TH", ["75"], "75"), ("TI", ["781"], "781"), ("RC", ["602"], "602"),
    ("RD", ["6032"], "6032"), ("RE", ["604", "605", "608"], "604,605,608"), ("RF", ["6033"], "6033"),
    ("RG", ["61"], "61"), ("RH", ["62", "63"], "62,63"), ("RI", ["64"], "64"), ("RJ", ["65"], "65"),
    ("RK", ["66"], "66"), ("TJ", ["791", "798", "799"], "791,798,799"), ("RL", ["681", "691"], "681,691"),
    ("TK", ["77"], "77"), ("TL", ["797"], "797"), ("TM", ["787"], "787"), ("RM", ["67"], "67"), ("RN", ["697"], "697"),
    ("TN", ["82"], "82"), ("TO", ["84", "86", "88"], "84,86,88"), ("RO", ["81"], "81"), ("RP", ["83", "85"], "83,85"),
    ("RQ", ["87"], "87"), ("RS", ["89"], "89"),
]:
    m(R, poste, prefixes, NC, source=f"{TP_R} {poste} : « {src} » (montant signé : produit +, charge −)")

# =====================================================================================
# 3. Concepts d'analyse
# =====================================================================================
CONCEPTS = [
    ("total_actif", 'line("BZ")', "[TP] poste BZ"),
    ("actif_immobilise", 'line("AZ")', "[TP] poste AZ (net)"),
    ("stocks", 'line("BB")', "[TP] poste BB (net)"),
    ("creances_clients", 'line("BI")', "[TP] poste BI (net)"),
    ("actif_circulant", 'line("BK") + line("BU")', f"[TP] BK + BU {VALIDER} écart de conversion-actif rattaché au circulant"),
    ("tresorerie_actif", 'line("BT")', "[TP] poste BT"),
    ("capitaux_propres", 'line("CP")', "[TP] poste CP"),
    ("dettes_financieres", 'line("DD")', "[TP] poste DD"),
    ("ressources_stables", 'line("DF")', "[TP] poste DF"),
    ("passif_circulant", 'line("DP") + line("DV")', f"[TP] DP + DV {VALIDER} écart de conversion-passif rattaché au circulant"),
    ("dettes_fournisseurs", 'line("DJ")', "[TP] poste DJ"),
    ("tresorerie_passif", 'line("DT")', "[TP] poste DT"),
    ("chiffre_affaires", 'line("XB")', "[TP] poste XB"),
    ("marge_commerciale", 'line("XA")', "[TP] poste XA"),
    ("valeur_ajoutee", 'line("XC")', "[TP] poste XC"),
    ("excedent_brut_exploitation", 'line("XD")', "[TP] poste XD"),
    ("resultat_exploitation", 'line("XE")', "[TP] poste XE"),
    ("resultat_financier", 'line("XF")', "[TP] poste XF"),
    ("resultat_activites_ordinaires", 'line("XG")', "[TP] poste XG"),
    ("resultat_hao", 'line("XH")', "[TP] poste XH"),
    ("resultat_net", 'line("XI")', "[TP] poste XI"),
    ("achats_consommes", '-(line("RA") + line("RB") + line("RC") + line("RD"))',
     f"[TP] RA à RD (charges présentées en négatif) {VALIDER} base : marchandises et matières, hors autres achats"),
    ("achats_fournisseurs", '-(line("RA") + line("RC") + line("RE") + line("RG") + line("RH"))',
     f"[TP] RA, RC, RE, RG, RH {VALIDER} base du délai fournisseurs (achats et services extérieurs, HT)"),
    ("charges_personnel", '-line("RK")', "[TP] poste RK"),
    ("charges_calculees", 'acct("681", "net_debit") + acct("691", "net_debit") + acct("697", "net_debit") '
     '+ acct("85", "net_debit")', "[TP] RL (681, 691), RN (697), dotations HAO (85) ; cohérent avec [CAF]"),
    ("produits_calcules", 'acct("791", "net_credit") + acct("798", "net_credit") + acct("799", "net_credit") '
     '+ acct("797", "net_credit") + acct("86", "net_credit")', "[TP] TJ (791, 798, 799), TL (797), reprises HAO (86) ; cohérent avec [CAF]"),
    ("produits_cessions", 'acct("82", "net_credit") + acct("754", "net_credit")',
     "[TP] TN (82) et [CAF] produits des cessions courantes (754)"),
    ("vnc_cessions", 'acct("81", "net_debit") + acct("654", "net_debit")',
     "[TP] RO (81) et [CAF] valeurs comptables des cessions courantes (654)"),
    ("produits_encaissables_hors_ebe", 'acct("77", "net_credit") + acct("787", "net_credit") + acct("84", "net_credit") '
     '+ acct("88", "net_credit") + acct("654", "net_debit") - acct("754", "net_credit")',
     "[CAF] revenus financiers (77), transferts de charges financières (787), produits HAO (84, 88) ; retraitement des "
     "cessions courantes (+654, −754)"),
    ("charges_decaissables_hors_ebe", 'acct("67", "net_debit") + acct("83", "net_debit") + acct("87", "net_debit") '
     '+ acct("89", "net_debit")', "[CAF] frais financiers (67), charges HAO (83), participation (87), impôts sur le résultat (89)"),
]

# =====================================================================================
# 4. Plan de comptes
# =====================================================================================
def nature(num: str) -> str:
    c, g = num[0], num[:2]
    if c == "1":
        return "capitaux_propres" if g in ("10", "11", "12", "13", "14", "15") else "passif"
    if c in "23":
        return "actif"
    if c in "45":
        return "mixte"
    if c == "6":
        return "charge"
    if c == "7":
        return "produit"
    if c == "8":
        return "charge" if g in ("81", "83", "85", "87", "89") else "produit"
    return "hors_bilan"


def build_chart(report: list[str]) -> list[list[str]]:
    from openpyxl import load_workbook

    wb = load_workbook(SOURCE_PC, read_only=True, data_only=True)
    ws = wb["PC-SYSCOHADA REVISE"]
    out, seen = [], {}
    dups = collections.defaultdict(list)
    for i, row in enumerate(ws.iter_rows(values_only=True), start=1):
        if i == 1 or row[0] is None:
            continue
        num = str(row[0]).replace("\xa0", "").strip()
        if num.endswith(".0"):
            num = num[:-2]
        label = " ".join(str(row[1] or "").split())
        if not num.isdigit():
            report.append(f"- Ligne {i} ignorée (numéro non numérique) : {row[0]!r}")
            continue
        if num in seen:
            dups[num].append((i, label))
            continue
        seen[num] = i
        out.append([num, label, nature(num), "", "", f"[PC] ligne {i}"])
    for num, extra in dups.items():
        first = next(r for r in out if r[0] == num)
        report.append(f"- Compte {num} présent plusieurs fois : conservé « {first[1]} » (ligne {seen[num]}) ; "
                      f"ignoré(s) : " + " ; ".join(f"ligne {i} « {lab} »" for i, lab in extra))
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
            rows.append([etat, code, label, order * 10, {"detail": "detail", "total": "total"}[kind], formula or "",
                         role or "", level])
    with open(HERE / "structure.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["etat", "code", "libelle", "ordre", "type", "formule", "role", "niveau"])
        w.writerows(rows)

    labels = {code: label for _, lines in (("", ACTIF), ("", PASSIF), ("", RESULTAT)) for code, label, *_ in lines}
    with open(HERE / "correspondances.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["etat", "code_rubrique", "libelle_rubrique", "prefixe", "exclusions", "regle", "colonne", "signe",
                    "priorite", "source"])
        for etat, poste, prefixes, excl, regle, colonne, source in MAP:
            for p in prefixes:
                ex = [x for x in excl if x.startswith(p) and x != p]
                w.writerow([etat, poste, labels[poste], p, " ".join(ex), regle, colonne, 1, 100, source])
                if not any(n.startswith(p) for n in nums):
                    report.append(f"- Racine {p} (poste {poste}) absente du plan de comptes source.")

    with open(HERE / "concepts.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["concept", "expression", "source"])
        w.writerows(CONCEPTS)

    (HERE / "anomalies_sources.txt").write_text("\n".join(report) + "\n", encoding="utf-8")
    print(f"{len(chart)} comptes, {len(rows)} lignes d'états, {sum(len(x[2]) for x in MAP)} correspondances, "
          f"{len(CONCEPTS)} concepts ; {len(report)} anomalie(s) de source")


if __name__ == "__main__":
    main()
