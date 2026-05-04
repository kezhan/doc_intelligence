"""
TODO-018 — Visualiseur HTML côte-à-côte original / traduction.

Génère un fichier HTML autonome (zéro JS externe) affichant les deux PDFs
en miroir, avec correspondance positionnelle cliquable : un clic sur un
fragment traduit met en surbrillance la position originale.

Aucun LLM. Pure génération HTML/CSS.
"""

from __future__ import annotations

import base64
import html
import logging
from dataclasses import dataclass
from pathlib import Path

import fitz  # PyMuPDF
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class SideBySideResult:
    output_path: Path
    page_count:  int


def render_side_by_side(
    source_pdf:        str | Path,
    translated_pdf:    str | Path,
    enriched_df:       pd.DataFrame,
    translated_spans:  dict[str, str],
    output_html:       str | Path,
    *,
    page_dpi:          int = 100,
) -> SideBySideResult:
    """
    TODO-018 — Générer un HTML interactif côte-à-côte.

    Args:
        source_pdf       : PDF original
        translated_pdf   : PDF traduit (sortie de reconstruct_pdf_translation)
        enriched_df      : DataFrame extract_full_with_style() avec positions
        translated_spans : dict {span_id: texte_traduit}
        output_html      : chemin du HTML généré
        page_dpi         : résolution rendu pages (défaut 100)
    """
    source_pdf     = Path(source_pdf)
    translated_pdf = Path(translated_pdf)
    output_html    = Path(output_html)

    src_pages = _render_pages_b64(source_pdf,     dpi=page_dpi)
    tr_pages  = _render_pages_b64(translated_pdf, dpi=page_dpi)
    n_pages   = max(len(src_pages), len(tr_pages))

    # Mapping bbox par page pour les overlays cliquables
    overlays_by_page = _build_overlays(enriched_df, translated_spans)

    html_content = _build_html(src_pages, tr_pages, overlays_by_page, n_pages)
    output_html.write_text(html_content, encoding="utf-8")
    logger.info("HTML côte-à-côte généré : %s (%d pages)", output_html, n_pages)

    return SideBySideResult(output_path=output_html, page_count=n_pages)


# ── Construction HTML ────────────────────────────────────────────────────────

