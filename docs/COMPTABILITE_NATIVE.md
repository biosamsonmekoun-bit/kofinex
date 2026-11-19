# KOFINEX — Comptabilité générale native (lot 3B)

*État au 18 novembre 2026 : **étapes A (fondations) et B (saisie et consultation) livrées**. Étapes C (auxiliaires et moteur de génération), D (inventaire et clôture) et E (états financiers et intégrations) non commencées.*

## 1. Ce que le module permet aujourd'hui
1. Ouvrir le plan comptable de l'entreprise à partir du référentiel publié (SYSCOHADA révisé ou SYSCEBNL), compte par compte ou en une fois.
2. Créer les tiers et les journaux.
3. Saisir une écriture, la contrôler, la soumettre, la faire réviser (si l'entreprise l'a décidé) et valider par une autre personne.
4. Corriger une écriture validée par extourne, puis nouvelle écriture.
5. Consulter le grand livre natif et les balances (générale, auxiliaire, avant / après inventaire, comparative) ; les exporter en CSV.
6. Lettrer les comptes lettrables.
7. Contrôler, générer et archiver le Fichier des Écritures Comptables (FEC) exigé par la DGI du Bénin (onglet « FEC », comptables et administrateurs) : voir `FEC_BENIN.md`.

Il ne permet pas encore : les opérations auxiliaires (achats, ventes, trésorerie, immobilisations, paie, fiscalité, stocks) et leur génération automatique d'écritures, les travaux d'inventaire guidés, la clôture et les à-nouveaux, ni les états financiers établis à partir des écritures natives.

## 2. Séparation avec les imports
| Donnée | Table | Origine |
|---|---|---|
| Balance importée | `trial_balance_entries` | lot 3, inchangé |
| Grand livre importé | `ledger_lines` | lot 3, inchangé |
| Écritures natives | `journal_entries`, `journal_entry_lines` | lot 3B |

Le module ne lit ni ne modifie les tables importées. Le grand livre et les balances natifs ne portent que sur les écritures natives validées ; les écrans le précisent. La provenance de chaque écriture native est conservée (`origin`) : saisie, générée (réservée au futur moteur, refusée en saisie), inventaire, extourne, correction, à-nouveaux.

## 3. Architecture
| Couche | Fichiers |
|---|---|
| Base | `backend/sql/0014_native_accounting.sql` (Alembic `0014`) |
| Modèles | `app/models/native_accounting.py` |
| Schémas d'entrée | `app/schemas/native_accounting.py` (montants en chaînes, flottants refusés) |
| Moteurs purs | `app/engines/accounting/entries.py` (montants, contrôles, extourne, lettrage), `app/engines/accounting/native_ledger.py` (grand livre, balances) |
| Services | `app/services/accounting_setup.py`, `app/services/journal_entries.py`, `app/services/native_ledger.py` |
| API | `app/api/v1/accounting.py`, préfixe `/api/v1/companies/{id}/accounting` |
| FEC DGI Bénin | `backend/sql/0016_fec_benin.sql`, `app/engines/accounting/fec_bj.py`, `app/services/fec.py`, `app/api/v1/fec.py`, `comptabilite/fec/page.tsx` (voir `FEC_BENIN.md`) |
| Interface | `frontend/app/(app)/companies/[companyId]/comptabilite/…`, `components/accounting-shell.tsx`, `components/entry-editor.tsx`, `lib/accounting-types.ts` |

Montants : `numeric(20,2)` en base, `Decimal` côté Python, centimes entiers (`BigInt`) pour les totaux affichés pendant la saisie. Aucun calcul monétaire en virgule flottante.

