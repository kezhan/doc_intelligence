---
name: Démarche de développement — notebook-first, sortie stockable
description: Workflow standard pour toute nouvelle capacité — partir d'un notebook avec inputs explicites, extraire des fonctions documentées, produire des sorties persistées (JSON ou DataFrame → SQL)
type: feedback
originSessionId: b7c9745e-d610-4d13-bdb3-9beb9c7cdbde
---
Toute nouvelle capacité doit être prototypée dans un notebook structuré en 4 temps :
1. **Inputs clairement identifiés** en début de notebook (fichiers, fixtures, paramètres nommés explicitement, pas de magie cachée).
2. **Fonctions** extraites au fur et à mesure, avec **explications** en markdown autour (le notebook doit se lire comme un article, pas comme un script).
3. **Résultats** sortis sous une forme **facilement stockable et réutilisable**.
4. **Persistance** : JSON ou DataFrame → table SQL (SQLite/Parquet acceptable selon la taille).

**Why:** L'utilisateur travaille en boucle *build → explain → harvest*. Le notebook est la surface de design ; les fonctions y sont mises au point avant d'être promues vers `src/`. Les sorties doivent être persistables pour que les notebooks/scripts en aval chaînent dessus sans avoir à re-parser (parsing PDF/Word/etc. coûteux).

**How to apply:**
- Quand on propose un plan d'implémentation pour un nouveau notebook ou une nouvelle brique, structurer la proposition autour de ces 4 temps.
- Ne pas terminer un notebook sur un `print()` ou un affichage ad hoc — toujours dumper un artefact (`.json`, `.parquet`, table SQLite).
- Les notebooks en aval doivent **charger l'artefact**, pas réexécuter le pipeline complet.
- Les fonctions définies dans le notebook qui méritent réutilisation finissent dans `src/docpipeline/` (cf. CLAUDE.md sur la promotion code-notebook → package).
