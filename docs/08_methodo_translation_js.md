# Méthodologie — translation pipeline (Tome 2)

Doc de cadrage de mon périmètre dans `doc_intelligence` : parsing exhaustif Word/PPTX, rendering symétrique, et premiers étages du pipeline de traduction (Tome 2 §1.2 / §1.3). Je ne touche ni à `parsing/pdf/toc/` (Sylvère) ni aux fichiers historiques de Kezhan : tous mes ajouts sont suffixés `_js`.

## 1. Les 3 principes que je suis

Repris du cadrage Kezhan, appliqués systématiquement avant chaque ajout :

- **Structure** — la donnée passe d'un étage à l'autre par un schéma typé (DataFrame avec colonnes stables, Pydantic). Pas de dict-de-dict, pas de tuples positionnels. Si un downstream a besoin d'une info, c'est une colonne nommée.
- **Indépendance** — chaque brique a un input/output explicite et zéro coupling caché. `parse_word` ne sait rien de la traduction. `apply_translation_scope` ne sait rien du moteur LLM. Une brique peut être testée et remplacée isolément.
- **Modularité** — un fichier = une fonction publique nommée d'après ce qu'elle fait. Pas de `helpers.py` / `utils.py`. Sous-package quand un topic dépasse 2-3 fichiers.

## 2. Pipeline 4 briques (rappel CLAUDE.md)

```
parsing  →  question  →  retrieval  →  generation  →  rendering
(Tome 1)                                              (Tome 2)
```

La traduction réutilise la même architecture, en glissant juste où le travail est lourd :

| brique | RAG (Tome 1) | Translation (Tome 2) |
|---|---|---|
| parsing | `line_df` (page-line) | + `span_df` (run-level styling) |
| question | `parse_question` | `parse_translation_request` |
| retrieval | `retrieve_pages` | `apply_translation_scope` |
| generation | LLM Q→A | `translate_chunks` (LLM) + `distribute_to_runs` |
| rendering | (annotation PDF) | `build_word_document` / `build_pptx_document` |

## 3. Où vit le LLM, où il vit pas

Règle stricte qui dicte tout le découpage :

- **LLM autorisé** : `generation/translation/translate_chunks` (à venir), `generation/summarizer`, `excel_agent`. Et à l'intérieur de briques ciblées de la couche question (rewrite, decompose, spell).
- **LLM banni** : tout `parsing/`, toute `conversion/`, toute `retrieval/`, le `rendering/`, et `parse_translation_request` (qui peut être full-LLM dans le spec mais tourne d'abord en regex/keyword pour la portabilité).

Ça contraint l'archi : si une brique fait du LLM, elle est isolable dans `generation/`. Si elle est dans `parsing/` ou `retrieval/`, elle DOIT être 100% heuristique. Pas de fallback caché.

## 4. Pattern transversal : extract → modify → rebuild

Le contrat qui rend la traduction round-trip-safe sur Word/PPTX (et bientôt PDF) :

```
source.docx
   ↓ parse_word                      (extract)
{paragraph_df, span_df, table_df, doc_summary}
   ↓ <modifications sur span_df>     (modify, ex: traduction)
   ↓ build_word_document(translated_runs_df, source, output)   (rebuild)
output.docx                          ← styles/structure préservés
```

Le pivot est le `span_id`, **clé stable** déterministe :
- Word : `w_<para>_<run>` (body) ou `w_t_<table>_<row>_<col>_<para>_<run>` (cells)
- PPTX : `pp_<slide>_<shape>_<para>_<run>` ou `pp_<slide>_<shape>_t_<row>_<col>_<para>_<run>`
- PDF : `p_<page>_<line>` (line-level pour le moment, span-level à venir Tome 2)

Le rebuilder ouvre le fichier source comme template, walk dans le même ordre que l'extracteur, remplace `.text` run par run via lookup `span_id → translated_text`. Les runs absents du dict gardent leur texte d'origine (skip propre).

## 5. État actuel — ce qui marche, ce qui manque

### Livré (commits sur `main`)

| brique | fichier | état | tests |
|---|---|---|---|
| parsing/word | `src/docpipeline/parsing/word/parse_word.py` | exhaustif (body + cells de tables) | smoke + round-trip |
| parsing/pptx | `src/docpipeline/parsing/pptx/parse_pptx.py` | exhaustif (body + cells de tables) | smoke + round-trip |
| rendering/word | `src/docpipeline/rendering/word/build_document.py` | DataFrame → .docx | round-trip identité |
| rendering/pptx | `src/docpipeline/rendering/pptx/build_document.py` | DataFrame → .pptx | round-trip identité |
| translation/scope | `src/docpipeline/translation/scope_js.py` | `apply_translation_scope` + `TranslationScope` | 14/14 pytest |
| translation/request | `src/docpipeline/translation/request_js.py` | `parse_translation_request` regex/keyword | 34/34 pytest |
| question_parsing | `src/docpipeline/question_parsing/question_parsing.py` | brique question (intent + hints) | smoke notebook |

### À faire

- **`span_df` PDF** — aujourd'hui placeholder vide. PyMuPDF expose les spans dans `page.get_text("dict")`, faut les agréger. À coordonner avec Sylvère qui touche `parsing/pdf/toc/` (zone disjointe en principe mais on s'aligne avant).
- **Step 5 `translate_chunks`** — paragraph-level batching + appel LLM. Bloqué tant que pas de clé OpenAI/Anthropic dans l'env.
- **Step 6 `distribute_to_runs`** — algo proportionnel par char-count (fallback) + variante par span markers (`<b>` etc.) si le LLM coopère. Pure logique, faisable sans clé.
- **`section_breadcrumb`** dans Word/PPTX — la colonne n'existe pas encore. Sans elle, `include/exclude_sections` warning + ignore. Faut la dériver des Heading 1/2/3 (Word) ou de l'ordre des slides (PPTX).
- **OCR images** — scope-flagged Tome 2, déféré.

