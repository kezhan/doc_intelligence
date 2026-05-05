"""
docpipeline — Interface en ligne de commande.

Usage :
    docpipeline convert  input.pdf  output.docx          # PDF → Word (auto)
    docpipeline convert  input.pdf  tableaux.xlsx        # PDF → Excel
    docpipeline convert  input.pdf  output.docx --engine ocr --lang fra+eng
    docpipeline classify input.pdf
    docpipeline parse    input.pdf
    docpipeline extract  input.pdf  --images-dir out/
    docpipeline ask      data.xlsx  "Quelle ligne a le montant max ?"
    docpipeline summarize input.pdf
    docpipeline translate input.docx --to en --glossary glossary.json
    docpipeline dedupe-images doc1.pdf doc2.pdf --store images.db
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Force UTF-8 sur Windows pour les caractères accentués
if sys.platform == "win32":
    os.environ.setdefault("PYTHONUTF8", "1")
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="docpipeline",
        description="Pipeline modulaire de traitement documentaire IA.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples :
  docpipeline convert contrat.pdf contrat.docx
  docpipeline convert rapport.pdf tableaux.xlsx
  docpipeline classify document.pdf
  docpipeline ask sinistres.xlsx "Quelle ligne a le montant max ?"
  docpipeline translate contrat.docx --to en
        """
    )

    sub = parser.add_subparsers(dest="cmd", required=True, metavar="COMMAND")

    # ── convert ──────────────────────────────────────────────────────────────
    p_conv = sub.add_parser("convert", help="Convertir un document (auto-détection format)")
    p_conv.add_argument("input",  help="Fichier source")
    p_conv.add_argument("output", help="Fichier de sortie (extension détermine la conversion)")
    p_conv.add_argument(
        "--engine",
        choices=["adobe", "msword", "docling", "libreoffice", "smart", "text", "ocr", "hybrid", "overlay"],
        help="Forcer un moteur de conversion (PDF→Word) :\n"
             "  adobe       = qualité Acrobat Pro (cloud, gratuit jusqu'à 500/mois)\n"
             "  msword      = Word PDF Reflow (Windows + Office)\n"
             "  docling     = IBM ML (gratuit, offline, ~80% qualité Adobe)\n"
             "  libreoffice = LibreOffice headless (multi-OS)\n"
             "  smart       = PyMuPDF reconstruction (offline)\n"
             "  text        = pdf2docx (PDFs Word natifs)\n"
             "  ocr         = Tesseract pour PDFs scannés\n"
             "  hybrid      = image + texte invisible (visuel parfait, non éditable)\n"
             "  overlay     = image + zones texte éditables (visuel parfait + éditable) ⭐"
    )
    p_conv.add_argument("--prefer", choices=["balanced", "editable", "visual"],
                        default="balanced",
                        help="Stratégie : 'editable' évite hybrid, 'visual' privilégie hybrid")
    p_conv.add_argument("--dpi", type=int, default=200,
                        help="Résolution rendu mode hybride (défaut 200)")
    p_conv.add_argument("--lang", default="fra+eng",
                        help="Langues OCR (défaut : fra+eng)")
    p_conv.add_argument("--no-enhance", action="store_true",
                        help="Désactiver le post-traitement DocxEnhancer")

    # ── classify ─────────────────────────────────────────────────────────────
    p_cls = sub.add_parser("classify", help="Classifier un PDF (sans LLM)")
    p_cls.add_argument("input")
    p_cls.add_argument("--json", action="store_true", help="Sortie JSON")

    # ── parse ────────────────────────────────────────────────────────────────
    p_par = sub.add_parser("parse", help="Parser un document → DataFrame standardisé")
    p_par.add_argument("input")
    p_par.add_argument("--head", type=int, default=10, help="Lignes à afficher (défaut 10)")
    p_par.add_argument("--csv", help="Exporter le résultat en CSV")

    # ── extract ──────────────────────────────────────────────────────────────
    p_ext = sub.add_parser("extract", help="Extraction enrichie PDF (texte + style + images)")
    p_ext.add_argument("input")
    p_ext.add_argument("--images-dir", help="Dossier où sauvegarder les images extraites")
    p_ext.add_argument("--style", action="store_true",
                       help="Extraction enrichie avec style (police, taille, couleur)")
    p_ext.add_argument("--csv", help="Exporter en CSV")

    # ── ask ──────────────────────────────────────────────────────────────────
    p_ask = sub.add_parser("ask", help="Agent SQL : question NL sur un Excel (LLM)")
    p_ask.add_argument("xlsx")
    p_ask.add_argument("question")
    p_ask.add_argument("--show-sql", action="store_true", help="Afficher la requête SQL")

    # ── summarize ────────────────────────────────────────────────────────────
    p_sum = sub.add_parser("summarize", help="Résumer un document (LLM)")
    p_sum.add_argument("input")
    p_sum.add_argument("--out", help="Fichier de sortie (défaut stdout)")

    # ── translate ────────────────────────────────────────────────────────────
    p_tr = sub.add_parser("translate", help="Traduire un .docx en préservant les styles (LLM)")
    p_tr.add_argument("input")
    p_tr.add_argument("--to", required=True, help="Langue cible (ex. en, fr, de)")
    p_tr.add_argument("--from", dest="source_lang", default="fr", help="Langue source (défaut fr)")
    p_tr.add_argument("--glossary", help="Fichier glossaire JSON")
    p_tr.add_argument("--out", help="Fichier .docx de sortie")

    # ── dedupe-images ────────────────────────────────────────────────────────
    p_dd = sub.add_parser("dedupe-images",
                          help="Indexer et dédupliquer les images entre plusieurs PDFs")
    p_dd.add_argument("pdfs", nargs="+", help="Fichiers PDF à indexer")
    p_dd.add_argument("--store", default="images.db", help="Base SQLite (défaut images.db)")
    p_dd.add_argument("--images-dir", default="dedup_images",
                      help="Dossier images uniques (défaut dedup_images/)")
    p_dd.add_argument("--logos", action="store_true",
                      help="Lister les logos (images apparaissant dans plusieurs documents)")

    # ── version ──────────────────────────────────────────────────────────────
    sub.add_parser("version", help="Afficher la version")

    args = parser.parse_args(argv)

    try:
        return _dispatch(args)
    except FileNotFoundError as exc:
        print(f"Erreur : {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"Erreur : {exc}", file=sys.stderr)
        return 1


# ── Dispatcher ───────────────────────────────────────────────────────────────

def _dispatch(args) -> int:
    cmd = args.cmd
    if cmd == "convert":       return _cmd_convert(args)
    if cmd == "classify":      return _cmd_classify(args)
    if cmd == "parse":         return _cmd_parse(args)
    if cmd == "extract":       return _cmd_extract(args)
    if cmd == "ask":           return _cmd_ask(args)
    if cmd == "summarize":     return _cmd_summarize(args)
    if cmd == "translate":     return _cmd_translate(args)
    if cmd == "dedupe-images": return _cmd_dedupe(args)
    if cmd == "version":       return _cmd_version()
    return 1


# ── Commandes ────────────────────────────────────────────────────────────────

def _cmd_convert(args) -> int:
    from . import convert
    options = {}
    if args.engine:
        options["force_engine"] = args.engine
    if args.lang:
        options["ocr_lang"] = args.lang
    if args.no_enhance:
        options["enhance"] = False
    if hasattr(args, "dpi"):
        options["hybrid_dpi"] = args.dpi
    if hasattr(args, "prefer") and args.prefer:
        options["prefer"] = args.prefer

    # On utilise la fonction interne pour récupérer les métadonnées
    src_ext = Path(args.input).suffix.lower()
    dst_ext = Path(args.output).suffix.lower()

    if src_ext == ".pdf" and dst_ext == ".docx":
        from .conversion import convert_pdf_to_word
        result = convert_pdf_to_word(args.input, args.output, **options)
        print(f"✓ Conversion terminée : {result.output_path}")
        print(f"  Moteur          : {result.engine_used}")
        print(f"  Catégorie PDF   : {result.category.value} ({result.confidence:.0%})")
        print(f"  Éditable        : {'oui' if result.editable else 'non (image)'}")
        print(f"  Fidélité visuel : {result.visual_fidelity}")
        for w in result.warnings:
            print(f"  ⚠ {w}")
    else:
        output = convert(args.input, args.output, **options)
        print(f"✓ Conversion terminée : {output}")
    return 0


def _cmd_classify(args) -> int:
    from . import classify
    result = classify(args.input)

    if args.json:
        print(json.dumps({
            "category":   result.category.value,
            "confidence": result.confidence,
            "creator":    result.creator,
            "producer":   result.producer,
            "page_count": result.page_count,
            "signals":    result.signals,
        }, indent=2, ensure_ascii=False))
    else:
        print(f"  Catégorie    : {result.category.value}")
        print(f"  Confiance    : {result.confidence:.0%}")
        print(f"  Créateur     : {result.creator or '(absent)'}")
        print(f"  Producteur   : {result.producer or '(absent)'}")
        print(f"  Pages        : {result.page_count}")
        print(f"  Signaux      : {', '.join(result.signals)}")
    return 0


def _cmd_parse(args) -> int:
    from . import parse
    result = parse(args.input)

    df = result.df if hasattr(result, "df") else result

    if args.csv:
        df.to_csv(args.csv, index=False)
        print(f"✓ Exporté : {args.csv} ({len(df)} lignes)")
    else:
        print(f"  {len(df)} lignes × {len(df.columns)} colonnes")
        print(f"  Colonnes : {list(df.columns)}\n")
        print(df.head(args.head).to_string(index=False))
    return 0


def _cmd_extract(args) -> int:
    from .parsing.pdf import extract_text_dataframe, extract_full_with_style, extract_images_dataframe

    if args.style:
        df = extract_full_with_style(args.input)
        print(f"  Extraction avec style : {len(df)} spans")
    else:
        df = extract_text_dataframe(args.input)
        print(f"  Extraction texte : {len(df)} lignes")

    if args.images_dir:
        imgs = extract_images_dataframe(args.input, args.images_dir)
        print(f"  Images extraites : {len(imgs)} → {args.images_dir}")

    if args.csv:
        df.to_csv(args.csv, index=False)
        print(f"  CSV : {args.csv}")
    else:
        print(df.head(10).to_string(index=False))
    return 0


def _cmd_ask(args) -> int:
    from .excel_agent import ExcelSQLAgent
    agent  = ExcelSQLAgent(args.xlsx)
    result = agent.ask(args.question)
    if args.show_sql:
        print(f"SQL : {result.sql}\n")
    print(result.answer.to_string(index=False))
    return 0


def _cmd_summarize(args) -> int:
    from . import summarize
    text = summarize(args.input)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"✓ Résumé : {args.out}")
    else:
        print(text)
    return 0


