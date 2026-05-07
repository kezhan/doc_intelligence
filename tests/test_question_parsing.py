"""Tests pour question_parsing — Brique 2."""

from __future__ import annotations

from dataclasses import asdict

import pytest

from docpipeline.question.question_parsing import (
    Disambiguation,
    ParsedQuestion,
    StructuralHints,
    classify_intent,
    extract_anchor_keywords,
    extract_disambiguation,
    extract_format_constraint,
    extract_hints,
    parse_question,
)


# ╔════════════════════════════════════════════════════════════════════════════╗
# ║ 1. Hints structurels                                                       ║
# ╚════════════════════════════════════════════════════════════════════════════╝

class TestPageHint:
    def test_page_simple_fr(self):
        assert extract_hints("C'est en page 1.").page_hint == 1

    def test_page_simple_en(self):
        assert extract_hints("Check on page 12.").page_hint == 12

    def test_page_avec_numero(self):
        assert extract_hints("Voir page n°47").page_hint == 47

    def test_page_p_dot(self):
        assert extract_hints("Cf. p. 3").page_hint == 3

    def test_page_a_la_page(self):
        assert extract_hints("à la page 8").page_hint == 8

    def test_no_page(self):
        assert extract_hints("Quelle est la date ?").page_hint is None


class TestSectionHint:
    def test_section_dans_la(self):
        h = extract_hints("Cherche dans la section exclusions.")
        assert h.section_hint and "exclusions" in h.section_hint.lower()

    def test_section_in_the(self):
        h = extract_hints("Look in the section Risks for the limit.")
        assert h.section_hint and "risks" in h.section_hint.lower()

    def test_section_called(self):
        h = extract_hints("It's in a section called 'Limits and Deductibles'.")
        assert h.section_hint and "limits" in h.section_hint.lower()

    def test_no_section(self):
        assert extract_hints("Quel est le tarif ?").section_hint is None


class TestLayoutHint:
    def test_table_fr(self):
        assert extract_hints("dans le tableau récapitulatif").layout_hint == "table"

    def test_table_en(self):
        assert extract_hints("in the recap table").layout_hint == "table"

    def test_image_figure(self):
        assert extract_hints("Voir la figure 3").layout_hint == "image"

    def test_header(self):
        assert extract_hints("in the header").layout_hint == "header"

    def test_footer_fr(self):
        assert extract_hints("en pied de page").layout_hint == "footer"

    def test_no_layout(self):
        assert extract_hints("Quel est le montant ?").layout_hint is None


class TestDocumentHint:
    def test_derniere_version(self):
        h = extract_hints("Dans la dernière version du contrat")
        assert h.document_hint and "dernière" in h.document_hint.lower()

    def test_latest_version(self):
        h = extract_hints("In the latest version of the policy.")
        assert h.document_hint and "latest" in h.document_hint.lower()


# ╔════════════════════════════════════════════════════════════════════════════╗
# ║ 2. Anchor keywords (codes / IDs / acronymes)                               ║
# ╚════════════════════════════════════════════════════════════════════════════╝

class TestAnchorKeywords:
    def test_code_juridique(self):
        kws, _ = extract_anchor_keywords("Article L131-1 du code des assurances")
        assert any("L131-1" in k for k in kws)

    def test_acronyme_court(self):
        kws, _ = extract_anchor_keywords("Compliance with GDPR and SLA requirements")
        assert "GDPR" in kws and "SLA" in kws

    def test_id_avec_tiret(self):
        kws, _ = extract_anchor_keywords("Référence du contrat : RC-2024-001")
        assert any("RC-2024" in k for k in kws)

    def test_stopwords_uppercase_filtered(self):
        kws, _ = extract_anchor_keywords("WITH THE LIMIT FOR DAMAGES")
        assert "WITH" not in kws and "THE" not in kws and "FOR" not in kws

    def test_no_keywords(self):
        kws, _ = extract_anchor_keywords("quel est le tarif ?")
        assert kws == []


# ╔════════════════════════════════════════════════════════════════════════════╗
# ║ 3. Format constraint                                                       ║
# ╚════════════════════════════════════════════════════════════════════════════╝

class TestFormatConstraint:
    def test_iso_date(self):
        fmt, _ = extract_format_constraint("Date au format YYYY-MM-DD")
        assert fmt == "ISO 8601 date (YYYY-MM-DD)"

    def test_json(self):
        fmt, _ = extract_format_constraint("Réponds en JSON.")
        assert fmt == "valid JSON"

    def test_euros(self):
        fmt, _ = extract_format_constraint("Montant en euros")
        assert "EUR" in fmt

    def test_bullet_list(self):
        fmt, _ = extract_format_constraint("Donne une bullet list des obligations")
        assert fmt == "bullet list"

    def test_one_sentence_fr(self):
        fmt, _ = extract_format_constraint("Réponds en une phrase.")
        assert "single sentence" in fmt

    def test_no_constraint(self):
        fmt, _ = extract_format_constraint("Quel est le plafond ?")
        assert fmt is None


