# Diagrams — sources, rendering, edition

Quatre fichiers par schéma — chaîne de production :

```
.excalidraw  ───►  .svg  ───►  .png
   source        rendu vectoriel  rendu pixel (utilisé dans l'article)
```

| Fichier | Rôle | Généré par |
|---|---|---|
| `NN_xxx.excalidraw` | **Source** Excalidraw (JSON) | `_build_excalidraw.py` puis édité par toi |
| `NN_xxx.svg` | **Rendu vectoriel** (intermédiaire) | export depuis Excalidraw |
| `NN_xxx.png` | **Rendu pixel** ← consommé par l'article | `_export_png.py` (resvg-py, 2× scale) |
| `_build_excalidraw.py` | Génère les `.excalidraw` initiaux | toi, si tu repars de zéro |
| `_export_png.py` | Re-convertit tous les `.svg` en `.png` | toi, après ré-export Excalidraw |

L'article [docs/06_question_layer.md](../06_question_layer.md) référence uniquement les **`.png`** — c'est le format le plus universellement accepté (Medium, GitHub, autres CMS, exports PDF). Le SVG reste committé comme source vectoriel intermédiaire pour ré-export à plus haute résolution si besoin.

---

## Workflow recommandé : VS Code + extension Excalidraw

```bash
code --install-extension pomdtr.excalidraw-editor
```

Une seule fois. Ensuite :

1. **Ouvrir** : double-clic sur `01_pipeline.excalidraw` → canvas plein écran dans VS Code
2. **Modifier** : cliquer un bloc, taper pour éditer le texte ; drag pour repositionner ; barre d'outils latérale pour les couleurs / styles
3. **Exporter SVG** : barre d'outils en haut à droite → *Export image* → onglet *SVG* → *Save to file* → écraser `01_pipeline.svg`
4. **Régénérer le PNG** : `python docs/diagrams/_export_png.py` (re-fabrique les 3 `.png` depuis les `.svg` actuels, en 2× scale)
5. **Commiter** : `.excalidraw` (source) + `.svg` (intermédiaire) + `.png` (consommé par l'article)

Le canvas Excalidraw a des raccourcis classiques (drag-select, Cmd+D pour duplicate, hold Shift pour aligner).

---

## Trois manières de modifier

### 1. Visuel dans VS Code (le plus rapide)

Voir au-dessus. Idéal pour : déplacer des blocs, changer un texte, ajouter une flèche, changer une couleur via le color-picker.

### 2. JSON direct dans VS Code

Le `.excalidraw` est du JSON tout simple. Si tu n'es pas sûr·e de t'en sortir avec le canvas, ouvre-le en *texte* (clic-droit → *Reopen Editor With… → Text Editor*) :

```json
{
  "type": "rectangle",
  "id": "abc123...",
  "x": 240,
  "y": 180,
  "width": 220,
  "height": 50,
  "strokeColor": "#1d4ed8",
  "backgroundColor": "#dbeafe",
  ...
}
```

Champs utiles à modifier :

| Champ | Effet |
|---|---|
| `text` (sur les éléments `text`) | le label affiché |
| `x`, `y` | position du coin haut-gauche |
| `width`, `height` | taille |
| `strokeColor` | couleur du contour (`#hex`) |
| `backgroundColor` | couleur de remplissage (`#hex` ou `"transparent"`) |
| `fontSize` | taille du texte |
| `roughness` | 0=clean, 1=normal, 2=très tremblant (style hand-drawn) |
| `fillStyle` | `"solid"` / `"hachure"` / `"cross-hatch"` |

Sauvegarde, ré-ouvre en visuel pour voir le rendu, ré-exporte le SVG.

### 3. Régénérer depuis le script

Si tu veux **repartir d'une base propre** ou que tu as massivement changé l'idée du schéma :

```bash
python docs/diagrams/_build_excalidraw.py
```

Édite le script (positions des boxes, labels, couleurs), re-run. ⚠ **Cela écrase tes
modifications visuelles directes** sur les `.excalidraw` — donc à utiliser seulement
si tu acceptes de perdre ces modifs.

Le script est idempotent (seeds déterministes via hash) : même code → même fichier.
Bon pour les diffs git.

---

## Style hand-drawn vs clean

Les SVG actuels sont en style **flat moderne** (rectangles arrondis nets, fills pastels).
Les `.excalidraw` une fois exportés via Excalidraw donneront un style **hand-drawn**
(traits roughjs, police Virgil) — c'est le look « Stripe / Linear blog ».

Si tu préfères garder le flat moderne :
- garde les SVG actuels (édite-les avec Inkscape ou drawio.com qui ouvre les SVG)
- les `.excalidraw` restent comme source alternative

Si tu veux passer au hand-drawn :
- ouvre le `.excalidraw` dans VS Code, ajuste, exporte SVG → écrase l'ancien
- l'article ne change pas (l'`<img src=…>` est inchangé)

---

## Convention de nommage

`NN_<sujet>.{excalidraw,svg}` — où `NN` = numéro de chapitre. Permet de retrouver
quel article consomme quel schéma.

Actuel :

| Schéma | Article qui le consomme |
|---|---|
| `01_pipeline.*` | [06_question_layer.md](../06_question_layer.md) §"One function" |
| `02_architecture.*` | [06_question_layer.md](../06_question_layer.md) §"The pattern" |
| `03_word_vs_pdf.*` | [06_question_layer.md](../06_question_layer.md) §"The Word case" |

Pour ajouter un schéma au chapitre 7 : `04_*.excalidraw` (continue la numérotation),
ou repars à `01_*.excalidraw` dans un sous-dossier `chap_07/`.
