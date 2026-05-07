"""Synthèse du bench parse_pdf — affiche les distributions et les erreurs."""

import sys
from pathlib import Path

import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO_ROOT = Path(__file__).resolve().parent.parent
df = pd.read_csv(REPO_ROOT / "bench_parse_pdf_results_js.csv")

print(f"Total PDFs : {len(df)}")
print(f"Total pages : {int(df['n_pages'].sum())}")
print(f"Pages needing OCR : {int(df['pages_needing_ocr'].sum())}")
print(f"Temps total : {df['parse_seconds'].sum():.1f}s ({df['parse_seconds'].sum()/60:.1f} min)")

errors = df[df["error"].fillna("").astype(str).str.strip() != ""]
print(f"\n=== Erreurs : {len(errors)}/{len(df)} ===")
if not errors.empty:
    print(errors[["path", "error"]].to_string(index=False))

print("\n=== Distribution content_type ===")
print(df["content_type"].fillna("(error)").value_counts().to_string())

print("\n=== Distribution recommended_strategy ===")
print(df["recommended_strategy"].fillna("(error)").value_counts().to_string())

print("\n=== Distribution source_tool (top 15) ===")
print(df["source_tool"].fillna("(error)").value_counts().head(15).to_string())

print("\n=== Distribution source_category ===")
print(df["source_category"].fillna("(error)").value_counts().to_string())

print("\n=== Top 10 plus lents ===")
top_slow = df.nlargest(10, "parse_seconds")[["filename", "n_pages", "parse_seconds"]]
print(top_slow.to_string(index=False))

print("\n=== Par corpus ===")
by_corpus = df.groupby("corpus").agg(
    n_pdfs=("path", "count"),
    n_pages_total=("n_pages", "sum"),
    avg_seconds=("parse_seconds", "mean"),
).round(2)
print(by_corpus.to_string())