def _build_html(
    src_pages: list[tuple[str, float, float]],
    tr_pages:  list[tuple[str, float, float]],
    overlays:  dict[int, list[dict]],
    n_pages:   int,
) -> str:
    pages_html = []
    for i in range(n_pages):
        src = src_pages[i] if i < len(src_pages) else ("", 0, 0)
        tr  = tr_pages[i]  if i < len(tr_pages)  else ("", 0, 0)
        page_overlays = overlays.get(i + 1, [])

        # Échelle d'affichage pour positionner les overlays
        scale = 1.0
        overlay_html = "".join(
            _overlay_html(o, scale=scale, side="left") for o in page_overlays
        )
        overlay_html_right = "".join(
            _overlay_html(o, scale=scale, side="right") for o in page_overlays
        )

        pages_html.append(f"""
<div class="page-pair" data-page="{i + 1}">
  <div class="page-label">Page {i + 1}</div>
  <div class="page-row">
    <div class="page-col">
      <div class="col-title">Original</div>
      <div class="page-wrapper" style="width:{src[1]}px;height:{src[2]}px">
        <img src="data:image/png;base64,{src[0]}" />
        {overlay_html}
      </div>
    </div>
    <div class="page-col">
      <div class="col-title">Traduction</div>
      <div class="page-wrapper" style="width:{tr[1]}px;height:{tr[2]}px">
        <img src="data:image/png;base64,{tr[0]}" />
        {overlay_html_right}
      </div>
    </div>
  </div>
</div>
""")

    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<title>Traduction côte-à-côte — docpipeline</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         background: #f4f5f7; color: #2c3e50; padding: 20px; }}
  h1 {{ font-size: 22px; margin-bottom: 4px; color: #1a73e8; }}
  .subtitle {{ font-size: 13px; color: #5f6368; margin-bottom: 20px; }}
  .page-pair {{ background: white; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.08);
                margin-bottom: 24px; padding: 16px; }}
  .page-label {{ font-weight: 600; font-size: 14px; color: #5f6368; margin-bottom: 12px;
                 text-transform: uppercase; letter-spacing: 0.5px; }}
  .page-row {{ display: flex; gap: 20px; justify-content: center; }}
  .page-col {{ flex: 1; max-width: 50%; }}
  .col-title {{ font-size: 13px; font-weight: 600; color: #1a73e8;
                margin-bottom: 8px; text-align: center; }}
  .page-wrapper {{ position: relative; margin: 0 auto; border: 1px solid #dadce0;
                   max-width: 100%; }}
  .page-wrapper img {{ display: block; width: 100%; height: auto; }}
  .overlay {{ position: absolute; cursor: pointer; border-radius: 2px;
              transition: background 0.15s; pointer-events: auto; }}
  .overlay:hover {{ background: rgba(26, 115, 232, 0.18); outline: 2px solid #1a73e8; }}
  .overlay.highlighted {{ background: rgba(255, 193, 7, 0.45);
                          outline: 2px solid #ffc107; }}
  .footer {{ text-align: center; font-size: 12px; color: #5f6368; margin-top: 20px; }}
</style>
</head>
<body>
  <h1>📄 Comparaison Original / Traduction</h1>
  <p class="subtitle">Cliquez sur un fragment pour voir sa correspondance dans l'autre version.</p>
  {''.join(pages_html)}
  <p class="footer">Généré par <strong>docpipeline</strong> — TODO-018</p>

<script>
  document.querySelectorAll('.overlay').forEach(el => {{
    el.addEventListener('click', () => {{
      const id = el.dataset.spanId;
      document.querySelectorAll('.overlay.highlighted').forEach(o => o.classList.remove('highlighted'));
      document.querySelectorAll(`[data-span-id="${{id}}"]`).forEach(o => o.classList.add('highlighted'));
    }});
  }});
</script>
</body>
</html>
"""


def _overlay_html(overlay: dict, *, scale: float, side: str) -> str:
    title = html.escape(overlay["text"][:200])
    return (
        f'<div class="overlay" data-span-id="{overlay["span_id"]}" '
        f'style="left:{overlay["x0"] * scale}px; top:{overlay["y0"] * scale}px; '
        f'width:{(overlay["x1"] - overlay["x0"]) * scale}px; '
        f'height:{(overlay["y1"] - overlay["y0"]) * scale}px;" '
        f'title="{title}"></div>'
    )


# ── Rendu pages ──────────────────────────────────────────────────────────────

def _render_pages_b64(pdf_path: Path, *, dpi: int) -> list[tuple[str, float, float]]:
    """Retourne [(image_b64, width_px, height_px), ...]"""
    doc      = fitz.open(str(pdf_path))
    pages    = []
    zoom     = dpi / 72.0
    matrix   = fitz.Matrix(zoom, zoom)
    try:
        for page in doc:
            pix = page.get_pixmap(matrix=matrix)
            b64 = base64.b64encode(pix.tobytes("png")).decode("ascii")
            pages.append((b64, pix.width, pix.height))
    finally:
        doc.close()
    return pages


def _build_overlays(
    enriched_df:      pd.DataFrame,
    translated_spans: dict[str, str],
) -> dict[int, list[dict]]:
    by_page: dict[int, list[dict]] = {}
    for _, row in enriched_df.iterrows():
        span_id = row["span_id"]
        if span_id not in translated_spans:
            continue
        page_num = int(row["page"])
        by_page.setdefault(page_num, []).append({
            "span_id": span_id,
            "text":    translated_spans[span_id],
            "x0": float(row["x0"]),
            "y0": float(row["y0"]),
            "x1": float(row["x1"]),
            "y1": float(row["y1"]),
        })
    return by_page
