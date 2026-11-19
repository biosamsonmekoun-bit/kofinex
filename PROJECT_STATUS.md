# KOFINEX — État du projet

*Mis à jour le 18 novembre 2026 (évolution du contrôle de gestion : pilotage).*

## Synthèse
| Lot | État |
|---|---|
| 1 Fondations | livré |
| 2 Design system | **identité visuelle et thèmes livrés** (voir `docs/DESIGN_SYSTEM.md`) ; tableaux triables et paginés livrés avec le lot 9 ; autres composants propres aux modules à créer avec ces modules |
| 3 Comptabilité et import | livré ; référentiels transcrits, **en attente de validation par un expert** |
| 3B Comptabilité générale native | **étapes A et B livrées** (voir `docs/COMPTABILITE_NATIVE.md`) : journaux, plan comptable de l'entreprise, tiers, saisie, circuit de validation, extournes, grand livre et balances natifs, lettrage ; étapes C (auxiliaires et génération), D (inventaire, clôture) et E (états natifs, intégrations) à faire ; **FEC DGI Bénin livré** (voir `docs/FEC_BENIN.md`) |
| 4 Analyse financière | livré |
| 5 Contrôle de gestion | **livré** (voir `docs/CONTROLE_GESTION.md`) ; **évolution « pilotage » livrée** (§ 11) : tableaux de bord financier, budgétaire, trésorerie, masse salariale, analyse, alimentés par les écritures validées |
| 6 Socle commun d'audit | **livré** (voir `docs/AUDIT_SOCLE.md`) ; constats, plans d'action, demandes de documents, temps, échantillonnage reportés |
| 7 Audit financier et comptable | **livré** (voir `docs/AUDIT_FINANCIER.md`) ; limite supérieure d'anomalie et dossier de synthèse reportés |
| 8 Audit interne | **livré** (voir `docs/AUDIT_INTERNE.md`) ; tableau de bord du comité reporté (lot 11) |
| 9 Contrôle interne | **livré** (voir `docs/CONTROLE_INTERNE.md`) ; aucun contenu de référentiel chargé (documents sources à fournir) ; exports PDF, Excel et Word au lot 11 |
| 10 Intelligence artificielle | **livré** (voir `docs/IA.md`) ; désactivé tant que le fournisseur, la clé et le modèle ne sont pas configurés et que l'organisation n'a pas activé les usages |
| 11 Reporting et génération documentaire | **livré** (voir `docs/REPORTING.md`) ; sans logo, graphiques ni formules Excel ; lettre de recommandations et rapport de gestion non faits |
| Interface (maquette de référence) | **livrée** (voir `docs/INTERFACE.md`) : page d'accueil publique, démonstration fictive, tableau de bord sur données réelles, nouvelle navigation ; non vérifiée dans un navigateur |
| 12 SaaS et mise en production | non commencé |

## Ce qui existe
- **Base** : 100 tables (migrations 0001 à 0015), RLS partout, 5 buckets privés ; acteur IA bloqué sur toutes les tables métier.
- **API** : `me`, `organizations`, `companies`, `fiscal_years`, `frameworks`, `imports`, `analysis`, `management`, `engagements` (méthodologies, missions, dossier), `financial_audit`, `internal_audit`, `ledger`, `internal_control`, `ai`, `reporting`, `dashboard`, `accounting` (comptabilité native), `fec` (FEC DGI Bénin), `steering` (pilotage).
- **Moteurs** :
  - `engines/importing` : lecture, OCR, détection, balance, contrôles ;
  - `engines/accounting` : profils, chargeur de référentiels, construction des états ;
  - `engines/financial` : expressions, bibliothèque KOFINEX-STD-1, calcul, pluriannuel ;
  - `engines/management` : réalisé et écarts, coûts complets, coût-volume-profit, coûts préétablis, projections ;
  - `engines/audit` : validation des méthodologies, règles de circuit, contrôle des éléments probants, audit financier, audit interne, contrôle interne (`control`, `ic_templates`) ;
  - `engines/ai` : contextes calculés, consignes versionnées, contrôle des chiffres, lecture des réponses, fournisseurs Anthropic et OpenAI ;
  - `engines/reporting` : document neutre, constructeurs des cinq documents, rendus PDF, Excel et Word, empreintes.
- **Référentiels** (`referentiels/`) :
  - SYSCOHADA révisé : validé sur le cas pratique du manuel et sur les balances de l'utilisateur ;
  - SYSCEBNL (associations) : couverture du plan vérifiée, pas de cas chiffré.
