# DÉMARCHE MÉTHODOLOGIQUE
## Traduction de documents avec préservation du style — Word, PPTX, PDF

## 1. Objectif

À partir d'un document source (.docx, .pptx, .pdf) et d'un message utilisateur, produire un document traduit qui **préserve fidèlement la structure et les styles d'origine** : mêmes paragraphes, mêmes tableaux, mêmes polices, mêmes couleurs, mêmes formats de listes, mêmes en-têtes/pieds de page.

L'API publique est unique : `translate_document(path, target_language, ...)`. Le dispatch par format (.docx / .pptx / .pdf) est interne. Le résultat est un nouveau fichier au même format que la source.

## 2. Démarche en 5 étapes

| # | Étape | Ce que l'on fait | Résultat attendu |
|---|---|---|---|
| 1 | **Parsing** | Le parser ouvre le document une seule fois et émet un schéma DataFrame stable : `paragraph_df`, `span_df` (un span = unité minimale de styling cohérent), `table_df`, `image_df`, `doc_summary`. Chaque span reçoit un `span_id` déterministe (ex. `w_<para>_<run>` Word, `pp_<slide>_<shape>_<para>_<run>` PPTX). Aucun LLM. | DataFrames + `span_id` stable |
| 2 | **Question** | Le message utilisateur est parsé en `TranslationRequest` Pydantic : langue cible, langue source, scope (page_range, include/exclude_sections), style (formal/casual/technical), glossaire ad-hoc. Implémentation regex/keyword (mode dégradé sans LLM) ; voie LLM ajoutable sans casser le schéma. | `TranslationRequest` typé |
| 3 | **Scope** | `apply_translation_scope(line_df, span_df, scope)` filtre les lignes et propage la sélection aux spans via clé étrangère auto-détectée (`paragraph_index` Word / `(page_num, line_num)` PDF). Retourne 4 DataFrames : `selected_line`, `selected_span`, `skipped_line`, `skipped_span`. Aucun LLM. | spans à traduire vs spans à laisser intacts |
| 4 | **Generation** | `translate_chunks` regroupe les lignes en chunks ≤ 8000 caractères (jamais à cheval sur deux sections), envoie chaque chunk au LLM avec glossaire inliné dans le prompt système, sortie JSON list[str] de même longueur. `distribute_to_runs` redistribue ensuite la traduction du paragraphe sur les runs source proportionnellement au char-count (fallback) ou via span markers (`<b>`, `<i>`) si le LLM coopère. | spans avec texte traduit |
| 5 | **Rendering** | `build_word_document` / `build_pptx_document` ouvre la source comme template, walk le même arbre que le parser, remplace `.text` de chaque run via lookup `span_id → translated_text`. Les runs absents du dict gardent leur texte d'origine. Aucun LLM. | document traduit, styles préservés |

**Pattern transversal : extract → modify → rebuild.** Le `span_id` est la clé stable qui fait le pont entre les 5 étapes. Le parser et le renderer sont des miroirs : tout nœud visité par `parse_*` doit être visité par `build_*` dans le même ordre, sinon perte silencieuse de runs.

## 3. Rôle du LLM dans le pipeline

Le LLM intervient **uniquement à l'étape 4** (Generation), pour traduire le texte. Tout le reste — parsing, scope, rendering — est 100% heuristique et déterministe.

L'étape 2 (Question) admet une voie LLM optionnelle pour parser des messages utilisateur très libres, mais le pipeline doit pouvoir fonctionner sans elle (mode dégradé regex/keyword, aujourd'hui par défaut). Cette discipline garantit que le pipeline tourne sans clé API pour tout sauf la traduction elle-même, et qu'aucune brique ne dépend silencieusement d'un fallback LLM caché.

## 4. Procédure d'évaluation des algorithmes

### 4.1 Constitution du corpus de référence

- **Corpus structurel (parsing + rendering)** : fixtures dédiées dans `tests/fixtures/` (.docx, .pptx) couvrant body + tables + listes + styles variés. Ground truth = nombre exact de runs + attributs de styling extraits manuellement.
- **Corpus PDF** : 71 PDFs de `data/` (sous-corpus client : CG contrats MRH, annual reports, insurance, cmo, nist, paper, reports). Ground truth = nombre de pages, content_type (native / mixed / scanned).
- **Corpus traduction** : sous-ensemble de 5 à 10 documents du corpus client, traduction de référence produite à la main pour 3 langues cibles (EN, DE, ES).

