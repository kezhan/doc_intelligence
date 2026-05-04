"""
MSWordConverter — Conversion PDF vers DOCX via le moteur natif Microsoft Word.

Porté depuis https://github.com/CHRISTMardochee/pdf2word et personnalisé.

C'est la **meilleure qualité disponible sans Adobe** pour les PDFs
complexes type brochure InDesign : Word utilise son propre moteur "PDF Reflow"
qui produit un DOCX entièrement éditable avec une fidélité de mise en page
remarquable (souvent supérieure à pdf2docx ou LibreOffice).

Prérequis (Windows uniquement) :
  - MS Office installé (Word ≥ 2013)
  - pip install pywin32
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


class MSWordConverter:
    """
    Convertisseur via Word COM. Édition complète + fidélité layout élevée.

    Word ouvre le PDF, applique son moteur de reflow interne, puis enregistre
    en .docx. Le résultat est intégralement éditable (texte, tableaux, images).
    """

    def __init__(self) -> None:
        if sys.platform != "win32":
            raise NotImplementedError(
                "MSWordConverter ne fonctionne que sur Windows. "
                "Sur Linux/macOS, utilisez LibreOfficeConverter."
            )

        try:
            import win32com.client  # noqa: F401
        except ImportError as exc:
            raise ImportError(
                "MSWordConverter nécessite pywin32. "
                "Installer : pip install pywin32"
            ) from exc

    def convert(
        self,
        input_pdf:    str | Path,
        output_docx:  str | Path,
        pages:        list[int] | None = None,
    ) -> str:
        """
        Ouvrir le PDF dans Word et l'enregistrer en .docx.

        Input  : chemin PDF + chemin DOCX de sortie
        Output : chemin DOCX généré
        """
        if pages is not None:
            logger.warning("MSWordConverter ignore l'argument 'pages' "
                           "(Word convertit toujours le document complet).")

        input_pdf  = os.path.abspath(str(input_pdf))
        output_pdf = os.path.abspath(str(output_docx))

        if not os.path.isfile(input_pdf):
            raise FileNotFoundError(f"PDF introuvable : {input_pdf}")

        import win32com.client
        logger.info("MSWordConverter : %s -> %s", input_pdf, output_pdf)

        word = None
        try:
            # DispatchEx = nouvelle instance, n'interfère pas avec Word ouvert
            word = win32com.client.DispatchEx("Word.Application")
            word.Visible        = False
            word.DisplayAlerts  = 0  # wdAlertsNone

            doc = word.Documents.Open(
                FileName            = input_pdf,
                ConfirmConversions  = False,
                ReadOnly            = True,
                AddToRecentFiles    = False,
            )
            doc.SaveAs2(FileName=output_pdf, FileFormat=16)  # 16 = wdFormatXMLDocument
            doc.Close(SaveChanges=0)
            logger.info("MSWordConverter terminé : %s", output_pdf)
            return output_pdf

        except Exception as exc:
            err = str(exc)
            if "Invalid class string" in err or "-2147221005" in err:
                raise RuntimeError(
                    "Microsoft Word ne semble pas installé sur ce système. "
                    "Installez MS Office ou utilisez un autre moteur "
                    "(--engine libreoffice ou --engine smart)."
                ) from exc
            raise RuntimeError(f"Erreur MS Word COM : {exc}") from exc

        finally:
            if word is not None:
                try:
                    word.Quit()
                except Exception as quit_err:
                    logger.warning("Impossible de fermer Word : %s", quit_err)
