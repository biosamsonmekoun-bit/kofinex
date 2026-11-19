# KOFINEX — Intelligence artificielle (lot 10)

**Principe : l'IA assiste, elle ne décide pas.** Elle commente des valeurs déjà calculées et propose des risques, des procédures, des projets de rédaction et des explications d'analyses. Chaque proposition est décidée par une personne de l'équipe, à son nom. Les interdits sont imposés **par la base de données et par l'API** ; la consigne donnée au modèle ne fait que les rappeler.

## 1. Fournisseur et configuration
- Fournisseurs pris en charge : **Anthropic** (API Messages) ou **OpenAI** (Chat Completions), par HTTP (`engines/ai/provider.py`).
- Variables d'environnement :
  - `AI_PROVIDER` : `anthropic`, `openai` ou `none` (valeur par défaut) ;
  - `AI_API_KEY` : la clé n'est jamais renvoyée par l'API ni journalisée ;
  - `AI_MODEL` : identifiant exact du modèle chez le fournisseur ; aucun modèle n'est choisi par défaut ;
  - `AI_MAX_OUTPUT_TOKENS`, `AI_TIMEOUT_SECONDS` ;
  - `AI_BASE_URL` : facultatif, pour une passerelle d'entreprise compatible.
- **Sans fournisseur, clé et modèle**, l'IA est indisponible :
  - `/ai/status` en donne la raison et les écrans affichent l'indisponibilité ;
  - une demande renvoie une erreur 503 ;
  - aucune réponse n'est simulée.
- Une erreur du fournisseur (clé refusée, délai dépassé, réponse vide) est rapportée telle quelle. Rien n'est enregistré, la question de l'utilisateur comprise.

## 2. Activation par l'organisation
- `ai_settings` : l'IA est désactivée par défaut. Un propriétaire ou un administrateur l'active **usage par usage**, avec une note d'accord sur la transmission des données au fournisseur (au moins 10 caractères, enregistrée à son nom).
- Usages :
  - `finance_assistant` : questions sur une analyse ;
  - `analysis_commentary` : commentaires d'analyse ;
  - `audit_risks` : risques ;
  - `audit_procedures` : procédures ;
  - `anomaly_explanation` : analyses du grand livre ;
  - `drafting` : constats et synthèses.
- La base vérifie l'usage (`public.ai_allowed`) à chaque conversation, message, commentaire et suggestion.

## 3. Contextes : uniquement des données calculées
`engines/ai/context.py` construit le contexte à partir des sorties des moteurs existants, lues avec les droits de l'utilisateur (RLS).

| Usage | Contexte transmis |
|---|---|
| Assistant financier, commentaires | Dernière analyse **terminée** de l'exercice : indicateurs N et N-1, lignes principales des états, alertes, contrôles. Les indicateurs non calculables sont signalés comme tels, jamais estimés |
| Risques d'audit | Mission, cartographie des risques de l'entité, risques déjà retenus, cycles et assertions de la méthodologie, analyse de l'exercice si elle existe |
| Procédures | Programmes types de la méthodologie (non encore repris) et risques évalués de la mission |
| Projet de constat | Une feuille de travail ou un test de contrôle de la mission, avec ses travaux et résultats enregistrés |
| Projet de synthèse | Constats validés de la mission et leurs recommandations |
| Analyses du grand livre | Résultats des analyses déterministes du lot 3 (doublons possibles, week-ends, numérotation, montants ronds, premiers chiffres…) |

- Chaque valeur chiffrée devient un fait numéroté (`[F1]`, `[F2]`…) que le modèle doit citer.
- Le contexte exact est conservé avec la réponse (`context_snapshot`), et l'interface permet de le consulter.

