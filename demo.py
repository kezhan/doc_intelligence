"""
demo.py - Test du pipeline docpipeline avec de vrais fichiers.

Lancer :  python demo.py
"""
import os, sys
# Force UTF-8 sur la console Windows
if sys.platform == "win32":
    os.environ.setdefault("PYTHONUTF8", "1")
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

import sys
from pathlib import Path

# Ajoute le package au path si non installé
sys.path.insert(0, str(Path(__file__).parent))

FIXTURES = Path(__file__).parent / "tests" / "fixtures"
WORD_FILE  = FIXTURES / "contrat_assurance.docx"
EXCEL_FILE = FIXTURES / "sinistres.xlsx"
PDF_FILE   = FIXTURES / "notice_garanties.pdf"

SEP = "=" * 60


def header(title: str) -> None:
    print(f"\n{SEP}\n  {title}\n{SEP}")


# ─────────────────────────────────────────────────────────────
# 1. PDF — Classification
# ─────────────────────────────────────────────────────────────
def demo_pdf_classifier():
    header("1. PDF — Classification (TODO-001 à 004)")
    from docpipeline.parsing.pdf.classifier import (
        classify_pdf, detect_scanned_no_text,
        detect_scanned_with_text, detect_native_text,
    )

    print(f"Fichier : {PDF_FILE.name}\n")

    result = classify_pdf(PDF_FILE)
    print(f"  Catégorie    : {result.category.value}")
    print(f"  Créateur     : {result.creator or '(vide)'}")
    print(f"  Producteur   : {result.producer or '(vide)'}")
    print(f"  Nb pages     : {result.page_count}")

    scanned = detect_scanned_no_text(PDF_FILE)
    print(f"\n  Scanné sans texte ? {scanned.is_scanned_no_text}")
    print(f"  Pages image  : {scanned.image_page_count}")
    print(f"  Pages texte  : {scanned.text_page_count}")
    print(f"  Ratio texte  : {scanned.text_image_ratio:.0%}")

    native = detect_native_text(PDF_FILE)
    print(f"\n  Texte natif ?  {native.is_native_text}")
    print(f"  Couverture   : {native.coverage_ratio:.0%}")


# ─────────────────────────────────────────────────────────────
# 2. PDF — Extraction texte (DataFrame standardisé)
# ─────────────────────────────────────────────────────────────
def demo_pdf_extractor():
    header("2. PDF — Extraction texte (TODO-005 / TODO-010)")
    from docpipeline.parsing.pdf.extractor import (
        extract_text_dataframe, extract_full_with_style,
    )

    print(f"Fichier : {PDF_FILE.name}\n")

    df = extract_text_dataframe(PDF_FILE)
    print(f"  DataFrame standard : {len(df)} lignes × {len(df.columns)} colonnes")
    print(f"  Colonnes : {list(df.columns)}")
    print(f"\n  Aperçu (5 premières lignes) :")
    print(df[["page", "line", "text"]].head(5).to_string(index=False))

    print()
    df_style = extract_full_with_style(PDF_FILE)
    print(f"  DataFrame enrichi (style) : {len(df_style)} spans")
    print(f"  Colonnes : {list(df_style.columns)}")
    print(f"\n  Aperçu avec style :")
    print(df_style[["page", "span_id", "text", "font", "size", "bold"]].head(5).to_string(index=False))


