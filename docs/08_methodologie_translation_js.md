# Methodology — translation pipeline (Tome 2 scope)

This document describes how I approach the work in `doc_intelligence`, and why I make the choices I make. It is the companion of [`CLAUDE_tome2_translation.md`](../CLAUDE_tome2_translation.md): that file is the implementation spec; this one is the reasoning. My scope is exhaustive parsing of Word/PPTX, symmetric rendering, and the early stages of the translation pipeline (Tome 2 §1.2 and §1.3). Sylvère owns `parsing/pdf/toc/`, and Kezhan's historical files are off-limits — every file I add is suffixed with `_js` so the boundary is visible at a glance.

A reader who skips to the bench numbers in §6 is missing the point of the document. Numbers come from a methodology; if the methodology is wrong, the numbers measure the wrong thing. So §1 to §5 explain the reasoning that produced the numbers.

## 1. Three principles that guide every decision

I follow three principles, in this order, before writing any new file. They were laid down by Kezhan during cadrage and they keep recurring as the right test when an architecture choice is unclear.

**Structure.** Data flows between stages through a typed schema — a DataFrame with stable, named columns, or a Pydantic model. Never a dict-of-dicts, never a positional tuple, never an undocumented kwargs bag. If a downstream stage needs a piece of information, it is a column with a name. The principle has a sharper edge than it looks: it forbids "I'll just add a flag here" patches. A new piece of information goes into the schema, where every consumer sees it, or it goes nowhere.

**Indépendance.** Each brick has an explicit input and output, and zero hidden coupling to the others. `parse_word` knows nothing about translation. `apply_translation_scope` knows nothing about which LLM (if any) will run downstream. `build_word_document` knows nothing about how its input was produced. The point is that any brick must be testable, replaceable, and reasonable about in isolation — without spinning up the rest of the pipeline.

**Modularité.** One file holds one publicly named function, named after what it does. There is no `helpers.py`, no `utils.py`, no `common.py`. When a topic outgrows two or three files, it becomes a sub-package with its own `__init__.py` that re-exports the public surface. The principle prevents the slow accretion of orphan utilities that nobody is responsible for and that quietly become the wrong abstraction.

These three principles compound. Without **Structure**, you cannot have **Indépendance** because every brick has to reverse-engineer what the previous one meant. Without **Indépendance**, you cannot have **Modularité** because every change leaks into half the codebase. The order matters when there is a tension to resolve.

## 2. Why the four-brick pipeline survives the shift to translation

Tome 1 designed the pipeline around RAG: `parsing → question → retrieval → generation`. The temptation, when translation arrives, is to invent a parallel architecture — translation feels different enough that it might want its own bricks. The temptation is wrong.

The four bricks are not about RAG specifically; they are about *what any document task needs*. Translation also needs to parse the document into a structured form (parsing), to understand what the user is asking (question), to scope down to the right subset of the document (retrieval), to produce new text (generation), and now also to write back into the source format (rendering, which is a fifth brick added by Tome 2). The work shifts where the heavy lifting sits — parsing carries most of the format-specific complexity, generation carries the LLM lift, rendering carries the round-trip safety — but the *structure* is the same.

Following the existing structure has a second benefit: every brick that already exists for RAG can be reused, partially or fully, for translation. The retrieval brick that filters lines by page range for citations also filters spans by page range for translation. The question brick that extracts intent for QA also extracts target language for translation. Reuse keeps the surface area small.

The four bricks for translation map as follows:

