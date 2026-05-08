# Document translation — implementation spec (PDF and Word)

This is the practical task list for the translation feature, covering both Word (`.docx`) and PDF. The architecture is in [CLAUDE_tome2.md](CLAUDE_tome2.md); read it once, then use this file day to day.

## Goal

```python
translate_document("contract.docx", target_language="en")
# → writes contract.en.docx
translate_document("contract.pdf", target_language="en")
# → writes contract.en.pdf
```

In both cases the result keeps:
- the same sections, paragraphs, tables, headers/footers, footnotes
- the same formatting (fonts, sizes, colors, bold/italic)
- the same numbering (lists not destroyed)
- glossary terms enforced
- track changes / annotations stripped by default

The user calls `translate_document(...)`. They never call `translate_word(...)` or `translate_pdf(...)` directly. Format dispatch is internal.

## 0. Granularity — RAG uses lines, translation uses spans

This is the key thing to understand before writing any translation code.

The current Tome 1 codebase is built for **RAG** (retrieve pages, cite lines, generate JSON answers). At that level, `line_df` (one row per text line) is the right granularity — what matters is the *content* of the line, not its typography. The PDF parser already produces `line_df`; that's enough for Q&A.

Translation has a different contract. The output document must *look* like the source: same fonts, same bold/italic, same colors, same colored words inside an otherwise plain sentence. That requires a **finer granularity than line**: one row per typographic *span* (smallest unit of consistent styling). A line like `"This is **bold** and this is italic"` is 1 line but 4 spans: plain / bold / plain / italic.

| format | RAG granularity (Tome 1, done) | Translation granularity (Tome 2, your work) |
|---|---|---|
| PDF | `line_df` ✅ | `span_df` — placeholder today, to build |
| Word | `line_df` (to build) | `runs_df` — Word's equivalent of spans |

What this means concretely:

- **PDF.** `parse_pdf` already returns `span_df: pd.DataFrame()` as an empty placeholder ([src/docintel/parsing/pdf/parse_pdf.py](src/docintel/parsing/pdf/parse_pdf.py)). Implementing it is one of your first tasks. PyMuPDF's `page.get_text("dict")` already exposes spans inside each line, with `text`, `font`, `size`, `color`, `flags`, `bbox`. You aggregate, you don't extract from raw glyphs.
- **Word.** A "span" is called a "run" in Word's vocabulary (`<w:r>` element). `runs_df` plays the same role as `span_df`.

The two granularities coexist. RAG keeps using `line_df`; translation uses `span_df` / `runs_df`. Both come out of the same `parse_*` call.

## 1. Pipeline — how translation maps onto the four bricks

**Strict rule: follow the same four-brick pipeline as Tome 1.** Don't invent a parallel architecture for translation. Each brick has work to do, even if some bricks are lighter than others compared to RAG. The bricks were designed around RAG, but the structure holds for translation too — it just shifts where the heavy lifting sits.

In order: **parsing → question → retrieval → generation → rendering**.

### 1.1 Parsing — finer granularity than RAG

Covered in §0 above. Translation needs `span_df` (PDF) and `runs_df` (Word) on top of the existing `line_df`. This is **substantial work** — the bulk of the format-specific complexity sits here.

### 1.2 Question — minimal but not nothing

For pure RAG, question parsing is heavy (intent + keywords + decomposition + expected answer shape). For translation, the user's message is mostly "translate this". So the brick is light, but not empty. The user can specify:

- **Target language** (mandatory).
- **Scope** — "translate only pages 3 to 15", "translate everything except the annexes", "skip the cover page".
- **Translation style** — formal vs casual, technical vs marketing. Optional, slightly speculative, but worth supporting.
- **Glossary additions** — "use these extra term mappings" on top of the standard glossary.

Output is a `TranslationRequest` Pydantic schema, parsed from the user message by an LLM call (same pattern as `parse_question` in Tome 1):

```python
class TranslationRequest(BaseModel):
    target_language: str                          # "en", "fr", "de", ...
    source_language: str | None = None            # None = auto-detect
    scope: TranslationScope | None = None         # which pages/sections; None = full doc
    style: Literal["formal", "casual", "technical", "default"] = "default"
    glossary_additions: list[GlossaryEntry] = []  # ad-hoc terms from the user message

class TranslationScope(BaseModel):
    page_range: tuple[int, int] | None = None     # inclusive, 1-based
    include_sections: list[str] | None = None     # by section title or breadcrumb
    exclude_sections: list[str] | None = None     # e.g. ["Annexes", "Glossary"]
```

**Files:**
- `src/docintel/question/intent.py` — intent classifier (qa | translation | summarization | comparison)
- `src/docintel/generation/translation/request.py` — `TranslationRequest`, `TranslationScope` schemas
- `src/docintel/generation/translation/parse_request.py` — `parse_translation_request(message: str) -> TranslationRequest`

