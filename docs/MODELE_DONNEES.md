# KOFINEX — Modèle de données

Conventions :
- clés UUID ;
- `organization_id` partout, plus `company_id` pour les données d'une entité ;
- clés étrangères composites anti-fuite entre organisations ;
- `created_at`, `created_by` ;
- énumérations en `text` + `CHECK` ;
- RLS sur chaque table.

« ✔ » : table existante (migrations 0001 à 0006). « + » : table à créer, avec son lot.

## 1. Existant

| Domaine | Tables |
|---|---|
| Tenancy | ✔ `profiles`, `organizations`, `organization_members`, `companies`, `company_members`, `fiscal_years` |
| Référentiels | ✔ `accounting_frameworks`, `framework_versions`, `chart_of_accounts`, `account_mappings`, `statement_line_definitions`, `framework_concepts` |
| Import | ✔ `financial_documents`, `import_jobs`, `import_mappings`, `import_staging_rows`, `trial_balance_entries` |
| Analyse | ✔ `financial_statements`, `financial_statement_lines`, `financial_formulas`, `financial_analyses`, `financial_indicators`, `financial_alerts` |
| Contrôle de gestion | ✔ `cost_centers`, `budgets`, `budget_lines`, `cost_entries` (complétées en 0006), ✔ `costing_models` (0006) ; `budget_actuals` non utilisé (réalisé calculé à la demande) — voir `CONTROLE_GESTION.md` |
| IA | ✔ `ai_conversations`, `ai_messages`, `ai_reports` |
| Reporting | ✔ `report_templates`, `generated_reports` |
| SaaS / transverse | ✔ `integrations`, `subscriptions`, `payments`, `audit_logs` (journal de traçabilité) |

## 2. Compléments comptables (lot 3, suite)

| Table | Rôle | Relations clés |
|---|---|---|
| `ledger_lines` (**créée par la migration 0010** ; nom retenu au lieu de `ledger_entries`) | Lignes d'écritures : journal, pièce, date, compte, libellé, débit, crédit, auxiliaire, lettrage, saisie par, date de saisie | `import_jobs`, `fiscal_years` ; contrôle de cohérence : total par compte = mouvements de `trial_balance_entries` |

## 3. Méthodologies (socle commun, lot 6) : données versionnées, comme les référentiels

| Table | Rôle |
|---|---|
| + `methodologies` / `methodology_versions` | Méthodologie d'audit ou cadre de contrôle interne (portée : plateforme ou organisation), source, statut `draft/published/archived`, figée une fois publiée |
| + `methodology_items` | Éléments typés de la version : `assertion`, `cycle` (avec racines de comptes), `risk_scale`, `materiality_benchmark` (options et fourchettes de la méthodologie), `sample_size_rule`, `procedure_template`, `deficiency_scale`, `ic_component` / `ic_principle`, `report_template_ref`. Contenu en `jsonb` validé par un schéma propre à chaque type. |

Une table générique typée a été préférée à une table par notion : les méthodologies des cabinets diffèrent, et le cycle de vie (brouillon, publication, gel) est commun. La validation du contenu se fait dans `engines/audit/methodology.py`.

## 4. Socle commun d'audit (lot 6)

**Créées par la migration 0007** : `methodology_versions`, `methodology_items`, `processes`, `risks`, `engagements`, `engagement_members`, `engagement_risks`, `work_programs`, `procedures`, `procedure_risks`, `workpapers`, `evidence_items`, `evidence_links`, `review_notes`, `signoffs` (bucket privé `audit-evidence`). **Reportées** aux lots qui les utilisent : `engagement_milestones`, `time_entries`, `document_requests`, `findings`, `action_plans`, `action_plan_updates`, échantillonnage et `data_analytics_runs`. Règles : `docs/AUDIT_SOCLE.md`.

