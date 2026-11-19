# KOFINEX — Page d'accueil publique et tableau de bord

*Intervention du 18 novembre 2026 : reproduction de la maquette de référence (page d'accueil à gauche, tableau de bord après connexion à droite). Aucun autre module n'a été modifié.*

## 1. Parcours
| Adresse | Accès | Contenu |
|---|---|---|
| `/` | public | Page d'accueil (navigation, hero, avantages, fonctionnalités, KOFINEX AI, publics, bandeau final, tarifs et à propos en pied de page) |
| `/demonstration` | public | Tableau de bord avec des **données fictives** statiques, bannière permanente « Démonstration » |
| `/tableau-de-bord` | connecté | Tableau de bord de l'entreprise, de l'exercice et de la période choisis dans la barre supérieure (données réelles) |

Après la connexion (mot de passe, lien magique ou retour d'authentification), l'utilisateur arrive sur `/tableau-de-bord`. Le middleware rend publiques `/` (adresse exacte) et `/demonstration`.

## 2. Données affichées
Le tableau de bord ne calcule aucun indicateur. Il lit `GET /companies/{cid}/fiscal-years/{fy}/dashboard?period=…`.

| Bloc | Source | Sans données |
|---|---|---|
| Chiffre d'affaires, résultat net, trésorerie | Dernière analyse annuelle **terminée** de l'exercice (bibliothèque KOFINEX-STD-1 : `CA`, `RESULTAT_NET`, `TN`) | « Aucune analyse terminée » |
| Variation | Convention de la bibliothèque : (N − N-1) / \|N-1\|, non calculée si N-1 est absent ou nul | « Variation non disponible » |
| Charges totales, structure des charges, répartition des produits | Exercice complet : balance validée. Sous-période : grand livre validé. Nature (charge / produit) et libellés : plan de comptes de la version publiée du référentiel. Trois premières rubriques, puis « Autres » | Message explicite (pas de grand livre pour une sous-période, pas de balance) |
| Évolution des produits et charges | Grand livre validé, par mois de l'exercice | « Importez et validez le grand livre… » |
| Principaux indicateurs | Marge commerciale, EBE, résultat d'exploitation, résultat net, CAF (méthode additive) de l'analyse terminée | « Aucune analyse financière terminée… » |
| Alertes financières | Imports en attente de validation ; alertes ouvertes de l'analyse ; état de la dernière analyse | Chaque ligne dit son état |
| Activités récentes | Journal d'audit de l'entreprise, filtré par la RLS | « Aucune activité journalisée » |
| Cloche | Nombre d'alertes appelant une action (imports à valider, alertes ouvertes, analyse manquante) | Pas de pastille |

La maquette montre une « marge brute » : cet indicateur n'existe pas dans la bibliothèque, il est remplacé par la **marge commerciale** (`MARGE_COMMERCIALE`).

Sur une sous-période, les indicateurs restent ceux de l'analyse annuelle ; une mention le rappelle sous le titre.

## 3. Données de démonstration
- Fichier unique `frontend/lib/demo-dashboard.ts`, marqué « DONNÉES DE DÉMONSTRATION — FICTIVES ».
- Utilisé seulement par `/demonstration` et par l'illustration de l'ordinateur de la page d'accueil ; jamais envoyé à l'API ni enregistré.
- Les montants reprennent la maquette. Les alertes et activités sont celles que KOFINEX produit réellement (imports, analyse, rapports), pas des fonctions absentes.
- Les organisations de démonstration en base (`is_demo`) passent par les vrais moteurs ; la barre supérieure affiche alors le badge « Démonstration ».

## 4. Coquille de l'application
- **Barre latérale** (ordre de la maquette) : Tableau de bord, Comptabilité, Achats, Ventes, Trésorerie, Stocks, Immobilisations, Paie, Fiscalité, Analyse financière, Contrôle de gestion, Audit financier, Contrôle interne, KOFINEX AI, Reporting, puis Paramètres.
  - Chaque rubrique s'ouvre sur les pages existantes (par exemple Comptabilité : entreprises, entreprise et exercices, balance, grand livre, référentiels).
  - Une page qui a besoin d'une entreprise ou d'un exercice reste grisée, avec la raison, tant que la sélection est vide.
  - Achats, Ventes, Trésorerie, Stocks, Immobilisations, Paie et Fiscalité n'existent pas : la rubrique affiche « Bientôt · Module non disponible dans cette version », sans lien.
- **Barre supérieure** : sélecteurs Organisation (si plusieurs), Entreprise, Exercice et Période, reliés aux données (`lib/workspace.tsx`, mémorisés dans le navigateur et recalés sur l'adresse) ; cloche ; menu du compte (profil, organisations, thème, déconnexion).
- Les droits restent vérifiés par l'API et la RLS ; les sélecteurs ne sont qu'un confort de navigation.

## 5. Éléments de la page d'accueil sans fonctionnalité derrière
Le texte de la maquette est conservé à la demande. Ces fonctions **ne sont pas encore réalisées** (lot 12) :
- essai gratuit de 14 jours (l'inscription existe, la durée n'est pas gérée) ;
- paiement via FedaPay et facturation en FCFA ;
- grille tarifaire (le pied de page l'indique) ;
- la carte « Comptabilité » parle de saisie des écritures et de journaux : KOFINEX importe la balance et le grand livre, il n'a pas de module de saisie.

## 6. Vérifications
- Moteur : `tests/engines/test_dashboard.py` (nature et rubriques depuis le plan, repli sur 3 chiffres quand le plan n'a pas la rubrique à 2 chiffres, « Autres », parts, variations, mois de l'exercice).
- API : `tests/integration/test_dashboard_api.py` (prêt pour la CI, non exécuté ici).
- Palette des graphiques (bleu, orange, vert, violet) passée au validateur de couleurs : séparation daltonisme vert / orange dans la zone tolérée **avec** légende libellée et pourcentages, ce que portent les deux anneaux.
