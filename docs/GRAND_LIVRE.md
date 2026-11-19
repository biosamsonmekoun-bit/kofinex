# KOFINEX — Grand livre (complément du lot 3)

Ce complément ajoute l'import et l'exploitation des écritures comptables d'un exercice. Il s'appuie sur le circuit d'import des balances (lot 3) : `import_jobs.kind = 'ledger'`, même cycle de vie, même stockage du fichier original et même journalisation.

**Principe** : aucun montant n'est deviné.
- Une cellule illisible met la ligne en erreur, et un grand livre comportant une seule ligne en erreur ne peut pas être validé.
- La convention de signe d'une colonne de montant unique est choisie par l'utilisateur.
- Les journaux d'à-nouveaux sont désignés par l'utilisateur.
- Aucun jour férié ni aucun seuil d'alerte n'est fixé par la plateforme.

> **Grand livre importé et grand livre natif.** Ce document décrit le grand livre **importé** (`ledger_lines`), inchangé par le lot 3B. Le grand livre calculé à partir des écritures saisies dans KOFINEX est décrit dans `ECRITURES_COMPTABLES.md` §5 ; il utilise d'autres tables et d'autres écrans (`/companies/{id}/comptabilite/grand-livre`).

## 1. Import (`/companies/{id}/grand-livre`)
- **Formats** : Excel (xlsx, xls) et CSV, quel que soit le séparateur. Le PDF n'est pas accepté pour un grand livre.
- **Colonnes** :
  - les en-têtes du fichier des écritures comptables (FEC : `JournalCode`, `EcritureNum`, `EcritureDate`, `CompteNum`, `CompAuxNum`, `PieceRef`, `EcritureLib`, `Debit`, `Credit`, `EcritureLet`, `ValidDate`…) sont reconnus tels quels ;
  - pour tout autre export, une association est proposée à partir des intitulés, et l'utilisateur la vérifie ;
  - l'association peut être enregistrée pour les imports suivants de l'entité.
- **Champs requis** : date d'écriture, numéro de compte, et soit Débit et Crédit, soit Montant accompagné d'une colonne Sens (D / C) ou d'une convention de signe. Les dates sont acceptées aux formats jj/mm/aaaa, aaaa-mm-jj, aaaammjj, jj-mm-aaaa, jj.mm.aaaa ou jj/mm/aa.
- **Contrôles** :

| Contrôle | Gravité |
|---|---|
| Lignes lisibles (date, compte, montants, sens) | bloquant |
| Dates comprises dans l'exercice | bloquant |
| Équilibre du grand livre (total débit = total crédit) | bloquant |
| Équilibre de chaque écriture, regroupée par journal et n° d'écriture (ou par journal, date et pièce) | bloquant ; non exécuté sans identifiant d'écriture |
| Comptes rattachés au plan du référentiel publié de l'exercice | avertissement |
| Rapprochement compte par compte avec la balance validée : mouvements du grand livre hors à-nouveaux = mouvements de la balance ; à-nouveaux = soldes d'ouverture, si des journaux d'à-nouveaux sont désignés | avertissement |

