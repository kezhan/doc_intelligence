"""Tests pour docpipeline.question_parsing — Brique 2."""

from __future__ import annotations

import pytest

from docpipeline.question_parsing import (
    BRICKS,
    PRESETS,
    classify_intent,
    extract_anchor_keywords,
    extract_disambiguation,
    extract_format_constraint,
    extract_hints,
    parse_question,
    preset_for,
    resolve_active,
)


# ╔════════════════════════════════════════════════════════════════════════════╗
# ║ 1. extract_hints — page                                                    ║
# ╚════════════════════════════════════════════════════════════════════════════╝

class TestPageHint:
    def test_page_simple_fr(self):
        assert extract_hints("C'est en page 1.").get("page_hint") == 1

    def test_page_simple_en(self):
        assert extract_hints("Check on page 12.").get("page_hint") == 12

    def test_page_avec_numero(self):
        assert extract_hints("Voir page n°47").get("page_hint") == 47

    def test_page_p_dot(self):
        assert extract_hints("Cf. p. 3").get("page_hint") == 3

    def test_page_a_la_page(self):
        assert extract_hints("à la page 8").get("page_hint") == 8

    def test_no_page(self):
        assert "page_hint" not in extract_hints("Quelle est la date ?")


# ╔════════════════════════════════════════════════════════════════════════════╗
# ║ 2. extract_hints — section (correctifs vs version Kezhan)                  ║
# ╚════════════════════════════════════════════════════════════════════════════╝

class TestSectionHint:
    def test_x_section_form(self):
        # FIX bug Kezhan : sa regex matchait « for the flooding clause »
        h = extract_hints("Look in the exclusions section for the flooding clause.")
        assert h.get("section_hint") == "exclusions"

    def test_in_the_section_x(self):
        h = extract_hints("Look in the section Risks for the limit.")
        assert h.get("section_hint") == "risks"

    def test_section_called(self):
        h = extract_hints("It's in a section called 'Limits'.")
        assert h.get("section_hint") == "limits"

    def test_dans_la_section(self):
        h = extract_hints("Cherche dans la section exclusions.")
        assert h.get("section_hint") == "exclusions"

    def test_no_section(self):
        assert "section_hint" not in extract_hints("Quel est le tarif ?")


# ╔════════════════════════════════════════════════════════════════════════════╗
# ║ 3. extract_hints — layout                                                  ║
# ╚════════════════════════════════════════════════════════════════════════════╝

class TestLayoutHint:
    def test_table_fr(self):
        assert extract_hints("dans le tableau récapitulatif").get("layout_hint") == "table"

    def test_table_en(self):
        assert extract_hints("in the recap table").get("layout_hint") == "table"

    def test_image_figure(self):
        assert extract_hints("Voir la figure 3").get("layout_hint") == "image"

    def test_header(self):
        assert extract_hints("in the header").get("layout_hint") == "header"

    def test_footer_fr(self):
        assert extract_hints("en pied de page").get("layout_hint") == "footer"

    def test_no_layout(self):
        assert "layout_hint" not in extract_hints("Quel est le montant ?")


# ╔════════════════════════════════════════════════════════════════════════════╗
# ║ 4. extract_hints — document                                                ║
# ╚════════════════════════════════════════════════════════════════════════════╝

class TestDocumentHint:
    def test_derniere_version(self):
        h = extract_hints("Dans la dernière version du contrat")
        assert h.get("document_hint") and "dernière" in h["document_hint"].lower()

    def test_latest_version(self):
        h = extract_hints("In the latest version of the policy.")
        assert h.get("document_hint") and "latest" in h["document_hint"].lower()


# ╔════════════════════════════════════════════════════════════════════════════╗
# ║ 5. anchor keywords (correctifs : articles juridiques + exclusion YYYY)     ║
# ╚════════════════════════════════════════════════════════════════════════════╝

class TestAnchorKeywords:
    def test_article_juridique_isole(self):
        # FIX bug Kezhan : "L131-1" doit apparaître
        kws = extract_anchor_keywords("Article L131-1 du code des assurances")
        assert any("L131-1" in k or "131-1" in k for k in kws)

    def test_article_avec_prefixe(self):
        kws = extract_anchor_keywords("voir article 1234 du code civil")
        assert any("1234" in k for k in kws)

    def test_acronyme_court(self):
        kws = extract_anchor_keywords("Compliance with GDPR and SLA requirements")
        assert "GDPR" in kws and "SLA" in kws

    def test_id_avec_tiret(self):
        kws = extract_anchor_keywords("Référence : RC-2024-001")
        assert any("RC-2024" in k for k in kws)

    def test_yyyy_exclu(self):
        # FIX bug Kezhan : "YYYY" était détecté comme code
        kws = extract_anchor_keywords("Date au format YYYY-MM-DD")
        assert "YYYY" not in kws

    def test_json_exclu(self):
        kws = extract_anchor_keywords("Réponds en JSON")
        assert "JSON" not in kws

    def test_stopwords_uppercase_filtered(self):
        kws = extract_anchor_keywords("WITH THE LIMIT FOR DAMAGES")
        assert all(w not in kws for w in ("WITH", "THE", "FOR"))

    def test_no_keywords(self):
        assert extract_anchor_keywords("quel est le tarif ?") == []