| brick | what it does for translation |
|---|---|
| parsing | extracts spans/runs (finer than RAG's lines), preserving styling |
| question | parses the user's message into a `TranslationRequest` |
| retrieval | filters spans by scope — page range, sections to include or exclude |
| generation | calls the LLM, redistributes translated paragraphs across source spans |
| rendering | writes a new file in the source format, keeping styles intact |

The single line that summarizes everything I have built so far: **a message and a source document go in, a translated document comes out, and the styles survive the trip.**

## 3. Where the LLM lives, and why this constraint shapes everything

Kezhan's rule, reaffirmed in [`CLAUDE.md`](../CLAUDE.md): the LLM is reserved for `generation/translation`, `generation/summarizer`, and the `excel_agent`. Inside the question layer, it is allowed within ciblées bricks (`rewrite`, `decompose`, `spell`) but never as orchestrator. Everywhere else — every parser, every converter, every retrieval helper, every renderer — runs on heuristics and specialized libraries with **zero LLM calls**.

The constraint is easy to state and quietly enforces a lot. It means a parser cannot have a "fallback to LLM if PyMuPDF didn't extract anything good"; either the parser is deterministic and you fix the heuristic, or you don't ship it. It means scoping by section cannot rely on the LLM to "understand" what the user means by "Annexes"; either there is a `section_breadcrumb` column produced upstream and matched by string normalization, or the function emits a warning and ignores the filter. It means rendering cannot ask the LLM to "redistribute the translation gracefully across runs"; that has to be a deterministic algorithm in `distribute_to_runs`, with the LLM only producing the source-language paragraph and the target-language paragraph.

The constraint also disciplines the LLM bricks themselves. When the LLM is the entire content of a brick, that brick can be rewritten, replaced, or stubbed without affecting anything else. `parse_translation_request`, in my implementation, is regex-and-keyword today (no LLM, no API key needed); the day a real LLM call replaces it, every consumer downstream (`apply_translation_scope`, `translate_chunks`, `build_word_document`) sees the same `TranslationRequest` object and does not change a line.

## 4. Extract → modify → rebuild — the round-trip strategy

Translation is a round trip. The source goes through the pipeline; a structurally identical document, with translated text, comes out. The strategy that makes this safe across Word, PPTX, and (eventually) PDF is the same in all three cases:

```
source.docx
   ↓ parse_word                                  (extract)
{paragraph_df, span_df, table_df, doc_summary}
   ↓ <modifications on span_df>                  (modify)
   ↓ build_word_document(modified_runs_df,
                         source, output)         (rebuild)
output.docx                ← styles, structure, metadata preserved
```

The pivot of the strategy is the `span_id`, a deterministic, reproducible key that uniquely identifies every styled run in the document. The format encodes the location:

- Word body: `w_<para>_<run>`
- Word table cell: `w_t_<table>_<row>_<col>_<para>_<run>`
- PPTX body: `pp_<slide>_<shape>_<para>_<run>`
- PPTX table cell: `pp_<slide>_<shape>_t_<row>_<col>_<para>_<run>`
- PDF: `p_<page>_<line>` (line-level today; span-level is on the Tome 2 to-do list)

Why is the `span_id` central? Because the rebuilder does not construct the document from scratch — that path loses too many invisible attributes (theme, header/footer relationships, embedded styles). Instead, the rebuilder opens the source as a template, walks the same tree the parser walked, and at each run looks up `span_id → translated_text`. Runs absent from the lookup keep their original text. Runs present get replaced. Nothing else changes.

This pattern has two non-obvious consequences. First, **the parser and the renderer are mirror images**: any tree node visited by `parse_*` must be visited by `build_*_document`, in the same order. A walk asymmetry means that some runs are extracted but never replaced (silent loss), or some runs are replaced from the wrong key (corruption). The bug I caught last week — table cells of Word being extracted but skipped during rebuild — is exactly that asymmetry. Now both walks include the cell paragraphs, and the round-trip identity test enforces the symmetry.

Second, **the `span_id` is the contract between bricks**. The translation brick does not need to know how the parser built the id; it only needs to know that the id exists, is stable, and is unique. The renderer does not need to know how the translation produced new text; it only needs to know that some span_ids have new text and others don't. The id is the seam.

## 5. What is built and what is missing — and why

### What is built

| brick | file | status |
|---|---|---|
| parsing/word | `src/docpipeline/parsing/word/parse_word.py` | exhaustive: body + table cells |
| parsing/pptx | `src/docpipeline/parsing/pptx/parse_pptx.py` | exhaustive: body + table cells |
| rendering/word | `src/docpipeline/rendering/word/build_document.py` | DataFrame → .docx, identity round-trip verified |
| rendering/pptx | `src/docpipeline/rendering/pptx/build_document.py` | DataFrame → .pptx, identity round-trip verified |
| translation/scope | `src/docpipeline/translation/scope_js.py` | `apply_translation_scope` + `TranslationScope` schema |
| translation/request | `src/docpipeline/translation/request_js.py` | `parse_translation_request`, regex/keyword (no LLM yet) |
| question_parsing | `src/docpipeline/question_parsing/question_parsing.py` | intent + structural hints (RAG-side) |

### What is missing, and the reasoning behind the gaps

**`span_df` for PDF.** Tome 2 §0 demands it: RAG uses lines, translation uses spans. `parse_pdf` currently returns `span_df` as an empty placeholder. PyMuPDF's `page.get_text("dict")` already exposes spans with `text`, `font`, `size`, `color`, `flags`, and `bbox` — the work is aggregation, not extraction. I have not built it yet because Sylvère is now active in `parsing/pdf/toc/` and I want to coordinate before touching `parse_pdf.py`, even if the two zones are technically disjoint.

**`translate_chunks` (Step 5 of the build order).** This is the LLM brick — paragraph-level batching, glossary injection, structured-output prompt, redistribution back to spans. It is blocked on having an OpenAI or Anthropic API key in the environment. The schema and the surrounding plumbing are designed to plug in without modifying anything upstream or downstream.

**`distribute_to_runs` (Step 6).** Pure logic, no LLM. The algorithm splits a translated paragraph across the source's styled runs by character-count proportion (fallback) or by span markers when the LLM cooperates (better). I have the spec and a clear path; I will build it next, since it does not need an API key.

**`section_breadcrumb` column.** Word and PPTX parsers do not yet emit a per-paragraph section path. Without it, `apply_translation_scope`'s `include_sections` and `exclude_sections` arguments emit a warning and pass through. The fix is to derive the breadcrumb from `Heading 1`/`Heading 2`/`Heading 3` styles in Word and from slide order in PPTX. This is the next clear improvement in scope quality.

**Image OCR translation.** Scope-flagged in Tome 2 itself. Deferred to a later phase.

I list the gaps explicitly because a methodology that hides what it does not do is dishonest about its coverage. Every gap above has a clear shape, a known input/output, and a chosen reason for the deferral.

## 6. Evaluation — numbers, with what they mean

The full executable bench is in [`notebooks/06_pipeline/08_bench_translation_pipeline_js.ipynb`](../notebooks/06_pipeline/08_bench_translation_pipeline_js.ipynb). The notebook outputs are saved in the file, so a reader who does not want to run anything can scroll through and see the same figures I am about to discuss.

### parse_pdf on the full client corpus

I ran `parse_pdf` on every PDF in `data/`: 71 files across seven sub-corpora (`CG contrats MRH`, `annuel_reports`, `insurance`, `cmo`, `nist`, `paper`, `reports`), totaling 6589 pages.

| metric | value |
|---|---|
| files parsed without error | **71 / 71** |
| total pages | 6589 |
| pages flagged as needing OCR | 22 (0.3%) |
| total wall time | 43 minutes (≈ 36 s per PDF) |
| documents pure native | 59 / 71 (83%) |
| documents mixed (some pages scanned) | 12 / 71 (17%) |

The interesting figure is the 17% of documents that are *mixed*. These are the cases that justify the per-page routing strategy in `parse_pdf`: a single file decision (native or scanned) would mishandle them. The architecture choice — classify each page independently, route to the right extractor — earns its complexity on this 17%.

### Round-trip identity, Word and PPTX

The most important thing the rendering bricks must do, before any translation, is **not break the document**. I verify this with an identity round-trip: parse, then rebuild without modifying anything, then check that the output document holds the same number of runs as the source, all in the same order, with the same styles.

For `tests/fixtures/contrat_assurance.docx` (10 paragraphs, 26 spans of which 15 are inside table cells):

| run | replaced | unchanged | skipped |
|---|---:|---:|---:|
| identity round-trip | 0 | 26 | 0 |
| translation FR→EN | 22 | 4 | 0 |

The 4 unchanged runs in the translation pass are numeric tokens (`300`, `500`, `0`) that are identical in both languages. Every styling attribute — font, size, bold, italic, underline, color, highlight, character style — survives the trip on the unchanged runs. The 22 replaced runs accept the new text but inherit the run's formatting from the source, since the translation only swaps `text`, never the styling attributes.

PPTX behaves the same way on `contrat_assurance.pptx` (4 slides, 28 runs, identity replaced=0).

### Translation scope and request — unit tests

The two pieces I added under `translation/` are pure-logic and easy to test exhaustively. The numbers below are not benchmarks of an algorithm against reality; they are coverage counts of cases the code has been hardened against.

| file | test count | what it covers |
|---|---:|---|
| `scope_js.py` | **14 / 14** | `scope=None`, page range with PDF (with 1-based normalization to 0-based PyMuPDF), include/exclude with case+accent insensitive matching, the FK propagation for Word `paragraph_index`, the cell-FK fix, warnings when columns are missing |
| `request_js.py` | **34 / 34** | nine target languages (FR/EN/DE/ES/IT/PT/NL/ZH/JA), source-language detection, three styles (formal/casual/technical), page range in French and English, exclude clauses in French and English, three glossary syntaxes, deduplication |

### End-to-end on the contract fixture

The pipeline I have so far is:

```
"Translate this contract into formal English, skip the cover,
 use 'deductible' for 'franchise'."
   ↓ parse_translation_request
   target = en, style = formal,
   exclude = [Cover], glossary = [franchise → deductible]
   ↓ apply_translation_scope
   9 of 10 paragraphs selected, 25 of 26 spans selected,
   1 cover span skipped, 15 cells preserved
   ↓ build_word_document (with translated text fed in)
   25 runs replaced, 1 skipped (cover keeps its source text),
   styles preserved on all 26 runs
```

The interesting line is the cell preservation. Cells are inside table paragraphs that have a cell-internal `paragraph_index` (almost always `0`), which collides with body paragraphs that share the same index. A naive foreign-key merge would incorrectly skip cells whenever paragraph `0` is excluded. The current code recognizes the `in_table` column on `span_df` and routes cells through a separate path that always selects them, on the grounds that cells do not yet have a `section_breadcrumb` to scope against. This is conservative: it never *wrongly* excludes a cell. When parse_word starts emitting per-cell breadcrumbs, the rule will tighten.

## 7. What I want to challenge together

A methodology should end with the questions it does not yet answer.

**Cell-level scope.** Today I always include table cells when scoping. The right behavior, when the user excludes a section that contains a table, depends on whether the table belongs to the section or sits across sections. Word does not make this trivial to determine. We should agree on the convention before parse_word ships a per-cell breadcrumb.

**Word page ranges.** Word has no native pagination — page count depends on margins, fonts, and the rendering engine. If we want `page_range` to work on `.docx`, the options are: render to PDF first and remap, or document that page-range is PDF-only. I lean toward the second; it is honest about what the format affords.

**Real translation evaluation.** The bench above measures structural fidelity (round-trip identity, scope correctness, schema coverage). It does not measure the linguistic quality of a real translation, because there is no LLM in the loop yet. Once we have the API key and `translate_chunks` is in place, I propose a small protocol on five to ten documents from the corpus, scoring three things: style preservation (visual diff), semantic fidelity (back-translation comparison), and glossary compliance (term-by-term presence check). Numbers without protocol are noise; we should agree on the protocol before the numbers exist.
