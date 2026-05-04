"""Tests for TODO-013, 014, 015: glossary and translation decision."""

import json
import pytest
import tempfile
from pathlib import Path

from docpipeline.translation.glossary import (
    Glossary,
    GlossaryEntry,
    detect_business_terms,
    decide_translate_or_keep,
)


@pytest.fixture
def insurance_glossary() -> Glossary:
    entries = [
        GlossaryEntry(
            term="IA",
            source_language="fr",
            translations={"en": ["Individual Accident"]},
            context="insurance",
        ),
        GlossaryEntry(
            term="BI",
            source_language="en",
            translations={"fr": ["Interruption d'activité", "Dommages corporels"]},
            context="insurance",
        ),
        GlossaryEntry(
            term="SLA",
            source_language="en",
            translations={},
            context="tech",
            keep_as_is=True,
        ),
    ]
    return Glossary(entries)


class TestGlossary:
    def test_get_existing_term(self, insurance_glossary):
        entry = insurance_glossary.get("IA")
        assert entry is not None
        assert entry.candidates("en") == ["Individual Accident"]

    def test_case_insensitive(self, insurance_glossary):
        assert insurance_glossary.get("ia") is not None
        assert insurance_glossary.get("IA") is not None

    def test_missing_term_returns_none(self, insurance_glossary):
        assert insurance_glossary.get("UNKNOWN_XYZ") is None

    def test_len(self, insurance_glossary):
        assert len(insurance_glossary) == 3

    def test_json_roundtrip(self, insurance_glossary):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            path = f.name
        insurance_glossary.to_json(path)
        loaded = Glossary.from_json(path)
        assert len(loaded) == 3
        assert loaded.get("IA") is not None


class TestDetectBusinessTerms:
    def test_detects_known_term(self, insurance_glossary):
        text = "La garantie IA couvre les accidents individuels."
        terms = detect_business_terms(text, insurance_glossary)
        assert any(t.term.upper() == "IA" for t in terms)

    def test_no_false_positive_inside_word(self, insurance_glossary):
        text = "Liaison des équipes."
        terms = detect_business_terms(text, insurance_glossary)
        # "ia" inside "Liaison" should NOT match
        ia_matches = [t for t in terms if t.term.upper() == "IA"]
        assert len(ia_matches) == 0


class TestDecideTranslateOrKeep:
    def test_keep_as_is_from_glossary(self, insurance_glossary):
        decision = decide_translate_or_keep("SLA", glossary=insurance_glossary)
        assert decision.action == "keep_as_is"

    def test_default_translate(self, insurance_glossary):
        decision = decide_translate_or_keep("contrat", glossary=insurance_glossary, target_language="en")
        assert decision.action == "translate"

    def test_already_in_target_language(self):
        # "the" is clearly English, target is English → keep
        decision = decide_translate_or_keep("the and for", target_language="en")
        assert decision.action == "keep_as_is"
