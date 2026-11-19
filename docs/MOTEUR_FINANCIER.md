# Moteur financier

## 1. Principe

Le moteur sépare trois niveaux, pour qu'aucune règle comptable ne soit écrite dans le code :

| Niveau | Contenu | Origine | Où |
|---|---|---|---|
| **Référentiel** (par version) | Structure des états (lignes, ordre, totaux, rôles), correspondances comptes → lignes, **liaison des concepts d'analyse** aux lignes et comptes | Textes officiels OHADA, chargés par un administrateur, figés à la publication | `/referentiels` |
| **Bibliothèque d'analyse** | Formules des indicateurs (FR, BFR, ratios…) exprimées sur des **concepts** | Livrée versionnée (`KOFINEX-STD-1`), conventions explicites ; formules propres à une organisation possibles | `app/engines/financial/library.py`, `/formules` |
| **Calcul** | États, indicateurs, contrôles | Python, `decimal.Decimal` (34 chiffres significatifs, arrondi bancaire par indicateur) | `app/engines/` |

Ainsi, la formule du fonds de roulement (`ressources_stables − actif_immobilise`) est la même pour
tous ; ce que recouvrent les « ressources stables » dans le bilan SYSCOHADA révisé ou SYSCEBNL est
défini, ligne par ligne, dans la version du référentiel.

## 2. États financiers

`app/engines/accounting/statements.py` applique à la balance validée :

1. les **correspondances** : pour chaque compte et chaque (état, colonne, règle), la racine la plus
   longue l'emporte, puis la priorité la plus basse ; une égalité est une erreur (jamais un choix
   arbitraire) ;
2. les règles de solde : solde débiteur, solde créditeur, solde net débiteur / créditeur,
   mouvements débit / crédit ; colonnes brut / amortissements / net (net = brut − amortissements si
   aucune correspondance « net » directe) ;
3. les **lignes de total** de la structure, dans l'ordre des dépendances.

Contrôles : total actif = total passif ; résultat au bilan = résultat du compte de résultat (lignes
désignées par leur **rôle** dans la structure) ; comptes mouvementés non rattachés.
Chaque montant conserve la liste des comptes et des règles qui l'ont produit (consultable en cliquant
sur une ligne).

**N-1** : la balance validée de l'exercice précédent est traitée avec la **même version** du
référentiel (présentation pro forma comparable).

## 3. Langage de formules

Analysé puis converti en arbre JSON stocké avec la formule ; jamais exécuté par `eval`.

| Élément | Exemple |
|---|---|
| Opérateurs, nombres | `+ - * /`, parenthèses, `360`, `0.5` |
| Fonctions | `abs(x)`, `min(a, b, …)`, `max(…)`, `avg(…)` |
| Concepts | `concept("capitaux_propres")`, `prev_concept(…)` |
| Indicateurs | `ind("EBE")`, `prev_ind("CA")` |
| Lignes d'état | `line("CODE")`, `line("CODE", "gross")`, `prev_line(…)` |
| Comptes | `acct("60", "net_debit")`, `prev_acct(…)` |
| Durée | `days()` : nombre réel de jours de l'exercice |

Cas limites, tracés sur chaque indicateur : donnée absente → « non calculable » (jamais estimée) ;
dénominateur nul → « non significatif » ; dépendance circulaire → erreur. Chaque indicateur conserve
les valeurs exactes de ses entrées, le code et la version de la formule.

## 4. Concepts d'analyse à lier dans chaque version de référentiel

