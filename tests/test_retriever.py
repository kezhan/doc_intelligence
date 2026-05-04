"""Tests for TODO-023: Retrieval brick."""

import pandas as pd
import pytest

from docpipeline.retrieval.retriever import retrieve


@pytest.fixture
def sample_df() -> pd.DataFrame:
    return pd.DataFrame({
        "page": [1, 1, 2, 2, 3],
        "line": [0, 1, 0, 1, 0],
        "text": [
            "Le montant de la prime d'assurance est de 500 euros.",
            "Le contrat couvre les dommages matériels.",
            "La franchise applicable est de 300 euros.",
            "Les exclusions de garantie sont listées à l'article 5.",
            "La date d'effet du contrat est le 1er janvier 2025.",
        ],
    })


class TestRetrieve:
    def test_returns_dataframe(self, sample_df):
        result = retrieve(sample_df, "montant prime")
        assert isinstance(result, pd.DataFrame)

    def test_keyword_filtering(self, sample_df):
        result = retrieve(sample_df, "franchise")
        assert len(result) >= 1
        assert "franchise" in result["text"].iloc[0].lower()

    def test_top_k_respected(self, sample_df):
        result = retrieve(sample_df, "contrat", top_k=2)
        assert len(result) <= 2

    def test_no_match_returns_empty(self, sample_df):
        result = retrieve(sample_df, "xyzqwerty")
        assert result.empty

    def test_raises_without_text_column(self):
        bad_df = pd.DataFrame({"content": ["hello"]})
        with pytest.raises(ValueError, match="text"):
            retrieve(bad_df, "hello")
