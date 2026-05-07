# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

`docpipeline` — modular document-processing toolkit (PDF/Word/Excel/PPTX/email). Code, comments, and docstrings are in **French**; match that convention when editing existing files.

PEP 621 / src layout: package lives in [src/docpipeline/](src/docpipeline/), build config in [pyproject.toml](pyproject.toml). Python ≥ 3.10.

## Commands

```bash
pip install -e .[dev]              # editable install + pytest/ruff/mypy/build
pip install -e .[all]              # also: openai, anthropic, pytesseract, docling, pywin32

pytest tests/ -v                   # full suite (~73 tests)
pytest tests/test_parse_pdf.py -v  # one file
pytest tests/test_parse_pdf.py::test_name -v   # one test

ruff check src/ tests/             # lint
mypy src/                          # strict typing (configured in pyproject.toml)

python -X utf8 demo.py             # run all 7 interactive demos against tests/fixtures/
python -X utf8 demo.py 1           # single demo (1..7)

docpipeline --help                 # CLI entry point ([src/docpipeline/cli.py](src/docpipeline/cli.py))
```

**Windows console:** stdout/stderr must be reconfigured to UTF-8 — see the boilerplate in [src/docpipeline/cli.py:25-32](src/docpipeline/cli.py#L25-L32) and [demo.py:6-13](demo.py#L6-L13). Always invoke Python with `-X utf8` on Windows when running scripts that print accented French.

## Architecture — "4 briques × N formats"

The codebase is organized around **4 transverse stages** (parsing → retrieval → question → generation) applied to **N format-specific pipelines** (PDF, Word, Excel, PPTX, email). Each brick has a clear input/output contract and zero hidden coupling.

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

A core design rule: **LLM is reserved for translation, summarization, and the Excel SQL agent.** Everything else (classification, extraction, conversion, retrieval, deduplication, table detection, PDF reconstitution) is heuristics + specialized libraries with **zero LLM**. Don't add LLM calls to the parsing/conversion/retrieval bricks.

### PDF → Word conversion: cascade in [conversion/pdf_to_word.py](src/docpipeline/conversion/pdf_to_word.py)

Engine selection is driven by `_select_engine()` and the PDF classifier's category (`word_native` / `design_tool` / `scanned` / `other`). **Adobe has absolute priority when configured** (`ADOBE_CLIENT_ID` + `ADOBE_CLIENT_SECRET` env vars), except for scanned PDFs where local OCR is faster. Fallback order for complex layouts when Adobe is absent: `msword` → `docling` → `libreoffice` → `smart` → (`hybrid` only if `prefer="visual"`). Each fallback appends a user-facing warning telling them what to install for better quality — preserve this pattern when adding engines.

`prefer="editable"` must never resolve to the `hybrid` engine (which produces image + invisible text — visually perfect but not editable). `enhance=True` skips the post-clean for engines that already produce clean DOCX (`adobe`, `msword`, `libreoffice`, `docling`, `hybrid`).

### `parse_pdf` — single-script PDF inspection: [parsing/pdf/parse_pdf.py](src/docpipeline/parsing/pdf/parse_pdf.py)

One client entry point, **one `fitz` open**, four outputs (`line_df`, `image_df`, `page_df`, `doc_summary` dict). Combines TODO-001 (source classification by metadata) with page-by-page typing (8 `page_type` values × 4 `extraction_strategy` values). All logic is pure functions + dataclasses, intentionally self-contained — don't refactor it into multiple modules.

### Standardized DataFrames

Parsers emit DataFrames with stable columns (`page`, `line`, `bbox`, `style`, `span_id`, ...) so retrieval, translation, and reconstitution can chain without reparsing. The `span_id` is what makes round-trip translation (Word DOCX or PDF reconstruct) work — preserve it when manipulating extraction output.

## Testing notes

- Fixtures in [tests/fixtures/](tests/fixtures/) (real `.pdf`/`.docx`/`.xlsx` samples). Tests reference these by path; don't move them.
- Some tests touch private helpers (`_decide_page_type`, `_normalize`, etc.) in `parse_pdf.py` — keep those names stable.
- Adobe / MSWord / LibreOffice / Docling / Tesseract are all **optional**. Tests must skip cleanly when an engine is unavailable; conversion code must already do this — follow the existing `_*_available()` pattern.