| Code | Concept | Définition |
|---|---|---|
| `total_actif` | Total du bilan | Total de l'actif net (égal au total du passif). |
| `actif_immobilise` | Actif immobilisé net | Immobilisations nettes d'amortissements et de dépréciations. |
| `stocks` | Stocks nets | Stocks et en-cours nets de dépréciations. |
| `creances_clients` | Créances clients nettes | Clients et comptes rattachés, nets de dépréciations. |
| `actif_circulant` | Actif circulant hors trésorerie | Actif circulant net, à l'exclusion de la trésorerie-actif. |
| `tresorerie_actif` | Trésorerie-actif | Disponibilités et placements assimilés à la trésorerie. |
| `capitaux_propres` | Capitaux propres | Capitaux propres, y compris le résultat de l'exercice. |
| `dettes_financieres` | Dettes financières | Dettes financières et ressources assimilées, hors trésorerie-passif. |
| `ressources_stables` | Ressources stables | Capitaux propres et dettes financières et ressources assimilées. |
| `passif_circulant` | Passif circulant hors trésorerie | Dettes d'exploitation et hors exploitation à court terme, à l'exclusion de la trésorerie-passif. |
| `dettes_fournisseurs` | Dettes fournisseurs | Fournisseurs et comptes rattachés. |
| `tresorerie_passif` | Trésorerie-passif | Concours bancaires courants et crédits de trésorerie. |
| `chiffre_affaires` | Chiffre d'affaires | Ventes de biens et de services (hors taxes). |
| `marge_commerciale` | Marge commerciale | Ventes de marchandises diminuées du coût d'achat des marchandises vendues. |
| `valeur_ajoutee` | Valeur ajoutée | Richesse créée par l'activité, avant charges de personnel. |
| `excedent_brut_exploitation` | Excédent brut d'exploitation | Valeur ajoutée diminuée des charges de personnel (et éléments assimilés selon le référentiel). |
| `resultat_exploitation` | Résultat d'exploitation | Résultat de l'activité d'exploitation. |
| `resultat_financier` | Résultat financier | Produits financiers diminués des charges financières. |
| `resultat_activites_ordinaires` | Résultat des activités ordinaires | Résultat d'exploitation et résultat financier. |
| `resultat_hao` | Résultat hors activités ordinaires | Résultat des opérations hors activités ordinaires. |
| `resultat_net` | Résultat net | Résultat de l'exercice. |
| `achats_consommes` | Achats consommés | Achats de marchandises et de matières, corrigés de la variation des stocks. |
| `achats_fournisseurs` | Base du délai fournisseurs | Achats et services extérieurs réglés aux fournisseurs (HT). |
| `charges_personnel` | Charges de personnel | Rémunérations et charges sociales. |
| `charges_calculees` | Charges calculées | Dotations aux amortissements, dépréciations et provisions (charges sans décaissement). |
| `produits_calcules` | Produits calculés | Reprises d'amortissements, de dépréciations et de provisions, quote-part des subventions d'investissement virée au résultat (produits sans encaissement). |
| `produits_cessions` | Produits de cession d'immobilisations | Prix de cession des immobilisations cédées. |
| `vnc_cessions` | Valeur comptable des cessions | Valeur comptable des immobilisations cédées. |
| `produits_encaissables_hors_ebe` | Produits encaissables après EBE | Produits encaissables comptabilisés après l'EBE : financiers, hors activités ordinaires (hors cessions), transferts… |
| `charges_decaissables_hors_ebe` | Charges décaissables après EBE | Charges décaissables comptabilisées après l'EBE : financières, hors activités ordinaires (hors valeur des cessions), participation, impôt sur le résultat… |

Un concept non lié n'est jamais remplacé par une estimation : les indicateurs qui l'utilisent sont
signalés « non calculables ».

## 5. Bibliothèque standard KOFINEX-STD-1

### Soldes intermédiaires de gestion

| Code | Indicateur | Formule | Unité | Convention |
|---|---|---|---|---|
| `CA` | Chiffre d'affaires | `concept("chiffre_affaires")` | montant |  |
| `MARGE_COMMERCIALE` | Marge commerciale | `concept("marge_commerciale")` | montant |  |
| `VALEUR_AJOUTEE` | Valeur ajoutée | `concept("valeur_ajoutee")` | montant |  |
| `EBE` | Excédent brut d'exploitation | `concept("excedent_brut_exploitation")` | montant |  |
| `RESULTAT_EXPLOITATION` | Résultat d'exploitation | `concept("resultat_exploitation")` | montant |  |
| `RESULTAT_FINANCIER` | Résultat financier | `concept("resultat_financier")` | montant |  |
| `RAO` | Résultat des activités ordinaires | `concept("resultat_activites_ordinaires")` | montant |  |
| `RESULTAT_HAO` | Résultat hors activités ordinaires | `concept("resultat_hao")` | montant |  |
| `RESULTAT_NET` | Résultat net | `concept("resultat_net")` | montant |  |

### Capacité d'autofinancement

| Code | Indicateur | Formule | Unité | Convention |
|---|---|---|---|---|
| `CAF_ADDITIVE` | CAF (méthode additive) | `concept("resultat_net") + concept("charges_calculees") - concept("produits_calcules") - concept("produits_cessions") + concept("vnc_cessions")` | montant | Doit être égale à la CAF calculée par la méthode soustractive ; un écart est signalé. |
| `CAF_SOUSTRACTIVE` | CAF (méthode soustractive) | `concept("excedent_brut_exploitation") + concept("produits_encaissables_hors_ebe") - concept("charges_decaissables_hors_ebe")` | montant |  |

### Équilibre financier

