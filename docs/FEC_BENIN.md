# KOFINEX — Fichier des Écritures Comptables (FEC) — DGI Bénin

*Rubrique du module Comptabilité (`/companies/{id}/comptabilite/fec`), livrée le 19 novembre 2026. Migration 0016.*

**Texte appliqué** : arrêté n° 1085/MEF/CAB/SGM/DGI/DLC/159SGG20 du 23 avril 2020 portant modalités et normes de présentation du fichier des écritures comptables (FEC). Source : copie numérisée signée de 6 pages, fournie le 19 novembre 2026 et lue page par page. Ce n'est **pas** le FEC français.

L'arrêté précise l'article 1085 ter-1 du Code général des impôts alors en vigueur. Le cahier des charges KOFINEX cite l'article 541 du CGI, sans doute la numérotation du code actuel. Cette correspondance n'a pas été vérifiée.

**Statut des fichiers produits** : un fichier sans anomalie bloquante est déclaré **« Sans anomalie bloquante · points réglementaires à confirmer »**, jamais « conforme », tant que les points du § 6 ne sont pas levés.

## 1. Fonctionnement

| Écran | Contenu |
|---|---|
| Tableau de bord | Écritures de l'exercice, écritures validées, écritures éligibles (validées, sans anomalie bloquante qui leur soit propre), anomalies (bloquantes et avertissements), date et statut de la dernière génération |
| Paramètres | Entreprise et exercice (barre supérieure), période, format TXT ou CSV, jeu de caractères, séparateur des zones (tabulation), fin d'enregistrement, type de comptabilité (engagement ou trésorerie), fractionnement |
| Contrôle de conformité | Exécuté avant toute génération ; aucune écriture n'est modifiée |
| Rapport des anomalies | Gravité, n° d'écriture (lien vers l'écriture), date, journal, compte, nature, description, action recommandée ; export CSV |
| Génération | **Définitive** : refusée s'il reste une anomalie bloquante. **Fichier de travail** : possible malgré des anomalies bloquantes, déclaré « non conforme ». Les deux sont refusés si le fichier ne peut pas être écrit fidèlement (IFU absent ou invalide, aucune écriture, caractère non représentable, tabulation ou saut de ligne dans une zone) |
| Historique | Chaque génération est une nouvelle version, figée en base. On y trouve le ou les fichiers, la documentation (art. 7), les empreintes SHA-256, les anomalies, l'auteur, la date, le format, l'encodage et le nombre de lignes |

Aucune valeur n'est proposée par défaut pour le format, l'encodage et la fin d'enregistrement : l'utilisateur les choisit.

## 2. Règles de l'arrêté appliquées