## 4. Contrôle des réponses
- **Chiffres (règle KOFINEX-NUM-1)** : les nombres de la réponse sont extraits (formats français et anglais, pourcentages, k / M / Md) puis rapprochés des valeurs du contexte. Sont acceptés : l'égalité, l'arrondi à la précision affichée, la mise à l'échelle, la valeur absolue et l'expression en pourcentage. Un nombre non traçable, par exemple un écart calculé par le modèle, est **signalé visiblement** à côté de la réponse.
- **Suggestions** : la réponse doit être un JSON conforme.
  - Une proposition est **écartée**, avec sa raison, si un champ obligatoire manque ou dépasse les longueurs admises, ou si elle cite une référence absente du contexte.
  - Elle l'est aussi si elle utilise un cycle, une assertion, un programme type, un risque ou un test absents ; ou si elle reprend un risque déjà présent dans la mission.
  - Rien n'est complété par KOFINEX.
- **Consignes** (`engines/ai/prompts.py`, version `KOFINEX-AI-1`, conservée avec chaque réponse) :
  - pas de décision, de validation, de signature ni de conclusion ;
  - pas d'opinion d'audit ;
  - pas de nouveau calcul ni de norme inventée ;
  - citer les références et dire ce qui manque.

## 5. Interdits imposés en base (migration 0012)
- **Acteur IA** :
  - pendant l'enregistrement d'une sortie du modèle, l'API pose `kofinex.actor = 'ai'` pour la transaction ;
  - un déclencheur `0_not_ai`, exécuté avant tous les autres, refuse alors toute écriture dans **toutes les tables métier** (83 tables) et dans le stockage des fichiers : preuves, signatures, statuts, constats, risques, procédures, balances, écritures, indicateurs… ;
  - seules les tables `ai_*` et le journal restent accessibles.
- **Sorties du modèle** : les réponses de l'assistant, les commentaires et les suggestions ne s'enregistrent **que** sous l'acteur IA, au nom du demandeur, avec leur contexte, leur contrôle des chiffres et le modèle utilisé. Il est impossible d'en fabriquer une hors de ce traitement.
- **Messages et commentaires** : ils ne sont jamais modifiés ni supprimés. Une conversation n'est donc pas supprimable.
- **Décisions humaines** :
  - acceptation, rejet et relecture se font hors acteur IA, au nom de l'utilisateur authentifié ;
  - le rejet est motivé, et une décision est unique ;
  - la proposition, ses sources et son contexte ne changent jamais ;
  - la version relue est conservée à part (`accepted_payload`).
- **Provenance** : un risque, une procédure ou un constat créé depuis une suggestion porte `origin = 'ai_suggestion'` et `ai_suggestion_id`. Il n'est accepté que si la suggestion :
  - est de même nature et vient de la même mission ;
  - a été acceptée **par la personne qui crée l'objet** ;
  - n'a pas encore été reprise.
- **L'objet naît en brouillon** :
  - un risque sans cotation (l'auditeur cote ensuite) ;
  - une procédure non attribuée et non commencée ;
  - un constat en brouillon, qui suit ensuite le circuit du lot 8.
- La provenance n'est jamais modifiable. Les feuilles de travail ne peuvent pas avoir d'origine IA.
- **Accès** :
  - conversations privées à leur auteur, réservées aux comptables, contrôleurs et analystes de l'entité ;
  - suggestions lisibles par l'équipe de mission, demandées et décidées par ses membres actifs (associé, manager, chef de mission, auditeur) ;
  - l'audité et les autres organisations ne voient rien ;
  - après l'émission de la mission, plus aucune suggestion n'est demandée ni décidée.

## 6. Ce que fait l'IA, par écran
- **Entreprise → Assistant IA** (`/companies/{id}/assistant`) :
  - conversations sur la dernière analyse terminée d'un exercice, avec le contrôle des chiffres et le contexte consultable ;
  - commentaires d'analyse par section (synthèse, bilan, compte de résultat, trésorerie, ratios, points d'attention) : brouillon IA, relu ou rejeté avec motif.