## 4. Plan comptable de l'entreprise et tiers
- Un compte de l'entreprise (`company_accounts`) relève d'un compte du plan du référentiel publié : son numéro commence par celui du compte du référentiel (vérifié en base). La nature (actif, passif, charge, produit…) est reprise du référentiel.
- La version du référentiel est celle applicable à la fin du dernier exercice de l'entreprise.
- « Ouvrir les comptes du référentiel » ouvre les comptes sans sous-compte, avec le même numéro et le même intitulé. **Aucun compte n'est déclaré collectif ni lettrable d'office** : c'est à l'entreprise de le décider.
- Un compte collectif exige un tiers sur chaque ligne ; il peut imposer un type de tiers (client, fournisseur, salarié…).
- Un compte mouvementé ne peut être ni supprimé ni renuméroté, et son caractère collectif est figé ; il peut être désactivé.
- Tiers (`third_parties`) : code unique, type, compte collectif de rattachement (du même type), coordonnées. Un tiers mouvementé garde son code.

## 5. Sécurité
- RLS sur les 10 nouvelles tables. Lecture : membres de l'entreprise et équipes de mission qui l'auditent (lecture seule). Écriture : comptables et administrateurs. Paramètres : administrateurs. Séquences et historique : écrits uniquement par la base.
- Déclencheur `0_not_ai` sur toutes les nouvelles tables (l'IA ne peut rien écrire).
- Journal d'audit (`audit_row_change`) sur les paramètres, comptes, tiers, journaux et lettrages ; historique propre aux écritures (`journal_entry_events`, immuable).
- Exercice clôturé : aucune écriture ni ligne ne peut être créée, modifiée ou supprimée.

## 6. Tests
- SQL : `tests/sql/test_native_accounting.sql`, 68 contrôles (RLS, isolation, droits, immutabilité, circuit, unicité des numéros, double validation, extourne, double comptabilisation d'une source, lettrage, exercice clôturé, acteur IA).
- Unitaires : `tests/engines/test_native_accounting.py`, 13 tests (montants, équilibre, contrôles, extourne, codes et contrôle du lettrage, grand livre, balances générale, auxiliaire, avant / après inventaire, comparative, reproductibilité).
- Intégration : `tests/integration/test_native_accounting_api.py` (paramétrage → saisie → contrôle → validation → grand livre → balances → lettrage → extourne et correction). **Non exécuté ici** : FastAPI et SQLAlchemy ne sont pas installés dans cet environnement.

- FEC DGI Bénin : 20 tests unitaires et 33 contrôles SQL exécutés et réussis ; test d'intégration `tests/integration/test_fec_api.py` non exécuté ici (voir `FEC_BENIN.md` § 9).

## 7. Décisions à valider
1. **Numérotation à la validation.** Le numéro définitif est attribué dans l'ordre des validations, par journal et par exercice, sans trou. C'est cohérent avec l'arrêté FEC du Bénin (ordre chronologique de validation, numéro séquentiel continu) ; la portée de la continuité (par journal ou pour tout le fichier) reste à confirmer (`FEC_BENIN.md` § 6). Si la réglementation applicable ou la politique de l'entreprise exige une numérotation dans l'ordre chronologique des dates d'écriture, il faut le dire : la règle sera adaptée (par exemple, validation par période).
2. **Extourne dans le même exercice.** L'extourne d'une écriture est passée dans l'exercice de l'écriture d'origine. Les erreurs découvertes après la clôture sont corrigées par une écriture de l'exercice en cours (étape D).
3. **Lettrage complet uniquement.** Les lignes lettrées ensemble doivent se solder. Le lettrage partiel n'est pas proposé.
4. **Lettrage sur un exercice clôturé.** Il n'est plus possible : les lignes sont figées. Le règlement d'une facture d'un exercice clos se lettrera avec l'à-nouveau détaillé (étape D).
5. **Pièces justificatives.** Elles acceptent les formats déjà autorisés par la plateforme (PDF, Excel, CSV). Les photos (JPEG, PNG) nécessitent d'élargir la liste des formats du stockage.
6. **Données de paie dans les journaux de paie.** Elles sont lisibles par tous les membres de l'entreprise. La restriction propre à la paie est prévue avec le module Paie (étape C).