| Article | Exigence | Mise en œuvre |
|---|---|---|
| 2 | Toutes les écritures comptables validées, par ordre chronologique de validation, après inventaire, par livre comptable | Écritures natives `validated` et `reversed` (une extourne et l'écriture extournée sont toutes deux dans les livres). Ordre : date et heure de validation, puis journal, numéro et rang de ligne. Exercice non clôturé : avertissement |
| 2 | Écritures de report incluses | Écritures `origin = 'opening'` ; absentes alors qu'un exercice précédent existe : bloquant |
| 2 | Ni écritures de centralisation, ni soldes des comptes de charges et de produits | KOFINEX n'en produit pas (clôture non livrée). Point à confirmer (§ 6) |
| 3 | Comptabilités tenues par systèmes informatisés | Écritures natives tenues dans KOFINEX ; un grand livre importé (tenu ailleurs) n'est jamais repris (§ 4) |
| 4 | Fichier plat CSV ou TXT | Extension `.txt` ou `.csv`, organisation séquentielle, sans guillemets |
| 4 | Jeux ASCII, ISO 8859-15 ou EBCDIC | ASCII et ISO 8859-15. Un caractère non représentable est bloquant, sans translittération. EBCDIC non proposé (§ 6) |
| 4 | Une ligne = une écriture comptable, terminée par retour chariot et/ou fin de ligne | Une ligne par ligne d'écriture (mouvement), comme les 18 champs l'imposent (un seul compte et un seul montant par ligne). Fin d'enregistrement CR LF, LF ou CR, au choix. **Aucune ligne d'en-tête** : les noms des champs sont dans la documentation |
| 4 | Zones séparées par une tabulation « ou le caractère « » » | **Tabulation seule** : le second caractère est absent du texte signé (§ 6). Une zone contenant une tabulation ou un saut de ligne est bloquante |
| 4 | Valeurs numériques en caractères, base décimale, signe en premier caractère, virgule décimale, aucun séparateur de milliers ; cadrage et remplissage pour les zones de longueur fixe | « 1234567,50 », « 0,00 », « -12,00 ». L'article 5 ne fixe **aucune longueur** : zones de longueur variable, sans cadrage ni remplissage |
| 4 | Dates AAAAMMJJ ; heures HH:MM:SS | Dates AAAAMMJJ. Aucun des 21 champs n'est une heure. La date de validation est exprimée à l'heure du Bénin (Africa/Porto-Novo) |
| 5 | 18 premiers champs, dans l'ordre, et valeurs obligatoires | Voir § 3. Zone obligatoire vide : bloquant |
| 5 | NumCompte : trois premiers caractères numériques, normes du plan SYSCOHADA | Contrôlé. Le compte doit être rattaché au plan du référentiel publié |
| 5 | LibCompte : nomenclature du plan SYSCOHADA | Intitulé différent de celui du référentiel pour le même numéro : avertissement (un sous-compte a son propre intitulé) |
| 5 | Montant / Sens si le système ne tient pas MontDebit et MontCredit | Non proposé : KOFINEX tient débit et crédit séparément |
| 5 | Trésorerie : champs 19 Date Règlement (date, obligatoire), 20 Mode Règlement (obligatoire), 21 NatOp (facultatif) | 21 colonnes produites. Les champs 19 et 20 ne sont pas tenus par KOFINEX : bloquant, et jamais remplis par une valeur inventée |
| 5 | Écritures de reprise : premiers numéros, LibEcriture = « REPORT » | LibEcriture = REPORT. Bloquant si une écriture ordinaire porte, dans le même journal, un numéro inférieur, ou si elle a été validée avant les écritures de report |
| 6 | Fichier unique FEC_IFU_AAAAMMJJ (date de clôture) ; si nécessaire FEC_IFU_AAAAMMJJ_X, X de 1 à n | IFU de l'entreprise (`companies.tax_id`), jamais modifié automatiquement. Fractionnement à la demande, avec un nombre maximal de lignes (l'arrêté ne fixe pas de seuil). La base vérifie les noms et la suite des suffixes |
| 6 | Contenu portant sur la période soumise à vérification | Période choisie, comprise dans l'exercice |
| 7 | Documentation : nom, description, signification de chaque champ, jeu de caractères, séparateurs des champs et des enregistrements | Fichier `DOCUMENTATION_FEC_IFU_AAAAMMJJ.txt`, produit et archivé avec chaque génération |
| 9 | Conservation (art. 1096 nouveau-1 du CGI) | Copie immuable en base et dans le stockage. La durée de conservation de l'article 1096 n'est pas reprise ici (§ 6) |
| 6, 8 | Remise sur CD, DVD, clé USB ou disque externe ; procès-verbal du vérificateur | Hors du logiciel : l'utilisateur télécharge le fichier |

## 3. Champs (article 5)

| N° | Champ | Obligatoire | Format | Origine dans KOFINEX |
|---|---|---|---|---|
| 1 | CodeJournal | OUI | | `journals.code` |
| 2 | LibJournal | OUI | | `journals.label` |
| 3 | NumEcriture | OUI | | `journal_entries.number`, attribué à la validation, continu par journal et par exercice |
| 4 | DateEcriture | OUI | AAAAMMJJ | `journal_entries.entry_date` |
| 5 | NumCompte | OUI | 3 premiers caractères : chiffres SYSCOHADA | `journal_entry_lines.account_number` |
| 6 | LibCompte | OUI | nomenclature SYSCOHADA | `company_accounts.label` |
| 7 | NumCompteAux | NON | | `third_parties.code` de la ligne |
| 8 | LibCompteAux | NON | | `third_parties.name` |
| 9 | RefPiece | OUI | | `journal_entries.piece_ref` |
| 10 | DatePiece | OUI | AAAAMMJJ | `journal_entries.piece_date` |
| 11 | LibEcriture | OUI | | Libellé de la ligne, à défaut de l'écriture ; « REPORT » pour les écritures de report |
| 12 | MontDebit | OUI | | Débit de la ligne (0,00 si la ligne est au crédit) |
| 13 | MontCredit | OUI | | Crédit de la ligne (0,00 si la ligne est au débit) |
| 14 | LetEcriture | NON | | `letterings.code` |
| 15 | DateLetEcriture | NON | AAAAMMJJ | Date du lettrage (`letterings.created_at`, heure du Bénin) |
| 16 | DateValid | OUI | AAAAMMJJ | `journal_entries.validated_at`, heure du Bénin |
| 17 | MontDevise | NON | | `journal_entry_lines.currency_amount`, si devise |
| 18 | CodeDevise | NON | | `journal_entry_lines.currency` |
| 19 | Date Règlement | OUI (trésorerie) | AAAAMMJJ | Non tenu |
| 20 | Mode Règlement | OUI (trésorerie) | | Non tenu |
| 21 | NatOp | NON | | Non tenu |

