"""Lance le bench parse_pdf en CLI (équivalent au notebook bench_parse_pdf.ipynb)."""

import sys
import time
from pathlib import Path

import pandas as pd

from docpipeline.parsing.pdf.parse_pdf import parse_pdf

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"

PDFS = sorted(DATA_DIR.rglob("*.pdf"))
print(f"Found {len(PDFS)} PDFs", flush=True)

rows = []
for i, pdf in enumerate(PDFS, 1):
    rel = pdf.relative_to(REPO_ROOT).as_posix()
    corpus = pdf.relative_to(DATA_DIR).parts[0] if pdf.is_relative_to(DATA_DIR) else ""
    print(f"[{i}/{len(PDFS)}] {rel}", flush=True)
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
            "error":                None,
        })
    except Exception as e:
        row.update({
            "parse_seconds": round(time.perf_counter() - t0, 2),
            "error": f"{type(e).__name__}: {e}",
        })
    rows.append(row)

df = pd.DataFrame(rows)
out_csv = REPO_ROOT / "bench_parse_pdf_results.csv"
df.to_csv(out_csv, index=False, encoding="utf-8")
print(f"\n>>> Saved {len(df)} rows to {out_csv.name}", flush=True)

errors = df[df["error"].notna()]
print(f"\n=== Erreurs : {len(errors)} / {len(df)} ===", flush=True)
if not errors.empty:
    print(errors[["path", "error"]].to_string(index=False), flush=True)

print("\n=== Distribution content_type ===", flush=True)
print(df["content_type"].value_counts(dropna=False).to_string(), flush=True)

print("\n=== Distribution source_tool (top 15) ===", flush=True)
print(df["source_tool"].value_counts(dropna=False).head(15).to_string(), flush=True)

print("\n=== Distribution recommended_strategy ===", flush=True)
print(df["recommended_strategy"].value_counts(dropna=False).to_string(), flush=True)

print(f"\nTotal pages : {int(df['n_pages'].sum() or 0)}", flush=True)
print(f"Pages OCR : {int(df['pages_needing_ocr'].sum() or 0)}", flush=True)
print(f"Temps total : {df['parse_seconds'].sum():.1f}s", flush=True)
