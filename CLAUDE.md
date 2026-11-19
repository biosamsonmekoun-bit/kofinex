# Règles permanentes du projet KOFINEX

## Avant toute modification
- Lire `PROJECT_STATUS.md`, puis seulement les documents de `docs/` qui concernent la tâche.
- Ne pas reconstruire un module existant ; l'étendre.
- Ne pas commencer un lot qui n'a pas été demandé.

## Règles métier non négociables
- **Aucune norme inventée** : les règles comptables, les cadres de contrôle interne, les méthodologies d'audit, les seuils, les tailles d'échantillon et les modèles de rapport sont des **données versionnées et sourcées**, jamais des constantes dans le code. Toute interprétation est marquée « [À VALIDER] ».
- **Calculs en `Decimal`**, par du code testé, jamais par l'IA.
- **L'IA propose, l'humain décide** : elle ne crée pas d'élément probant, ne signe pas, ne valide pas, ne conclut pas et ne modifie aucun chiffre. Ces interdits sont imposés en base et dans l'API, pas seulement par le prompt.
- **Pas de simulation** : aucun bouton factice, aucun connecteur simulé, aucune page vide présentée comme terminée. Les données de démonstration sont isolées (`is_demo`) et signalées.
- **Données importées intactes** : une balance validée n'est jamais modifiée. Les ajustements d'audit produisent une balance ajustée calculée.

## Règles techniques
- Couches : `api/v1` (HTTP, permissions) → `services` (transactions, journal) → `engines` (Python pur, testé).
- Chaque table métier porte `organization_id` (et `company_id` / `engagement_id` si besoin), avec des clés étrangères composites et la RLS. **Ne jamais compter sur le frontend pour la sécurité.**
- Migrations : un fichier `backend/sql/NNNN_*.sql` exécuté par une révision Alembic. Pour toute nouvelle table : policies RLS et test SQL négatif.
- Énumérations en `text` + `CHECK`. Objets figés protégés par *trigger*.
- **Toute nouvelle table métier reçoit le déclencheur `"0_not_ai"`** (`EXECUTE FUNCTION public.guard_not_ai()`), pour que l'IA ne puisse jamais y écrire (voir `docs/IA.md`).
- Journal : chaque action métier passe par le service d'audit (`audit_logs`, en ajout seul). Les permissions du module d'audit sont préfixées `engagement.` (`audit.read` désigne le journal).
- Tables partagées, pour éviter les doublons :
  - un seul registre `processes` / `risks` par entité ;
  - une seule table `findings` / `action_plans` ;
  - une seule table `signoffs` et une seule `review_notes`, polymorphes.
- Interface : couleurs uniquement via les tokens de `frontend/app/globals.css` (jamais de HEX ni de `red-600`, `slate-900`… dans les composants) ; l'or (`accent`) est réservé aux touches de prestige ; voir `docs/DESIGN_SYSTEM.md`.
- Tests à lancer avant de livrer : `make test-unit`. Pour une modification de schéma ou de RLS, ajouter `make test-sql`. Pour le frontend : `npm run typecheck` et `npm run build`. Les tests d'intégration de l'API (`backend/tests/integration`) sont à exécuter dès que les dépendances sont installées.
- **Aucun résultat de test inventé** : ne jamais déclarer réussi un test qui n'a pas été exécuté. Dire précisément ce qui a été exécuté, ce qui ne l'a pas été et pourquoi.
- **Réutiliser avant de créer** : examiner les tables, services, permissions et composants existants avant d'en ajouter. Toute nouvelle table est justifiée dans la documentation. Ne jamais modifier une migration déjà livrée : en ajouter une nouvelle.
- Montants : `Decimal` côté Python, `numeric` en base, jamais de nombre flottant (y compris dans le navigateur : les calculs restent côté serveur).
- Livraisons : chaque archive livrée porte un nom distinct (ex. `KOFINEX_<lot>_<objet>.zip`), sans `node_modules`.

## Points en attente de décision (ne pas trancher sans validation)
- **Lot 12 (SaaS)** : conception rédigée dans `docs/LOT12_SAAS_CONCEPTION.md`, **en attente d'approbation** ; aucun développement avant validation (décisions listées au § 16).
- **FEC DGI Bénin** : livré (`docs/FEC_BENIN.md`), mais aucun fichier n'est déclaré « conforme » tant que les points du § 6 restent ouverts (`SPEC_CONFIRMED = False` dans `engines/accounting/fec_bj.py`).
- **Comptabilité native** : décisions du § 7 de `docs/COMPTABILITE_NATIVE.md` ; étapes C, D et E du lot 3B non commencées.
- **Contrôle de gestion** : points à valider du § 11.14 et du § 11.15 de `docs/CONTROLE_GESTION.md` (produits en net ou en brut, seuils par défaut, codes tiers du grand livre).

## Documentation
- `docs/CDC_FONCTIONNEL.md`, `docs/CDC_TECHNIQUE.md` : exigences.
- `docs/ARCHITECTURE.md`, `docs/MODULES.md`, `docs/MODELE_DONNEES.md`, `docs/DESIGN_SYSTEM.md` : conception ; `docs/CONTROLE_GESTION.md` : règles du lot 5 ; `docs/AUDIT_SOCLE.md` : règles du lot 6 ; `docs/AUDIT_FINANCIER.md` : règles du lot 7 ; `docs/AUDIT_INTERNE.md` : règles du lot 8 ; `docs/GRAND_LIVRE.md` : grand livre (complément du lot 3) ; `docs/CONTROLE_INTERNE.md` : règles du lot 9 ; `docs/IA.md` : règles du lot 10 ; `docs/REPORTING.md` : règles du lot 11 ; `docs/INTERFACE.md` : page d'accueil, démonstration fictive isolée et tableau de bord ; `docs/COMPTABILITE_NATIVE.md`, `docs/JOURNAUX_COMPTABLES.md`, `docs/ECRITURES_COMPTABLES.md` : comptabilité native (lot 3B) ; `docs/FEC_BENIN.md` : FEC DGI Bénin (arrêté n° 1085 du 23 avril 2020, migration 0016) ; `docs/LOT12_SAAS_CONCEPTION.md` : conception du lot 12, non approuvée. Les écritures natives ne sont jamais stockées dans `ledger_lines` (grand livre importé).
- `docs/ROADMAP.md`, `PROJECT_STATUS.md` : avancement. Mettre `PROJECT_STATUS.md` à jour à la fin de chaque lot.
- Documentation en français, concise.
