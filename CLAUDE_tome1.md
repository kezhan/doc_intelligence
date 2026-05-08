# Guidance for Claude Code working in this repository

This file tells Claude (or any AI assistant) how to work productively in this book project.

## Project overview

This is a book project — **Enterprise Document Intelligence**. The audience is engineers building production RAG systems on enterprise documents.

The book has **25 chapters across 5 parts**. The full plan lives in `book/00_full_plan.md`. Chapter status is in the top-level `README.md`.

The book takes a strong opinionated stance: RAG is not machine learning, embeddings are not magic, the four pillars (parsing, question parsing, retrieval, generation) are the conceptual core, structured output is what makes answers verifiable.

## Repository layout

- `book/` — the manuscript. One markdown file per chapter, plus a sub-folder of the same name for figures (e.g. `book/01_minimal_rag.md` and `book/01_minimal_rag/figure1.png`). Each figure folder also has a `_sources/` sub-folder holding the Python generators that produce those figures (`book/01_minimal_rag/_sources/draw_pipeline_ch1.py` → `book/01_minimal_rag/pipeline.png`). Sources stay next to their outputs so a single figure folder is self-contained.
- `notebooks/` — one notebook per chapter, same numbering as the markdown (`notebooks/01_minimal_rag.ipynb`). Notebooks import from `docintel`; they don't redefine functions.
- `src/docintel/` — the Python package. Code is organized **by module (pillar/topic)**, not by chapter. See [Code organization](#code-docintel-package) below.
- `data/` — input documents (PDFs).
- `output/` — generated artefacts (gitignored).
- `tests/` — tests for `src/docintel/` modules.
- `scripts/` — cross-chapter dev utilities (`excalidraw_to_png.py`, `code_to_png.py`, `_book_table.py`, `normalize_chapter.py`, probes). **Per-chapter figure generators live in `book/NN_topic/_sources/`, not here.**

## Conventions

### Manuscript (`book/` directory)

- **Filenames**: `NN_topic.md` with two-digit numeric prefix (e.g., `01_minimal_rag.md`).
- **Figures**: in a sub-folder of the same name as the chapter (`book/01_minimal_rag/figure1.png`). Reference from markdown with relative paths: `![Caption](01_minimal_rag/figure1.png)`.
- **Schemas / diagrams — full workflow**: **Excalidraw is the canonical tool for every figure in the series.** Matplotlib was tried and abandoned (chunky `mutation_scale` arrowheads, shadow halos around pills, fights to keep arrows from overshooting box edges). Excalidraw with bindings + `roughness: 0` arrows produces pixel-perfect tips for free.

  **The two-step pipeline** (run in order whenever a figure changes):
  1. **Generate the `.excalidraw` JSON from a Python script** at `book/NN_topic/_sources/draw_<topic>_excalidraw_ch<N>.py`. Reference template: `book/01_minimal_rag/_sources/draw_pipeline_excalidraw_ch1.py`. The script declares geometry constants (box positions, gap widths, font sizes), then assembles the elements via the `rect`, `text`, `arrow` factory functions and writes the JSON to `book/NN_topic/<name>.excalidraw`.
  2. **Export via Playwright + system Chrome.** The output extension chooses the format:
     ```bash
     # PNG (default rasterizer: SVG -> browser-render -> PNG, crispest text)
     python scripts/excalidraw_to_png.py \
         book/NN_topic/<name>.excalidraw \
         book/NN_topic/<name>.png \
         --scale 2.0

     # Vector SVG (text stays as text, lines stay as paths — smaller file, no rasterization)
     python scripts/excalidraw_to_png.py \
         book/NN_topic/<name>.excalidraw \
         book/NN_topic/<name>.svg

     # Force the legacy canvas PNG path (Excalidraw's native exportToBlob; text can look soft)
     python scripts/excalidraw_to_png.py ... --png-via canvas
     ```
     The export script ([`scripts/excalidraw_to_png.py`](scripts/excalidraw_to_png.py)) loads [`scripts/excalidraw_export.html`](scripts/excalidraw_export.html) in headless Chrome (via `channel="chrome"` — no need to download Chromium, which fails behind corp SSL). The HTML imports `@excalidraw/excalidraw@0.18.0` from `esm.sh` and exposes both `window.exportPng(data, scale)` and `window.exportSvg(data)`. By default the script exports to SVG first then takes a screenshot of that SVG rendered by the browser — the resulting PNG has subpixel-AA text rather than canvas rasterization. Medium accepts PNG at upload time.

  Both `.excalidraw` source and `.png` export are committed; the markdown references the `.png`. Re-run both steps when the figure source changes — they take seconds.

  **Geometry rules to follow inside the generator** (these are what make figures look professional, not "Excalidraw default"):
  - **Font**: `fontFamily: 2` (Helvetica) for all labels — *not* the hand-drawn Virgil default. Code identifiers (`AnswerWithEvidence`, `line_df`) read as junk in hand-drawn font; sans-serif labels look like a real architecture diagram.
  - **Box `roughness: 1`** (slightly wobbly hand-drawn outline — recognizably Excalidraw). **Arrow `roughness: 0`** (mathematically clean lines, no wobble overshoot). Pills, bands, zone backgrounds: `roughness: 0` (clean).
  - **Every arrow is bound** to its source and target rectangles via `startBinding` and `endBinding` with `{"elementId": "<box-id>", "focus": 0, "gap": 8}`. The bound rectangle's `boundElements` lists every attached arrow. Result: arrowheads always sit `gap` pixels off the box edge — clean buffer, never an overshoot, and arrows track the box if it moves in the Excalidraw editor. The canonical generator does this in a post-build pass.
  - **Pipeline gap widths sized to host the data pill** (no horizontal overflow into adjacent boxes). At `fontSize: 14` and pill height 26: `line_df` (~7 chars) needs ≥ 100 px gap, `filtered_pages` (~14 chars) needs ≥ 130 px, `AnswerWithEvidence` (~18 chars) needs ≥ 180 px.
  - **Inputs feeding multiple pipeline blocks: route via a horizontal trunk at the input box's *center y***, NOT diagonal arrows. Place the input below (or above) the pipeline row by enough that the trunk's y-coordinate is *outside* the pipeline boxes' vertical extent — that way the trunk runs straight right from the input's right edge with no DOWN-elbow into the pipeline-bottom area. Branches go UP from the trunk to each target box's bottom-center. For inputs feeding a *single* block, a direct diagonal is fine.
  - **Multi-target arrows skipping a pipeline box** (e.g. Generation → JSON output passes over Highlighting): route via an above-pipeline rail at `band_top + 40`. Use multi-segment paths via `points: [[0,0], [0,dy1], [dx,dy1], [dx,dy2]]` (relative to arrow origin). Never let an arrow cut diagonally through an unrelated box.
  - **Pipeline box labels are the topic name only** (`Parsing`, not `Block 1\nParsing`).
  - **Three-zone color grammar** (must match across diagrams): INPUTS amber band `#fff8e6` with `#fde68a` fills + `#b45309` strokes; PIPELINE blue band `#eef4ff` with `#bfdbfe` fills + `#1d4ed8` strokes; OUTPUTS emerald band `#ecfdf5` with `#a7f3d0` fills + `#047857` strokes. Zone labels in slate-400 `#94a3b8` at `band_top + 12`.
  - **Z-stacking by element order**: bands first → zone labels → boxes → box labels → arrows → pills (rect + text last). Excalidraw renders later elements on top.

  **One-time setup** (already done in this repo):
  - `pip install playwright`
  - System Chrome installed at `C:\Program Files\Google\Chrome\Application\chrome.exe` (or equivalent on macOS/Linux). The export script uses `channel="chrome"` to skip Playwright's 150 MB Chromium download (which fails behind corp SSL inspection).

  Image insertion in markdown follows the Medium-friendly pattern with a searchable caption marker:
  ```markdown
  ![Short alt text](NN_topic/figure.png)
  *Caption — figure.png: One-line description that doubles as Medium legend.*
  ```
  The `Caption — <filename>:` prefix is **mandatory**. Reasons: (1) when copy-pasting markdown into Medium, the image fails to upload — searching for `Caption` in the editor jumps you to every spot needing a manual drag-drop; (2) the filename in the caption tells you which PNG to drag from `book/NN_topic/` without leaving the editor.

  **Alt text** (the bracketed `[...]` part) must DESCRIBE what the figure shows, never just repeat a class or function name. Bad: `[RetrievalGranularity Pydantic schema]`, `[choose_methods function]`. Good: `[The two-scope schema, field by field]`, `[How choose_methods picks retrieval methods from the parsed question]`. Patterns: *"How X does Y"* (action), *"X: <what is shown>"* (structure), *"<verb phrase>"* or comma-separated steps (sequence). Alt text and caption are complementary — the caption is the technical legend with the filename marker; the alt text is the conceptual one-liner that helps screen readers, Google Images, and Medium previews. A reader scanning only the alt texts of an article should know what each figure is about.
- **Diagram visual grammar**: every diagram in the series uses the **same three-zone, three-color structure** so the reader builds a single visual vocabulary across articles:

  | Zone | Role | Fill | Edge | Text |
  |---|---|---|---|---|
  | **INPUTS** (left) | Data going in (PDF, question, schema, ...) | `#fde68a` (amber-200) | `#b45309` (amber-700) | `#78350f` (amber-900) |
  | **PIPELINE / PROCESSING** (middle) | Functions, steps, transformations | `#bfdbfe` (blue-200) | `#1d4ed8` (blue-700) | `#1e3a8a` (blue-900) |
  | **OUTPUTS** (right) | What the system returns (JSON, annotated PDF, table, ...) | `#a7f3d0` (emerald-200) | `#047857` (emerald-700) | `#064e3b` (emerald-900) |

  Background bands tinted with the same hue at low saturation (`#fff8e6`, `#eef4ff`, `#ecfdf5`) make the zones explicit. Zone labels (`INPUTS`, `PIPELINE`, `OUTPUTS`) sit at the top of each band in muted slate (`#94a3b8`).

  **Arrows:**
  - **Solid black** (slate-900 `#0f172a`) — main horizontal pipeline flow between processing blocks.
  - **Solid amber** (`#b45309`) — input feeding the *first* block.
  - **Dashed amber** (`#b45309`, `linestyle=(0, (5, 3))`) — input that's injected into *several* blocks (e.g., the same question feeds retrieval and generation).
  - **Solid emerald** (`#047857`) — pipeline producing an output.

  **Data labels between blocks**: white pill (`bbox=dict(boxstyle="round,pad=0.3", facecolor="#ffffff", edgecolor="#cbd5e1")`) positioned **above** the arrow (offset y of about +0.55 in matplotlib units), italic bold slate-700 text. Naming uses the actual data type or variable: `line_df`, `filtered_lines`, `AnswerWithEvidence`, etc.

  **Box style**: `FancyBboxPatch` with `boxstyle="round,pad=0.06,rounding_size=0.2"`, linewidth ~2.5, plus a soft drop shadow:
  ```python
  import matplotlib.patheffects as pe
  SHADOW = pe.withSimplePatchShadow(offset=(2, -2), shadow_rgbFace="#9ca3af", alpha=0.25)
  box.set_path_effects([SHADOW])
  ```

  **Typography**: bold sans-serif for box labels (fontsize 15-18 depending on box size), italic for data labels.

  **Same grammar for function-level diagrams**: when documenting a single function, frame it as `inputs (amber) → function box (blue) → outputs (emerald)` — same colors, same shadow style, same arrow conventions. The reader recognizes "input/process/output" instantly across the series.

  **Reference template**: `book/01_minimal_rag/_sources/draw_pipeline_ch1.py` is the canonical script. Copy + adapt it for new diagrams; do not invent a different palette or layout.
- **Tables as images**: never embed markdown tables (`| col | col |`) in published articles. Medium renders them poorly and they break copy-paste flow. Convert every table to a PNG via Excalidraw (default) or a matplotlib script that renders the table figure, then embed the PNG with the standard caption marker. Source files (`.excalidraw` or `book/NN_topic/_sources/draw_*.py`) live next to the chapter so the table can be edited and re-exported. Same caption rule: `*Caption — <filename>.png: ...*`.
- **Article header — series line + title + subtitle** (Medium publication format, mandatory for every article in `book/`):
  ```
  *Article N of Enterprise Document Intelligence*

  # Title

  *One-line italic subtitle that hooks the reader.*
  ```
  Three components in this exact order:
  - **Series line** (italic, line 1): plain text `*Article N of Enterprise Document Intelligence*`. No link (the series doesn't have a public Medium URL yet), no bold, no brackets. Top placement so the reader sees series position before reading the title.
  - **H1** (line 3): article title only, **no number prefix** (the series line conveys position). Em-dash `—` inside title when present, not hyphen.
  - **Subtitle** (italic, line 5): one-line tagline / hook. Becomes the Medium subtitle field at publish time.
  - Medium kicker is added by hand in the Medium editor at publish time — don't author one in the markdown source.
  - This format applies to **all** articles in `book/`. When migrating an existing chapter from the old `# Chapter N — Title` format, run the full sweep: replace the H1 line with the 3-component header, and apply the chapter→article voice rule.
- **Title self-sufficiency**: titles are read in isolation. Search results, social shares, Medium feeds, link previews. The reader doesn't know the series exists. So the title alone must (1) tell a stranger what the article is about, and (2) be interesting enough on its own to earn the click. Generic words like "Parsing" and series-internal phrases like "Structure Before Search" fail both: nothing in either tells the stranger this is about extracting text from PDFs for RAG. Prefer concrete, topic-specific titles that name the actual subject ("How RAG pipelines parse PDFs without losing structure", not "Parsing"). Test: imagine the title alongside articles from other authors in a Google result. Does it sell itself? Subtitles are not a rescue mechanism — many readers see only the title.
- **Code blocks**: NEVER leave empty lines inside ``` blocks. Medium splits the code block at empty lines, breaking the rendered output. Use minimal vertical breathing room and rely on inline comments.
- **Code-as-image** (when the code is more pedagogical than functional): the convention is the **annotated pill-box style**, NOT plain Pygments PNGs. The figure has a code panel on the left (line numbers, syntax-highlighted in soft pastel) and colored pill-boxes on the right that group code lines and explain *what each group does* in 1–2 italic sentences. Pill colors use the same accents as the pipeline diagrams: `amber`, `blue`, `violet`, `emerald`, `rose`. **Reference:** `book/01_minimal_rag/answer_schema_annotated.png`. Workflow:
  1. Identify 4–8 pedagogical code blocks (signature schemas, key functions, decision trees) per article.
  2. Copy `book/01_minimal_rag/_sources/draw_annotated_code_ch1.py` to `book/<NN_topic>/_sources/draw_annotated_code_ch<N>.py`. The script is a generic renderer; only the `SNIPPETS` list change (output goes to the script's parent directory by default).
  3. Define each snippet as `Snippet(name=..., code_lines=[(text, kind), ...], annotations=[(start, end, accent, title, body_lines), ...])`. `kind` is one of `"class"`, `"code"`, `"blank"`, `"comment"`. Line numbers in `(start, end)` are 1-based.
  4. The default `out_dir = Path(__file__).resolve().parent.parent` writes into the chapter folder; only change it if you need a sub-path.
  5. Run: `python book/<NN_topic>/_sources/draw_annotated_code_ch<N>.py`. Both light (`<name>.png`) and dark (`<name>_dark.png`) variants are produced into `book/<NN_topic>/`.
  6. Embed the light variant ABOVE the original code block, with the standard caption marker:
     ```markdown
     ![Short alt text](NN_topic/<name>.png)
     *Caption — <name>.png: One-line description.*

     ```python
     # original runnable code block stays here, untouched
     ```
     ```
  7. Don't delete the original code block. The author picks at publish time whether to keep image, code, or both.

  **Plain Pygments fallback (`scripts/code_to_png.py`)**: kept for cosmetic snippets where pill-boxes would be overkill (e.g. tiny one-liners). NOT the default. If unsure, use the annotated style.
- **Section headers**: don't double-number. The section number already conveys order — write `## 3. Parsing`, not `## 3. Block 1 — Parsing`. The "Block N" / "Step N" / "Stage N" prefix is filler when the section is already numbered. Same in notebooks: use plain headers like `# Parsing`, not `# Block 1 — Parsing`.
- **Voice — Medium series**: chapters in `book/` are published as a Medium article series, so the body uses **"Article N"**, **"this article"**, **"the series"** — not "Chapter N", "this chapter", "the book". First-person plural ("we'll") for explanatory parts is fine. Don't reference "Tome 1" or "Tome 2" — adjacent topics are framed as "out of scope" or "follow-up work". Exception: internal planning docs (`00_full_plan.md`, master plan files) keep "Chapter N" because they're not published.
- **Code in chapters**: should be illustrative and runnable, type-hinted, and consistent with the modules in `src/docintel/` (same function names, same signatures).
- **Worked examples**:
  - Parts I-III: NIST Cybersecurity Framework + *Attention Is All You Need* (1706.03762)
  - Parts IV-V: fictional insurance broker corpus (recurring across Chapters 16-25)
- **Never use proprietary documents as published examples.** The `data/` folder contains real proprietary PDFs (insurance contracts: AXA, Aviva, Generali, Groupama, MAIF, MMA, Allianz, GMF, Direct Assurance, Urban Jungle, StateFarm; corporate annual reports; client documents) that are present **for local testing only**. They must NOT be referenced by name or wired in as fixtures in any file under `book/` or `notebooks/`. Use only public-domain or openly-licensed sources (NIST publications, arXiv papers, US/EU government publications, openly-licensed datasets) or the fictional broker corpus authored for the series. Reason: copyright / redistribution risk for the published series.

### Cross-article references

When pointing to another article, use the explicit form: `Article 5` or `Article 5 (Parsing)`. Never say "later" without a number. The reader needs to be able to navigate.

### Notebooks (`notebooks/` directory)

- One notebook per chapter, named identically: `notebooks/NN_topic.ipynb`.
- Notebooks **import from `docintel`** — they don't redefine helper functions. The first cells set up imports; subsequent cells call the imported functions and inspect the outputs.
- Notebooks live alongside the chapter and serve as the interactive companion. The chapter's code blocks should match the notebook's calls (function names, signatures, argument order).

### Code (`src/docintel/` package)

The package is organized **by module (pillar/topic)**, not by chapter. The four bricks of the architecture (Part II opener) map directly to the top-level modules:

| Module | Purpose | Chapters |
|---|---|---|
| `core/` | Pydantic models, types, LLM/embedding clients | shared |
| `parsing/` | Brick 1 — document parsing, **split per format** (`pdf/`, future `docx`, `xlsx`, `pptx`, `mail`) | Ch 5, 10 |
| `question/` | Brick 2 — question parsing (question → structured JSON) | Ch 6 |
| `retrieval/` | Brick 3 — retrieval as scope selection | Ch 7, 9, 11, 12 |
| `generation/` | Brick 4 — generation as controlled execution | Ch 8 |
| `extraction/` | Structured extraction pipelines | Ch 14 |
| `pipeline/` | Composite orchestrator + dispatcher + feedback loops | Ch 13, 15 |
| `corpus/` | Corpus index, classification, versioning, filtering, SQL agent | Ch 16-21 |
| `storage/` | Long-format tables, repositories, replayable artefacts | Ch 25 |
| `annotation/` | PDF highlighting and annotated outputs | Ch 1, 25 |

**Parsing is split by format.** Tome 1 covers PDF only, but the package layout already anticipates the formats Tome 2 adds (Word, Excel, PowerPoint, mail). Each format lives in its own subpackage of `parsing/`:

```
src/docintel/parsing/
    pdf/                  # Tome 1 — current code
        line_df.py
        page_df.py
        columns.py
        objects.py
        source.py
        toc.py
        parse_pdf.py
        __init__.py       # re-exports parse_pdf, fitz_pdf_to_line_df, ...
    docx/                 # Tome 2 (other dev) — empty scaffold today
    xlsx/                 # Tome 2 — empty scaffold today
    pptx/                 # Tome 2 — empty scaffold today
    mail/                 # Tome 2 — empty scaffold today
    __init__.py           # documents the per-format split, no re-exports
```

Every format is a **subpackage** (folder with `__init__.py`), not a flat `.py` file. The `__init__.py` is the public surface (re-exports the entry point and shared types); the implementation is split across one file per topic inside the folder, mirroring how `parsing/pdf/` is laid out today.

Imports are **always format-explicit**: `from docintel.parsing.pdf import parse_pdf`. The top-level `parsing/__init__.py` does not re-export anything, so `from docintel.parsing import parse_pdf` is intentionally invalid — the format is part of the contract.

Every format produces the same output shape: a dict with `line_df`, `page_df` (or the format's page-equivalent), `parsing_summary`, plus format-specific tables (`toc_df`, `object_registry`, `image_df` for PDF; `runs_df`, `table_df` for Word; `cell_df`, `sheet_df` for Excel). Downstream bricks (`question`, `retrieval`, `generation`) stay format-agnostic because they consume `line_df`.

The same subfolder convention applies elsewhere in the package whenever a topic grows past a couple of modules — `retrieval/`, `generation/`, `corpus/` already follow it, and Tome 2's new intent files (`generation/translation/`, `generation/summarization/`, ...) graduate to subfolders the same way.

**Tome 2 conventions** (Word, Excel, PowerPoint, mail, plus translation/summarization/comparison) live in `CLAUDE_tome2.md`. Read that file before adding non-PDF parsing or any new intent (`generation/translation.py`, `generation/summarization.py`, ...).

**Code style:**

- Python 3.11+ syntax (`int | None`, etc.).
- Type hints on every public function.
- Pydantic for structured I/O.
- DataFrames over ORM objects for cross-layer data exchange.
- DB connections injected, never imported globally inside the function.
- Imports inside the package use the absolute, format-explicit form: `from docintel.parsing.pdf import fitz_pdf_to_line_df`. Never `from docintel.parsing import ...` for parsing helpers — that bypasses the per-format split.

**Variable naming — describe content, not the operation.** Local variables, DataFrames, and intermediate results are named after **what they hold**, not after the function that produced them. `parsed_question` (the parsed object), not `parsed`. `retrieved_pages_df`, not `result_df`. `bboxes_df`, `filtered_line_df`, `answer` — all describe content. Past participles as bare names (`parsed`, `filtered`, `extracted`, `matched`) name an operation, not a thing — append the noun. Single-letter (`q`, `p`, `df`) and lazy-numbered (`q2`, `p2`, `df3`) abbreviations are banned outside the tightest math loops where `i`, `j`, `n` are still fine. The rule is stricter in `book/` snippets than in throwaway shell experiments — published code is read as prose.

**Module organization — one method = one script.** When a module hosts multiple competing methods (retrieval, parsing, classification...), each method gets its own file **named after the method**. Examples: `retrieval/keyword_matching.py` (the keyword method), `retrieval/embedding_similarity.py` (the embedding + cosine method). Future siblings: `retrieval/bm25.py`, `retrieval/hybrid.py`. Avoid generic-operation file names (`top_k.py`, `cosine.py`, `helpers.py`, `utils.py`) — they say nothing about which method the file implements. Helpers used by exactly one method live in that method's file (`cosine_sim` lives in `embedding_similarity.py`, not in a separate `cosine.py`). The `__init__.py` re-exports public names so callers do `from docintel.retrieval import retrieve_pages`, not `from docintel.retrieval.keyword_matching import retrieve_pages`. **Article subsections map 1-to-1 to source files**: §2.4.a "Embeddings + cosine similarity" → `embedding_similarity.py`, §2.4.b "Keyword matching" → `keyword_matching.py`. The reader maps article ↔ source file at a glance.

**Adding code for a new chapter:**

1. Identify which module the new functions belong to (a chapter can touch several modules — that's expected).
2. Add the functions to the right module file (or create a new one).
3. Re-export public functions in the module's `__init__.py`.
4. Reference the new functions from the chapter's notebook (`notebooks/NN_topic.ipynb`) — don't redefine.
5. The chapter's prose can show simplified inline versions; the notebook calls the package version.

### Style

- Long-form, prose-heavy chapters with code blocks woven in.
- Each chapter follows roughly: Problem → Concepts → Approach → Watch out for → In practice → Summary.
- Recurring boxes: "In the wild" (real-world anecdote), "Common pitfall" (mistake to avoid), "Going further" (pointers).
- Worked examples are rich and concrete. Numbers are realistic.
- Insurance broker case continues across chapters with consistent framing.
- **Plain English**, not sophisticated. Short sentences, common words over Latinate ones.
- **Avoid AI-generated tells**. The series is written by a human; readers should never wonder if it was generated. Specific patterns to **avoid**:
  - **Em-dash `—`**: the single biggest tell. Overuse signals AI. Default to a period (start a new sentence), a comma, a colon, or parentheses. Em-dash is acceptable maybe once per article for a genuine parenthetical aside; never as a rhythmic substitute for periods.
  - **Vocabulary tells**: `delve`, `tapestry`, `leverage` (as a verb), `robust`, `seamless`, `comprehensive`, `plethora`, `myriad`, `intricate`, `intricacies`, `navigate the complexities`, `realm`, `embark`, `embark on a journey`, `transformative`, `cutting-edge`, `state-of-the-art`, `harness`, `harnessing the power of`, `bolster`, `shed light on`, `pave the way`, `elevate`, `profound`, `pivotal`, `crucial`, `vital`, `foster`, `cultivate`, `streamline`, `empower`, `spearhead`, `testament to`, `showcase`.
  - **Filler connectors**: `in essence`, `essentially`, `moreover`, `furthermore`, `additionally`, `it's worth noting that`, `it's important to note that`, `that being said`. Cut them — the sentence is usually stronger without.
  - **Generic openers**: `In today's [adjective] world`, `In the digital age`, `In the modern era`, `Whether you're a beginner or an expert`. Never use these.
  - **Construction patterns**: parallel three-item lists where two would do, hedge openings (`While X has its merits...`), wrap-up phrases (`In conclusion`, `To summarize`, `All in all`). Just stop the article when the argument ends.
  - When in doubt, write the way a senior engineer talks to another senior engineer: direct, specific, no padding.

## How to work on a chapter

When asked to write or revise a chapter:

1. **Read the master plan**: `book/00_full_plan.md` has the key ideas for that chapter.
2. **Read adjacent chapters**: chapters reference each other heavily; pick up the conventions and tone from neighbors.
3. **Match length and depth**: written chapters average 400-500 lines of markdown. Section count is typically 8-11 plus a Summary.
4. **Validate cross-references**: every chapter pointer must exist in the plan.
5. **Verify code blocks**: no empty lines inside; runnable if extracted; consistent with the corresponding `src/docintel/` modules.
6. **Update the README**: bump the chapter status in the table.

## Per-article checklist (proactively remind the author)

Every article in `book/` is a Medium publication. A working manuscript is *not* the same as a publication-ready article. Before considering an article done, walk through this checklist with the author. **Bring up each item proactively** — don't wait to be asked. The author may skip items, but they should be raised every time.

### Visual assets

For each section in the article, ask: *would a figure help here?* If yes, decide which kind:

- **Pipeline / architecture diagrams** → `book/NN_topic/_sources/draw_<topic>_ch<N>.py` with the three-zone matplotlib grammar (INPUTS amber / PIPELINE blue / OUTPUTS emerald). Reference template: `book/01_minimal_rag/_sources/draw_pipeline_ch1.py`. Always reproducible, versioned, consistent across articles.
- **Hand-drawn / interactive diagrams** → Excalidraw when the diagram benefits from organic layout (sketches, conceptual maps, anything that would feel sterile in matplotlib). Save both `<name>.excalidraw` (source, editable) and `<name>.png` (export) in `book/NN_topic/`. The markdown references the `.png`. **Geometry rules** (any tweak in Excalidraw must preserve these — see `book/01_minimal_rag/_sources/draw_pipeline_excalidraw_ch1.py` as canonical generator):
   - Arrow start/end points snap to source/target box edges. Never overshoot, never undershoot.
   - Arrows never cross unrelated boxes. If the source and target are not horizontally aligned with no obstacles between them, route the arrow above (rail at `band_top + 40`) or below (trunk at `pipeline_bottom + 100`) using multi-segment paths via `points: [[0,0], [dx1,dy1], ...]`.
   - Apply the same three-zone color grammar as matplotlib (zone bands, fills, strokes, dashed amber for inputs feeding multiple blocks, solid emerald for pipeline → output).
   - Pipeline-box gap widths are sized to host the data pill on the arrow (~100-180px depending on label length).
   - Box labels are the topic name only (`Parsing`, not `Block 1\nParsing`).
- **Pedagogical code snippets** (Pydantic schemas, function signatures, configuration objects, dataclass fields) → `scripts/code_to_png.py` produces a syntax-highlighted PNG with line-by-line comments as the lesson. Generates `<name>.png` (light) + `<name>_dark.png` (dark) by default. Keep the original code block in markdown alongside the image — the author trims at publish time.
- **Tables / DataFrames** → render via matplotlib for visual consistency (see `book/01_minimal_rag/_sources/draw_line_df_head_ch1.py`), not as raw markdown tables, when the rendered look matters for the article.
- **Document screenshots** → when the article shows a *result on a real document* (highlighted PDF page, annotated table, before/after view of the source), capture a screenshot of the rendered output. The annotated PDF from Article 1 is the canonical example: showing the highlighted lines on the actual page is more convincing than describing them. Workflow: open the artefact (PDF in a viewer at a clean zoom level, no surrounding chrome), screenshot the relevant page or region, save as `book/NN_topic/<descriptive_name>.png`. Crop tightly. If you annotate the screenshot itself (red box around the highlighted region, callout arrow), do that overlay in Excalidraw on top of the imported screenshot — saves both `.excalidraw` (with the screenshot embedded) and `.png` (export).
- **Screenshots of tools / terminals** → for terminal output, IDE views, browser views, anything not reproducible from code. Crop tightly, no surrounding chrome unless it's part of the point.

For every figure: caption line `*Caption — <filename>: one-line legend.*` is mandatory (Medium drag-drop marker).

### Prose hygiene

- **Voice**: "Article N", "this article", "the series" — never "Chapter", "this chapter", "the book". First person plural for explanations is fine. No "Tome 1/2" framing.
- **Header**: 3-component format (series line / `# Title` without number / italic subtitle). Title must stand alone in a Google result.
- **AI tells sweep**: count em-dashes (`—`) — if more than 3, run a contextual sweep replacing with period / comma / colon / parens. Grep for vocabulary tells (`delve`, `tapestry`, `leverage`, `robust`, `seamless`, `comprehensive`, `plethora`, `intricate`, `realm`, `transformative`, `harness`, `bolster`, `pivotal`, `crucial`, `foster`, `streamline`, `testament to`, `showcase`, etc.) and filler connectors (`in essence`, `moreover`, `it's worth noting`, etc.). Cut or rewrite each.
- **Plain English**: short sentences, common words over Latinate ones. Senior-engineer-to-senior-engineer tone.
- **Cross-references**: every "Article N" pointer must match the plan. No vague "later".
- **Code blocks**: no empty lines inside ``` (Medium splits the block).

### Structure

- Each article opens with an anecdote / hook, not a back-reference to the previous article.
- Section headers don't double-number (`## 3. Parsing`, not `## 3. Block 1 — Parsing`).
- Closes when the argument closes — no "In conclusion" wrap-ups.

### Final pass

- Update `README.md` chapter status table.
- Verify code in chapter matches `src/docintel/` signatures.
- Verify notebook in `notebooks/NN_topic.ipynb` imports rather than redefines.

## Trigger phrase: `audit <file>`

When the author writes `audit <path>` (e.g. `audit book/01_minimal_rag.md` or `audit notebooks/01_minimal_rag.ipynb`), run a full verification pass on that file and return a structured report. The audit is the same every time so the author can track progress across articles.

### `audit book/NN_topic.md` — markdown audit procedure

Run these checks in order, report findings as a numbered list with line numbers:

1. **Em-dash count**: `text.count("—")`. Target = 0, acceptable ≤ 1 (genuine parenthetical aside). Report count and grep each occurrence with `-n`.
2. **Vocabulary tells**: grep (case-insensitive) for `delve|tapestry|leverage|robust|seamless|comprehensive|plethora|myriad|intricate|navigate the complexities|realm|embark|transformative|cutting-edge|state-of-the-art|harness|bolster|shed light on|pave the way|elevate|profound|pivotal|crucial|vital|foster|cultivate|streamline|empower|spearhead|testament to|showcase`. Report every hit with line number; suggest replacement.
3. **Filler connectors**: grep (case-insensitive) for `\bin essence\b|\bessentially\b|\bmoreover\b|\bfurthermore\b|\badditionally\b|it's worth noting|it's important to note|\bthat being said\b`. Report every hit; the sentence is usually stronger without — suggest cut.
4. **Generic openers**: grep for `In today's|In the digital age|In the modern era|Whether you're a beginner`. Report every hit; rewrite required.
5. **Wrap-up phrases**: grep for `In conclusion|To summarize|All in all|To wrap up`. Report every hit; usually delete.
6. **Header format**: check lines 1-5 match exactly `*Article N of Enterprise Document Intelligence*` / blank / `# Title` (no number prefix) / blank / `*subtitle*`. Report mismatch.
7. **Voice consistency**: grep for `\bChapter \d|\bthis chapter\b|\bthe book\b|\bTome [12]\b`. Every hit must be replaced with Article/article/series language. Report each.
8. **Caption markers**: for every `![...](...)` image, the next non-empty line must start with `*Caption (filename:` or `*Caption — filename` (legacy). Report missing or malformed captions with line number.
9. **Cross-references**: grep for `Article \d+`. Verify each referenced number exists in `book/00_full_plan.md` (or current chapter set). Report broken pointers.
10. **Code block hygiene**: grep for empty lines inside ``` fences (Medium splits at empty lines). Report each.
11. **Section header double-numbering**: grep for `^##+ \d+\.\s*(Block|Step|Stage|Brick) \d+`. Report each.
12. **Visual asset opportunities**: scan section by section. For each section without a figure, judge whether one would help (pipeline diagram, schema-as-image, table-as-image, screenshot, Excalidraw sketch). Suggest concrete figure ideas — but flag as suggestion, not blocker.

End the audit with a summary: total issues found, issues that block publication (header, em-dash > 1, voice violations, broken refs, empty lines in code) vs polish suggestions (vocab tells, missing figures).

### `audit notebooks/NN_topic.ipynb` — notebook audit procedure

1. **Imports from `docintel`**: grep cells for `def ` definitions of helper functions that already exist in `src/docintel/`. Notebooks must import, not redefine. Report each redefinition.
2. **Setup pattern**: client setup should be direct in the notebook (`OpenAI(api_key=os.getenv(...), base_url=os.getenv(...))`), not wrapped in `get_chat_client()`-style helpers. Variable name is `model_chat`, not `model_name`.
3. **Header style**: markdown cell headers should be plain (`# Parsing`, not `# Block 1 — Parsing`).
4. **Signature alignment**: function calls in the notebook must match `src/docintel/` signatures (parameter names, order). Report mismatches.
5. **Path correctness**: `pdf_path`, `output_folder`, etc. point to `data/<subdir>/` and `output/<subdir>/` per the repo layout.
6. **Document fitness**: open the per-PDF index MD next to the document used (`data/<subdir>/<doc_stem>.md`). Confirm the chosen PDF is appropriate for the questions the notebook asks (length, structure, TOC quality, parsing quirks). If a more suitable document exists in the same `data/` subfolder, suggest swapping. If the PDF has no companion MD, write one as part of the audit.
7. **Multiple test scenarios**: don't trust a single happy-path question. Run the notebook end-to-end with at least 2-3 questions covering different difficulty regimes:
   - **Easy**: answer is in continuous prose on a single page (verifies the baseline works).
   - **Medium**: answer requires combining 2-3 lines or pages, or uses a slightly ambiguous wording.
   - **Hard / "should fail"**: question whose answer is not in the document, or that tests a known weakness (table-only data, OCR'd page, multi-column layout). The system should return the schema's null path or a clearly-marked "not found", never a fabricated answer.
   Report each result: did retrieval pull the right pages? Did generation cite correctly? Did highlighting land on the right region? Each failure mode is a real article finding.
8. **Cell output staleness**: flag cells where `execution_count` is null or out of order — the notebook should be runnable top-to-bottom and committed in a clean state.

End with summary as above.

## How to work on code

When asked to write or revise the runnable code for a chapter:

1. **Locate the right module(s)** in `src/docintel/`. A chapter typically extends one or two modules.
2. **Match the chapter's code blocks**: function names, parameter names, and signatures must match what the chapter shows. The chapter's inline code is the documentation; the package is the canonical version.
3. **Update the notebook**: `notebooks/NN_topic.ipynb` should import the new functions and use them, not redefine them.
4. **Test against fixtures**: code should produce the output described in the chapter when run against the documented fixture (e.g., `data/paper/1706.03762v7.pdf` for Chapter 1).
5. **Update the chapter if reality differs**: if running the code surfaces a different output than what the chapter claims, the chapter must be updated to match — never the other way around.

## Working with input documents (`data/`)

`data/` contains the curated input PDFs used by chapters and notebooks, grouped by source (`data/insurance/`, `data/nist/`, `data/paper/`, ...).

**Before picking a PDF for a chapter example or notebook**, check `data/<subdir>/<doc_stem>.md` if present. The MD describes the document's length, TOC quality, structural quirks, and what it's good for demonstrating. Pick from the index rather than re-parsing every candidate.

**When you analyze a PDF for the first time**, write a short companion MD next to it (`data/<subdir>/<doc_stem>.md`). Include: page count, structural notes (TOC depth, tables, multi-column, OCR), the kind of demo questions it suits, and parsing quirks worth remembering — for example, *NIST CSF v1.1 has a recurring 4-line page header that pollutes page-level embeddings; its Framework Core table is extracted column-wise so function-name and subcategory code never co-occur on a single line.* Update the MD whenever you discover new information.

These per-PDF notes are persistent context: future conversations should pick the right document from the index without re-parsing.

## Don'ts

- **Don't drift from the book's voice**: the book has a clear stance and a particular tone. Don't soften it, don't add hedge words, don't add LLM-style "as a helpful assistant" framing.
- **Don't add chapters that aren't in the plan** without confirming with the author.
- **Don't modify written chapters without explicit instruction**: the chapters in the table marked "Written" are reviewed and stable.
- **Don't add empty lines inside code blocks**: this breaks Medium rendering.
- **Don't use bullet points where prose flows better**: the book is prose-heavy by design.
- **Don't reference "Tome 1" or "Tome 2"**: out-of-scope topics are framed as "out of scope for this book" or "adjacent operations left for follow-up work".
- **Don't redefine helper functions in notebooks**: notebooks import from `docintel`. If the function isn't in the package yet, add it there first.
- **Don't organize new code by chapter**: the `code/chapter_NN/` layout is gone; everything goes into the right module under `src/docintel/`.
