# KOFINEX — Contrôle interne (lot 9)

Module de conception, de documentation, d'évaluation, de test et d'amélioration du dispositif de contrôle interne d'une entité. Il couvre le dispositif organisationnel (évaluation globale, par domaine, processus, cycle, composante du référentiel ou risque) et le contrôle par domaine et cycle opérationnel (achats, ventes, trésorerie, stocks, immobilisations, paie, fiscal et social, clôture, autres fonctions).

Il **réutilise** le socle d'audit (lot 6 : méthodologies, missions, équipe, programmes, procédures, éléments probants, signatures), le registre des processus et des risques, les constats, recommandations et plans d'action (lot 8), et le moteur de sélection d'échantillons (lot 7). Aucune table parallèle de processus, de risques ou de constats n'a été créée.

## 1. Référentiels : des données, pas du code
- COSO, IIA, IFACI, OHADA ou une méthodologie interne sont des **méthodologies** de type `internal_control`, versionnées (`draft → published → archived`) et figées à la publication.
- Chaque version porte, saisis par l'utilisateur : nom, édition, **catégorie** (`ic_framework` cadre de contrôle interne, `professional_standard` référentiel professionnel d'audit, `legal_requirement` exigence juridique ou comptable, `internal_methodology`), organisme source, date de publication, date d'application, référence et document source, statut. Les quatre référentiels ne sont donc jamais présentés comme des normes équivalentes.
- Éléments chargés par CSV : `ic_component`, `ic_principle`, `ic_requirement`, `ic_criterion` (arborescence par `parent_code`), `control_level_scale` (niveaux de maîtrise), `deficiency_scale` (gravité des déficiences), `risk_scale` (probabilité × impact).
- **Correspondances** entre éléments de référentiels différents (`framework_mappings`) : relation `equivalent`, `partial` ou `related`, motivation obligatoire, jamais déduites ; impossibles à l'intérieur d'une même version ou vers un référentiel non publié.
- Contrôles, risques, objectifs et domaines se rattachent à un ou plusieurs éléments publiés (`ic_framework_links`) : on peut travailler avec un référentiel seul ou en combiner plusieurs.
- **Contenu chargé : aucun.** KOFINEX ne livre ni ne reproduit de contenu normatif. Documents à fournir par l'organisation pour charger chaque référentiel (avec les droits d'usage nécessaires) :
  - COSO : le cadre *Internal Control — Integrated Framework* dans l'édition retenue ;
  - IIA : les *Global Internal Audit Standards* dans l'édition retenue ;
  - IFACI : les guides et publications choisis par l'organisation ;
  - OHADA : l'Acte uniforme relatif au droit comptable et à l'information financière et le référentiel comptable applicable (SYSCOHADA révisé ou SYSCEBNL), pour les exigences d'organisation comptable, de tenue des comptes, de justification et de production de l'information financière ;
  - les échelles (niveau de maîtrise, gravité des déficiences, cotation des risques) de la méthodologie de l'organisation.

## 2. Domaines, processus, objectifs
- `ic_domains` : domaines et cycles propres à chaque entité (`accounting_financial`, `organizational`, `custom`), avec code, responsable, ordre, activation.
- **Modèles** (`engines/audit/ic_templates.py`) : 8 cycles comptables et financiers et 9 domaines organisationnels, avec les sous-processus listés dans la spécification. Ce sont des intitulés d'organisation : aucun risque, contrôle, seuil ou critère n'est fourni. L'utilisateur choisit les modèles utiles ; tout reste modifiable, désactivable et complétable, et rien n'est imposé.
- `processes` (registre existant) reçoit `domain_id` : un sous-processus hérite du domaine de son parent (imposé en base).
- `control_objectives` : objectifs de contrôle par domaine ou processus, avec les assertions concernées.

## 3. Registre des risques
- La table `risks` existante est complétée : domaine (hérité du processus), objectif, catégorie, causes, conséquences, propriétaire, cycle, niveau de maîtrise.
- Les cotations inhérente et résiduelle (probabilité × impact) et le niveau de maîtrise doivent appartenir à la **grille de la version publiée choisie** (`scale_version_id`). Aucun seuil de gravité n'est fixé par la plateforme.
- Chaque modification de cotation est historisée (`risk_rating_history`, avec le niveau de maîtrise).
- Indicateur de couverture calculé : non couvert, non testé, inefficace, partiel, efficace.

