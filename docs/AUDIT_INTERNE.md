# KOFINEX — Audit interne (lot 8)

Le lot couvre le plan d'audit, la cartographie des processus et des risques, les constats, les recommandations, les plans d'action et leur suivi, ainsi que le rapport d'audit. Il s'appuie sur le socle du lot 6 : missions, équipe, indépendance, programmes, feuilles, éléments probants, gel.

**Principe** : KOFINEX ne fournit ni grille de cotation ni échelle des constats. Ce sont des données de la méthodologie chargée par l'utilisateur :
- `risk_scale` pour coter les risques ;
- `finding_scale`, ajoutée par ce lot, pour coter les constats. Format : `{"levels":[{"code","label","rank"}]}`, le rang 1 désignant le niveau le plus grave.

Le rapport ne contient que ce que l'équipe a saisi et validé ; aucun texte n'est rédigé par la plateforme.

## 1. Plan d'audit (`/organizations/{org}/plan-audit`)
- Un plan couvre une période. Il contient les missions prévues : entité, processus de la cartographie, justification fondée sur les risques (obligatoire), priorité, dates, budget en jours.
- Le plan est établi par les propriétaires et administrateurs de l'organisation et lu par tous ses membres.
- **Approbation** : instance (comité d'audit, conseil…), date et référence de la décision, enregistrées au nom de l'utilisateur qui les saisit. Un plan vide ne peut pas être approuvé.
- **Après approbation**, la base impose :
  - l'en-tête est figé ;
  - un ajout ou une modification exige un **motif**, et l'ajout est marqué comme postérieur à l'approbation ;
  - une mission prévue ne se supprime plus : elle se **reporte ou s'annule avec un motif** ;
  - chaque opération est inscrite dans un **historique** avec son motif propre.
- Une mission prévue se rattache à une mission d'audit interne de la même entité. Elle ne passe « réalisée » qu'une fois la mission émise.
- Le plan ne se clôture que si chaque mission est réalisée, reportée ou annulée.
- Synthèse affichée : nombre de missions, taux de réalisation, budget, ajouts postérieurs à l'approbation.

## 2. Cartographie (`/companies/{id}/cartographie`)
- Registre unique de l'entité (processus hiérarchisés avec leur propriétaire, risques cotés en brut et en résiduel), partagé avec le contrôle interne et l'audit financier.
- Carte probabilité × impact sur les niveaux de la grille choisie. Un risque coté hors grille est signalé, jamais corrigé ; les risques non cotés ou cotés sur une autre grille sont listés à part.
- **Historique des cotations** de chaque risque, alimenté par la base.
- Couverture : pour chaque processus, les missions du plan qui le concernent.

## 3. Constats et recommandations (onglet de la mission)
- Constat structuré : constat, référentiel, cause, conséquence, cotation sur l'échelle de la méthodologie (vérifiée en base), processus, risque de la mission, feuille de travail.
- Circuit **brouillon → validé → communiqué**, avec les règles suivantes, imposées en base :
  - la validation revient au manager ou à l'associé, en son nom, et à une **autre personne que l'auteur** ; elle exige une cotation et au moins une recommandation ;
  - la communication à l'audité revient à l'encadrement, avec une date de réponse attendue ;
  - un constat validé est figé, ainsi que ses recommandations ;
  - la remise en brouillon revient au manager ou à l'associé et exige un motif.
- **Réponse de la direction** :
  - l'audité la saisit à son nom ;
  - l'équipe peut la saisir pour l'audité, en indiquant son auteur. Elle ne peut pas l'attribuer à un compte.

## 4. Plans d'action et suivi
- Plusieurs plans d'action par recommandation : action, responsable, échéance. L'audité peut les créer sur les constats qui lui sont communiqués.
- **Mises à jour de suivi** : statut et commentaire obligatoires, nouvelle échéance si besoin, auteur et rôle enregistrés par la base.
  - Le statut et l'échéance d'un plan d'action ne changent **que** par une mise à jour, et l'historique n'est ni modifiable ni supprimable.
  - Statuts : prévue, en cours, mise en œuvre (déclarée), **vérifiée**, non mise en œuvre, risque accepté.
  - **Seul l'encadrement de la mission vérifie** une action, après qu'elle a été déclarée mise en œuvre. Une action vérifiée clôt son suivi.
  - L'acceptation du risque est déclarée par l'audité ou enregistrée par le manager ou l'associé.
- **Le suivi continue après l'émission de la mission** : constats, recommandations et contenu des plans d'action sont figés, pas leur suivi.
- Vue transversale `/organizations/{org}/suivi-recommandations` : toutes les missions accessibles, filtres par entité, par statut et par retard.

## 5. Rapport (onglet de la mission)
- Versions : projet → émis → remplacé. Il y a au plus un projet et un rapport émis à la fois.
- L'équipe rédige la synthèse, la conclusion générale (requise pour émettre) et la diffusion. KOFINEX assemble le reste : en-tête de la mission, méthodologie et sa source, nombre de constats par niveau, constats ordonnés par gravité, recommandations, plans d'action, réponses de la direction (« non reçue à la date du rapport » à défaut).
- **Émission par l'associé**, imposée en base :
  - tous les constats doivent être communiqués ;
  - le contenu doit les reprendre tous ;
  - le contenu est figé et son **empreinte SHA-256 est calculée par la base** ;
  - le rapport émis devient visible de l'audité.
- **Export Word** du projet (mention « PROJET » en en-tête) et du rapport émis (date, émetteur et empreinte en pied de page).
- **Émission d'une mission d'audit interne** : elle exige un rapport émis (règle imposée en base, qui s'ajoute aux conditions du socle).

## 6. Accès de l'audité
L'audité, membre de la mission avec le rôle `auditee` et dispensé de déclaration d'indépendance :
- voit les constats **communiqués**, leurs recommandations, les plans d'action et leur suivi, ainsi que le rapport **émis** ;
- répond aux constats et met à jour ses plans d'action ;
- ne voit pas le dossier de travail (feuilles, notes, éléments probants) ni les projets de rapport.

## 7. Limites connues
- Pas de tableau de bord du comité d'audit (prévu avec le reporting, lot 11), ni d'envoi de notifications d'échéance (lot 12).
- L'audité ne dépose pas lui-même de pièces justificatives : l'équipe les joint comme éléments probants lors de la vérification.
- Les heures réelles des missions ne sont pas suivies (pas de feuilles de temps).

## 8. Tests
- `backend/tests/sql/test_internal_audit.sql` : 59 contrôles (plan et historique, cartographie, circuit des constats, accès de l'audité, suivi, rapport et empreinte, émission, gel, cloisonnement).
- `backend/tests/engines/test_internal_audit.py` : 5 tests (échelle des constats, carte des risques, plan, ordre des constats et suivi, export Word du projet et du rapport émis).
- `backend/tests/integration/test_internal_audit_api.py` : parcours API complet (CI).