L'arrêté qualifie MontCredit de « montant au débit » : c'est manifestement une erreur de rédaction du tableau. Le champ porte le montant au crédit.

## 4. Périmètre des écritures et doublons
- Seules les écritures natives (`journal_entries`, `journal_entry_lines`) **validées** sont reprises. Elles sont lues par `native_ledger.posted`, le même lecteur que le grand livre et les balances natifs, sans copie ni second système de journaux.
- Brouillons, écritures soumises, en revue et rejetées : non reprises, signalées (avertissement, avec leur nombre).
- **Grand livre importé** : jamais repris. Ses écritures sont tenues dans un autre logiciel, qui doit produire le FEC. Il est signalé quand il coexiste avec des écritures natives, et bloquant s'il est la seule source. Aucun doublon n'est donc possible entre les deux sources.
- Une ligne d'écriture ne figure qu'une fois par fichier : contrôle du moteur et contrainte d'unicité en base.
- **Traçabilité** : `fec_export_lines` relie chaque ligne n du fichier à la ligne d'écriture source (`GET …/exports/{id}/trace?row=n`). La base refuse toute ligne qui ne provient pas d'une écriture validée de l'exercice.

## 5. Contrôles

| Gravité | Contrôles |
|---|---|
| Bloquant | IFU absent ou non alphanumérique ; aucune écriture validée ; seule source = grand livre importé ; journal sans code ou libellé ; écriture sans numéro ; rupture ou doublon de numérotation (par journal, sur l'exercice) ; écritures de report absentes (exercice précédent existant) ou ne portant pas les premiers numéros ; date hors exercice ; compte hors plan SYSCOHADA ; compte sans intitulé ; référence ou date de pièce absente ; libellé absent ; montant invalide ; écriture déséquilibrée ; date de validation absente ; compte collectif sans tiers ; devise incomplète ; zone obligatoire vide ; tabulation ou saut de ligne dans une zone ; caractère non représentable ; champs de trésorerie non tenus ; ligne en double |
| Avertissement | Pays autre que le Bénin ; référentiel autre que le SYSCOHADA révisé ; exercice non clôturé ; écritures non validées ; grand livre importé non repris ; intitulé différent de la nomenclature ; tiers sans nom ; ligne lettrée sans date de lettrage |

Une écriture validée n'est jamais modifiée pour la rendre conforme. L'action recommandée est l'extourne puis la ressaisie, ou la correction du paramétrage (compte, tiers, journal, IFU).

## 6. Points restant à confirmer
1. **Second caractère séparateur** (art. 4) : le texte signé indique « une tabulation ou le caractère « » », sans le caractère. Seule la tabulation est proposée.
2. **EBCDIC** (art. 4) : autorisé, mais la page de code n'est pas précisée. Non proposé.
3. **Continuité de NumEcriture** (art. 5, « numéro séquentiel continu ») : KOFINEX numérote par journal et par exercice. Le texte ne dit pas si la continuité s'entend par journal ou pour l'ensemble du fichier.
4. **Écritures de centralisation et soldes des comptes de gestion** (art. 2) : non produites par KOFINEX. Une écriture saisie manuellement à cette fin ne peut pas être reconnue automatiquement.
5. **Durée de conservation** (art. 9, renvoi à l'article 1096 nouveau-1 du CGI) : texte non consulté. L'archive est immuable et n'est jamais supprimée par KOFINEX.
6. **Article 541 du CGI** cité par le cahier des charges et article 1085 ter-1 cité par l'arrêté : correspondance non vérifiée.

Tant que ces points restent ouverts, la constante `SPEC_CONFIRMED` du moteur est fausse et la base refuse le statut « conforme » (`CHECK (compliance <> 'compliant' OR spec_confirmed)`).

## 7. Architecture

| Couche | Fichier |
|---|---|
| Base | `backend/sql/0016_fec_benin.sql` (Alembic `0016`) : `fec_exports`, `fec_export_lines`, bucket privé `fec` |
| Moteur pur | `app/engines/accounting/fec_bj.py` : spécification (art. 4 à 7), contrôles, rendu, fractionnement, documentation, empreintes |
| Service | `app/services/fec.py` : lecture des livres (via `native_ledger.posted`), contrôle, génération, archivage, téléchargement avec vérification d'empreinte |
| API | `app/api/v1/fec.py` : préfixe `/api/v1/companies/{id}/accounting/fec` — `spec`, `dashboard`, `check`, `exports` (création, liste, détail), `exports/{id}/file[?part=n]`, `exports/{id}/documentation`, `exports/{id}/anomalies.csv`, `exports/{id}/trace?row=n` |
| Interface | `frontend/app/(app)/companies/[companyId]/comptabilite/fec/page.tsx`, `lib/fec-types.ts` ; onglet « FEC » de la comptabilité, affiché aux seuls utilisateurs autorisés |
| Modèles | `app/models/fec.py` |

Seule modification d'un fichier livré dans le lecteur des écritures : `native_ledger.posted` renvoie en plus, sans rien retirer, la date de pièce, la date de validation, le journal, le rang de ligne, le tiers et la devise. Les autres modifications sont des ajouts : permission `fec.export`, droit `fec` dans les paramètres comptables, onglet de navigation.

**Volumétrie** : la génération est synchrone et le fichier est construit en mémoire, comme les rapports du lot 11. Pour de très gros volumes, un passage en tâche de fond (Celery, déjà présent) reste à faire.

## 8. Sécurité
- Permission `fec.export` : comptables et administrateurs de l'entreprise, les rôles qui voient déjà le détail de la paie, puisque le FEC contient toutes les écritures. Les autres rôles (contrôleur, analyste, auditeur, lecteur) n'y ont pas accès.
- **RLS** : la même règle est appliquée en base (`authz.has_company_role(company_id, ARRAY['accountant'])`, administrateurs compris), sur les tables et sur le bucket `fec`.
- **Gardes en base** :
  - droit vérifié en premier, pour ne rien révéler à un tiers ;
  - auteur = utilisateur authentifié ;
  - version suivante sous verrou ;
  - période comprise dans l'exercice ;
  - nom portant la date de clôture ;
  - noms des fichiers scindés `_1` à `_n` ;
  - fichiers rangés sous l'organisation et l'entreprise ;
  - total des lignes cohérent ;
  - génération définitive sans anomalie bloquante ;
  - ni modification ni suppression, y compris par la clé de service ;
  - acteur IA refusé.
- **Journal** : chaque génération (`fec_exports` dans `audit_logs`, et `fec.generated`) et chaque téléchargement (`fec.downloaded`) sont tracés. Un fichier dont l'empreinte ne correspond plus n'est pas servi.

## 9. Tests

| Fichier | Contenu | Exécuté ici |
|---|---|---|
| `backend/tests/engines/test_fec_bj.py` | 20 tests : ordre des 18 champs et des champs 19 à 21 ; valeurs obligatoires de l'art. 5 ; formats des dates et des montants (virgule, signe, sans milliers, refus du flottant) ; date de validation à l'heure du Bénin ; tabulation, sans en-tête, fins CR LF / LF / CR ; ISO 8859-15 et refus en ASCII ; nom et fractionnement `_1.._n` (contenu identique, empreinte globale) ; ordre chronologique ; « points à confirmer » et jamais « conforme » ; REPORT (libellé, rang, présence) ; numérotation (ruptures, doublons, ligne en double) ; champs obligatoires bloquants ; comptes SYSCOHADA et nomenclature ; écritures non validées et grand livre importé ; trésorerie (21 colonnes, jamais remplies) ; séparateur dans une zone et IFU ; équilibre ; devise et lettrage ; documentation (art. 7) ; rendu déterministe | **oui, 20 réussis** |
| `backend/tests/sql/test_fec_benin.sql` | 33 contrôles : droits (contrôleur, autre entreprise sans divulgation, autre organisation), auteur, version, nommage et date de clôture, IFU non alphanumérique, séparateur, fin d'enregistrement, période, conformité (définitive non bloquée, cohérence, « conforme » impossible), versions conservées, fractionnement (suffixes, total, rangement), immutabilité (utilisateur et service), traçabilité (validées seulement, doublon, mauvaise écriture), acteur IA, journal, isolation, bucket privé | **oui, 33 réussis** |
| `backend/tests/integration/test_fec_api.py` | Parcours API : droits, tableau de bord (3 / 2 / 1), contrôle (IFU, date de pièce, non validées), paramètres refusés, définitive refusée (409), fichier de travail non conforme, définitive scindée « points à confirmer », téléchargements et contenu, documentation, anomalies, traçabilité, historique, accès refusés | **non** : compilé et vérifié par ruff ; FastAPI et SQLAlchemy absents de cet environnement (à exécuter en CI) |
