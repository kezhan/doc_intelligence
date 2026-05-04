"""
Parsing emails (.eml) — section 3.4 du document Faseya.

Sortie : DataFrame standardisé une ligne = un paragraphe du corps,
avec métadonnées (from, to, subject, date) + pièces jointes listées.

Aucun LLM. Utilise la stdlib `email`.
"""

from __future__ import annotations

import email
import logging
from dataclasses import dataclass, field
from email import policy
from pathlib import Path
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class EmailParseResult:
    df:           pd.DataFrame              # corps du mail, ligne par ligne
    headers:      dict[str, str]            # from, to, subject, date, cc, bcc
    body_text:    str                       # corps complet en texte brut
    body_html:    str                       # corps HTML si présent
    attachments:  list[dict[str, Any]] = field(default_factory=list)


def parse_email(eml_path: str | Path) -> EmailParseResult:
    """
    Parser un email .eml.

    Input  : chemin .eml
    Output : EmailParseResult avec DataFrame + headers + corps + pièces jointes
    """
    eml_path = Path(eml_path)
    raw      = eml_path.read_bytes()
    msg      = email.message_from_bytes(raw, policy=policy.default)

    headers = {
        "from":    str(msg.get("From",    "")),
        "to":      str(msg.get("To",      "")),
        "cc":      str(msg.get("Cc",      "")),
        "bcc":     str(msg.get("Bcc",     "")),
        "subject": str(msg.get("Subject", "")),
        "date":    str(msg.get("Date",    "")),
        "message_id": str(msg.get("Message-ID", "")),
    }

    body_text   = ""
    body_html   = ""
    attachments: list[dict[str, Any]] = []

    if msg.is_multipart():
        for part in msg.walk():
            disp = str(part.get("Content-Disposition", ""))
            ctype = part.get_content_type()

            if "attachment" in disp.lower():
                filename = part.get_filename() or "unnamed"
                payload  = part.get_payload(decode=True) or b""
                attachments.append({
                    "filename":     filename,
                    "content_type": ctype,
                    "size_bytes":   len(payload),
                })
                continue

            if ctype == "text/plain" and not body_text:
                body_text = _payload_text(part)
            elif ctype == "text/html" and not body_html:
                body_html = _payload_text(part)
    else:
        ctype = msg.get_content_type()
        text  = _payload_text(msg)
        if ctype == "text/html":
            body_html = text
        else:
            body_text = text

    # DataFrame standardisé : une ligne par paragraphe non vide
    paras = [p.strip() for p in (body_text or "").splitlines() if p.strip()]
    df = pd.DataFrame({
        "line": list(range(len(paras))),
        "text": paras,
    })

    logger.info("Email parsé : sujet=%s, %d paragraphes, %d pièces jointes",
                headers["subject"][:40], len(df), len(attachments))

    return EmailParseResult(
        df          = df,
        headers     = headers,
        body_text   = body_text,
        body_html   = body_html,
        attachments = attachments,
    )


def _payload_text(part) -> str:
    payload = part.get_payload(decode=True)
    if payload is None:
        return ""
    charset = part.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="replace")
    except (LookupError, AttributeError):
        return payload.decode("utf-8", errors="replace")