# ╔════════════════════════════════════════════════════════════════════════════╗
# ║ 6. format constraint                                                       ║
# ╚════════════════════════════════════════════════════════════════════════════╝

class TestFormatConstraint:
    def test_iso_date(self):
        assert extract_format_constraint("au format YYYY-MM-DD") == "ISO 8601 date (YYYY-MM-DD)"

    def test_json(self):
        assert extract_format_constraint("Réponds en JSON.") == "valid JSON"

    def test_euros(self):
        assert "EUR" in extract_format_constraint("Montant en euros")

    def test_dollars(self):
        assert "USD" in extract_format_constraint("amount in dollars")

    def test_bullet_list(self):
        assert extract_format_constraint("en liste") == "bullet list"

    def test_one_sentence(self):
        assert "single sentence" in extract_format_constraint("Réponds en une phrase.")

    def test_no_constraint(self):
        assert extract_format_constraint("Quel est le plafond ?") is None


# ╔════════════════════════════════════════════════════════════════════════════╗
# ║ 7. disambiguation                                                          ║
# ╚════════════════════════════════════════════════════════════════════════════╝

class TestDisambiguation:
    def test_pas_la_franchise(self):
        instr, ds = extract_disambiguation("Le plafond, pas la franchise")
        assert any("franchise" in d for d in ds)
        assert instr is not None

    def test_not_the_deductible(self):
        instr, ds = extract_disambiguation("the limit, not the deductible")
        assert any("deductible" in d for d in ds)

    def test_dont_confuse(self):
        _, ds = extract_disambiguation("the maximum coverage. Don't confuse it with the deductible.")
        assert any("deductible" in d for d in ds)

    def test_excluding(self):
        _, ds = extract_disambiguation("All the clauses excluding the optional ones.")
        assert any("optional" in d for d in ds)

    def test_no_disambiguation(self):
        instr, ds = extract_disambiguation("Quel est le plafond ?")
        assert instr is None and ds == []


# ╔════════════════════════════════════════════════════════════════════════════╗
# ║ 8. classify_intent                                                         ║
# ╚════════════════════════════════════════════════════════════════════════════╝

class TestClassifyIntent:
    def test_compare(self):
        assert classify_intent("Compare the indemnification and liability caps") == "compare"

    def test_aggregate(self):
        assert classify_intent("List all the obligations of the seller") == "aggregate"

    def test_yes_no(self):
        assert classify_intent("Does this contract include a clause?") == "yes_no"

    def test_extract_default(self):
        # FIX : « what is » doit prévaloir sur le « is » de yes_no
        assert classify_intent("What is the maximum coverage amount?") == "extract"

    def test_extract_fr(self):
        assert classify_intent("Quel est le plafond ?") == "extract"

    def test_unknown_falls_to_extract(self):
        assert classify_intent("blabla random text") == "extract"


# ╔════════════════════════════════════════════════════════════════════════════╗
# ║ 9. PRESETS et resolve_active                                               ║
# ╚════════════════════════════════════════════════════════════════════════════╝

class TestPresets:
    def test_pdf_has_page_hint(self):
        assert "page_hint" in preset_for("pdf")

    def test_word_no_page_hint(self):
        # En Word, page_hint n'a pas de sens (pas de pagination stable)
        assert "page_hint" not in preset_for("word")

    def test_excel_minimal(self):
        # En Excel, ni page_hint ni section_hint
        active = preset_for("excel")
        assert "page_hint" not in active
        assert "section_hint" not in active

    def test_unknown_doctype_falls_to_pdf(self):
        assert preset_for("unknown") == preset_for("pdf")


class TestResolveActive:
    def test_no_enable_returns_preset(self):
        assert resolve_active("pdf", None) == preset_for("pdf")

    def test_enable_disables_brick(self):
        active = resolve_active("pdf", {"page_hint": False})
        assert "page_hint" not in active

    def test_enable_adds_brick(self):
        active = resolve_active("word", {"page_hint": True})
        assert "page_hint" in active


# ╔════════════════════════════════════════════════════════════════════════════╗
# ║ 10. parse_question — orchestration end-to-end                              ║
# ╚════════════════════════════════════════════════════════════════════════════╝