- Les avertissements doivent être **acceptés explicitement** à la validation : le grand livre et la balance peuvent venir d'extractions différentes, et c'est à l'utilisateur d'en juger.
- **La base revérifie à la validation** : aucune ligne en erreur, équilibre global, équilibre de chaque écriture numérotée, dates dans l'exercice. Le grand livre validé devient celui de l'exercice (`fiscal_years.active_ledger_import_job_id`) et remplace le précédent, qui reste consultable. Ses lignes sont **figées**.
- La balance de l'exercice n'est jamais modifiée. La base refuse aussi qu'un grand livre devienne la balance de l'exercice, et inversement.
- **Effet de l'import** (option `mode`) :
  - `replace` (par défaut) : le fichier remplace le grand livre validé ; c'est aussi la voie du **fichier correctif** complet ;
  - `complement` : le fichier complète le grand livre validé de l'exercice (refusé s'il n'y en a pas). L'import porte alors le grand livre validé repris, plus les seules lignes nouvelles :
    - une ligne identique à une ligne déjà validée (journal, n° d'écriture, date, compte, auxiliaire, débit, crédit, libellé sans tenir compte de la casse ni des espaces) est écartée comme doublon (`DUPLICATE_OF_ACTIVE`), ligne par ligne ;
    - une écriture déjà importée sous la même référence mais au contenu différent est refusée (`ENTRY_CONFLICT`, bloquant) : une modification passe par un remplacement ;
    - les contrôles portent sur le grand livre complet obtenu ; la synthèse (`controls.complement`) indique les lignes reprises, ajoutées, écartées, refusées, ainsi que les mois ajoutés et les mois déjà importés qui reçoivent des lignes ;
    - la validation est refusée si le grand livre actif a changé entre la lecture et la validation.
  - Dans les deux cas, un seul import est actif : rien n'est additionné deux fois. Aucune table ni migration supplémentaire (l'option est conservée avec les options de l'import).

## 2. Exploitation
- **Consultation** :
  - filtres : compte, racine, journal, tiers, période, texte, montant minimal et maximal, lettrage ;
  - **solde progressif** pour un compte exact, y compris à partir d'une date (le solde antérieur est repris) ; il n'est pas affiché si d'autres filtres rendraient le cumul trompeur ;
  - détail d'une écriture ;
  - export CSV des lignes filtrées.
- **Comptes** : à-nouveaux, débits, crédits et solde par compte. Chaque compte est rapproché de la balance validée (concordance ou écart) ; les comptes mouvementés dans la balance sans écriture au grand livre sont signalés.
- **Centralisation** : nombre d'écritures et totaux par journal et par mois de l'exercice.
- **Analyses de données** : elles signalent des écritures à examiner, sans qualifier d'anomalie.
  - écritures datées un samedi ou un dimanche ;
  - doublons possibles : même compte, même date, mêmes montants et même libellé dans des écritures distinctes ;
  - lignes sans libellé ;
  - écritures validées après la fin de l'exercice, si la date de validation est fournie ;
  - trous dans la numérotation des écritures, par journal (numéros entièrement numériques) ;
  - montants multiples d'une valeur saisie par l'utilisateur ;
  - répartition du premier chiffre des montants, comparée à la loi de Benford (log10(1 + 1/d)), sans test de conformité.

## 3. Utilisation par les autres modules
- **Contrôle de gestion (lot 5)** : le suivi budgétaire par racine de comptes affiche le **réalisé mensuel** tiré du grand livre validé, à-nouveaux exclus. Le réalisé annuel reste celui de la balance ; si le cumul mensuel en diffère, l'écart est signalé sur la ligne.
- **Audit financier (lot 7)** : une population « grand livre » est formée des lignes d'écritures de l'exercice audité, filtrées par racines, journaux, période, montant minimal ou sens (200 000 lignes au plus).
  - Elle vient obligatoirement du grand livre validé de l'exercice de la mission.
  - Chaque élément reprend exactement le montant net (débit − crédit) de sa ligne ; la base le vérifie.
  - L'échantillonnage du lot 7 s'applique ensuite sans changement.
- **Missions d'audit** : l'onglet « Grand livre » de la mission donne à l'équipe (indépendance déclarée) une lecture seule du grand livre de l'exercice audité. L'audité n'y a pas accès.

## 4. Accès
- Lecture : membres de l'entité, et équipe de mission sur l'entité auditée (`authz.audits_company`).
- Import et validation : rôle comptable de l'entité, ou administrateur de l'organisation.

## 5. Limites connues
- Pas de lecture des exports PDF de grand livre.
- Pas de reconstitution de la balance à partir du grand livre : la balance reste importée séparément, et les deux sont rapprochées.
- Pas encore d'analyse par utilisateur de saisie, faute de colonne normalisée dans les exports courants.

## 6. Tests
- `backend/tests/sql/test_general_ledger.sql` : 19 contrôles (lignes, validation refusée en base pour une ligne en erreur, un déséquilibre global ou par écriture, une date hors exercice ; grand livre actif ; gel ; accès ; populations d'audit).
- `backend/tests/engines/test_ledger.py` : 6 tests (FEC, association générique, lecture, contrôles, montant unique, analyses).
- `backend/tests/engines/test_management.py` : réalisé mensuel tiré du grand livre et écart avec la balance.
- `backend/tests/integration/test_ledger_api.py` : parcours API complet (CI).
- `backend/tests/engines/test_ledger_complement.py` : 4 tests de l'import complémentaire (exécutés ici, réussis).
- `backend/tests/integration/test_ledger_complement_api.py` : complément, refus d'une écriture modifiée, fichier correctif, historique (CI ; non exécuté ici).
