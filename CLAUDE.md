# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

`docpipeline` — modular document-processing toolkit (PDF/Word/Excel/PPTX/email). The repo also contains a question-understanding layer ([src/question/](src/question/)), design notes + diagrams in [docs/](docs/), and notebooks demonstrating each piece.

**Language convention** — code identifiers are always English. For prose:
- Core code (comments, docstrings, errors) in [src/docpipeline/](src/docpipeline/) and the earlier notebooks (04–06) are in **French**.
- Notebooks **07+** are in **English (US style)** per recent direction (USD currency, MM/DD/YYYY dates, US labels like *BILL FROM* / *BILL TO*).

Match the convention of the file you're editing.

PEP 621 / src layout: package at [src/docpipeline/](src/docpipeline/), build config in [pyproject.toml](pyproject.toml). Python ≥ 3.10.

## Commands

```bash
pip install -e .[dev]              # editable install + pytest/ruff/mypy/build
pip install -e .[all]              # also: openai, anthropic, pytesseract, docling, pywin32

pytest tests/ -v                   # full suite
pytest tests/test_parse_pdf.py -v  # one file
pytest tests/test_parse_pdf.py::test_name -v   # one test

ruff check src/ tests/             # lint
mypy src/                          # strict typing (configured in pyproject.toml)

python -X utf8 demo.py             # all 7 interactive demos against tests/fixtures/
python -X utf8 demo.py 1           # single demo (1..7)

docpipeline --help                 # CLI entry point ([src/docpipeline/cli.py](src/docpipeline/cli.py))

python docs/diagrams/_build_excalidraw.py   # regenerate .excalidraw sources
python docs/diagrams/_export_png.py         # SVG → PNG (2× scale via resvg-py)
```

