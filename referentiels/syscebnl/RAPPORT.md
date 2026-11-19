# SYSCEBNL : rapport de transcription (modèle « associations, ordres professionnels, fondations et assimilés »)

**Statut : projet à faire valider par un expert-comptable avant la publication.** À charger dans une version « brouillon » du référentiel SYSCEBNL.

## Fichiers produits

| Fichier | Contenu | Volume |
|---|---|---|
| `plan_comptes.csv` | Plan de comptes (classes 1 à 9) : numéro, libellé, nature, source | 1 149 comptes |
| `structure.csv` | Bilan actif (AA à BZ), bilan passif (CA à DZ), compte de résultat (RA à XE) | 86 lignes |
| `correspondances.csv` | Racines de comptes → postes | 194 règles |
| `concepts.csv` | Liaison des concepts d'analyse | 23 concepts liés sur 30 |
| `ocr_jo/` | Texte OCR des pages 77 à 105 du JO (plan des comptes), conservé pour la relecture | 29 pages |
| `anomalies_sources.txt`, `build.py` | Remarques sur les sources ; générateur | — |

Interprétations marquées **[À VALIDER]** : 22 correspondances, 8 concepts, et 124 comptes du plan (voir « Plan de comptes »).

## Sources utilisées

- **[JO]** Acte uniforme relatif au système comptable des entités à but non lucratif, Journal officiel OHADA, 2023. `SYCEBNL-2022_fr.pdf` et `SYSCEBNL.pdf` sont le même document de 438 pages.
  - Le PDF ne contient pas de texte exploitable. Le plan des comptes (Partie 2, pp. 77-105) a donc été lu par **reconnaissance OCR**.
  - Les modèles du bilan (p. 346) et du compte de résultat (p. 347), ainsi que les tableaux de correspondance (pp. 395-396), ont été lus directement sur l'image des pages.
- **[XL]** `ETATS_FINANCIERS_DES_ASSOCIATIONS…SYCEBNL-1_1.xlsx` : utilisé **seulement pour recouper**, car il contient des erreurs :
  - le total DZ y soustrait l'écart de conversion-passif ;
  - les codes AG / AH sont en double pour les immobilisations financières ;
  - le poste « titres de placement » (BU) est absent ;
  - le passif contient un poste « provisions » en trop.
- `SYCEBNL-GUIDE-D-APPLICATION.pdf` : il contient 22 applications (écritures). Il ne contient pas d'états financiers chiffrés complets ; il n'a donc pas pu servir de cas de contrôle.

## Plan de comptes

- **1 025 comptes** lus dans le JO sont confirmés par le modèle Excel.
- **90 comptes** du JO sont absents du modèle Excel (groupes 38 à 41, 70x à 77x…). Ils sont repris, marqués **[À VALIDER] absent de [XL]**.
- **34 comptes** du modèle Excel n'ont pas été retrouvés dans l'OCR : par exemple 1211, 1281, 1291, 183, 566, 651. Ce sont probablement des lignes mal lues par l'OCR. Ils sont repris, marqués **[À VALIDER]**.
- **5 comptes** du modèle Excel sont écartés, car ils contredisent la numérotation du JO :
  - 6811 « Voyages et déplacements » est le compte 6181 du JO ;
  - 8321, 8325, 8421 et 8422 sont numérotés 8311, 8315, 8411 et 8412 au JO.
- **Natures** :
  - 10 à 17 : fonds propres (y compris les fonds affectés 16 et les fonds reportés 17, qui figurent dans « ressources propres ») ;
  - 18, 19 : passif ;
  - 2, 3 : actif ;
  - 4, 5 : mixte ;
  - 6 : charges ;
  - 7 : revenus ;
  - 8 : charges pour 81, 83, 85 et 87, revenus pour 82, 84, 86 et 88 ;
  - 9 : contributions volontaires en nature, hors bilan.
- **À relire en priorité** : les libellés proviennent de l'OCR. Les numéros sont recoupés avec le modèle Excel, mais une coquille peut subsister dans un libellé.

## Structure et correspondances

