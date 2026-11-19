# KOFINEX — Reporting et génération documentaire (lot 11)

Documents **PDF, Excel et Word** établis à partir de **données validées uniquement**. Un document généré est **figé** et conservé avec :
- l'empreinte de son fichier ;
- l'empreinte de ses données ;
- son contenu structuré ;
- ses sources et le modèle utilisé.

Le reporting ne calcule aucun chiffre et n'écrit aucun texte : il met en forme les sorties des moteurs des lots 4 à 9 et les textes enregistrés (constats, conclusions, commentaires relus, textes du modèle).

## 1. Documents disponibles

| Document | Données reprises | Condition imposée par la base |
|---|---|---|
| Rapport financier (`financial_report`) | Analyse : contrôles, états N et N-1, indicateurs (« non calculé » si besoin, jamais estimé), alertes ; commentaires d'analyse (lot 10) | Analyse **terminée** de l'entreprise ; commentaires de cette analyse, jamais rejetés ; présence de brouillons IA obligatoirement signalée |
| Suivi budgétaire (`budget_report`) | Budget, réalisé, écarts, sens, totaux, avertissements et conventions du lot 5 | Budget **approuvé** (ou archivé après approbation) de l'entreprise |
| Rapports du contrôle interne (`ic_report`) | Les neuf rapports structurés du lot 9 (évaluation, domaine, processus, cycle, cartographie, matrice, contrôles inefficaces, déficiences, remédiation) | Type de rapport connu ; les conclusions ne reposent que sur les tests revus et les évaluations approuvées (règle IC-SYNTH-1) |
| Rapport d'audit interne (`internal_audit_report`) | Contenu **figé à l'émission** (lot 8) | Rapport **émis** de la mission ; son empreinte (`content_sha256`) doit figurer dans les sources : un projet ne s'exporte pas ici |
| Synthèse des anomalies (`fa_summary`) | Seuils, anomalies, cumuls et effets sur les états, conclusion rédigée par l'équipe (lot 7) | Mission d'audit financier ; seuils **approuvés** cités dans les sources. Le document porte la mention « aucune opinion » |

**Brouillons IA** :
- par défaut, seuls les commentaires relus figurent dans le rapport financier ;
- sur demande explicite, les brouillons non relus sont inclus. Ils sont alors signalés en tête du document et à leur emplacement, et `contains_ai_drafts` est vrai ;
- les commentaires rejetés n'y figurent jamais.

## 2. Formats et présentation
- **Modèle commun** (`engines/reporting/document.py`) : un document neutre (titre, entité, période, avertissements, sections de paragraphes, champs et tableaux typés, sources) alimente les trois formats.
- **Word** (python-docx) : titres, tableaux, chiffres alignés à droite ; en-tête avec l'entité et le titre ; pied de page avec l'empreinte des données.
- **Excel** (openpyxl) :
  - une feuille de synthèse et une feuille par tableau, avec de **vrais nombres** formatés et un en-tête figé ;
  - une feuille « Sources » qui porte l'empreinte complète.
- **PDF** (reportlab) :
  - A4, en paysage si un tableau dépasse six colonnes ;
  - filet or et pied de page sur chaque page (générateur, date, auteur, empreinte, numéro de page) ;
  - polices standard : un caractère hors du jeu Windows-1252 est remplacé visiblement, jamais supprimé.
- **Rendu déterministe** : mêmes données, même date et même modèle donnent un fichier identique, octet pour octet.
- **Mise en forme française** : espaces insécables entre milliers, virgule décimale, dates JJ/MM/AAAA.
- **Couleurs** : bleu nuit KOFINEX par défaut, filets or ; une organisation peut choisir sa couleur principale dans son modèle.

## 3. Empreintes et traçabilité
- `sha256` : empreinte du fichier ; elle est rendue avec le lien de téléchargement.
- `data_sha256` : empreinte du contenu structuré (règle `KOFINEX-REPORT-1`).
  - Elle ne dépend ni du format, ni de la date, ni de l'auteur : un PDF et un Excel des mêmes données ont la même.
  - Elle change dès qu'une donnée, une section ou un texte change.
- `content_snapshot` : le document neutre exact mis en forme.
- `source_refs` : analyse, balance, grand livre, budget, rapport émis, seuils, commentaires IA (avec modèle et version des consignes).
- Également conservés : modèle et version, paramètres de la demande, auteur, date, version du générateur.
- **Échec** : un rendu impossible est enregistré en échec, avec son motif ; il n'est jamais masqué.
- **Ordre d'enregistrement** : la base valide d'abord les sources, puis le fichier est déposé (`reports/{organisation}/{entreprise}/{document}.{format}`). Un dépôt en échec annule l'enregistrement.
- **Immuabilité** : aucune modification ni suppression. Pour mettre à jour, on génère un nouveau document.
- **Journal** : `report.generate`, `report.download`, `report_template.*`.

