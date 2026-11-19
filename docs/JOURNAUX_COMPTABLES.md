# KOFINEX — Journaux comptables (lot 3B, étape A)

## Paramètres d'un journal (`journals`)
| Champ | Règle |
|---|---|
| Code | Majuscules et chiffres, 8 au plus, unique dans l'entreprise |
| Intitulé | Obligatoire |
| Type | Achats, ventes, banque, caisse, opérations diverses, paie, immobilisations, stocks, à-nouveaux |
| Préfixe de numérotation | 12 caractères au plus (majuscules, chiffres, `-`, `_`) ; par défaut, le code suivi d'un tiret |
| Compte de trésorerie | Obligatoire pour un journal de banque ou de caisse, choisi dans le plan de l'entreprise |
| Utilisateurs autorisés | Vide : tous les comptables de l'entreprise ; sinon, liste d'utilisateurs. Les administrateurs de l'organisation gardent l'accès |
| Actif | Un journal désactivé n'accepte plus de nouvelle écriture, ni de soumission ou de validation |

Les codes et paramètres sont propres à chaque entreprise ; aucun journal n'est créé d'office.

## Règles imposées en base
- Un journal qui contient des écritures ne peut pas être supprimé (clé étrangère). Son code, son type et son préfixe de numérotation sont figés ; il peut être désactivé.
- Une écriture d'à-nouveaux (`origin = opening`) ne peut être passée que dans un journal d'à-nouveaux.
- Les restrictions d'utilisateurs sont vérifiées à la création de l'écriture, en base.

## Numérotation (`journal_sequences`)
- Une séquence par journal et par exercice.
- Le numéro est attribué **à la validation** : préfixe + numéro d'ordre sur six chiffres (`VT-000001`). Une écriture non validée n'a pas de numéro définitif.
- La fonction `je_next_number` verrouille la ligne de séquence. L'incrément est annulé avec la transaction s'il y a un échec : il n'y a ni trou ni doublon.
- Unicité garantie par la base : `(journal, exercice, numéro)` et `(journal, exercice, rang)`.
- Les utilisateurs ne peuvent ni écrire dans les séquences ni attribuer un numéro.

## Consultation des mouvements
Les écrans « Écritures » (filtre par journal) et « Grand livre » (filtre par journal) affichent les mouvements d'un journal. Le tableau des journaux indique le nombre d'écritures de chacun.