### 1.3 Retrieval — scope filtering and image text extraction

Two roles:

**Scope filtering.** When `TranslationScope` is set, filter `line_df` and `span_df` to the requested pages or sections before sending anything to the LLM. Reuse existing retrieval helpers (`retrieve_pages`, `retrieve_sections` from Tome 1) to land the scope. Output: a sub-DataFrame to translate, plus a "skip" mask for everything else (the rendering step will keep the source text untouched for those rows).

**Image text extraction (OCR).** Documents have images with embedded text — diagrams, screenshots, scanned tables, signed stamps. To translate the document end-to-end, **the text inside images has to come out as another text source**, get translated, and be re-rendered onto the image. This is its own pipeline arm:

```
parsed image bytes
    → OCR (Tesseract / Azure Vision / GPT-4V) → image_text_df
    → translate_chunks (same as text)
    → render translated text on the image (PIL / PyMuPDF rectangle overlays)
    → swap the image back into the source document
```

**Files:**
- `src/docintel/retrieval/translation_scope.py` — `apply_translation_scope(line_df, span_df, scope) -> (selected, skipped)`
- `src/docintel/parsing/{pdf,docx}/image_text.py` — extract image bytes + OCR them into `image_text_df`
- `src/docintel/rendering/{pdf,docx}/images.py` — re-render an image with translated text overlay

Image translation is **scope-flagged**: ship text translation first (steps 1–6 of the build order), add images as a follow-up phase. Document the API now so the dispatch is in place; defer the heavy lifting.

### 1.4 Generation — the prompt, the heavy lift

Where most of the translation work happens.