def _cmd_translate(args) -> int:
    from .translation import Glossary, translate_word

    glossary = Glossary.from_json(args.glossary) if args.glossary else None
    out = args.out or str(Path(args.input).with_stem(f"{Path(args.input).stem}_{args.to}"))

    result = translate_word(
        args.input, target_lang=args.to, source_lang=args.source_lang,
        glossary=glossary, output_path=out,
    )
    print(f"✓ Traduction terminée : {result}")
    return 0


def _cmd_dedupe(args) -> int:
    from .parsing.pdf.image_store import CrossDocImageStore
    store = CrossDocImageStore.open(args.store, args.images_dir)
    for pdf in args.pdfs:
        stats = store.ingest_pdf(pdf)
        print(f"  {Path(pdf).name} : {stats['new']} nouvelles, {stats['duplicates']} doublons")

    s = store.stats()
    print(f"\nTotal : {s['unique_images']} images uniques sur "
          f"{s['total_occurrences']} occurrences ({s['documents']} documents)")

    if args.logos:
        logos = store.find_logo_candidates()
        if logos:
            print(f"\nLogos détectés ({len(logos)}) :")
            for lo in logos:
                print(f"  {lo['hash'][:12]} — {lo['width']}×{lo['height']} — "
                      f"{lo['documents']} docs — {lo['path']}")
    return 0


def _cmd_version() -> int:
    from . import __version__
    print(f"docpipeline {__version__}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
