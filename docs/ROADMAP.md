# KOFINEX — Feuille de route (12 lots, version novembre 2026)

Correspondance avec l'ancienne numérotation : phase 1 → lot 1 ; phase 2 → lot 3 ; « lot 3 » moteur financier → lot 4.

| Lot | Contenu | État | Reste à faire |
|---|---|---|---|
| **1. Fondations et architecture** | Schéma, RLS, Storage, Auth Supabase, organisations, entités, membres, permissions, exercices, journal, CI | **livré** | — (RLS et permissions de mission ajoutées par le lot 6) |
| **2. Design system et interface** | Identité KOFINEX, tokens clair/sombre, thème automatique, navigation, composants de base harmonisés, cartes KPI, accessibilité — voir `DESIGN_SYSTEM.md` | **livré** (identité visuelle et thèmes) | Composants propres aux modules (signatures, téléversement de preuves, tableaux triables et paginés), créés avec les lots qui les utilisent ; revue visuelle après `npm run build` |
| **3. Comptabilité et importation** | Référentiels versionnés, import Excel/CSV/PDF/OCR, contrôles, balances ; fichiers SYSCOHADA révisé et SYSCEBNL (associations) | **livré**, grand livre compris (`GRAND_LIVRE.md`) | Validation des référentiels par un expert, puis publication ; tableau des flux de trésorerie ; SYSCEBNL « projets de développement » |
| **4. Analyse financière** | États N et N-1, SIG, CAF, FR/BFR/TN, ratios, pluriannuel, bibliothèque de formules versionnée | **livré** | Règles d'alerte (`financial_alerts`) |
| **5. Contrôle de gestion** | Centres de coûts, saisies analytiques, budgets et prévisions (circuit, versions), réalisé et écarts, coûts complets avec prestations réciproques, marges, seuil de rentabilité, coûts préétablis, projections, tableau de bord — voir `CONTROLE_GESTION.md` | **livré** | Réalisé mensuel comptable (dépend du grand livre) ; import de fichiers de saisies analytiques |
| **5 bis. Pilotage du contrôle de gestion** | Couche de lecture des sources validées (natif, grand livre, balance), tableaux de bord financier (AO / HAO, Top 10, N / N-1), budgétaire (prévision à terminaison, alertes à seuils), trésorerie, masse salariale, analyse, détail jusqu'aux écritures, import de budget | **livré** — voir `CONTROLE_GESTION.md` § 11 | Import complémentaire de grand livre avec dédoublonnage ; engagements ; axes département / projet ; branchement des modules auxiliaires (lot 3B, étape C) |
| **6. Socle commun d'audit** | Méthodologies versionnées, missions, équipe et indépendance, permissions de mission, jalons et temps, documents demandés, processus et risques, programmes et procédures, feuilles, éléments probants (bucket dédié), constats, plans d'action, notes de revue, signatures, workflow, archivage figé, moteur d'échantillonnage, analyses de données | **livré** : méthodologies, missions et phases, équipe et indépendance, risques, programmes et procédures, feuilles, signatures, notes de revue, éléments probants, supervision — voir `AUDIT_SOCLE.md` | Constats et plans d'action, demandes de documents et portail de l'audité, jalons et temps, échantillonnage (après le grand livre), analyses de données |
| **7. Audit financier et comptable** | Seuils, cycles × assertions, revue analytique, échantillons et tests, circularisations, anomalies et ajustements, balance et états ajustés, synthèse des anomalies non corrigées, dossier de synthèse | **livré** sauf dossier de synthèse (lot 11), import structuré du grand livre (lot 3) et limite supérieure d'anomalie — voir `AUDIT_FINANCIER.md` | — (prise en compte des tests de contrôle interne livrée au lot 9) |
| **8. Audit interne** | Univers d'audit, cartographie des processus et des risques, programme annuel et approbation, missions, constats, suivi des plans d'action, tableau de bord du comité | **livré** sauf tableau de bord du comité (lot 11) — voir `AUDIT_INTERNE.md` | — |
| **9. Contrôle interne** | Référentiels multi-cadres (données), domaines et cycles, registre des risques, catalogue des contrôles, matrice risques-contrôles, exécutions supervisées, programmes et tests de conception et d'efficacité, évaluations, déficiences et remédiation, prise en compte par le lot 7, rapports | **livré** — voir `CONTROLE_INTERNE.md` | Chargement des référentiels à partir des documents sources ; exports PDF / Excel / Word (lot 11) ; rapprochement avec les centres de coûts (lot 5) |
| **3B. Comptabilité générale native** | Journaux, plan comptable de l'entreprise, tiers, saisie, circuit de validation, extournes, grand livre et balances natifs, lettrage ; puis auxiliaires et génération automatique, inventaire, clôture, états financiers | **étapes A et B livrées** — voir `COMPTABILITE_NATIVE.md` ; **FEC DGI Bénin livré** — voir `FEC_BENIN.md` | C : achats, ventes, trésorerie, immobilisations, paie, fiscalité, stocks, moteur de génération ; D : travaux d'inventaire, clôture, à-nouveaux ; E : états financiers natifs et intégrations |
| **10. Intelligence artificielle** | Assistant financier (contexte calculé, vérification des chiffres) ; commentaires d'analyse relus ; assistance à l'audit (suggestions de risques et de procédures, explication des analyses du grand livre, projets de constats et de synthèses) avec `ai_suggestions` et les interdits imposés en base | **livré** — voir `IA.md` | Configuration d'un fournisseur et essai réel ; traitement asynchrone ; suggestions pour le contrôle interne et l'audit financier |
| **11. Reporting et génération documentaire** | Modèles versionnés, PDF / Excel / Word, rapport financier, suivi budgétaire, rapports du contrôle interne, rapport d'audit interne émis, synthèse des anomalies, à partir de données validées, empreintes et sources figées | **livré** — voir `REPORTING.md` | Logo, graphiques, formules Excel, lettre de recommandations, rapport de gestion, dossier complet de mission |
| **12. SaaS et mise en production** | Abonnements, paiements, quotas par module, connecteurs (Odoo, Sage sur appel réel), administration, supervision, sauvegardes, durcissement, recette | à faire | — |

## Ordre d'exécution recommandé
1 ✔ → 3 ✔ → 4 ✔ → 2 ✔ → 5 ✔ → 6 ✔ → 7 ✔ → 8 ✔ → 3 (grand livre) ✔ → 9 ✔ → 10 ✔ → 11 ✔ → **12**

Deux écarts avec la numérotation, à confirmer :
- le **lot 9 avant le lot 7** : l'audit financier réutilise les tests de contrôle interne ;
- le complément du **lot 3 avant le lot 6** : l'échantillonnage sur écritures en dépend.

Si l'ordre numérique est imposé, ces deux points se traitent par des interfaces prévues dans le lot 6.

## Critères de fin de lot (inchangés)
- Migrations SQL et tests RLS négatifs pour chaque nouvelle table.
- Tests unitaires des moteurs et parcours d'intégration API.
- Écrans fonctionnels de bout en bout, sans bouton factice.
- Documentation du lot (`docs/`) et mise à jour de `PROJECT_STATUS.md`.