## 4. Modèles de rapport
- `report_templates`, table du lot 1, complétée :
  - type de document, version, statut (`draft → published → archived`) ;
  - textes : titre, introduction, mentions finales et leurs intitulés ;
  - sections incluses (rapport financier) ;
  - couleur principale (`#RRGGBB`, vérifiée en base).
- Gérés par les propriétaires et administrateurs de l'organisation.
- Une version publiée est **figée** : « nouvelle version » crée une copie en brouillon de numéro suivant. Seul un brouillon peut être supprimé.
- Un document ne peut utiliser qu'une version **publiée**, du même type et de la même organisation (ou de la plateforme). Le numéro de version est enregistré avec le document.

## 5. Accès (RLS et API)

| Document | Lecture | Génération |
|---|---|---|
| Rapport financier, suivi budgétaire | Utilisateurs ayant accès à l'entreprise | Administrateurs, comptables, contrôleurs, analystes de l'entreprise |
| Rapports du contrôle interne | Lecteurs du dispositif (entreprise, rôles du contrôle interne, équipes de mission) | Mêmes lecteurs |
| Documents de mission | Équipe de mission (dossier) | Associé, manager, chef de mission, auditeur |

- L'audité n'a accès à aucun document de mission par ce module.
- Aucune autre organisation ne voit rien.
- L'IA ne peut ni générer ni modifier un document : l'interdit du lot 10 s'applique à ces tables.
- Le téléchargement passe par un lien signé valable 5 minutes, délivré après le contrôle de lecture.

## 6. Interface
- **Entreprise → Rapports** (`/companies/{id}/rapports`) :
  - génération du rapport financier (exercice, option des brouillons IA), du suivi budgétaire (budget approuvé) et des rapports du contrôle interne ;
  - choix du format et du modèle ;
  - liste des documents, avec empreintes, sources et téléchargement.
- **Contrôle interne → Rapports** : boutons PDF, Excel et Word sur le rapport affiché, avec ses filtres ; l'export CSV par section est conservé.
- **Mission → Documents** : export du rapport d'audit interne émis ou de la synthèse des anomalies, et liste des documents de la mission.
- **Organisation → Modèles de rapports** : création, modification du brouillon, publication, nouvelle version, archivage.

## 7. API
- `GET /reporting/document-types`.
- Documents de l'entreprise : `GET` et `POST /companies/{id}/documents` (`financial_report`, `budget_report`, `ic_report`).
- Documents de mission : `GET` et `POST /engagements/{id}/documents` (`internal_audit_report`, `fa_summary`).
- `GET /documents/{id}` : document figé et contenu structuré.
- `GET /documents/{id}/download` : lien signé, empreintes.
- Modèles :
  - `GET` et `POST /organizations/{id}/report-templates` ;
  - `PATCH` et `DELETE /organizations/{id}/report-templates/{id}` ;
  - `POST /organizations/{id}/report-templates/{id}/publish`, `/archive`, `/new-version`.

Le lot 8 conserve `/engagements/{id}/reports` pour la rédaction et l'émission du rapport d'audit interne ; ce module exporte ce rapport une fois émis.

## 8. Tests
- **SQL** (`tests/sql/test_reporting.sql`, 41 contrôles) :
  - conditions de chaque type (analyse terminée, budget approuvé, rapport émis et son empreinte, seuils approuvés) ;
  - commentaires IA rejetés refusés, brouillons obligatoirement signalés ;
  - immuabilité (RLS et déclencheur), échec motivé ;
  - modèles : publication au nom de l'utilisateur, gel, conservation, type, archivage ;
  - accès de la lectrice, de l'auditeur, de l'auditée, d'une autre organisation ; acteur IA.
- **Unitaires** (`tests/engines/test_reporting.py`, 16 tests) :
  - mise en forme française ;
  - constructeurs des cinq documents, valeurs reprises sans calcul ;
  - avertissements IA ;
  - modèle : titre, textes, sections, couleur ;
  - empreinte des données indépendante du format ;
  - fichiers PDF, Excel et Word relus par pypdf, openpyxl et python-docx, et rendus identiques d'une génération à l'autre ;
  - caractères PDF, noms de feuilles.
- **Intégration** (`tests/integration/test_reporting_api.py`) :
  - rapport financier dans les trois formats, avec la même empreinte de données ;
  - document figé et lien de téléchargement ;
  - refus sans analyse terminée ;
  - modèle refusé en brouillon, puis appliqué une fois publié, figé et versionné ;
  - documents de mission refusés sans rapport émis ni seuils ;
  - accès refusés.

## 9. Limites connues
- Génération synchrone, sans file de tâches : les très grands grands livres ne sont pas exportés par ce module ; leur export CSV existe au lot 3.
- Pas de logo dans les documents : le compartiment `branding` existe, mais son intégration au rendu n'est pas faite.
- Pas de signature électronique des fichiers : l'intégrité repose sur les empreintes conservées.
- Le rapport financier ne contient pas de graphiques.
- Les feuilles de travail et le dossier complet d'une mission ne s'exportent pas encore en un seul document.
