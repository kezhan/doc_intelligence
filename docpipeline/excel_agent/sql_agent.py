"""
TODO-020 — Natural-language SQL agent for Excel files.

Pipeline:
  TODO-019 : Excel → SQLite  (parsing.excel.ingester)
  TODO-020 : NL question → SQL → execute → answer  (this module)
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from ..generation.llm_client import LLMClient, LLMConfig
from ..parsing.excel.ingester import ingest_excel


_SYSTEM = (
    "You are an expert SQL analyst. "
    "Given a SQLite database schema and a user question in natural language, "
    "write the minimal SQL query that answers the question. "
    "Return ONLY the SQL query — no explanations, no markdown fences."
)

_PROMPT_TEMPLATE = """\
Database schema:
{schema}

User question: {question}

Write a SQLite SQL query that answers this question.
"""


@dataclass
class AgentResult:
    question: str
    sql: str
    answer: pd.DataFrame
    explanation: str = ""


class ExcelSQLAgent:
    """
    TODO-020 — Query an Excel file with natural language.

    Usage:
        agent = ExcelSQLAgent("data.xlsx")
        result = agent.ask("Which row has the highest amount?")
        print(result.sql)
        print(result.answer)
    """

    def __init__(
        self,
        xlsx_path: str | Path,
        *,
        config: LLMConfig | None = None,
        db_path: str | Path | None = None,
    ) -> None:
        self.xlsx_path = Path(xlsx_path)
        self.config = config or LLMConfig.openai()
        self.db_path = Path(db_path) if db_path else self.xlsx_path.with_suffix(".db")
        self._schema: str | None = None

        # Ingest on first use
        if not self.db_path.exists():
            ingest_excel(self.xlsx_path, self.db_path, output_format="sqlite")

    def ask(self, question: str) -> AgentResult:
        """
        TODO-020 — Answer a natural-language question about the Excel file.

        Input : question in natural language
        Output: AgentResult with SQL query + result DataFrame
        """
        schema = self._get_schema()
        prompt = _PROMPT_TEMPLATE.format(schema=schema, question=question)

        client = LLMClient(self.config)
        resp = client.complete(prompt, system=_SYSTEM)
        sql = _clean_sql(resp.content)

        answer = self._execute(sql)
        return AgentResult(question=question, sql=sql, answer=answer)

    # ── schema ────────────────────────────────────────────────────────────────

    def _get_schema(self) -> str:
        if self._schema:
            return self._schema
        conn = sqlite3.connect(str(self.db_path))
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in cursor.fetchall()]
            lines: list[str] = []
            for table in tables:
                cursor.execute(f"PRAGMA table_info({table})")  # noqa: S608
                cols = cursor.fetchall()
                col_defs = ", ".join(f"{c[1]} {c[2]}" for c in cols)
                # Attach a sample row for context
                cursor.execute(f"SELECT * FROM {table} LIMIT 1")  # noqa: S608
                sample = cursor.fetchone()
                lines.append(f"Table: {table}({col_defs})")
                if sample:
                    lines.append(f"  Sample: {dict(zip([c[1] for c in cols], sample))}")
            self._schema = "\n".join(lines)
        finally:
            conn.close()
        return self._schema

    # ── execution ─────────────────────────────────────────────────────────────

    def _execute(self, sql: str) -> pd.DataFrame:
        conn = sqlite3.connect(str(self.db_path))
        try:
            return pd.read_sql_query(sql, conn)
        except Exception as exc:
            return pd.DataFrame({"error": [str(exc)], "sql": [sql]})
        finally:
            conn.close()

    def refresh(self) -> None:
        """Re-ingest the Excel file (call after the source file changes)."""
        self._schema = None
        ingest_excel(self.xlsx_path, self.db_path, output_format="sqlite")


# ── helpers ───────────────────────────────────────────────────────────────────

def _clean_sql(content: str) -> str:
    content = content.strip()
    fence = re.search(r"```(?:sql)?\s*([\s\S]+?)\s*```", content, re.IGNORECASE)
    if fence:
        return fence.group(1).strip()
    return content
