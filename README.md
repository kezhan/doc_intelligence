# docpipeline

[![PyPI](https://img.shields.io/pypi/v/docpipeline.svg)](https://pypi.org/project/docpipeline/)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-73%20passed-brightgreen.svg)](#tests)

**Pipeline modulaire de traitement documentaire IA** — architecture *4 briques × N formats* basée sur la spécification Faseya.

> Le code n'est jamais le problème — c'est la clarté de l'organisation.
> La valeur se construit autour du LLM (parsing en amont, reconstitution en aval), pas dans le LLM lui-même.

---

## ⚡ Démarrage en 30 secondes

```bash
pip install docpipeline
```

**Python (4 fonctions, c'est tout) :**
```python
import docpipeline

docpipeline.convert("contrat.pdf", "contrat.docx")    # PDF → Word
docpipeline.convert("rapport.pdf", "tableaux.xlsx")   # PDF → Excel
docpipeline.parse("document.pdf")                     # → DataFrame
docpipeline.classify("document.pdf")                  # → catégorie + confiance
docpipeline.summarize("rapport.pdf")                  # → résumé (LLM)
```

**Ligne de commande :**
```bash
docpipeline convert  contrat.pdf contrat.docx       # Conversion auto
docpipeline convert  rapport.pdf tableaux.xlsx      # Tableaux → Excel
docpipeline classify document.pdf                   # Catégoriser un PDF
docpipeline parse    document.pdf --csv out.csv     # Extraction → CSV
docpipeline ask      data.xlsx "Quelle ligne a le montant max ?"
docpipeline translate contrat.docx --to en
docpipeline summarize rapport.pdf
docpipeline dedupe-images doc1.pdf doc2.pdf --logos
```

## Philosophie

- **Modularité totale** — chaque brique a un *input clair, un output clair*, zéro interdépendance non maîtrisée
- **LLM uniquement où c'est justifié** — extraction, classification, conversion = 100% sans LLM (heuristiques + libs spécialisées). LLM réservé à : traduction, résumé, agent SQL en langage naturel
- **DataFrames standardisés** — sortie cohérente des parseurs (page, ligne, bbox, style, …) pour réutilisation aux étapes suivantes

## Architecture

```
                    ┌─────────────────────────────────────────┐
                    │  4 BRIQUES TRANSVERSES                  │
                    │  Parsing → Retrieval → Question → Gen   │
                    └─────────────────────────────────────────┘
                                       │
       ┌──────────────┬─────────────┬──┴──────────────┬─────────────┬──────────────┐
       ▼              ▼             ▼                 ▼             ▼              ▼
     PDF           Word          Excel             PPTX           Email      Conversion
   pipeline      pipeline      (SQL agent)       pipeline       pipeline     PDF↔Word
```

```
docpipeline/
├── parsing/
│   ├── pdf/         classifier 3-niveaux, extracteur texte+style+images,
│   │                tableaux multi-pages, image_store cross-documents
│   ├── word/        parser XML natif (TOC, spans, tableaux), consolidator Word+PDF
│   ├── excel/       ingestion → SQLite/Parquet
│   ├── pptx/        parser slides natif
│   └── email/       parser .eml (headers + corps + pièces jointes)
├── conversion/      PDF→Word (Smart/Text/OCR + Enhancer 11 étapes)
├── retrieval/       Python (keyword/regex/embeddings) ou SQL (FTS5)
├── generation/      client LLM unifié (OpenAI + Anthropic) + résumé
├── translation/     glossaire métier + traduction Word + reconstitution PDF
│                    + visualiseur HTML côte-à-côte
└── excel_agent/     agent SQL : question NL → SQL → résultat
```

## Installation

```bash
pip install docpipeline                  # base
pip install docpipeline[llm]             # + OpenAI + Anthropic (résumé, traduction, agent SQL)
pip install docpipeline[ocr]             # + Tesseract pour PDFs scannés
pip install docpipeline[all]             # tout
```

### Dépendances système optionnelles

- **OCR Tesseract** : installer le binaire [Tesseract](https://tesseract-ocr.github.io/tessdoc/Installation.html)
- **Conversion DOCX → PDF** : `pip install docx2pdf` ou avoir LibreOffice installé

## Conversions supportées

| Source | → | Cible | Moteur | LLM ? |
|---|:-:|---|---|:-:|
| `.pdf` (Word natif) | → | `.docx` | TextConverter (pdf2docx) | ❌ |
| `.pdf` (design tool) | → | `.docx` | SmartConverter (PyMuPDF) | ❌ |
| `.pdf` (scanné) | → | `.docx` | OCRConverter (Tesseract) | ❌ |
| `.pdf` (avec tableaux) | → | `.xlsx` | pdfplumber + consolidation | ❌ |
| `.docx` | → | `.pdf` | docx2pdf / LibreOffice | ❌ |
| `.xlsx` | → | `.db` (SQLite) | pandas + sqlite3 | ❌ |
| `.docx` (FR) | → | `.docx` (EN) | translate_word + glossaire | ✅ |

Toutes ces conversions **préservent le contenu original** : police, taille, couleur, position, tableaux, images, mise en page.

## Usage avancé

### Classification PDF (sans LLM)

```python
from docpipeline import classify

result = classify("contrat.pdf")
print(result.category.value)   # word_native | design_tool | scanned | other
print(result.confidence)        # 0.95
print(result.signals)           # ['meta:word_creator']
```

### Conversion PDF → Word avec choix moteur

```python
from docpipeline.conversion import convert_pdf_to_word

result = convert_pdf_to_word(
    "contrat.pdf", "contrat.docx",
    force_engine="smart",     # 'smart' (PyMuPDF) | 'text' (pdf2docx) | 'ocr' (Tesseract)
    enhance=True,             # post-traitement DocxEnhancer (11 étapes de nettoyage)
)
print(result.engine_used)     # SmartConverter (PyMuPDF)
```

### Parsing Word natif avec TOC + spans

```python
from docpipeline.parsing.word import parse_word

doc = parse_word("contrat.docx")
print(doc.toc)                # Table des matières hiérarchique
print(doc.tables[0])          # Premier tableau natif (DataFrame)
print(len(doc.spans))         # Spans avec ID stables (pour traduction)
```

### Consolidation Word + PDF

```python
from docpipeline.parsing.word import consolidate_word_pdf

unified = consolidate_word_pdf("contrat.docx", "contrat_signe.pdf")
# → structure native Word + annotations PDF (signatures, surlignages)
```

### Excel → Agent SQL en langage naturel

```python
from docpipeline.excel_agent import ExcelSQLAgent

agent = ExcelSQLAgent("sinistres.xlsx")  # nécessite OPENAI_API_KEY
result = agent.ask("Quelle ligne a le montant le plus élevé ?")
print(result.sql)             # SELECT * FROM sinistres ORDER BY ...
print(result.answer)          # DataFrame du résultat
```

### Traduction Word avec glossaire métier

```python
from docpipeline.translation import translate_word, Glossary, GlossaryEntry

glossary = Glossary([
    GlossaryEntry("IA", "fr", {"en": ["Individual Accident"]}, "insurance"),
    GlossaryEntry("BI", "fr", {"en": ["Business Interruption"]}, "insurance"),
])

translate_word("contrat.docx", target_lang="en", glossary=glossary)
# → contrat_en.docx avec spans/styles/couleurs préservés
```

### Reconstitution PDF traduit + visualiseur côte-à-côte

```python
from docpipeline.parsing.pdf import extract_full_with_style
from docpipeline.translation import reconstruct_pdf_translation, render_side_by_side

df         = extract_full_with_style("contrat.pdf")
translated = {row.span_id: translate(row.text) for _, row in df.iterrows()}

reconstruct_pdf_translation("contrat.pdf", df, translated, "contrat_en.pdf")
render_side_by_side("contrat.pdf", "contrat_en.pdf", df, translated, "compare.html")
# → compare.html : visualisation interactive avec correspondance positionnelle
```

### Retrieval SQL (FTS5)

```python
from docpipeline.retrieval import SQLRetriever
from docpipeline.parsing.pdf import extract_text_dataframe

df  = extract_text_dataframe("rapport.pdf")
ret = SQLRetriever.from_dataframe(df, "rapport.db")

results = ret.retrieve("franchise garantie", top_k=10)
```

### Déduplication d'images cross-documents

```python
from docpipeline.parsing.pdf.image_store import CrossDocImageStore

store = CrossDocImageStore.open("images.db", "images_dir/")
for pdf in ["contrat1.pdf", "contrat2.pdf", "contrat3.pdf"]:
    store.ingest_pdf(pdf)

logos = store.find_logo_candidates(min_documents=2)
# → liste des images apparaissant dans plusieurs documents
```

### Parsing PowerPoint et email

```python
from docpipeline.parsing.pptx import parse_pptx
from docpipeline.parsing.email import parse_email

slides = parse_pptx("presentation.pptx")
print(slides.slide_titles)
print(slides.df)              # une ligne = un paragraphe par slide

email = parse_email("notification.eml")
print(email.headers["from"])
print(email.attachments)
```

## Le LLM, où et pourquoi ?

| Brique | LLM ? | Pourquoi |
|---|:---:|---|
| Classification PDF (4 catégories) | ❌ | Heuristiques métadonnées + analyse contenu PyMuPDF |
| Extraction texte/images/style | ❌ | PyMuPDF natif |
| Tableaux multi-pages PDF→Excel | ❌ | pdfplumber + détection de fragments |
| Parsing Word/PPTX/email | ❌ | XML natif |
| Excel → SQLite | ❌ | pandas + sqlite3 |
| Conversion PDF→Word | ❌ | PyMuPDF (Smart) / pdf2docx (Text) / Tesseract (OCR) |
| Retrieval | ❌ | keyword + regex + FTS5 SQL + embeddings (optionnel) |
| Reconstitution PDF traduit | ❌ | PyMuPDF redact + insert_textbox |
| Visualiseur côte-à-côte | ❌ | HTML/CSS/JS pur |
| Déduplication images | ❌ | Hash MD5 |
| **Traduction** | ✅ | Sémantique cross-langue + glossaire contextuel |
| **Agent SQL Excel** | ✅ | Compréhension de question NL |
| **Résumé** | ✅ | Synthèse de contenu |

## Tests

```bash
pytest tests/ -v
# 73 passed
```

Démonstration interactive avec fichiers réels :

```bash
python -X utf8 demo.py        # toutes les démos
python -X utf8 demo.py 1      # une démo isolée (1 à 7)
```

## Crédits

- Architecture inspirée du document de spécification interne **Faseya IA**
- Convertisseurs PDF → Word portés depuis [CHRISTMardochee/pdf2word](https://github.com/CHRISTMardochee/pdf2word) — code intégré et personnalisé (couleurs neutres, multi-langues OCR, sélection auto par classification)

## Licence

MIT — voir [LICENSE](LICENSE)