## 4. Catalogue des contrôles et matrice
- `controls` : code, intitulé, description, objectif, domaine, processus, objectif de contrôle, responsable (obligatoire), exécutant et superviseur (nom et compte), fréquence, nature (préventif ou détectif), mode (manuel, automatique, semi-automatique), permanent ou périodique, mode d'exécution, procédure de contrôle, justificatifs attendus, critères de réussite, contrôle clé, date de mise en place, statut opérationnel.
- Statut de conception : `existing`, `expected`, `not_formalized`, `absent`. Un contrôle « inefficace » n'est pas un statut saisi : c'est la conclusion de ses tests. Un contrôle existant doit être caractérisé (fréquence, nature, mode).
- Chaque modification incrémente la version et est historisée.
- `control_risks` : relation **N-N** (couverture complète ou partielle, assertions, justification).
- **Matrice** : processus, objectif, risque, contrôle, statut, responsable, fréquence, preuves, conclusions, indicateur. Seul un contrôle existant ou non formalisé et actif couvre un risque. Les contrôles attendus ou absents apparaissent comme manquants. Les risques non couverts et les contrôles sans risque sont listés.

## 5. Exécutions des contrôles
- `control_executions` : l'exécutant documente une occurrence (date, résultat, exceptions, preuve facultative stockée dans le bucket privé `ic-evidence` avec son empreinte SHA-256).
- La supervision est faite par le superviseur du contrôle, un superviseur du domaine ou son responsable, **jamais par l'exécutant** (imposé en base). Une exécution supervisée est figée et une exécution n'est jamais supprimée.
- Les exécutions approuvées peuvent constituer la population d'un test d'efficacité.

## 6. Programmes et tests (dans une mission)
- Mission de type `ic_assessment` (ouverte par un pilote du contrôle interne) ou `internal_audit`.
- **Programme de contrôle** : crée un programme de travail du socle, puis une procédure et un test planifié par contrôle et par type de test.
- `control_tests` : test de **conception** ou d'**efficacité opérationnelle** ; natures (examen documentaire, observation, entretien, inspection, rapprochement, recalcul, réexécution, analyse de données) ; objectif, risque visé, procédure, responsable, période, population, méthode de sélection, taille d'échantillon, critères d'acceptation, exceptions tolérées, résultat attendu, synthèse, anomalies, conclusion et justification.
- **Taille d'échantillon** : saisie par l'utilisateur avec son fondement (méthodologie ou jugement), jamais proposée.
- **Sélection** : moteur du lot 7 (exhaustive, aléatoire ou systématique avec graine), sur les exécutions de la période ou sur une liste collée. Les paramètres sont conservés ; la sélection par jugement se fait par ajout manuel.
- `control_test_items` : éléments testés (conforme, exception décrite, sans objet motivé) et testeur enregistré.
- Critères évalués (oui, partiellement, non, sans objet, commentaire) :
  - **conception** : répond au risque, correctement défini, attribué, fréquence adaptée, documenté, indépendant, prévient ou détecte ;
  - **efficacité** : exécuté, par la bonne personne, à la bonne fréquence, preuves produites, supervisé, anomalies détectées ou prévenues.
- **Conclusion** : efficace, partiellement efficace, inefficace, non testé, non applicable (justification obligatoire). La base refuse :
  - « efficace » sans tous les critères évalués positivement, avec plus d'exceptions que tolérées ou sans élément probant ;
  - toute conclusion avec des éléments non testés, un échantillon incomplet ou, pour l'efficacité, sans période.
- **Circuit** : en cours → préparé (préparateur) → revu (réviseur, **autre personne**). Un test préparé ou revu est figé, éléments et preuves compris ; la réouverture d'un test revu est motivée et ne supprime pas le résultat précédent. Les éléments probants du dossier sont rattachés au test ou à un élément.

## 7. Synthèse et évaluations
- **Règle IC-SYNTH-1** (moteur Python et fonction SQL identiques) : conclusion d'un contrôle à partir de ses derniers tests revus de conception et d'efficacité :
  - aucun test : non testé ;
  - un test inefficace : inefficace ;
  - sans test d'efficacité concluant : non testé (la conception seule ne suffit pas) ;
  - un test partiel : partiellement efficace ;
  - sinon : efficace.
