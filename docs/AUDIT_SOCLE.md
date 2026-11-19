# KOFINEX — Socle commun d'audit (lot 6)

Le socle sert aux trois disciplines : audit financier (lot 7), audit interne (lot 8), contrôle interne (lot 9). Il ne contient **aucun contenu normatif** : les assertions, cycles, grilles de cotation et programmes types sont chargés par chaque cabinet comme des données versionnées et sourcées.

## 1. Méthodologies (`/methodologies`)
- Version = nom + libellé de version + **source de référence obligatoire** ; portée plateforme (administrateurs de la plateforme) ou organisation (propriétaires et administrateurs).
- Éléments chargés par CSV `type;code;libelle;parent;contenu;ordre` (modèle vide téléchargeable). Types : `assertion`, `cycle`, `risk_scale`, `procedure_template`, `ic_component`, `ic_principle`, `deficiency_scale`, `parameter`. Le chargement remplace les éléments ; les anomalies sont rendues ligne par ligne et un fichier en erreur n'est pas chargé.
- Cycle de vie `draft → published → archived`. Publication refusée si le contenu est incohérent (`engines/audit/methodology.py`). **Une version publiée est figée en base** ; une mission garde la version choisie en planification.

## 2. Missions (`/organizations/{org}/missions`, `/missions/{id}`)
- Types : `statutory_audit`, `contractual_audit`, `internal_audit`, `ic_assessment`. Entité, exercice (facultatif), période, objectifs, périmètre, méthodologie publiée.
- Phases : `planning → fieldwork ⇄ review ⇄ reporting → issued → archived`.

| Transition | Qui | Conditions contrôlées en base |
|---|---|---|
| planification → terrain, revue → rapport | manager, associé | indépendance déclarée |
| terrain ⇄ revue | encadrement (associé, manager, chef de mission) | — |
| rapport → émise | associé | toutes les feuilles approuvées ; aucune note de revue ouverte ; signature de revue qualité si un réviseur qualité est dans l'équipe ; signature d'approbation de la mission par l'associé |
| émise → archivée | manager, associé | — |
| émise / archivée → rapport | associé | **motif obligatoire**, tracé |

- Une mission émise ou archivée est **figée** : feuilles, procédures, éléments probants, notes et signatures ne bougent plus.
- Suppression possible seulement en planification, sans feuille ni élément probant.

## 3. Équipe, indépendance et accès
- Rôles : `partner`, `manager`, `in_charge`, `staff`, `quality_reviewer`, `auditee`, `observer`. Le créateur est ajouté comme associé.
- **Accès au dossier** (`authz.can_read_dossier`) : membre de l'équipe d'audit ayant **déclaré son indépendance** (`public.confirm_independence`, déclaration horodatée, par l'intéressé uniquement). Un changement de rôle annule la déclaration. L'audité ne voit ni les feuilles ni les notes de revue.
- Les capacités renvoyées par l'API (`capabilities`) pilotent l'affichage ; les mêmes règles sont appliquées par l'API et par les triggers et la RLS.

## 4. Risques, programmes, procédures
- Registre des processus et risques **de l'entité** (partagé par les lots 8 et 9) et risques retenus **pour la mission** (`engagement_risks`).
- Cotation = probabilité × impact selon la grille `risk_scale` de la méthodologie ; la grille peut indiquer un seuil « au-dessus duquel » le risque est signalé, mais le caractère **significatif** est coché par l'auditeur.
- Programmes → procédures (nature, étapes, assertions, affectation, échéance, avancement, motif obligatoire si « non applicable »), créées à la main ou copiées depuis les programmes types. Lien N-N procédures ↔ risques ; la supervision signale les risques non couverts.

## 5. Feuilles de travail et signatures
- Circuit `draft → prepared → reviewed → approved`, porté par les signatures (`preparer`, `reviewer`, `approver`, `quality_reviewer`).
- Règles imposées en base : signataire = `auth.uid()` ; réviseur ≠ préparateur et de rôle supérieur ; approbateur ≠ préparateur ; approbation impossible avec des notes ouvertes ; chaque signature porte l'**empreinte SHA-256 du contenu**.
- Toute modification d'une feuille signée la renvoie en brouillon, incrémente la version et **révoque les signatures** (motif « Contenu modifié après signature »). Une révocation manuelle exige un motif et révoque les signatures dépendantes.
- Notes de revue : rédigées par l'encadrement et le réviseur qualité, répondues puis closes ; jamais supprimées.

## 6. Éléments probants
- Fichier déposé par l'API après contrôle (format réel, macros refusées, 50 Mo) dans le bucket privé `audit-evidence`, empreinte SHA-256, source, date d'obtention ; original immuable, lecture par URL signée courte.
- **Instantané de la balance validée** de l'exercice audité : données figées et empreinte, sans copie modifiable.
- Rattachements N-N aux procédures et feuilles ; figés quand la feuille est signée.
- **Aucune preuve n'est produite par l'IA** ; un élément probant est toujours déposé ou figé par un humain identifié.

## 7. Supervision
Tableau de bord par mission : avancement des procédures et des feuilles, notes ouvertes, risques non couverts (dont significatifs), membres sans déclaration d'indépendance, procédures en retard, liste des contrôles d'émission avec leur résultat.

## 8. Reporté aux lots suivants
Constats et plans d'action (`findings`, `action_plans`), demandes de documents à l'audité, jalons et temps passés, échantillonnage, analyses de données, portail de l'audité. Les tables `signoffs`, `review_notes` et `evidence_links` sont déjà polymorphes pour les accueillir.

## 9. Tests
- `backend/tests/sql/test_audit_foundation.sql` : 46 contrôles (RLS, indépendance, séparation des tâches, empreintes et révocation, gel, émission, réouverture).
- `backend/tests/engines/test_audit_foundation.py` : 5 tests (méthodologie, workflow, éléments probants).
- `backend/tests/integration/test_engagements_api.py` : parcours API complet, à exécuter en CI.
