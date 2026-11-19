# SYSCOHADA révisé : rapport de transcription

**Statut : projet à faire valider par un expert-comptable avant la publication de la version dans la plateforme.**
Aucun fichier de ce dossier n'est publié automatiquement. Il faut le charger dans une version au statut « brouillon » (Référentiels → nouvelle version), le faire relire, puis publier.

## Fichiers produits

| Fichier | Contenu | Volume |
|---|---|---|
| `plan_comptes.csv` | Plan de comptes : numéro, libellé, nature, source | 1 404 comptes |
| `structure.csv` | Lignes du bilan actif, du bilan passif et du compte de résultat, avec les formules des totaux | 99 lignes |
| `correspondances.csv` | Racines de comptes → postes, avec la règle de solde et la colonne (brut / amortissements / net) | 211 règles |
| `concepts.csv` | Liaison des 30 concepts de la bibliothèque KOFINEX-STD-1 aux postes | 30 concepts |
| `anomalies_sources.txt` | Défauts relevés dans les fichiers sources | 10 |
| `build.py` | Générateur : relancer `python build.py` reproduit les fichiers | — |

Chaque ligne indique sa source dans la colonne `source`. Une interprétation qui n'est pas écrite telle quelle dans une source est marquée **[À VALIDER]** : 28 correspondances et 4 concepts.

## Sources utilisées

- **[PC]** `PLAN_COMPTABLE_SYSCOHADA.xlsx`, feuille « PC-SYSCOHADA REVISE » : liste des comptes.
- **[TP]** `DSF_20_SYSCOHADA.xlsm`, feuilles « Bilan de passage » et « Compte de résultat de passage » : grille *postes / numéros de comptes à incorporer*. C'est le **texte** de la grille qui fait foi, pas les formules Excel de la DSF : celles-ci contiennent des erreurs (le poste DR n'a pas la même formule en N et en N-1, AI inclut AP, BH ajoute 401).
- **[CAF]** `DSF_20_SYSCOHADA.xlsm`, feuille « CAFG » : composition de la capacité d'autofinancement globale.
- **[MAN]** « Montage des états financiers du SYSCOHADA révisé » : cas pratique utilisé pour le contrôle des résultats.
- `REFERENTIEL_SYSCOHADA.pdf` (AUDCIF) : consulté pour le cadre général. Les fiches de la version peuvent reprendre : Acte uniforme relatif au droit comptable et à l'information financière, adopté le 26 janvier 2017 à Brazzaville (JO OHADA, numéro spécial du 15 février 2017).

## Contrôles effectués

1. **Chargement par les lecteurs de la plateforme.** Les quatre fichiers passent par les mêmes fonctions que l'interface (`parse_chart`, `parse_mappings`, `parse_structure`, `parse_concepts`), puis par la validation du profil SYSCOHADA. Résultat : 0 erreur, publication possible.
2. **Cas pratique du manuel [MAN].** Les balances N et N-1 du manuel ont été extraites du PDF, contrôlées (équilibre et ouverture + mouvements = clôture pour chaque compte), puis traitées par le moteur :

   | | N | N-1 | Manuel |
   |---|---|---|---|
   | Total bilan (BZ = DZ) | 1 054 424 478 | 446 088 093 | identique |
   | Brut / amortissements N | 1 407 259 359 / 352 834 881 | | identique |
   | Capitaux propres (CP) | 656 959 701 | | identique |
   | Résultat net (XI = CJ) | 215 389 710 | 118 619 674 | identique |
   | CAF globale, méthode additive = soustractive | 241 773 904 | 150 177 096 | identique (TFT, ligne FA) |

   Toutes les lignes du compte de résultat sont égales à celles du manuel. Contrôles croisés : FR − BFR = trésorerie nette, et CAF additive = CAF soustractive.
3. **Vos balances** (`BALANCE_N_et_N-1SYSCOHADA.xlsm` et `BALANCE_GENERALE_DES_COMPTES_SYSCOHADA.xlsx`) : importées par le module d'import de la plateforme (détection de l'en-tête et des colonnes, contrôles de cohérence), puis états produits. On obtient les mêmes chiffres que dans le tableau ci-dessus. Les deux balances sont équilibrées : 162 comptes en N, 146 en N-1, aucune ligne rejetée.
4. **Couverture du plan** (test automatique `test_referentiels_officiels.py`) : une balance fictive affecte un solde à chacun des 1 057 comptes terminaux. Le bilan doit s'équilibrer et le résultat doit être le même au bilan et au compte de résultat. Les seuls comptes non repris sont ceux que la grille ne cite pas (voir ci-dessous).

