"""
TODO-023 — Migration retrieval Python → SQL.

Backend SQLite pour le retrieval. Le DataFrame du parsing est stocké en
table SQL ; les requêtes utilisent FTS5 (full-text search) pour la
performance et la lisibilité.

Avantages vs Python :
- Performance constante quel que soit le volume
- Filtrage cross-pages trivial
- Pas de chargement du DataFrame complet en mémoire
"""

from __future__ import annotations

import logging
import re
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class SQLRetriever:
    """
    Retrieval backend SQL — drop-in replacement de retrieval/retriever.py.

    Usage :
        backend = SQLRetriever.from_dataframe(df, db_path="doc.db")
        results = backend.retrieve("franchise garantie", top_k=10)
    """
    db_path:    Path
    table_name: str = "documents"

    @classmethod
    def from_dataframe(
        cls,
        df:         pd.DataFrame,
        db_path:    str | Path,
        table_name: str = "documents",
        *,
        with_fts:   bool = True,
    ) -> "SQLRetriever":
        """
        Persister un DataFrame dans SQLite + créer un index FTS5.

        Input  : DataFrame (doit contenir une colonne 'text')
        Output : SQLRetriever prêt à requêter
        """
        if "text" not in df.columns:
            raise ValueError("Le DataFrame doit contenir une colonne 'text'")

        db_path = Path(db_path)
        with sqlite3.connect(str(db_path)) as conn:
            df.to_sql(table_name, conn, if_exists="replace", index=True,
                      index_label="row_id")

            if with_fts:
                # Index FTS5 sur la colonne text — recherche full-text rapide
                conn.executescript(f"""
                    DROP TABLE IF EXISTS {table_name}_fts;
                    CREATE VIRTUAL TABLE {table_name}_fts USING fts5(
                        text, content='{table_name}', content_rowid='row_id'
                    );
                    INSERT INTO {table_name}_fts(rowid, text)
                        SELECT row_id, text FROM {table_name};
                """)

        logger.info("SQLRetriever créé : %s (%d lignes)", db_path, len(df))
        return cls(db_path=db_path, table_name=table_name)

    def retrieve(
        self,
        query:    str,
        *,
        top_k:    int  = 20,
        use_fts:  bool = True,
    ) -> pd.DataFrame:
        """
        Rechercher les lignes pertinentes via SQL.

        Input  : requête utilisateur
        Output : DataFrame des lignes les plus pertinentes
        """
        if use_fts:
            return self._retrieve_fts(query, top_k)
        return self._retrieve_like(query, top_k)

    def _retrieve_fts(self, query: str, top_k: int) -> pd.DataFrame:
        """Recherche via FTS5 (rapide, scoring intégré)."""
        clean_query = _sanitize_fts_query(query)
        if not clean_query:
            return pd.DataFrame()

        sql = f"""
            SELECT d.*, fts.rank AS _score
            FROM {self.table_name}_fts AS fts
            JOIN {self.table_name} AS d ON d.row_id = fts.rowid
            WHERE {self.table_name}_fts MATCH ?
            ORDER BY fts.rank
            LIMIT ?;
        """
        with self._connect() as conn:
            try:
                df = pd.read_sql_query(sql, conn, params=(clean_query, top_k))
            except sqlite3.OperationalError:
                # Fallback LIKE si FTS indisponible
                return self._retrieve_like(query, top_k)
        return df.drop(columns=["_score"], errors="ignore")

    def _retrieve_like(self, query: str, top_k: int) -> pd.DataFrame:
        """Fallback recherche LIKE (lent mais universel)."""
        tokens = [t for t in re.findall(r"\w+", query) if len(t) > 2]
        if not tokens:
            return pd.DataFrame()

        where = " OR ".join(f"text LIKE ?" for _ in tokens)
        sql   = f"SELECT * FROM {self.table_name} WHERE {where} LIMIT ?;"
        params = [f"%{t}%" for t in tokens] + [top_k]

        with self._connect() as conn:
            return pd.read_sql_query(sql, conn, params=params)

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(str(self.db_path))
        try:
            yield conn
        finally:
            conn.close()


def _sanitize_fts_query(query: str) -> str:
    """Nettoyer la requête utilisateur pour FTS5 (échapper les opérateurs)."""
    tokens = re.findall(r"\w+", query)
    return " OR ".join(f'"{t}"' for t in tokens if len(t) > 2)