### 4.2 Métriques

| Métrique | Formule | Ce qu'elle mesure |
|---|---|---|
| Couverture parsing | PDFs sans erreur / Total PDFs | Robustesse du parser sur le corpus réel |
| Identité round-trip | runs_replaced sur parse → render sans modif | Invariant structurel : 0 attendu |
| Préservation styles | runs avec tous attributs identiques / runs unchanged | Aucune dérive de formatage |
| Précision scope | spans correctement classés selected/skipped / total | Fiabilité du dispatching |
| Couverture pytest | tests passants / tests collectés | Couverture des cas (langues, syntaxes, formats) |
| Fidélité traduction | titre/glossaire/style préservés (manuelle) | Qualité linguistique — nécessite LLM en place |
| Précision glossaire | termes cibles présents dans la sortie / termes demandés | Respect du glossaire utilisateur |

**Critère d'acceptation** : couverture parsing ≥ 99 %, identité round-trip = 100 %, précision scope ≥ 95 %, fidélité traduction ≥ 90 % sur le corpus de référence.

### 4.3 Protocole

- **Étape 1 — Test unitaire par brique** : pytest sur chaque module (parsing, scope, request, rendering) sur fixtures dédiées. Objectif : 100 % vert avant intégration.
- **Étape 2 — Test intégration structurel** : parse → render sans modif sur tout le corpus, vérifier `runs_replaced=0` partout. Tout écart est un bug bloquant.
- **Étape 3 — Test intégration scope** : message libre → request → scope → render avec faux remplacement (`[EN] {text}`), vérifier que les spans skipped gardent leur texte source et que les selected sont bien remplacés.
- **Étape 4 — Test intégration translation (avec LLM)** : pipeline complet sur les 5–10 documents du corpus de référence, dans 3 langues cibles. Comparaison avec ground truth sur les 7 métriques.
- **Étape 5 — Analyse des échecs** : classifier par type (parser a raté un run / scope a mal filtré / LLM a perdu un terme du glossaire / renderer a perdu un style). Itérer sur la brique fautive uniquement.

## 5. État actuel — étapes livrées

| brique | fichier | état |
|---|---|---|
| Parsing Word | `src/docpipeline/parsing/word/parse_word.py` | exhaustif, body + cells de tables |
| Parsing PPTX | `src/docpipeline/parsing/pptx/parse_pptx.py` | exhaustif, body + cells de tables |
| Rendering Word | `src/docpipeline/rendering/word/build_document.py` | identité round-trip vérifiée |
| Rendering PPTX | `src/docpipeline/rendering/pptx/build_document.py` | identité round-trip vérifiée |
| Scope | `src/docpipeline/translation/scope_js.py` | 14 / 14 tests verts |
| Request | `src/docpipeline/translation/request_js.py` | 34 / 34 tests verts |

**Reste à livrer** : `span_df` PDF (Tome 2 §0), Step 5 `translate_chunks` (bloqué sur clé LLM), Step 6 `distribute_to_runs` (faisable sans clé), `section_breadcrumb` Word/PPTX (dérivable des Heading 1/2/3).

## 6. Premiers chiffres

Bench détaillé exécutable dans [`notebooks/06_pipeline/08_bench_translation_pipeline_js.ipynb`](../notebooks/06_pipeline/08_bench_translation_pipeline_js.ipynb).

| mesure | valeur |
|---|---|
| parse_pdf — couverture corpus | **71 / 71 PDFs sans erreur**, 6589 pages |
| parse_pdf — distribution | 83 % natifs purs, 17 % mixtes (justifie per-page routing) |
| Round-trip Word | 26 / 26 spans préservés, replaced=0 |
| Round-trip PPTX | 28 / 28 runs préservés, replaced=0 |
| Pipeline e2e Word | 25 spans replaced + 1 cover skipped (préservé), styles conservés |
| Tests pytest scope_js + request_js | **48 / 48 verts** |
