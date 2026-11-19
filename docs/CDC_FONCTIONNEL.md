# KOFINEX — Cahier des charges fonctionnel

> Ce document consolide le cahier des charges initial et l'extension « audit et contrôle interne » de novembre 2026. Les règles détaillées des modules déjà livrés sont dans `REFERENTIELS_ET_IMPORTS.md` et `MOTEUR_FINANCIER.md`.

## 1. Utilisateurs

| Profil | Exemples | Besoin principal |
|---|---|---|
| Cabinet | expert-comptable, commissaire aux comptes, cabinet d'audit | Gérer plusieurs entités clientes en toute confidentialité ; conduire des missions |
| Entreprise ou groupe | DAF, contrôleur de gestion, comptable | Piloter ses propres entités |
| Direction de l'audit interne | directeur de l'audit interne, auditeurs | Programme annuel, missions, suivi des plans d'action |
| Fonction contrôle interne / conformité | responsable du contrôle interne, propriétaires de processus | Matrices risques-contrôles, tests, évaluation |
| Audité | responsable d'un processus, comptable du client | Fournir les documents demandés, répondre aux constats, mettre à jour ses plans d'action |
| Gouvernance | comité d'audit, conseil d'administration | Consulter les rapports et le suivi des recommandations (lecture seule) |
| Administrateur de la plateforme | équipe KOFINEX | Abonnements, référentiels officiels, supervision |

## 2. Domaines fonctionnels

### 2.1 Comptabilité SYSCOHADA / SYSCEBNL — *livré (lots 1-3)*
- Les référentiels sont des données versionnées et sourcées, figées une fois publiées (plan de comptes, structure des états, correspondances, concepts).
- Import des balances : Excel, CSV, PDF texte, PDF numérisé (OCR), avec contrôles de cohérence. Une balance ne peut pas être validée tant qu'un contrôle bloquant échoue.
- **À compléter** :
  - import du **grand livre / journal des écritures**, indispensable à l'audit (tests sur les écritures, échantillonnage, analyses de données) ;
  - tableau des flux de trésorerie ;
  - modèle SYSCEBNL « projets de développement ».

### 2.2 Analyse financière — *livré (lot 3)*
- Bilan et compte de résultat (N et N-1), soldes intermédiaires de gestion (SIG), capacité d'autofinancement (CAF) par deux méthodes, fonds de roulement / besoin en fonds de roulement / trésorerie nette (FR/BFR/TN), ratios, comparaisons pluriannuelles.
- Les formules sont versionnées et calculées en `Decimal`.
- **À compléter** : règles d'alerte, comparaison sectorielle (si données sourcées).

### 2.3 Contrôle de gestion
Budgets et versions budgétaires, réalisé alimenté par les balances importées, écarts, centres de coûts, analyse des coûts, tableaux de bord. Les tables de base existent déjà (`budgets`, `budget_lines`, `budget_actuals`, `cost_centers`, `cost_entries`).

### 2.4 Socle commun d'audit (missions)
Ce socle sert à l'audit financier, à l'audit interne et à l'évaluation du contrôle interne.

