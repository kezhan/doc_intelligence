"""TODO-TOC-005 — Extraction de TOC par LLM (OpenAI).

Portage adapté de ``ai_toc.toc.detect_mot_cle`` — stratégie LLM optionnelle
pour les PDFs où les méthodes heuristiques échouent (PDFs scannés mal OCRisés,
mises en page non-standard sans leaders ni signets).

Approche : identique au projet de base ``toc_detector`` — on lit simplement
les N premières pages (défaut : 5) via ``extract_text_from_first_pages``
(pdfplumber), on concatène le texte et on l'envoie au LLM.  Pas de pré-filtre
par mots-clés : le LLM décide lui-même si une TOC est présente.

Correspondance avec ai_toc :
  ai_toc.toc.detect_mot_cle.detect_toc_pages           → find_toc_pages (conservé pour l'inspection)
  ai_toc.toc.detect_mot_cle.extract_toc_with_fitz      → extract_raw_toc_text (conservé pour l'inspection)
  ai_toc.toc.detect_mot_cle.extract_structured_toc_... → _extract_structured_with_openai
  ai_toc.toc.detect_mot_cle.extract_toc_with_gpt       → extract_toc_with_gpt

Différences par rapport à ai_toc :
  - Utilise les N premières pages (pdfplumber, même logique que toc_detector)
    au lieu d'un scan par mots-clés avant d'appeler le LLM.
  - Utilise ``client.beta.chat.completions.parse`` (openai>=1.12) plutôt que
    ``client.responses.parse`` (openai v2 uniquement).
  - Modèle par défaut ``gpt-4o-mini`` (plus économique que ``gpt-4.1``).
  - La dépendance openai est optionnelle : ``pip install 'docpipeline[llm]'``.
  - Retourne un DataFrame vide (jamais None) en cas d'échec, pour cohérence
    avec les autres extracteurs du package.

Usage :
    from docpipeline.parsing.pdf.toc.gpt import extract_toc_with_gpt

    df = extract_toc_with_gpt("rapport_annuel.pdf", api_key="sk-...")
    # → DataFrame colonnes [level, title, page_num]
"""

from __future__ import annotations

import fitz  # PyMuPDF — conservé pour find_toc_pages / extract_raw_toc_text
import pandas as pd

from .patterns import TOC_KEYWORDS
from .reader import DEFAULT_MAX_PAGES, extract_text_from_first_pages


# ── Lazy helpers ──────────────────────────────────────────────────────────────


def _get_openai_client(api_key: str):
    """Instancier le client OpenAI, avec message d'erreur clair si absent."""
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise ImportError(
            "openai is required for LLM-based TOC extraction. "
            "Install the optional dependency with: pip install 'docpipeline[llm]'"
        ) from exc
    return OpenAI(api_key=api_key)


def _get_toc_schema():
    """Charger les schémas Pydantic TOC (lazy, uniquement quand openai est installé)."""
    try:
        from pydantic import BaseModel
    except ImportError as exc:
        raise ImportError(
            "pydantic is required for structured LLM output. "
            "It is installed automatically with openai>=1.0."
        ) from exc

    class TocEntry(BaseModel):
        title: str
        page_num: int
        level: int

    class TocList(BaseModel):
        entries: list[TocEntry]

    return TocEntry, TocList


# ── Helpers d'inspection (conservés depuis ai_toc pour usage notebook) ───────


def find_toc_pages(doc: fitz.Document) -> list[int]:
    """
    Identifier les pages contenant des mots-clés de table des matières.

    Adapté de ``ai_toc.toc.detect_mot_cle.detect_toc_pages``.
    Utilisé pour l'inspection/debug dans les notebooks — ``extract_toc_with_gpt``
    n'en dépend pas : il envoie toujours les N premières pages au LLM.

    Input  : document PyMuPDF ouvert (fitz.Document)
    Output : liste de numéros de pages 1-indexés contenant un mot-clé TOC
    """
    keywords = [kw.lower() for kw in TOC_KEYWORDS]
    return [
        page_num + 1
        for page_num in range(len(doc))
        if any(kw in doc[page_num].get_text().lower() for kw in keywords)
    ]


