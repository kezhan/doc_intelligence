"""Generates the 3 .excalidraw source files for docs/06_question_layer.md.

Run :
    python docs/diagrams/_build_excalidraw.py

Output (overwrites if exists) :
    docs/diagrams/01_pipeline.excalidraw
    docs/diagrams/02_architecture.excalidraw
    docs/diagrams/03_word_vs_pdf.excalidraw

Edition workflow
----------------

1. Visual edit (recommended) — open the .excalidraw file in VS Code with the
   `pomdtr.excalidraw-editor` extension. Drag boxes, edit text in place,
   export to SVG via the toolbar (top-right → Export → SVG).

2. JSON edit — the .excalidraw file is plain JSON. Each element has clear
   fields (`text`, `x`, `y`, `width`, `height`, `backgroundColor`,
   `strokeColor`). Edit, save, the visual editor reflects the change live.

3. Re-generate — edit this script (move boxes, change labels), re-run.
   ⚠ This overwrites visual edits made directly to the .excalidraw files.

The script is idempotent : same input → same output (deterministic seeds).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


# ── Excalidraw building blocks ──────────────────────────────────────────────

VIRGIL = 1   # Hand-drawn font (Excalidraw's signature)


def _seed(key: str) -> int:
    return int(hashlib.md5(key.encode()).hexdigest()[:8], 16)


def _id(key: str) -> str:
    return hashlib.md5(key.encode()).hexdigest()[:21]


class Doc:
    """Minimal Excalidraw document builder."""

    def __init__(self) -> None:
        self.elts: list[dict[str, Any]] = []

    def _base(self, type_: str, key: str, x: float, y: float, w: float, h: float,
              fill: str = "transparent", stroke: str = "#1e1e1e",
              fill_style: str = "solid") -> dict[str, Any]:
        e: dict[str, Any] = {
            "type": type_,
            "version": 1,
            "versionNonce": _seed(key + "v"),
            "isDeleted": False,
            "id": _id(key),
            "fillStyle": fill_style,
            "strokeWidth": 2,
            "strokeStyle": "solid",
            "roughness": 1,
            "opacity": 100,
            "angle": 0,
            "x": x,
            "y": y,
            "width": w,
            "height": h,
            "strokeColor": stroke,
            "backgroundColor": fill,
            "seed": _seed(key),
            "groupIds": [],
            "frameId": None,
            "boundElements": [],
            "updated": 1,
            "link": None,
            "locked": False,
        }
        if type_ == "rectangle":
            e["roundness"] = {"type": 3}
        elif type_ in ("diamond", "ellipse"):
            e["roundness"] = {"type": 2}
        else:
            e["roundness"] = None
        return e

    def box(self, key: str, label: str, x: float, y: float, w: float, h: float,
            fill: str = "transparent", stroke: str = "#1e1e1e", fs: int = 16,
            fill_style: str = "solid") -> dict[str, Any]:
        rect = self._base("rectangle", key, x, y, w, h, fill=fill, stroke=stroke,
                          fill_style=fill_style)
        if label:
            t = self._bound_text(key + "_t", rect, label, fs=fs)
            rect["boundElements"].append({"id": t["id"], "type": "text"})
            self.elts.extend([rect, t])
        else:
            self.elts.append(rect)
        return rect

    def diamond(self, key: str, label: str, cx: float, cy: float, w: float, h: float,
                fill: str = "transparent", stroke: str = "#1e1e1e",
                fs: int = 14) -> dict[str, Any]:
        d = self._base("diamond", key, cx - w / 2, cy - h / 2, w, h,
                       fill=fill, stroke=stroke)
        if label:
            t = self._bound_text(key + "_t", d, label, fs=fs)
            d["boundElements"].append({"id": t["id"], "type": "text"})
            self.elts.extend([d, t])
        else:
            self.elts.append(d)
        return d

    def text(self, key: str, txt: str, x: float, y: float, fs: int = 14,
             color: str = "#1e1e1e", align: str = "left") -> dict[str, Any]:
        n_lines = txt.count("\n") + 1
        approx_w = max(len(line) for line in txt.split("\n")) * fs * 0.55
        e = self._base("text", key, x, y, approx_w, fs * 1.25 * n_lines,
                       stroke=color)
        e.update({
            "fontSize": fs,
            "fontFamily": VIRGIL,
            "text": txt,
            "textAlign": align,
            "verticalAlign": "top",
            "containerId": None,
            "originalText": txt,
            "lineHeight": 1.25,
            "autoResize": True,
        })
        self.elts.append(e)
        return e

    def _bound_text(self, key: str, container: dict[str, Any], text: str,
                    fs: int = 16) -> dict[str, Any]:
        cx = container["x"] + container["width"] / 2
        cy = container["y"] + container["height"] / 2
        e = self._base("text", key, cx - 50, cy - fs / 2, 100, fs * 1.25)
        e.update({
            "fontSize": fs,
            "fontFamily": VIRGIL,
            "text": text,
            "textAlign": "center",
            "verticalAlign": "middle",
            "containerId": container["id"],
            "originalText": text,
            "lineHeight": 1.25,
            "autoResize": True,
        })
        return e

    def arrow(self, key: str, src: dict[str, Any], dst: dict[str, Any],
              side: str = "auto", label: str | None = None) -> dict[str, Any]:
        """Bound arrow from src to dst. `side` = 'down' | 'right' | 'auto'."""
        if side == "auto":
            # Decide based on relative position
            src_cx = src["x"] + src["width"] / 2
            src_cy = src["y"] + src["height"] / 2
            dst_cx = dst["x"] + dst["width"] / 2
            dst_cy = dst["y"] + dst["height"] / 2
            side = "down" if abs(dst_cy - src_cy) > abs(dst_cx - src_cx) else "right"

        if side == "down":
            sx = src["x"] + src["width"] / 2
            sy = src["y"] + src["height"]
            ex = dst["x"] + dst["width"] / 2
            ey = dst["y"]
        elif side == "right":
            sx = src["x"] + src["width"]
            sy = src["y"] + src["height"] / 2
            ex = dst["x"]
            ey = dst["y"] + dst["height"] / 2
        elif side == "left":
            sx = src["x"]
            sy = src["y"] + src["height"] / 2
            ex = dst["x"] + dst["width"]
            ey = dst["y"] + dst["height"] / 2
        else:  # up
            sx = src["x"] + src["width"] / 2
            sy = src["y"]
            ex = dst["x"] + dst["width"] / 2
            ey = dst["y"] + dst["height"]

        a = self._base("arrow", key, sx, sy, ex - sx, ey - sy)
        a["roundness"] = {"type": 2}
        a["startBinding"] = {"elementId": src["id"], "focus": 0, "gap": 8,
                             "fixedPoint": None}
        a["endBinding"] = {"elementId": dst["id"], "focus": 0, "gap": 8,
                           "fixedPoint": None}
        a["lastCommittedPoint"] = None
        a["startArrowhead"] = None
        a["endArrowhead"] = "arrow"
        a["points"] = [[0, 0], [ex - sx, ey - sy]]

        src["boundElements"].append({"id": a["id"], "type": "arrow"})
        dst["boundElements"].append({"id": a["id"], "type": "arrow"})
        self.elts.append(a)

        if label:
            # Bound text on arrow (Excalidraw places it mid-arrow)
            mid_x = (sx + ex) / 2
            mid_y = (sy + ey) / 2
            fs = 13
            t = self._base("text", key + "_lbl", mid_x - 20, mid_y - fs / 2, 40,
                           fs * 1.25)
            t.update({
                "fontSize": fs,
                "fontFamily": VIRGIL,
                "text": label,
                "textAlign": "center",
                "verticalAlign": "middle",
                "containerId": a["id"],
                "originalText": label,
                "lineHeight": 1.25,
                "autoResize": True,
            })
            a["boundElements"].append({"id": t["id"], "type": "text"})
            self.elts.append(t)

        return a

    def save(self, path: Path) -> None:
        path.write_text(
            json.dumps({
                "type": "excalidraw",
                "version": 2,
                "source": "https://excalidraw.com",
                "elements": self.elts,
                "appState": {
                    "gridSize": None,
                    "viewBackgroundColor": "#ffffff",
                },
                "files": {},
            }, indent=2),
            encoding="utf-8",
        )


# ── Color palette (kept consistent across the 3 diagrams) ──────────────────

BLUE_FILL,  BLUE_STROKE  = "#dbeafe", "#1d4ed8"
GREEN_FILL, GREEN_STROKE = "#d1fae5", "#047857"
RED_FILL,   RED_STROKE   = "#fee2e2", "#b91c1c"
YELLOW_FILL, YELLOW_STROKE = "#fef3c7", "#b45309"
PURPLE_FILL, PURPLE_STROKE = "#ede9fe", "#6d28d9"
CYAN_FILL,   CYAN_STROKE   = "#cffafe", "#0e7490"
WHITE_FILL = "#ffffff"


# ── Diagram 1 : pipeline ────────────────────────────────────────────────────

def build_pipeline() -> Doc:
    d = Doc()
    d.text("title", "understand_question — orchestration flow", 200, 20, fs=20,
           color="#0f172a")

    inp = d.box("input", "User question\n+ document_type", 240, 70, 280, 70,
                fill=BLUE_FILL, stroke=BLUE_STROKE)
    spell = d.box("spell", "spell-correct", 270, 180, 220, 50, fill=WHITE_FILL)
    diam1 = d.diamond("diam_amb", "ambiguous\nreferent?", 380, 320, 160, 100,
                      fill=YELLOW_FILL, stroke=YELLOW_STROKE)
    clarify = d.box("clarify", "return\nclarify + options", 600, 295, 160, 60,
                    fill=RED_FILL, stroke=RED_STROKE)
    classify = d.box("classify", "classify_intent", 270, 430, 220, 50,
                     fill=WHITE_FILL)
    diam2 = d.diamond("diam_cmp", "compound?", 380, 570, 140, 100,
                      fill=YELLOW_FILL, stroke=YELLOW_STROKE)
    decompose = d.box("decompose", "decompose into\nN sub-questions", 600, 545,
                      170, 60, fill=WHITE_FILL)
    one = d.box("one", "1 sub-question", 270, 690, 220, 50, fill=WHITE_FILL)
    loop = d.box("loop", "for each sub-question:\nrun active bricks", 220, 800,
                 320, 70, fill=WHITE_FILL)
    output = d.box("output", "list of dicts\n[{ retrieval, generation, _meta }, ...]",
                   200, 920, 360, 80, fill=GREEN_FILL, stroke=GREEN_STROKE)

    d.arrow("a1", inp, spell, side="down")
    d.arrow("a2", spell, diam1, side="down")
    d.arrow("a3", diam1, clarify, side="right", label="yes")
    d.arrow("a4", diam1, classify, side="down", label="no")
    d.arrow("a5", classify, diam2, side="down")
    d.arrow("a6", diam2, decompose, side="right", label="yes")
    d.arrow("a7", diam2, one, side="down", label="no")
    d.arrow("a8", one, loop, side="down")
    d.arrow("a9", decompose, loop, side="down")
    d.arrow("a10", loop, output, side="down")
    return d


# ── Diagram 2 : architecture (registry + presets) ──────────────────────────

def build_architecture() -> Doc:
    d = Doc()
    d.text("title", "Registry + presets — the shape of the system", 220, 20,
           fs=20, color="#0f172a")

    inp = d.box("input", "question\ndocument_type\nenable={...}", 30, 230, 200,
                120, fill=BLUE_FILL, stroke=BLUE_STROKE)
    uq = d.box("uq", "understand_question\nspell · clarify · classify · decompose",
               280, 250, 240, 80, fill=WHITE_FILL)
    select = d.diamond("select", "select\nactive bricks", 660, 290, 160, 100,
                       fill=YELLOW_FILL, stroke=YELLOW_STROKE)
    presets = d.box("presets", "PRESETS per doc_type\npdf  → page · section · …\nword → section · format · …\nexcel → format · disambig",
                    560, 70, 240, 110, fill=YELLOW_FILL, stroke=YELLOW_STROKE,
                    fs=13)
    override = d.box("override", "enable={...} OVERRIDE\n{\"page_hint\": False}\n{\"jurisdiction\": True}",
                     560, 430, 240, 90, fill=YELLOW_FILL, stroke=YELLOW_STROKE,
                     fs=13)
    run = d.box("run", "run each brick\nbrick.run(q, ctx)", 850, 250, 200, 80,
                fill=WHITE_FILL)
    bricks = d.box("bricks", "BRICKS REGISTRY\nrewrite (LLM)\nanchor_keywords\npage_hint  [pdf, pptx]\nsection_hint  [pdf, word, pptx]\nformat · disambiguation",
                   850, 60, 240, 170, fill=YELLOW_FILL, stroke=YELLOW_STROKE,
                   fs=13)
    out = d.box("out", "list of dicts\nretrieval { only populated }\ngeneration { only populated }\n_meta { intent, doc_type,\n        bricks_active }",
                770, 430, 280, 140, fill=GREEN_FILL, stroke=GREEN_STROKE, fs=13)

    d.arrow("a1", inp, uq, side="right")
    d.arrow("a2", uq, select, side="right")
    d.arrow("a3", presets, select, side="down")
    d.arrow("a4", override, select, side="up")
    d.arrow("a5", select, run, side="right")
    d.arrow("a6", bricks, run, side="down")
    d.arrow("a7", run, out, side="down")
    return d


# ── Diagram 3 : word vs pdf ─────────────────────────────────────────────────

def build_word_vs_pdf() -> Doc:
    d = Doc()
    d.text("title",
           "Same question, two document types — page_hint disappears on Word",
           80, 20, fs=20, color="#0f172a")

    inp = d.box("input",
                "\"What's the effective date?\nIt's usually on page 1, top-right block.\"",
                300, 70, 400, 70, fill=BLUE_FILL, stroke=BLUE_STROKE)

    # Left column : PDF
    pdf_pre = d.box("pdf_pre",
                    "preset_pdf\n[rewrite, anchor_keywords, page_hint,\nsection_hint, layout_hint, format, disambig]",
                    50, 200, 380, 90, fill=PURPLE_FILL, stroke=PURPLE_STROKE,
                    fs=13)
    pdf_run = d.box("pdf_run", "page_hint brick runs ✓", 110, 320, 260, 50,
                    fill=WHITE_FILL)
    pdf_out = d.box("pdf_out",
                    "retrieval JSON\n{\n  \"main_query\": \"What's the effective…\",\n  \"page_hint\": 1,\n  \"layout_hint\": \"header\"\n}",
                    50, 400, 380, 160, fill=GREEN_FILL, stroke=GREEN_STROKE,
                    fs=13)
    pdf_note = d.text("pdf_note", "→ retriever filters page=1 (stable)", 80, 580,
                      fs=14, color=GREEN_STROKE)

    # Right column : Word
    word_pre = d.box("word_pre",
                     "preset_word\n[rewrite, anchor_keywords,\nsection_hint, layout_hint, format, disambig]",
                     570, 200, 380, 90, fill=CYAN_FILL, stroke=CYAN_STROKE,
                     fs=13)
    word_skip = d.box("word_skip", "page_hint brick — skipped", 630, 320, 260, 50,
                      fill=YELLOW_FILL, stroke=YELLOW_STROKE)
    word_out = d.box("word_out",
                     "retrieval JSON\n{\n  \"main_query\": \"What's the effective…\",\n  \"layout_hint\": \"header\"\n}\n— no page_hint field at all",
                     570, 400, 380, 160, fill=GREEN_FILL, stroke=GREEN_STROKE,
                     fs=13)
    word_note = d.text("word_note",
                       "→ retriever sees no misleading hint", 600, 580, fs=14,
                       color=GREEN_STROKE)

    # Bottom callout
    callout = d.box("callout",
                    "One line in PRESETS[\"word\"] saved three hours of debugging.\nDomain knowledge (\"Word has no stable pages\") lives in the preset, not in the pipeline.",
                    150, 640, 700, 80, fill="#f8fafc", fs=14)

    d.arrow("a1", inp, pdf_pre, side="down")
    d.arrow("a2", inp, word_pre, side="down")
    d.arrow("a3", pdf_pre, pdf_run, side="down")
    d.arrow("a4", pdf_run, pdf_out, side="down")
    d.arrow("a5", word_pre, word_skip, side="down")
    d.arrow("a6", word_skip, word_out, side="down")
    return d


# ── Main ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    here = Path(__file__).parent
    for name, build in [
        ("01_pipeline", build_pipeline),
        ("02_architecture", build_architecture),
        ("03_word_vs_pdf", build_word_vs_pdf),
    ]:
        out = here / f"{name}.excalidraw"
        build().save(out)
        size = out.stat().st_size
        print(f"  wrote {out.name}  ({size} bytes)")