| Fonction | Exigences |
|---|---|
| **Missions** | Type de mission (audit légal, audit contractuel, mission d'audit interne, évaluation du contrôle interne), entité auditée, exercice ou période, objectifs, périmètre, calendrier, statut. |
| **Équipe** | Rôles de mission : associé, manager, chef de mission, auditeur, réviseur qualité, contact audité. Affectation, charge prévue et réalisée, déclaration d'indépendance avant l'accès aux données. |
| **Planification** | Jalons, budget d'heures, liste des documents demandés à l'audité avec relances et dépôt sécurisé par l'audité. |
| **Évaluation des risques** | Risques identifiés au niveau de l'entité et au niveau des cycles/assertions ou des processus. Cotation selon la grille de la méthodologie (probabilité × impact, risque inhérent / risque lié au contrôle). Réponse prévue pour chaque risque. |
| **Programmes de travail** | Bibliothèque de programmes types (données de la méthodologie, versionnées). Chaque procédure est liée aux risques qu'elle couvre ; un risque sans procédure est signalé. |
| **Feuilles de travail** | Objectif, travaux réalisés, conclusion, références croisées. Versionnées ; une feuille signée puis modifiée perd sa signature. |
| **Éléments probants** | Fichiers déposés (originaux immuables, empreinte SHA-256) ou extractions de la plateforme (balance, écritures, états) figées à une date. Ils sont liés aux procédures, aux feuilles et aux constats. |
| **Constats et recommandations** | Constat, critère, cause, conséquence, recommandation, niveau de priorité, réponse de l'audité. |
| **Plans d'action** | Responsable, échéance, état d'avancement, preuves de mise en œuvre ; clôture validée par l'auditeur. |
| **Revue et supervision** | Notes de revue avec réponse obligatoire. Signatures « préparé par » et « revu par ». La mission n'est approuvée que si toutes les notes sont soldées. Revue qualité indépendante, si la méthodologie l'exige. |
| **Clôture et archivage** | Après émission du rapport, le dossier est figé dans le délai d'archivage défini par la méthodologie. Il n'est ensuite consultable qu'en lecture ; toute modification exige une réouverture motivée et tracée. |

### 2.5 Audit financier et comptable
- **Seuils de signification** : calculés à partir des états financiers produits par la plateforme. Ils comprennent le seuil global, le seuil de planification et le seuil des anomalies manifestement insignifiantes. **Le référentiel de calcul et le pourcentage sont choisis par l'auditeur et justifiés.** La plateforme propose les options de la méthodologie chargée ; elle ne fixe aucun pourcentage dans le code.
- **Audit par cycles** (ventes-clients, achats-fournisseurs, stocks, immobilisations, trésorerie, personnel, capitaux propres et provisions, impôts…). Les cycles sont rattachés aux comptes par la méthodologie, et chaque cycle est évalué selon les assertions.
- **Revue analytique** : variations N/N-1 et ratios, réutilisés depuis le moteur financier.
- **Tests et échantillonnage** :
  - échantillonnage aléatoire, systématique, par unités monétaires ou par sélection ciblée ;
  - graine conservée, donc échantillon reproductible ;
  - population tirée des écritures ou de la balance ;
  - résultat de chaque élément testé ; extrapolation des anomalies.
- **Circularisations** : tiers, montant, envoi, relance, réponse, écart, conclusion.
- **Anomalies et ajustements** :
  - types : anomalie factuelle, de jugement ou extrapolée ;
  - écritures d'ajustement proposées, puis acceptées ou refusées par l'entité ;
  - **balance et états ajustés calculés sans modifier la balance importée** ;
  - synthèse des anomalies non corrigées comparée aux seuils.
- **Rapports** : synthèse de mission, lettre de recommandations, projet de rapport d'opinion. Le texte normatif du rapport provient de modèles fournis et validés par le cabinet, **jamais généré librement**.

### 2.6 Audit interne
- **Univers d'audit et cartographie des processus** : macro-processus, processus, sous-processus et propriétaires.
- **Cartographie des risques** : risques par processus, cotation, risques résiduels.
- **Programme annuel** : missions proposées à partir de la cartographie, priorisation, ressources, approbation (comité d'audit), suivi de la réalisation.
- **Missions** : socle commun (§ 2.4).
- **Suivi des plans d'action** : l'audité met à jour ses plans ; relances automatiques ; tableau de bord des recommandations par ancienneté et par priorité, à destination du comité d'audit.

### 2.7 Contrôle interne
- **Référentiels de contrôle interne** : cadre, composantes, principes, chargés comme données versionnées et sourcées, de la même façon que les référentiels comptables. Aucun cadre n'est codé en dur.
- **Matrices risques-contrôles** : chaque contrôle porte sa nature (préventif / détectif, manuel / automatique), sa fréquence, son propriétaire, les risques couverts et les assertions ou objectifs concernés.
- **Tests** :
  - test de conception, puis test d'efficacité opérationnelle ;
  - taille d'échantillon fixée par l'utilisateur ou sa méthodologie, avec son fondement (jamais proposée par KOFINEX) ;
  - résultat et déficiences constatées.
- **Évaluation** : efficacité par contrôle, par processus et par composante. Déficiences classées selon la grille de la méthodologie, avec plan de remédiation (plans d'action du socle).
- **Lien avec l'audit financier** : quand un cycle s'appuie sur les contrôles, l'auditeur réutilise les tests de contrôle interne au lieu de les ressaisir.
- **Livré au lot 9** (détail dans `CONTROLE_INTERNE.md`) : référentiels multi-cadres distingués par nature (cadre de contrôle interne, référentiel professionnel d'audit, exigence juridique ou comptable), correspondances motivées ; domaines et cycles configurables à partir de modèles ; registre des risques partagé ; catalogue des contrôles (existant, attendu, non formalisé, absent) ; matrice N-N ; exécutions supervisées ; programmes et tests de conception et d'efficacité ; évaluations figées ; déficiences et plans de remédiation du lot 8 ; prise en compte motivée par l'audit financier ; tableau de bord et neuf rapports établis sur les données revues.

### 2.8 Intelligence artificielle appliquée à la finance et à l'audit
L'IA assiste, elle ne décide pas.

| Usage | Ce que fait l'IA | Garde-fous |
|---|---|---|
| Analyse des données | Commente des indicateurs **déjà calculés**, priorise des anomalies détectées par des règles déterministes | Chaque chiffre cité doit exister dans le contexte transmis ; contrôle automatique après réponse |
| Anomalies potentielles | Explique et classe les résultats des tests automatiques (doublons, écritures hors période, montants ronds, distribution des premiers chiffres, saisies inhabituelles) | Les tests sont calculés par du code Python ; l'IA ne « détecte » pas seule |
| Programmes de travail | Propose des procédures tirées de la bibliothèque de la méthodologie au regard des risques évalués | Proposition marquée « suggestion IA » ; l'auditeur doit l'accepter |
| Analyse des risques | Suggère des risques à partir des données et de la cartographie | Cotation finale par l'auditeur |
| Rédaction | Projets de constats, de synthèses et de lettres, à partir des constats validés et des données | Texte marqué brouillon IA ; jamais d'opinion d'audit ; sources citées |

**Interdits absolus** :
- l'IA ne crée pas d'élément probant ;
- elle ne signe pas, ne valide pas et ne conclut pas une procédure ;
- elle ne modifie pas un chiffre ;
- elle n'attribue pas un travail à une personne qui ne l'a pas fait.

Ces interdits sont imposés **par la base de données et l'API**, pas seulement par le prompt (voir `CDC_TECHNIQUE.md` § 5).

**Livré au lot 10** (détail dans `IA.md`) : assistant financier et commentaires d'analyse relus, avec contrôle des chiffres ; suggestions de risques, de procédures (programmes types), de projets de constats et de synthèses et d'explications des analyses du grand livre, acceptées ou rejetées par l'équipe ; activation par l'organisation, usage par usage. La détection d'anomalies reste faite par les analyses déterministes du lot 3.

### 2.9 Reporting et génération documentaire
- Formats : PDF, Excel (formules conservées), Word.
- Modèles par type de document : états financiers, analyse, rapport de gestion, synthèse d'audit, lettre de recommandations, rapport d'audit interne, rapport sur le contrôle interne.
- Un rapport ne s'appuie que sur des données validées : balance validée, feuilles approuvées, constats validés.
- Chaque rapport émis est stocké avec son empreinte et la liste des données utilisées.
- **Livré au lot 11** (détail dans `REPORTING.md`) : rapport financier, suivi budgétaire, rapports du contrôle interne, rapport d'audit interne émis et synthèse des anomalies, en PDF, Excel et Word, avec modèles versionnés. Les fichiers Excel contiennent les valeurs (nombres), pas de formules. La lettre de recommandations, le rapport de gestion et le dossier complet de mission restent à faire.

### 2.10 SaaS
Abonnements et paiements, quotas par offre, connecteurs (Odoo, Sage : uniquement sur appel réel réussi), administration de la plateforme, supervision.

## 3. Exigences transverses
- **Aucune donnée simulée en production, aucun bouton sans action, aucune page vide présentée comme terminée.** Les données de démonstration sont isolées et signalées.
- **Aucune norme inventée** : référentiels comptables, cadres de contrôle interne, méthodologies d'audit et modèles de rapport sont des **données chargées, sourcées et validées**.
- **Traçabilité** : qui a fait quoi, quand, sur quelle version. Le journal est en ajout seul.
- **Confidentialité** : cloisonnement par organisation, par entité et, pour l'audit, par mission. Un membre du cabinet ne voit une mission que s'il y est affecté.
