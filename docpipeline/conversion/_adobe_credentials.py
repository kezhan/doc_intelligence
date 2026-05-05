"""
Détection automatique des credentials Adobe PDF Services.

Ordre de priorité :
  1. Variables d'environnement ADOBE_CLIENT_ID + ADOBE_CLIENT_SECRET
  2. Fichier persistant ~/.docpipeline/adobe_credentials.json
  3. Fichier pdfservices-api-credentials.json téléchargé du SDK Adobe
     (recherché dans le CWD et ses sous-dossiers, profondeur max 3)

L'utilisateur n'a donc pas besoin de réexporter ses variables à chaque session.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional


_CONFIG_DIR  = Path.home() / ".docpipeline"
_CONFIG_FILE = _CONFIG_DIR / "adobe_credentials.json"
_SDK_FILENAME = "pdfservices-api-credentials.json"


def get_adobe_credentials() -> tuple[Optional[str], Optional[str]]:
    """
    Cherche les credentials Adobe dans toutes les sources possibles.

    Returns:
        (client_id, client_secret) ou (None, None) si introuvable
    """
    # 1. Variables d'environnement
    cid = os.environ.get("ADOBE_CLIENT_ID")
    sec = os.environ.get("ADOBE_CLIENT_SECRET")
    if cid and sec:
        return cid, sec

    # 2. Fichier de config persistant
    if _CONFIG_FILE.is_file():
        try:
            data = json.loads(_CONFIG_FILE.read_text(encoding="utf-8"))
            cid = data.get("client_id")
            sec = data.get("client_secret")
            if cid and sec:
                return cid, sec
        except (json.JSONDecodeError, OSError):
            pass

    # 3. Auto-détection du fichier SDK Adobe dans CWD ± sous-dossiers
    sdk_file = _find_sdk_credentials_file()
    if sdk_file:
        try:
            data = json.loads(sdk_file.read_text(encoding="utf-8"))
            creds = data.get("client_credentials", {})
            cid = creds.get("client_id")
            sec = creds.get("client_secret")
            if cid and sec:
                return cid, sec
        except (json.JSONDecodeError, OSError):
            pass

    return None, None


def save_adobe_credentials(client_id: str, client_secret: str) -> Path:
    """Persiste les credentials dans ~/.docpipeline/adobe_credentials.json."""
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    _CONFIG_FILE.write_text(
        json.dumps({"client_id": client_id, "client_secret": client_secret},
                   indent=2),
        encoding="utf-8",
    )
    # Permissions restrictives (Unix uniquement)
    try:
        os.chmod(_CONFIG_FILE, 0o600)
    except OSError:
        pass
    return _CONFIG_FILE


def adobe_credentials_available() -> bool:
    cid, sec = get_adobe_credentials()
    return bool(cid and sec)


def _find_sdk_credentials_file(max_depth: int = 3) -> Optional[Path]:
    """Cherche pdfservices-api-credentials.json dans cwd et sous-dossiers."""
    cwd = Path.cwd()

    # Direct dans cwd
    direct = cwd / _SDK_FILENAME
    if direct.is_file():
        return direct

    # Recherche limitée en profondeur
    for path in cwd.rglob(_SDK_FILENAME):
        # Vérifier la profondeur
        try:
            rel = path.relative_to(cwd)
            if len(rel.parts) <= max_depth + 1:
                return path
        except ValueError:
            continue

    return None
