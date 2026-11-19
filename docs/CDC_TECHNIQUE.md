# KOFINEX — Cahier des charges technique

Ce document complète `ARCHITECTURE.md` (vue d'ensemble), `MODULES.md` (découpage et dépendances), `MODELE_DONNEES.md` (tables) et `SECURITY.md`.

## 1. Stack (inchangée, décisions validées)

| Couche | Choix |
|---|---|
| Frontend | Next.js 15 (App Router), React, TypeScript, Tailwind, shadcn/ui, Recharts |
| API | Python 3.12, FastAPI, Pydantic, SQLAlchemy 2, Alembic (chaque migration exécute un fichier `backend/sql/NNNN_*.sql`) |
| Données | PostgreSQL (Supabase), RLS sur toutes les tables, Supabase Auth (JWT) et Storage (buckets privés) |
| Traitements | Redis + Celery (import, OCR, calculs, génération de documents, analyses de données d'audit) |
| Documents | openpyxl, pdfplumber, pypdfium2 + Tesseract (OCR), WeasyPrint/ReportLab, python-docx |
| Calcul | `decimal.Decimal` ; expressions évaluées par un arbre syntaxique restreint (pas d'`eval`) |

## 2. Règles d'implémentation communes à tous les modules
1. **Trois couches** :
   - `api/v1` : HTTP, validation, permissions ;
   - `services` : transactions, audit, tâches ;
   - `engines` : Python pur, sans HTTP ni ORM, testé unitairement.
2. **Multi-tenant** :
   - chaque table métier porte `organization_id`, et `company_id` quand elle concerne une entité ;
   - les clés étrangères sont composites (`id, organization_id`), pour qu'aucun lien ne traverse deux organisations ;
   - l'API s'exécute sous `SET LOCAL ROLE authenticated` avec les *claims* du JWT, donc la RLS s'applique aussi aux requêtes de l'API.
3. **Énumérations** : `text` + `CHECK` (convention du projet).
4. **Objets figés** : référentiel publié, formule publiée, analyse terminée, feuille signée, dossier archivé. Un *trigger* refuse leur modification ; la réouverture est explicite, motivée et journalisée.
5. **Journal** : `audit_logs`, en ajout seul, alimenté par le service d'audit pour chaque action métier.
   - Ne pas confondre ce « journal d'audit » (traçabilité) avec le **module d'audit** (missions). Les permissions du module d'audit sont préfixées `engagement.` ; `audit.read` reste réservé au journal.
6. **Normes et méthodes en données** : les référentiels comptables, les cadres de contrôle interne et les méthodologies d'audit (cycles, assertions, grilles de cotation, options de seuil, tailles d'échantillon, programmes types, modèles de rapport) suivent le même cycle `draft → published → archived` que `framework_versions`. Le code ne contient aucune valeur normative.

## 3. Besoins de données nouveaux
| Besoin | Réponse |
|---|---|
| Écritures comptables (tests de détail, sondages, analyses) | Table `ledger_lines` (livrée, voir `GRAND_LIVRE.md`) alimentée par un nouvel import « grand livre / journal », qui réutilise le pipeline d'import existant (lecteurs, association des colonnes, contrôles). Contrôle de cohérence : le total des écritures par compte doit égaler les mouvements de la balance validée. |
| Données figées pour preuve | « Instantané » d'une balance, d'un état ou d'une extraction d'écritures, stocké comme élément probant avec son empreinte |
| Seuils, revue analytique, états ajustés | Moteur financier existant (états, indicateurs, N-1) appelé avec la balance **ajustée**, calculée à la volée : balance validée + écritures d'ajustement acceptées |
| Échantillonnage | Moteur Python déterministe (graine stockée), reproductible à l'identique |
| Analyses de données d'audit | Moteur déterministe (doublons, ruptures de séquence, écritures de week-end ou après clôture, montants ronds, distribution des premiers chiffres, utilisateurs inhabituels) exécuté en tâche Celery ; résultats stockés et traçables |
| Contrôle interne (lot 9) | Référentiels = méthodologies versionnées ; registre partagé `processes` / `risks` ; matrice N-N `control_risks` ; tests dans les missions avec préparateur et réviseur distincts ; synthèse déterministe IC-SYNTH-1 identique en Python et en SQL, figée à la soumission d'une évaluation ; déficiences dans `findings` (`kind = 'ic_deficiency'`) — voir `CONTROLE_INTERNE.md` |

## 4. Workflow de validation (machine d'états commune)

```
feuille / procédure / test :  draft → prepared (signature préparateur) → reviewed (signature réviseur) → approved
                                         ↑___________ modification après signature : signatures révoquées, retour à draft
mission :  planning → fieldwork → review → reporting → issued → archived (figé) [→ reopened, motivé]
constat :  draft → validated (auditeur) → communicated → responded (audité) → closed
plan d'action :  open → in_progress → implemented (audité) → verified (auditeur) | overdue (calculé)
```
- **Signatures** : table unique `signoffs` (objet, rôle de signature, utilisateur, date, empreinte du contenu signé). L'empreinte permet de détecter toute modification ultérieure.
- **Règles en base** :
  - une signature exige un utilisateur humain authentifié (`auth.uid()`) membre de la mission avec un rôle autorisé ;
  - le préparateur ne peut pas être le réviseur du même objet ;
  - une mission ne passe à `issued` que si aucune note de revue n'est ouverte et si toutes les feuilles sont approuvées.

## 5. IA : garde-fous techniques
- **Contexte** : l'IA ne reçoit que des données structurées, déjà calculées et autorisées pour l'utilisateur (même RLS). Le contexte envoyé est conservé (`ai_messages`).
- **Provenance** : toute ligne créée à partir d'une suggestion porte `origin = 'ai_suggestion'` et le lien vers le message IA. Elle reste au statut `draft` tant qu'un humain ne l'a pas acceptée.
- **Interdits imposés par la base** :
  - `signoffs`, `evidence_items` et les changements de statut vers `prepared`, `reviewed`, `approved`, `validated` ou `verified` exigent `auth.uid()` d'un membre de la mission ;
  - le rôle de service utilisé par les workers IA n'a pas le droit d'insérer dans ces tables.
- **Chiffres** : après chaque réponse, les nombres sont extraits et rapprochés du contexte. Un nombre non traçable entraîne le rejet de la réponse ou un avertissement visible.
- **Rédaction** : les brouillons IA sont marqués comme tels dans l'interface et dans les exports, tant qu'ils n'ont pas été relus. L'IA ne produit jamais une opinion d'audit.
- **Mise en œuvre (lot 10)** : l'IA n'a pas de rôle de base distinct, car les appels passent par l'API avec l'identité de l'utilisateur. L'interdit est porté par l'acteur de session `kofinex.actor = 'ai'`, posé pendant l'enregistrement d'une sortie du modèle : un déclencheur bloque alors toute table métier. Les statuts et signatures exigent en plus `auth.uid()` d'un membre (lots 6 à 9). Détail : `IA.md`.

## 6. Stockage des éléments probants
- Nouveau bucket privé `audit-evidence`, organisé en `organization_id/engagement_id/…`. Les originaux sont immuables ; une nouvelle version est un nouvel objet.
- Les fichiers suivent les mêmes contrôles que les imports : *magic bytes*, macros refusées, taille maximale, empreinte SHA-256. Les dépôts par l'audité ne sont acceptés que pour une demande ouverte.
- Accès par URL signée courte ; chaque téléchargement est journalisé.
- Conservation : durée fixée par la méthodologie et par la réglementation applicable (paramètre de l'organisation). La suppression est impossible avant l'échéance.

## 7. Exigences non fonctionnelles
| Domaine | Exigence |
|---|---|
| Sécurité | RLS + permissions côté API (jamais le frontend seul) ; MFA recommandée pour les rôles de signature ; chiffrement des secrets d'intégration (Fernet) |
| Performance | Imports et analyses de données en tâche de fond ; pagination côté serveur ; populations de plusieurs centaines de milliers d'écritures traitées par lots |
| Fiabilité | Calculs reproductibles (même entrée = même sortie, versions de formules et de méthodologie enregistrées) |
| Tests | Moteurs : tests unitaires. RLS et Storage : scénarios SQL. Parcours : tests d'intégration API. Chaque règle de workflow a un test SQL négatif (tentative refusée). |
| Accessibilité, i18n | Interface en français, montants au format local, contraste et navigation clavier (design system, lot 2) |
