# KOFINEX — Architecture des modules

## 1. Découpage

| Module | Backend (`app/…`) | Frontend (`app/(app)/…`) | Lot | État |
|---|---|---|---|---|
| Tenancy et sécurité | `core/`, `api/v1/{me,organizations,companies,fiscal_years}` | `organizations/`, `companies/[id]` | 1 | livré |
| Design system | — | `components/ui`, `components/app-shell` | 2 | à faire (composants de base existants) |
| Référentiels et import | `engines/importing`, `engines/accounting`, `api/v1/{frameworks,imports}` | `referentiels/`, onglet *Imports* | 3 | livré, grand livre compris (voir `GRAND_LIVRE.md`) |
| Analyse financière | `engines/financial`, `api/v1/analysis` | `…/analysis`, `formules/` | 4 | livré (alertes à faire) |
| Contrôle de gestion | `engines/management` (réalisé, budget, coûts complets, CVP, standards, projections), `api/v1/management` | `companies/[id]/gestion` | 5 | livré |
| Pilotage (contrôle de gestion) | `engines/management/steering`, `services/steering`, `api/v1/steering` | `gestion` : tableaux de bord financier, budgétaire, trésorerie, masse salariale, analyse ; import de budget | 5 (évolution) | **livré** (voir `CONTROLE_GESTION.md` § 11) ; alimenté par les écritures validées |
| Socle d'audit | `engines/audit/{methodology,workflow,evidence}`, `api/v1/engagements` | `methodologies/`, `organizations/[orgId]/missions/`, `missions/[engagementId]/` | 6 | **livré** (voir `AUDIT_SOCLE.md`) ; échantillonnage et analyses de données reportés |
| Audit financier | `engines/audit/financial`, `api/v1/financial_audit` (`/engagements/{id}/fa/…`) | `missions/[engagementId]` (onglet « Audit financier ») | 7 | **livré** (voir `AUDIT_FINANCIER.md`) ; grand livre structuré, limite supérieure d'anomalie et dossier de synthèse reportés |
| Audit interne | `engines/audit/internal`, `api/v1/internal_audit` | `organizations/[orgId]/plan-audit`, `plan-audit/[planId]`, `companies/[companyId]/cartographie`, `organizations/[orgId]/suivi-recommandations`, onglets « Constats » et « Rapport » de la mission | 8 | **livré** (voir `AUDIT_INTERNE.md`) ; tableau de bord du comité reporté (lot 11) |
| Contrôle interne | `engines/audit/{control,ic_templates}`, `services/internal_control`, `api/v1/internal_control` (`/companies/{id}/ic/…`, `/engagements/{id}/ic/…`) | `organizations/[orgId]/controle-interne`, `companies/[companyId]/controle-interne/…` (14 espaces), onglet « Contrôle interne » de la mission | 9 | **livré** (voir `CONTROLE_INTERNE.md`) ; contenu des référentiels à charger |
| IA | `engines/ai` (contexte, chiffres, consignes, lecture, fournisseur), `services/ai`, `api/v1/ai` | `companies/[companyId]/assistant`, onglet « Assistant IA » de la mission, réglages de l'organisation | 10 | **livré** (voir `IA.md`) ; appels synchrones |
| Reporting | `engines/reporting` (document, constructeurs, rendus), `services/reporting`, `api/v1/reporting` | `companies/[companyId]/rapports`, onglet « Documents » de la mission, `organizations/[orgId]/modeles-rapports`, exports du contrôle interne | 11 | **livré** (voir `REPORTING.md`) ; génération synchrone |
| Comptabilité native | `engines/accounting/entries`, `engines/accounting/native_ledger`, `services/accounting_setup`, `services/journal_entries`, `services/native_ledger`, `api/v1/accounting` | `companies/[companyId]/comptabilite/…` (écritures, nouvelle écriture, grand livre, balance, lettrage, journaux, plan comptable, tiers, paramètres) | 3B | **étapes A et B livrées** (voir `COMPTABILITE_NATIVE.md`) ; auxiliaires, inventaire, clôture et états natifs à venir |
| FEC DGI Bénin (comptabilité) | `engines/accounting/fec_bj`, `services/fec`, `api/v1/fec` | `companies/[companyId]/comptabilite/fec` | 3B (évolution) | **livré** (voir `FEC_BENIN.md`) ; fichiers déclarés « points réglementaires à confirmer », jamais « conformes », tant que 6 points restent ouverts |
| Tableau de bord | `engines/financial/dashboard`, `services/dashboard`, `api/v1/dashboard` | `/tableau-de-bord`, coquille (`app-shell`, `lib/workspace`), `/` et `/demonstration` (publics) | interface | **livré** (voir `INTERFACE.md`) ; lecture seule de données validées |
| SaaS | `api/v1/{billing,admin,integrations}`, `connectors/` | `admin/`, `parametres/` | 12 | à faire |

Règle UI inchangée : **aucune entrée de menu pour un module non développé**.

