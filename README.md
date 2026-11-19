# KOFINEX

Plateforme SaaS de comptabilité (**SYSCOHADA révisé**, **SYSCEBNL**), d'analyse financière, de
contrôle de gestion, d'audit financier et comptable, d'audit interne et de contrôle interne, avec IA
et reporting. (Nom technique du code : `kofinex`.)

- État du projet : [`PROJECT_STATUS.md`](PROJECT_STATUS.md) — règles permanentes : [`CLAUDE.md`](CLAUDE.md)
- Cahiers des charges : [`docs/CDC_FONCTIONNEL.md`](docs/CDC_FONCTIONNEL.md), [`docs/CDC_TECHNIQUE.md`](docs/CDC_TECHNIQUE.md)
- Architecture : [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md), [`docs/MODULES.md`](docs/MODULES.md), [`docs/MODELE_DONNEES.md`](docs/MODELE_DONNEES.md)
- Feuille de route (12 lots) : [`docs/ROADMAP.md`](docs/ROADMAP.md) — sécurité : [`docs/SECURITY.md`](docs/SECURITY.md)

## État actuel — lots 1 (fondations), 2 (design system), 3 (comptabilité et import), 4 (analyse financière) et 5 (contrôle de gestion) livrés

Contrôle de gestion : budgets, réalisations, écarts, coûts complets, marges, seuil de rentabilité, tableau de bord —
[`docs/CONTROLE_GESTION.md`](docs/CONTROLE_GESTION.md).

Analyse financière : états financiers, SIG, CAF, FR/BFR/TN, ratios, comparaisons pluriannuelles —
[`docs/MOTEUR_FINANCIER.md`](docs/MOTEUR_FINANCIER.md).

Phase 2 : référentiels versionnés, importation Excel/CSV/PDF avec OCR, contrôles de cohérence,
consultation des balances — détail dans [`docs/REFERENTIELS_ET_IMPORTS.md`](docs/REFERENTIELS_ET_IMPORTS.md).

### Phase 1

| Domaine | Contenu |
|---|---|
| Base de données | 34 tables (les 33 demandées + `generated_reports`), UUID, clés étrangères composites anti-fuite inter-tenant, contraintes métier, index, triggers d'audit, RLS sur toutes les tables |
| Authentification | Supabase Auth (mot de passe, lien magique, invitation), JWT vérifié par l'API |
| Multi-tenant | Organisations, rôles d'organisation, attribution des entreprises par membre, rôles d'entreprise |
| API | `/me`, `/organizations`, membres, entreprises, accès par entreprise, exercices (création, clôture, réouverture motivée), journal d'audit, référentiels |
| Frontend | Connexion, inscription, mot de passe oublié / réinitialisation, profil, organisations (création, paramètres, suppression), entreprises, membres, exercices, accès, journal d'audit |
| Storage | Buckets privés `financial-documents`, `reports`, `branding` ; accès par entreprise, originaux immuables |
| Tests | 35 tests unitaires Python, 39 scénarios RLS + 12 scénarios Storage en SQL, 12 tests d'intégration API (parcours complet), CI GitHub Actions |

Les modules suivants (référentiels détaillés, import, moteurs comptable et financier, budgets, IA,
rapports, abonnements, connecteurs) sont développés dans l'ordre de la feuille de route. Aucun écran
ni bouton n'est affiché pour un module non encore développé.

## Démarrage local

Prérequis : Docker, Node 22, Python 3.12, `psql`, et le [CLI Supabase](https://supabase.com/docs/guides/cli) (recommandé).

```bash
make setup          # dépendances backend + frontend, création de .env
make db-supabase    # pile Supabase locale (Auth, Storage, Studio, mails de test) + migrations
#   ou : make db-docker   (PostgreSQL seul + shim Supabase, sans Auth réelle)
# reporter dans .env les valeurs de `supabase status` (API URL, anon key, service_role key, JWT secret)
make dev-api        # http://localhost:8000/api/v1/docs
make dev-web        # http://localhost:3000
```

Les e-mails (confirmation, invitation, réinitialisation) de la pile locale arrivent dans Inbucket :
http://localhost:54324.

> Le shim `backend/sql/local/00_supabase_shim.sql` n'émule que le schéma `auth`, `auth.uid()`, les rôles et la
> structure de `storage` pour les tests. **Ne jamais** l'exécuter sur un projet Supabase.

### Déploiement sur Supabase

1. `DATABASE_URL` = chaîne de connexion « session » du projet (port 5432).
2. `alembic upgrade head` — le schéma `auth`, `auth.uid()` et les rôles existent déjà.
3. Auth > URL Configuration : ajouter `https://<domaine>/auth/callback` aux URL de redirection.
4. Les buckets Storage privés et leurs policies sont créés par la migration 0003.
5. Reporter les réglages Auth de `supabase/config.toml` (mot de passe ≥ 10 caractères avec minuscule, majuscule
   et chiffre ; confirmation e-mail ; rotation des refresh tokens ; MFA TOTP) dans le tableau de bord.

### Données de démonstration

```bash
psql "$DATABASE_URL" -v demo_user="'<uuid utilisateur>'" -f backend/scripts/seed_demo.sql
```
Organisation et entreprises préfixées « [DÉMO] », marquées `is_demo = true` ; l'interface affiche un bandeau.

## Tests

```bash
make test-unit          # tests unitaires
make test-sql           # base de test neuve + migrations + tests RLS et Storage
make test-integration   # API de bout en bout sur la base de test
```
