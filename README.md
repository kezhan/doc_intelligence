# docpipeline

[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-59%20passed-brightgreen.svg)](#tests)

**Pipeline modulaire de traitement documentaire IA** — architecture *4 briques × N formats* inspirée du document de spécification Faseya.

> Le code n'est jamais le problème — c'est la clarté de l'organisation.
> La valeur se construit autour du LLM (parsing en amont, reconstitution en aval), pas dans le LLM lui-même.

---

## Philosophie

- **Modularité totale** — chaque brique a un *input clair, un output clair*, zéro interdépendance non maîtrisée
- **LLM uniquement où c'est justifié** — extraction, classification, conversion = 100% sans LLM (heuristiques + libs spécialisées). LLM réservé à : traduction, résumé, agent SQL en langage naturel
- **DataFrames standardisés** — sortie cohérente des parseurs (page, ligne, bbox, style, …) pour réutilisation aux étapes suivantes

## Architecture

```
                    ┌─────────────────────────────────────────┐
                    │  4 BRIQUES TRANSVERSES                  │
                    ├─────────────────────────────────────────┤
                    │  Parsing → Retrieval → Question → Gen   │
                    └─────────────────────────────────────────┘
                                       │
        ┌──────────────┬───────────────┼──────────────┬──────────────┐
        ▼              ▼               ▼              ▼              ▼
      PDF           Word            Excel       Translation     Excel SQL
   pipeline       pipeline        pipeline       pipeline      Agent (NL)
```

```
docpipeline/
├── parsing/
│   ├── pdf/         classifier (3 niveaux), extractor (texte+style+images), tables
│   ├── word/        parsing XML natif (TOC, spans, tableaux)
│   └── excel/       ingestion → SQLite/Parquet
├── conversion/      PDF → Word (Smart, Text, OCR + Enhancer)
├── retrieval/       filtrage progressif (keyword → regex → embeddings)
├── generation/      client LLM unifié (OpenAI + Anthropic) + résumé
├── translation/     glossaire métier + traduction Word préservant les styles
└── excel_agent/     agent SQL : question NL → SQL → résultat
```

## Installation

```bash
pip install docpipeline
```

ou depuis les sources :

```bash
git clone https://github.com/BosterJack/docpipeline.git
cd docpipeline
pip install -e .
```

### Dépendances système optionnelles

- **OCR** : installer [Tesseract](https://tesseract-ocr.github.io/tessdoc/Installation.html) puis `pip install pytesseract`
- **PaddleOCR** : `pip install paddleocr` (alternative GPU-friendly)

## Usage rapide

### Classification PDF (sans LLM)

```python
from docpipeline.parsing.pdf import classify_pdf

result = classify_pdf("contrat.pdf")
print(result.category.value)   # word_native | design_tool | scanned | other
print(result.confidence)        # 0.95
print(result.signals)           # ['meta:word_creator']
```

### Conversion PDF → Word

```python
from docpipeline.conversion import convert_pdf_to_word

result = convert_pdf_to_word("contrat.pdf", "contrat.docx")
print(result.engine_used)       # TextConverter (pdf2docx)
print(result.enhanced)          # True (post-traitement appliqué)
```

### Parsing Word natif

```python
from docpipeline.parsing.word import parse_word

doc = parse_word("contrat.docx")
print(doc.toc)                  # Table des matières
print(doc.tables[0])            # Premier tableau (DataFrame)
print(len(doc.spans))           # Spans avec ID stables
```

### Excel → Agent SQL en langage naturel

```python
from docpipeline.excel_agent import ExcelSQLAgent

agent = ExcelSQLAgent("sinistres.xlsx")  # nécessite OPENAI_API_KEY
result = agent.ask("Quelle ligne a le montant le plus élevé ?")
print(result.sql)               # SELECT * FROM sinistres ORDER BY ...
print(result.answer)            # DataFrame du résultat
```

### Traduction Word avec préservation des styles

```python
from docpipeline.translation import translate_word, Glossary, GlossaryEntry

glossary = Glossary([
    GlossaryEntry("IA", "fr", {"en": ["Individual Accident"]}, "insurance"),
    GlossaryEntry("BI", "fr", {"en": ["Business Interruption"]}, "insurance"),
])

translate_word("contrat.docx", target_lang="en", glossary=glossary)
# Génère contrat_en.docx avec spans/styles/couleurs préservés
```

## Le LLM, où et pourquoi ?

| Brique | LLM ? | Pourquoi |
|---|:---:|---|
| Classification PDF | ❌ | Heuristiques métadonnées + analyse contenu PyMuPDF |
| Extraction texte/images | ❌ | PyMuPDF natif |
| Tableaux PDF→Excel | ❌ | pdfplumber + détection de fragments |
| Parsing Word | ❌ | XML natif via python-docx |
| Excel → SQLite | ❌ | pandas + sqlite3 |
| Conversion PDF→Word | ❌ | PyMuPDF (Smart) / pdf2docx (Text) / Tesseract (OCR) |
| Retrieval | ❌ | keyword + regex + embeddings (optionnel) |
| **Traduction** | ✅ | Sémantique cross-langue + glossaire contextuel |
| **Agent SQL Excel** | ✅ | Compréhension de question NL |
| **Résumé** | ✅ | Synthèse de contenu |

## Tests

```bash
pytest tests/ -v
# 59 passed
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