- **Tests** :
  - 227 tests unitaires des moteurs (plus 1 test d'appel HTTP exécuté en CI) ;
  - tests SQL : RLS 39, Storage 12, référentiels et imports 20, moteur financier 16, contrôle de gestion 17, socle d'audit 46, audit financier 57, audit interne 59, grand livre 19, contrôle interne 94, IA 60, reporting 41, comptabilité native 68, seuils du pilotage 8, FEC Bénin 33 ;
  - tests d'intégration API (parcours complet) : à exécuter sur une base de test.

## Décisions en attente (utilisateur ou expert)
1. **Référentiels** : relire les points marqués « [À VALIDER] » (`referentiels/*/RAPPORT.md`). Pour le SYSCEBNL, rattacher les comptes 702, 7054 et 7055.
2. **Ordre des lots** : lot 12 (SaaS et mise en production) ensuite (voir `docs/ROADMAP.md`).
5. **IA** : choisir le fournisseur (Anthropic ou OpenAI) et le modèle, fournir la clé (`AI_PROVIDER`, `AI_MODEL`, `AI_API_KEY`) ; chaque organisation décide ensuite d'activer les usages, en acceptant la transmission de ses données calculées au fournisseur.
3. **Méthodologie d'audit** : l'outil de chargement existe (lot 6) et KOFINEX ne livre aucun contenu. Il faut décider si une méthodologie de départ est fournie, et laquelle : elle doit être sourcée et validée.
4. **Référentiels de contrôle interne** : aucun n'est chargé. Fournir les documents sources (COSO, IIA, IFACI, OHADA, méthodologie interne, avec les droits d'usage) et les échelles de l'organisation (niveau de maîtrise, gravité des déficiences, cotation des risques) ; liste dans `docs/CONTROLE_INTERNE.md` §1.

## Lot 2 — ce qui a été fait
- Tokens centralisés (clair / sombre) aux couleurs officielles. Aucune couleur codée en dur dans les composants ni dans les pages.
- Thème clair / sombre / automatique : choix mémorisé, sans flash au chargement, changement immédiat.
- Logo et signature KOFINEX. Sidebar bleu nuit avec état actif (fond bleu royal, filet or), sélecteur de thème et accès au profil. Barre supérieure sur ordinateur (organisation courante, utilisateur). Menu mobile.
- Composants harmonisés : boutons, cartes, champs, tableaux (chiffres tabulaires), modales, onglets, badges, alertes (nouveau type « avertissement »), états vides et de chargement. Nouveau composant `KpiCard`, utilisé en tête de la page d'analyse (résultat net, CAF, FR, TN).
- Graphique pluriannuel sur les tokens de graphique.
- Accessibilité : focus visible, rôles ARIA (onglets, sélecteur de thème, page active), contrastes AA visés, réduction des animations respectée.
- **Non vérifié dans un navigateur ici** : les dépendances du frontend ne peuvent pas être installées dans cet environnement (réseau fermé). La syntaxe des fichiers modifiés a été vérifiée avec TypeScript. Il reste à lancer `npm run typecheck` et `npm run build`, puis à faire une revue visuelle des deux thèmes.

## Lot 5 — ce qui a été fait
- Migration 0006 :
  - budgets avec scénario (budget ou prévision), hypothèses, circuit de validation et gel ;
  - séparation auteur / approbateur contrôlée en base ;
  - saisies analytiques figées une fois l'exercice clôturé ;
  - nouvelle table `costing_models`, figée à la validation.
- Moteur `engines/management` : réalisé et écarts, prévision par hypothèses, coûts complets avec prestations réciproques résolues exactement, coût-volume-profit (seuil, point mort, marge et indice de sécurité, levier), écarts prix/quantité, projections (tendance linéaire, TCAM).
- API `api/v1/management.py` et interface `/companies/{id}/gestion` (tableau de bord, budgets, centres et saisies, coûts / marges / seuils, projections).
- **Vérifié ici** : 12 tests de cas de référence calculés à la main et 17 tests SQL.
- **Non exécuté ici** : l'API et l'interface ne peuvent pas tourner dans cet environnement (FastAPI et les dépendances du frontend ne sont pas installables). Le test d'intégration `test_management_api.py` est prêt pour la CI. La syntaxe TypeScript a été vérifiée. Restent à faire : `npm run typecheck`, `npm run build`, la CI et une revue visuelle.

