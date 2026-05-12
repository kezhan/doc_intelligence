"""
build_document.py — Reconstruire un .pptx à partir d'un runs_df modifié.

Symétrique de `parsing/pptx/parse_pptx.py`. Step 2 du build order Tome 2
translation (cf. CLAUDE_tome2_translation.md §Step 2) :

    extract  : parse_pptx(source)             → runs_df avec span_id stable
    modify   : on remplace seulement le 'text' de chaque run par le texte
               traduit (jamais run-by-run translation, c'est paragraph-level
               translate-then-redistribute via generation/translation/distribute.py)
    rebuild  : build_pptx_document(translated_runs_df, source, output)
               → ouvre source comme template, walk slides/shapes/paragraphs/runs,
                 remplace .text par span_id, save

Le `span_id` (format `pp_<slide>_<shape>_<para>_<run>`) est la clé stable :
matching par span_id, pas par contenu textuel — robuste aux textes dupliqués.

Smoke test (round-trip identité) :
    runs_df = parse_pptx(source)['runs_df']
    build_pptx_document(runs_df, source, out)
    # output.pptx visuellement identique au source

Aucun LLM (règle CLAUDE.md : LLM réservé à translation/summarization/Excel
SQL agent ; le rendering est pure manipulation python-pptx).

Limitations connues :
  - Tables : les cells de tables ne sont pas traitées dans cette première
    version (les runs PPTX standard sont OK ; les cells de tables ont leur
    propre text_frame qui demande un span_id séparé). À ajouter en follow-up.
  - Speaker notes : pas reconstruites pour l'instant.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from pptx import Presentation


def build_pptx_document(
    translated_runs_df: pd.DataFrame,
    source_path,
    output_path,
) -> dict:
    """
    Reconstruit un .pptx en remplaçant le texte de certains runs, en
    préservant tous les styles d'origine (font, size, bold, italic, color).

    Args:
        translated_runs_df : DataFrame avec colonnes 'span_id' et 'text'.
                              Les runs non listés gardent leur texte original.
                              Format span_id : "pp_<slide>_<shape>_<para>_<run>".
        source_path        : chemin du .pptx source (utilisé comme template)
        output_path        : chemin du .pptx de sortie

    Returns:
        dict {output_path, runs_replaced, runs_skipped, runs_unchanged, warnings}

    Le matching se fait par `span_id` (pas par texte) → robuste aux textes
    dupliqués.
    """
    source_path = Path(source_path)
    output_path = Path(output_path)

    # Construire le mapping span_id → nouveau texte (depuis le DataFrame)
    if "span_id" not in translated_runs_df.columns or "text" not in translated_runs_df.columns:
        raise ValueError("translated_runs_df doit contenir les colonnes 'span_id' et 'text'.")
    runs_by_span_id: dict[str, str] = {
        row["span_id"]: row["text"]
        for _, row in translated_runs_df.iterrows()
    }

    prs = Presentation(str(source_path))

    replaced = 0
    unchanged = 0
    skipped: list[str] = []
    warnings: list[str] = []

    for slide_idx, slide in enumerate(prs.slides):
        for shape_idx, shape in enumerate(slide.shapes):
            if not getattr(shape, "has_text_frame", False):
                continue
            try:
                tf = shape.text_frame
            except Exception as e:
                warnings.append(f"slide {slide_idx} shape {shape_idx} : "
                                f"text_frame inaccessible ({e})")
                continue

            for para_idx, para in enumerate(tf.paragraphs):
                for run_idx, run in enumerate(para.runs):
                    span_id = f"pp_{slide_idx}_{shape_idx}_{para_idx}_{run_idx}"
                    if span_id in runs_by_span_id:
                        new_text = runs_by_span_id[span_id]
                        if new_text != run.text:
                            run.text = new_text
                            replaced += 1
                        else:
                            unchanged += 1
                    else:
                        skipped.append(span_id)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(output_path))

    return {
        "output_path":     output_path,
        "runs_replaced":   replaced,
        "runs_unchanged":  unchanged,
        "runs_skipped":    len(skipped),
        "warnings":        warnings,
    }


# ╔════════════════════════════════════════════════════════════════════════════╗
# ║ CLI minimal                                                                ║
# ╚════════════════════════════════════════════════════════════════════════════╝

if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) != 3:
        print("Usage: python build_document.py <source.pptx> <output.pptx>", file=sys.stderr)
        print("       (round-trip identité : reconstruit source à output sans modif)", file=sys.stderr)
        sys.exit(1)

    src = Path(sys.argv[1])
    out = Path(sys.argv[2])

    # Round-trip identité : on parse, on passe le runs_df tel quel
    from docpipeline.parsing.pptx.parse_pptx import parse_pptx
    runs_df = parse_pptx(src)["runs_df"]
    result = build_pptx_document(runs_df, src, out)
    print(json.dumps({k: str(v) if isinstance(v, Path) else v
                      for k, v in result.items()}, indent=2, ensure_ascii=False))
