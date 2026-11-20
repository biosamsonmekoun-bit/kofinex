# KOFINEX — Lot 12 : architecture commerciale et fonctionnelle SaaS (conception)

> **Statut : conception (18 novembre 2026) ; décisions commerciales du § 16 arrêtées le 20 novembre 2026**, elles priment sur les propositions des paragraphes précédents. Numéros de migration décalés le 19 novembre 2026 (0016 : FEC DGI Bénin ; 0017 : types d'états). **Étape 12A livrée le 20 novembre 2026** (migration 0018, § 14). Les étapes 12B à 12E ne commencent que sur demande explicite, après les vérifications préalables du § 16.

Conventions :
- **Constaté** : vérifié dans le code, les migrations SQL ou une documentation officielle (sources au § 17).
- **Proposé** : choix de conception soumis à validation.
- **À confirmer** : point qui n'a pas pu être vérifié ; il ne doit pas être présumé.

Les prix, les quotas, les taux de taxe et les durées commerciales ne sont **pas** fixés ici. Ce sont des données saisies par l'administrateur de la plateforme. Ce document ne contient aucun montant.

---

## 1. État réel du socle SaaS existant (constaté)

| Élément | Où | État réel |
|---|---|---|
| Tables `organizations`, `organization_members`, `subscriptions`, `payments`, `integrations`, `audit_logs` | `backend/sql/0001_core_schema.sql`, RLS dans `0002_rls_policies.sql` | Créées depuis le lot 1. |
| Modèles ORM, services, routes API pour `subscriptions`, `payments`, `integrations` | `backend/app/` | **Inexistants.** Aucun fichier Python ne lit ni n'écrit ces trois tables. Aucune ligne n'est donc produite par l'application. |
| Rôle d'administrateur de plateforme | `profiles.is_platform_admin`, `authz.is_platform_admin()`, `require_platform_admin` (`api/v1/frameworks.py`) | Booléen unique, utilisé pour les référentiels et les méthodologies. Pas de rôles différenciés (support, finance). |
| Organisations, membres, entreprises | `api/v1/organizations.py`, `api/v1/companies.py` | Création, invitation, rôles, archivage : livrés. **Aucune limite** de nombre (utilisateurs, entreprises, organisations par utilisateur). |
| Journal d'audit | `audit_logs`, déclencheur `audit_row_change()`, `services/audit.py` | Ajout seul, secrets exclus. Déclencheur posé sur `organizations`, `organization_members`, `companies`, `integrations`, `subscriptions`… mais **pas sur `payments`**. |
| Chiffrement des identifiants | `INTEGRATIONS_ENCRYPTION_KEY` (Fernet), colonne `integrations.encrypted_credentials` illisible côté client | Prévu, non utilisé. |
| Traitements asynchrones | Celery + Redis (`core/config.py`, `docker-compose.yml`) | Utilisés pour les imports ; réutilisables pour les relances et rapprochements. |
| Comptage possible des usages | `organization_members`, `companies`, `engagements` (missions), `import_jobs`, `generated_reports`, `ai_messages.input_tokens/output_tokens`, objets du stockage | Toutes les grandeurs de quota sont **déjà mesurables** à partir des tables existantes. |
| Interface | `frontend/app/page.tsx` | Page publique : « Essai gratuit 14 jours », « Paiement sécurisé via FedaPay », « La grille tarifaire (en FCFA) sera publiée prochainement ». Aucun écran d'abonnement ni d'administration. **FedaPay n'est pas une passerelle retenue** : ce texte devra être corrigé en 12A. |
| Documentation | `ROADMAP.md`, `MODULES.md` (`api/v1/{billing,admin,integrations}`, `connectors/`), `SECURITY.md` §2 (« usages prévus : webhooks de paiement »), §5 (sauvegardes) | Lot 12 « à faire ». |

**Constat de sécurité important.** Le frontend ne passe que par l'API, sans appel direct aux tables. Mais `0002_rls_policies.sql` accorde `SELECT, INSERT, UPDATE, DELETE` sur toutes les tables au rôle `authenticated`. Si l'API REST de Supabase (PostgREST) expose le schéma `public`, un utilisateur muni de son jeton peut insérer directement une entreprise ou un membre (dans la limite des RLS), **sans passer par un contrôle de quota fait seulement dans le backend**. Le backend lui-même s'exécute sous `SET LOCAL ROLE authenticated` : la base ne distingue donc pas un appel de l'API d'un appel direct.

Mesures proposées :
1. Retirer `public` des schémas exposés par l'API REST de Supabase (réglage du projet). C'est possible puisque le frontend ne l'utilise pas. Ce réglage est à vérifier sur le projet réel.
2. Doubler les quotas des ressources comptées par une garde en base (§ 8.4).

---

## 2. Analyse des tables existantes et de leurs limites

### 2.1 `organizations` — client facturé (réutilisée)
- **Utile** : `country_code`, `default_currency` (XOF par défaut), `archived_at`, `is_demo`, RLS (modification par owner / admin, suppression par owner).
- **Limites** :
  - pas d'identité de facturation (raison sociale, identifiant fiscal, adresse, e-mail de facturation) ;
  - `default_currency` est la devise **comptable** de l'organisation, pas sa devise de **facturation** ;
  - pas d'état commercial (suspendue, résiliée) ;
  - n'importe quel utilisateur peut créer des organisations sans limite, d'où un risque d'essais gratuits multiples.
- **Décision proposée** : ne pas surcharger `organizations` (ses colonnes modifiables sont accordées une à une). Ajouter une table `billing_accounts` 1:1 (§ 10).

### 2.2 `organization_members` — sièges (réutilisée)
- **Utile** : rôles `owner` / `admin` / `member` / `viewer`, unicité, RLS (un admin ne crée pas d'owner).
- **Limites** : aucune notion de siège facturable. Le nombre de membres est la mesure du quota « utilisateurs ». Les invitations en attente comptent-elles ? Décision à prendre (§ 16).
- **Décision proposée** : aucune modification de structure. Le quota est lu par comptage, et une garde en base est ajoutée à l'insertion.

### 2.3 `subscriptions` — à compléter (ALTER, pas de doublon)
Colonnes actuelles : `plan_code` (texte libre), `status` ∈ {`trialing`, `active`, `past_due`, `canceled`, `expired`}, `seats`, `max_companies`, `provider`, `provider_customer_id`, `provider_subscription_id` (unique), `current_period_start/end`, `cancel_at`. Index unique : un seul abonnement « vivant » (`trialing`, `active`, `past_due`) par organisation. Déclencheur d'audit présent.

Écriture refusée au client (`REVOKE INSERT, UPDATE, DELETE`). Lecture réservée à owner / admin ; l'administrateur de plateforme n'a **pas** de politique de lecture.

| Limite | Conséquence | Correction proposée (migration 0018, sans réécrire 0001) |
|---|---|---|
| `plan_code` sans lien avec un catalogue | Prix et droits non traçables | `product_version_id` (FK vers la version d'offre souscrite, figée) ; `plan_code` conservé, renseigné pour lecture |
| Pas d'état `suspended` ni d'état « en attente du premier paiement » | Impossible de distinguer l'impayé, la suspension et une souscription non payée | Statuts ajoutés : `incomplete`, `suspended`. L'index « vivant » est recréé pour inclure `incomplete` et `suspended` |
| Pas de périodicité, devise, fin d'essai, fin de période de grâce, motif de résiliation | Renouvellement et relances impossibles | `billing_interval` (`month` / `year`), `currency` (`XOF`, `XAF`, `GNF`, `KMF`, `CDF` : § 16), `trial_end`, `grace_until`, `suspended_at`, `canceled_at`, `cancel_reason`, `renewal_mode` (`manual` / `automatic`) |
| `seats`, `max_companies` codés en colonnes | Les quotas ne couvrent ni missions, stockage, imports, rapports ou IA | Conservés (aucune suppression) mais **dérivés** des droits (§ 8). La source unique devient la version d'offre et les options |
| `provider_*` : un abonnement lié à **un** prestataire | Incompatible avec plusieurs passerelles et avec le mobile money (sans prélèvement récurrent documenté, § 6) | Le moteur d'abonnement est **interne à KOFINEX**. Les passerelles n'encaissent que des paiements de commandes. Les colonnes restent, nullables, et ne sont plus utilisées comme source d'état |

Les tables sont vides aujourd'hui (aucun code ne les alimente). La migration 0018 vérifiera cette hypothèse et s'arrêtera avec un message explicite si des lignes existent.

### 2.4 `payments` — à compléter (ALTER)
- **Utile** : `numeric(14,2)`, `currency char(3)`, unicité `(provider, provider_payment_id)`, `raw_event`, lecture **owner seulement**.
- **Limites** :
  - pas de lien vers une commande ni une facture ;
  - statuts insuffisants (`pending`, `succeeded`, `failed`, `refunded`) : il manque `expired`, `canceled`, `partially_refunded` ;
  - pas de montant net ni de frais ;
  - pas de trace de la vérification serveur (date, moyen) ;
  - pas de clé d'idempotence ;
  - **pas de déclencheur d'audit** ;
  - un seul `raw_event`, alors qu'un paiement reçoit plusieurs notifications ;
  - XOF et XAF n'ont pas de décimales (code ISO à 0 décimale ; Stripe les traite en « zero-decimal »), sans contrainte qui l'impose.
- **Corrections proposées** :
  - colonnes `order_id`, `invoice_id`, `idempotency_key` (unique), `checkout_url`, `expires_at`, `net_amount`, `fee_amount`, `refunded_amount`, `failure_code`, `failure_message`, `verified_at`, `verified_by` (`api_verify` / `webhook_then_verify` / `reconciliation`), `method` (`mobile_money` / `card` / `other`), `network`, `country_code` ;
  - statuts étendus ;
  - contrainte : nombre de décimales conforme à la devise (§ 16 : 0 pour XOF, XAF, GNF, KMF ; 2 pour CDF) ;
  - déclencheur d'audit ;
  - politique de lecture pour l'administrateur de plateforme.
- `raw_event` est conservé ; les notifications passent dans `payment_webhook_events`.

### 2.5 `integrations` — connecteurs comptables (réutilisée telle quelle)
- **Utile** :
  - fournisseurs `odoo`, `sage_business_cloud`, `sage_100_export`, `quickbooks`, `file_export`, `other` ;
  - statut `active` impossible sans `last_verified_at` (garde en base) ;
  - identifiants chiffrés illisibles côté client ; audit qui exclut les secrets ; RLS owner / admin.
- **Limites** : un seul `last_error` et `last_sync_at` ; aucun historique des synchronisations.
- **Décision** : ne **pas** y ranger les passerelles de paiement. `integrations` appartient à une organisation cliente, alors que les comptes marchands appartiennent à la plateforme KOFINEX. Ajout de `integration_runs` en 12C.

### 2.6 `audit_logs` — réutilisée
- **Utile** : ajout seul, imposé par déclencheur.
- **Limite** : la politique d'insertion exige `user_id = auth.uid()` **et** l'appartenance à l'organisation. Une action de l'administrateur de plateforme sur une organisation dont il n'est pas membre serait refusée, et un webhook n'a pas d'utilisateur.
- **Proposé** :
  - les écritures système (webhooks, tâches planifiées) passent par la session de service. C'est un usage à ajouter à la liste de `SECURITY.md` §2 ;
  - une politique d'insertion ajoutée pour `authz.is_platform_admin()` ;
  - actions nommées `billing.*`, `subscription.*`, `payment.*`, `admin.*`, `support.*`, `integration.*`.

---

## 3. Catalogue fonctionnel des offres et modules

### 3.1 Modules commercialisables : correspondance avec les modules livrés (constaté)
| Clé de droit (proposée) | Module livré | Routes protégées |
|---|---|---|
| `core` | Organisations, entités, exercices, membres, tableau de bord, référentiels publiés | toujours inclus |
| `accounting_import` | Import balances / grand livre, contrôles (lot 3) | `api/v1/imports`, `ledger` |
| `native_accounting` | Comptabilité générale native (lot 3B, A et B) | `api/v1/accounting` |
| `financial_analysis` | États, SIG, ratios, formules (lot 4) | `api/v1/analysis` |
| `management_control` | Contrôle de gestion et pilotage (lots 5, 5 bis) | `api/v1/management`, `steering` |
| `audit_core` | Socle d'audit : missions, programmes, preuves (lot 6) | `api/v1/engagements` |
| `financial_audit` | Audit financier (lot 7) | `api/v1/financial_audit` |
| `internal_audit` | Audit interne (lot 8) | `api/v1/internal_audit` |
| `internal_control` | Contrôle interne (lot 9) | `api/v1/internal_control` |
| `ai` | Assistant et suggestions IA (lot 10) ; reste soumis à l'activation par l'organisation | `api/v1/ai` |
| `reporting` | Rapports PDF / Excel / Word (lot 11) | `api/v1/reporting` |
| `connectors` | Connecteurs Odoo / Sage (12C) | `api/v1/integrations` |

Les modules non livrés (Achats, Ventes, Trésorerie, Paie, Immobilisations, Stocks, Fiscalité) **ne figurent pas** au catalogue tant qu'ils n'existent pas : pas de module vendu sans fonctionnalité.

Dépendances à imposer dans le catalogue :
- `financial_audit`, `internal_audit` et `internal_control` exigent `audit_core` ;
- `management_control` (pilotage) exige une source de données : `accounting_import` ou `native_accounting`.

### 3.2 Les trois formules (structure proposée, contenu à valider)
| | ESSENTIEL | PROFESSIONNEL | ENTREPRISE |
|---|---|---|---|
| Cible (proposée) | petite structure, comptabilité et analyse | cabinet / PME : gestion et audit | groupe, cabinet multi-entités |
| Modules inclus (proposition) | `core`, `accounting_import`, `native_accounting`, `financial_analysis`, `reporting` | ESSENTIEL + `management_control`, `audit_core`, `financial_audit` | PROFESSIONNEL + `internal_audit`, `internal_control`, `connectors` |
| Options payantes | les modules non inclus, `ai`, packs de quotas | `internal_audit`, `internal_control`, `ai`, `connectors`, packs | `ai`, packs |
| Quotas | saisis par l'administrateur (aucune valeur fixée) | idem | idem, ou « sur devis » |

La répartition est une proposition commerciale, non une règle : elle se change par une nouvelle version d'offre, sans code.

### 3.3 Quotas couverts (§ 8)
Utilisateurs, sociétés, modules, missions, stockage (Mo), imports par période, rapports générés par période, IA (jetons ou requêtes par période : unité à décider).

---

## 4. Modèle commercial cible

- **Produits versionnés** : une offre (ESSENTIEL…) ou une option a des **versions**. Une version publiée est **figée** (prix, modules, quotas, durée d'essai). Changer un prix crée une nouvelle version. Les abonnés restent sur leur version jusqu'à migration explicite, journalisée. C'est le même principe que les référentiels versionnés du projet.
- **Prix** : par version, périodicité (`month` / `year`) et devise (`XOF`, `XAF`, `GNF`, `KMF`, `CDF` : § 16), en `numeric` au nombre de décimales de la devise. L'affichage commercial écrit « FCFA » ; le stockage garde le code ISO. Aucune conversion XOF ↔ XAF n'est calculée : chaque devise a son prix saisi.
- **Zone de facturation** : déduite du pays de facturation (`billing_accounts.country_code`) : UEMOA → XOF, CEMAC → XAF. La correspondance pays → devise est une donnée publiée, pas un calcul. Guinée → GNF, Comores → KMF, RD Congo → CDF (§ 16). Hors OHADA : non commercialisé au lancement.
- **Options** : modules supplémentaires et packs de quotas, en quantité, avec la même périodicité que l'abonnement.
- **Promotions** :
  - code promotionnel ou remise attribuée par l'administrateur ;
  - pourcentage ou montant fixe (par devise) ;
  - portée : offre, option, périodicité ;
  - durée : une fois, N périodes, ou permanente ;
  - validité et nombre maximal d'utilisations ;
  - jamais de remise sur une taxe ;
  - chaque application est tracée sur la commande et la facture.
- **Essai** : durée portée par la version d'offre ; **30 jours sans moyen de paiement** (§ 16). Un seul essai par organisation **et** par identité de facturation (identifiant fiscal, e-mail du propriétaire), pour limiter les essais multiples.
- **Paiement** : à la commande (souscription, changement, option), puis à chaque renouvellement (§ 5.3).

---

## 5. Architecture des abonnements

### 5.1 États et transitions (moteur interne, source de vérité unique)
```
            ┌──────────── essai expiré sans paiement ───────────┐
            │                                                    ▼
(création) ─┼─> trialing ──paiement vérifié──> active        expired
            │                                   │  ▲
            └─> incomplete ─paiement vérifié────┘  │ paiement vérifié
                     │ commande expirée            │
                     ▼                    échéance non payée
                  expired                          ▼
                                     past_due (période de grâce)
                                           │ fin de grâce
                                           ▼
                                    suspended (lecture seule)
                                     │                │
                       paiement vérifié         délai écoulé ou demande
                                     ▼                ▼
                                   active          canceled
```
- **Activation** uniquement sur un paiement **vérifié côté serveur** (§ 6.4), jamais sur un retour navigateur. La page de retour affiche « paiement en cours de vérification » et interroge l'API KOFINEX, qui interroge le prestataire.
- **Résiliation** :
  - par l'owner : effet en fin de période (`cancel_at`), réversible jusque-là (réactivation) ;
  - par l'administrateur : immédiate ou en fin de période, avec motif obligatoire.
- **Suspension** :
  - **lecture seule** : consultation et export de toutes les données conservés ; création et modification refusées par le backend (§ 8.3) ;
  - aucune donnée supprimée ;
  - réactivation par paiement du solde dû.
- **Après résiliation** : durée de conservation puis suppression, à décider. Les données comptables peuvent être soumises à des obligations de conservation ; une validation juridique est requise. Un export complet doit être offert avant toute suppression.
- Chaque transition écrit dans `audit_logs` (`subscription.<transition>`) avec l'acteur (utilisateur, administrateur, système) et le motif.

### 5.2 Changement d'offre et options
- **Montée en gamme** : effet immédiat. Proposition : crédit au prorata du temps restant sur l'ancienne offre, imputé sur la nouvelle commande ; calcul en `Decimal`, arrondi à l'unité de la devise. Règle d'arrondi à valider.
- **Descente en gamme** : effet en fin de période. Elle est refusée si l'usage dépasse les nouveaux quotas (par exemple, trop de sociétés actives) : l'écran liste ce qu'il faut réduire. Les données ne sont jamais supprimées automatiquement.
- **Ajout d'une option** : immédiat, au prorata. **Retrait** : en fin de période.
- **Changement de périodicité** (mois ↔ an) : au renouvellement.
- Un aperçu chiffré (« devis ») est **calculé par le serveur** avant toute commande ; le navigateur ne calcule aucun montant.

### 5.3 Renouvellement
- **Mobile money** (SASPay, PayDunya) : la documentation consultée ne décrit **aucun mandat de prélèvement récurrent** (§ 6). Le renouvellement est donc **manuel** : une commande de renouvellement est émise N jours avant l'échéance ; des relances partent par e-mail et dans l'application ; le paiement se fait en un clic depuis la commande.
- **Carte** : Stripe est écarté (entité au Bénin, § 16) ; les cartes passent par SASPay, sans prélèvement récurrent documenté : renouvellement manuel, comme pour le mobile money.
- **Tâches planifiées** (Celery beat) :
  - émission des commandes de renouvellement ;
  - relances ;
  - bascules `active → past_due → suspended → canceled` aux dates prévues ;
  - expiration des commandes et des sessions de paiement ;
  - rapprochement.

  Toutes sont idempotentes : une même échéance ne produit qu'une commande (clé unique abonnement + période).

### 5.4 Impayés et période de grâce
La durée de grâce, le délai avant suspension, le délai avant résiliation et le calendrier des relances sont des paramètres de plateforme saisis par l'administrateur. Ils sont journalisés à chaque modification.

---

## 6. Architecture multi-passerelles

### 6.1 Principe : connecteurs indépendants derrière une interface commune
```
services/billing/payments.py ── PaymentConnector (interface)
   ├─ connectors/payments/saspay.py
   ├─ connectors/payments/paydunya.py
   └─ connectors/payments/stripe.py
Méthodes : capabilities() · create_checkout(order, attempt) · verify(payment) ·
           parse_webhook(headers, raw_body) · refund(payment, amount) [si supporté] · list_transactions(période) [si supporté]
```
- Chaque connecteur déclare ses **capacités vérifiées** : pays, devises, moyens, remboursement par API, récurrence, liste des transactions. Le routage ne propose que ce qui est déclaré **et** activé par l'administrateur pour la zone du client.
- Un connecteur n'écrit jamais l'état d'un abonnement. Il retourne un résultat de vérification normalisé : `{statut, montant, devise, référence, frais, net}`. Le service de facturation décide.
- Secrets : variables d'environnement par prestataire et par mode (`SASPAY_SECRET_KEY`, `SASPAY_WEBHOOK_SECRET`, `PAYDUNYA_MASTER_KEY` / `PRIVATE_KEY` / `TOKEN`, `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`), comme le reste des secrets du projet (`SECURITY.md` §4). La base ne contient que la configuration non secrète (`payment_providers`).

### 6.2 Étude des passerelles (documentation consultée le 18 novembre 2026)

**SASPay** (docs.saspay.me)
- **API** (constaté, documentation officielle) :
  - REST, URL de base `https://api.saspay.me/api/v1` ;
  - environnement de test séparé `https://sandbox-api.saspay.me/api/v1`, avec clés `sk_test_` (production : `sk_live_`) ;
  - authentification `Authorization: Bearer`, clé exclusivement côté serveur ;
  - enveloppe de réponse `success` / `data` / `error` ; limite de 300 requêtes par minute.
- **Idempotence** : en-tête `Idempotency-Key` (même clé et même corps : même réponse ; corps différent : 409).
- **Encaissement** :
  - session de checkout hébergée (`POST /checkout-sessions/`, page `pay.saspay.me/checkout/{slug}`) ;
  - paiement direct « softpay » (`POST /payments/softpay/`) ;
  - vérification `GET /payments/{id}/verify/` (renvoie notamment `status`, `net_amount`, `currency`) ;
  - statuts documentés dans le démarrage rapide : `PENDING`, `SUCCESS` ;
  - autres opérations : liens de paiement, retraits (payouts), wallet, transactions, confirmation OTP, relance d'un paiement échoué.
  - La documentation demande de toujours interroger le statut réel avant de considérer un paiement réussi.
- **Moyens** : mobile money (MTN Bénin en mode « push » ; Wave, Orange Money, Djamo et carte avec redirection), cartes, d'après la documentation et le site.
- **Pays** : liste d'une spécification tierce (afro.tools), à confirmer par l'appel officiel `GET /countries/` : BF, BJ, CD, CI, CM, GH, GN, KE, ML, MW, NE, NG, RW, SN, TG, TZ, UG, ZM.
- **XOF** : constaté (exemples officiels en XOF).
- **XAF : à confirmer.** Le Cameroun figure dans la liste tierce, mais aucune page officielle consultée ne montre de paiement en XAF. Gabon, Congo, Tchad, Centrafrique et Guinée équatoriale ne figurent pas dans cette liste.
- **Webhooks** : la page officielle n'a pas pu être lue directement. Selon la spécification tierce qui la résume, la signature est un HMAC-SHA256 hexadécimal :
  - en-tête `X-Webhook-Signature`, calculé sur `X-Webhook-Timestamp` + « . » + corps brut, avec le secret de signature (affiché une seule fois) ;
  - tolérance de 5 minutes ; 5 tentatives de livraison.

  **À confirmer** sur `docs.saspay.me/api-reference/webhooks` avant développement.
- **Remboursements** : **aucune API de remboursement** dans l'index officiel. Un remboursement passerait par un retrait (payout) ou hors plateforme.
- **Abonnements** : annoncés sur le site commercial (« plans, essais, prélèvements automatiques ») mais **absents de la référence API** consultée. On ne s'appuie pas dessus.
- **Points de vigilance** :
  - d'après le même relevé tiers, l'idempotence n'est pas prise en charge sur la création de session de checkout, la redirection après paiement par carte n'est pas fiable, le montant minimal est de 200 XOF, et la session aurait été traitée en production avec une clé de test sur l'hôte principal : utiliser l'hôte sandbox ;
  - la société est récente, et des sites d'évaluation tiers lui attribuent une confiance faible (domaine récent, titulaire masqué). Ces signaux ne prouvent rien mais justifient une **vérification préalable** : entité juridique, agrément ou partenaire régulé, contrat, délais de reversement.

**PayDunya** (developers.paydunya.com)
- **API** (constaté, documentation officielle) :
  - HTTP / JSON ; en-têtes `PAYDUNYA-MASTER-KEY`, `PAYDUNYA-PRIVATE-KEY`, `PAYDUNYA-TOKEN` ;
  - environnements `…/sandbox-api/v1/` et `…/api/v1/`.
- **Encaissement** :
  - facture de paiement hébergée : `POST checkout-invoice/create` (renvoie un jeton et l'URL de paiement) ;
  - vérification `GET checkout-invoice/confirm/{token}` ;
  - statuts `pending` (peut passer automatiquement à annulé après 24 heures si impayé), `completed`, `cancelled`, `failed` ;
  - paiement direct « SoftPay » par canal.
- **Canaux SoftPay documentés** :
  - Sénégal : Orange Money, Free Money, Expresso, Wave, Wizall, Djamo ;
  - Côte d'Ivoire : Orange, MTN, Moov, Wave, Djamo ;
  - Burkina Faso : Orange, Moov ;
  - Bénin : Moov, MTN, Celtiis ;
  - Togo : T-Money, Moov ;
  - Mali : Orange, Moov ;
  - Cameroun : MTN ;
  - carte bancaire.
- **XOF** : constaté sur les canaux UEMOA. **XAF : seul le canal MTN Cameroun** affiche XAF dans la documentation ; aucun autre canal CEMAC n'est documenté.
- **Point de vigilance** : la création de facture ne documente **aucun champ devise**.
- **Notification (IPN)** :
  - `POST` en `application/x-www-form-urlencoded` vers `callback_url`, contenu sous la clé `data` ;
  - authentification par un champ `hash` décrit comme le SHA-512 de la clé maître : **valeur statique, qui ne signe pas le contenu**.

  ⇒ l'IPN n'est qu'un **déclencheur** ; la décision repose toujours sur `confirm/{token}` (statut `completed`, montant identique à la commande).
- **Remboursements** : non documentés. **Abonnements** : non documentés. **Reversement** : `direct-pay/credit-account`, entre comptes PayDunya.

**Stripe** (docs.stripe.com)
- **Devises** (constaté) : XOF et XAF figurent parmi les devises de présentation et sont des devises « zero-decimal » (le montant API est le montant entier). La liste dépend toutefois du pays du compte Stripe, et XOF n'est pas accepté par American Express.
- **Disponibilité** (constaté sur stripe.com/global) : 51 pays et régions. En Afrique, seuls Côte d'Ivoire, Ghana, Kenya, Nigeria et Afrique du Sud sont listés, en « Extended network » (partenaire). **Sénégal, Cameroun, Bénin et Gabon ne sont pas listés.**

  ⇒ un compte Stripe n'est possible que si KOFINEX dispose d'une entité dans un pays éligible. Les fonds seraient alors reversés dans la devise de règlement de ce compte, avec conversion.
- **Capacités** (documentation officielle) :
  - Checkout Sessions ;
  - idempotence sur toutes les requêtes `POST` (clés conservées au moins 24 heures) ;
  - webhooks signés par l'en-tête `Stripe-Signature`, vérifié avec une tolérance d'horodatage par les bibliothèques officielles. Détail du calcul (HMAC-SHA256 de l'horodatage et du corps brut, 5 minutes) relevé dans des sources secondaires, à relire sur la page officielle des webhooks avant 12B ;
  - remboursements par API, Billing (abonnements) et moyens de paiement enregistrés sont des fonctions générales de Stripe ; leur disponibilité pour le pays du futur compte est à confirmer.
- **Mobile money UEMOA / CEMAC via Stripe** : non constaté dans la documentation consultée. Stripe est donc envisagé pour les **cartes** uniquement.

### 6.3 Matrice de routage (mise à jour par les décisions du § 16)
| Zone / moyen | Principal | Secours | Condition |
|---|---|---|---|
| UEMOA, mobile money (XOF) | **SASPay** (§ 16) | PayDunya (non développé au lancement) | Guinée-Bissau sans couverture SASPay documentée : virement manuel |
| CEMAC, mobile money (XAF) | Cameroun : SASPay si XAF confirmé, sinon PayDunya (MTN) | — | **Lacune** : aucune couverture documentée pour Gabon, Congo, Tchad, RCA, Guinée équatoriale. Prévoir virement bancaire avec rapprochement manuel, ou un autre prestataire (hors périmètre de l'étude) |
| Carte bancaire | **SASPay** | — | Stripe écarté (entité au Bénin, § 16) |
| Guinée (GNF), RD Congo (CDF) | SASPay si ces devises sont confirmées | virement manuel | pays présents dans la liste tierce SASPay ; devises à confirmer |
| Comores (KMF) et pays sans couverture | virement bancaire manuel | — | paiement enregistré par un administrateur `finance` avec justificatif, double validation, audit |

### 6.4 Vérification serveur, webhooks et idempotence (règles communes)
1. **Commande puis tentative** : chaque tentative crée une ligne `payments` (`pending`) avec une `idempotency_key` unique **avant** l'appel au prestataire. La clé est transmise au prestataire quand il la prend en charge. Un double clic retrouve la tentative en cours au lieu d'en créer une autre.
2. **Webhook** (`POST /api/v1/webhooks/payments/{provider}`, sans jeton utilisateur) :
   - corps brut conservé ;
   - signature vérifiée **avant** toute lecture : HMAC en comparaison à temps constant, horodatage dans la tolérance ;
   - événement enregistré dans `payment_webhook_events` avec une clé de déduplication unique (identifiant d'événement, ou empreinte du corps) ; une signature invalide est enregistrée et rejetée (400) ;
   - réponse 2xx rapide, puis traitement asynchrone.
3. **Vérification** : quelle que soit l'origine (webhook, retour navigateur, tâche de rapprochement), le paiement n'est accepté qu'après un **appel serveur au prestataire** (`verify`, `confirm`, lecture de l'objet Stripe). Ce statut doit être final et réussi, avec un **montant égal** au montant attendu et la **même devise** quand elle est fournie (PayDunya ne la fournit pas : montant et canal).
4. **Application unique** : en une seule transaction, paiement `succeeded`, commande payée, émission de la facture et du reçu, transition de l'abonnement. Le verrou porte sur la commande, et un contrôle de statut garantit qu'un rejeu n'a aucun effet.
5. **Échec et expiration** : `failed` / `expired` / `canceled` selon le prestataire. La commande reste payable par une nouvelle tentative ; aucune transition d'abonnement.
6. **Écarts** : un paiement réussi sans commande ouverte, ou d'un montant différent, n'active rien. Il passe en « à examiner » dans la console, en vue d'un remboursement ou d'une imputation manuelle journalisée.
7. **Rapprochement planifié** :
   - les paiements `pending` au-delà d'un délai sont revérifiés ;
   - un rapprochement quotidien compare avec la liste des transactions du prestataire quand l'API l'offre (SASPay : transactions ; Stripe : objets de paiement ; PayDunya : non documenté, rapprochement sur relevé) ;
   - le résultat est consigné ; aucune activation sans vérification unitaire.

### 6.5 Remboursements
- **Stripe** : remboursement par API, total ou partiel.
- **SASPay / PayDunya** : pas d'API documentée. Le remboursement est un **processus manuel tracé** : demande, validation par un second administrateur, exécution (retrait SASPay si activé, ou virement), justificatif joint, statut.
- Dans tous les cas, un **avoir** est émis (§ 7) et le paiement passe en `refunded` ou `partially_refunded`.

---

## 7. Modèle de facturation

| Document | Rôle | Numérotation | Modifiable |
|---|---|---|---|
| **Commande** (`billing_orders`) | Intention chiffrée : souscription, renouvellement, changement, option. Lignes figées (version, prix, remise, taxe). Sert d'avis d'échéance | interne, non fiscale | annulable tant qu'elle n'est pas payée ; expire |
| **Facture** | Émise **au paiement vérifié** de la commande. Vendeur et acheteur figés, lignes, taxes, totaux, devise | série continue sans trou, par entité vendeuse et par année (`billing_document_sequences`) | **jamais** : correction par avoir |
| **Reçu** | Preuve d'encaissement : paiement, prestataire, référence, date | série propre | jamais |
| **Avoir** | Annulation totale ou partielle d'une facture (remboursement, geste commercial, erreur) | série propre, référence à la facture d'origine | jamais |

- Les documents sont générés en PDF par le moteur de rendu du lot 11 (`engines/reporting`), stockés dans un bucket privé, avec empreinte SHA-256. L'historique est consultable par l'owner et téléchargeable par URL signée courte.
- Les montants sont en `Decimal` côté Python et `numeric` en base. XOF, XAF, GNF et KMF sont entiers, CDF a deux décimales (§ 16). La règle d'arrondi de la taxe (par ligne ou sur le total) est à valider.
- **Règles fiscales par pays** (`tax_rules`) :
  - pays, nature de taxe, taux, base, dates d'effet, **source** (texte, article), statut `draft` / `published` ;
  - **aucun taux n'est pré-chargé** : comme les référentiels comptables, une règle n'est utilisable qu'une fois publiée après validation par un fiscaliste ;
  - sans règle publiée pour le pays de l'acheteur, la commande est bloquée avec un message explicite. On ne facture jamais avec un taux présumé.
- **Mentions et obligations** : mentions obligatoires, identifiants du vendeur, et éventuelles obligations de facture normalisée ou électronique selon les pays. Elles dépendent de l'entité vendeuse KOFINEX et de chaque pays : **validation juridique et fiscale requise** avant la mise en production (§ 13).

---

## 8. Moteur de droits et quotas

### 8.1 Calcul des droits (« entitlements »)
Les droits effectifs d'une organisation sont ceux de la version d'offre souscrite, plus ceux des options actives (quantités), plus d'éventuelles dérogations accordées par l'administrateur (avec motif et date de fin, journalisées).

L'état de l'abonnement s'applique ensuite :
- `trialing`, `active`, `past_due` : droits complets ;
- `suspended` : lecture seule ;
- `incomplete`, `expired`, `canceled` : lecture seule si l'organisation a des données, rien sinon.

Le résultat est calculé par le serveur et mis en cache pour la durée d'une requête. Il est exposé au frontend (`GET …/entitlements`) **pour l'affichage seulement**.

### 8.2 Mesure des usages (sur les tables existantes, sans compteur dupliqué)
| Quota | Mesure |
|---|---|
| Utilisateurs | `count(organization_members)` (et invitations en attente : à décider) |
| Sociétés | `count(companies where archived_at is null)` (les archivées comptent-elles ? à décider) |
| Missions | `count(engagements)` non archivées / actives (définition à valider) |
| Stockage | somme de la taille des objets du stockage préfixés par l'organisation (`storage.objects`, métadonnée de taille, à confirmer sur Supabase) |
| Imports | `count(import_jobs)` créés dans la période de facturation |
| Rapports | `count(generated_reports)` dans la période |
| IA | somme de `ai_messages.input_tokens + output_tokens` (ou nombre d'appels) dans la période |

### 8.3 Contrôle côté backend
- Dépendance FastAPI `require_module(key)` sur chaque routeur de module (tableau § 3.1). Réponse 402 ou 403 avec code `module_not_included`.
- Service `quota.check_and_reserve(org, key, n)`, appelé dans la **même transaction** que la création. Un verrou sur la ligne d'abonnement sérialise deux créations simultanées (sinon deux requêtes concurrentes dépasseraient la limite).
- Garde « lecture seule » : toute route d'écriture refuse avec `subscription_read_only` si l'abonnement est suspendu ou expiré. La lecture et l'export restent permis.
- Les quotas périodiques (imports, rapports, IA) sont vérifiés avant l'opération. L'IA vérifie un plafond **avant** l'appel au fournisseur.

### 8.4 Défense en base (ressources comptées)
Fonction `authz.entitlement_limit(org, key)` et déclencheurs `BEFORE INSERT` sur `organization_members`, `companies` et `engagements`, qui refusent au-delà de la limite. C'est la même approche que les gardes métier existantes (exercice clôturé, dernier propriétaire). Elle couvre l'accès direct éventuel décrit au § 1. Les autres quotas, périodiques ou de volume, restent contrôlés par le backend, avec le retrait de l'exposition PostgREST.

---

## 9. Architecture des écrans

Règle du projet maintenue : aucune entrée de menu pour une fonction non développée, aucun bouton fictif. Un module non inclus est présenté comme « non inclus dans votre offre », avec un lien réel vers l'écran d'abonnement.

### 9.1 Espace client (`/organizations/[orgId]/abonnement`, owner ; lecture limitée pour admin)
1. **Vue d'ensemble** : offre et version, état, période, prochaine échéance, solde dû, bandeau d'essai ou d'impayé.
2. **Utilisation** : jauges par quota (usage / limite), modules inclus et options.
3. **Changer d'offre / options** : comparaison des offres publiées (données du catalogue), aperçu chiffré par le serveur, puis commande.
4. **Paiement** : choix du moyen parmi ceux routés pour la zone, redirection vers le prestataire, puis page de retour « vérification en cours » et état final venant du serveur.
5. **Factures, reçus, avoirs** : liste et téléchargement.
6. **Informations de facturation** : raison sociale, identifiant fiscal, adresse, pays (qui détermine la devise), e-mail.
7. **Résiliation / réactivation**.

Page publique **Tarifs** : alimentée par l'API du catalogue publié, à la place du texte « grille publiée prochainement » ; la mention FedaPay est retirée.

### 9.2 Console d'administration (`/admin`, administrateurs de plateforme)
- **Tableau de bord** : abonnements par état, encaissements, impayés, échecs de paiement, webhooks en erreur.
- **Organisations** : fiche, abonnement, usages, dérogations, suspension et réactivation motivées.
- **Offres et versions** : brouillon → publication (figée).
- **Modules, options, promotions**.
- **Abonnements** : historique depuis `audit_logs`.
- **Paiements et rapprochement** : à examiner, revérification manuelle, remboursements (double validation), journal des webhooks.
- **Documents de facturation**, **règles fiscales** (brouillon → publication), **prestataires** (activation par zone, mode test / live, état de vérification).
- **Connecteurs** (12C), **supervision** (12D), **journaux administratifs**.
- **Support** : accès temporaire à une organisation, accordé et motivé, limité dans le temps, en lecture seule par défaut, journalisé (`support.*`). L'accès du support n'est jamais implicite.

---

## 10. Nouvelles tables proposées (avec justification)

| Table | Étape | Pourquoi aucune table existante ne convient |
|---|---|---|
| `billing_accounts` | 12A | Identité de facturation 1:1 avec l'organisation, RLS owner, audit dédié ; évite d'élargir les colonnes modifiables de `organizations` |
| `billing_products` | 12A | Catalogue des offres et options (`kind` = `plan` / `addon`) ; `plan_code` texte n'est pas un catalogue |
| `billing_product_versions` | 12A | Versions figées (essai, état `draft` / `published` / `retired`), comme les référentiels |
| `billing_prices` | 12A | Prix par version × périodicité × devise (XOF, XAF, GNF, KMF, CDF) |
| `billing_entitlements` | 12A | Modules inclus et limites de quotas par version (une ligne par clé) ; source unique des droits |
| `billing_modules` | 12A | Clés de modules commercialisables et dépendances (§ 3.1) |
| `billing_promotions`, `billing_promotion_redemptions` | 12A | Codes, portée, validité, plafond d'utilisation ; utilisations tracées |
| `subscription_items` | 12A | Lignes d'un abonnement (offre de base + options et quantités) ; `subscriptions` n'a qu'un `plan_code` |
| `billing_settings` (une ligne) | 12A | Paramètres de plateforme : grâce, délais, relances, entité vendeuse |
| `billing_orders` | 12B | Commande non fiscale, préalable au paiement et à la facture (§ 7) |
| `billing_documents`, `billing_document_lines` | 12B | Factures, reçus, avoirs figés ; historique |
| `billing_document_sequences` | 12B | Numérotation continue sous verrou ; `journal_sequences` est une numérotation comptable d'entreprise cliente |
| `tax_rules` | 12B | Règles fiscales versionnées et sourcées, publiées après validation |
| `payment_providers` | 12B | Configuration non secrète de plateforme (activation, zones, devises, mode, vérification) ; `integrations` est propre à une organisation cliente |
| `payment_webhook_events` | 12B | Déduplication, preuve de signature, rejeu, erreurs ; `payments.raw_event` ne garde qu'un événement |
| `refunds` | 12B | Remboursement API ou manuel avec double validation et justificatif ; lié à l'avoir |
| `support_access_grants` | 12C | Accès support temporaire, motivé, journalisé |
| `integration_runs` | 12C | Historique des vérifications et synchronisations des connecteurs |
| `platform_staff` | 12C | Rôles de plateforme différenciés (`super_admin`, `finance`, `support`) : retenu, l'administration est confiée à une petite équipe (§ 16, décision 11) |

**Tables existantes modifiées par ALTER** (nouvelle migration ; 0001 et 0002 ne sont pas réécrites) : `subscriptions` (§ 2.3), `payments` (§ 2.4), politiques RLS et d'audit (§ 2.6). **Aucune table n'est supprimée ; aucune colonne n'est retirée.**

**Pas de table** pour l'historique des abonnements (on utilise `audit_logs`, qui couvre déjà les modifications de lignes) ni pour les compteurs d'usage (mesure sur les tables existantes, § 8.2).

Toutes les nouvelles tables auront : RLS activé ; déclencheur `0_not_ai` sur les tables métier ; déclencheur d'audit ; écriture refusée au rôle `authenticated` pour tout ce qui est commercial (écriture par le backend, contrôlée) ; clés étrangères composites quand une organisation est en jeu.

---

## 11. API et services à créer ou compléter

### 11.1 Services et moteurs (backend)
- `engines/billing/` (pur, `Decimal`, testé unitairement) :
  - `pricing.py` : prix, remises, prorata, taxes, arrondis ;
  - `lifecycle.py` : transitions autorisées de l'abonnement ;
  - `entitlements.py` : agrégation des droits ;
  - `numbering.py` : format des numéros.
- `services/billing/` :
  - `catalog.py`, `subscriptions.py`, `orders.py`, `invoicing.py` (réutilise `engines/reporting` pour le PDF), `taxes.py` ;
  - `payments.py` : routage, tentatives, application unique ;
  - `webhooks.py`, `reconciliation.py`, `refunds.py`, `quota.py`, `dunning.py` (tâches Celery beat).
- `connectors/payments/{saspay,paydunya,stripe}.py` (§ 6.1) et `connectors/accounting/{odoo,sage_business_cloud,sage_100_export}.py` (12C, interface `AccountingConnector` déjà décrite dans `ARCHITECTURE.md` §5.6).
- `core/permissions.py` : permissions `billing.read`, `billing.manage` (owner), `platform.*`. Dépendances `require_module`, `require_writable`, `require_platform_role`.

### 11.2 Routes
| Groupe | Routes (préfixe `/api/v1`) |
|---|---|
| Public | `GET /billing/catalog` (offres publiées, prix par devise, modules) |
| Client (owner, sauf lecture) | `GET/PUT /organizations/{id}/billing-account` · `GET …/subscription` · `GET …/entitlements` · `GET …/usage` · `POST …/subscription/trial` · `POST …/subscription/quote` (aperçu) · `POST …/orders` · `POST …/orders/{oid}/checkout` (`provider`, `method`) · `GET …/payments/{pid}` (déclenche une revérification serveur si `pending`) · `POST …/subscription/cancel` · `POST …/subscription/reactivate` · `GET …/billing-documents` · `GET …/billing-documents/{did}/download` |
| Webhooks (sans jeton, signature) | `POST /webhooks/payments/saspay` · `/paydunya` · `/stripe` |
| Administration | `/admin/organizations…` · `/admin/products…` (versions, publication) · `/admin/promotions…` · `/admin/subscriptions…` (changement, dérogation, suspension, résiliation) · `/admin/payments…` (revérifier, à examiner, paiement manuel) · `/admin/refunds…` (demander, approuver, exécuter) · `/admin/webhook-events…` (consulter, rejouer) · `/admin/reconciliation/runs` · `/admin/tax-rules…` · `/admin/providers…` (activer, vérifier) · `/admin/settings` · `/admin/support-access…` · `/admin/audit-logs` |
| Connecteurs (12C) | `GET/POST /organizations/{id}/integrations` · `PATCH/DELETE …/{iid}` · `POST …/{iid}/verify` · `POST …/{iid}/sync` · `GET …/{iid}/runs` |
| Supervision (12D) | `GET /health/live`, `GET /health/ready` (base, Redis, stockage) ; métriques internes réservées à l'administration |

---

## 12. Règles de sécurité

1. **Aucune activation sans paiement vérifié par le serveur auprès du prestataire** (§ 6.4). Le retour navigateur et le webhook ne font que déclencher la vérification.
2. **Webhooks** :
   - signature vérifiée sur le corps brut, comparaison à temps constant, tolérance d'horodatage ;
   - déduplication ; journalisation de chaque réception, valide ou non ;
   - limitation de débit sur la route ;
   - liste d'adresses IP si le prestataire en publie une ;
   - PayDunya (hash statique) : confirmation systématique par API.
3. **Idempotence** de bout en bout : clé de tentative unique, application unique sous verrou, tâches planifiées idempotentes.
4. **Montants** : `Decimal` / `numeric` ; décimales conformes à chaque devise (contrainte en base) ; aucun montant calculé ou accepté depuis le navigateur.
5. **Droits et quotas** contrôlés côté backend, doublés en base pour les ressources comptées ; retrait de l'exposition PostgREST du schéma `public` (§ 1).
6. **Séparation** : écriture commerciale interdite au rôle `authenticated` ; lecture des paiements réservée à l'owner ; administrateur de plateforme par politique explicite ; session de service limitée aux usages listés dans `SECURITY.md` §2 (webhooks, tâches planifiées).
7. **Secrets** dans l'environnement uniquement, jamais journalisés ni renvoyés ; clés test et live séparées et vérifiées au démarrage (refus d'une clé de test en production) ; rotation documentée.
8. **Traçabilité** : chaque opération administrative ou commerciale sensible écrit dans `audit_logs` avec acteur, motif et avant / après. Sont concernées : publication d'offre, dérogation, suspension, remboursement, paiement manuel, accès support, modification des paramètres ou d'une règle fiscale.
9. **Double validation** pour les remboursements et les paiements saisis manuellement.
10. **Accès support** temporaire, motivé, en lecture seule par défaut, visible par l'owner dans le journal.
11. **Anti-abus d'essai** : un essai par organisation et par identité de facturation ; plafond de création d'organisations par utilisateur (paramètre).
12. **Données de carte** : jamais transmises à KOFINEX ; uniquement des pages hébergées par le prestataire.

---

## 13. Dépendances externes

| Dépendance | Nécessaire pour | Statut |
|---|---|---|
| Entité juridique vendeuse KOFINEX : **Bénin** (§ 16) ; immatriculation, régime fiscal, compte bancaire | factures, taxes, contrats marchands | identifiants **à fournir** |
| Compte marchand SASPay (test puis production), vérification du prestataire, contrat | connecteur SASPay | à ouvrir ; XAF et webhooks à confirmer |
| Compte marchand PayDunya (test puis production), canaux activés | connecteur PayDunya | à ouvrir |
| Compte Stripe | — | **écarté** : entité au Bénin, pays non éligible (§ 16) |
| Fiscaliste ou juriste par pays de vente | `tax_rules`, mentions, obligations de facturation électronique, conservation des données après résiliation | à mandater |
| Service d'envoi d'e-mails transactionnels | relances, factures, essais | à choisir |
| Odoo (instance de test, version) ; Sage Business Cloud (enregistrement d'application, OAuth) ; Sage 100 (formats d'export réels) | connecteurs 12C | à fournir / à vérifier en 12C |
| Hébergement de l'application : VPS **KVM**, mémoire garantie, Ubuntu 24.04, root SSH (le cPanel mutualisé LWS M2 et les VPS LXC de LWS ne conviennent pas) | 12D | **à choisir** (§ 16) |
| Supabase : plan (sauvegardes, PITR), réglage des schémas exposés | 12D, § 1 | à confirmer |

---

## 14. Plan détaillé des étapes

### 12A — Catalogue commercial et abonnements
> **Livrée le 20 novembre 2026** (migration 0018 ; détail et tests dans `PROJECT_STATUS.md`). Précisions de réalisation :
> - les opérations du client sur son abonnement passent par des fonctions SQL `SECURITY DEFINER` : le rôle `authenticated` reste sans droit d'écriture sur `subscriptions` (§ 2.3) ;
> - le catalogue public est lu par une session `anon` soumise à RLS, et non par la session de service ;
> - la correspondance pays → devise (§ 4) est une donnée de `billing_settings`, sans table supplémentaire ;
> - un code promotionnel se vérifie un par un (`billing_promotion_lookup`) ; la liste reste réservée à l'administrateur ;
> - en attendant les tâches planifiées de 12B, l'état effectif (essai échu, résiliation échue) est calculé à la lecture.
- **Migration 0018** :
  - `billing_accounts`, `billing_products`, `billing_product_versions`, `billing_prices`, `billing_modules`, `billing_entitlements`, `billing_promotions`, `billing_promotion_redemptions`, `subscription_items`, `billing_settings` ;
  - ALTER `subscriptions` ;
  - RLS, audit, `0_not_ai` ;
  - garde « tables vides » avant l'ALTER.
- **Moteurs** : `pricing` (sans taxe), `lifecycle`, `entitlements`.
- **Services** : catalogue, abonnement (essai, transitions, annulation et réactivation, changement d'offre en aperçu).
- **API** : catalogue public, compte de facturation, abonnement, droits, usages.
- **Administration** : offres, versions, publication, modules, promotions, paramètres.
- **Écrans** : abonnement client (sans paiement), tarifs publics, console (offres) ; correction de la page publique (FedaPay, grille).
- **Tests** : moteurs, SQL (RLS, publication figée, un seul abonnement vivant), intégration API.

### 12B — Paiements, facturation et quotas
- **Migration 0022 (prévision)** : 0019 à 0021 sont prises par le correctif du contrôle de gestion (`CONTROLE_GESTION.md` § 12.2) ; le numéro est arrêté au démarrage de 12B, après la dernière migration du correctif :
  - `billing_orders`, `billing_documents`, `billing_document_lines`, `billing_document_sequences`, `tax_rules`, `payment_providers`, `payment_webhook_events`, `refunds` ;
  - ALTER `payments` et audit ;
  - `authz.entitlement_limit` et gardes de quota.
- **Interface** `PaymentConnector` et connecteur **SASPay** (§ 16), développé et recetté en sandbox après la vérification préalable et la confirmation des points « à confirmer » du § 6.2 ; enregistrement manuel des virements (administrateur `finance`, double validation). PayDunya reste un connecteur de secours, non développé au lancement ; Stripe est écarté.
- **Flux** : commande → paiement → vérification → facture et reçu → abonnement ; webhooks ; rapprochement ; relances et bascules (Celery beat) ; remboursements et avoirs.
- **Contrôles** : `require_module`, `require_writable` et `quota` branchés sur les routeurs existants. Les moteurs livrés ne sont pas modifiés : seules les dépendances de route sont ajoutées.

### 12C — Administration centrale et connecteurs
- Console complète (organisations, abonnements, paiements, prestataires, supervision métier, journaux, support).
- `support_access_grants`, `integration_runs`, `platform_staff` (rôles `super_admin`, `finance`, `support` : § 16).
- Connecteurs comptables :
  - Odoo (JSON-RPC, lecture des écritures et de la balance) ;
  - Sage 100 (import des fichiers d'export, en réutilisant `engines/importing`) ;
  - Sage Business Cloud (API REST, après vérification de sa documentation).

  Pour chacun : secrets chiffrés (Fernet existant), vérification réelle obligatoire avant `active`, synchronisation journalisée.

### 12D — Supervision, sécurité, sauvegardes et restauration
- Sondes de santé, journaux structurés, alertes (webhooks en échec, paiements en attente, tâches en retard, erreurs 5xx).
- Durcissement : en-têtes, CSP, limitation de débit, retrait de l'exposition PostgREST, rotation des secrets, revue des usages de la session de service.
- Sauvegardes : PITR ou export quotidien de la base, export du stockage, copie hors site. **Restauration testée** et consignée dans `docs/RUNBOOK.md`.
- Préparation du déploiement sur un VPS KVM (mémoire garantie, Ubuntu 24.04, root SSH), Supabase hébergé conservé (§ 16).

### 12E — Tests, recette et préparation de production
- Recette de bout en bout en sandbox pour chaque prestataire et chaque zone, et campagne de tests d'erreurs (§ 15).
- Bascule des clés live, avec un paiement réel de faible montant et un remboursement par prestataire.
- Plan de retour arrière ; documentation d'exploitation ; mise à jour de `PROJECT_STATUS.md`, `ROADMAP.md`, `SECURITY.md`, `MODELE_DONNEES.md`.

---

## 15. Tests et critères de validation

| Domaine | Tests | Critère de validation |
|---|---|---|
| Moteurs (`engines/billing`) | prix par devise et périodicité, remises, prorata montée / descente, arrondis selon les décimales de chaque devise (XOF, XAF, GNF, KMF : 0 ; CDF : 2), transitions autorisées et interdites, agrégation des droits | 100 % des cas de référence calculés à la main ; aucun `float` |
| SQL | RLS (owner, admin, membre, autre organisation, administrateur de plateforme) ; écriture commerciale refusée au client ; version publiée figée ; un seul abonnement vivant ; montants entiers ; numérotation sans trou sous concurrence ; gardes de quota ; audit ; `0_not_ai` | toutes les suites réussies |
| Webhooks | signature invalide, horodatage hors tolérance, rejeu du même événement, événements désordonnés, paiement réussi mais montant différent, devise différente, paiement sans commande | aucune activation indue ; chaque cas journalisé |
| Paiement | retour navigateur « succès » sans paiement réel ; double clic ; expiration ; échec ; webhook perdu (rattrapé par la revérification et le rapprochement) ; prestataire indisponible | l'abonnement ne change que sur paiement vérifié, une seule fois |
| Abonnements | essai → actif ; essai expiré ; impayé → grâce → suspension (lecture et export possibles, écriture refusée) → réactivation ; résiliation en fin de période ; descente refusée si l'usage dépasse | transitions conformes au § 5 |
| Quotas | dépassement par l'API, par création concurrente, par insertion directe en base ; quotas périodiques ; IA plafonnée avant appel | refus systématique, message explicite |
| Facturation | facture émise uniquement au paiement ; avoir sur remboursement ; PDF avec empreinte ; blocage sans règle fiscale publiée | documents conformes et figés |
| Sandbox prestataires | SASPay, PayDunya, Stripe : succès, échec, annulation, remboursement (Stripe) ou processus manuel | exécutés réellement et consignés avec date ; **aucun résultat déclaré sans exécution** |
| Restauration | restauration d'une sauvegarde sur un environnement vierge | durée et intégrité consignées |
| Non-régression | suites existantes (SQL, unitaires, intégration, `npm run typecheck` / `build`) | inchangées et réussies |

---

## 16. Décisions commerciales (arrêtées le 20 novembre 2026)

| N° | Sujet | Décision | Conséquence pour la conception |
|---|---|---|---|
| 1 | Entité vendeuse | **Entreprise immatriculée au Bénin** | Factures émises depuis le Bénin ; règles fiscales béninoises à saisir et faire valider par un fiscaliste (`tax_rules`, aucune valeur pré-chargée). **Stripe écarté** : le Bénin ne figure pas parmi les pays où Stripe ouvre un compte (§ 6.2). Cartes bancaires via SASPay. |
| 2 | Pays de lancement | **Les 17 États membres de l'OHADA** | Bénin, Burkina Faso, Côte d'Ivoire, Guinée-Bissau, Mali, Niger, Sénégal, Togo (XOF) ; Cameroun, Centrafrique, Congo, Gabon, Guinée équatoriale, Tchad (XAF) ; Guinée (GNF) ; Comores (KMF) ; RD Congo (CDF). Hors OHADA : non commercialisé au lancement. |
| 3 | Passerelle principale | **SASPay** | Connecteur SASPay développé en premier (12B) ; PayDunya conservé comme option de secours, non développé au lancement. Pays sans couverture SASPay documentée (liste tierce à confirmer par `GET /countries/`) : Guinée-Bissau, Centrafrique, Congo, Gabon, Guinée équatoriale, Tchad, Comores → paiement par **virement bancaire enregistré manuellement** (double validation, justificatif). |
| 4 | Essai | **30 jours, sans moyen de paiement** | Un essai par organisation et par identité de facturation (§ 12, règle 11). La page d'accueil (« 14 jours ») est corrigée en 12A. |
| 5 | Devises hors franc CFA | **Facturation en devise locale** pour la Guinée (GNF), les Comores (KMF) et la RD Congo (CDF) | La règle « XOF et XAF seulement » du lot 12 est étendue à ces trois devises (codes ISO). Décimales ISO 4217 : XOF 0, XAF 0, GNF 0, KMF 0, CDF 2 ; un prix est saisi pour chaque devise, aucune conversion n'est calculée. Prise en charge de GNF, KMF et CDF par SASPay : **à confirmer** avant ouverture de ces pays. |
| 6 | Répartition des modules | **Proposition du § 3.2 retenue par défaut** (aucune préférence exprimée) | Modifiable par l'administrateur par une nouvelle version d'offre, sans code. |
| 7 | Impayés | **7 jours de grâce**, puis lecture seule | Paramètre de plateforme (`billing_settings`), modifiable et journalisé. Délai entre suspension et résiliation : à fixer par l'administrateur (aucune résiliation automatique tant qu'il n'est pas fixé). |
| 8 | Changement d'offre | **Montée en gamme au prorata**, effet immédiat | Calcul serveur en `Decimal`, arrondi à l'unité de la devise (règle d'arrondi au plus proche, la moitié vers le haut : décision du 20 novembre 2026, arrondi à confirmer par le fiscaliste). Descente en gamme en fin de période (§ 5.2). |
| 9 | Remboursements | **Aucun remboursement** | Seule une erreur de facturation donne un avoir, émis manuellement avec double validation. La table `refunds` reste prévue pour ces cas (exécution manuelle, SASPay n'ayant pas d'API de remboursement). |
| 10 | Conservation après résiliation | **Avis d'un juriste d'abord** | Aucune suppression automatique des données en attendant ; export complet toujours proposé. |
| 11 | Administration de la plateforme | **Une petite équipe** | Table `platform_staff` retenue (§ 10) : rôles `super_admin`, `finance` (paiements, avoirs, virements manuels), `support` (lecture, accès support temporaire). `is_platform_admin` reste l'équivalent de `super_admin`. |
| 12 | Page d'accueil | **Remplacer « FedaPay » par SASPay** | Correction en 12A, avec la grille tarifaire lue dans le catalogue publié. |

**Restant à trancher ou à vérifier avant les étapes concernées :**
- **Avant 12B : vérification préalable de SASPay** (entité juridique, agrément ou partenaire régulé, contrat, délais de reversement). Ouvrir un compte sandbox, puis confirmer contre la documentation officielle les devises XAF, GNF, KMF et CDF, la liste des pays (`GET /countries/`) et la signature des webhooks.
- **Avant 12B : fiscalité béninoise** des abonnements (taxe applicable, mentions obligatoires, éventuelle facture normalisée) par un fiscaliste.
- **Avant 12D : sécurité Supabase.** Le retrait de l'exposition PostgREST du schéma `public` est recommandé (§ 1) et sera appliqué au déploiement.
- **Avant 12D : hébergement.** Supabase hébergé est conservé. Pour l'application, il faut un VPS **KVM** avec mémoire garantie et Ubuntu 24.04 (Python 3.12 requis). Les VPS standard LWS (LXC, mémoire incluant du VSWAP) ne conviennent pas. Le VPS Docker LWS (KVM) ou un autre hébergeur restent à confirmer.
- Unités de quota : **décision du 20 novembre 2026** : IA en jetons, sociétés non archivées, utilisateurs = membres de l'organisation. Arrondi au plus proche, la moitié vers le haut : à confirmer par le fiscaliste.

---

## 17. Sources consultées (18 novembre 2026)

**Dépôt KOFINEX** :
- `backend/sql/0001_core_schema.sql`, `0002_rls_policies.sql`, `0003_storage.sql`, `0012_ai.sql` ;
- `backend/app/core/{config,permissions}.py`, `api/v1/{organizations,companies,frameworks}.py` ;
- `frontend/app/page.tsx` ;
- `PROJECT_STATUS.md`, `docs/{ROADMAP,MODULES,MODELE_DONNEES,ARCHITECTURE,SECURITY,CDC_FONCTIONNEL}.md`.

**SASPay** :
- documentation officielle : https://docs.saspay.me/api-reference/introduction, https://docs.saspay.me/quickstart, https://docs.saspay.me/llms.txt, https://docs.saspay.me/api-reference/payment-links/create ;
- site : https://saspay.me ;
- spécification tierce (non officielle, à recouper) : https://afro.tools/providers/saspay ;
- pages non lisibles directement dans cette étude, à relire avant 12B : `/api-reference/webhooks`, `/api-reference/reference/countries`, `/api-reference/reference/networks`, `/sandbox`.

**PayDunya** : https://developers.paydunya.com/doc/EN/http_json, https://developers.paydunya.com/doc/EN/softpay, https://developers.paydunya.com/doc/EN/sandbox_softpay.

**Stripe** : https://docs.stripe.com/currencies, https://stripe.com/global, https://docs.stripe.com/api/idempotent_requests, https://docs.stripe.com/error-low-level, https://stripe.dev/stripe-java/com/stripe/net/Webhook.Signature.html (vérification de signature avec tolérance) ; page https://docs.stripe.com/webhooks non relue dans cette étude.
