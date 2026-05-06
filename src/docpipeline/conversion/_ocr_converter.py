"""
OCRConverter — Conversion PDF scanné vers DOCX via OCR.

Porté depuis https://github.com/CHRISTMardochee/pdf2word
Utilisé pour les PDFs de catégorie SCANNED où chaque page est une image.

Moteurs supportés :
  - tesseract  : open-source, requiert pytesseract + Tesseract installé
  - paddleocr  : plus précis sur le français, requiert paddleocr
"""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path

import fitz  # PyMuPDF
from docx import Document
from docx.shared import Pt
from PIL import Image

logger = logging.getLogger(__name__)

# Correspondance langues docpipeline → codes PaddleOCR
_PADDLE_LANG_MAP = {"fra": "fr", "eng": "en", "fra+eng": "fr", "deu": "de"}


class OCRConverter:
    """
    Convertisseur PDF scanné → DOCX via reconnaissance optique de caractères.

    Aucun LLM. Utilise Tesseract ou PaddleOCR selon la disponibilité.
    """

    def __init__(self, engine: str = "tesseract", lang: str = "fra+eng") -> None:
        """
        Args:
            engine : "tesseract" ou "paddleocr"
            lang   : code(s) de langue (ex. "fra+eng", "eng")
        """
        self.engine = engine.lower()
        self.lang   = lang

    def convert(
        self,
        pdf_path: str | Path,
        docx_path: str | Path,
        *,
        dpi: int = 300,
    ) -> str:
        """
        Convertir un PDF scanné en DOCX via OCR.

        Input  : chemin PDF (scanné) + chemin DOCX de sortie
        Output : chemin DOCX généré
        """
        pdf_path  = str(pdf_path)
        docx_path = str(docx_path)
        logger.info("OCRConverter (%s, lang=%s) : %s -> %s",
                    self.engine, self.lang, pdf_path, docx_path)

        doc     = Document()
        pdf_doc = fitz.open(pdf_path)

        try:
            for page_num in range(len(pdf_doc)):
                logger.info("OCR page %d/%d", page_num + 1, len(pdf_doc))
                page = pdf_doc[page_num]
                mat  = fitz.Matrix(dpi / 72, dpi / 72)
                pix  = page.get_pixmap(matrix=mat)

                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                    tmp_path = tmp.name
                    pix.save(tmp_path)

                try:
                    ocr_data = self._run_ocr(tmp_path)
                    self._build_page_content(doc, ocr_data)
                    if page_num < len(pdf_doc) - 1:
                        doc.add_page_break()
                finally:
                    os.unlink(tmp_path)

            doc.save(docx_path)
            logger.info("OCRConverter terminé : %s", docx_path)

        except Exception as exc:
            logger.error("OCRConverter échoué : %s", exc)
            raise
        finally:
            pdf_doc.close()

        return docx_path

    # ── Moteurs OCR ───────────────────────────────────────────────────────────

    def _run_ocr(self, image_path: str) -> list[dict]:
        if self.engine == "tesseract":
            return self._run_tesseract(image_path)
        if self.engine == "paddleocr":
            return self._run_paddleocr(image_path)
        raise ValueError(f"Moteur OCR inconnu : {self.engine!r} (choix : tesseract, paddleocr)")

    def _run_tesseract(self, image_path: str) -> list[dict]:
        try:
            import pytesseract
        except ImportError as exc:
            raise ImportError(
                "pytesseract requis. Installer : pip install pytesseract "
                "(+ Tesseract binaire sur le système)"
            ) from exc

        img  = Image.open(image_path)
        data = pytesseract.image_to_data(img, lang=self.lang,
                                         output_type=pytesseract.Output.DICT)

        results: list[dict] = []
        current_line: list[dict] = []
        cur_line_num  = -1
        cur_block_num = -1

        for i in range(len(data["text"])):
            text      = data["text"][i].strip()
            conf      = int(data["conf"][i])
            line_num  = data["line_num"][i]
            block_num = data["block_num"][i]

            if conf < 0:
                continue

            if line_num != cur_line_num or block_num != cur_block_num:
                if current_line:
                    results.append(self._merge_line(current_line))
                current_line  = []
                cur_line_num  = line_num
                cur_block_num = block_num

            if text:
                current_line.append({
                    "text":      text,
                    "bbox":      (data["left"][i], data["top"][i],
                                  data["left"][i] + data["width"][i],
                                  data["top"][i]  + data["height"][i]),
                    "confidence": conf,
                    "block_num":  block_num,
                    "line_num":   line_num,
                })

        if current_line:
            results.append(self._merge_line(current_line))

        return results

    def _run_paddleocr(self, image_path: str) -> list[dict]:
        try:
            from paddleocr import PaddleOCR
        except ImportError as exc:
            raise ImportError("paddleocr requis. Installer : pip install paddleocr") from exc

        paddle_lang = _PADDLE_LANG_MAP.get(self.lang, "fr")
        ocr         = PaddleOCR(use_angle_cls=True, lang=paddle_lang, show_log=False)
        result      = ocr.ocr(image_path, cls=True)

        results: list[dict] = []
        if result and result[0]:
            for line in result[0]:
                pts  = line[0]
                text = line[1][0]
                conf = line[1][1]
                xs   = [p[0] for p in pts]
                ys   = [p[1] for p in pts]
                results.append({
                    "text":       text,
                    "bbox":       (min(xs), min(ys), max(xs), max(ys)),
                    "confidence": conf * 100,
                    "block_num":  0,
                })

        return results

    # ── Reconstruction du contenu DOCX ────────────────────────────────────────

    def _build_page_content(self, doc: Document, ocr_data: list[dict]) -> None:
        if not ocr_data:
            return

        # Grouper par bloc, trier par position verticale
        blocks: dict[int, list] = {}
        for item in ocr_data:
            bid = item.get("block_num", 0)
            blocks.setdefault(bid, []).append(item)

        for _, lines in sorted(blocks.items(), key=lambda kv: min(i["bbox"][1] for i in kv[1])):
            lines.sort(key=lambda l: l["bbox"][1])
            text = " ".join(l["text"] for l in lines).strip()
            if text:
                para = doc.add_paragraph(text)
                for run in para.runs:
                    run.font.size = Pt(11)

    @staticmethod
    def _merge_line(words: list[dict]) -> dict:
        return {
            "text":       " ".join(w["text"] for w in words),
            "bbox":       (min(w["bbox"][0] for w in words),
                           min(w["bbox"][1] for w in words),
                           max(w["bbox"][2] for w in words),
                           max(w["bbox"][3] for w in words)),
            "confidence": sum(w["confidence"] for w in words) / len(words),
            "block_num":  words[0].get("block_num", 0),
        }
