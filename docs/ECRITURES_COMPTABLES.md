# KOFINEX — Écritures comptables natives (lot 3B, étapes A et B)

## 1. Saisie
- **En-tête** : journal, date (dans l'exercice), référence et date de la pièce, libellé, tiers facultatif. L'exercice est celui choisi dans la barre supérieure ; la période est le mois de la date.
- **Lignes** : compte (recherche dans le plan de l'entreprise), tiers (filtré par le type exigé par le compte collectif), libellé, débit ou crédit, centre analytique (centres du contrôle de gestion), devise et montant en devise (facultatifs, ensemble).
- **Calculs à l'écran** : total débit, total crédit, écart, équilibre, en centimes entiers.
- **Ergonomie** :
  - ajout, duplication et suppression de lignes ;
  - une nouvelle ligne reprend l'écart restant ;
  - Entrée sur le dernier crédit ajoute une ligne ; Alt+N ajoute une ligne ; Ctrl+S enregistre ;
  - enregistrement en brouillon ;
  - prévisualisation des contrôles du serveur sans enregistrer ;
  - duplication d'une écriture ;
  - pièces justificatives jointes.
- **Contrôles côté serveur** (`POST …/entries/check` et à la soumission), puis de nouveau en base :
  - au moins deux lignes ;
  - un seul sens par ligne ;
  - montants positifs à deux décimales ;
  - équilibre ;
  - comptes ouverts et actifs ;
  - tiers obligatoire sur les comptes collectifs, actif et du bon type ;
  - date dans l'exercice ;
  - journal actif.

## 2. Circuit de validation
| Départ | Arrivée | Qui | Conditions (en base) |
|---|---|---|---|
| brouillon | soumise | comptable, administrateur | contrôles complets |
| soumise | brouillon | l'auteur | retrait |
| soumise | en revue | comptable ou administrateur | revue activée dans les paramètres ; pas l'auteur si la séparation des tâches est active |
| soumise ou en revue | validée | comptable ou administrateur | revue faite si elle est obligatoire ; validateur différent du préparateur et de celui qui a soumis (séparation des tâches, active par défaut) ; contrôles refaits ; numéro attribué |
| soumise ou en revue | rejetée | comptable ou administrateur | motif de 5 caractères au moins |
| rejetée | brouillon | l'auteur | reprise |
| validée | extournée | la base, à la validation de l'extourne | — |

- **Immutabilité** : une écriture validée ou extournée ne peut être ni modifiée (en-tête, lignes, totaux) ni supprimée. Seul le lettrage de ses lignes peut évoluer.
- **Concurrence** : le changement de statut verrouille la ligne de l'écriture (`SELECT … FOR UPDATE`), puis la base refuse toute transition depuis un statut qui n'est plus le bon. Deux validations simultanées ne peuvent pas aboutir toutes les deux.
- **Suppression** : un brouillon ou une écriture rejetée peut être supprimé, par son auteur uniquement ; l'historique est conservé.
- **Totaux** : `total_debit`, `total_credit` et `line_count` sont tenus par la base à partir des lignes ; ils ne peuvent pas être écrits directement.
- **Historique** (`journal_entry_events`) : création, soumission, retrait, revue, validation, rejet (avec motif), reprise, extourne, suppression, avec l'auteur et l'horodatage. Il ne peut être modifié ni supprimé, même par le propriétaire de la base.
- **Journal d'audit** de la plateforme : validations, rejets et préparations d'extourne.

## 3. Extourne et correction
- Seule une écriture validée peut être extournée, une seule fois (index unique), dans le même exercice et à une date égale ou postérieure.
- L'extourne doit inverser **exactement** l'écriture d'origine : mêmes comptes, tiers et montants, sens inversé. C'est vérifié en base à la soumission et à la validation.
- L'extourne suit le circuit complet. À sa validation, l'écriture d'origine passe à « extournée » et renvoie à son extourne.
- Avec l'option « correction », une écriture de correction (`origin = correction`) est préparée en brouillon. Elle reprend les lignes d'origine à rectifier et renvoie à l'écriture corrigée.

## 4. Double comptabilisation
Une opération source (`source_type`, `source_id`) ne peut être comptabilisée que par une seule écriture non rejetée (index unique). Les écritures « générées » ne peuvent être créées que par le moteur de génération (étape C) ; une saisie manuelle avec cette provenance est refusée.

## 5. Grand livre natif
- **Écritures prises en compte** : écritures validées et extournées de l'exercice ; une extournée est neutralisée par son extourne.
- **Filtres** : compte (début du numéro), journal, dates, pièce, tiers.
- **Par compte** : solde d'ouverture (à-nouveaux et mouvements antérieurs à la période), lignes avec solde progressif, totaux, solde final, lettrage.
- **Traçabilité** : chaque ligne renvoie à son écriture, avec ses pièces et son historique.
- **Export** : CSV.

## 6. Balances
- **Types** :
  - générale ou auxiliaire (par tiers) ;
  - avant inventaire (sans les écritures de provenance « inventaire ») ou après inventaire ;
  - définitive, uniquement pour un exercice clôturé ;
  - comparative : soldes de clôture de N et de N-1, et écart.
- **Filtres** : période, journal, compte.
- **Colonnes** : soldes d'ouverture (débit, crédit), mouvements de la période, soldes de clôture.
- **Contrôles affichés** : équilibre des trois groupes de colonnes, nombre d'écritures validées prises en compte et d'écritures non validées écartées.
- **Reproductibilité** : le calcul est déterministe (tri explicite, Decimal), testé indépendamment de l'ordre des lignes.
- **Export** : CSV.

## 7. Lettrage
- **Comptes concernés** : les comptes déclarés lettrables ; par tiers pour un compte collectif.
- **Lignes** : uniquement celles d'écritures validées.
- **Lettrage complet** : la sélection doit être soldée et compter au moins deux lignes du même compte et du même tiers. La base le vérifie en fin d'opération (contrainte différée).
- **Codes** : attribués à la suite par compte (A, B… Z, AA…).
- **Délettrage** : on supprime le lettrage. Un lettrage n'est jamais modifié.
- **Exercice clôturé** : ses lignes ne sont plus lettrables (voir les décisions dans `COMPTABILITE_NATIVE.md`).

## 8. API (`/api/v1/companies/{id}/accounting`)
| Domaine | Routes |
|---|---|
| Paramètres | `GET /settings` (avec les droits), `PUT /settings` |
| Plan comptable | `GET /accounts`, `POST /accounts`, `POST /accounts/import-chart`, `PATCH /accounts/{id}`, `DELETE /accounts/{id}` |
| Tiers | `GET /third-parties`, `POST /third-parties`, `PATCH /third-parties/{id}` |
| Journaux | `GET /journals`, `POST /journals`, `PATCH /journals/{id}`, `DELETE /journals/{id}` |
| Écritures | `GET /entries` (filtres, pagination), `POST /entries/check`, `POST /entries`, `GET` / `PATCH` / `DELETE /entries/{id}`, `POST /entries/{id}/transition`, `POST /entries/{id}/duplicate`, `POST /entries/{id}/reverse` |
| Pièces | `POST /entries/{id}/attachments`, `GET /entries/{id}/attachments/{doc}/url`, `DELETE /entries/{id}/attachments/{doc}` |
| Grand livre | `GET /fiscal-years/{fy}/ledger`, `GET /fiscal-years/{fy}/ledger.csv` |
| Balance | `GET /fiscal-years/{fy}/balance` (`scope`, `auxiliary`, `compare`), `GET /fiscal-years/{fy}/balance.csv` |
| Lettrage | `GET /lettering`, `POST /lettering`, `DELETE /lettering/{id}` |
