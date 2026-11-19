# KOFINEX — Audit financier et comptable (lot 7)

Onglet « Audit financier » des missions d'audit légal et contractuel (`statutory_audit`, `contractual_audit`). Il s'appuie sur le socle du lot 6 (équipe, indépendance, feuilles, signatures, éléments probants, gel) et sur les balances validées et les états des lots 3 et 4.

**Principe** : KOFINEX ne fixe aucun pourcentage de seuil, aucune taille d'échantillon, aucun facteur de confiance. Ce sont des saisies de l'auditeur, justifiées, ou des paramètres de sa méthodologie. Le moteur (`engines/audit/financial.py`) ne fait que des calculs exacts en `Decimal` et des tirages reproductibles.

## 1. Seuils
- Seuil de signification = montant de référence × pourcentage. Le seuil de planification et le seuil des anomalies insignifiantes sont exprimés en % du seuil de signification. Les montants sont arrondis au centime.
- Référence : une **ligne des états** de l'exercice, recalculée depuis la balance validée (valeur absolue, rattachée à l'import), ou un **montant saisi**.
- Justification obligatoire. Les paramètres de la méthodologie de la mission sont affichés pour mémoire.
- Versions : brouillon → approuvée (manager ou associé, en son nom) → remplacée. Une version approuvée est figée. En base, les montants doivent être le produit exact des pourcentages.

## 2. Cycles et revue des comptes
- Rattachement des comptes aux cycles **de la méthodologie** par préfixe ; le préfixe le plus long l'emporte. Les préfixes proposés par la méthodologie (`account_prefixes` dans le contenu d'un cycle) peuvent être repris.
- Revue des comptes établie depuis les balances validées N et N-1 : soldes, variation, total par cycle (feuille maîtresse).
- **La base vérifie** que chaque solde est celui de la balance validée et que le seuil appliqué est le seuil de planification approuvé.
- Une variation (ou un solde, sans N-1) égale ou supérieure à ce seuil doit être **expliquée** avant de conclure. Si un solde change à la suite d'un nouvel import, le compte repasse « à revoir ».

## 3. Populations, échantillons, tests
- **Population** créée depuis les **écritures du grand livre validé** (filtres par racines, journaux, période, montant, sens ; chaque montant vérifié en base), depuis les comptes de la balance validée (par préfixes) ou depuis un **fichier probant** CSV/XLSX (liste de factures, etc.). Le fichier est lu côté serveur avec un aperçu et une association des colonnes.
- Un fichier comportant une seule ligne illisible est rejeté entièrement. La population porte une empreinte SHA-256 et elle est **figée dès le premier tirage**.
- **Méthodes de sélection** : aléatoire simple, systématique, unités monétaires (UM), éléments clés au-dessus d'un seuil, sélection raisonnée.
  - Les tirages sont faits par le moteur, avec une graine aléatoire conservée : ils sont reproductibles.
  - La base refuse tout échantillon et tout élément inséré hors du moteur, ainsi que toute modification des paramètres.
  - Le fondement de la taille ou de la sélection est obligatoire.
- **Tests** élément par élément : sans anomalie (le montant audité est égal au montant comptable) ou anomalie (montant audité et description requis), enregistrés au nom du testeur.
- **Conclusion** : tous les éléments doivent être testés. Le moteur calcule l'anomalie constatée et l'**estimation ponctuelle** extrapolée :
  - aléatoire et systématique : estimation par le ratio ;
  - UM : taux d'anomalie × intervalle, et anomalie réelle pour les éléments ≥ intervalle ;
  - éléments clés et sélection raisonnée : pas d'extrapolation.

  La **limite supérieure d'anomalie n'est pas calculée** : elle exige les facteurs de confiance de la méthodologie. Seul l'encadrement de la mission peut rouvrir un échantillon conclu.

## 4. Circularisations
- Demandes uniques ou une demande par élément d'une population ou d'un échantillon. Types : client, fournisseur, banque, avocat, autre. Formes : positive, négative, en blanc.
- Cycle : préparée → envoyée (date requise) → reçue (date et montant confirmé) ou sans réponse → close.
  - L'écart (solde comptable − montant confirmé) est calculé.
  - Une demande ne peut pas être close sans **rapprochement** si l'écart est non nul, ni sans **procédures alternatives** si elle est restée sans réponse (forme positive ou en blanc).
  - Conclusion obligatoire.
- Une demande envoyée ne peut plus être modifiée ni supprimée. Les relances sont datées. La liste s'exporte en CSV pour le publipostage ; les réponses reçues se joignent comme éléments probants.

## 5. Anomalies et ajustements
- Chaque anomalie porte une **écriture d'ajustement proposée**, équilibrée et d'au moins deux lignes ; ce contrôle est fait en base à la validation de la transaction.
- Nature : avérée, de jugement ou extrapolée (une anomalie extrapolée provient obligatoirement d'un échantillon). La source (échantillon, circularisation, compte) doit exister dans la mission.
- Décision par l'encadrement : **corrigée par l'entité**, **non corrigée** (réponse de l'entité requise) ou **retirée** (motif requis). Une fois la décision prise, l'écriture est figée.
- **Effets** de chaque anomalie et du cumul sur chaque ligne des états, calculés par le même moteur que les états publiés (lot 4) : effet sur le résultat et sur le total de l'actif.
- Position par rapport aux seuils approuvés (sous le seuil des anomalies insignifiantes, sous le seuil de signification, ou égale ou supérieure) : c'est une **comparaison arithmétique, pas une conclusion**.
- **Balance ajustée** = balance validée + ajustements corrigés ; elle est calculée et exportable en CSV, et la balance importée n'est jamais modifiée.
- **Conclusion sur les anomalies non corrigées** : rédigée par le manager ou l'associé, obligatoire avant l'émission dès qu'il en existe une.

## 6. Conditions d'émission ajoutées (imposées en base)
Seuils approuvés ; tous les comptes revus ; tous les échantillons conclus ; toutes les circularisations closes ; une décision sur chaque anomalie ; une conclusion si des anomalies restent non corrigées. Ces conditions s'ajoutent à celles du socle et figurent dans la supervision.

## 7. Accès
- Lecture du dossier : équipe d'audit ayant déclaré son indépendance (`authz.can_read_dossier`).
- **Lecture seule des balances, exercices et imports de l'entité auditée** pour l'équipe de mission tant que la mission n'est pas archivée (`authz.audits_company`, migration 0008). L'audité n'en bénéficie pas.
- Écriture :
  - seuils et cycles : associé, manager, chef de mission ;
  - travaux : jusqu'à l'assistant ;
  - décisions sur les anomalies : chef de mission et au-dessus ;
  - approbation des seuils et conclusion sur les anomalies non corrigées : manager et associé.

## 8. Limites connues
- Pas de limite supérieure d'anomalie, ni de calcul de taille d'échantillon. Les deux dépendent de paramètres de méthodologie à définir.
- Pas encore de lettres de circularisation générées (lot 11), de dossier de synthèse ni de rapport (lot 11), ni de réutilisation des tests de contrôle interne (lot 9).

## 9. Tests
- `backend/tests/sql/test_financial_audit.sql` : 57 contrôles (seuils, soldes vérifiés, tirages par le moteur, tests, conclusions, circularisations, écritures équilibrées, décisions, cloisonnement, lecture des balances, émission, gel).
- `backend/tests/engines/test_financial_audit.py` : 8 tests de calculs vérifiés à la main.
- `backend/tests/integration/test_financial_audit_api.py` : parcours API complet (CI).
