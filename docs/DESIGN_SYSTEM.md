# KOFINEX — Design system

Identité : **KOFINEX**. Signature : **FINANCE • ANALYTICS • INTELLIGENCE**. Positionnement : *la plateforme intelligente de pilotage financier*.

## 1. Où sont les styles

| Élément | Fichier |
|---|---|
| Tokens (clair et sombre), mouvement réduit, chiffres tabulaires | `frontend/app/globals.css` |
| Exposition des tokens à Tailwind (`bg-primary`, `text-success-strong`, `bg-chart-1`…) | `frontend/tailwind.config.ts` |
| Thème clair / sombre / automatique : fournisseur, persistance, script anti-flash | `frontend/lib/theme.tsx` |
| Sélecteur de thème | `frontend/components/theme-toggle.tsx` |
| Logo, monogramme, signature | `frontend/components/brand.tsx` |
| Composants | `frontend/components/ui/*` : button, card, dialog, feedback (Badge, Alert, Loading, EmptyState, PageHeader), form, table, kpi-card |
| Composants de module | `Dialog` accepte `size` (`md` par défaut, `lg`, `xl`) et défile au-delà de la hauteur de l'écran ; `components/ic-list.tsx` : recherche, tri et pagination des tableaux (`useListView`, `SearchBox`, `Pager`), utilisés par le contrôle interne |
| Navigation : sidebar, barre supérieure, menu mobile | `frontend/components/app-shell.tsx` |

**Règle** : aucun code HEX ni couleur Tailwind brute (`red-600`, `slate-900`…) dans les composants. On utilise uniquement les tokens.

## 2. Tokens

| Token | Clair | Sombre | Usage |
|---|---|---|---|
| `background` | #F8FAFC | #0B1220 | Fond général |
| `foreground` | #172554 | #F8FAFC | Titres et texte |
| `card` | #FFFFFF | #172554 | Cartes, tableaux, modales |
| `secondary`, `muted` | #F1F5F9 | #1E293B | Surfaces secondaires, en-têtes de tableau |
| `muted-foreground` | #64748B | #CBD5E1 | Texte secondaire |
| `primary` | #2563EB | #2563EB | Boutons principaux, interactions, sélection |
| `link` | #1D4ED8 | bleu clair | Liens (lisibles dans les deux modes) |
| `accent` | #D6A84F | #D6A84F | Or : emblème, filets, signature. Pas de grande surface. **Seule exception pour un bouton** : les appels à l'action de la page d'accueil publique et de la démonstration (maquette de référence), texte bleu nuit. |
| `border`, `input` | #E2E8F0 | #334155 | Bordures |
| `ring` | #2563EB | bleu clair | Focus clavier |
| `sidebar` | #172554 | #080F1E | Navigation (bleu nuit dans les deux modes) |
| `success` / `warning` / `destructive` / `info` | #16A34A / #F59E0B / #DC2626 / #0EA5E9 | variantes lisibles | Icônes, bordures, fonds teintés |
| `*-strong` | teinte foncée | teinte claire | **Texte** coloré : contraste WCAG AA dans les deux modes |
| `chart-1` à `chart-5` | royal, nuit, or, information, ardoise | variantes éclaircies | Graphiques, dans cet ordre |
| `chart-blue`, `chart-orange`, `chart-green`, `chart-violet` | #2563EB, #F97316, #22C55E, #7C3AED | variantes éclaircies | Tableau de bord : produits / charges et répartitions, dans cet ordre |
| `violet` | #7C3AED | violet clair | Icône « Trésorerie », carte « Contrôle de gestion » et badge IA de la page d'accueil |
| `selection` | royal 8 % | royal 18 % | Ligne ou élément sélectionné |

Les tokens semi-transparents (`selection`, `sidebar-active`, `sidebar-hover`, `sidebar-border`) contiennent une couleur complète. Ils ne prennent donc pas de modificateur d'opacité Tailwind (`/50`).

## 3. Typographie
- Police : Inter (`next/font`).
- Graisses : titres de page 700 (`PageHeader`), titres de carte 600, texte courant 400.
- **Chiffres tabulaires** sur tous les tableaux, les cartes KPI et les champs numériques (`tabular-nums`).

## 4. Composants : conventions
- **Badges** :
  - tons `neutral` (neutre), `blue` (information), `green` (succès), `amber` (avertissement), `red` (risque), `gold` (prestige, rare) ;
  - à utiliser comme statut, toujours accompagné d'un libellé : la couleur ne porte jamais seule le sens.
- **Alertes** : `error`, `warning`, `success`, `info`, chacune avec son icône. Le texte reste dans la couleur du texte normal ; seuls le fond, la bordure et l'icône sont colorés.
- **États prévus** :
  - chargement (`Loading`), absence de données (`EmptyState`), erreur et succès (`Alert`), confirmation (`Dialog`) ;
  - désactivé (`disabled:` : opacité et curseur), survol et sélection (`hover:bg-muted`, `bg-selection`) ;
  - focus clavier visible partout (`ring`).
- **Cartes KPI** (`KpiCard`) : elles affichent des valeurs **déjà calculées** par le moteur. La flèche indique seulement le sens de la variation, sans juger si elle est favorable.
- **Graphiques** (Recharts) : couleurs `hsl(var(--chart-n))`, grille et axes en `border` / `muted-foreground`, infobulle sur `popover`.

## 5. Thème
- Trois choix : clair, sombre, automatique (préférence du système, suivie en direct).
- Le choix est mémorisé dans `localStorage` (`kofinex.theme`).
- Le changement est immédiat, sans rechargement de la page.
- Un script placé dans `<head>` applique le thème avant le premier rendu : il n'y a pas de flash du mauvais thème.
- Le sélecteur se trouve dans le menu du compte (barre supérieure) et sur les pages de connexion.
- Les animations sont courtes (150 ms) et désactivées si l'utilisateur a demandé la réduction des animations.

## 6. Logo et coquille (maquette de référence, novembre 2026)
- Emblème : quatre barres montantes et flèche de croissance, en or (`BrandMark`) ; nom « KOFINEX » et signature « Financial Intelligence » (`Logo`).
- Barre latérale bleu nuit ; rubrique active sur fond bleu royal plein ; rubriques dépliables vers les pages existantes.
- Détail du tableau de bord, des sources de données et de la démonstration : `docs/INTERFACE.md`.