**Windows console:** stdout/stderr must be reconfigured to UTF-8 — see boilerplate in [src/docpipeline/cli.py:25-32](src/docpipeline/cli.py#L25-L32) and [demo.py:6-13](demo.py#L6-L13). Always invoke Python with `-X utf8` on Windows when scripts print accented French.

## Repository layout

```
src/
├── docpipeline/        Main toolkit (4 transverse stages × N formats — see "docpipeline" below)
└── question/           Question-understanding layer (registry + presets — see "question layer" below)

notebooks/              .ipynb files only — no .py helpers. Organized by topic chapter:
├── 01_document_parsing/{pdf,word,excel,pptx,email}/   per-format parsing (pdf/word/pptx also have a toc/ subfolder)
├── 02_question_parsing/                               question-understanding layer
├── 03_retrieval/
├── 04_generation/
├── 05_rendering/                                       reconstitution / annotation / conversion outputs
├── 06_pipeline/                                        end-to-end orchestration
└── _outputs/                                           Per-notebook output subdirectories

docs/                   Design notes (.md) + diagram chain (docs/diagrams/)
└── diagrams/           .excalidraw sources → .svg → .png

tests/                  pytest suite
└── fixtures/           Small samples (.pdf, .docx, .xlsx) for unit tests

data/                   Real corpus for demos and benchmarks (not unit-tested)

demo.py                 7 interactive demos against tests/fixtures/
```

## Notebooks — conventions

**Filenames:** `NN_<topic>.ipynb` with a two-digit numeric prefix (e.g., `06_understanding_question.ipynb`). The number is a sort key within the parent folder, nothing more — drop any "chapter / article / part" framing in prose. The *chapter* is the parent folder (`01_document_parsing/` … `06_pipeline/`).

**Notebooks-only rule:** `notebooks/` contains **only `.ipynb` files**. No `.py` helpers alongside. If a notebook needs a helper, **inline it as a cell**. Per repo policy (commit `43ad3de` "Suppression des .py dans notebooks/ — notebooks only").

**Section title style** in markdown cells:
- Top-level: `## N. Titre`
- Sub-section: `## N.M Titre`
- **No `§` symbol, no em-dash** between number and title.
- **No double-numbering**: write `## 3. Parsing`, not `## 3. Block 1 — Parsing`. The number conveys order; the prefix is filler.

**Outputs**: each notebook writes to its own subdirectory in `notebooks/_outputs/` (e.g. `_outputs/invoices/`). Outputs are not unit-tested and may be regenerated freely.

**Two notebook shapes** coexist — pick the right one before writing:

1. **Walkthrough** — multi-cell, didactic. Mix of markdown explanations and code cells with intermediate prints. Use this when the notebook teaches the API piece by piece. Examples: [06_understanding_question.ipynb](notebooks/02_question_parsing/06_understanding_question.ipynb), [07_generate_invoice_pdfs.ipynb](notebooks/01_document_parsing/pdf/07_generate_invoice_pdfs.ipynb).
2. **Minimal usage (`_js` suffix)** — **exactly 3 cells**: one markdown intro, one `pip install` cell, one actual call cell with output. Use this when you only want to show *"here is how you call X on a real input, here is what comes out"*. Examples: [05_parse_pdf_js.ipynb](notebooks/01_document_parsing/pdf/05_parse_pdf_js.ipynb), [05_bench_parse_pdf_js.ipynb](notebooks/01_document_parsing/pdf/05_bench_parse_pdf_js.ipynb), [06_question_parsing_js.ipynb](notebooks/02_question_parsing/06_question_parsing_js.ipynb). Pattern enforced by commit `af9e4d1` ("1 markdown + 1 install + 1 cellule appel"). **Do not** add multi-section walkthroughs to a `_js` notebook.

**Imports**: notebooks import from `docpipeline` and `src.question`; they don't redefine helpers. If a helper isn't in the package yet, add it there first.

**Paths**: notebooks reference `tests/fixtures/<subdir>/` for unit-test inputs and `data/<subdir>/` for the real corpus. Outputs always go to `notebooks/_outputs/<subdir>/`.

**Cell hygiene**: `execution_count` not null, cells in order, no stale outputs from an older version of the code.

## Scripts — conventions

A "script" here is a small Python file you run from the command line. Two locations only:

- **Per-content scripts live next to what they generate.** Example: [docs/diagrams/_build_excalidraw.py](docs/diagrams/_build_excalidraw.py) and [docs/diagrams/_export_png.py](docs/diagrams/_export_png.py) live alongside the diagrams they produce, **not** in a top-level `scripts/` folder. The prefix `_` (e.g. `_build_excalidraw.py`) marks a non-public helper.
- **Cross-cutting CLI**: extend the existing `docpipeline` CLI in [src/docpipeline/cli.py](src/docpipeline/cli.py) rather than adding standalone scripts at the repo root.

**Single-use helpers for one notebook** belong inside that notebook as a cell, not as a separate `.py` (the "notebooks-only" rule above).

## Code organization — `src/` package layout

The packages are organized **by topic** (parsing, conversion, retrieval, ...), not chronologically. When a topic grows past 2-3 files, it becomes a **subpackage** (folder with `__init__.py`).

**One method = one file**, named after the method. Examples: [retrieval/sql_backend.py](src/docpipeline/retrieval/sql_backend.py) (FTS5 backend), [conversion/_adobe_converter.py](src/docpipeline/conversion/_adobe_converter.py). Avoid generic-operation file names (`top_k.py`, `helpers.py`, `utils.py`) — they say nothing about what the file actually implements. Helpers used by exactly one method live in that method's file.

**The `__init__.py` is the public surface** — re-export public names so callers do `from docpipeline.retrieval import SQLRetriever`, not `from docpipeline.retrieval.sql_backend import SQLRetriever`.

**Variable naming — describe content, not operation.** Locals and DataFrames are named after what they hold:
- ✅ `parsed_question`, `retrieved_pages_df`, `bboxes_df`, `filtered_line_df`
- ❌ `parsed`, `result_df`, `out`, `tmp`, `df3`, `q2`

Past participles as bare names (`parsed`, `filtered`, `extracted`) name an operation, not a thing — append the noun. Single-letter abbreviations are only OK in tight math loops (`i`, `j`, `n`).

**Python 3.10+ syntax**: `int | None`, `list[Foo]`, no `from typing import Optional, List, Dict`. Type hints on every public function. Pydantic for structured I/O. DataFrames over ORM for cross-layer data exchange.

## Architecture — docpipeline: "4 briques × N formats"

Organized around **4 transverse stages** (parsing → retrieval → question → generation) applied to **N format-specific pipelines** (PDF, Word, Excel, PPTX, email). Each brick has a clear input/output contract and zero hidden coupling.

```
src/docpipeline/
├── __init__.py        Top-level API: convert / parse / classify / summarize
├── cli.py             argparse CLI — mirrors the top-level API
├── parsing/           Per-format extraction → standardized pandas DataFrames
│   ├── pdf/           classifier (3-level heuristic), extractor, tables, parse_pdf, image_store
│   ├── word/          XML-native parser (TOC, spans, tables) + consolidator (Word ⊕ signed PDF)
│   ├── excel/         ingest_excel → SQLite/Parquet
│   ├── pptx/          parse_pptx
│   └── email/         parse_email (.eml)
├── conversion/        PDF → Word: 8 engines + DocxEnhancer (11-step post-clean)
├── retrieval/         Python (keyword/regex/embeddings) and SQL (FTS5) backends
├── generation/        Unified LLM client (OpenAI + Anthropic) + summarizer
├── translation/       Word translator + PDF reconstructor + side-by-side HTML viewer + glossary
└── excel_agent/       Natural-language → SQL agent over an ingested .xlsx
```

### Where the LLM is — and is not

Core design rule: **LLM is reserved for translation, summarization, and the Excel SQL agent.** Everything else (classification, extraction, conversion, retrieval, deduplication, table detection, PDF reconstitution) is heuristics + specialized libraries with **zero LLM**. Don't add LLM calls to parsing/conversion/retrieval bricks.

### PDF → Word conversion: cascade in [conversion/pdf_to_word.py](src/docpipeline/conversion/pdf_to_word.py)

Engine selection is driven by `_select_engine()` and the PDF classifier's category (`word_native` / `design_tool` / `scanned` / `other`). **Adobe has absolute priority when configured** (`ADOBE_CLIENT_ID` + `ADOBE_CLIENT_SECRET`), except for scanned PDFs where local OCR is faster. Fallback for complex layouts: `msword` → `docling` → `libreoffice` → `smart` → (`hybrid` only if `prefer="visual"`). Each fallback appends a user-facing warning telling them what to install for better quality — preserve this pattern when adding engines.

`prefer="editable"` must never resolve to `hybrid` (which produces image + invisible text — visually perfect but not editable). `enhance=True` skips the post-clean for engines that already produce clean DOCX (`adobe`, `msword`, `libreoffice`, `docling`, `hybrid`).

### `parse_pdf` — single-script PDF inspection: [parsing/pdf/parse_pdf.py](src/docpipeline/parsing/pdf/parse_pdf.py)

One client entry point, **one `fitz` open**, four outputs (`line_df`, `image_df`, `page_df`, `doc_summary` dict). Combines source classification by metadata with page-by-page typing (8 `page_type` values × 4 `extraction_strategy` values). All logic is pure functions + dataclasses, intentionally self-contained — don't refactor it into multiple modules.

### Standardized DataFrames

Parsers emit DataFrames with stable columns (`page`, `line`, `bbox`, `style`, `span_id`, ...) so retrieval, translation, and reconstitution can chain without reparsing. The `span_id` is what makes round-trip translation (Word DOCX or PDF reconstruct) work — preserve it when manipulating extraction output.

## Architecture — question layer ([src/question/](src/question/))

Public entry point:

```python
from src.question import understand_question

plan = understand_question(question, *, document_type="pdf", enable=None, ...) -> list[dict]
# always a list (1 entry for simple questions, N for compound questions)
# each entry: {"retrieval": {...}, "generation": {...}, "_meta": {...}}
```

The pipeline ([pipeline.py](src/question/pipeline.py)) is intentionally tiny. All capabilities are entries in two declarative tables:

- **[bricks.py](src/question/bricks.py)** — `BRICKS: dict[str, Brick]` registry. Each `Brick` declares its target (`retrieval` | `generation`), its `run(question, ctx) -> dict | None` extractor, and `compatible_doc_types` (empty = all).
- **[presets.py](src/question/presets.py)** — `PRESETS: dict[doc_type, list[brick_name]]`. Domain knowledge lives here (e.g., `page_hint` is in `PRESETS["pdf"]` but not `PRESETS["word"]` because `.docx` has no stable pages).

**Adding a capability** = (1) write extractor, (2) one line in `BRICKS`, (3) add brick name to relevant presets. Pipeline never changes. The output JSON contains *only fields that were actually populated* — no `null`.

**LLM rule (mirrors the docpipeline rule, applied to the question layer):** LLM stays **inside** individual bricks that need it (`rewrite`, `decompose`, `spell`). Never use an LLM as orchestrator/gating around the bricks. Static `document_type`-driven presets capture ~95% of routing decisions; agentic gating costs latency, determinism, and the LLM bill.

## Docs & diagrams

Design notes live as `NN_<topic>.md` in [docs/](docs/). Diagrams follow a deterministic chain:

```
.excalidraw  ───►  .svg  ───►  .png
   source         vectoriel    pixel (consumed by .md via ![](...))
```

- `.excalidraw` (JSON) — sources, edited via VS Code extension `pomdtr.excalidraw-editor` (visual canvas) or as JSON. Initially generated by [_build_excalidraw.py](docs/diagrams/_build_excalidraw.py) (deterministic seeds, idempotent).
- `.svg` — exported manually from the Excalidraw editor.
- `.png` — re-rendered by [_export_png.py](docs/diagrams/_export_png.py) (resvg-py, 2× scale). `.md` files reference `.png` because it's universally accepted (Medium, GitHub, other CMS).

All three are committed. Full workflow detail in [docs/diagrams/README.md](docs/diagrams/README.md).

## Notebook 07 — synthetic invoice generator

[notebooks/01_document_parsing/pdf/07_generate_invoice_pdfs.ipynb](notebooks/01_document_parsing/pdf/07_generate_invoice_pdfs.ipynb) builds a varied PDF invoice corpus using `reportlab` + `Faker` (en_US locale) and demonstrates a **pure heuristic** for address-block detection (`detect_address_zones`): split the upper third of the page on the midline → leftmost cluster = sender, rightmost = recipient. Stable on ~85% of US B2B invoices.

Key reusables exported by the notebook (copy into `src/` if needed for production):

- `Address`, `LineItem`, `Invoice`, `InvoiceStyle` — data models with structural toggles (logo style, label phrasings, optional fields)
- `random_invoice()` / `random_style()` — Faker en_US generators with deterministic seeds
- `generate_invoice(inv, out_path, style)` — reportlab US-Letter rendering (themes, fonts, banner/box/no logo)
- `detect_address_zones(pdf)` → `(sender_bbox, recipient_bbox)` — geometry-only heuristic, no LLM
- `render_with_bboxes(pdf, png)` — visual validation overlay

Adversarial PDFs in `_outputs/invoices/_adversarial/` deliberately violate the convention (sender on right, no labels) to stress-test future detectors. Reportlab built-in fonts: use the `_BOLD` / `_ITALIC` mappings from the notebook — `Times-Bold` and `Times-Italic`, not `Times-Roman-Bold` (which doesn't exist).

## Testing & data

- Fixtures in [tests/fixtures/](tests/fixtures/) (small `.pdf`/`.docx`/`.xlsx` samples for unit tests). Tests reference these by path; don't move them.
- Real corpus in [data/](data/) — grouped by source. Used by demo notebooks and benchmarks ([notebooks/01_document_parsing/pdf/05_bench_parse_pdf_js.ipynb](notebooks/01_document_parsing/pdf/05_bench_parse_pdf_js.ipynb)). Not unit-tested.
- Each PDF in `data/<subdir>/` may have a companion `data/<subdir>/<doc_stem>.md` describing length, TOC quality, parsing quirks, and what it's good for demonstrating — read it before re-parsing.
- Some tests touch private helpers (`_decide_page_type`, `_normalize`, etc.) in `parse_pdf.py` — keep those names stable.
- Adobe / MSWord / LibreOffice / Docling / Tesseract are all **optional**. Tests must skip cleanly when an engine is unavailable; conversion code already does this — follow the existing `_*_available()` pattern.
- Never use proprietary client documents as test fixtures. Use small synthetic samples (e.g. notebook 07's invoice generator) or openly-licensed public corpora.
