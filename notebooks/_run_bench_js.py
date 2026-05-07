"""Lance le bench parse_pdf en CLI, écrit le CSV au fil de l'eau (1 ligne par PDF)."""

import csv
import sys
import time
from pathlib import Path

# Boilerplate Windows : forcer stdout/stderr en UTF-8 (cf. CLAUDE.md du repo)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from docpipeline.parsing.pdf.parse_pdf import parse_pdf

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
OUT_CSV = REPO_ROOT / "bench_parse_pdf_results_js.csv"

FIELDS = [
    "path", "corpus", "filename", "n_pages",
    "source_tool", "source_category", "content_type", "recommended_strategy",
    "n_native", "n_scanned", "n_mixed", "n_empty",
    "pages_needing_ocr", "ocr_quality", "parse_seconds", "error",
]

PDFS = sorted(DATA_DIR.rglob("*.pdf"))
print(f"Found {len(PDFS)} PDFs", flush=True)
print(f"Output : {OUT_CSV.relative_to(REPO_ROOT).as_posix()}", flush=True)

with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
    writer.writeheader()
    f.flush()

    for i, pdf in enumerate(PDFS, 1):
        rel = pdf.relative_to(REPO_ROOT).as_posix()
        corpus = pdf.relative_to(DATA_DIR).parts[0] if pdf.is_relative_to(DATA_DIR) else ""
        size_mb = round(pdf.stat().st_size / (1 << 20), 1)
        print(f"[{i:>3}/{len(PDFS)}] ({size_mb:>6.1f}MB) {rel}", flush=True)

        row = {"path": rel, "corpus": corpus, "filename": pdf.name}
        t0 = time.perf_counter()
        try:
            result = parse_pdf(pdf)
            s = result["doc_summary"]
            ptc = s.get("page_type_counts", {})
            row.update({
                "n_pages":              s["n_pages"],
                "source_tool":          s["source_tool"],
                "source_category":      s["source_category"],
                "content_type":         s["content_type"],
                "recommended_strategy": s["recommended_strategy"],
                "n_native":             ptc.get("native", 0) + ptc.get("native_with_image", 0),
                "n_scanned":            ptc.get("scanned", 0) + ptc.get("scanned_ocr_good", 0) + ptc.get("scanned_ocr_bad", 0),
                "n_mixed":              ptc.get("mixed", 0),
                "n_empty":              ptc.get("empty", 0),
                "pages_needing_ocr":    len(s.get("pages_needing_ocr", [])),
                "ocr_quality":          s.get("ocr_quality"),
                "parse_seconds":        round(time.perf_counter() - t0, 2),
                "error":                "",
            })
        except Exception as e:
            row.update({
                "parse_seconds": round(time.perf_counter() - t0, 2),
                "error": f"{type(e).__name__}: {e}",
            })

        writer.writerow(row)
        f.flush()
        # Petit récap par PDF (visible immédiatement)
        if row.get("error"):
            print(f"           FAIL {row['error']}", flush=True)
        else:
            print(f"           OK   {row['n_pages']:>3}p / {row['source_tool']:<25} / {row['content_type']:<18} / {row['parse_seconds']}s", flush=True)

print(f"\n>>> Done. CSV : {OUT_CSV.name}", flush=True)