- **Totaux du bilan** : le modèle du JO ne donne pas de formules. Elles sont déduites de la présentation :
  - actif : AA = AB + AC ; AD = AE à AG ; AH = AI à AN ; AO = AX + AY ; AZ = AA + AD + AH + AO ; BT = BA à BE ; BX = BU à BW ; BZ = AZ + BT + BX + BY ;
  - passif : CK = CA à CJ ; CY = CW + CX ; CZ = CK + CY ; DD = DA à DC ; DE = CZ + DD ; DV = DF à DI ; DX = DW ; DZ = DE + DV + DX + DY.
- **XA** : le libellé du JO dit « somme RA à **RG** », mais le poste RH (reprises) figure au-dessus du total. Le modèle Excel additionne RA à RH, et le résultat XE ne serait pas juste sans RH. **RH est donc inclus.**
- **Compte de résultat en montants signés** (revenus +, charges −), comme pour la version SYSCOHADA. « XA − XB » s'écrit donc XA + XB dans le fichier.
- **Correspondances** : elles reprennent le tableau de correspondance du JO (pp. 395-396), avec les mêmes règles que la version SYSCOHADA :
  - soldes débiteurs / créditeurs pour les comptes cités des deux côtés ;
  - solde net pour les autres ;
  - CH = 13 + résultat des classes 6 à 8 (balance avant affectation).

## Points à valider

- **AG, amortissements** : la cellule est illisible dans le JO. **2951** a été retenu : c'est la valeur du modèle Excel, et elle est symétrique de AN (2952).
- **Comptes « p »** : 2919 va en AF ; 2939 va en AJ ; 2949 va en AL.
- **Comptes absents de la grille mais présents au plan, rattachés par analogie** :
  - 35 « Produits et services en cours » → BB ;
  - 46 « Bailleurs, État et autres organismes, fonds d'administration » → BE (solde débiteur) ou DI (solde créditeur) ;
  - 2817 « Amortissements des indemnités de transfert aux joueurs » → AF ;
  - soldes débiteurs des comptes 40 → BC ; soldes créditeurs des comptes 41 → DG.
- **Comptes de revenus non rattachés** : le tableau du JO ne cite pas **702** « Quote-part de fonds d'administration transférés », **7054** « Ventes de produits intermédiaires » ni **7055** « Ventes de produits résiduels ». Ils ne sont pas affectés d'office. Une balance qui les mouvemente sera bloquée par le contrôle « comptes non rattachés ». À trancher : 702 en RB ou en RG ? 7054 et 7055 en RE ?
- **585 et 588** (virements internes) : ils ne sont pas rattachés ; ils doivent être soldés à la clôture.
- **Concepts d'analyse** :
  - les « capitaux propres » des ratios = CK (fonds propres), sans les fonds affectés et reportés (CY) ;
  - le « chiffre d'affaires » = ventes (RD + RE), sans les cotisations, la générosité et les subventions ;
  - CAF additive : charges calculées = 68, 69 et 85 ; produits calculés = 79 et 86 (RH contient aussi les reprises de subventions) ;
  - marge commerciale, valeur ajoutée, EBE, résultat d'exploitation et résultat financier **n'existent pas** dans le modèle EBNL. Ils restent sans liaison : les ratios qui en dépendent, et la CAF soustractive, affichent « donnée manquante » au lieu d'un chiffre fabriqué.

## Contrôles effectués

- **Chargement par les lecteurs de la plateforme et validation du profil SYSCEBNL** : 0 erreur, publication possible.
- **Balance fictive** (montants tirés au hasard, non comptables) sur les 875 comptes terminaux :
  - bilan équilibré ;
  - résultat du bilan = résultat du compte de résultat ;
  - FR − BFR = trésorerie nette vérifié ;
  - les seuls comptes non repris sont ceux listés ci-dessus.

  Ce test est automatisé (`backend/tests/engines/test_referentiels_officiels.py`).
- **Aucun contrôle sur des chiffres réels** : aucune source ne fournit d'états EBNL chiffrés. Une vraie balance d'association avec ses états approuvés serait le meilleur contrôle.

## Non couvert

- **Modèle « projets de développement »** (`SYCEBNL-1_2`, et JO pp. 397-431) : il a ses propres états, son tableau emplois-ressources, son tableau d'exécution budgétaire et ses propres tableaux de correspondance. Il demande une version de référentiel distincte.
- **Système minimal de trésorerie des EBNL** et **tableau des flux de trésorerie** : non chargés.
