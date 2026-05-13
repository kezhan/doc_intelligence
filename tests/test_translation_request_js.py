"""Tests pour `parse_translation_request` (Step 3 build order Tome 2)."""

from __future__ import annotations

import pytest

from docpipeline.translation.request_js import (
    GlossaryEntry,
    TranslationRequest,
    parse_translation_request,
)


# -------- Cas du spec --------------------------------------------------------

def test_spec_example_full():
    """Test verbatim du spec CLAUDE_tome2_translation.md Step 3."""
    msg = (
        "Translate this contract into formal English, skip the annexes, "
        "and use 'deductible' for 'franchise'."
    )
    req = parse_translation_request(msg)
    assert req.target_language == "en"
    assert req.style == "formal"
    assert req.scope is not None
    assert req.scope.exclude_sections == ["Annexes"]
    assert req.glossary_additions[0] == GlossaryEntry(
        source="franchise", target="deductible"
    )


# -------- Detection de la langue cible --------------------------------------

@pytest.mark.parametrize("msg, expected", [
    ("Translate to English.",                              "en"),
    ("Traduire en français.",                              "fr"),
    ("Bitte ins Deutsche übersetzen.",                     "de"),
    ("Traduce esto al español.",                           "es"),
    ("Traduci questo in italiano.",                        "it"),
    ("Translate into Portuguese.",                         "pt"),
    ("Translate into Dutch.",                              "nl"),
    ("Translate into Chinese.",                            "zh"),
    ("Translate this document into Japanese.",             "ja"),
])
def test_target_language_lookup(msg, expected):
    req = parse_translation_request(msg)
    assert req.target_language == expected


def test_no_language_raises_value_error():
    with pytest.raises(ValueError, match="langue cible"):
        parse_translation_request("Translate this document please.")


def test_empty_message_raises():
    with pytest.raises(ValueError, match="vide"):
        parse_translation_request("")
    with pytest.raises(ValueError, match="vide"):
        parse_translation_request("   \n  ")


# -------- Source language ----------------------------------------------------

def test_source_language_from_to():
    req = parse_translation_request("Translate this from French to English.")
    assert req.source_language == "fr"
    assert req.target_language == "en"


def test_source_language_optional():
    req = parse_translation_request("Translate to German.")
    assert req.source_language is None
    assert req.target_language == "de"


# -------- Style --------------------------------------------------------------

@pytest.mark.parametrize("kw, expected", [
    ("formal",       "formal"),
    ("formel",       "formal"),
    ("professional", "formal"),
    ("casual",       "casual"),
    ("informel",     "casual"),
    ("technical",    "technical"),
    ("technique",    "technical"),
])
def test_style_keyword(kw, expected):
    req = parse_translation_request(f"Translate to English, {kw} style.")
    assert req.style == expected


def test_style_default_when_none():
    req = parse_translation_request("Translate to English.")
    assert req.style == "default"


# -------- Scope : page_range ------------------------------------------------

def test_page_range_pages_to():
    req = parse_translation_request("Translate pages 3 to 15 into English.")
    assert req.scope is not None
    assert req.scope.page_range == (3, 15)


def test_page_range_with_dash():
    req = parse_translation_request("Translate pages 5-12 into German.")
    assert req.scope is not None
    assert req.scope.page_range == (5, 12)


def test_page_range_french():
    req = parse_translation_request(
        "Traduire de la page 2 à 8 en allemand."
    )
    assert req.scope is not None
    assert req.scope.page_range == (2, 8)


# -------- Scope : exclude_sections ------------------------------------------

def test_exclude_sections_skip():
    req = parse_translation_request(
        "Translate to English, skip the Annexes."
    )
    assert req.scope is not None
    assert req.scope.exclude_sections == ["Annexes"]


def test_exclude_sections_french_sauf():
    req = parse_translation_request(
        "Traduire en anglais, sauf les annexes."
    )
    assert req.scope is not None
    assert "Annexes" in req.scope.exclude_sections


def test_no_scope_when_no_marker():
    req = parse_translation_request("Translate to English.")
    assert req.scope is None


# -------- Glossary -----------------------------------------------------------

def test_glossary_use_x_for_y():
    req = parse_translation_request(
        "Translate to English, use 'deductible' for 'franchise'."
    )
    assert len(req.glossary_additions) == 1
    assert req.glossary_additions[0].source == "franchise"
    assert req.glossary_additions[0].target == "deductible"


def test_glossary_translate_x_as_y():
    req = parse_translation_request(
        "Translate to English. Translate 'foo' as 'bar'."
    )
    assert len(req.glossary_additions) == 1
    assert req.glossary_additions[0].source == "foo"
    assert req.glossary_additions[0].target == "bar"


def test_glossary_arrow():
    req = parse_translation_request(
        'Translate to English. "alpha" -> "beta"'
    )
    assert any(
        g.source == "alpha" and g.target == "beta"
        for g in req.glossary_additions
    )


def test_glossary_no_duplicates():
    req = parse_translation_request(
        "Translate to English, use 'B' for 'A'. Translate 'A' as 'B'."
    )
    assert len(req.glossary_additions) == 1


def test_no_glossary_when_no_quotes():
    req = parse_translation_request("Translate to English.")
    assert req.glossary_additions == []


# -------- Integration --------------------------------------------------------

def test_full_request_serializable():
    req = parse_translation_request(
        "Translate pages 3 to 15 into formal English, skip the Annexes, "
        "use 'deductible' for 'franchise'."
    )
    js = req.model_dump_json()
    rebuilt = TranslationRequest.model_validate_json(js)
    assert rebuilt == req
