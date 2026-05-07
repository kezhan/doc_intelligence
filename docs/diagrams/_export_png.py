"""Convert all .svg files in this folder to .png at 2x scale.

Run :
    python docs/diagrams/_export_png.py

Used after re-exporting a `.svg` from Excalidraw, to refresh the `.png` consumed
by the markdown article.

Why PNG and not SVG in the .md ?
  - GitHub renders SVG fine, but Medium / many CMS don't accept SVG.
  - PNG is the safest universal format for upload.
  - SVG remains the source of truth (re-runnable to higher res if needed).

Why 2x ?
  - The SVG viewBox dimensions are sized for ~700-1000 px wide rendering.
  - 2x gives a crisp result on Retina displays and survives Medium's
    image processing without visible aliasing.
"""

from __future__ import annotations

from pathlib import Path

import resvg_py

ZOOM = 2  # integer scale factor


def main() -> None:
    here = Path(__file__).parent
    for svg in sorted(here.glob("*.svg")):
        png_path = svg.with_suffix(".png")
        svg_text = svg.read_text(encoding="utf-8")
        png_bytes = resvg_py.svg_to_bytes(svg_string=svg_text, zoom=ZOOM)
        png_path.write_bytes(bytes(png_bytes))
        size_kb = len(png_bytes) // 1024
        print(f"  {svg.name:30s} -> {png_path.name}  ({size_kb} KB)")


if __name__ == "__main__":
    main()
