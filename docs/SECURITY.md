# Sécurité — KOFINEX

## 1. Défense en profondeur

| Couche | Mécanisme | Fichier |
|---|---|---|
| Transport | HTTPS obligatoire (terminaison TLS au load balancer), en-têtes `nosniff`, `DENY`, `no-store` | `app/main.py` |
| Authentification | JWT Supabase vérifié : signature, `exp`, `aud`, `iss`, `role=authenticated`, `alg` en liste blanche (refus de `none` et des confusions d'algorithme) | `app/core/security.py` |
| Autorisation API | Contexte organisation / entreprise résolu à chaque requête ; 404 pour une ressource d'un autre tenant (pas de fuite d'existence) ; 403 explicite pour un rôle insuffisant | `app/api/deps.py`, `app/core/permissions.py` |
| Autorisation base | **Toutes** les requêtes de l'API s'exécutent sous `SET LOCAL ROLE authenticated` avec les claims de l'utilisateur → les policies RLS s'appliquent aussi au backend | `app/db/session.py`, `sql/0002_rls_policies.sql` |
| Intégrité inter-tenant | Clés étrangères composites `(company_id, organization_id)` : impossible, même pour un superutilisateur, de rattacher une donnée à l'entreprise d'un autre tenant | `sql/0001_core_schema.sql` |
| Privilèges colonne | `profiles.is_platform_admin` non modifiable par l'utilisateur ; `integrations.encrypted_credentials` illisible côté client | `sql/0002_rls_policies.sql` |
| Journalisation | Triggers d'audit sur les tables sensibles + événements métier ; journal en ajout seul (trigger bloquant UPDATE/DELETE, y compris pour le propriétaire de la table) ; secrets exclus du journal | `sql/0001_core_schema.sql`, `app/services/audit.py` |
| Gardes métier | Exercice clôturé figé (balances, imports, états) ; dernier propriétaire non supprimable ; chevauchement d'exercices interdit ; intégration « active » impossible sans vérification réelle | `sql/0001`, `sql/0002` |

## 2. Session `service_session`

Elle contourne RLS. Usages autorisés (à lister ici à chaque ajout) :

1. Recherche d'un profil par e-mail exact lors d'une invitation (`organizations.invite_member`).

Usages prévus : webhooks de paiement, workers système (après vérification d'appartenance du job).

**Session `anon_session`** (lot 12A) : visiteur non connecté, rôle `anon`, **soumise à RLS**. Seul usage : le catalogue public (`GET /billing/catalog`), qui ne voit que les versions publiées. Elle est préférée à la session de service, qui contournerait RLS.

**Fonctions `SECURITY DEFINER` du lot 12A** (migration 0018) : elles contrôlent elles-mêmes l'appelant. L'essai, la demande de résiliation et son retrait sont réservés au propriétaire ; l'état de l'abonnement et la présence de données sont lisibles par les membres, les usages et la vérification d'un code promotionnel par le propriétaire et les administrateurs. Le rôle `authenticated` n'a aucun droit d'écriture sur `subscriptions` ni `subscription_items`.

## 3. Fichiers

Déjà en place (migration 0003) : buckets **privés** `financial-documents` (50 Mo, xlsx/xls/csv/pdf),
`reports` (100 Mo, pdf/xlsx/docx), `branding` (2 Mo, images) ; chemin imposé
`{organization_id}/{company_id}/{fichier}` dont la cohérence organisation ↔ entreprise est vérifiée ;
lecture selon l'accès à l'entreprise, dépôt selon le rôle ; aucune modification ni suppression côté client.

Avec le module d'importation (phase 3) :
- Extensions autorisées : `ALLOWED_UPLOAD_EXTENSIONS` ; vérification des *magic bytes* (pas seulement l'extension).
- Taille maximale : `MAX_UPLOAD_SIZE_MB`.
- Hash SHA-256 conservé ; le fichier original n'est jamais modifié.
- Téléchargement par URL signée de courte durée (≤ 5 min), journalisé.
- Classeurs Excel ouverts en lecture seule, sans évaluation de macros ni de liens externes.

## 4. Secrets

- Uniquement en variables d'environnement ; `SUPABASE_SERVICE_ROLE_KEY` jamais exposée au navigateur
  (pas de préfixe `NEXT_PUBLIC_`).
- Identifiants d'intégrations chiffrés par Fernet (`INTEGRATIONS_ENCRYPTION_KEY`), rotation documentée.

## 4 bis. Intelligence artificielle
- La clé du fournisseur (`AI_API_KEY`) est un secret serveur : jamais renvoyée par l'API, jamais journalisée.
- Les données transmises au fournisseur sont des valeurs calculées, lues avec les droits de l'utilisateur. L'organisation active chaque usage en acceptant cette transmission.
- Les sorties du modèle ne peuvent écrire aucune donnée métier : acteur IA bloqué par un déclencheur sur toutes les tables métier et le stockage (`docs/IA.md` §5).

## 5. Sauvegardes

- Supabase : sauvegardes quotidiennes + PITR (plan Pro ou supérieur) à activer.
- Storage : réplication / export périodique du bucket `financial-documents`.
- Test de restauration trimestriel (procédure à consigner dans `docs/RUNBOOK.md`).

## 6. Tests de sécurité

- `tests/sql/test_rls.sql` (39 scénarios) : isolation entre cabinets, attribution par entreprise, escalade de
  privilèges, références croisées, `INSERT … RETURNING`, immutabilité de l'audit, exercices clôturés…
- `tests/sql/test_storage.sql` (12 scénarios) : chemins, cohérence tenant, immutabilité des originaux.
- `tests/sql/test_ai.sql` (60 scénarios) : interdits de l'IA, provenance, décisions humaines, isolation.
- `tests/sql/test_reporting.sql` (41 scénarios) : documents figés, sources validées, accès par entreprise, contrôle interne ou mission.
- `tests/integration/` : parcours API complets avec de vrais JWT et RLS active.
Tous exécutés par la CI (`.github/workflows/ci.yml`) à chaque push.