| Code | Indicateur | Formule | Unité | Convention |
|---|---|---|---|---|
| `FR` | Fonds de roulement | `concept("ressources_stables") - concept("actif_immobilise")` | montant |  |
| `BFR` | Besoin en fonds de roulement | `concept("actif_circulant") - concept("passif_circulant")` | montant |  |
| `TN` | Trésorerie nette | `concept("tresorerie_actif") - concept("tresorerie_passif")` | montant | Doit être égale à FR − BFR ; un écart est signalé. |
| `COUVERTURE_EMPLOIS_STABLES` | Couverture des emplois stables | `concept("ressources_stables") / concept("actif_immobilise")` | ratio |  |

### Liquidité

| Code | Indicateur | Formule | Unité | Convention |
|---|---|---|---|---|
| `LIQUIDITE_GENERALE` | Liquidité générale | `(concept("actif_circulant") + concept("tresorerie_actif")) / (concept("passif_circulant") + concept("tresorerie_passif"))` | ratio |  |
| `LIQUIDITE_REDUITE` | Liquidité réduite | `(concept("actif_circulant") - concept("stocks") + concept("tresorerie_actif")) / (concept("passif_circulant") + concept("tresorerie_passif"))` | ratio |  |
| `LIQUIDITE_IMMEDIATE` | Liquidité immédiate | `concept("tresorerie_actif") / (concept("passif_circulant") + concept("tresorerie_passif"))` | ratio |  |

### Solvabilité et endettement

| Code | Indicateur | Formule | Unité | Convention |
|---|---|---|---|---|
| `AUTONOMIE_FINANCIERE` | Autonomie financière | `concept("capitaux_propres") / concept("total_actif") * 100` | % | Base : total du bilan (et non total des dettes). |
| `ENDETTEMENT` | Endettement financier (gearing) | `concept("dettes_financieres") / concept("capitaux_propres")` | ratio | Non significatif si les capitaux propres sont négatifs. |
| `CAPACITE_REMBOURSEMENT` | Capacité de remboursement | `concept("dettes_financieres") / ind("CAF_ADDITIVE")` | années | CAF retenue : méthode additive. Non significatif si la CAF est négative. |

### Rentabilité et marges

| Code | Indicateur | Formule | Unité | Convention |
|---|---|---|---|---|
| `ROE` | Rentabilité des capitaux propres (ROE) | `concept("resultat_net") / concept("capitaux_propres") * 100` | % | Capitaux propres de clôture, résultat de l'exercice inclus. Non significatif si les capitaux propres sont négatifs. |
| `ROA` | Rentabilité de l'actif (ROA) | `concept("resultat_net") / concept("total_actif") * 100` | % | Total du bilan de clôture. |
| `MARGE_NETTE` | Marge nette | `concept("resultat_net") / concept("chiffre_affaires") * 100` | % |  |
| `TAUX_EBE` | Taux de marge brute d'exploitation | `concept("excedent_brut_exploitation") / concept("chiffre_affaires") * 100` | % |  |
| `TAUX_VALEUR_AJOUTEE` | Taux de valeur ajoutée | `concept("valeur_ajoutee") / concept("chiffre_affaires") * 100` | % |  |
| `TAUX_RESULTAT_EXPLOITATION` | Marge d'exploitation | `concept("resultat_exploitation") / concept("chiffre_affaires") * 100` | % |  |
| `PART_CHARGES_PERSONNEL_VA` | Charges de personnel / valeur ajoutée | `concept("charges_personnel") / concept("valeur_ajoutee") * 100` | % |  |

### Activité et rotations

| Code | Indicateur | Formule | Unité | Convention |
|---|---|---|---|---|
| `BFR_JOURS_CA` | BFR en jours de chiffre d'affaires | `ind("BFR") / ind("CA") * days()` | jours | Durée de référence : nombre réel de jours de l'exercice (days()), ce qui rend comparables les exercices de durée inhabituelle. CA hors taxes. |
| `ROTATION_STOCKS` | Rotation des stocks | `concept("stocks") / concept("achats_consommes") * days()` | jours | Durée de référence : nombre réel de jours de l'exercice (days()), ce qui rend comparables les exercices de durée inhabituelle. Stock de clôture (et non stock moyen). |
| `DELAI_CLIENTS` | Délai de recouvrement clients | `concept("creances_clients") / concept("chiffre_affaires") * days()` | jours | Durée de référence : nombre réel de jours de l'exercice (days()), ce qui rend comparables les exercices de durée inhabituelle. Créances de clôture rapportées au CA hors taxes : si les créances incluent la TVA, le délai est majoré d'autant. |
| `DELAI_FOURNISSEURS` | Délai de paiement fournisseurs | `concept("dettes_fournisseurs") / concept("achats_fournisseurs") * days()` | jours | Durée de référence : nombre réel de jours de l'exercice (days()), ce qui rend comparables les exercices de durée inhabituelle. Dettes de clôture rapportées aux achats hors taxes : si les dettes incluent la TVA, le délai est majoré d'autant. |
| `ROTATION_ACTIF` | Rotation de l'actif | `concept("chiffre_affaires") / concept("total_actif")` | fois |  |