def extract_raw_toc_text(doc: fitz.Document, page_nums: list[int]) -> str:
    """
    Extraire le texte brut des pages identifiées (fitz).

    Adapté de ``ai_toc.toc.detect_mot_cle.extract_toc_with_fitz``.
    Utilisé pour l'inspection/debug dans les notebooks.

    Input  : document PyMuPDF ouvert, liste de numéros 1-indexés
    Output : texte brut concaténé (str)
    """
    return "\n".join(
        doc[num - 1].get_text()
        for num in page_nums
        if 0 < num <= len(doc)
    )


# ── Extraction structurée via OpenAI ──────────────────────────────────────────


def _extract_structured_with_openai(
    raw_text: str,
    api_key: str,
    model: str = "gpt-4o-mini",
    custom_prompt: str | None = None,
) -> list[dict]:
    """
    Extraire les entrées TOC structurées via OpenAI structured outputs.

    Adapté de ``ai_toc.toc.detect_mot_cle.extract_structured_toc_with_chatgpt``.

    Utilise ``client.beta.chat.completions.parse`` avec un schéma Pydantic pour
    garantir une sortie JSON validée côté API.

    Input  : texte brut (premières pages), clé API OpenAI, modèle, prompt custom
    Output : liste de dicts {title, page_num, level}
    """
    client = _get_openai_client(api_key)
    _, TocList = _get_toc_schema()

    if custom_prompt is None:
        user_content = (
            "Extract structured TOC entries from the document text below.\n\n"
            "Look for a table of contents, sommaire, or similar section. "
            "Each entry typically contains a title followed by dots or spaces "
            "and ends with a page number. Assign hierarchical levels (1, 2, 3…) "
            "based on indentation or numbering patterns. "
            "Return an empty list if no table of contents is found.\n\n"
            f"Document text (first pages):\n{raw_text}"
        )
    else:
        user_content = f"{custom_prompt}\n\nDocument text (first pages):\n{raw_text}"

    response = client.beta.chat.completions.parse(
        model=model,
        messages=[
            {
                "role": "system",
                "content": "You extract structured table of contents from document text.",
            },
            {"role": "user", "content": user_content},
        ],
        response_format=TocList,
    )

    result = response.choices[0].message.parsed
    if result is None:
        return []

    return [
        {"title": e.title, "page_num": e.page_num, "level": e.level}
        for e in result.entries
    ]


# ── Orchestrateur principal ────────────────────────────────────────────────────


def extract_toc_with_gpt(
    pdf_path,
    api_key: str,
    *,
    max_pages: int = DEFAULT_MAX_PAGES,
    model: str = "gpt-4o-mini",
    custom_prompt: str | None = None,
) -> pd.DataFrame:
    """
    TODO-TOC-005 — Extraire le TOC d'un PDF via LLM (OpenAI).

    Même approche que le projet de base ``toc_detector`` : on lit les
    ``max_pages`` premières pages via pdfplumber (``extract_text_from_first_pages``),
    on concatène le texte et on l'envoie directement au LLM — sans pré-filtre
    par mots-clés.  Le LLM décide si une TOC est présente.

    Cette stratégie est le fallback LLM de dernier recours dans la chaîne :
      native → links → textual (dotted / multiline) → **gpt** (ce module)

    Input  : chemin PDF, clé API OpenAI
             max_pages     : nombre de premières pages à envoyer (défaut: 5)
             model         : modèle OpenAI à utiliser (défaut: gpt-4o-mini)
             custom_prompt : instructions personnalisées remplaçant le prompt par défaut
    Output : DataFrame colonnes [level, title, page_num]
             — vide (0 lignes) si le LLM ne trouve pas de TOC ou en cas d'échec
    """
    pages = extract_text_from_first_pages(pdf_path, max_pages=max_pages)
    raw_text = "\n\n--- page break ---\n\n".join(
        p["text"] for p in pages if p["text"].strip()
    )

    if not raw_text.strip():
        return pd.DataFrame(columns=["level", "title", "page_num"])

    try:
        entries = _extract_structured_with_openai(
            raw_text,
            api_key=api_key,
            model=model,
            custom_prompt=custom_prompt,
        )
    except Exception:
        return pd.DataFrame(columns=["level", "title", "page_num"])

    if not entries:
        return pd.DataFrame(columns=["level", "title", "page_num"])

    return (
        pd.DataFrame(entries)
        .sort_values("page_num")
        .reset_index(drop=True)
    )