- **Mission → Assistant IA** : demande de suggestions selon les usages activés et le rôle, puis relecture, correction, acceptation ou rejet motivé :
  - risques à évaluer (droit de planification) ;
  - procédures tirées des programmes types (droit de planification ; le programme d'accueil est choisi à l'acceptation) ;
  - projet de constat à partir d'une feuille ou d'un test (audit interne et contrôle interne ; pour une déficience, le contrôle concerné est choisi à l'acceptation) ;
  - projet de synthèse des constats validés ;
  - explication des analyses du grand livre (exercice de la mission).
- Les synthèses et les explications acceptées sont conservées relues ; elles ne créent rien dans le dossier.
- Les objets issus d'une suggestion portent la mention « Suggestion IA » dans les onglets Risques, Programme et Constats.
- **Paramètres de l'organisation → Intelligence artificielle** : activation, usages, note d'accord, fournisseur et modèle en service.

## 7. API
- `GET /ai/status` : fournisseur et modèle en service, ou raison de l'indisponibilité ; jamais la clé.
- `GET` et `PUT /organizations/{id}/ai-settings`.
- Assistant financier, `/companies/{id}/ai/conversations` :
  - `GET` liste, `POST` création ;
  - `GET /companies/{id}/ai/conversations/{id}` : détail ;
  - `POST /companies/{id}/ai/conversations/{id}/messages` : question.
- Commentaires d'analyse :
  - `GET` et `POST /companies/{id}/analyses/{id}/ai-reports` ;
  - `POST /companies/{id}/ai-reports/{id}/review`.
- Suggestions d'audit, `/engagements/{id}/ai/suggestions` :
  - `GET` liste, avec les usages disponibles et la raison d'une indisponibilité ;
  - `POST` demande ;
  - `POST /engagements/{id}/ai/suggestions/{id}/accept` et `/reject`.
- Chaque action est journalisée (`ai.*`), avec le modèle, les jetons et le statut du contrôle des chiffres.

## 8. Tests
- **SQL** (`tests/sql/test_ai.sql`, 60 contrôles) :
  - activation par l'organisation et usages ;
  - sorties du modèle impossibles à fabriquer hors traitement, et figées ;
  - écritures métier refusées sous l'acteur IA (exercice, centres de coûts, preuves, signatures, programmes, phases de mission, risques) ;
  - décisions humaines et motivées ;
  - provenance : avant ou après acceptation, autre décideur, nature, reprise unique, cotation et attribution d'office refusées ;
  - relecture des commentaires ;
  - accès de l'observatrice, de l'audité et d'une autre organisation ;
  - mission émise.
- **Unitaires** (`tests/engines/test_ai.py`, 14 tests) :
  - extraction et rapprochement des chiffres ;
  - contextes financier et du grand livre ;
  - lecture des suggestions (références, codes, doublons, chiffres) ;
  - requêtes et réponses Anthropic et OpenAI ;
  - appel HTTP et erreurs, par un transport simulé : ce test exige `httpx` et tourne en CI ;
  - version des consignes.
- **Intégration** (`tests/integration/test_ai_api.py`) :
  - indisponibilité sans configuration ;
  - activation ;
  - conversation avec un chiffre non traçable signalé ;
  - commentaire relu ;
  - suggestions de risques et de procédures acceptées avec provenance, puis proposition en double écartée ;
  - accès refusés.
  - Le fournisseur y est remplacé par un double de test : c'est le seul endroit où une réponse de modèle est fabriquée.

## 9. Limites connues
- Les appels au modèle sont synchrones (délai `AI_TIMEOUT_SECONDS`) ; il n'y a ni file de tâches ni réponse en continu.
- Le contrôle des chiffres signale, il ne bloque pas. Un arrondi très grossier d'une valeur du contexte peut être jugé traçable : la relecture humaine reste nécessaire.
- Pas de suggestions pour le contrôle interne (risques ou contrôles du catalogue) ni pour l'audit financier (seuils, échantillons) : ces décisions restent entièrement manuelles.
- Les toutes nouvelles tables créées après la migration 0012 doivent recevoir le déclencheur `0_not_ai` (règle inscrite dans `CLAUDE.md`).
- Le contexte peut contenir des noms de personnes figurant dans les constats ou feuilles ; l'organisation en accepte la transmission en activant l'usage.
