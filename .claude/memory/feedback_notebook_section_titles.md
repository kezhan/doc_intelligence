---
name: Notebook section title style
description: Markdown section headers in notebooks use "## N. Title" (or "## N.M Title" for sub-sections), not "## §N — Title"
type: feedback
originSessionId: ab537f14-b206-4abe-b2c3-e4e16a6f564e
---
Dans les cellules markdown des notebooks, les titres de section utilisent le format :

- **Top-level** : `## 1. Titre` (numéro, point, espace, titre)
- **Sub-level** : `## 2.1 Titre` (numéro pointé, espace, titre — pas de point après le sous-numéro)

PAS de symbole `§`, PAS d'em-dash `—` entre le numéro et le titre.

**Exemples :**

| ❌ Avant | ✅ Après |
|---|---|
| `## §1 — Une question prépare DEUX choses, pas une` | `## 1. Une question prépare DEUX choses, pas une` |
| `## §2.1 — Spell correction` | `## 2.1 Spell correction` |
| `## §3.3 — Disambiguation cues` | `## 3.3 Disambiguation cues` |

**Why:** Demande explicite de l'utilisateur ("changer style ... pour tous les notebooks présents et futurs"), pour cohérence avec la numérotation classique des chapitres/manuels.

**How to apply:** À chaque création ou modification de notebook dans `notebooks/`, vérifier que les titres `##` suivent ce format. S'applique aussi au renaming rétroactif quand on touche un notebook existant.