## Lot 6 — ce qui a été fait
- Migration 0007 : 15 tables, bucket `audit-evidence`, fonctions `authz.engagement_role`, `authz.has_engagement_role`, `authz.can_read_dossier`, `public.confirm_independence`.
- Règles imposées **en base** : accès au dossier après déclaration d'indépendance ; signature par l'utilisateur connecté uniquement ; séparation préparateur / réviseur / approbateur ; empreinte du contenu sur chaque signature et révocation automatique en cas de modification ; mission figée une fois émise ; réouverture par l'associé avec motif ; conditions d'émission (feuilles approuvées, notes closes, revue qualité, approbation de l'associé).
- Méthodologies chargées par CSV, versionnées, figées à la publication ; aucun contenu normatif livré.
- API `api/v1/engagements.py` ; interface : `/methodologies`, `/organizations/{id}/missions`, `/missions/{id}` (supervision, équipe, risques, programme, feuilles, éléments probants, notes) et `/missions/{id}/feuilles/{id}`.
- **Vérifié ici** : 46 tests SQL et 5 tests unitaires.
- **Non exécuté ici** : l'API et l'interface (dépendances non installables). `test_engagements_api.py` est prêt pour la CI ; la syntaxe TypeScript a été vérifiée. Restent : `npm run typecheck`, `npm run build`, la CI et une revue visuelle.

## Lot 7 — ce qui a été fait
- Migration 0008 : 11 tables `fa_*`, lecture seule des balances de l'entité auditée pour l'équipe de mission (`authz.audits_company`), conditions d'émission propres à l'audit financier.
- **Règles imposées en base** :
  - montants des seuils égaux au produit exact des pourcentages ; seuils approuvés par le manager ou l'associé, puis figés ;
  - soldes de la revue des comptes conformes aux balances validées N et N-1 ; variation au-dessus du seuil expliquée avant conclusion ;
  - tirage et projection réservés au moteur ; population figée et paramètres immuables après le tirage ;
  - circularisations : contenu figé après envoi, écart rapproché ou procédures alternatives exigées avant clôture ;
  - écritures d'ajustement équilibrées ; décision sur les anomalies réservée à l'encadrement, puis écriture figée ;
  - conclusion sur les anomalies non corrigées exigée avant l'émission.
- Moteur : seuils, revue analytique, rattachement aux cycles, sélections (aléatoire, systématique, unités monétaires, éléments clés, raisonnée), projection ponctuelle, lecture des populations depuis un fichier, balance ajustée et effets sur les états (même moteur que les états publiés).
- Aucun pourcentage, aucune taille d'échantillon et aucun facteur de confiance n'est livré.
- API `api/v1/financial_audit.py` ; interface : onglet « Audit financier » de la mission (seuils, comptes et cycles, échantillons et tests, circularisations, anomalies et ajustements, conditions d'émission).
- Les tests du lot 6 utilisent désormais une mission d'audit interne : une mission d'audit légal ne peut plus être émise sans les travaux du lot 7.
- **Vérifié ici** : 57 tests SQL, 8 tests unitaires, non-régression des 6 autres séries SQL et des 132 tests unitaires.
- **Non exécuté ici** : l'API et l'interface. `test_financial_audit_api.py` est prêt pour la CI ; la syntaxe TypeScript a été vérifiée. Restent : `npm run typecheck`, `npm run build`, la CI et une revue visuelle.

## Lot 8 — ce qui a été fait
- Migration 0009 : 9 tables, type de méthodologie `finding_scale`, accès de l'audité, condition d'émission propre à l'audit interne.
- **Règles imposées en base** :
  - plan approuvé figé ; ajouts et modifications motivés, historisés ; report et annulation motivés ;
  - constats validés par une autre personne que l'auteur, puis figés ; communication par l'encadrement ;
  - réponse de l'audité à son nom ;
  - statut des plans d'action modifié uniquement par une mise à jour de suivi ; historique non modifiable ; vérification réservée à l'encadrement ;
  - rapport émis par l'associé, figé, avec une empreinte calculée par la base ;
  - mission d'audit interne émise seulement après son rapport.
- Moteur : carte des risques sur la grille de la méthodologie, synthèse du plan, ordre des constats par gravité, retards du suivi, export Word du rapport.
- API `api/v1/internal_audit.py` ; interface :
  - plan d'audit (liste et détail) ;
  - cartographie (carte, processus, registre des risques et historique des cotations) ;
  - onglets « Constats et recommandations » et « Rapport » de la mission, également ouverts à l'audité ;
  - suivi transversal des recommandations.
- Comportements modifiés :
  - une mission émise laisse désormais suivre et vérifier les plans d'action ;
  - les tests du lot 6 utilisent une mission d'évaluation du contrôle interne, car une mission d'audit interne ne peut plus être émise sans rapport.
- **Vérifié ici** : 59 tests SQL, 5 tests unitaires (dont l'export Word), non-régression des 7 autres séries SQL et des 137 tests unitaires.
- **Non exécuté ici** : l'API et l'interface. `test_internal_audit_api.py` est prêt pour la CI ; la syntaxe TypeScript a été vérifiée. Restent : `npm run typecheck`, `npm run build`, la CI et une revue visuelle.

## Complément du lot 3 (grand livre) — ce qui a été fait
- Migration 0010 : table `ledger_lines`, type d'import `ledger`, grand livre actif de l'exercice, populations d'audit « grand livre ».
- **Règles imposées en base** :
  - validation refusée en cas de ligne en erreur, de déséquilibre global ou d'une écriture, ou de date hors de l'exercice ;
  - lignes figées après la validation ;
  - un grand livre ne peut pas devenir la balance de l'exercice, ni l'inverse ;
  - chaque élément d'une population d'audit reprend exactement le montant de sa ligne ;
  - lecture par l'équipe de mission sur l'entité auditée.
- Moteur `engines/importing/ledger.py` : reconnaissance du FEC et des intitulés courants, lecture stricte, contrôles, rapprochement compte par compte avec la balance, outils d'analyse.
- Service et API `services/ledger.py`, `api/v1/ledger.py` : import, consultation avec solde progressif, écriture, comptes rapprochés, centralisation, analyses de données, export CSV ; mêmes vues pour les missions (`/engagements/{id}/ledger`).
- Raccordements : réalisé mensuel du contrôle de gestion, populations « grand livre » de l'audit financier.
- Interface : page « Grand livre » de l'entreprise (imports, consultation, comptes, centralisation, analyses), assistant d'import, onglet « Grand livre » des missions, source « Écritures du grand livre » des populations.
- Les imports de balance ignorent désormais les imports de grand livre (listes, modèles d'association).
- **Vérifié ici** :
  - 19 tests SQL et 7 tests unitaires ; non-régression des 8 autres séries SQL et des 144 tests unitaires ;
  - les requêtes d'exploitation exécutées sur un jeu d'écritures (solde progressif, à-nouveaux, centralisation, doublons, week-ends, montants ronds) ;
  - la lecture du fichier de test par le vrai lecteur CSV.
- **Non exécuté ici** : l'API et l'interface. `test_ledger_api.py` est prêt pour la CI ; la syntaxe TypeScript a été vérifiée.

## Lot 9 — ce qui a été fait
- Migration 0011 : 13 tables (`framework_mappings`, `ic_domains`, `ic_members`, `control_objectives`, `controls`, `control_risks`, `ic_framework_links`, `control_executions`, `control_tests`, `control_test_items`, `ic_assessments`, `control_test_reliances`, `ic_history`), bucket `ic-evidence`.
- Tables existantes complétées, sans doublon : métadonnées des référentiels sur `methodology_versions`, nouveaux types d'éléments, domaine sur `processes`, attributs de risque sur `risks`, nature `ic_deficiency` et clôture sur `findings`, nouveaux objets des éléments probants et des notes de revue.
- **Règles imposées en base** :
  - référentiel publié figé ; correspondances déclarées et motivées ; rattachements à des éléments publiés uniquement ;
  - héritage du domaine (sous-processus, risque, déficience) ; cotations sur la grille versionnée choisie ;
  - contrôle avec responsable ; contrôle existant caractérisé ; version et historique à chaque modification ;
  - exécution au nom de l'utilisateur, supervisée par une autre personne, puis figée ;
  - conclusion « efficace » impossible sans critères positifs, éléments testés, période, preuve et exceptions dans la tolérance ; « non applicable » justifié ;
  - préparateur et réviseur distincts ; test préparé ou revu figé ; réouverture motivée ;
  - synthèse IC-SYNTH-1 calculée et figée à la soumission d'une évaluation ; approbation refusée si les résultats ont changé ;
  - déficience rattachée à un contrôle, cotée sur l'échelle de la méthodologie, close après vérification de tous ses plans ;
  - prise en compte par l'audit financier limitée aux tests revus concluants dont la période recouvre la période auditée, avec instantané figé.
- Moteur `engines/audit/control.py` (synthèse, cohérence des tests, matrice et couverture, points à examiner, cycle des déficiences, tableau de bord, rapports) et modèles `ic_templates.py` (8 cycles comptables, 9 domaines organisationnels, intitulés uniquement).
- Service et API `services/internal_control.py`, `api/v1/internal_control.py` (`/companies/{id}/ic/…`, `/engagements/{id}/ic/…`) ; déficiences par les constats du lot 8.
- Interface :
  - entrée « Contrôle interne » de la navigation ;
  - 14 espaces par entité (tableau de bord, référentiels, domaines, risques, contrôles et fiche, matrice, programmes, tests et évaluations, déficiences, recommandations, remédiation, suivi, rapports, rôles) ;
  - onglet « Contrôle interne » des missions (programme, fiche de test, évaluations ; prise en compte pour l'audit financier) ;
  - métadonnées des référentiels dans le formulaire des méthodologies.
- **Vérifié ici** :
  - 94 tests SQL et 12 tests unitaires ; non-régression des 9 autres séries SQL et des 167 tests unitaires ; ruff sans erreur ;
  - RLS active, avec politiques, sur les 13 nouvelles tables ;
  - TypeScript vérifié avec résolution des modules du projet (bibliothèques externes remplacées par des déclarations minimales) ;
  - chaque appel API des nouveaux écrans rapproché d'une route existante.
- **Non exécuté ici** : l'API et l'interface. `test_internal_control_api.py` (parcours complet) est prêt pour la CI. Restent : `npm run typecheck`, `npm run build`, la CI et une revue visuelle.

## Lot 10 — ce qui a été fait
- Migration 0012 : tables `ai_settings` et `ai_suggestions` ; tables du lot 1 complétées (`ai_conversations.purpose`, `ai_messages.prompt_version`, `ai_reports.review_note`) ; provenance (`ai_suggestion_id`, `findings.origin`) sur les risques de mission, procédures et constats.
- **Règles imposées en base** :
  - acteur IA de session : aucune écriture possible dans les 83 tables métier ni dans le stockage ; déclencheur exécuté avant tous les autres ;
  - réponses, commentaires et suggestions enregistrés uniquement par le traitement du modèle, avec contexte, contrôle des chiffres et modèle, puis jamais modifiés ;
  - décisions (acceptation, rejet motivé, relecture) humaines, uniques, au nom de l'utilisateur ;
  - objet issu d'une suggestion : accepté par celui qui le crée, de même nature, une seule fois, en brouillon, sans cotation ni attribution ; provenance non modifiable ;
  - IA désactivée par défaut, activée usage par usage avec un accord motivé.
- Moteur `engines/ai` : contextes à partir des sorties des moteurs existants, règle de contrôle des chiffres KOFINEX-NUM-1, consignes `KOFINEX-AI-1`, lecture stricte des suggestions, appels réels Anthropic et OpenAI (aucune réponse simulée sans configuration).
- Service et API `services/ai.py`, `api/v1/ai.py` : statut, réglages, assistant financier, commentaires d'analyse, suggestions d'audit (risques, procédures, projets de constats et de synthèses, explication des analyses du grand livre).
- Interface : page « Assistant IA » de l'entreprise (conversations, commentaires relus), onglet « Assistant IA » des missions, réglages IA de l'organisation, mention « Suggestion IA » sur les objets créés.
- **Vérifié ici** :
  - 60 tests SQL et 13 tests unitaires ; non-régression des 10 autres séries SQL et des 167 autres tests unitaires ; ruff sans erreur ;
  - déclencheur `0_not_ai` présent sur toutes les tables publiques sauf les 5 tables IA et le journal ;
  - TypeScript vérifié avec résolution des modules du projet ; appels API des nouveaux écrans rapprochés des routes.
- **Non exécuté ici** :
  - l'API, l'interface et tout appel réel à un fournisseur : réseau fermé, pas de clé ;
  - `test_ai_api.py` (fournisseur remplacé par un double de test) et le test d'appel HTTP (`httpx`) sont prêts pour la CI ;
  - restent `npm run typecheck`, `npm run build`, la CI et un essai avec une vraie clé.

## Lot 11 — ce qui a été fait
- Migration 0013 :
  - `generated_reports` généralisée : documents d'entreprise ou de mission, type et sous-type, empreinte des données, contenu structuré, sources, paramètres, modèle et version, brouillons IA signalés ;
  - `report_templates` complétée : type, version, statut, textes, couleur vérifiée.
- **Règles imposées en base** :
  - document figé (ni modification ni suppression), généré au nom de l'utilisateur, échec motivé ;
  - données validées selon le type : analyse terminée, budget approuvé, rapport d'audit émis avec son empreinte, seuils approuvés ;
  - commentaires IA rejetés exclus, brouillons IA obligatoirement signalés ;
  - modèle publié uniquement, du même type et de l'organisation ; modèle publié figé, conservé, archivable ;
  - lecture selon l'entreprise, le contrôle interne ou le dossier de mission ; acteur IA exclu.
- Moteur `engines/reporting` :
  - document neutre ;
  - constructeurs : rapport financier, suivi budgétaire, rapports du contrôle interne, rapport d'audit interne émis, synthèse des anomalies ;
  - rendus Word, Excel (vrais nombres) et PDF, déterministes, avec empreinte en pied de page ;
  - mise en forme française.
- Service et API `services/reporting.py`, `api/v1/reporting.py` : génération, liste, document figé, téléchargement signé, modèles (création, brouillon, publication, nouvelle version, archivage). `reportlab` passe en dépendance principale.
- Interface :
  - page « Rapports » de l'entreprise ;
  - onglet « Documents » des missions ;
  - exports PDF, Excel et Word des rapports du contrôle interne ;
  - page « Modèles de rapports » de l'organisation (navigation principale).
- **Vérifié ici** :
  - 41 tests SQL et 16 tests unitaires, dont la relecture des trois formats et le déterminisme des rendus ; non-régression des 11 autres séries SQL et des 180 autres tests unitaires ; ruff sans erreur ;
  - aucune route en double (les routes du lot 8 `/engagements/{id}/reports` sont conservées) ;
  - TypeScript vérifié avec résolution des modules du projet ;
  - rendu PDF contrôlé visuellement.
- **Non exécuté ici** : l'API et l'interface. `test_reporting_api.py` est prêt pour la CI. Restent `npm run typecheck`, `npm run build`, la CI et une revue visuelle des documents Word et Excel.

## Prochaine étape
**Lot 12 — SaaS et mise en production** : abonnements et paiements, quotas par module, connecteurs (Odoo, Sage) sur appels réels, administration, supervision, sauvegardes, durcissement et recette.

## Points techniques connus
- Import PDF : les colonnes de montants alignées à droite peuvent être mal attribuées sur certaines mises en page. Les contrôles d'équilibre bloquent alors l'import ; amélioration à prévoir.

## Interface d'après la maquette de référence — ce qui a été fait
- **Page d'accueil publique** (`/`) : navigation, hero et illustration (le vrai tableau de bord réduit, alimenté par des données fictives), bandeau d'avantages, fonctionnalités, KOFINEX AI, publics, bandeau final, tarifs et à propos.
- **Démonstration publique** (`/demonstration`) : données fictives isolées dans `lib/demo-dashboard.ts`, bannière permanente.
- **Tableau de bord** (`/tableau-de-bord`, page d'arrivée après connexion) : quatre indicateurs avec icônes, barres groupées produits / charges, deux anneaux, principaux indicateurs, alertes, activités ; états vides explicites.
- **Backend** : moteur `engines/financial/dashboard.py` (regroupements selon le plan publié, parts, variations, série mensuelle), service `services/dashboard.py`, route `GET /companies/{cid}/fiscal-years/{fy}/dashboard`. Aucune migration.
- **Coquille** : barre latérale dans l'ordre de la maquette (modules absents signalés « non disponible »), sélecteurs entreprise / exercice / période reliés aux données, cloche, menu du compte.
- **Design system** : nouvel emblème, tokens `violet` et `chart-blue/orange/green/violet`.
- **Vérifié ici** : 5 tests unitaires du tableau de bord ; non-régression des 196 autres tests unitaires ; ruff sans erreur ; 328 routes sans doublon ; TypeScript vérifié avec résolution des modules du projet (bibliothèques externes remplacées par des déclarations minimales) ; appels API des nouveaux écrans rapprochés des routes.
- **Non exécuté ici** : l'API, l'interface et le rendu visuel (dépendances non installables, réseau fermé). `test_dashboard_api.py` est prêt pour la CI. Restent : `npm run typecheck`, `npm run build`, la CI et **une revue visuelle comparée à la maquette** (clair et sombre, ordinateur et mobile).
- **Affichés mais non réalisés** (texte de la maquette, lot 12) : essai de 14 jours, paiement FedaPay, grille tarifaire ; modules Achats, Ventes, Trésorerie, Stocks, Immobilisations, Paie, Fiscalité.

## Lot 3B — étapes A et B — ce qui a été fait
- **Migration 0014** : 10 tables, distinctes des imports (`ledger_lines` et `trial_balance_entries` inchangés) :
  - paramètres comptables, plan comptable de l'entreprise (rattaché au référentiel publié), tiers ;
  - journaux et séquences ;
  - écritures et lignes, pièces jointes, historique du circuit ;
  - lettrages.

  Le type de document `accounting_voucher` est ajouté (élargissement de la contrainte, sans retrait).
- **Règles imposées en base** :
  - **Saisie** :
    - écriture créée en brouillon ;
    - lignes modifiables en brouillon seulement ;
    - totaux tenus par la base ;
    - soumission refusée si l'écriture est déséquilibrée, a moins de deux lignes, un compte non ouvert ou inactif, ou un tiers absent ou incompatible sur un compte collectif ;
    - date hors exercice et journal inactif refusés.
  - **Validation** :
    - revue optionnelle ;
    - séparation préparateur / validateur, active par défaut ;
    - validation réservée aux comptables et administrateurs ;
    - numéro attribué à la validation, sans trou ni doublon ;
    - écriture validée immuable ;
    - suppression limitée aux brouillons et rejets, par leur auteur ;
    - rejet motivé.
  - **Extourne** : une seule par écriture, miroir exact, dans le même exercice ; l'écriture d'origine passe à « extournée » à sa validation.
  - **Origine** : une écriture « générée » est réservée au moteur (étape C) ; une opération source ne peut être comptabilisée qu'une fois.
  - **Lettrage** : complet, sur lignes validées, même compte et même tiers, contrôle différé.
  - **Exercice et droits** : exercice clôturé figé ; RLS (lecture par l'entité et les équipes de mission, écriture par les comptables) ; déclencheur `0_not_ai` sur les 10 tables.
- **Moteurs** :
  - `engines/accounting/entries.py` : montants Decimal stricts, contrôles, extourne, codes et contrôle de lettrage ;
  - `engines/accounting/native_ledger.py` : grand livre avec solde progressif ; balances générale, auxiliaire, avant / après inventaire et comparative ; contrôles d'équilibre.
- **Services et API** : `services/accounting_setup.py`, `services/journal_entries.py`, `services/native_ledger.py`, `api/v1/accounting.py` (33 routes sous `/companies/{id}/accounting`). Nouvelles permissions : `accounting.setup`, `accounting.settings`, `entry.write`, `entry.validate`.
- **Interface** (`/companies/{id}/comptabilite/…`) :
  - écritures (à valider, brouillons, rejetées, historique) ;
  - nouvelle écriture et fiche d'écriture (circuit, extourne et correction, pièces, historique) ;
  - grand livre, balance, lettrage ;
  - journaux, plan comptable, tiers, paramètres.

  La rubrique « Comptabilité » de la navigation renvoie à ces écrans ; le bouton « Comptabilité générale » est ajouté sur la fiche de l'entreprise.
- **Vérifié ici** :
  - 68 tests SQL ; non-régression des 12 autres séries SQL (480 contrôles) ;
  - 13 nouveaux tests unitaires, 214 au total, réussis (1 ignoré : il nécessite `httpx`) ;
  - ruff sans erreur ; 361 routes, sans doublon ;
  - RLS et `0_not_ai` présents sur les 10 nouvelles tables ;
  - TypeScript vérifié avec résolution des modules du projet ; appels API des nouveaux écrans rapprochés des routes.
- **Non exécuté ici** : l'API, l'interface et le test d'intégration `test_native_accounting_api.py` (FastAPI, SQLAlchemy et les dépendances du frontend ne sont pas installés). Restent : la CI, `npm run typecheck`, `npm run build` et une revue visuelle.
- **Décisions à valider** : voir `docs/COMPTABILITE_NATIVE.md` §7 (numérotation à la validation, extourne dans l'exercice, lettrage complet, lettrage après clôture, formats des pièces, confidentialité de la paie).
- **Non commencé** : étapes C, D et E du lot 3B. Les documents `OPERATIONS_AUXILIAIRES.md`, `TRAVAUX_INVENTAIRE.md` et `CLOTURE_COMPTABLE.md` seront créés avec ces étapes, pour ne décrire que ce qui existe.

## Contrôle de gestion — évolution « pilotage » — ce qui a été fait
- **Couche de lecture normalisée** : écritures natives validées, sinon grand livre importé, sinon balance. Les sources ne sont jamais additionnées ; la source retenue est affichée.
- **Classification des comptes par le référentiel publié** (concepts, lignes, correspondances), sans numéro de compte codé en dur. Elle est vérifiée sur le référentiel SYSCOHADA réel.
- **Tableau de bord financier** :
  - indicateurs : marges AO / HAO / totale, charges et produits AO, indicateurs KOFINEX-STD-1 de la période ;
  - 6 Top 10 ; évolutions mensuelles ;
  - périodes mensuelle, cumulée, annuelle ou libre ; N / N-1 sur période équivalente, exercice décalé compris ;
  - fiabilité et résultats provisoires ; détail jusqu'aux écritures.
- **Tableau de bord budgétaire** :
  - budget initial, révisé et approuvé ; réalisé de la source retenue ; écarts et taux ;
  - prévision à terminaison (deux méthodes, présentées comme extrapolations) ;
  - tableau mensuel ou cumulé ; alertes à seuils paramétrables ; Top 10.
- **Trésorerie, masse salariale, analyse** :
  - trésorerie : transferts internes exclus, contrôle du solde ;
  - masse salariale agrégée, détail des écritures protégé par `payroll.detail` ;
  - points d'attention factuels.
- **Gestion budgétaire** : import Excel / CSV des lignes d'un brouillon, avec contrôle préalable.
- **Correctif du lot 5** : les natures `expense` / `income` du plan de comptes sont traduites en `charge` / `produit`. Sans ce correctif, le suivi budgétaire refusait toutes les lignes sur des données réelles.
- **Migration 0015** : `management_alert_settings` (RLS, journal d'audit, `0_not_ai`).
- **Vérifié ici** :
  - 16 nouveaux tests unitaires, 230 au total, réussis (1 ignoré) ;
  - les 14 séries SQL, réussies ;
  - ruff sans erreur ; 371 routes, sans doublon ;
  - TypeScript vérifié avec résolution des modules du projet.
- **Non exécuté ici** : `test_steering_api.py` (cas 2, 3 et 6), l'API et l'interface. Restent la CI, `npm run typecheck`, `npm run build` et une revue visuelle.
- **Modèle Excel de référence** (reçu ensuite) : examiné et rapproché sur son grand livre. Les charges AO de juillet 2014 sont identiques au centime près. Les écarts sont expliqués : produits en net, extournes de factures à établir déduites ; impôt (IMF) hors HAO selon le référentiel. Deux ajustements : la carte « Impôt et participation », et la base « montants facturés » pour le Top 10 des tiers. Voir `docs/CONTROLE_GESTION.md` § 11.15.
- **Vérifié après ces ajustements** : 230 tests unitaires réussis (1 ignoré) ; les 14 séries SQL réussies, dont 8 contrôles pour la migration 0015 ; ruff sans erreur ; 371 routes, sans doublon ; TypeScript vérifié avec résolution des modules du projet.
- **Finalisation (diagnostic et points restants)** — voir `docs/CONTROLE_GESTION.md` § 11.16 :
  - migration 0015 contrôlée : chaîne linéaire 0001 → 0015, une tête, aucune migration antérieure modifiée ;
  - cas de test 4 traité : import complémentaire du grand livre (doublons écartés, écriture modifiée refusée, garde à la validation) ; fichier correctif = remplacement ; aucune table créée ;
  - trésorerie : banque / caisse distinguées par les journaux de l'entité, pour toutes les sources ;
  - cumul budgétaire et évolution mensuelle calculés côté serveur en décimal ;
  - revue de l'interface des quatre espaces (période incomplète, composant `Select`, accessibilité clavier) ; option de mode et synthèse dans l'import du grand livre ;
  - test instable corrigé : rendus Excel / Word datés de la génération du rapport ;
  - tests d'intégration ajoutés : cas 5, import de budget, seuils, cas 4 (compilés ; à exécuter en CI).
- **Vérifié ici après finalisation** : 238 tests unitaires réussis (1 ignoré) ; 14 séries SQL sur 14 ; ruff sans erreur ; 376 routes backend sans doublon, appels frontend tous rapprochés d'une route ; TypeScript sans erreur (déclarations de substitution des dépendances).
- **Non exécuté ici** : `npm run typecheck`, `npm run build` (pas de `node_modules`, installations bloquées) et les tests d'intégration API (FastAPI / SQLAlchemy absents).
- **Restant et à valider** : voir `docs/CONTROLE_GESTION.md` § 11.14 et § 11.15 :
  - cas de test 1 (module Achats, lot suivant) ;
  - engagements ; axes département et projet ;
  - seuils par défaut ;
  - produits en net ou en brut ;
  - import d'un grand livre où le code du tiers remplace le compte.

## FEC DGI Bénin (comptabilité, 19 novembre 2026) — ce qui a été fait
- **Texte appliqué** : arrêté n° 1085/MEF/CAB/SGM/DGI/DLC/159SGG20 du 23 avril 2020 (copie signée fournie et lue). Détail des règles et des points ouverts : `docs/FEC_BENIN.md`.
- **Livré** :
  - rubrique « FEC » du module Comptabilité : tableau de bord, paramètres, contrôle de conformité, rapport des anomalies (avec lien vers l'écriture), génération définitive ou de travail, historique, téléchargement du fichier, de la documentation (art. 7) et des anomalies ;
  - fichier plat TXT ou CSV, tabulation, fin d'enregistrement CR LF / LF / CR, sans en-tête ;
  - ASCII ou ISO 8859-15 ;
  - 18 champs de l'art. 5, plus les champs 19 à 21 pour la trésorerie ;
  - nom FEC_IFU_AAAAMMJJ et fractionnement FEC_IFU_AAAAMMJJ_X.
- **Migration 0016** (`fec_exports`, `fec_export_lines`, bucket `fec`) : historique figé, traçabilité ligne → écriture, RLS comptables et administrateurs. Aucune migration antérieure modifiée.
- **Réutilisé** : lecteur des écritures validées `native_ledger.posted` (complété de champs, rien retiré), stockage, journal d'audit, garde anti-IA, rôles existants.
- **Exécuté ici** : 20 tests unitaires du moteur FEC (258 au total, 1 ignoré, sur trois passages) ; 15 suites SQL sur 15, dont celle du FEC (33 contrôles) ; ruff sans erreur ; compilation ; 386 routes sans doublon, appels du frontend rapprochés ; TypeScript sans erreur (déclarations de substitution).
- **Non exécuté ici** : `tests/integration/test_fec_api.py` (FastAPI et SQLAlchemy absents), `npm run typecheck` et `npm run build` (pas de `node_modules`, installations bloquées).
- **Restant à confirmer** (`docs/FEC_BENIN.md` § 6) : second caractère séparateur (absent du texte signé), page de code EBCDIC, portée de la continuité de NumEcriture, reconnaissance des écritures de centralisation et de solde des comptes de gestion, durée de conservation (art. 1096 nouveau-1 du CGI), correspondance avec l'article 541. Tant qu'ils restent ouverts, aucun fichier n'est déclaré « conforme ».