### Corrections apportées au module d'import pendant ces essais

- Les colonnes « Solde N-2 / Solde N-1 » sont désormais classées **par exercice** : le solde le plus ancien est pris comme ouverture, le plus récent comme clôture. Avant, la balance N-1 était lue à l'envers.
- Le mot « mouvement » prime sur le repère d'exercice : « Mouvement N-1 » n'est plus pris pour une ouverture.
- La colonne de solde signé n'est plus proposée lorsque les colonnes débit/crédit du même solde existent.
- Les en-têtes « débiteur », « créditeur », « intitulés » et « cptes » sont maintenant reconnus.

## Points à valider

**Répartition des comptes « p » (comptes répartis entre plusieurs postes par la grille)** : la plateforme rattache chaque compte à un seul poste.
- 2818, 2918 et 2919 vont en AH (et non en AE / AF). 2937 va en AK. 2939 va en AL. 2949 va en AM (et non en AN).
- La grille du poste AL cite « 2924 ». Ce compte a été lu comme **2934** : 2924 relève des terrains (poste AJ).

**Comptes de tiers à deux sens (non-compensation)** :
- Les soldes débiteurs des comptes 40 (sauf 409) vont en **BH**. Pour les comptes 41, les soldes débiteurs vont en BI et les soldes créditeurs (sauf 419) en **DI**. La grille ne cite pas ces cas. C'est aussi le traitement de la DSF fournie.
- 478 et 479 sont repris **en totalité** en BU / DV. Ils sont exclus des postes BJ et DM des deux côtés : sans cela, ils seraient comptés deux fois.

**Sens des soldes** : un compte qui n'est cité que d'un côté de la grille est repris pour son **solde net**. Un solde de sens inhabituel apparaît alors en négatif au lieu de disparaître du bilan. Par exemple, des titres de placement créditeurs donneraient un BQ négatif. Les règles « soldes débiteurs / créditeurs » ne s'appliquent qu'aux comptes que la grille cite des deux côtés : 40, 41, 42 à 47, 185, 52, 53.

**Résultat au bilan (CJ)** : CJ = 13 + (produits − charges des classes 6 à 8). Cette formule permet de traiter une balance avant affectation du résultat. Le contrôle « résultat bilan = compte de résultat » signale tout écart.

**Comptes que la grille ne rattache à aucun poste** : la plateforme les signale à l'import (contrôle « comptes non rattachés ») et ne les affecte pas d'office.
- 186, 187, 188 (comptes de liaison) ;
- 2394, 2395, 2398 ;
- 585, 588 (virements internes, normalement soldés). Votre balance N contient le compte 585000, avec un solde nul.

**Concepts d'analyse** :
- L'actif circulant inclut l'écart de conversion-actif (BK + BU), et le passif circulant l'écart de conversion-passif (DP + DV).
- Achats consommés = RA à RD.
- Base du délai fournisseurs = RA, RC, RE, RG, RH.

**Codes du manuel** : le cas pratique du manuel utilise d'autres codes pour le haut du passif (CD = écarts, CF = report à nouveau…). Les montants correspondent ligne à ligne ; les codes retenus sont ceux de la DSF officielle.

**Défauts du plan de comptes source** (`anomalies_sources.txt`) :
- Les en-têtes 70 et 88 sont absents.
- Des comptes sont en double : 219, 416, 4781, 4783, 4791, 4793, 4998, 91. La ligne 699 « Apporteurs, opérations sur le capital » est probablement le compte 461.
- Les racines 214 et 484, citées par la grille, sont absentes du plan.

## Non couvert

- **Tableau des flux de trésorerie** : sa présentation n'est pas encore chargée. La CAF est calculée par la bibliothèque.
- **Système minimal de trésorerie** (`SYSCOHADA_LIASSE_SMT.xlsx`) : à charger comme une version distincte si vous en avez besoin.