## 6. Évaluation des algos — chiffres

Cf. `notebooks/06_pipeline/08_bench_translation_pipeline_js.ipynb` pour le détail exécutable. Résumé :

### parse_pdf (Tome 1, repris pour la base)

Run sur l'intégralité de `data/` (71 PDFs, 6589 pages, 7 sous-corpus) :

| métrique | valeur |
|---|---|
| Erreurs | **0 / 71** |
| Pages totales | 6589 |
| Pages OCR-needed | 22 (0.3%) |
| Temps total | 43 min (~36s/PDF moyen) |
| Content-type natif pur | 59 / 71 (83%) |
| Content-type mixte | 12 / 71 (17%) |
| Tools détectés | Adobe InDesign 41%, Word 11%, Ghostscript 10%, autres 38% |

→ couverture corpus client validée.

### parse_word + rendering (round-trip identité)

Sur `tests/fixtures/contrat_assurance.docx` (10 paragraphes, 26 spans dont 15 cells de tables) :

| étape | runs replaced | runs unchanged | runs skipped | warnings |
|---|---:|---:|---:|---:|
| Round-trip identité | 0 | 26 | 0 | 0 |
| Translation FR→EN (manuelle) | 22 | 4 | 0 | 0 |

Les 4 unchanged en translation correspondent à des nombres identiques en FR/EN (`300`, `500`, `0`, etc.). Tous les styles (font, bold, italic, color, size, highlight, underline, etc.) sont préservés byte-pour-byte sur les runs non-modifiés.

### parse_pptx + rendering (round-trip identité)

Sur `tests/fixtures/contrat_assurance.pptx` :

| étape | runs replaced | runs skipped |
|---|---:|---:|
| Round-trip identité | 0 | 0 |
| Translation FR→EN | tous body + cells | 0 |

Bug fixé en cours de route (les cells de tables n'étaient pas walked dans la version initiale → slide 4 manquante en sortie). Test pytest dédié maintenant.

### translation/scope + translation/request

| fichier | tests | couverture cas |
|---|---:|---|
| `scope_js.py` | **14 / 14** | scope=None, page_range PDF (1-based normalisé), include/exclude case+accent insensible, FK Word `paragraph_index`, FK cells (toujours selected), warnings colonne absente |
| `request_js.py` | **34 / 34** | 9 langues cibles (FR/EN/DE/ES/IT/PT/NL/ZH/JA), source language, 3 styles (formal/casual/technical), page_range FR+EN, exclude FR+EN, glossaire 3 syntaxes, dédup |

Pipeline end-to-end testé sur `contrat_assurance.docx` :
```
"Translate this contract into formal English, skip the cover,
 use 'deductible' for 'franchise'."
   → request : target=en, style=formal, exclude=[Cover], glossary=[franchise→deductible]
   → scope   : 9/10 paragraphes, 25/26 spans (1 cover skip, 15 cells preserved)
   → render  : 25 replaced, 1 skipped, .docx généré
```

## 7. Ce qui reste à challenger ensemble

- Sémantique des cells de tables face au scope : aujourd'hui je les laisse toujours selected (conservateur). Si on veut les filtrer par section, il faut un `section_breadcrumb` par cell, donc enrichir parse_word.
- Page-range côté Word : pas de pagination native, on devrait soit rendre le `.docx` en PDF puis remapper, soit ignorer et documenter.
- Bench translation real (pas juste roundtrip + remplacement) : nécessite la clé LLM. Quand on l'aura, je propose un protocole d'éval sur 5-10 docs avec critères : préservation styles, fidélité sémantique, glossaire respecté.
