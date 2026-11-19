# KOFINEX — Architecture logicielle

Plateforme SaaS multi-tenant de comptabilité (**SYSCOHADA révisé**, **SYSCEBNL**), d'analyse
financière, de contrôle de gestion, d'**audit financier et comptable, d'audit interne et de
contrôle interne**, avec IA et reporting.

Documents associés : `CDC_FONCTIONNEL.md`, `CDC_TECHNIQUE.md`, `MODULES.md` (découpage,
dépendances, permissions), `MODELE_DONNEES.md`, `ROADMAP.md`, `SECURITY.md`.

---

## 1. Principes directeurs

| Principe | Application concrète |
|---|---|
| **Les calculs ne sont jamais faits par l'IA** | Tous les indicateurs sont calculés en Python avec `decimal.Decimal` (précision 28, arrondi `ROUND_HALF_EVEN` configurable par formule). L'IA reçoit uniquement des indicateurs déjà calculés, sous forme JSON structuré, avec leur identifiant de formule et sa version. |
| **Aucune règle comptable inventée** | Les référentiels (plans de comptes, tables de passage balance → états financiers, formules) sont des **données versionnées** chargées en base, pas du code en dur. Chaque version porte sa source (Acte uniforme OHADA, date d'entrée en vigueur). Tant qu'une version n'est pas validée (`status = 'published'`), elle ne peut pas être utilisée en production. |
| **Traçabilité de bout en bout** | Document source (conservé intact, hash SHA-256) → job d'import → lignes de balance → état financier → indicateur (formule + version + entrées) → analyse IA (prompt, modèle, réponse) → rapport. |
| **Isolation multi-tenant en profondeur** | 3 couches : (1) contrôles de permission dans FastAPI, (2) `organization_id` sur toutes les tables métier + RLS Supabase, (3) Storage segmenté par `organization_id/`. Le frontend n'est jamais une barrière de sécurité. |
| **Méthodes et normes en données** | Les méthodologies d'audit et les cadres de contrôle interne suivent le même cycle de version que les référentiels comptables (`methodology_versions`). Une mission fige la version utilisée. |
| **L'IA assiste, l'humain conclut** | Signatures, éléments probants et validations exigent un utilisateur humain membre de la mission (RLS + API). Les propositions de l'IA passent par `ai_suggestions` et restent en brouillon tant qu'elles ne sont pas acceptées. |
| **Données sources intactes** | La balance validée n'est jamais modifiée : balance et états ajustés par l'audit sont calculés (balance + ajustements acceptés). |
| **Pas de simulation** | Pas de bouton sans action, pas de connecteur simulé. Un connecteur absent est affiché « non disponible ». Les données de démonstration sont dans une organisation marquée `is_demo = true` et signalées dans l'interface. |

---

## 2. Vue d'ensemble

```
                    ┌───────────────────────────────┐
                    │  Next.js 15 (App Router)      │   futur : React Native
                    │  React, TS, Tailwind, shadcn  │   (consomme la même API)
                    └──────────────┬────────────────┘
                     JWT Supabase  │  HTTPS / REST JSON (OpenAPI)
                    ┌──────────────▼────────────────┐
                    │  API FastAPI  (/api/v1)       │
                    │  auth · tenant · permissions  │
                    ├───────────────────────────────┤
                    │ engines/ (Python pur, testés) │
                    │  importing   accounting       │
                    │  financial   management       │
                    │  audit/ (socle, financial,    │
                    │   internal, control,          │
                    │   sampling, analytics)        │
                    │  ai          reporting        │
                    └───┬──────────────┬────────────┘
                        │              │ tâches longues
              ┌─────────▼───┐   ┌──────▼──────┐   ┌──────────────────┐
              │ PostgreSQL  │   │ Redis       │◄──┤ Workers Celery   │
              │ (Supabase)  │   │ broker/cache│   │ import, OCR,     │
              │ + RLS       │   └─────────────┘   │ calculs, rapports│
              └─────────────┘                     └────────┬─────────┘
              ┌─────────────┐                              │
              │ Supabase    │◄─────────────────────────────┘
              │ Auth/Storage│   documents originaux, éléments probants,
              └─────────────┘   rapports générés (buckets privés)
```

### Séparation des responsabilités

- **`frontend/`** : affichage, saisie, appels API. Utilise Supabase Auth uniquement pour obtenir le JWT. N'accède **pas** directement aux tables métier (sauf lecture RLS éventuelle) : toute écriture passe par l'API.
- **`backend/app/api`** : couche HTTP (validation Pydantic, permissions, pagination).
- **`backend/app/services`** : orchestration (transactions, audit, déclenchement de tâches).
- **`backend/app/engines`** : moteurs métier **sans dépendance HTTP ni ORM** (fonctions pures sur des dataclasses) → testables unitairement, réutilisables par les workers.
- **`backend/app/workers`** : tâches Celery (import, OCR, calcul, génération de rapports).

---

## 3. Arborescence

```
kofinex/
├── CLAUDE.md, PROJECT_STATUS.md, README.md, Makefile, docker-compose.yml, .env.example
├── .github/workflows/ci.yml     # lint, migrations, tests SQL/API, build frontend
├── supabase/config.toml
├── docs/                        # CDC fonctionnel et technique, architecture, modules, modèle
│                                # de données, feuille de route, sécurité, référentiels, moteur
├── referentiels/                # fichiers de chargement sourcés (SYSCOHADA, SYSCEBNL) + outils
│                                # futur : methodologies/ (audit, contrôle interne)
├── backend/
│   ├── alembic/versions/        # 0001…0013 (une révision = un fichier sql/)
│   ├── sql/                     # schéma, RLS, Storage, référentiels/imports, moteur financier
│   ├── app/
│   │   ├── core/ db/ models/ schemas/ services/ workers/
│   │   ├── api/v1/              # me, organizations, companies, fiscal_years, frameworks,
│   │   │                        # imports, analysis, management, engagements, financial_audit,
│   │   │                        # internal_audit, ledger, internal_control, ai, reporting | à venir : admin
│   │   ├── engines/
│   │   │   ├── importing/ accounting/ financial/         # livrés
│   │   │   ├── management/                               # lot 5
│   │   │   ├── audit/  methodology, workflow, sampling,  # lot 6
│   │   │   │           analytics, financial (7), internal (8), control (9)
│   │   │   ├── ai/ reporting/                            # lots 10, 11
│   │   └── connectors/                                   # lot 12
│   └── tests/ engines/ sql/ integration/
└── frontend/
    ├── app/(auth)/ app/(app)/   # organizations, companies, referentiels, formules, profile
    │                            # missions, plan-audit, cartographie, grand-livre, controle-interne, assistant, rapports
    ├── components/ui            # design system (lot 2)
    └── lib/                     # client API typé, types, formatage
```

---

## 4. Modèle multi-tenant

```
organization (cabinet, groupe, entreprise individuelle)
 ├── organization_members (role : owner | admin | member | viewer)
 ├── subscriptions / payments
 └── companies (entités analysées — clients du cabinet ou filiales)
      ├── company_members (droits fins : accountant | controller | analyst | auditor | viewer)
      ├── fiscal_years → trial_balance_entries → financial_statements → indicators
      ├── ledger_entries (grand livre, lot 3) · processes / risks (registre partagé, lot 6)
      ├── budgets, cost_centers, documents, rapports…
      └── engagements (missions d'audit, audit interne, évaluation du contrôle interne)
           └── engagement_members (partner | manager | in_charge | staff | quality_reviewer
                                   | auditee | observer) → dossier de mission cloisonné
```

**Règle d'accès à une entreprise** : un utilisateur y accède s'il est `owner`/`admin` de
l'organisation, **ou** s'il figure dans `company_members`. Les `member` d'une organisation
ne voient pas automatiquement toutes les entreprises (indispensable pour un cabinet qui
gère des clients confidentiels).

### Matrice des permissions (organisation et entité)

| Action | owner | admin | member | viewer |
|---|---|---|---|---|
| Modifier l'organisation | ✔ | ✔ | | |
| Gérer membres / rôles | ✔ | ✔ (pas owner) | | |
| Créer une entreprise | ✔ | ✔ | | |
| Gérer abonnement | ✔ | | | |

| Action (sur une entreprise) | accountant | controller | analyst | auditor | viewer |
|---|---|---|---|---|---|
| Lire données & analyses | ✔ | ✔ | ✔ | ✔ | ✔ |
| Importer / corriger balances | ✔ | | | | |
| Clôturer / rouvrir un exercice | ✔ | | | | |
| Budgets, centres de coûts | ✔ | ✔ | | | |
| Lancer analyses / IA / rapports | ✔ | ✔ | ✔ | | |
| Consulter le journal d'audit | ✔ | | | ✔ | |

Les owners/admins de l'organisation ont implicitement tous les droits sur ses entreprises.

**Troisième niveau : la mission d'audit.** Rôles `partner`, `manager`, `in_charge`, `staff`,
`quality_reviewer`, `auditee`, `observer`. L'accès au dossier d'une mission est réservé à ses
membres (y compris pour les administrateurs de l'organisation, qui doivent s'y ajouter de façon
tracée). Matrice complète : `MODULES.md` § 3.

---

## 5. Moteurs métier

Modules d'audit, de contrôle interne et dépendances entre modules : voir `MODULES.md`.


### 5.1 Moteur comptable (`engines/accounting`)
- Référentiel = `accounting_frameworks` (SYSCOHADA_REV, SYSCEBNL) × `framework_versions`.
- `chart_of_accounts` : plan de comptes par version.
- `account_mappings` : règles de passage **préfixe de compte → rubrique d'état financier**,
  avec sens (débit/crédit/solde), signe, et priorité. Moteurs distincts par référentiel
  (les rubriques du SYSCEBNL — fonds associatifs, ressources affectées… — diffèrent).
- Contrôles : balance équilibrée, total actif = total passif, résultat bilan = résultat CR.

### 5.2 Moteur financier (`engines/financial`)
- `financial_formulas` : bibliothèque versionnée (code, version, expression sur des
  rubriques/indicateurs, convention, unité, politique en cas de division par zéro).
- Évaluateur **sans `eval()`** : arbre syntaxique restreint (+, −, ×, ÷, références).
- Chaque résultat stocke : valeur `NUMERIC(20,4)`, formule+version, valeurs d'entrée,
  statut (`ok`, `missing_input`, `division_by_zero`, `not_applicable`).
- Indicateurs : SIG (MC, VA, EBE, RE, RAO, RHAO, RN), CAF (méthode additive et soustractive,
  contrôlées l'une par l'autre), FR, BFR (exploitation / hors exploitation), TN
  (avec contrôle FR − BFR = TN), ratios de liquidité, autonomie, endettement, ROE, ROA,
  marges, rotation des stocks, DSO/DPO.

### 5.3 Audit (`engines/audit`)
- `methodology` : validation et lecture des méthodologies versionnées (cycles, assertions, grilles,
  options de seuil, règles de taille d'échantillon, programmes types).
- `workflow` : machine d'états commune (feuilles, procédures, tests, constats, plans d'action,
  mission) et règles de signature ; doublée de *triggers* en base.
- `sampling` : échantillonnage aléatoire, systématique, par unités monétaires ; graine stockée.
- `analytics` : tests déterministes sur les écritures (doublons, séquences, dates, montants ronds,
  distribution des premiers chiffres).
- `financial` : seuils, cycles × assertions, anomalies, balance ajustée (réutilise `financial`).
- `internal`, `control` : univers et programme annuel ; matrices risques-contrôles, tests, évaluation.

### 5.4 IA (`engines/ai`)
- Entrée : JSON des indicateurs calculés + alertes + métadonnées (référentiel, exercice) ; pour
  l'audit, objets de la mission autorisés pour l'utilisateur.
- Sorties d'audit : uniquement des **suggestions** (`ai_suggestions`) ou des brouillons marqués ;
  aucune signature, validation ni élément probant possible (interdits imposés en base).
- Prompt système : interdiction d'introduire un chiffre absent du contexte ; chaque chiffre
  cité doit référencer un `indicator_code`.
- **Validation post-réponse** : extraction des nombres de la réponse et rapprochement avec le
  contexte ; réponse rejetée/annotée si un nombre n'est pas traçable.
- Tout est stocké dans `ai_conversations` / `ai_messages` (modèle, tokens, contexte envoyé).

### 5.5 Reporting (`engines/reporting`)
- PDF (WeasyPrint/ReportLab), Excel (OpenPyXL, formules natives conservées), Word (python-docx).
- `report_templates` : sections, logo, couleurs ; rapports générés stockés dans Storage avec hash.

### 5.6 Connecteurs (`connectors/`)
- Interface `AccountingConnector` (`test_connection`, `list_companies`, `fetch_trial_balance`).
- **Odoo** : API XML-RPC/JSON-RPC documentée (`account.move.line`) → implémentable.
- **Sage** : dépend du produit (Sage 100 local = export fichier / ODBC ; Sage Business Cloud
  = API REST). On implémente d'abord l'**import de fichiers d'export** ; les API seront
  ajoutées produit par produit. Aucun connecteur n'est affiché comme « connecté » sans
  appel réel réussi.

---

## 6. Sécurité (résumé — détails dans SECURITY.md)

- JWT Supabase vérifié côté API (HS256 avec secret projet, ou JWKS ES256/RS256),
  `aud = authenticated`, expiration contrôlée.
- RLS activé sur **toutes** les tables du schéma `public`. Le backend se connecte avec un
  rôle de service mais applique ses propres contrôles ; le frontend, s'il lit en direct,
  est contraint par RLS.
- Fichiers : liste blanche d'extensions + vérification des *magic bytes*, taille max,
  hash SHA-256, stockage privé, URL signées courtes.
- `audit_logs` : append-only (pas de policy UPDATE/DELETE), alimenté par le service d'audit.
- Secrets uniquement en variables d'environnement ; tokens d'intégration chiffrés (Fernet,
  clé `INTEGRATIONS_ENCRYPTION_KEY`).

---

## 7. Feuille de route

12 lots, état et ordre recommandé : voir `ROADMAP.md` ; avancement : `PROJECT_STATUS.md`.
