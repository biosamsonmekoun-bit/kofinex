# Référentiels et importation des balances

## 1. Référentiels SYSCOHADA révisé et SYSCEBNL

### Principe : aucune règle comptable dans le code

Le code définit **comment** un référentiel est chargé, validé, publié et appliqué. Le **contenu**
normatif (plan de comptes, rubriques des états financiers, rattachement des comptes aux rubriques)
est chargé depuis des fichiers transcrivant les textes officiels de l'OHADA, dans une **version**
datée et sourcée. Aucune version n'est livrée pré-remplie.

| Élément | Où |
|---|---|
| Profils distincts par référentiel (`SyscohadaRevise`, `Syscebnl`) : exigences avant publication | `app/engines/accounting/frameworks.py` |
| Lecture et validation des fichiers | `app/engines/accounting/reference_loader.py` |
| Verrouillage d'une version publiée (base de données) | `sql/0004_frameworks_imports.sql` |
| API d'administration | `app/api/v1/frameworks.py` |
| Interface | `/referentiels` |

### Cycle de vie d'une version

1. **Brouillon** — un administrateur de la plateforme crée la version : libellé, dates
   d'application, **référence précise du texte officiel** (obligatoire), lien éventuel.
2. **Plan de comptes** — dépôt d'un CSV/XLSX (`modele-plan-de-comptes.csv`). Refusé en bloc
   s'il contient une erreur (numéro invalide, doublon, classe 0, intitulé manquant, nature ou sens
   inconnus). La hiérarchie est déduite des racines présentes.
3. **Correspondances** — dépôt d'un CSV/XLSX (`modele-correspondances.csv`) rattachant des
   racines de comptes aux rubriques des états. Refusé si une ligne est invalide ou si un même
   compte est rattaché à deux rubriques d'un même état sans règle de priorité (ambiguïté).
4. **Vérification puis publication** — le profil du référentiel exige au minimum le plan de
   comptes et des correspondances pour le bilan (actif, passif) et le compte de résultat. Deux
   versions publiées d'un même référentiel ne peuvent pas couvrir la même période.
5. **Figée** — après publication, le plan, les correspondances et les métadonnées ne peuvent plus
   être modifiés ni supprimés (triggers en base, y compris pour un accès direct à la base). Seuls
   le retrait (`deprecated`) et la date de fin d'application restent possibles.

Les empreintes SHA-256 des fichiers chargés sont conservées sur la version, et chaque chargement
ou publication est inscrit au journal d'audit.

### Formats des fichiers

**Plan de comptes** — colonnes : `numero`, `libelle` (obligatoires), `nature`
(`actif | passif | capitaux_propres | produit | charge | hors_bilan | mixte`), `sens`
(`debit | credit | indifferent`), `imputable` (`oui | non`).
La nature des comptes de bilan est nécessaire au contrôle des à-nouveaux.

**Correspondances** — colonnes : `etat` (`bilan_actif | bilan_passif | compte_resultat |
flux_tresorerie | hors_bilan`), `code_rubrique`, `libelle_rubrique`, `prefixe`, `regle`
(`solde_debiteur | solde_crediteur | solde_net_debiteur | solde_net_crediteur |
mouvements_debit | mouvements_credit`) et, en option, `exclusions`, `colonne`
(`brut | amortissement | net`), `signe`, `priorite`, `source` (article, tableau, page).

### Fichiers de chargement fournis (dossier `referentiels/`)

