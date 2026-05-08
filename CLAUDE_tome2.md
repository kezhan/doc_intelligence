# Guidance for Claude Code working on Tome 2

This file is the playbook for **Tome 2** of the *Enterprise Document Intelligence* series. Tome 1 (this repo, articles 1–25) covers PDF Q&A end to end. Tome 2 extends the same four-brick architecture to:

- **More document formats** — Word (`.docx`), Excel (`.xlsx`), PowerPoint (`.pptx`), mail (`.eml`/`.msg`), beyond PDF.
- **More intents than Q&A** — translation, summarization, comparison, redaction. Each intent is a generation flavor that reuses the parsing/retrieval bricks.
- **Document rendering** — produce target documents (translated `.docx`, generated `.xlsx`, summary report) that match the source document's structure.

Read [CLAUDE.md](CLAUDE.md) first. Everything below extends those rules; nothing overrides them.

## 1. Architecture: where new code goes

The four-brick spine is unchanged. Tome 2 adds two things: a **per-format split inside `parsing/`** and a sibling **`rendering/`** module mirroring it.

**Every format and every intent is a subpackage** (folder + `__init__.py`), not a flat `.py` file. The `__init__.py` is the public surface; implementation is split across one file per topic inside, the same way `parsing/pdf/` already is.

```
src/docintel/
├── core/                       # Pydantic models, types, LLM clients (shared)
│
├── parsing/                    # Brick 1 — document → DataFrames
│   ├── pdf/                    # Tome 1
│   │   ├── line_df.py
│   │   ├── page_df.py
│   │   ├── columns.py
│   │   ├── objects.py
│   │   ├── source.py
│   │   ├── toc.py
│   │   ├── parse_pdf.py
│   │   └── __init__.py         # re-exports parse_pdf, fitz_pdf_to_line_df, ...
│   ├── docx/                   # Tome 2 (Word)
│   │   ├── line_df.py
│   │   ├── runs_df.py          # styled runs (font, bold, italic, color)
│   │   ├── sections.py         # logical sections / page-equivalents
│   │   ├── tables.py           # in-document tables
│   │   ├── parse_docx.py
│   │   └── __init__.py
│   ├── xlsx/                   # Tome 2 (Excel)
│   │   ├── cell_df.py          # one row per cell (sheet, row, col, value, formula)
│   │   ├── sheet_df.py
│   │   ├── formulas.py
│   │   ├── parse_xlsx.py
│   │   └── __init__.py
│   ├── pptx/                   # Tome 2 (PowerPoint)
│   │   ├── line_df.py
│   │   ├── slide_df.py
│   │   ├── shapes.py
│   │   ├── parse_pptx.py
│   │   └── __init__.py
│   ├── mail/                   # Tome 2 (.eml / .msg)
│   │   ├── line_df.py
│   │   ├── headers.py
│   │   ├── attachments.py
│   │   ├── parse_mail.py
│   │   └── __init__.py
│   ├── types.py                # shared LineDF schema, doc_id rules
│   └── __init__.py             # documents the split, no re-exports
│
├── question/                   # Brick 2 — question → JSON
│   ├── pipeline.py             # parse_question() (Tome 1)
│   ├── intent.py               # NEW — qa | translation | summarization | comparison
│   ├── expert_dictionary.py    # Tome 1 (Article 6) — mono-lingual retrieval expansion
│   └── __init__.py
│
├── retrieval/                  # Brick 3 — filter on structured data (Tome 1)
│   └── ...
│
├── generation/                 # Brick 4 — one subpackage per intent
│   ├── qa/                     # Tome 1 — AnswerWithEvidence + llm_answer_with_evidence
│   ├── translation/            # NEW Tome 2
│   │   ├── translate_chunks.py
│   │   ├── glossary.py         # paired-language term mapping (insurance_fr_en, ...)
│   │   ├── prompts.py
│   │   └── __init__.py
│   ├── summarization/          # NEW Tome 2
│   ├── comparison/             # NEW Tome 2
│   ├── prompts.py              # cross-intent shared prompt constants
│   └── __init__.py
│
├── rendering/                  # NEW module — mirror of parsing/, data → document
│   ├── pdf/                    # absorbs Tome 1's annotation/ over time
│   │   ├── annotate.py
│   │   ├── highlight.py
│   │   └── __init__.py
│   ├── word/                   # NEW Tome 2
│   │   ├── build_document.py
│   │   ├── fill_template.py
│   │   ├── runs.py             # paragraph translate-then-redistribute
│   │   └── __init__.py
│   ├── xlsx/                   # NEW Tome 2
│   ├── pptx/                   # NEW Tome 2
│   ├── markdown.py             # report rendering — single file is fine here
│   └── types.py
│
├── pipeline/                   # Public orchestrators
│   ├── ask_document.py         # Tome 1 — Q&A on one document
│   ├── ask_corpus.py           # Tome 1 — Q&A on a whole corpus
│   ├── translate_document.py   # NEW Tome 2
│   ├── summarize_document.py   # NEW Tome 2
│   └── compare_documents.py    # NEW Tome 2
│
└── corpus/                     # Tome 1 (Part IV — index, classification, versioning)
```