### Croissance

| Code | Indicateur | Formule | Unité | Convention |
|---|---|---|---|---|
| `CROISSANCE_CA` | Croissance du chiffre d'affaires | `(ind("CA") - prev_ind("CA")) / abs(prev_ind("CA")) * 100` | % | Base : valeur absolue de l'exercice précédent (évite une inversion de signe si elle est négative). Non calculé si l'exercice précédent n'a pas de balance validée ou si sa valeur est nulle. |
| `CROISSANCE_VA` | Croissance de la valeur ajoutée | `(ind("VALEUR_AJOUTEE") - prev_ind("VALEUR_AJOUTEE")) / abs(prev_ind("VALEUR_AJOUTEE")) * 100` | % | Base : valeur absolue de l'exercice précédent (évite une inversion de signe si elle est négative). Non calculé si l'exercice précédent n'a pas de balance validée ou si sa valeur est nulle. |
| `CROISSANCE_EBE` | Croissance de l'EBE | `(ind("EBE") - prev_ind("EBE")) / abs(prev_ind("EBE")) * 100` | % | Base : valeur absolue de l'exercice précédent (évite une inversion de signe si elle est négative). Non calculé si l'exercice précédent n'a pas de balance validée ou si sa valeur est nulle. |
| `CROISSANCE_RESULTAT_NET` | Croissance du résultat net | `(ind("RESULTAT_NET") - prev_ind("RESULTAT_NET")) / abs(prev_ind("RESULTAT_NET")) * 100` | % | Base : valeur absolue de l'exercice précédent (évite une inversion de signe si elle est négative). Non calculé si l'exercice précédent n'a pas de balance validée ou si sa valeur est nulle. |

### Contrôles croisés

| Code | Contrôle |
|---|---|
| `FR_BFR_TN` | FR − BFR = trésorerie nette — Les concepts liés au référentiel ne couvrent pas l'intégralité du bilan (ou le classent deux fois). |
| `CAF_METHODS` | CAF additive = CAF soustractive — Les concepts de la CAF ne couvrent pas tous les éléments entre l'EBE et le résultat net. |

## 6. Versionnage et immuabilité

- Une formule publiée ne peut plus être modifiée (trigger en base) : une correction crée une nouvelle
  version, la précédente est retirée. Les analyses passées gardent la version utilisée.
- Une analyse terminée est figée (états, indicateurs) ; relancer crée une nouvelle analyse.
- Pour un même code, la formule propre à l'organisation prime sur la formule standard.

## 7. Pluriannuel

`/companies/{id}/multi-year` : dernière analyse terminée de chaque exercice, variation absolue et
relative (base |N-1|) d'un exercice à l'autre, taux de croissance annuel moyen pour les montants
strictement positifs, graphique d'évolution par indicateur.

## 8. Fichiers de référentiel supplémentaires

**Structure des états** — colonnes : `etat`, `code`, `libelle`, `ordre`, `type`
(`detail | total | titre`), `formule` (totaux : `AE + AF - AG`), `role`
(`total_actif | total_passif | resultat_bilan | resultat_compte_resultat`), `niveau`.
Les codes de ligne sont uniques dans une version.

**Concepts** — colonnes : `concept`, `expression` (lignes, comptes, autres concepts ; pas
d'indicateurs), `source`.

La publication d'une version exige désormais la structure des états et des correspondances
vers des lignes de détail existantes.

## 9. Tests

| Fichier | Contenu |
|---|---|
| `tests/engines/test_expressions.py` | Langage de formules : calcul exact, refus des expressions dangereuses |
| `tests/engines/test_financial_engine.py` | États (brut/amortissements/net, totaux, contrôles, ambiguïtés), 27 indicateurs vérifiés au centime, contrôles croisés, N-1 absent, séries |
| `tests/sql/test_financial_engine.sql` | Immuabilité des formules, structure figée, analyses figées, isolation |
| `tests/integration/test_analysis_api.py` | Parcours API : référentiel de test complet, import, analyse, traçabilité, séries, formule personnalisée versionnée |

Le référentiel utilisé par les tests (`tests/engines/fictitious_framework.py`) est **fictif** : ses
lignes et rattachements ne reproduisent pas les états officiels.
