"""
AdobeConverter — Conversion PDF vers DOCX via Adobe PDF Services API.

C'est la **référence professionnelle** pour la conversion PDF → Word :
même moteur que celui d'Acrobat Pro DC. Qualité visuelle ET éditabilité
au plus haut niveau, y compris pour les PDFs Adobe InDesign complexes.

Coût :
  - 500 transactions/mois GRATUITES (suffit largement pour la plupart des usages)
  - Au-delà : ~0.05 USD par conversion (très bon marché)

Configuration :
  1. Créer un compte développeur : https://developer.adobe.com/document-services/
  2. Créer un projet → activer "PDF Services API"
  3. Récupérer Client ID + Client Secret
  4. Exporter en variables d'environnement :
       PowerShell : $env:ADOBE_CLIENT_ID='...'; $env:ADOBE_CLIENT_SECRET='...'
       bash       : export ADOBE_CLIENT_ID=... ADOBE_CLIENT_SECRET=...

Aucune dépendance externe : on utilise l'API REST directement avec urllib.
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

_TOKEN_URL  = "https://pdf-services.adobe.io/token"
_ASSETS_URL = "https://pdf-services.adobe.io/assets"
_OPS_URL    = "https://pdf-services.adobe.io/operation/exportpdf"


class AdobeConverter:
    """
    Convertisseur PDF → DOCX via Adobe PDF Services Cloud API.

    Qualité industrielle (même moteur qu'Acrobat Pro). Préserve le layout
    des PDFs InDesign, Photoshop, Illustrator avec édition complète.
    """

    def __init__(
        self,
        client_id:     str | None = None,
        client_secret: str | None = None,
        timeout:       int = 300,
    ) -> None:
        self.client_id     = client_id     or os.environ.get("ADOBE_CLIENT_ID")
        self.client_secret = client_secret or os.environ.get("ADOBE_CLIENT_SECRET")
        self.timeout       = timeout

        if not self.client_id or not self.client_secret:
            raise ValueError(
                "Adobe credentials manquants. Configurez :\n"
                "  $env:ADOBE_CLIENT_ID='...'      (PowerShell)\n"
                "  $env:ADOBE_CLIENT_SECRET='...'  (PowerShell)\n"
                "Compte gratuit : https://developer.adobe.com/document-services/"
            )

    def convert(
        self,
        input_pdf:    str | Path,
        output_docx:  str | Path,
        pages:        list[int] | None = None,
    ) -> str:
        """
        Convertir un PDF en DOCX via l'API Adobe (qualité Acrobat Pro).

        Input  : chemin PDF + chemin DOCX
        Output : chemin DOCX généré
        """
        if pages is not None:
            logger.warning("AdobeConverter ignore l'argument 'pages'.")

        input_pdf  = Path(input_pdf)
        output_pdf = Path(output_docx)

        if not input_pdf.is_file():
            raise FileNotFoundError(f"PDF introuvable : {input_pdf}")

        logger.info("AdobeConverter : %s -> %s", input_pdf, output_pdf)

        token = self._get_access_token()

        # 1. Upload du PDF
        upload_url, asset_id = self._create_upload_url(token, "application/pdf")
        self._upload_file(upload_url, input_pdf, "application/pdf")
        logger.info("PDF uploadé (asset_id=%s)", asset_id[:12])

        # 2. Lancer la conversion
        job_url = self._submit_export_job(token, asset_id, "docx")
        logger.info("Job de conversion soumis")

        # 3. Polling du résultat
        download_url = self._poll_job(token, job_url)
        logger.info("Conversion terminée, téléchargement...")

        # 4. Téléchargement du DOCX
        self._download_file(download_url, output_pdf)
        logger.info("AdobeConverter terminé : %s", output_pdf)
        return str(output_pdf)

    # ── API helpers ──────────────────────────────────────────────────────────

    def _get_access_token(self) -> str:
        data = (
            f"client_id={self.client_id}&client_secret={self.client_secret}"
        ).encode()
        req = urllib.request.Request(
            _TOKEN_URL, data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            payload = json.loads(resp.read())
        return payload["access_token"]

    def _create_upload_url(self, token: str, mime: str) -> tuple[str, str]:
        body = json.dumps({"mediaType": mime}).encode()
        req  = urllib.request.Request(
            _ASSETS_URL, data=body,
            headers={
                "Authorization":     f"Bearer {token}",
                "X-API-Key":         self.client_id,
                "Content-Type":      "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            payload = json.loads(resp.read())
        return payload["uploadUri"], payload["assetID"]

    def _upload_file(self, upload_url: str, file_path: Path, mime: str) -> None:
        data = file_path.read_bytes()
        req  = urllib.request.Request(
            upload_url, data=data, method="PUT",
            headers={"Content-Type": mime},
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            resp.read()

    def _submit_export_job(self, token: str, asset_id: str, target_fmt: str) -> str:
        body = json.dumps({
            "assetID":      asset_id,
            "targetFormat": target_fmt,
            "ocrLang":      "fr-FR",
        }).encode()
        req = urllib.request.Request(
            _OPS_URL, data=body,
            headers={
                "Authorization": f"Bearer {token}",
                "X-API-Key":     self.client_id,
                "Content-Type":  "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return resp.headers["location"]

    def _poll_job(self, token: str, job_url: str, *, interval: int = 3) -> str:
        deadline = time.time() + self.timeout
        headers  = {
            "Authorization": f"Bearer {token}",
            "X-API-Key":     self.client_id,
        }
        while time.time() < deadline:
            req = urllib.request.Request(job_url, headers=headers)
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                payload = json.loads(resp.read())
            status = payload.get("status")
            if status == "done":
                return payload["asset"]["downloadUri"]
            if status == "failed":
                raise RuntimeError(f"Adobe job failed : {payload}")
            time.sleep(interval)
        raise RuntimeError(f"Adobe job timeout après {self.timeout}s")

    def _download_file(self, url: str, output_path: Path) -> None:
        with urllib.request.urlopen(url, timeout=self.timeout) as resp:
            output_path.write_bytes(resp.read())