- Un contrôle déclaré existant reste donc « non testé » tant qu'aucun test ne l'a établi.
- `ic_assessments` : évaluation du dispositif général, d'un domaine, d'un processus, d'un cycle, d'une composante, d'un risque ou d'un contrôle, à une date :
  - niveau de maîtrise choisi sur l'échelle de la méthodologie de la mission, conclusion motivée ;
  - à la soumission, la base calcule et fige la synthèse (contrôles par conclusion, contrôles clés inefficaces, contrôles manquants, risques non couverts) ;
  - l'approbation par une autre personne est refusée si les résultats ont changé depuis la soumission ;
  - une évaluation approuvée est figée et conservée ; une nouvelle évaluation crée une nouvelle ligne, les évaluations historiques restent consultables.

## 8. Déficiences et remédiation
- Une déficience est un `findings.kind = 'ic_deficiency'`, dans une mission `ic_assessment` ou `internal_audit`. Elle exige le contrôle concerné et peut porter le risque ; son domaine est hérité du contrôle. Sa gravité est un niveau de la `deficiency_scale` de la méthodologie. La nature d'un constat ne change pas.
- Contenu : critère de référence, situation observée, cause, conséquence, recommandations (`recommendations`), réponse de la direction, plans de remédiation (`action_plans`) et leur historique (`action_plan_updates`, non modifiable).
- Cycle : brouillon → validation (autre personne que l'auteur, au moins une recommandation) → communication → réponse → plan d'action → mise en œuvre → vérification (encadrement) → **clôture**.
- La clôture (statut `closed`, note obligatoire) exige un plan par recommandation, chacun vérifié ou en risque accepté. Une déficience validée n'est modifiable qu'après une remise en brouillon motivée ; une déficience close est figée.
- Après l'émission de la mission : le suivi, la vérification et la clôture restent possibles, rien d'autre.
- « Points à examiner » : contrôles conclus inefficaces ou partiels, contrôles manquants, risques non couverts, sans déficience. Ils sont présentés sans aucune création automatique.

## 9. Intégrations
- **Audit financier (lot 7)** : `control_test_reliances`. L'équipe d'une mission d'audit légal ou contractuel consulte les tests revus de l'entité et décide :
  - décisions possibles : confiance, confiance partielle, pas de confiance ; motivation, cycle, assertions, adaptation de l'approche ;
  - la confiance exige un test d'efficacité « efficace », la confiance partielle « efficace » ou « partiellement efficace », et la période testée doit recouvrir la période auditée ;
  - période, périmètre, conclusion et empreintes des preuves sont figés dans la décision ; le retrait est motivé et la décision conservée.
- **Audit interne (lot 8)** : même registre, mêmes constats et plans ; les missions d'audit interne peuvent tester des contrôles et consulter les évaluations selon leurs droits.
- **Contrôle de gestion (lot 5)** : aucun changement du moteur. Un rapprochement futur des risques avec les centres de coûts reste possible par le domaine ou le processus.

## 10. Rôles et permissions
`ic_members` : rôles par entité, éventuellement limités à un domaine. Ils sont vérifiés par l'API (`IcContext`) et par la base (`authz.ic_roles`, `ic_admin`, `ic_manages`, `ic_reader`, RLS et déclencheurs).

| Rôle | Droits |
|---|---|
| Administrateur de l'organisation, responsable du contrôle interne (`ic_manager`), DAF (`daf`) | Pilotes : rôles, domaines, référentiels et correspondances, tout le registre ; ouvrent les missions d'évaluation |
| Responsable de domaine, responsable de processus | Processus, risques, contrôles et liens de leur domaine ; supervision de ses exécutions |
| Exécutant (`control_performer`) | Documente les exécutions des contrôles qui lui sont attribués ou de son domaine |
| Superviseur | Supervise les exécutions documentées par d'autres |
| Auditeur interne, auditeur financier | Rôles de mission (lot 6) : préparent, revoient, décident dans leur dossier ; lecture du dispositif, sans modification des données opérationnelles |
| Audité | Déficiences communiquées et évaluations approuvées ; aucun accès aux tests ni aux dossiers |
| Observateur | Lecture seule du dispositif de l'entité |

Les pilotes et le responsable du domaine suivent les déficiences communiquées ou closes ; les déficiences en brouillon ne sont visibles que de l'équipe de mission. Les tests non revus restent dans le dossier de la mission. Aucune donnée n'est visible d'une autre organisation.

## 11. Historisation
`ic_history` (en ajout seul) trace les créations, modifications et suppressions : domaines, objectifs, contrôles, liens risques-contrôles, exécutions, tests, éléments, évaluations, prises en compte. Le journal `audit_logs` reçoit en plus chaque action d'API (`ic.*`).

## 12. Interface
- Navigation principale : **Contrôle interne** → choix de l'entité.
- Espaces de l'entité (`/companies/{id}/controle-interne/…`) :
  - tableau de bord filtrable par domaine et processus ;
  - référentiels et méthodologies ;
  - domaines et processus, avec la fiche d'un domaine : processus, risques, contrôles, tests, déficiences et recommandations ;
  - registre des risques ;
  - catalogue des contrôles et fiche d'un contrôle : risques couverts, référentiels, exécutions et supervision, tests, déficiences, historique ;
  - matrice risques-contrôles ;
  - programmes, tests et évaluations ;
  - déficiences, recommandations, plans de remédiation, suivi des actions ;
  - rapports, rôles.
- Les tableaux offrent recherche, filtres, tri et pagination.
- Onglet **Contrôle interne** de la mission :
  - évaluation du contrôle interne ou audit interne : programme, tests (fiche complète) et évaluations ;
  - audit financier : prise en compte des tests revus.
- Les déficiences se rédigent dans l'onglet « Constats et recommandations ». Le suivi des actions se saisit dans la mission d'origine, avec ses droits.
- Formulaire des méthodologies : catégorie, organisme, dates et document source pour le type « contrôle interne ».

## 13. Rapports
Neuf rapports, établis uniquement sur les tests revus et les évaluations approuvées :
- évaluation du contrôle interne ;
- par domaine, par processus, par cycle comptable ;
- cartographie des risques ;
- matrice risques-contrôles ;
- contrôles inefficaces ;
- déficiences ;
- suivi des plans de remédiation.

Chacun est une structure neutre (titre, filtres, sections tabulaires, sources) servie par l'API et exportable par section en CSV. Elle est prête pour les exports PDF, Excel et Word du lot 11, non développés ici.

## 14. API
- Entité, `/companies/{id}/ic/…` :
  - droits et rôles : `access`, `members`, `candidates` ;
  - référentiels : `frameworks`, `framework-mappings`, `framework-links` ;
  - structure : `templates`, `domains` (dont `from-templates` et `overview`), `processes`, `objectives` ;
  - registre : `risks` (et `history`), `controls` (fiche, `history`, `risks`, `executions`), `executions/{id}/supervise|download`, `matrix` ;
  - pilotage : `deficiency-candidates`, `dashboard`, `tests`, `assessments`, `deficiencies`, `action-plans`, `reports/{kind}` (et `{section}.csv`), `history`.
- Mission, `/engagements/{id}/ic/…` :
  - `program`, `tests` (CRUD, `status`, `items`, `select`), `test-items/{id}` ;
  - `assessments` (CRUD, `status`) ;
  - `registry`, `reliance-candidates`, `reliances` (et `withdraw`).

## 15. Tests
- **SQL** (`tests/sql/test_internal_control.sql`, 94 contrôles) : isolation entre organisations, RLS de chaque table, domaines et héritages, grilles versionnées, matrice N-N, versions et historique, référentiels publiés et correspondances, séparation exécutant / superviseur et préparateur / réviseur, règles de conclusion, gel des tests et des évaluations, réouverture motivée, déficiences et cycle complet jusqu'à la clôture, prise en compte par l'audit financier, accès de l'audité, de l'observateur, des pilotes et des auditeurs, mission émise.
- **Unitaires** (`tests/engines/test_internal_control.py`, 12 fonctions dont une paramétrée) : cotation sur la grille, synthèse identique à la règle SQL, dernier test revu par type, évaluation de la conception et de l'efficacité, matrice et couverture, identification des déficiences, étapes de leur cycle, indicateurs du tableau de bord, rapports et CSV, modèles de domaines, validation des méthodologies et des échelles.
- **Intégration** (`tests/integration/test_internal_control_api.py`) : parcours complet, de la création du domaine jusqu'à la clôture et aux rapports, avec contrôles d'isolation. Exécuté par la CI.

## 16. Limites connues
- Aucun contenu de référentiel chargé (voir §1) : les évaluations par composante et les échelles dépendent des documents que l'organisation importera.
- Le rapprochement avec les centres de coûts et budgets (lot 5) n'est pas développé.
- Les exports PDF, Excel et Word relèvent du lot 11 ; seul le CSV par section est livré.
- Les mises à jour de suivi des plans se saisissent dans la mission d'origine : un pilote qui n'est pas membre de la mission ne peut que les consulter.
- Pas de relances automatiques des responsables d'action.
- Les exécutions récurrentes ne sont pas planifiées automatiquement (calendrier de contrôle).
