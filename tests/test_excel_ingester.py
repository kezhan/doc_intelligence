"""Tests for TODO-019: Excel ingestion."""

import sqlite3
import tempfile
import pandas as pd
import pytest
from pathlib import Path

from docpipeline.parsing.excel.ingester import ingest_excel, _safe_name, _clean_df


class TestSafeName:
    def test_basic(self):
        assert _safe_name("My Sheet!") == "my_sheet"

    def test_spaces(self):
        assert _safe_name("Total Amount") == "total_amount"

    def test_empty(self):
        assert _safe_name("") == "sheet"


class TestCleanDf:
    def test_drops_all_na_rows(self):
        df = pd.DataFrame({"a": [1, None], "b": [2, None]})
        cleaned = _clean_df(df)
        assert len(cleaned) == 1

    def test_renames_columns(self):
        df = pd.DataFrame({"My Column!": [1, 2]})
        cleaned = _clean_df(df)
        assert "my_column" in cleaned.columns


class TestIngestExcel:
    def _make_xlsx(self, path: Path) -> None:
        df = pd.DataFrame({"Name": ["Alice", "Bob"], "Amount": [100, 200]})
        with pd.ExcelWriter(str(path)) as w:
            df.to_excel(w, sheet_name="Data", index=False)

    def test_sqlite_output(self):
        tmpdir = tempfile.mkdtemp()
        try:
            xlsx = Path(tmpdir) / "test.xlsx"
            db = Path(tmpdir) / "test.db"
            self._make_xlsx(xlsx)

            result = ingest_excel(xlsx, db, output_format="sqlite")
            assert result == db
            assert db.exists()

            conn = sqlite3.connect(str(db))
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            conn.close()
            assert len(tables) >= 1
        finally:
            import shutil, gc
            gc.collect()  # release any remaining file handles on Windows
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_invalid_format_raises(self):
        with pytest.raises(ValueError, match="output_format"):
            ingest_excel("fake.xlsx", output_format="csv")