# ╔════════════════════════════════════════════════════════════════════════════╗
# ║ 4. Disambiguation (« X, not Y », ...)                                      ║
# ╚════════════════════════════════════════════════════════════════════════════╝

class TestDisambiguation:
    def test_pas_la_franchise(self):
        d = extract_disambiguation("Le plafond, pas la franchise")
        assert any("franchise" in x for x in d.distractors)
        assert d.instruction is not None

    def test_not_the_deductible(self):
        d = extract_disambiguation("the limit per claim, not the deductible")
        assert any("deductible" in x for x in d.distractors)

    def test_dont_confuse_with(self):
        d = extract_disambiguation("the maximum coverage. Don't confuse it with the deductible.")
        assert any("deductible" in x for x in d.distractors)

    def test_excluding(self):
        d = extract_disambiguation("All the clauses excluding the optional ones.")
        assert any("optional" in x for x in d.distractors)

    def test_no_disambiguation(self):
        d = extract_disambiguation("Quel est le plafond ?")
        assert d.distractors == []
        assert d.instruction is None


# ╔════════════════════════════════════════════════════════════════════════════╗
# ║ 5. Intent classification                                                   ║
# ╚════════════════════════════════════════════════════════════════════════════╝

class TestClassifyIntent:
    def test_compare(self):
        assert classify_intent("Compare the indemnification and liability caps") == "compare"

    def test_aggregate(self):
        assert classify_intent("List all the obligations of the seller") == "aggregate"

    def test_conditional_or_yes_no(self):
        assert classify_intent("Is there a non-compete clause, and if so for how long?") in ("conditional", "yes_no")

    def test_yes_no(self):
        assert classify_intent("Does this contract include a clause?") == "yes_no"

    def test_extract_default(self):
        assert classify_intent("What is the maximum coverage amount?") == "extract"

    def test_unknown_falls_to_extract(self):
        assert classify_intent("blabla random text") == "extract"


# ╔════════════════════════════════════════════════════════════════════════════╗
# ║ 6. parse_question — orchestration complète                                 ║
# ╚════════════════════════════════════════════════════════════════════════════╝

class TestParseQuestionContract:
    def test_returns_parsed_question(self):
        assert isinstance(parse_question("test"), ParsedQuestion)

    def test_json_serializable(self):
        import json
        p = parse_question("Le plafond page 3, format JSON, pas la franchise")
        json.dumps(asdict(p))

    def test_empty_question(self):
        p = parse_question("")
        assert p.original_question == ""
        assert p.intent == "extract"
        assert p.anchor_keywords == []

    def test_none_question_safe(self):
        assert isinstance(parse_question(None), ParsedQuestion)


class TestParseQuestionRichExample:
    """Question riche couvrant tous les champs."""

    @pytest.fixture(scope="class")
    def parsed(self):
        return parse_question(
            "What's the limit per claim, not the deductible, in section 'Limits' page 5? "
            "Format YYYY-MM-DD. Article L131-1 applies."
        )

    def test_page_hint_extracted(self, parsed):
        assert parsed.structural_hints.page_hint == 5

    def test_section_hint_extracted(self, parsed):
        assert parsed.structural_hints.section_hint and "limits" in parsed.structural_hints.section_hint.lower()

    def test_anchor_keyword_extracted(self, parsed):
        assert any("L131-1" in k for k in parsed.anchor_keywords)

    def test_format_constraint_extracted(self, parsed):
        assert "ISO 8601" in (parsed.format_constraint or "")

    def test_disambiguation_extracted(self, parsed):
        assert any("deductible" in x for x in parsed.disambiguation.distractors)

    def test_raw_signals_traceability(self, parsed):
        assert len(parsed.raw_signals) >= 4


class TestParseQuestionMinimal:
    """Question sans aucun signal — tout doit être propre."""

    def test_no_signals(self):
        p = parse_question("Combien coûte l'assurance ?")
        assert p.structural_hints.page_hint is None
        assert p.structural_hints.section_hint is None
        assert p.structural_hints.layout_hint is None
        assert p.anchor_keywords == []
        assert p.format_constraint is None
        assert p.disambiguation.distractors == []
