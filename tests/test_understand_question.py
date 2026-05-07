"""Tests pour extract_hints — extraction d'indices structurels d'une question."""

from __future__ import annotations

import pytest

from docpipeline.question.understand_question import (
    StructuralHints,
    extract_hints,
)


# ╔════════════════════════════════════════════════════════════════════════════╗
# ║ Page hints                                                                 ║
# ╚════════════════════════════════════════════════════════════════════════════╝

class TestPageHint:
    def test_page_simple_fr(self):
        h = extract_hints("Quelle est la date ? C'est en page 1.")
        assert h.page_hint == 1

    def test_page_simple_en(self):
        h = extract_hints("What's the date? Check on page 12.")
        assert h.page_hint == 12

    def test_page_avec_numero(self):
        h = extract_hints("Voir page n°47 du contrat")
        assert h.page_hint == 47

    def test_page_p_dot(self):
        h = extract_hints("Cf. p. 3 pour les conditions")
        assert h.page_hint == 3

    def test_page_a_la_page(self):
        h = extract_hints("Trouve le plafond à la page 8.")
        assert h.page_hint == 8

    def test_no_page(self):
        h = extract_hints("Quelle est la date d'effet ?")
        assert h.page_hint is None


# ╔════════════════════════════════════════════════════════════════════════════╗
# ║ Section hints                                                              ║
# ╚════════════════════════════════════════════════════════════════════════════╝

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
        h = extract_hints("Quel est le tarif ?")
        assert h.section_hint is None


# ╔════════════════════════════════════════════════════════════════════════════╗
# ║ Layout hints                                                               ║
# ╚════════════════════════════════════════════════════════════════════════════╝

class TestLayoutHint:
    def test_table_fr(self):
        h = extract_hints("Le plafond est dans le tableau récapitulatif.")
        assert h.layout_hint == "table"

    def test_table_en(self):
        h = extract_hints("It's in the recap table at the end.")
        assert h.layout_hint == "table"

    def test_image_figure(self):
        h = extract_hints("Voir la figure 3 pour le diagramme de flux.")
        assert h.layout_hint == "image"

    def test_header(self):
        h = extract_hints("The policy number is in the header.")
        assert h.layout_hint == "header"

    def test_footer_fr(self):
        h = extract_hints("La référence est en pied de page.")
        assert h.layout_hint == "footer"

    def test_no_layout(self):
        h = extract_hints("Quel est le montant ?")
        assert h.layout_hint is None


# ╔════════════════════════════════════════════════════════════════════════════╗
# ║ Document / version hints                                                   ║
# ╚════════════════════════════════════════════════════════════════════════════╝

class TestDocumentHint:
    def test_derniere_version(self):
        h = extract_hints("Dans la dernière version du contrat, quel est le plafond ?")
        assert h.document_hint is not None
        assert "dernière" in h.document_hint.lower() or "derniere" in h.document_hint.lower()

    def test_latest_version(self):
        h = extract_hints("In the latest version of the policy.")
        assert h.document_hint is not None
        assert "latest" in h.document_hint.lower()


# ╔════════════════════════════════════════════════════════════════════════════╗
# ║ Combinaisons + edge cases                                                  ║
# ╚════════════════════════════════════════════════════════════════════════════╝

class TestCombinations:
    def test_page_et_section(self):
        h = extract_hints("Le plafond est dans la section Limits, page 3.")
        assert h.page_hint == 3
        assert h.section_hint and "limits" in h.section_hint.lower()

    def test_table_et_page(self):
        h = extract_hints("Voir le tableau page 5.")
        assert h.layout_hint == "table"
        assert h.page_hint == 5

    def test_aucun_hint(self):
        h = extract_hints("Combien coûte l'assurance ?")
        assert h.page_hint is None
        assert h.section_hint is None
        assert h.layout_hint is None
        assert h.document_hint is None
        assert h.raw_signals == []

    def test_question_vide(self):
        h = extract_hints("")
        assert isinstance(h, StructuralHints)
        assert h.page_hint is None

    def test_raw_signals_traceability(self):
        """raw_signals doit lister chaque pattern matché pour audit."""
        h = extract_hints("Voir page 3 dans la section Limits, c'est dans le tableau.")
        assert len(h.raw_signals) >= 3   # page + section + layout
