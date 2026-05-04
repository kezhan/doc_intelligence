"""
TextConverter — Conversion PDF natif (Word) vers DOCX via pdf2docx.

Porté depuis https://github.com/CHRISTMardochee/pdf2word
Utilisé pour les PDFs de catégorie WORD_NATIVE où le texte est natif
et la structure paragraphe/style est préservable fidèlement.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class TextConverter:
    """
    Convertisseur pour PDFs texte natifs (générés depuis Word/LibreOffice).

    Utilise pdf2docx comme moteur, avec des paramètres ajustés pour
    minimiser les pertes sur les layouts complexes.
    """

    # Paramètres pdf2docx optimisés (évitent la perte de texte sur layouts denses)
    _KWARGS = {
        "connected_border_tolerance": 2.0,
        "line_overlap_threshold":     0.8,
        "line_margin_weight":         2.0,
        "word_margin_weight":         2.0,
        "clip_image_res_ratio":       2.0,
    }

    def convert(
        self,
        pdf_path: str | Path,
        docx_path: str | Path,
        pages: list[int] | None = None,
    ) -> str:
        """
        Convertir un PDF natif en DOCX.

        Input  : chemin PDF + chemin DOCX de sortie
        Output : chemin DOCX généré
        """
        try:
            from pdf2docx import Converter as Pdf2DocxConverter
        except ImportError as exc:
            raise ImportError(
                "pdf2docx requis pour le TextConverter. "
                "Installer : pip install pdf2docx"
            ) from exc

        pdf_path  = str(pdf_path)
        docx_path = str(docx_path)
        logger.info("TextConverter : %s -> %s", pdf_path, docx_path)

        cv = Pdf2DocxConverter(pdf_path)
        try:
            if pages is not None:
                cv.convert(docx_path, pages=pages, **self._KWARGS)
            else:
                cv.convert(docx_path, **self._KWARGS)
            logger.info("TextConverter terminé : %s", docx_path)
        except Exception as exc:
            logger.error("TextConverter échoué : %s", exc)
            raise
        finally:
            cv.close()

        return docx_path