| Dossier | Contenu | Validation |
|---|---|---|
| `syscohada_revise/` | Plan (1 404 comptes), structure (99 lignes), correspondances (211), concepts (30) | Cas pratique du manuel de montage reproduit au franc près (N et N-1, CAF comprise) |
| `syscebnl/` | Modèle associations / fondations : plan (1 149 comptes), structure (86 lignes), correspondances (194), concepts (23 / 30) | Chargement et couverture du plan ; pas de cas chiffré disponible |
| `tools/` | `verifier.py` (chargement + états + indicateurs sur une balance CSV), `essai_balance.py` (import complet d'un classeur), `couverture.py` (couverture du plan), `manuel_balance.py` (extraction des balances du manuel) | — |

Chaque dossier contient un `RAPPORT.md` (sources, méthode, résultats, **points à valider**) et
un `build.py` qui régénère les fichiers. Les fichiers sont des **projets** : ils se chargent dans
une version brouillon et ne sont publiés qu'après relecture par un expert-comptable.

Règles de correspondance retenues dans les deux référentiels : les comptes que la grille officielle
cite des deux côtés du bilan (tiers, banques) suivent la règle « solde débiteur / solde créditeur » ;
les autres sont repris pour leur **solde net**, afin qu'un solde de sens inhabituel apparaisse en
négatif au lieu de disparaître du bilan.

### Application aux entreprises

Une entreprise est rattachée à un référentiel à sa création. Pour chaque import, la version
applicable est la version **publiée** dont la période couvre la date de fin de l'exercice
(`public.applicable_framework_version`). Sans version publiée, l'import reste possible mais les
contrôles s'appuyant sur le plan de comptes sont signalés « non exécutés ».

### Utilisation par la comptabilité native (lot 3B)
Le plan comptable d'une entreprise qui tient sa comptabilité dans KOFINEX (`company_accounts`) est rattaché au plan de la version publiée applicable. Chaque compte de l'entreprise relève d'un compte du référentiel, dont il reprend la nature. Le référentiel n'est ni copié ni modifié ; aucune règle comptable n'est ajoutée dans le code. Voir `COMPTABILITE_NATIVE.md` §4.

## 2. Importation des balances

### Étapes

| Étape | Statut du job | Détail |
|---|---|---|
| Dépôt | `pending` | Vérification réelle du fichier (signature binaire, structure ZIP, macros refusées, taille, PDF chiffré refusé), empreinte SHA-256, détection d'un fichier déjà déposé, stockage **immuable** de l'original |
| Lecture | `parsing` | Excel (valeurs calculées ; formules sans valeur signalées), CSV (encodage et séparateur détectés), PDF texte (mots positionnés), PDF numérisé (OCR Tesseract français, 300 dpi) |
| Association | `awaiting_mapping` | Ligne d'en-tête détectée (y compris en-têtes sur deux niveaux), association des colonnes proposée, aperçu ; modèle enregistré de l'entreprise réappliqué automatiquement |
| Contrôles | `validating` → `awaiting_confirmation` | Normalisation de chaque ligne et contrôles de cohérence ; lignes de travail consultables |
| Validation | `completed` | Copie dans `trial_balance_entries`, contrôle final d'équilibre en base, l'import devient la balance active de l'exercice ; le précédent passe en `superseded` |

En production, la lecture et les contrôles s'exécutent dans des workers Celery
(`IMPORT_PROCESSING=celery`) ; l'interface suit l'avancement.

### Lecture des montants

Formats acceptés : `1 234 567,89`, `1.234.567,89`, `1,234,567.89`, `(1 500,00)`, `1 500,00-`,
espaces insécables, mention de devise. Calcul en `Decimal`, arrondi au centime. Une valeur ambiguë
(`1.234`, `1,234`) n'est **jamais devinée** : la ligne est signalée tant que le séparateur
décimal n'est pas précisé. Dispositions de colonnes prises en charge : débit/crédit pour
l'ouverture, les mouvements et la clôture, ou solde signé (convention à préciser) ; lorsque les
colonnes portent un repère d'exercice (« Solde N-2 », « Solde N-1 »), le plus ancien est proposé
comme ouverture et le plus récent comme clôture ; si la clôture
est absente, elle est calculée à partir de l'ouverture et des mouvements (et marquée comme telle).

### Contrôles de cohérence

| Code | Gravité | Contrôle |
|---|---|---|
| `ROW_ERRORS` | bloquant | Lignes illisibles (montant invalide, montants sans compte, montant négatif) |
| `BALANCE_EMPTY` | bloquant | Aucun compte exploitable |
| `DUPLICATE_ACCOUNT` | bloquant | Même compte sur plusieurs lignes |
| `AGGREGATE_ACCOUNTS` | bloquant (sauf option d'exclusion) | Compte égal au total de ses sous-comptes : double comptage |
| `OPENING_BALANCED`, `MOVEMENT_BALANCED`, `CLOSING_BALANCED` | bloquant (avertissement dans une tolérance explicite) | Total débit = total crédit |
| `ROW_ARITHMETIC` | bloquant | Solde de clôture = ouverture + mouvements, compte par compte |
| `DECLARED_TOTALS` | bloquant | Totaux du fichier (général et par classe) = montants recalculés |
| `CLOSING_BOTH_SIDES` | avertissement | Solde débiteur et créditeur simultanés |
| `OCR_CONFIDENCE` | avertissement | Lignes lues par OCR avec une confiance < 80 % |
| `ACCOUNT_CLASS` | bloquant | Classe absente du référentiel publié |
| `UNKNOWN_ACCOUNTS` | avertissement | Comptes non rattachables au plan publié |
| `OPENING_VS_PREVIOUS` | avertissement | À-nouveaux des comptes de bilan (natures actif, passif, capitaux propres et mixte — tiers, trésorerie) = clôture validée de l'exercice précédent |

Un avertissement doit être **explicitement accepté** à la validation ; l'acceptation est
enregistrée (utilisateur, date) avec l'événement `import.validated` du journal d'audit.

### Traçabilité

Document original (non modifiable, téléchargeable par lien signé de 5 min, téléchargements
journalisés) → job d'import (feuille, ligne d'en-tête, association, options, rapport de contrôles)
→ lignes de travail (ligne et page d'origine, données brutes, anomalies, confiance OCR)
→ lignes de balance (`raw_data`, ligne/page source).

## 3. Tests

| Fichier | Contenu |
|---|---|
| `tests/engines/test_numbers_accounts.py` | Formats de montants et de comptes |
| `tests/engines/test_import_pipeline.py` | Fichiers réels générés (Excel à double en-tête, CSV Windows-1252, PDF texte, PDF numérisé lu par OCR) jusqu'aux contrôles |
| `tests/engines/test_reference_loader.py` | Validation des plans de comptes et correspondances |
| `tests/sql/test_frameworks_imports.sql` | Verrouillage des versions, chevauchements, version applicable, RLS des lignes d'import |
| `tests/integration/test_imports_api.py` | Parcours API complet : référentiel de test publié, dépôt, association, contrôles, validation, remplacement, refus d'une balance déséquilibrée, exercice clôturé |

Toutes les données de test sont **fictives** (référentiel « de test », comptes et montants inventés
pour les tests) et ne constituent pas des règles comptables.