# ─────────────────────────────────────────────────────────────
# 3. Word — Parsing natif XML
# ─────────────────────────────────────────────────────────────
def demo_word_parser():
    header("3. Word — Parsing natif XML (TODO-011)")
    from docpipeline.parsing.word.parser import parse_word

    print(f"Fichier : {WORD_FILE.name}\n")

    result = parse_word(WORD_FILE)

    print(f"  Paragraphes  : {len(result.df)}")
    print(f"  Spans totaux : {len(result.spans)}")
    print(f"  Tableaux     : {len(result.tables)}")

    print(f"\n  Table des matières ({len(result.toc)} entrées) :")
    for entry in result.toc:
        indent = "  " * entry["level"]
        print(f"    {indent}[H{entry['level']}] {entry['title']}")

    if result.tables:
        print(f"\n  Premier tableau natif ({len(result.tables[0])} lignes) :")
        print(result.tables[0].to_string(index=False))

    print(f"\n  Spans avec style (5 premiers) :")
    for s in result.spans[:5]:
        flags = []
        if s["bold"]:    flags.append("GRAS")
        if s["italic"]:  flags.append("ITALIC")
        if s["color"]:   flags.append(f"couleur={s['color']}")
        style_str = ", ".join(flags) or "normal"
        print(f"    [{s['span_id']}] \"{s['text'][:40]}\" → {style_str}")


# ─────────────────────────────────────────────────────────────
# 4. Excel — Ingestion SQLite
# ─────────────────────────────────────────────────────────────
def demo_excel_ingester():
    header("4. Excel — Ingestion SQLite (TODO-019)")
    import sqlite3
    from docpipeline.parsing.excel.ingester import ingest_excel

    print(f"Fichier : {EXCEL_FILE.name}\n")

    db_path = FIXTURES / "sinistres.db"
    db_path.unlink(missing_ok=True)

    result = ingest_excel(EXCEL_FILE, db_path, output_format="sqlite")
    print(f"  Base SQLite créée : {result.name}")

    conn = sqlite3.connect(str(result))
    tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    print(f"  Tables : {[t[0] for t in tables]}")

    for (table_name,) in tables:
        count = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]  # noqa: S608
        cols  = [r[1] for r in conn.execute(f"PRAGMA table_info({table_name})").fetchall()]
        print(f"\n  [{table_name}] — {count} lignes, colonnes : {cols}")

    # Requête directe de vérification
    print("\n  Requête test : 3 sinistres avec le plus gros montant réclamé")
    rows = conn.execute(
        "SELECT id_sinistre, type_garantie, montant_reclame "
        "FROM sinistres ORDER BY montant_reclame DESC LIMIT 3"
    ).fetchall()
    for row in rows:
        print(f"    {row}")
    conn.close()


# ─────────────────────────────────────────────────────────────
# 5. Retrieval — Filtrage progressif
# ─────────────────────────────────────────────────────────────
def demo_retrieval():
    header("5. Retrieval — Filtrage progressif (TODO-023)")
    from docpipeline.parsing.pdf.extractor import extract_text_dataframe
    from docpipeline.retrieval.retriever import retrieve

    print(f"Fichier source : {PDF_FILE.name}")

    df = extract_text_dataframe(PDF_FILE)
    print(f"  DataFrame complet : {len(df)} lignes\n")

    queries = ["franchise garantie", "accident individuel IA", "exclusion sinistre"]
    for query in queries:
        result = retrieve(df, query, top_k=3)
        print(f"  Query : \"{query}\" → {len(result)} résultats")
        for _, row in result.iterrows():
            print(f"    [p{int(row['page'])}] {row['text'][:70]}")
        print()