A topic stays a single `.py` file only when it has one logical unit (e.g. `rendering/markdown.py`, `parsing/types.py`, `pipeline/translate_document.py`). The moment a topic needs two or three files, it becomes a subpackage. The PDF code crossed that threshold long ago, so does Word once runs/sections/tables enter the picture.

### 1.1 The directing principle: dissemination by brick

**No top-level `translation/` or `summarization/` modules.** Each new intent is a subpackage inside the brick where its work happens, not its own silo. Translation logic gets distributed:

- The **prompt + glossary integration** lives in `generation/translation/` (it's a generation concern).
- The **translation glossary** lives in `generation/translation/glossary.py` (LLM input data scoped to the translation intent).
- The **target document rebuild** lives in `rendering/word/` (mirror of `parsing/docx/`).
- The **public entry point** lives in `pipeline/translate_document.py` (orchestrator, single file).

Same pattern for summarization, comparison, redaction. The intent name is a *subpackage name* inside `generation/` and (when it produces an artifact) inside `rendering/`, never a top-level package.

### 1.2 Symmetry parsing ↔ rendering

```
parsing  (document → data)        rendering  (data → document)
  pdf/                              pdf/    (highlights, annotations)
  docx/                             word/   (fill template, preserve runs)
  xlsx/                             xlsx/
  pptx/                             pptx/
```

The current `annotation/` module (PDF highlighting from Tome 1) is the seed of `rendering/pdf/`. When you start adding Word output, **move PDF annotation under `rendering/pdf/`** and update the imports. Don't keep `annotation/` as a parallel hierarchy — collapse it into `rendering/`.

## 2. Word parsing & translation — the active work

The other dev is currently working on **Word translation**. The flow:

1. **Parse source** — `parsing/docx/parse_docx.py::parse_docx(path) -> dict` returns the same-shape dict as `parse_pdf`: `line_df`, `section_df` (Word has logical sections, not fixed pages), `parsing_summary`, plus Word-specific tables (`runs_df`, `table_df`, `style_df`).
2. **Question / intent parsing** — `question/intent.py` classifies the user request as `translation` and extracts target language, glossary name, formality level.
3. **Translate chunks** — `generation/translation/translate_chunks.py::translate_chunks(line_df, target_lang, glossary)` returns a translated `line_df` with the same row count and `(section_id, line_num)` keys.
4. **Rebuild target** — `rendering/word/build_document.py::build_word_document(translated_line_df, source_path)` reconstructs the `.docx` preserving runs, styles, paragraph numbering, table cells, headers/footers.

### 2.1 What "preserving structure" means for Word

Translation that destroys formatting is unusable in production. Word documents have:

- **Runs** — a paragraph is a sequence of runs, each with its own font/bold/italic/color. Translated text must be re-distributed across runs that match the original styling.
- **Numbering & list levels** — auto-numbered lists (`1.`, `1.1`, `a)`) are maintained by the document, not the text. Don't translate the numbers.
- **Fields** — `{ DATE }`, `{ PAGE }`, `{ REF }` are dynamic. Skip them.
- **Tables** — translate cell-by-cell, never collapse rows.
- **Headers / footers / footnotes** — separate streams; translate them independently and write back to their own zones.
- **Track changes / comments** — preserved or stripped per a flag (default: stripped, since they rarely have legal value in the translated copy).

`python-docx` is the standard library; for runs preservation, the trick is the **paragraph-level translate-then-redistribute** pattern: send the full paragraph text to the LLM, get the translation back, then split it across runs proportionally to the source run boundaries (best-effort) — never one run at a time, which destroys cross-run grammar.

### 2.2 The translation glossary

`generation/translation/glossary.py` exposes:

```python
class Glossary(BaseModel):
    name: str                   # "insurance_fr_en"
    source_lang: str            # "fr"
    target_lang: str            # "en"
    entries: list[GlossaryEntry]

class GlossaryEntry(BaseModel):
    source: str                 # "franchise"
    target: str                 # "deductible"
    note: str | None = None     # context / domain restriction

def load_glossary(name: str) -> Glossary: ...
def render_glossary_for_prompt(glossary: Glossary) -> str: ...
```

The glossary is **inlined into the system prompt** (not retrieved per-chunk), because it's typically short (50–500 entries) and the LLM enforces it best when it's part of the prompt.

This is **distinct** from the Article 6 expert dictionary in Tome 1 (`question/expert_dictionary.py`): that one is mono-lingual and used for retrieval keyword expansion. The translation glossary is paired-language and used for output enforcement.

### 2.3 Public entry point

`pipeline/translate_document.py` is the orchestrator:

```python
from pathlib import Path
from docintel.pipeline import translate_document

result_path = translate_document(
    document_path="contract.docx",
    target_language="en",
    glossary_name="insurance_fr_en",  # optional
    preserve_track_changes=False,     # optional
)
# result_path is the translated .docx file
```

Same shape as `ask_document` and `ask_corpus` — single function, named arguments, returns the artifact path.

## 3. Conventions

These are extensions of [CLAUDE.md](CLAUDE.md). Read CLAUDE.md first.

### 3.1 Imports — format-explicit

```python
# Good
from docintel.parsing.pdf import parse_pdf
from docintel.parsing.docx import parse_docx
from docintel.generation.translation import translate_chunks
from docintel.rendering.word import build_word_document

# Bad — bypasses the per-format split
from docintel.parsing import parse_pdf, parse_docx
```

The top-level `parsing/__init__.py` does not re-export anything. The format is part of the contract.

### 3.2 Naming

- **One method = one script** (same as Tome 1). When `generation/translation/` hosts several strategies (LLM-only, LLM+glossary, LLM+TM lookup), each strategy gets its own file inside the subpackage.
- **Variables describe content**: `translated_line_df`, `glossary_entries`, `target_path` — never `result`, `out`, `tmp`.
- **No abbreviations**: `target_language` not `tgt_lang`, `glossary` not `gloss`.

### 3.3 File-format module shape

A new format module (`parsing/docx.py`, `parsing/xlsx.py`, ...) exposes one entry point matching `parse_pdf`'s contract:

```python
def parse_docx(path: str | Path) -> dict:
    """One Word document in, a dict of relational tables out.

    Returns:
        line_df:         one row per text line (paragraph segments + table cells + headers)
        section_df:      one row per logical section
        runs_df:         one row per styled run (font/bold/italic/color/run_id)
        table_df:        one row per table cell (table_id, row, col, text)
        parsing_summary: dict (n_sections, n_lines, has_track_changes, source_creator, ...)
    """
```

The `line_df` schema is **the cross-format contract**: `(doc_id, section_id, line_num, text, char_count, ...)`. Whatever else a format adds (PDF bboxes, Word runs, Excel formulas) lives in format-specific tables alongside.

### 3.4 Tests

Each format gets a tests file: `tests/parsing/test_docx.py`, `tests/parsing/test_xlsx.py`, etc. Same pattern for rendering and generation: `tests/rendering/test_word.py`, `tests/generation/test_translation.py`. Use small, real fixtures committed under `tests/fixtures/<format>/`. Never use proprietary client documents as test fixtures (same rule as Tome 1).

### 3.5 What stays in Tome 1

- `parsing/pdf/` — frozen during Tome 2 work unless a real bug surfaces.
- `pipeline/ask_document.py`, `pipeline/ask_corpus.py` — frozen.
- `corpus/` (classification, versioning, filtering, SQL agent) — frozen.
- Articles 1–25 in `book/` — frozen. Tome 2 articles will be a separate numeric range (start at 26 or restart from 1 with a Tome-2 prefix; the author decides at series-launch time).

If Tome 2 work surfaces a real Tome 1 bug, file it as a tracked issue and fix it explicitly — don't rewrite Tome 1 modules opportunistically.

## 4. Writing for Tome 2 (when articles start)

Tome 2 articles will follow the same Medium-style conventions as Tome 1: 3-component header (`*Article N of Enterprise Document Intelligence*` / `# Title` / `*subtitle*`), three-zone diagram grammar (amber/blue/emerald), pill-box code-as-image, plain-English voice, no AI tells.

Re-read [CLAUDE.md](CLAUDE.md) §"Manuscript", §"Style", §"Visual assets", §"Audit checklist" — those are unchanged. The series voice is a single voice across both tomes.

The cross-tome rule that *is* worth restating: **never reference real proprietary documents** (insurance contracts, corporate annual reports, client documents from `data/`) in any published article. Tome 2 examples use the same fictional broker corpus from Tome 1 Part IV, plus public-domain Word/Excel sources (US/EU government docs, OECD, openly-licensed templates).

## 5. Don'ts

- **Don't create top-level intent modules** (`translation/`, `summarization/`, `comparison/`). Disseminate per brick.
- **Don't break the format-explicit import contract**. `from docintel.parsing.pdf import ...` always.
- **Don't translate run-by-run.** Paragraph-level translate-then-redistribute is the documented pattern.
- **Don't re-implement parsing helpers per format.** Whatever can live in `parsing/types.py` (line_df schema, doc_id rules, common cleanup) goes there once.
- **Don't expose a Word-only public API.** `translate_document` takes any supported format and dispatches.
- **Don't reach into Tome 1's PDF code from Tome 2 modules.** Cross-tome dependencies go through public re-exports (the `__init__.py` of each subpackage), never internal modules.