class TestParseQuestionContract:
    def test_returns_list(self):
        plan = parse_question("test")
        assert isinstance(plan, list)
        assert len(plan) == 1

    def test_entry_structure(self):
        plan = parse_question("test")
        entry = plan[0]
        assert "retrieval" in entry
        assert "generation" in entry
        assert "_meta" in entry

    def test_retrieval_has_main_query(self):
        plan = parse_question("Quel est le plafond ?")
        assert plan[0]["retrieval"]["main_query"] == "Quel est le plafond ?"

    def test_generation_has_original(self):
        plan = parse_question("Quel est le plafond ?")
        assert plan[0]["generation"]["original_question"] == "Quel est le plafond ?"

    def test_meta_has_intent_doctype_bricks(self):
        plan = parse_question("Quel est le plafond ?", document_type="pdf")
        meta = plan[0]["_meta"]
        assert "intent" in meta
        assert meta["document_type"] == "pdf"
        assert "bricks_active" in meta

    def test_no_null_in_json(self):
        # Une question minimale ne doit avoir AUCUN null dans le JSON
        import json
        plan = parse_question("Combien coûte l'assurance ?")
        s = json.dumps(plan, ensure_ascii=False)
        assert "null" not in s

    def test_empty_question_safe(self):
        plan = parse_question("")
        assert isinstance(plan, list) and len(plan) == 1

    def test_none_question_safe(self):
        plan = parse_question(None)
        assert isinstance(plan, list) and len(plan) == 1

    def test_json_serializable(self):
        import json
        plan = parse_question(
            "Le plafond page 3, format JSON, pas la franchise. Article L131-1."
        )
        json.dumps(plan)  # ne doit pas lever


# ╔════════════════════════════════════════════════════════════════════════════╗
# ║ 11. parse_question — question riche (vérifie l'orchestration complète)     ║
# ╚════════════════════════════════════════════════════════════════════════════╝

class TestParseQuestionRich:
    @pytest.fixture(scope="class")
    def plan(self):
        return parse_question(
            "What is the limit per claim, not the deductible, in the Limits section "
            "page 5? Format YYYY-MM-DD. Article L131-1 applies.",
            document_type="pdf",
        )

    def test_page_extracted(self, plan):
        assert plan[0]["retrieval"].get("page_hint") == 5

    def test_section_extracted_clean(self, plan):
        # Pas le bug Kezhan « for the flooding clause »
        assert plan[0]["retrieval"].get("section_hint") == "limits"

    def test_anchor_juridique_extracted(self, plan):
        kws = plan[0]["retrieval"].get("anchor_keywords", [])
        assert any("L131-1" in k or "131-1" in k for k in kws)

    def test_format_extracted(self, plan):
        assert "ISO 8601" in plan[0]["generation"].get("format_constraint", "")

    def test_disambiguation_extracted(self, plan):
        ds = plan[0]["generation"].get("must_distinguish", [])
        assert any("deductible" in d for d in ds)

    def test_yyyy_not_in_anchors(self, plan):
        # FIX : YYYY ne doit PAS être un anchor (faux positif Kezhan)
        kws = plan[0]["retrieval"].get("anchor_keywords", [])
        assert "YYYY" not in kws

    def test_bricks_active_traceability(self, plan):
        bricks = plan[0]["_meta"]["bricks_active"]
        assert "page_hint" in bricks
        assert "section_hint" in bricks
        assert "anchor_keywords" in bricks
        assert "format" in bricks
        assert "disambiguation" in bricks


class TestParseQuestionDocTypes:
    def test_word_no_page_hint_in_output(self):
        plan = parse_question("Plafond page 3 du contrat", document_type="word")
        # En Word, page_hint ne doit PAS apparaître (preset n'inclut pas page_hint)
        assert "page_hint" not in plan[0]["retrieval"]
        assert "page_hint" not in plan[0]["_meta"]["bricks_active"]

    def test_excel_no_section_hint(self):
        plan = parse_question("Dans la section X, le montant", document_type="excel")
        assert "section_hint" not in plan[0]["retrieval"]


# ╔════════════════════════════════════════════════════════════════════════════╗
# ║ 12. Compatibilité drop-in avec src.question (même structure de sortie)     ║
# ╚════════════════════════════════════════════════════════════════════════════╝

class TestDropInCompat:
    def test_same_top_level_keys_as_kezhan(self):
        plan = parse_question("test")
        keys = set(plan[0].keys())
        assert keys == {"retrieval", "generation", "_meta"}

    def test_meta_keys_match_kezhan(self):
        plan = parse_question("test")
        meta_keys = set(plan[0]["_meta"].keys())
        assert {"intent", "document_type", "bricks_active"}.issubset(meta_keys)
