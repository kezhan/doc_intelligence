"""
LibreOfficeConverter — Conversion PDF vers DOCX via LibreOffice headless.

Porté depuis https://github.com/CHRISTMardochee/pdf2word et personnalisé.

Meilleure alternative open-source au moteur Word PDF Reflow.
Multi-plateforme (Linux, macOS, Windows). DOCX entièrement éditable.

Prérequis : LibreOffice installé sur le système.
  Ubuntu  : sudo apt install libreoffice-writer
  macOS   : brew install --cask libreoffice
  Windows : https://www.libreoffice.org/download/
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)

# Emplacements communs du binaire LibreOffice
_BINARY_CANDIDATES = [
    "libreoffice", "soffice",
    "/usr/bin/libreoffice", "/usr/bin/soffice",
    "/Applications/LibreOffice.app/Contents/MacOS/soffice",
    r"C:\Program Files\LibreOffice\program\soffice.exe",
    r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
]


def _find_libreoffice() -> str | None:
    for path in _BINARY_CANDIDATES:
        if shutil.which(path) or os.path.isfile(path):
            return path
    return None


class LibreOfficeConverter:
    """
    Convertisseur PDF → DOCX via LibreOffice en mode headless.

    Qualité bonne pour PDFs majoritairement textuels.
    Layouts complexes (multi-colonnes, brochures) : différences possibles
    mais le résultat reste éditable.
    """

    def __init__(self, soffice_path: str | None = None, timeout: int = 300) -> None:
        """
        Args:
            soffice_path : chemin explicite vers le binaire (sinon auto-détection)
            timeout      : timeout en secondes (défaut 300)
        """
        self.soffice_path = soffice_path or _find_libreoffice()
        self.timeout      = timeout

        if not self.soffice_path:
            raise FileNotFoundError(
                "LibreOffice n'est pas installé. Installation :\n"
                "  Ubuntu/Debian : sudo apt install libreoffice-writer\n"
                "  macOS         : brew install --cask libreoffice\n"
                "  Windows       : https://www.libreoffice.org/download/"
            )

    def convert(
        self,
        input_pdf:    str | Path,
        output_docx:  str | Path,
        pages:        list[int] | None = None,
    ) -> str:
        """
        Convertir un PDF en DOCX via LibreOffice headless.

        Input  : chemin PDF + chemin DOCX
        Output : chemin DOCX généré
        """
        if pages is not None:
            logger.warning("LibreOfficeConverter ignore 'pages'.")

        input_pdf  = os.path.abspath(str(input_pdf))
        output_pdf = os.path.abspath(str(output_docx))

        if not os.path.isfile(input_pdf):
            raise FileNotFoundError(f"PDF introuvable : {input_pdf}")

        unique_id   = uuid.uuid4().hex[:8]
        tmp_outdir  = tempfile.mkdtemp(prefix=f"lo_out_{unique_id}_")
        tmp_profile = tempfile.mkdtemp(prefix=f"lo_prof_{unique_id}_")

        try:
            cmd = [
                self.soffice_path,
                "--headless", "--norestore", "--nofirststartwizard",
                f"-env:UserInstallation=file:///{tmp_profile.replace(os.sep, '/')}",
                "--infilter=writer_pdf_import",
                "--convert-to", "docx",
                "--outdir", tmp_outdir,
                input_pdf,
            ]
            logger.info("LibreOffice : %s", " ".join(cmd[:3]) + " ...")

            result = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=self.timeout, cwd=tmp_outdir,
            )
            if result.returncode != 0:
                raise RuntimeError(
                    f"LibreOffice échoué (code {result.returncode}) :\n"
                    f"stdout: {result.stdout}\nstderr: {result.stderr}"
                )

            base       = os.path.splitext(os.path.basename(input_pdf))[0]
            generated  = os.path.join(tmp_outdir, base + ".docx")
            if not os.path.isfile(generated):
                docx_files = [f for f in os.listdir(tmp_outdir) if f.endswith(".docx")]
                if not docx_files:
                    raise RuntimeError("LibreOffice n'a produit aucun fichier .docx")
                generated = os.path.join(tmp_outdir, docx_files[0])

            os.makedirs(os.path.dirname(output_pdf) or ".", exist_ok=True)
            if os.path.exists(output_pdf):
                os.remove(output_pdf)
            shutil.move(generated, output_pdf)

            logger.info("LibreOfficeConverter terminé : %s", output_pdf)
            return output_pdf

        except subprocess.TimeoutExpired:
            raise RuntimeError(
                f"LibreOffice dépassé le timeout ({self.timeout}s). "
                f"Augmentez avec timeout=... pour les gros PDFs."
            )
        finally:
            shutil.rmtree(tmp_outdir,  ignore_errors=True)
            shutil.rmtree(tmp_profile, ignore_errors=True)