- **The system prompt** — translation rules, glossary inlined, span-marker conventions for styled translation, format-specific instructions (don't translate field codes, etc.).
- **Paragraph-level batching** — group spans/runs into visual paragraphs, translate as one chunk per paragraph (never span-by-span), redistribute back. Same algorithm for both formats — lives once in `generation/translation/distribute.py`.
- **Glossary injection** — load the glossary YAML, render the `GLOSSARY:` block, inline into the system prompt. Add `glossary_additions` from the parsed request on top of the standard glossary.
- **Caching** — cache by `(chunk_text_hash, target_language, glossary_hash, style)` so re-runs don't pay twice.

**Files:** `src/docintel/generation/translation/` — `translate_chunks.py`, `distribute.py`, `glossary.py`, `prompts.py`, `cache.py`.

### 1.5 Rendering — rebuild at the end

New module for Tome 2 (Tome 1 only had PDF annotation, which becomes part of `rendering/pdf/`). The rendering step runs **after everything is translated**: text spans/runs, image text, scoped vs skipped rows. It walks the source document as a template and writes a new copy with replacements applied in place.

**Files:** `src/docintel/rendering/pdf/` and `src/docintel/rendering/word/` (covered in detail in the build order below).

---

The whole pipeline as a one-liner:

```
parse(doc)                     # → line_df + span_df/runs_df + image_df
  → parse_translation_request  # → TranslationRequest
  → apply_scope                # → selected_df + skipped_df
  → translate_chunks(text)     # → translated_df
  → translate_chunks(images)   # → translated image_text_df    (later phase)
  → build_translated_doc       # → output_path
```

## 2. Build order

Build in this order. Each step has a clear deliverable and a smoke test that takes minutes, not hours. Don't move to step N+1 until N's smoke test is green.

Steps 1–8 below describe the **Word path** end to end (it's the active work). Section §3 "PDF translation — what changes" lists the deltas for PDF: which files exist already, which new files to add, and the PDF-specific gotchas. Image translation is step 9, deferred to a later phase.

Step ↔ brick mapping:

| step | brick | what |
|---|---|---|
| 1 | parsing | `parse_docx` baseline (line_df + runs_df) |
| 2 | rendering | round-trip Word build (no translation yet) |
| 3 | question | `TranslationRequest` schema + `parse_translation_request` |
| 4 | retrieval | `apply_translation_scope` (page / section filtering) |
| 5 | generation | `translate_chunks` |
| 6 | generation | `distribute_to_runs` (paragraph translate-then-redistribute) |
| 7 | generation | glossary loading + prompt inlining |
| 8 | pipeline | `translate_document` public entry point |
| 9 | retrieval + rendering | image text extraction + translated image overlay (later phase) |

### Step 1 — parse_docx baseline

**File:** `src/docintel/parsing/docx/parse_docx.py` (plus `line_df.py`, `runs_df.py`, `sections.py`, `tables.py`).

**Goal:** `.docx` in, dict of DataFrames out. No translation yet.

```python
def parse_docx(path: str | Path) -> dict:
    """One Word document in, a dict of relational tables out."""
    return {
        "line_df": ...,         # one row per paragraph / table cell / header / footer / footnote
        "section_df": ...,      # one row per logical section
        "runs_df": ...,         # one row per styled run
        "table_df": ...,        # one row per table cell
        "parsing_summary": ...,
    }
```

**`line_df` schema** (cross-format contract):

| column | type | meaning |
|---|---|---|
| `doc_id` | str | document hash or filename stem |
| `section_id` | int | sections are 0-indexed within the doc |
| `line_num` | int | line index within the section |
| `text` | str | the line's text (numbering stripped) |
| `line_kind` | str | `paragraph` / `table_cell` / `header` / `footer` / `footnote` |
| `ref_id` | str | python-docx element id; used to map back when rendering |
| `char_count` | int | `len(text)` |

**`runs_df` schema** (Word-specific):

| column | type | meaning |
|---|---|---|
| `doc_id`, `section_id`, `line_num` | | foreign key into `line_df` |
| `run_idx` | int | run order within the line, 0-based |
| `text` | str | text of this run |
| `font_name`, `font_size`, `bold`, `italic`, `underline`, `color` | | styling |
| `run_id` | str | python-docx run id, for round-trip mapping |

**Smoke test:** `parse_docx(tests/fixtures/docx/minimal.docx)` — assert `n_lines` equals what you counted by hand in Word.

### Step 2 — render Word from parsed data (round-trip)

**File:** `src/docintel/rendering/word/build_document.py`.

**Goal:** take a (possibly modified) `line_df` + `runs_df` + the source path, write a new `.docx`.

The trick: **don't build the document from scratch**. Open the source as a template, walk its paragraph tree in order, replace `.text` in each run.

```python
def build_word_document(
    translated_line_df: pd.DataFrame,
    translated_runs_df: pd.DataFrame,
    source_path: str | Path,
    output_path: str | Path,
) -> Path:
    """Re-emit source.docx with replaced text.

    Opens source_path as a python-docx Document, walks paragraphs in order,
    looks up translated runs by ref_id + run_id, replaces run.text. Saves to
    output_path. Returns output_path.
    """
```

**Smoke test:** identity round-trip — `parse_docx(source) → build_word_document(line_df, runs_df, source, out)` — open `out.docx` and `source.docx` in Word, compare visually. Should be indistinguishable. XML diff: empty or only whitespace.

### Step 3 — TranslationRequest (question brick)

**Files:** `src/docintel/generation/translation/request.py`, `src/docintel/generation/translation/parse_request.py`.

**Goal:** turn the user message into a structured `TranslationRequest`.

```python
class TranslationRequest(BaseModel):
    target_language: str
    source_language: str | None = None
    scope: TranslationScope | None = None
    style: Literal["formal", "casual", "technical", "default"] = "default"
    glossary_additions: list[GlossaryEntry] = []

class TranslationScope(BaseModel):
    page_range: tuple[int, int] | None = None      # inclusive, 1-based
    include_sections: list[str] | None = None
    exclude_sections: list[str] | None = None      # e.g. ["Annexes"]

def parse_translation_request(message: str, client: OpenAI | None = None) -> TranslationRequest:
    """LLM-driven parsing of the user message into a TranslationRequest."""
```

The system prompt is intentionally narrow — translation requests are simple, the schema is constraining, the LLM's job is to fill the slots, not interpret intent broadly.

**Smoke test:** parse `"Translate this contract into formal English, skip the annexes, and use 'deductible' for 'franchise'."` and assert `target_language == "en"`, `style == "formal"`, `scope.exclude_sections == ["Annexes"]`, `glossary_additions[0] == ("franchise", "deductible")`.

### Step 4 — apply_translation_scope (retrieval brick)

**File:** `src/docintel/retrieval/translation_scope.py`.

**Goal:** filter `line_df` and `runs_df` to the rows the user wants translated; keep the rest as a "skipped" view that the rendering step writes back untouched.

```python
def apply_translation_scope(
    line_df: pd.DataFrame,
    runs_df: pd.DataFrame,
    scope: TranslationScope | None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Returns (selected_line_df, selected_runs_df, skipped_line_df, skipped_runs_df).

    When scope is None, selected = full; skipped = empty.
    """
```

Section matching uses the breadcrumb (or normalized title) — case-insensitive, accent-insensitive. Page ranges are inclusive on both ends.

**Smoke test:** with `scope=TranslationScope(exclude_sections=["Annexes"])` on a fixture that has an "Annexes" section, assert no row in the Annexes section appears in `selected_line_df`, and that the Annexes rows appear verbatim in `skipped_line_df`.

### Step 5 — translate_chunks (generation brick)

**File:** `src/docintel/generation/translation/translate_chunks.py`.

**Goal:** `line_df` in, translated `line_df` out. Same row count, same keys, only `text` changes.

```python
def translate_chunks(
    line_df: pd.DataFrame,
    target_language: str,
    glossary: Glossary | None = None,
    style: str = "default",
    client: OpenAI | None = None,
    chunk_size: int = 8000,         # chars per LLM call
    system_prompt: str | None = None,
) -> pd.DataFrame:
    """Translate every text line in line_df."""
```

**Chunking rule:** group consecutive lines into chunks of ≤ `chunk_size` characters, never crossing a `section_id` boundary. Each chunk is one LLM call with structured output asking for a JSON list of strings, in the same order, same length as the input batch.

**System prompt skeleton** (lives in `generation/translation/prompts.py`):

```
You translate text from {source_lang} to {target_lang}.
Rules:
- Translate every input line. Do not skip, merge, or split lines.
- Output a JSON list of strings, same length as input, same order.
- Preserve placeholders like {{NAME}}, [REF], <FIELD> verbatim.
- Apply the glossary below — these mappings are mandatory.

GLOSSARY:
{glossary_block}
```

**Smoke test:** `translate_chunks(line_df, "en")` — assert `len(out) == len(line_df)`, assert all texts differ from source, assert no row has empty text where source was non-empty.

### Step 6 — run distribution (the hard part)

**Files:** `src/docintel/generation/translation/distribute.py` (the algorithm) and `src/docintel/rendering/word/runs.py` (the Word-side wiring). The PDF spans path will reuse the same `distribute.py`.

A paragraph in the source has 3 styled runs (bold word, plain phrase, italic word). Its translation is one fluid sentence in another language. There's no clean 3-way split.

The pattern:

1. Translate the **whole paragraph as one chunk**. NOT run-by-run; that destroys grammar.
2. Distribute the translated text across the source runs **proportionally to source-run character counts**.
3. **Better strategy when you have time:** ask the LLM to return the translation with span markers (`<b>...</b>`, `<i>...</i>`, ...) at the styled spans. Use the markers to land styling. Fall back to proportional when the LLM omits markers.

```python
def distribute_to_runs(
    translated_text: str,
    source_runs: list[dict],   # each {"text": ..., "char_count": ...}
) -> list[str]:
    """Split translated_text into len(source_runs) pieces.

    Strategy: proportional by character count, snapped to nearest word boundary.
    Empty source runs (zero-length style anchors) get empty translations.
    """
```

**Smoke test:** a paragraph with three runs (bold "Important", plain ":", italic "do not skip"). Translate to French. Output: bold "Important", plain ":", italic "ne pas ignorer". Eye-check that the bold/italic markers landed on visually equivalent words, even if not perfectly aligned.

### Step 7 — glossary

**File:** `src/docintel/generation/translation/glossary.py`. Glossary files live under `data/glossaries/<name>.yaml`.

```yaml
# data/glossaries/insurance_fr_en.yaml
name: insurance_fr_en
source_lang: fr
target_lang: en
entries:
  - source: franchise
    target: deductible
    note: insurance contracts only — not the trademark sense
  - source: sinistre
    target: claim
  - source: police
    target: policy
    note: insurance — not law enforcement
```

```python
class GlossaryEntry(BaseModel):
    source: str
    target: str
    note: str | None = None

class Glossary(BaseModel):
    name: str
    source_lang: str
    target_lang: str
    entries: list[GlossaryEntry]

def load_glossary(name: str) -> Glossary: ...
def render_glossary_for_prompt(glossary: Glossary) -> str:
    """Returns the GLOSSARY block to inline in the system prompt."""
```

The glossary is **inlined in the system prompt**, not retrieved per chunk. Glossaries are short (50–500 entries) and the LLM enforces them best when they sit in the system prompt above the chunk.

This is **not** the Article 6 expert dictionary (`question/expert_dictionary.py`). That one is mono-lingual and feeds retrieval. The translation glossary is paired-language and feeds output enforcement.

### Step 8 — public entry point

**File:** `src/docintel/pipeline/translate_document.py`.

```python
def translate_document(
    document_path: str | Path,
    user_message: str | None = None,        # full free-text request, parsed into TranslationRequest
    target_language: str | None = None,     # short-hand when no user_message; one of these is required
    output_path: str | Path | None = None,
    glossary_name: str | None = None,
    preserve_track_changes: bool = False,
    client: OpenAI | None = None,
) -> Path:
    """Translate any supported document. Dispatches by extension.

    .docx → parsing.docx → generation.translation → rendering.word
    .pdf  → parsing.pdf  → generation.translation → rendering.pdf
    .xlsx → parsing.xlsx → generation.translation → rendering.xlsx
    .pptx → parsing.pptx → generation.translation → rendering.pptx
    """
```

Internally:

```
parse(doc)
  → parse_translation_request(user_message) or TranslationRequest(target_language=...)
  → apply_translation_scope(line_df, runs_df_or_span_df, request.scope)
  → translate_chunks(selected, request.target_language, glossary, request.style)
  → distribute back across runs/spans
  → build_translated_doc(translated, skipped, source_path, output_path)
```

When `output_path` is None, default to `<stem>.<lang>.<ext>` next to the source (`contract.docx` → `contract.en.docx`).

**Smoke test:** `translate_document("sample.docx", target_language="en")`. Open the result in Word. The text is in English, formatting matches, lists are still numbered, the file opens without "this file is corrupted" warnings.

### Step 9 — image text extraction and overlay (later phase)

**Defer until steps 1–8 are green.** Image translation is its own arm of the pipeline and adds OCR + image rendering complexity on top of text translation.

**Files:**
- `src/docintel/parsing/{pdf,docx}/image_text.py` — extract image bytes from the document, OCR them into `image_text_df` (one row per text region inside an image, with bbox + image_id).
- `src/docintel/rendering/{pdf,docx}/images.py` — overlay translated text on the source image using PIL or PyMuPDF rectangle overlays, then swap the image back into the document.

**Image OCR backend** — start with the same OpenAI-compatible LLM client used elsewhere (vision-capable model). Fall back to Tesseract for batch mode if cost/latency matters. Don't ship a Tesseract dependency in the first phase.

**`image_text_df` schema:**

| column | type | meaning |
|---|---|---|
| `doc_id`, `image_id` | | foreign key into the existing `image_df` |
| `region_idx` | int | order within the image |
| `text` | str | OCR'd text |
| `x0`, `y0`, `x1`, `y1` | float | bbox in image-local pixel coordinates |
| `font_size_estimate` | float | for re-rendering |
| `confidence` | float | OCR confidence, 0–1 |

The same `translate_chunks` from step 5 handles `image_text_df` rows — they're text lines like any other. Output gets re-rendered by `rendering/{pdf,docx}/images.py`, which produces a new image with the translated text drawn over (or replacing) the source regions, then the document's image stream is updated.

**Smoke test:** a simple PNG with the word "Bonjour" on a plain background. OCR produces one region with text "Bonjour". Translate to English. Overlay produces a PNG with "Hello" in roughly the same position, font, color.

## 3. PDF translation — what changes

PDF translation reuses steps 3 (`TranslationRequest`), 4 (`apply_translation_scope`), 5 (`translate_chunks`), 6 (`distribute`), 7 (glossary), 8 (`translate_document` dispatch) unchanged. The format-specific work is steps 1, 2, and 9 — parsing, rendering, and (later) image overlays. PDF is **harder than Word** because PDF has no editable text model; you can't just "replace a run". You delete a region and rewrite it.

### PDF-1. Build `span_df`

**File:** `src/docintel/parsing/pdf/span_df.py`. Wire it into `parse_pdf.py` (replace the empty placeholder).

**Goal:** one row per typographic span inside `line_df`'s lines.

```python
def build_span_df(doc: fitz.Document) -> pd.DataFrame:
    """One row per typographic span across the document."""
```

**Schema:**

| column | type | meaning |
|---|---|---|
| `page_num`, `line_num` | int | foreign key into `line_df` |
| `span_idx` | int | span order within the line |
| `text` | str | span text |
| `font_name` | str | PyMuPDF span `"font"` |
| `font_size` | float | PyMuPDF span `"size"` |
| `color` | int | PyMuPDF span `"color"` (24-bit RGB packed) |
| `flags` | int | PyMuPDF span `"flags"` (bold = 16, italic = 2, ...) |
| `x0`, `y0`, `x1`, `y1` | float | span bbox |
| `origin_x`, `origin_y` | float | span baseline origin (for re-insertion) |
| `is_bold`, `is_italic` | bool | derived from `flags` |

PyMuPDF gives you all of this directly: `page.get_text("dict")["blocks"][i]["lines"][j]["spans"][k]` already contains every field. You're walking the dict and flattening.

**Smoke test:** `parse_pdf(tests/fixtures/pdf/styled_paragraph.pdf)` — assert `span_df` is non-empty, assert at least one row has `is_bold == True`, assert `n_spans >= n_lines` (every line has at least one span).

### PDF-2. Render translated PDF

**File:** `src/docintel/rendering/pdf/build_translated_pdf.py`.

**Goal:** take a translated `span_df` + the source PDF path, write a translated PDF.

PDF has no `run.text = "new"` API. The pattern with PyMuPDF:

1. **Open the source as the canvas.** Don't build from scratch — keep images, vector graphics, page geometry intact.
2. **For each translated span:** `page.add_redact_annot(span_bbox, fill=(1, 1, 1))` to mark the source text for removal. Run `page.apply_redactions()` once per page (not per span). The original glyphs are gone.
3. **Re-insert the translated text** at the same position, same font, same size, same color: `page.insert_textbox(span_bbox, translated_text, fontname=mapped_font, fontsize=span.font_size, color=rgb_from_int(span.color), align=...)`. Use `insert_textbox` (not `insert_text`) so the text wraps inside the original bbox if the translation is longer.
4. **Save** the modified document.

```python
def build_translated_pdf(
    translated_span_df: pd.DataFrame,
    source_path: str | Path,
    output_path: str | Path,
) -> Path:
    """Re-emit the source PDF with translated spans."""
```

**Smoke test:** identity round-trip — translate every span to itself (no LLM), assert visual equivalence with the source. Only round-tripping reveals font-mapping bugs, redaction artefacts, and bbox drift.

### PDF-3. Span distribution (the hard part for PDF)

Same problem as Word run distribution, harder edge cases. A single visible "paragraph" in a PDF is often **many spans across many lines**, because PDF emits text in glyph batches with column wraps:

```
[span1: "This is "] [span2: "bold"] [span3: " text and"]   ← line 5
[span4: " here is "] [span5: "italic"] [span6: " text."]   ← line 6
```

Translation must:

1. **Group spans into visual paragraphs.** Use `line_df` paragraph grouping (whatever parse_pdf already gives you) plus span continuity (same font / size on the same `y` coordinate ± tolerance).
2. **Translate the assembled paragraph as one chunk.**
3. **Redistribute** the translated text across the source spans, proportional to source-span character count, snapped to word boundaries. Same algorithm as `distribute_to_runs` for Word.

**File:** `src/docintel/rendering/pdf/spans.py`. The shared distribution algorithm should live in `generation/translation/distribute.py` and be called from both `rendering/word/runs.py` and `rendering/pdf/spans.py`. Don't duplicate it.

### PDF-4. Public API — same entry point

`translate_document` already exists from step 6. Wire the PDF dispatch:

```python
def translate_document(document_path, target_language, ...):
    ext = Path(document_path).suffix.lower()
    if ext == ".pdf":
        return _translate_pdf(...)
    if ext == ".docx":
        return _translate_docx(...)
    raise UnsupportedFormatError(ext)
```

**Smoke test:** `translate_document("sample.pdf", "en")`. Open the result in any PDF viewer. The text is in English, the page layout matches, fonts look right, no overlapping glyphs.

## PDF format gotchas

These are different from Word's gotchas. Read once.

1. **Embedded fonts are often subset.** A French PDF may embed only the glyphs it actually uses (e.g. `é, à, ç`). Translating to German may need glyphs the embedded font doesn't have (`ß, ü`). Detect missing-glyph cases (PyMuPDF returns 0 width for unknown glyphs) and fall back to a TTF you ship with the package (e.g. Noto Sans).

2. **Spans are in PDF object order, not visual order.** Two-column layouts (the Attention paper, NIST CSF) interleave spans in surprising ways. Always sort by `(page, y, x)` before grouping into paragraphs.

3. **Rotated text.** Pages can have spans with non-zero rotation (sideways tables). PyMuPDF gives the bbox; use `page.insert_textbox(rect, text, rotate=90)` when re-inserting.

4. **Vertical text (CJK).** Same flag, different rotation. Out of scope for the first pass — log and skip.

5. **Forms, annotations, comments.** Separate streams. `page.widgets()` for form fields, `page.annots()` for annotations. Strip annotations by default. Don't translate form field labels — they have a separate `field_label` API.

6. **Scanned PDFs.** `span_df` will be empty — there's no text layer, only images. Detect this case (`n_spans == 0` despite `n_pages > 0`) and raise `ScannedPdfError`. OCR is a follow-up, out of scope for this work.

7. **Hyperlinks.** PyMuPDF: `page.get_links()`. Translate the visible text that overlaps the link rect; keep the URL.

8. **Justified text.** Spaces in justified PDF text are wider than normal. The character count changes when you re-insert with `insert_textbox(align=fitz.TEXT_ALIGN_JUSTIFY)`. Set the same alignment as the source paragraph.

9. **Line spacing.** Source PDFs use specific leading; default `insert_textbox` leading often differs. Pass `lineheight=...` derived from the source line spacing (`y` deltas in `line_df`).

10. **Color.** PyMuPDF's `color` field is a packed int (`0xRRGGBB`); `insert_textbox` wants a tuple `(r, g, b)` with 0..1 floats. Helper:

    ```python
    def rgb_from_int(c: int) -> tuple[float, float, float]:
        return ((c >> 16) & 0xFF) / 255, ((c >> 8) & 0xFF) / 255, (c & 0xFF) / 255
    ```

11. **TOC and bookmarks.** `doc.get_toc()` returns the bookmark tree. Translate the titles, write back with `doc.set_toc(...)`. Don't drop bookmarks silently.

12. **Page headers / footers** are spans like any other. They get translated by default. If you want to skip them (e.g. proprietary client name), filter `span_df` by `y < header_threshold` or `y > footer_threshold` before sending to the LLM.

## Word format gotchas

These are real and bit other people. Read once, keep them in mind.

1. **A paragraph with 0 runs can have text.** Body text sits inside `<w:p>` directly. Rare but exists. Treat as a single implicit run.

2. **Empty paragraphs are real.** They create vertical space. Don't skip them in `line_df` or the rendering will collapse layout. Keep them with `line_kind="paragraph"` and empty text.

3. **Numbered list numbers are NOT in the text.** They come from a `<w:numPr>` reference in the paragraph properties. Word renders the number at display time. `paragraph.text` may or may not include it depending on the python-docx version. Strip them: walk runs explicitly, never use `paragraph.text` for the line text.

4. **Footnotes and endnotes are separate streams.** `document.part.footnotes_part`. Treat them as their own sections (`section_id`s after the body sections). Their `line_kind` is `footnote`.

5. **Comments are also separate.** Default behavior: strip them. If `preserve_comments=True` (future flag), translate them as their own stream.

6. **Track changes / revisions** (`<w:ins>` / `<w:del>`). Default: accept all revisions before parsing. Otherwise the translation lands in the pre-revision text and the cleaned document still shows old language in the diff.

7. **Fields** (`<w:fldSimple>`, `<w:instrText>`). `PAGE`, `DATE`, `REF`, `TOC`, `HYPERLINK` etc. are dynamic. Skip them — never send to the LLM. Their visible value gets recomputed by Word.

8. **Hyperlinks** wrap runs (`<w:hyperlink>`). Translate the **visible text** but keep the URL untouched.

9. **Headers / footers** are different XML parts (`header1.xml`, `header2.xml`, ...) per section. Each is its own parse target. Multiple headers per document is normal (first-page header, even-page header, default header).

10. **Tables can be nested.** Walk recursively. The first version that crashes on nested tables will fail on a customer document within a week.

11. **Section breaks change page format** (margins, orientation). Don't merge across section breaks.

12. **`paragraph.text` joins runs without spaces.** If two runs are `"Hello"` and `"world"`, `paragraph.text == "Helloworld"`. Source text reconstruction must use the run iteration explicitly.

## Test fixtures

Put fixtures under `tests/fixtures/<format>/`. Each fixture is small (≤ 1–2 pages), publicly shareable (no real client documents — same rule as Tome 1).

**Word fixtures** (`tests/fixtures/docx/`):

| fixture | what it exercises |
|---|---|
| `minimal.docx` | 3 plain paragraphs |
| `styled.docx` | bold + italic + colored runs in one paragraph |
| `numbered.docx` | numbered list, 5 items |
| `table.docx` | 2×3 table, header row bold |
| `nested.docx` | table inside table |
| `track_changes.docx` | revision marks (insert + delete) |
| `footnotes.docx` | body + 2 footnotes |
| `header_footer.docx` | document with header and footer |
| `hyperlink.docx` | one paragraph with two hyperlinks |
| `mixed.docx` | combines all of the above on 1–2 pages |

**PDF fixtures** (`tests/fixtures/pdf/`):

| fixture | what it exercises |
|---|---|
| `minimal.pdf` | 3 plain paragraphs, single column |
| `styled_paragraph.pdf` | one paragraph with bold + italic + colored spans |
| `two_column.pdf` | two-column layout (object order ≠ visual order) |
| `rotated.pdf` | one page with sideways text |
| `table.pdf` | one tabular page |
| `forms_annotations.pdf` | form fields + annotations |
| `hyperlinks.pdf` | text with two hyperlinks |
| `bookmarks.pdf` | document with a TOC / outline |
| `subset_font.pdf` | embedded subset font that lacks German `ß` (used to test fallback) |
| `scanned.pdf` | image-only page (used to test `ScannedPdfError`) |

Each fixture has a sibling `<name>.expected.json` describing **shape** assertions (`n_sections`, `n_lines`, `n_runs` or `n_spans`, `n_tables`, `has_track_changes`, ...). Tests assert the shape, not the exact text — text changes with parser tweaks; shape is the contract.

## Test plan

`tests/parsing/test_docx.py`:
- `test_minimal_round_trip` — parse + build = visually identical
- `test_styled_runs_preserved` — n_runs in `line_df` matches the source
- `test_numbered_list_strips_numbers` — line text does NOT contain `"1. "`
- `test_table_cells_in_line_df` — every cell is one row with `line_kind="table_cell"`
- `test_track_changes_accepted_by_default`
- `test_footnotes_in_separate_section`
- `test_empty_paragraphs_kept`
- `test_hyperlink_text_extracted_url_kept`

`tests/rendering/test_word.py`:
- `test_round_trip_no_change` — XML diff is empty (or only whitespace) after parse → build
- `test_modified_text_preserves_styling` — replace one word in a styled run; the run's bold/italic/color survive
- `test_proportional_distribution` — split a translated paragraph back into 3 runs, check proportional alignment

`tests/parsing/test_pdf_spans.py`:
- `test_span_df_non_empty` — every text PDF has spans
- `test_span_count_geq_line_count` — `n_spans >= n_lines`
- `test_styled_spans_flagged` — at least one span has `is_bold == True` in `styled_paragraph.pdf`
- `test_two_column_visual_order` — spans sorted by `(page, y, x)` reconstruct the visual reading order
- `test_scanned_pdf_raises` — `scanned.pdf` raises `ScannedPdfError`

`tests/rendering/test_pdf.py`:
- `test_round_trip_no_change` — translate every span to itself; output PDF visually equivalent to source
- `test_font_fallback_on_missing_glyph` — translating a French-subset PDF to German triggers the TTF fallback, no missing-glyph artefacts
- `test_two_column_layout_preserved` — translated two-column PDF still has two columns

`tests/generation/test_translation.py`:
- `test_translate_chunks_preserves_row_count` — `len(out) == len(input)`
- `test_glossary_terms_enforced` — inject glossary `franchise → deductible`, translate a paragraph using `franchise`, assert `deductible` appears
- `test_chunking_respects_section_boundaries` — chunks never cross `section_id`

`tests/pipeline/test_translate_document.py`:
- `test_e2e_minimal_docx_to_en` — full pipeline on `minimal.docx`, output opens in Word, text is in English
- `test_e2e_minimal_pdf_to_en` — full pipeline on `minimal.pdf`, output opens in any PDF viewer, text is in English

The end-to-end tests call a real LLM. Mark them as `@pytest.mark.slow` and skip in CI by default.

## Resolved decisions (don't re-litigate)

- **Batch, not streaming.** One LLM call per chunk. Retries are simpler.
- **Sync, not async.** If speed matters later, parallelize at the chunk level, not the line level.
- **Translation backend: the `docintel.core` LLM client.** Same OpenAI-compatible interface used everywhere else in the codebase. Swap-in for DeepL or Azure Translator is a follow-up, gated by a customer requirement, not built upfront.
- **Cache by `(chunk_text_hash, target_lang, glossary_name)`** in `output/cache/translation/` so re-runs don't pay twice. Disk cache, not Redis.

## What NOT to do

- **Don't invent a parallel pipeline for translation.** Follow the four-brick pipeline strictly: parsing → question → retrieval → generation → rendering. Each brick has a translation file inside it. No top-level `translation/` module.
- **Don't skip the question brick** because "translation has nothing to parse". `TranslationRequest` is real — target language, scope, style, glossary additions all come from the user message.
- **Don't skip the retrieval brick** when the user asks for partial translation ("only pages 3-15", "skip annexes"). Reuse the existing scope helpers; don't filter ad-hoc inside `translate_chunks`.
- Don't translate run by run (Word) or span by span (PDF). Paragraph-level translate-then-redistribute, period.
- Don't rebuild the Word or PDF document from scratch. Open the source as template, modify in place.
- Don't add Excel or PowerPoint translation in the same PR as Word + PDF. One format family per PR.
- Don't ship image translation in the first phase. Steps 1–8 first; step 9 once 1–8 are green.
- Don't expose `translate_word(...)` or `translate_pdf(...)` as the public API. The user calls `translate_document(...)` and dispatch is internal.
- Don't translate fields, numbering, hyperlink URLs, form-field labels, or PDF annotations. Skip them; don't send them to the LLM.
- Don't put the glossary inside the Pydantic model registry. It's data, lives in `data/glossaries/`.
- Don't extend `line_df` with span-level columns. `span_df` and `runs_df` are separate tables. `line_df` stays the RAG contract.
- Don't duplicate the run-distribution algorithm. It lives once in `generation/translation/distribute.py` and is called from both `rendering/word/runs.py` and `rendering/pdf/spans.py`.
- Don't reach into another format's parsing code. Cross-format dependencies go through `parsing/types.py` (the shared `LineDF` schema).
- Don't OCR scanned PDFs in this work. Raise `ScannedPdfError` and let the user know upfront. (Image-inside-PDF OCR is step 9 and is different from a fully-scanned PDF.)
