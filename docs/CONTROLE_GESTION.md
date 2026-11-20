# KOFINEX — Contrôle de gestion (lot 5, puis évolution « pilotage »)

Interface : fiche entreprise → **Contrôle de gestion** (`/companies/{id}/gestion`), en quatre espaces (§ 11) :
- **Tableau de bord financier** : performance financière, trésorerie, masse salariale ;
- **Tableau de bord budgétaire** : budget et réalisé ;
- **Gestion budgétaire** : budgets et prévisions (avec import Excel / CSV), centres et saisies ;
- **Analyse et aide à la décision** : points d'attention, coûts, marges et seuils, projections, synthèse des modèles.

Aucune règle de gestion n'est présumée :
- clés de répartition, parts variables, standards et taux d'évolution sont **saisis par l'utilisateur** et restitués avec chaque résultat ;
- les calculs se font en `Decimal` (34 chiffres) dans `backend/app/engines/management/` ;
- la restitution est arrondie au centime.

## 1. Données

| Élément | Table | Remarques |
|---|---|---|
| Centres de coûts | `cost_centers` (+ `description`, `work_unit`) | Hiérarchie parent → enfants. Types : principal, auxiliaire, structure, profit, investissement. |
| Saisies analytiques | `cost_entries` | Coût daté, affecté à un centre (et à un compte, facultatif). Refusées sur un exercice clôturé (*trigger*). Seule source de réalisé **mensuel** tant que le grand livre n'est pas importé. |
| Budgets et prévisions | `budgets` (+ `scenario`, `assumptions`, `notes`, `source_budget_id`, `submitted_*`), `budget_lines` | Ligne = racine de comptes de charges ou de produits et/ou centre ; période 0 (annuel) ou 1 à 12 (mois de l'exercice). |
| Modèles de coûts | `costing_models` (nouvelle table) | Types `full_cost`, `cvp`, `standard_cost`. Paramètres en `jsonb` validés par le moteur, résultats figés à la validation, balance utilisée tracée. |

`budget_actuals` (schéma initial) n'est pas utilisé : le réalisé est **calculé à la demande** à partir de la balance validée et des saisies, ce qui évite tout réalisé périmé.

## 2. Budgets, réalisations, écarts
- **Réalisé**, d'après la nature de la racine lue dans le plan de comptes de l'exercice :
  - charge : solde débiteur net des comptes de la racine ;
  - produit : solde créditeur net ;
  - les comptes de bilan sont refusés.
- **Lignes par centre** : réalisé = saisies analytiques du centre et de ses sous-centres, mois par mois.
- **Écart et appréciation** :
  - écart = réalisé − budget ; taux de réalisation = réalisé / budget ;
  - pour une charge, un réalisé inférieur au budget est *favorable* ; pour un produit, un réalisé supérieur l'est ;
  - l'appréciation porte sur le montant, pas sur la cause.
- **Racines qui se chevauchent** (par exemple 60 et 601) : elles sont signalées et les totaux par nature ne sont pas calculés, pour ne pas compter deux fois.
- **Circuit** : brouillon → soumis → approuvé → archivé ; un budget soumis peut être renvoyé en brouillon.
  - Seul un brouillon est modifiable : la base de données refuse toute autre modification (*triggers*).
  - L'approbation se fait **par une autre personne que l'auteur**, sauf si l'auteur est administrateur de l'organisation. La règle est appliquée par l'API et par la base.
  - Pour modifier un budget approuvé, on crée une nouvelle version.
- **Prévision par hypothèses** : montant = réalisé d'un exercice source × (1 + taux saisi).
  - Répartition annuelle, ou en 12 mensualités égales ; l'arrondi est porté sur le 12e mois.
  - Les hypothèses sont enregistrées dans `assumptions`.

## 3. Coûts complets (centres d'analyse)
1. **Charges incorporées** : racines de la balance, avec exclusions possibles, réparties par clés vers des centres ou directement vers des objets (charges directes). S'y ajoutent les charges supplétives saisies. Les charges non citées sont les *non incorporées*.
2. **Répartition secondaire** des centres auxiliaires, **prestations réciproques comprises**. Le système linéaire est résolu exactement, en fractions. Un système sans solution unique est refusé.
3. **Imputation des centres principaux** :
   - par unités d'œuvre : coût de l'UO = total du centre / volume ;
   - ou par clés vers les objets.

   La **différence d'imputation** (sous- ou suractivité) est restituée.
4. **Coût de revient** par objet, coût unitaire, coût des ventes (coût unitaire × quantité vendue), coût de la production non vendue, marge, puis résultat analytique = Σ marges − différences d'imputation.

**Contrôle bloquant pour la validation** : charges incorporées = coûts imputés + différences d'imputation.

## 4. Marges et seuil de rentabilité (coût-volume-profit)
- **Données** : chiffre d'affaires (racines de produits) et classement des racines de charges avec leur part variable en %. Les charges non classées sont signalées.
- **Formules** :
  - marge sur coût variable (MCV) = chiffre d'affaires − charges variables ; taux de MCV ;
  - résultat = MCV − charges fixes ;
  - seuil de rentabilité = charges fixes / taux de MCV ;
  - point mort = seuil / chiffre d'affaires × durée réelle de l'exercice en jours ; la date est celle du jour au cours duquel le seuil est atteint ;
  - marge de sécurité et indice de sécurité ;
  - levier opérationnel = MCV / résultat.
- **Hypothèses du modèle** : linéarité, charges fixes constantes, activité régulière.

## 5. Coûts préétablis
Pour chaque élément, sur la production réelle :
- écart sur quantité = (Qr − Qs) × Cs ;
- écart sur prix = (Cr − Cs) × Qr ;
- écart global = somme des deux (vérifiée).

Un écart positif est défavorable.

## 6. Projections
Une racine de comptes est projetée sur 1 à 5 exercices à partir des réalisés des exercices dont la balance est validée :
- **tendance linéaire** (moindres carrés, R²), à partir de 3 exercices ;
- **taux de croissance annuel moyen**, à partir de 2 exercices et avec des valeurs positives.

Ce sont des extrapolations présentées comme telles, pas des prévisions validées.

## 7. Tableau de bord
`GET /companies/{id}/fiscal-years/{fy}/management-dashboard` reprend uniquement des résultats déjà calculés :
- **budget de référence** : approuvé, sinon le plus avancé. On y trouve les totaux budget / réalisé, le graphique, et les cinq écarts défavorables les plus importants ;
- **prévision**, présentée de la même façon ;
- **coûts saisis** par centre et par mois ;
- **coûts de revient et marges** par objet ;
- **seuil de rentabilité**, point mort et indice de sécurité ;
- **écarts sur coûts préétablis**.

Un résultat périmé (paramètres ou balance modifiés depuis le calcul) est signalé.

## 8. Permissions
| Action | Rôles |
|---|---|
| Lecture | Tous les membres de l'entité |
| Centres, saisies, budgets, modèles (`budget.write`) | Comptable, contrôleur, administrateurs de l'organisation |
| Approuver ou renvoyer un budget, valider un modèle, archiver (`budget.approve`) | Contrôleur, administrateurs de l'organisation |

Toutes les actions sont journalisées (`audit_logs` : `budget.*`, `cost_center.*`, `cost_entry.*`, `costing_model.*`).

## 9. Tests
| Fichier | Contenu |
|---|---|
| `tests/engines/test_management.py` | Cas de référence calculés à la main : écarts et sens, chevauchements, centres et mois, prévision, prestations réciproques exactes, coût complet complet (coûts, marges, sous-activité, contrôle), seuil et date du point mort, écarts prix/quantité, tendance et TCAM |
| `tests/sql/test_management_control.sql` | Circuit, gel, séparation auteur / approbateur, modèles figés, lecteur, isolation, exercice clôturé |
| `tests/integration/test_management_api.py` | Parcours API complet (à exécuter en CI) |

## 10. Limites connues
- **Réalisé mensuel comptable** : tiré du grand livre validé de l'exercice (à-nouveaux exclus) pour les lignes par racine de comptes ; le réalisé annuel reste celui de la balance et tout écart entre les deux est signalé (voir `GRAND_LIVRE.md`). Sans grand livre, seules les lignes par centre ont un réalisé mensuel.
- **Coûts complets** : pas de valorisation des stocks initiaux. Le coût des ventes utilise le coût unitaire de l'exercice.
- **Saisies analytiques** : saisie manuelle uniquement pour l'instant (pas d'import de fichier).