## 2. Dépendances

```
1 Fondations ─┬─> 2 Design system ──────────────────────────────> (tous les écrans)
              └─> 3 Comptabilité/import ─> 4 Analyse financière ─> 5 Contrôle de gestion
                         │                        │
                         │ (balances, écritures)  │ (états, indicateurs, N-1)
                         ▼                        ▼
                    6 Socle d'audit (méthodologies, missions, équipe, risques, programmes,
                         │            feuilles, preuves, constats, revue, signatures)
           ┌─────────────┼───────────────┐
           ▼             ▼               ▼
   7 Audit financier  8 Audit interne  9 Contrôle interne
           ▲                             │ (tests de contrôles réutilisés par 7)
           └─────────────────────────────┘
   10 IA  : s'appuie sur 4 et sur 6 à 9 (contexte + table de suggestions)
   11 Reporting : s'appuie sur 4 à 9 (données validées uniquement)
   12 SaaS : quotas par module, facturation, connecteurs, mise en production
```

Dépendances critiques :
- Le grand livre (complément du lot 3, table `ledger_lines`) alimente le réalisé mensuel du contrôle de gestion et les populations d'écritures de l'audit financier ; les missions le consultent en lecture seule.
- **Les lots 8 et 9 partagent `processes` et `risks`** : ces tables naissent dans le lot 6, pas dans le 8 ni le 9. Le lot 9 les complète (domaine, attributs de risque) et réutilise `findings`, `recommendations`, `action_plans` et `action_plan_updates` (déficiences `kind = 'ic_deficiency'`).
- Le lot 7 lit les tests revus du lot 9 par `control_test_reliances` (décision motivée, instantané figé) ; le lot 9 réutilise le moteur de sélection du lot 7.
- **L'IA d'audit (lot 10)** exige que les tables de signatures et `ai_suggestions` existent, avec leurs interdits en base (lot 6). L'IA d'analyse financière peut être livrée plus tôt dans le lot 10, car le lot 4 est prêt.

## 3. Permissions

Trois niveaux, cumulatifs, appliqués **à la fois** dans l'API (`core/permissions.py`) et en RLS (fonctions `authz.*`).

| Niveau | Rôles | Portée |
|---|---|---|
| Organisation | `owner`, `admin`, `member`, `viewer` | Administration, création d'entités et de missions |
| Entité | `accountant`, `controller`, `analyst`, `auditor`, `viewer` | Données comptables et financières de l'entité |
| **Mission (nouveau)** | `partner`, `manager`, `in_charge`, `staff`, `quality_reviewer`, `auditee`, `observer` | Dossier de la mission uniquement |

Nouvelles fonctions RLS :
- `authz.engagement_role(engagement_id)` et `authz.can_access_engagement(engagement_id)` ;
- `authz.has_engagement_role(engagement_id, roles[])`.

Les tables du dossier de mission sont filtrées par `engagement_id`. L'**audité** ne voit que :
- les demandes de documents et les dépôts qui le concernent ;
- les constats communiqués ;
- ses plans d'action.

Il n'a jamais accès aux feuilles de travail ni aux notes de revue.

Matrice des actions de mission :

| Action | partner | manager | in_charge | staff | quality_reviewer | auditee | observer |
|---|---|---|---|---|---|---|---|
| Lire le dossier | ✔ | ✔ | ✔ | ✔ | ✔ | partiel | ✔ |
| Planifier, gérer l'équipe | ✔ | ✔ | ✔ (sauf associé et manager) | | | | |
| Seuils, évaluation des risques | ✔ | ✔ | ✔ | | | | |
| Préparer (procédures, feuilles, tests) | ✔ | ✔ | ✔ | ✔ | | | |
| Signer « revu par » | ✔ | ✔ | ✔ (travaux du staff) | | ✔ | | |
| Valider un constat, approuver la mission, émettre le rapport | ✔ | ✔ (sauf émission) | | | | | |
| Répondre aux constats, mettre à jour les plans d'action, déposer des documents | | | | | | ✔ | |
| Rouvrir un dossier archivé | ✔ (motif obligatoire) | | | | | | |

Les rôles d'entité continuent de régir l'accès aux données comptables. Une mission d'audit financier donne en plus à ses membres la **lecture** des balances, des écritures et des états de l'entité et de l'exercice audités, pendant la durée de la mission. Cet accès est accordé par `authz.audits_company` (migration 0008), en lecture seule sur les exercices, les imports et les balances ; `authz.can_access_company` n'est pas modifié.

## 4. Traçabilité
Chaque action d'un module d'audit écrit dans `audit_logs` (événements `engagement.*`, `workpaper.*`, `signoff.*`, `evidence.*`, `finding.*`, `ai.suggestion.*`). Les signatures portent l'empreinte du contenu signé. Les éléments probants portent leur empreinte et leur origine. Chaque suggestion IA garde le lien vers le message et le contexte qui l'ont produite.
