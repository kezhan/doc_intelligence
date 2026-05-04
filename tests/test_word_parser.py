"""Tests for TODO-011: Word native parser."""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from docpipeline.parsing.word.parser import _heading_level, _docx_table_to_df


class TestHeadingLevel:
    def test_heading1(self):
        para = MagicMock()
        para.style.name = "Heading 1"
        assert _heading_level(para) == 1

    def test_heading3(self):
        para = MagicMock()
        para.style.name = "Heading 3"
        assert _heading_level(para) == 3

    def test_title(self):
        para = MagicMock()
        para.style.name = "Title"
        assert _heading_level(para) == 0

    def test_normal_paragraph(self):
        para = MagicMock()
        para.style.name = "Normal"
        assert _heading_level(para) is None


class TestDocxTableToDf:
    def _make_table(self, rows: list[list[str]]):
        table = MagicMock()
        table.rows = []
        for row_data in rows:
            row = MagicMock()
            row.cells = [MagicMock(text=c) for c in row_data]
            table.rows.append(row)
        return table

    def test_basic_table(self):
        table = self._make_table([
            ["Name", "Amount"],
            ["Alice", "100"],
            ["Bob", "200"],
        ])
        df = _docx_table_to_df(table)
        assert list(df.columns) == ["Name", "Amount"]
        assert len(df) == 2
        assert df.iloc[0]["Name"] == "Alice"

    def test_empty_table(self):
        table = MagicMock()
        table.rows = []
        df = _docx_table_to_df(table)
        assert df.empty