---

## 11. Pilotage (évolution du contrôle de gestion, 18 novembre 2026)

### 11.1 Architecture
- **Couche de lecture** : `services/steering.py` (sources, classification, tableaux de bord) et `engines/management/steering.py` (calculs purs, Decimal).
- **API** : `api/v1/steering.py`, préfixe `/companies/{id}`.
- **Réutilisé sans le réécrire** :
  - le moteur des états `build_statements` et le `Calculator` de la bibliothèque KOFINEX-STD-1, appliqués à la balance d'une période ;
  - le moteur budgétaire `track` du lot 5 ;
  - les correspondances `statements._select` et les concepts du référentiel ;
  - les lecteurs de fichiers et `parse_amount` des imports.
- **Base de données** : une seule table ajoutée, `management_alert_settings` (migration 0015, seuils par entreprise).

### 11.2 Sources des données
| Source | Contenu | Granularité |
|---|---|---|
| `native` | écritures natives validées ou extournées (l'extourne neutralise l'écriture d'origine) | écriture, ligne, tiers, mois |
| `imported` | grand livre importé et validé (un nouvel import **remplace** le précédent ou le **complète** sans doublon ; deux imports ne s'additionnent jamais) | ligne, compte auxiliaire, mois |
| `trial_balance` | balance importée | montants annuels uniquement |

- **Règle de priorité** (`auto`) : les écritures natives s'il y en a au moins une validée sur l'exercice, sinon le grand livre importé, sinon la balance.
- **Pas de mélange** : les sources ne sont jamais additionnées. L'utilisateur peut imposer une source ; celle qui est retenue est affichée.
- **Données non intégrées** : brouillons, écritures soumises et écritures rejetées n'entrent jamais dans les indicateurs. Leur nombre est affiché.
- **Modules sources** : Achats, Ventes, Trésorerie, Stocks, Immobilisations, Paie et Fiscalité n'existent pas encore (lot 3B, étape C). Leurs opérations alimenteront le pilotage par les écritures qu'ils généreront, sans autre branchement.

### 11.3 Actualisation
- **Recalcul à chaque demande** : les indicateurs sont recalculés à partir des sources validées. Il n'y a ni copie des écritures ni valeur stockée qui pourrait se périmer, et l'enregistrement comptable n'est jamais bloqué par un tableau de bord.
- **Filigrane** (`GET …/steering/watermark`) :
  - contenu : nombre et date de la dernière écriture native validée, dernière écriture intégrée, écritures en attente, imports actifs, état de l'exercice, et un jeton ;
  - l'interface l'interroge chaque minute et signale « Nouvelles données disponibles » quand le jeton change ;
  - « Actualiser » relance le calcul.
- **Calcul idempotent et relançable** : un même état des sources donne le même résultat.
- **Affichage** : date du calcul, source, dernière opération intégrée, écritures en attente, période couverte, réserves.

### 11.4 Classification des comptes (aucun numéro codé en dur)
- **Nature et intitulé** : plan de comptes du référentiel, racine la plus longue.
- **Rubrique** : ligne des états, par les correspondances du référentiel.
- **Ensembles de comptes** : comptes rattachés aux lignes qui composent un concept du référentiel. Pour SYSCOHADA révisé :

| Ensemble | Concept du référentiel | Ligne |
|---|---|---|
| AO | `resultat_activites_ordinaires` | XG |
| HAO | `resultat_hao` | XH |
| Autres (participation, impôt) | le reste de `resultat_net` | XI |
| Chiffre d'affaires | `chiffre_affaires` | XB |
| Personnel | `charges_personnel` | RK |
| Trésorerie | `tresorerie_actif` + `tresorerie_passif` | — |
| Clients | `creances_clients` | — |
| Fournisseurs | `dettes_fournisseurs` | — |

- **Vérification sur le référentiel réel** (`tests/engines/test_steering_referential.py`) :
  - les comptes 476 (produits constatés d'avance) ne sont pas du chiffre d'affaires ;
  - marge AO = ligne XG, marge HAO = XH, résultat = XI.

### 11.5 Tableau de bord financier
- **Indicateurs principaux** : marge AO, marge HAO, marge totale, charges AO, produits AO.
  - Marge AO = produits AO − charges AO ; marge HAO = produits HAO − charges HAO.
  - Marge totale = AO + HAO, avant participation et impôt.
- **Indicateurs complémentaires** : CA, EBE, résultat d'exploitation, résultat financier, RAO, résultat HAO et résultat net, par la bibliothèque appliquée à la balance de la période ; total des charges et total des produits.
  - L'EBITDA n'est pas présenté.
  - Un écart entre marge AO et RAO des états est signalé.
- **Top 10** : produits AO, charges AO, produits HAO, charges HAO, clients, fournisseurs.
  - Le pourcentage est rapporté au **total de la catégorie**.
  - Clients : chiffre d'affaires des écritures portant sur un seul compte client.
  - Fournisseurs : charges des écritures portant sur un seul fournisseur.
  - Les règlements, avances et transferts n'ont ni produit ni charge, donc ils ne faussent pas le classement. Les avoirs viennent en déduction.
  - Écritures sans tiers ou à plusieurs tiers : montant « non attribuable » et taux de couverture affichés.
  - Sans tiers dans la source, le classement est déclaré indisponible.
- **Graphiques** : charges et produits AO / HAO (N et N-1) ; évolution des marges ; CA, charges et résultat par mois ; tableau des variations mensuelles.
- **Périodes** :
  - vues : exercice, mois, cumul depuis le début de l'exercice, période personnalisée bornée à l'exercice ;
  - le calcul suit les dates réelles de l'exercice, même décalé ;
  - **N-1** : période équivalente, même rang de mois et même jour. Pour un exercice décalé : juillet 2024 – février 2025 face à juillet 2023 – février 2024.
- **Détail** (`…/steering/drilldown`) : chaque carte, ligne de Top 10, compte de trésorerie ou ligne budgétaire ouvre les comptes, puis les écritures (date, journal, numéro, pièce, libellé, tiers). Pour les écritures natives, chaque ligne mène à la fiche de l'écriture.

### 11.6 Qualité des données
- **Réserves affichées** : comptes de gestion non rattachés aux soldes, comptes sans nature, concepts absents, correspondances ambiguës, exercice non clôturé (résultats **provisoires**), écritures en attente, absence d'écriture d'inventaire, données auxiliaires manquantes.
- **Niveau** : élevé, moyen ou faible.
- **Donnée absente** : elle s'affiche « — », jamais 0.

### 11.7 Tableau de bord budgétaire
- **Budget de référence** : l'approuvé, sinon le plus avancé ; on peut en choisir un autre.
- **Réalisé** : celui de la source retenue (natif en priorité), via le moteur `track` du lot 5.
- **Indicateurs** :
  - budget initial (version 1), budget révisé (version courante si elle est supérieure à 1), budget approuvé ;
  - réalisé comptable et réalisé analytique (lignes par centre) ;
  - écart = réalisé − budget ; taux d'exécution = réalisé / budget × 100, non calculé si le budget est nul ;
  - budget disponible = budget − réalisé (les engagements ne sont pas encore suivis, et c'est affiché) ;
  - prévision à terminaison et écart prévisionnel.
- **Appréciation selon la nature** : pour une charge, un réalisé inférieur au budget est favorable ; pour un produit, un réalisé supérieur l'est.
- **Prévision à terminaison** : présentées comme des extrapolations.
  - « budget restant » = réalisé cumulé + budget des mois restants ;
  - « tendance » = réalisé cumulé / mois écoulés × mois de l'exercice.
- **Tableau mensuel** : budget, réalisé, écart, taux et appréciation, en vue mensuelle ou cumulée. Un budget annuel non ventilé est réparti également pour la lecture.
- **Alertes** (information, avertissement, critique), à seuils paramétrables par l'entreprise :
  - dépassement ;
  - risque de dépassement (tendance) ;
  - consommation anormalement rapide (avance sur le temps écoulé) ;
  - budget largement consommé ;
  - recettes en retrait ;
  - écart important sur un centre.

  Chaque alerte indique la ligne, la racine ou le centre, le budget, le réalisé et le taux.
- **Top 10** : dépassements de charges, sous-exécution des recettes, économies, budgets les plus consommés, écarts par centre.
- **Seuils par défaut** (à adapter, ce ne sont pas des normes) :
  - information à 80 % de consommation ;
  - avertissement au-delà de 100 %, critique à partir de 110 % ;
  - avance de 15 points sur le temps écoulé ;
  - retard des recettes de 25 points ;
  - écart d'un centre de 10 % ;
  - variation N / N-1 de 10 % ;
  - concentration sur un tiers de 30 %.

### 11.8 Gestion budgétaire
- **Circuit inchangé** : brouillon → soumis → approuvé → archivé, séparation auteur / approbateur, nouvelle version pour modifier un budget approuvé.
- **Nouveauté : import Excel / CSV des lignes d'un brouillon** (`POST /budgets/{id}/lines/import`, avec contrôle préalable `dry_run`).
  - Deux présentations : en lignes (compte ou centre, libellé, période, montant), ou en colonnes (M1 à M12 et/ou annuel).
  - L'import passe par le même contrôle que la saisie : nature de la racine, centre existant, pas de mélange annuel / mensuel, période unique.
  - Il est journalisé (`budget.lines_imported`, avec l'empreinte du fichier).

### 11.9 Trésorerie et masse salariale
- **Trésorerie** :
  - solde initial (à-nouveaux et mouvements antérieurs), encaissements, décaissements, solde final, variation ;
  - contrôle affiché : solde final = initial + encaissements − décaissements ;
  - une écriture dont toutes les lignes portent sur la trésorerie est un **transfert interne**, exclu des flux ;
  - détail par compte, par catégorie de contrepartie et par mois ;
  - banque et caisse sont distinguées par le compte de contrepartie des journaux de l'entité de type banque ou caisse, quelle que soit la source ; un compte de trésorerie qui n'est la contrepartie d'aucun journal est classé « non déterminé » et une note le signale ;
  - pas de prévision : aucune donnée prévisionnelle n'existe dans KOFINEX.
- **Masse salariale** :
  - comptes du concept « charges de personnel », par compte et par mois ; ratio masse salariale / CA ;
  - l'effectif et le détail individuel sont indisponibles (aucune donnée RH ni de paie détaillée) ;
  - le détail des écritures de personnel exige la permission `payroll.detail` (comptables et administrateurs). Ailleurs, ces lignes sont masquées dans le détail.

### 11.10 Analyse et aide à la décision
- **Points d'attention factuels** : hausse des charges, baisse des produits, dégradation de la marge AO, hausse de la masse salariale, concentration sur un client ou un fournisseur, données auxiliaires manquantes, dégradation de la trésorerie, alertes budgétaires, réserves de fiabilité.
- **Contenu de chaque point** : intitulé, indicateur, valeur observée, référence, écart, période, gravité, explication, source et point d'attention proposé.
- **Aucune cause présumée.** L'IA n'est pas appelée par cet écran.

### 11.11 Permissions
| Action | Permission |
|---|---|
| Consulter les tableaux de bord et le détail (hors lignes de rémunération) | membres de l'entité |
| Détail des écritures de personnel | `payroll.detail` (comptables, administrateurs) |
| Seuils d'alerte | `budget.approve` (contrôleurs, administrateurs), RLS et journal d'audit (`management.thresholds`) |
| Import d'un budget | `budget.write` |

### 11.12 Correctif du lot 5
Le plan de comptes enregistre les natures `expense` / `income`, alors que le moteur budgétaire attendait `charge` / `produit`. Sur des données réelles, le suivi aurait refusé toute ligne. La correspondance est désormais faite dans `services/management.chart_natures`.

### 11.13 Tests
| Fichier | Contenu | Exécuté ici |
|---|---|---|
| `tests/engines/test_steering.py` | Écarts avec le modèle Excel (montants nets, impôt hors HAO, tiers sur montants facturés), périodes (exercice décalé, N-1 équivalent), AO / HAO, Top 10, clients et fournisseurs (règlements exclus, avoirs déduits), trésorerie (transfert interne, contrôle), masse salariale, prévision, alertes à seuils, classements, tableau mensuel, import de budget | oui, réussi |
| `tests/engines/test_steering_referential.py` | Classification sur le référentiel SYSCOHADA réel ; marge AO = XG, HAO = XH, résultat = XI | oui, réussi |
| `tests/sql/test_management_steering.sql` | Seuils : droits, cohérence, journal, IA, isolation (8 contrôles) | oui, réussi |
| `tests/engines/test_steering_fixture.py` | Pré-validation du scénario d'intégration avec le référentiel fictif (classement attendu de chaque compte) | oui, réussi |
| `tests/engines/test_ledger_complement.py` | Import complémentaire : doublons écartés sans double comptage, écriture modifiée refusée, renumérotation, mois ajoutés / déjà importés (4 tests) | oui, réussi |
| `tests/engines/test_reporting.py` (ajout) | Régression : archives Excel et Word datées de la génération, et non de l'horloge | oui, réussi |
| `tests/integration/test_steering_api.py` | Cas 2 (actualisation, extourne), 3 (budget approuvé par un autre utilisateur, réalisé natif, alertes), 5 (vues : Top 10, trésorerie banque, masse salariale, analyse, détail d'un tiers, erreurs 422, source native / balance), 6 (sécurité) ; import de budget (simulation, erreurs, PDF refusé, budget non brouillon) et seuils (403 / 422) | non : compilé et vérifié par ruff ; FastAPI et SQLAlchemy absents ici |
| `tests/integration/test_ledger_complement_api.py` | Cas 4 : complément sans grand livre actif refusé ; complément (4 reprises, 4 doublons, 2 ajouts) sans double comptage (produits 1 500 et non 2 700) ; filigrane modifié ; écriture modifiée refusée (409) ; fichier correctif en remplacement ; historique des imports | non : compilé ; les comptages attendus ont été obtenus en exécutant le moteur sur les mêmes fichiers |

Les tests d'intégration doivent être exécutés en CI (ou sur un poste disposant des dépendances du backend).

### 11.14 Limites et points à valider
- **Cas de test 1 (facture d'achat)** : attend le module Achats (lot suivant, non engagé).
- **Cas de test 4 (import complémentaire ou correctif)** : traité (voir `docs/GRAND_LIVRE.md`).
  - option « Effet de l'import » : *remplacer* (par défaut ; fichier complet ou correctif) ou *compléter* ;
  - en complément, le résultat est le grand livre validé **plus** les seules lignes nouvelles : une ligne identique (journal, numéro, date, compte, auxiliaire, montants, libellé normalisé) est écartée comme doublon (`DUPLICATE_OF_ACTIVE`) ; une écriture déjà importée dont le contenu diffère est refusée (`ENTRY_CONFLICT`, bloquant : passer par un remplacement) ;
  - les mois ajoutés et les mois déjà importés qui reçoivent des lignes nouvelles sont signalés ;
  - la validation est refusée si le grand livre actif a changé depuis la lecture du complément ;
  - rien n'est jamais additionné deux fois : un complément validé devient l'unique import actif, l'ancien passe « superseded » et reste consultable. Annuler un complément revient à valider de nouveau un fichier de remplacement ; aucune table n'a été créée (option conservée dans les options de l'import).
- **Engagements** (commandes) : non suivis, faute de module Achats ; rien n'est simulé.
- **Départements et projets** : aucun axe configuré dans les données ; seuls les centres de coûts sont proposés.
- **Changement de plan entre deux exercices** : chaque exercice est classé avec son propre référentiel. Les comptes de N-1 absents de N sont signalés ; aucune correspondance automatique entre plans n'est appliquée.
- **Modèle Excel de référence** : examiné et rapproché (§ 11.15) ; les décisions qui restent sont listées dans ce paragraphe.
- **Seuils par défaut** : à valider par l'entreprise.
- **Écriture à plusieurs tiers clients ou fournisseurs** : non attribuée. Une règle de répartition reste à décider si nécessaire.


### 11.15 Rapprochement avec le modèle Excel « 2. Tableau de bord financier.xlsm »
**Contenu du modèle.**
- Onglet « Tdb » : 5 indicateurs (marges AO, HAO et totale, charges AO, produits AO) et 6 Top 10 (rang, libellé, %, montant, barre).
- Onglet « Analyse » : tableaux croisés par type (Produit, CHARGES, Client, Fournisseur), et marge par mois.
- Onglet « Grands Livres » : compte, date, journal, numéro, libellé, débit, crédit, type.
- Onglet « Donnees » : plan comptable et tiers.

**Fonctions déjà couvertes.**
- Les 5 indicateurs et les 6 Top 10.
- Le pourcentage rapporté au total de la catégorie : 100 % pour les produits AO, 92,6 % pour le Top 10 des charges AO.
- La marge mensuelle, les filtres de mois, le plan et les tiers.

**Contrôle chiffré.** Le moteur a été appliqué en mémoire au grand livre du fichier ; aucune donnée du fichier n'est conservée dans le projet. Juillet 2014 est le mois affiché par l'onglet « Tdb ».

| Indicateur | Modèle Excel | KOFINEX | Explication |
|---|---:|---:|---|
| Charges AO | 482 793 193,58 | 482 793 193,58 | identiques |
| Produits AO | 478 826 546,75 | −84 686 106,90 | le modèle additionne les seuls **crédits** des comptes de produits ; KOFINEX retient le **net**, donc les extournes en OD des factures à établir et des produits constatés d'avance (comptes 705…) viennent en déduction |
| Marge HAO | 240 968 555,69 | 249 120 000,00 | le modèle classe le 895 (IMF, impôt sur le résultat) en charges HAO ; le référentiel le classe en impôt sur le résultat (ligne RS), présenté à part (« Impôt et participation » : 8 151 444,31) |

**Ajustements réalisés.**
1. Carte « Impôt et participation » (hors HAO, incluse dans le résultat net), pour rapprocher la marge HAO du modèle.
2. Classement des clients et fournisseurs selon deux bases au choix :
   - « chiffre d'affaires et charges HT des écritures » (par défaut) ;
   - « montants facturés sur les comptes de tiers (TTC) », comme le modèle : débits des comptes clients et crédits des comptes fournisseurs, sans les règlements.

   Les à-nouveaux restent exclus des deux bases, alors que le modèle compte le journal RAN dans les montants fournisseurs.
3. Conventions affichées à l'écran : montants nets, impôt hors HAO.

**Points à valider.**
1. **Produits en net ou en brut** : KOFINEX applique le net, conformément au sens débit / crédit et au traitement des extournes demandés. Confirmer que les écarts avec le modèle sont attendus.
2. **Grand livre du modèle** : les lignes de tiers y portent le **code du tiers à la place du compte** (IHS01, ANDR01…), avec une colonne TYPE. L'import du grand livre (lot 3) attend un numéro de compte et, à part, un compte auxiliaire. Pour qu'un fichier de ce format alimente les classements clients et fournisseurs, il faudra une correspondance « code tiers → compte collectif » à l'import (évolution du moteur d'import, hors de ce lot).

### 11.16 Vérification de fin de lot (18 novembre 2026)
**Exécuté réellement ici.**
- Migrations : chaîne Alembic linéaire 0001 → 0015, une seule tête. Reconstruction complète de la base de test : 100 tables.
- Migration 0015 (`management_alert_settings`) : RLS active ; politiques de lecture et d'écriture ; déclencheurs anti-IA, audit et garde ; clé étrangère composite vers `companies(id, organization_id)` ; contraintes de cohérence des seuils. Aucune migration antérieure modifiée.
- SQL : 14 suites sur 14 réussies. Tests unitaires (`tests/engines`) : 238 réussis, 1 ignoré (httpx absent). Ruff : aucune erreur. Compilation : OK.
- Routage : 376 routes backend, sans doublon. Appels frontend : 236 correspondances exactes, 138 par suffixe, 11 vérifiés à la main (constantes de chemin, routes paramétrées) ; aucun appel sans route.
- TypeScript : contrôle avec des déclarations de substitution des dépendances ; aucune erreur dans le code de l'application.
- Test instable corrigé : `test_rendus_relisibles_et_deterministes[xlsx]` échouait environ une fois sur six. Cause : openpyxl et python-docx datent les entrées de l'archive (et openpyxl la date de modification) à l'heure de l'enregistrement. Les rendus Excel et Word sont désormais datés de la génération du rapport, ce qui les rend réellement déterministes.

**Non exécuté ici (environnement).** `npm run typecheck`, `npm run build` (pas de `node_modules`, installations réseau bloquées) et les tests d'intégration API (FastAPI et SQLAlchemy absents). Aucun résultat n'est déclaré pour ces commandes.

**Revue de l'interface des quatre espaces.**
- Période personnalisée incomplète : la requête n'est plus envoyée et un message l'indique, au lieu d'un appel en erreur.
- Sélecteurs natifs remplacés par le composant `Select` du système de conception.
- Évolution mensuelle du résultat et cumul budgétaire calculés côté serveur en décimal, et non plus dans le navigateur en nombres flottants.
- Détail par compte de trésorerie accessible au clavier.
- Couleurs : jetons du thème uniquement, aucune couleur codée en dur.
- Import du grand livre : choix « Effet de l'import » et synthèse du complément (reprises, ajouts, doublons, refus, mois concernés).

## 12. Correctif : contrôle de gestion et intégration avec la comptabilité générale (20 novembre 2026)

Audit du 20 novembre 2026 (phase 1) : budget sans lien avec le plan comptable, aucun plan de trésorerie prévisionnel, tiers non obligatoirement rattachés, imputation analytique des écritures ignorée. Correctif mené par phases, chacune validée avant la suivante.

### 12.1 Décisions arrêtées
1. **Auxiliaires de tiers** : un compte auxiliaire de la classe 4 est un **tiers** (code alphanumérique, ex. 4011TOY) **obligatoirement rattaché à un compte collectif** compatible du plan de l'entreprise ; le plan comptable reste numérique.
2. **Comptes d'un budget** : le plan comptable de l'entreprise s'il est ouvert, sinon le référentiel publié de l'exercice.
3. **Comptes de bilan dans un budget** : autorisés uniquement pour un budget d'investissement (classe 2 et comptes 16). Les classes autorisées par type de budget sont des **données**, pas des constantes du code, et sont marquées [À VALIDER].
4. **Plan de trésorerie** : prévision par rubriques avec règles de calendrier, réalisé lu sur les comptes de trésorerie ; **aucune échéance simulée** tant que les modules commerciaux et de trésorerie n'existent pas (lot 3B, étape C).
5. **Imputation analytique** : le réalisé par centre est lu dans les écritures natives qui portent un centre ; `cost_entries` reste pour les coûts hors comptabilité, avec une règle qui empêche de compter deux fois un même coût entre les écritures et `cost_entries`.

### 12.2 Phases et migrations
| Phase | Objet | Migration | État |
|---|---|---|---|
| 1 | Audit | — | fait |
| 2 | Référentiel comptable : plan tiers, rattachement, sous-totaux de la balance | 0019 | **livrée** (branche `cg-phase2-referentiel`, fondée sur `lot12a`) |
| 3 | Budget relié au plan comptable (décisions 2 et 3) | 0020 prévue | à faire |
| 4 | Plan de trésorerie (décision 4 ; modèle `PLAN DE TRESORRRIE (1).xlsx`, feuilles `SUIVI` et `Feuil1`) | 0021 prévue | à faire |
| 5 | Intégrations et tableaux de bord (décision 5) | selon le besoin | à faire |

### 12.3 Phase 2 — ce qui a été fait
- **Migration 0019** (aucune donnée modifiée, 0014 non réécrite) :
  - contrainte `third_parties_collective_required` posée `NOT VALID` : obligatoire pour tout nouveau tiers et toute modification ; un tiers existant non rattaché est signalé (« À rattacher ») et refusé sur une ligne d'écriture tant qu'il n'est pas rattaché ;
  - rattachement refusé vers un compte collectif en sommeil ;
  - un compte collectif auquel des tiers sont rattachés ne perd pas son caractère collectif et ne change pas pour un type incompatible.
- **Balance hiérarchique** (option « Sous-totaux par classe et racine », écran et export CSV) : sous-totaux par compte du **référentiel publié** (classes, comptes, subdivisions ; aucun niveau codé) ; en balance auxiliaire, chaque compte collectif regroupe ses tiers. Chaque ligne de détail est ajoutée une seule fois à chacun de ses parents ; les totaux généraux restent ceux des lignes de détail : **aucun double comptage** (4011TOY remonte dans 4011000, puis dans 4011, 401 et la classe 4).
- **Plan tiers** : écran en quatre catégories (clients, fournisseurs, salariés, autres tiers : administration fiscale, organismes sociaux, autres), recherche par code et intitulé, mise en sommeil, tiers à rattacher ; compte collectif obligatoire à la saisie (API et écran).
- **Règle conservée** (décision du 20 novembre 2026) : le compte d'une ligne d'écriture doit être un collectif **du même type** que le tiers (règle de 0014), sans être forcément son compte de rattachement : un même tiers peut mouvementer un compte d'avances ou de retenues de garantie. Voir `COMPTABILITE_NATIVE.md` § 4.