# ─────────────────────────────────────────────────────────────
# 6. Glossaire — Détection termes métier
# ─────────────────────────────────────────────────────────────
def demo_glossary():
    header("6. Glossaire métier — Détection et décision (TODO-013/014/015)")
    from docpipeline.translation.glossary import (
        Glossary, GlossaryEntry, detect_business_terms, decide_translate_or_keep,
    )

    glossary = Glossary([
        GlossaryEntry("IA",  "fr", {"en": ["Individual Accident"]},    "insurance"),
        GlossaryEntry("BI",  "fr", {"en": ["Business Interruption"]},  "insurance"),
        GlossaryEntry("RC",  "fr", {"en": ["Civil Liability"]},        "insurance"),
        GlossaryEntry("DM",  "fr", {"en": ["Property Damage"]},        "insurance"),
        GlossaryEntry("SLA", "en", {},                                 "tech", keep_as_is=True),
    ])

    # Sauvegarder le glossaire
    glossary_path = FIXTURES / "glossaire.json"
    glossary.to_json(glossary_path)
    print(f"  Glossaire sauvegardé : {glossary_path.name} ({len(glossary)} entrées)\n")

    text = (
        "La garantie IA couvre les accidents individuels. "
        "La garantie BI s'applique en cas d'interruption d'activité. "
        "Le SLA de traitement est de 48 heures."
    )
    print(f"  Texte analysé :\n  \"{text}\"\n")

    terms = detect_business_terms(text, glossary)
    print(f"  Termes détectés ({len(terms)}) :")
    for t in terms:
        print(f"    [{t.start}:{t.end}] \"{t.term}\" → candidats EN : {t.candidates}")

    print(f"\n  Décisions conserver/traduire :")
    for term in ["IA", "SLA", "the contract", "franchise"]:
        dec = decide_translate_or_keep(term, glossary=glossary, target_language="en")
        print(f"    \"{term}\" → {dec.action} ({dec.reason})")


# ─────────────────────────────────────────────────────────────
# 7. Image — Décision de traitement (heuristique)
# ─────────────────────────────────────────────────────────────
def demo_image_decision():
    header("7. Images — Décision de traitement LLM (TODO-007)")
    from PIL import Image
    import io
    from docpipeline.parsing.pdf.extractor import should_process_image

    test_cases = {
        "Icône 16×16 (trop petite)": Image.new("RGB", (16, 16), color=(200, 200, 200)),
        "Couleur uniforme (décorative)": Image.new("RGB", (200, 200), color=(240, 240, 240)),
        "Image complexe (schéma)": _make_complex_image(),
    }

    for label, img in test_cases.items():
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        decision = should_process_image(buf.getvalue())
        status = "✓ À traiter" if decision.should_process else "✗ Ignorer"
        print(f"  {status}  {label} — raison : {decision.reason}")


def _make_complex_image():
    """Crée une image avec du contraste (simule un schéma)."""
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (300, 200), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    for i in range(0, 300, 20):
        draw.line([(i, 0), (i, 200)], fill=(0, 0, 0), width=1)
    for j in range(0, 200, 20):
        draw.line([(0, j), (300, j)], fill=(0, 0, 0), width=1)
    draw.rectangle([50, 50, 250, 150], outline=(255, 0, 0), width=3)
    return img


# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────
DEMOS = {
    "1": ("PDF — Classification",         demo_pdf_classifier),
    "2": ("PDF — Extraction texte",        demo_pdf_extractor),
    "3": ("Word — Parsing natif",          demo_word_parser),
    "4": ("Excel — Ingestion SQLite",      demo_excel_ingester),
    "5": ("Retrieval — Filtrage",          demo_retrieval),
    "6": ("Glossaire — Termes métier",     demo_glossary),
    "7": ("Images — Décision traitement",  demo_image_decision),
}

if __name__ == "__main__":
    print("\ndocpipeline — Démonstration avec fichiers réels")
    print(f"Fixtures : {FIXTURES}\n")

    if len(sys.argv) > 1:
        # python demo.py 3   → exécute seulement la démo 3
        keys = sys.argv[1:]
    else:
        # Sans argument → tout exécuter
        keys = list(DEMOS.keys())

    for key in keys:
        if key not in DEMOS:
            print(f"  [ERREUR] Démo '{key}' inconnue. Choix : {list(DEMOS.keys())}")
            continue
        label, fn = DEMOS[key]
        try:
            fn()
        except Exception as exc:
            print(f"\n  [ERREUR dans {label}] {exc}")
            import traceback; traceback.print_exc()

    print(f"\n{SEP}")
    print("  Démonstrations terminées.")
    print(SEP)
