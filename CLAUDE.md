# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

`docpipeline` — modular document-processing toolkit (PDF/Word/Excel/PPTX/email). The repo also contains the **chapter 6 question-understanding layer** ([src/question/](src/question/)), and design articles + diagrams in [docs/](docs/).

Comments and docstrings are in **French**; match that convention when editing existing files. Code identifiers stay English.

PEP 621 / src layout: package lives in [src/docpipeline/](src/docpipeline/), build config in [pyproject.toml](pyproject.toml). Python ≥ 3.10.

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

python docs/diagrams/_build_excalidraw.py   # regenerate .excalidraw sources from script
python docs/diagrams/_export_png.py         # SVG → PNG (2× scale via resvg-py)
```

**Windows console:** stdout/stderr must be reconfigured to UTF-8 — see boilerplate in [src/docpipeline/cli.py:25-32](src/docpipeline/cli.py#L25-L32) and [demo.py:6-13](demo.py#L6-L13). Always invoke Python with `-X utf8` on Windows when scripts print accented French.

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

### Where the LLM is — and is not (docpipeline)

Core design rule: **LLM is reserved for translation, summarization, and the Excel SQL agent.** Everything else (classification, extraction, conversion, retrieval, deduplication, table detection, PDF reconstitution) is heuristics + specialized libraries with **zero LLM**. Don't add LLM calls to parsing/conversion/retrieval bricks.

### PDF → Word conversion: cascade in [conversion/pdf_to_word.py](src/docpipeline/conversion/pdf_to_word.py)

Engine selection is driven by `_select_engine()` and the PDF classifier's category (`word_native` / `design_tool` / `scanned` / `other`). **Adobe has absolute priority when configured** (`ADOBE_CLIENT_ID` + `ADOBE_CLIENT_SECRET`), except for scanned PDFs where local OCR is faster. Fallback for complex layouts: `msword` → `docling` → `libreoffice` → `smart` → (`hybrid` only if `prefer="visual"`). Each fallback appends a user-facing warning telling them what to install for better quality — preserve this pattern when adding engines.

`prefer="editable"` must never resolve to `hybrid` (which produces image + invisible text — visually perfect but not editable). `enhance=True` skips the post-clean for engines that already produce clean DOCX (`adobe`, `msword`, `libreoffice`, `docling`, `hybrid`).

### `parse_pdf` — single-script PDF inspection: [parsing/pdf/parse_pdf.py](src/docpipeline/parsing/pdf/parse_pdf.py)

One client entry point, **one `fitz` open**, four outputs (`line_df`, `image_df`, `page_df`, `doc_summary` dict). Combines TODO-001 (source classification by metadata) with page-by-page typing (8 `page_type` values × 4 `extraction_strategy` values). All logic is pure functions + dataclasses, intentionally self-contained — don't refactor it into multiple modules.

### Standardized DataFrames

Parsers emit DataFrames with stable columns (`page`, `line`, `bbox`, `style`, `span_id`, ...) so retrieval, translation, and reconstitution can chain without reparsing. The `span_id` is what makes round-trip translation (Word DOCX or PDF reconstruct) work — preserve it when manipulating extraction output.

## Architecture — question layer: [src/question/](src/question/)

Implements the design from [docs/06_question_layer.md](docs/06_question_layer.md). Public entry point:

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

Notebook companion: [notebooks/06_understanding_question.ipynb](notebooks/06_understanding_question.ipynb) walks through each brick + the full `understand_question` API.

## Docs & diagrams: [docs/](docs/)

Design articles (chapter format `NN_<topic>.md`) live in [docs/](docs/). Diagrams follow a deterministic chain:

```
.excalidraw  ───►  .svg  ───►  .png
   source         vectoriel    pixel (consumed by article)
```

- `.excalidraw` (JSON) — sources, edited via VS Code extension `pomdtr.excalidraw-editor` (visual canvas) or as JSON. Initially generated by [_build_excalidraw.py](docs/diagrams/_build_excalidraw.py) (deterministic seeds, idempotent).
- `.svg` — exported manually from Excalidraw editor.
- `.png` — re-rendered by [_export_png.py](docs/diagrams/_export_png.py) (resvg-py, 2× scale). Articles reference `.png` because it's universally accepted (Medium, GitHub, other CMS).

All three are committed. Workflow detail in [docs/diagrams/README.md](docs/diagrams/README.md).

## Notebooks convention

- Filenames prefixed by chapter number: `NN_<topic>.ipynb` (e.g., `06_understanding_question.ipynb`).
- Markdown section titles: `## N. Titre` for top-level, `## N.M Titre` for sub-sections. **No `§` symbol, no em-dash** between number and title.

## Testing & data

- Fixtures in [tests/fixtures/](tests/fixtures/) (small `.pdf`/`.docx`/`.xlsx` samples for unit tests). Tests reference these by path; don't move them.
- Real corpus in [data/](data/) — insurance contracts, SFCR reports, finance docs, the *Attention Is All You Need* paper, etc. Used by demo notebooks and benchmarks ([notebooks/bench_parse_pdf_js.ipynb](notebooks/bench_parse_pdf_js.ipynb)). Not unit-tested.
- Some tests touch private helpers (`_decide_page_type`, `_normalize`, etc.) in `parse_pdf.py` — keep those names stable.
- Adobe / MSWord / LibreOffice / Docling / Tesseract are all **optional**. Tests must skip cleanly when an engine is unavailable; conversion code already does this — follow the existing `_*_available()` pattern.