| Table | Rôle | Relations clés |
|---|---|---|
| + `engagements` | Mission : type (`statutory_audit`, `contractual_audit`, `internal_audit`, `ic_assessment`), entité, exercice ou période, objectifs, périmètre, statut, version de méthodologie figée | `companies`, `fiscal_years` (facultatif), `methodology_versions` |
| + `engagement_members` | Équipe : rôle de mission (`partner`, `manager`, `in_charge`, `staff`, `quality_reviewer`, `auditee`, `observer`), heures prévues, date de déclaration d'indépendance | `profiles` ; **accès à la mission = présence dans cette table**, les administrateurs de l'organisation compris (qui peuvent s'ajouter, de façon tracée) |
| + `engagement_milestones` | Jalons et échéances | `engagements` |
| + `time_entries` | Temps passé par membre et par tâche | `engagement_members` |
| + `document_requests` | Liste des documents demandés à l'audité : objet, échéance, relances, statut | `engagements` ; un dépôt de l'audité crée un `evidence_items` |
| + `processes` | Cartographie des processus de l'entité (arborescence parent → enfant, propriétaire) | `companies` ; **partagée** par l'audit interne et le contrôle interne |
| + `risks` | Registre des risques de l'entité : processus ou cycle/assertion, cotation inhérente et résiduelle, version de la grille | `processes`, `methodology_items` |
| + `engagement_risks` | Risques retenus pour une mission (réévalués à la date de la mission), réponse prévue | `engagements`, `risks` (facultatif), cycle/assertion |
| + `work_programs`, `procedures` | Programme et procédures : objectif, nature (test de contrôle, procédure analytique, test de détail, observation…), assigné, statut | `engagements`, `methodology_items` (modèle d'origine), N-N avec `engagement_risks` via `procedure_risks` |
| + `workpapers` | Feuille de travail : référence, contenu structuré, conclusion, version | `procedures` (facultatif), `engagements` |
| + `evidence_items` | Élément probant : fichier (bucket `audit-evidence`) ou instantané de données de la plateforme, empreinte, source, date d'obtention, déposé par | `engagements` ; liens N-N via `evidence_links` (vers procédure, feuille, constat, élément d'échantillon, test de contrôle, plan d'action) |
| + `findings` | Constat : critère, cause, conséquence, recommandation, priorité, réponse de l'audité, statut | `engagements`, `processes`/`risks` (facultatif), `controls` (facultatif) |
| + `action_plans`, `action_plan_updates` | Plan d'action : responsable, échéance, statut ; historique des mises à jour et preuves | `findings` ; suivi possible au-delà de la mission |
| + `review_notes` | Note de revue sur un objet : auteur, destinataire, réponse, statut | objet polymorphe (`object_type`, `object_id`) contrôlé par `CHECK` + *trigger* |
| + `signoffs` | Signature : objet, rôle (`preparer`, `reviewer`, `quality_reviewer`, `approver`), utilisateur, date, empreinte du contenu, révoquée le | objet polymorphe ; réservée aux humains (cf. CDC technique § 5) |

## 5. Audit financier et comptable (lot 7)

**Créées par la migration 0008** : `fa_materiality`, `fa_cycle_mappings`, `fa_account_reviews`, `fa_populations`, `fa_population_items`, `fa_samples`, `fa_sample_items`, `fa_confirmations`, `fa_misstatements`, `fa_misstatement_lines`, `fa_conclusions`. Les noms diffèrent de la conception initiale ci-dessous (préfixe `fa_`, cycles × assertions portés par les risques du lot 6) ; la balance et les états ajustés sont **calculés**, pas enregistrés. Règles : `docs/AUDIT_FINANCIER.md`.

| Table | Rôle | Relations clés |
|---|---|---|
| + `fa_materiality` | Seuils : référentiel retenu, montant de base (issu d'un état figé), pourcentage, justification, seuil global, de planification et des anomalies insignifiantes ; versions successives (planification, révisée, finale) | `engagements`, `financial_statements` |
| + `fa_cycle_assessments` | Évaluation par cycle × assertion : risque inhérent, appui sur les contrôles, approche retenue | `engagements`, `methodology_items` (cycle, assertion), `ic_assessments` (facultatif) |
| + `fa_samples`, `fa_sample_items` | Échantillon : population (définition + empreinte), méthode, paramètres, graine, taille ; éléments tirés, résultat du test, anomalie constatée | `procedures`, `ledger_entries` ou `trial_balance_entries` |
| + `fa_confirmations` | Circularisations : tiers, compte, solde comptable, envoi, relance, réponse, écart | `engagements`, `evidence_items` |
| + `fa_misstatements` | Anomalie : type (factuelle, de jugement, extrapolée), montant, effet sur le résultat et les capitaux propres, statut (corrigée / non corrigée) | `engagements`, `fa_sample_items`/`findings` (facultatif) |
| + `fa_adjustments`, `fa_adjustment_lines` | Écritures d'ajustement proposées : lignes compte / débit / crédit, statut (proposée, acceptée, refusée) | `fa_misstatements` ; la balance ajustée = balance validée + lignes acceptées, **calculée, jamais écrite dans `trial_balance_entries`** |

## 6. Audit interne (lot 8)

**Créées par la migration 0009** : `audit_plans`, `audit_plan_items`, `audit_plan_item_history`, `risk_rating_history`, `findings`, `recommendations`, `action_plans`, `action_plan_updates`, `audit_reports` ; type de méthodologie `finding_scale`. `findings`, `recommendations` et `action_plans` servent aussi au lot 9 (missions `ic_assessment`). Règles : `docs/AUDIT_INTERNE.md`.

| Table | Rôle | Relations clés |
|---|---|---|
| + `iaud_universe_items` | Univers d'audit : entités auditables (processus, sites, filiales, systèmes), dernière mission, cotation | `processes`, `companies` |
| + `iaud_annual_plans`, `iaud_plan_items` | Programme annuel : version, statut d'approbation ; missions prévues, priorité, ressources, justification par les risques | `iaud_universe_items` ; un élément réalisé est lié à son `engagements` |

Les missions, constats et plans d'action réutilisent le socle commun.

## 7. Contrôle interne (lot 9)

**Créées par la migration 0011** (13 tables) ; règles : `docs/CONTROLE_INTERNE.md`.

| Table | Rôle | Relations clés |
|---|---|---|
| `framework_mappings` | Correspondance motivée entre éléments de deux référentiels (équivalent, partiel, en rapport) | `methodology_items` (source, cible) ; organisation ou plateforme |
| `ic_domains` | Domaine ou cycle de l'entité (comptable et financier, organisationnel, libre), éventuellement issu d'un modèle | `companies` |
| `ic_members` | Rôle du contrôle interne sur l'entité, éventuellement limité à un domaine | `companies`, `ic_domains`, `profiles` |
| `control_objectives` | Objectif de contrôle, assertions | `ic_domains`, `processes` |
| `controls` | Contrôle : statut (existant, attendu, non formalisé, absent), responsable, exécutant, superviseur, fréquence, nature, mode, procédure, justificatifs, critères, clé, version | `ic_domains`, `processes`, `control_objectives` |
| `control_risks` | Matrice risques-contrôles **N-N** : couverture, assertions, justification | `controls`, `risks` |
| `ic_framework_links` | Rattachement d'un contrôle, risque, objectif ou domaine à un élément publié | `methodology_items` |
| `control_executions` | Exécution documentée, preuve (bucket `ic-evidence`, SHA-256), supervision | `controls`, `profiles` |
| `control_tests` | Test de conception ou d'efficacité dans une mission : période, population, sélection et paramètres, taille et fondement, critères, conclusion, préparateur, réviseur | `engagements`, `controls`, `risks`, `procedures`, `workpapers` |
| `control_test_items` | Élément testé : résultat, exception, motif, testeur | `control_tests`, `control_executions` |
| `ic_assessments` | Évaluation à une date (dispositif, domaine, processus, cycle, composante, risque, contrôle) : niveau de maîtrise, synthèse figée (`basis`) | `engagements`, `ic_domains`, `processes`, `risks`, `controls`, `methodology_items` |
| `control_test_reliances` | Prise en compte d'un test revu par une mission d'audit financier : décision, instantané figé | `engagements`, `control_tests` |
| `ic_history` | Historique non modifiable du dispositif | `companies` |

**Tables existantes complétées** :
- `methodology_versions` : `framework_category`, `issuing_body`, `published_on`, `effective_from`, `source_document` ;
- `methodology_items.item_type` : `ic_requirement`, `ic_criterion`, `control_level_scale` ;
- `processes` : `domain_id`, `owner_user_id` ;
- `risks` : `domain_id`, `objective_id`, `category`, `causes`, `consequences`, `owner_name`, `owner_user_id`, `control_level_code` ;
- `risk_rating_history` : `control_level_code` ;
- `findings` : `kind` (`audit_finding`, `ic_deficiency`, `management_letter_point`), `control_id`, `risk_id`, `domain_id`, clôture (`closed_by`, `closed_at`, `closure_note`, statut `closed`) ;
- `evidence_links`, `review_notes` : objets `control_test`, `control_test_item`, `ic_assessment`.

## 8. IA et documents (lots 10 et 11)
- **IA** :
  - **livré au lot 10 (migration 0012)** — règles : `docs/IA.md` ;
  - `ai_settings` : activation par organisation, usages autorisés, note d'accord ;
  - `ai_conversations` (+ `purpose`) et `ai_messages` (+ `prompt_version`) : assistant financier, contexte et contrôle des chiffres conservés ;
  - `ai_reports` (+ `review_note`) : commentaires d'analyse, relus ou rejetés ;
  - `ai_suggestions` : mission, nature, proposition, sources, contexte, contrôle, modèle, statut (`pending`, `accepted`, `rejected`), décideur, version relue, objet créé ;
  - provenance : `engagement_risks.ai_suggestion_id`, `procedures.ai_suggestion_id`, `findings.origin` et `findings.ai_suggestion_id` ;
  - les conversations d'audit (`engagement_id` sur `ai_conversations`) n'ont pas été créées : l'assistance d'audit passe par les suggestions.
- **Reporting** :
  - **livré au lot 11 (migration 0013)** — règles : `docs/REPORTING.md` ;
  - `report_templates` (+ `document_type`, `version`, `status`, `content`, `published_by`, `published_at`) : modèles versionnés, figés à la publication ;
  - `generated_reports` (+ `engagement_id`, `document_type`, `subtype`, `title`, `filename`, `mime_type`, `size_bytes`, `data_sha256`, `content_snapshot`, `source_refs`, `parameters`, `template_version`, `generator_version`, `contains_ai_drafts` ; `analysis_id` devient facultatif) : documents figés ;
  - `data_analytics_runs` (analyses de données d'audit) n'a pas été créée : les analyses du grand livre sont recalculées à la demande (lot 3).

## 8 bis. Comptabilité native (lot 3B, migration 0014)
| Table | Rôle |
|---|---|
| `accounting_settings` | Étape de revue, séparation des tâches (une ligne par entreprise, valeurs par défaut sinon) |
| `company_accounts` | Plan comptable de l'entreprise ; chaque compte rattaché à un compte de `chart_of_accounts` d'une version publiée ; collectif, type de tiers, lettrable, actif |
| `third_parties` | Tiers : code, type, compte collectif, coordonnées |
| `journals` | Journaux : code, type, préfixe, compte de trésorerie, utilisateurs autorisés, actif |
| `journal_sequences` | Dernier numéro par journal et exercice (écrit par la base seulement) |
| `journal_entries` | Écritures natives : en-tête, provenance (`origin`, `source_type` / `source_id`, extourne, correction), statut, numéro, totaux tenus par la base, auteurs et dates du circuit |
| `journal_entry_lines` | Lignes : compte de l'entreprise, tiers, débit ou crédit, centre analytique, devise, lettrage |
| `journal_entry_attachments` | Pièces justificatives (`financial_documents`, type `accounting_voucher`) |
| `journal_entry_events` | Historique du circuit, immuable |
| `letterings` | Lettrages complets (code par compte, montant) |

Réutilisé sans duplication : `fiscal_years` (exercice et clôture), `chart_of_accounts` et `framework_versions` (référentiel), `cost_centers` (analytique), `financial_documents` et le stockage (pièces), `audit_logs`. Non modifié : `ledger_lines`, `trial_balance_entries`, `import_jobs`.

## 8 ter. Pilotage du contrôle de gestion (migration 0015)
| Table | Rôle |
|---|---|
| `management_alert_settings` | Seuils d'alerte budgétaire et d'analyse, par entreprise (valeurs par défaut si absente) ; RLS : lecture par l'entité, écriture par les contrôleurs et administrateurs |

Aucune table d'indicateurs ni copie des écritures : le pilotage lit `journal_entries` / `journal_entry_lines`, `ledger_lines` ou `trial_balance_entries` (une seule source à la fois) et les recalcule à la demande (`CONTROLE_GESTION.md` § 11).

## 8 quater. FEC DGI Bénin (migration 0016)
| Table | Rôle |
|---|---|
| `fec_exports` | Historique des générations du FEC, figé : entreprise, exercice, version, période, IFU, nom réglementaire, format, encodage, séparateurs, type de comptabilité, fichiers produits (`parts`, un ou plusieurs avec suffixe `_1.._n`), totaux, nombre de lignes, résultat du contrôle (anomalies, conformité), empreintes SHA-256, documentation, auteur, date |
| `fec_export_lines` | Traçabilité : ligne n du fichier → ligne d'écriture native validée |

Pas de copie des écritures : le FEC lit `journal_entries` / `journal_entry_lines` par `native_ledger.posted`. Fichiers dans le bucket privé `fec`. Voir `FEC_BENIN.md`.

## 8 quinquies. Catalogue commercial et abonnements (lot 12A, migration 0018)
| Table | Rôle |
|---|---|
| `billing_settings` | Paramètres de la plateforme, une ligne : grâce, délais, relances, vendeur, pays ouverts et devise de chacun |
| `billing_modules` | Modules commercialisables (modules livrés seulement) et leurs dépendances |
| `billing_products` | Offres de base (`plan`) et options (`addon`) |
| `billing_product_versions` | Versions figées à la publication (essai, libellé) ; une seule publiée par offre |
| `billing_prices` | Prix par version, périodicité et devise (XOF, XAF, GNF, KMF, CDF) |
| `billing_entitlements` | Modules et limites de quota par version (`NULL` : illimité) |
| `billing_promotions`, `billing_promotion_redemptions` | Codes promotionnels (conditions figées) et leurs utilisations (écrites en 12B) |
| `billing_accounts` | Identité de facturation, 1:1 avec l'organisation ; le pays fixe la devise |
| `subscription_items` | Lignes d'un abonnement : offre de base et options |

`subscriptions` (0001) est complétée par ALTER, jamais remplacée ; le client n'y écrit pas (fonctions `billing_start_trial`, `billing_schedule_cancel`, `billing_reactivate`). Pas de table d'historique (journal d'audit) ni de compteur d'usage (mesure sur les tables existantes, `billing_org_usage`). Voir `LOT12_SAAS_CONCEPTION.md`.

## 8 sexies. Budget relié au plan comptable (migration 0020)
| Table | Rôle |
|---|---|
| `budget_kinds` | Types de budget (résultat, ventes, achats, charges, investissements) et racines / natures de comptes autorisées : **données** de plateforme, « à valider » ; base du réalisé (soldes ou mouvements) |
| `budget_rubrics` | Rubriques d'un budget : regroupent des lignes de plusieurs comptes ou une ligne sans compte ; figées avec le budget |

`budgets.budget_kind`, `budget_lines.rubric_id` et `budget_lines.forecast_mode` (manuel, calculé, importé) sont ajoutés par ALTER. Le plan de référence n'est pas copié : il est lu par `budget_reference_accounts` (plan de l'entreprise, sinon référentiel publié). Voir `CONTROLE_GESTION.md` § 12.4.

## 8 septies. Plan de trésorerie (migration 0021)
| Table | Rôle |
|---|---|
| `treasury_plans` | Plan de trésorerie d'un exercice : nom, devise, solde initial (saisi ou proposé d'après la comptabilité), statut (brouillon, approuvé, archivé) |
| `treasury_rubrics` | Rubriques A (encaissements) et B (décaissements), sous-rubriques sur un niveau, comptes associés (racines) pour le réalisé, modalité de prévision (manuelle, % d'une rubrique, budget décalé) |
| `treasury_amounts` | Montants mensuels (1 à 12, positifs) par rubrique de saisie et scénario (initial, actualisé) |

Justification : aucune table existante ne porte une prévision de trésorerie (les budgets portent des charges et produits, pas des flux d'encaissement). Soldes, totaux, réalisé et écarts ne sont pas stockés. Voir `CONTROLE_GESTION.md` § 12.5.

## 9. Anti-doublons : décisions
- **Un seul registre** de processus et de risques par entité, partagé par l'audit interne, le contrôle interne et l'audit financier.
- **Une seule table** de constats et de plans d'action pour les trois disciplines (colonne `kind` : `audit_finding`, `ic_deficiency`, `management_letter_point`).
- **Une seule table** de signatures et une de notes de revue, polymorphes.
- Les éléments probants **référencent** les données existantes (balances, écritures, documents importés) au lieu de les copier, sauf les instantanés figés, nécessaires à la preuve.
- Les alertes financières (`financial_alerts`) restent dans l'analyse financière. Les résultats des analyses de données d'audit vont dans `data_analytics_runs` : leurs cycles de vie diffèrent.
