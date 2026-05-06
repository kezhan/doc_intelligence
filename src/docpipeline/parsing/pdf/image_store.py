"""
Déduplication d'images entre documents — section 3.1 du document Faseya.

Un logo répété sur 100 contrats ne devrait être stocké qu'une fois.
On utilise un hash MD5 du contenu binaire pour identifier les doublons,
plus un index SQLite pour la traçabilité.
"""

from __future__ import annotations

import hashlib
import logging
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)


@dataclass
class CrossDocImageStore:
    """
    Magasin d'images dédupliquées entre tous les documents traités.

    Schéma SQLite :
      images(hash, format, width, height, path)              — fichier unique
      occurrences(hash, document, page, x0, y0, x1, y1)      — toutes les apparitions

    Usage :
        store = CrossDocImageStore.open("images.db", "images_dir/")
        store.ingest_pdf("contrat1.pdf")
        store.ingest_pdf("contrat2.pdf")
        print(store.stats())  # {'unique': 12, 'occurrences': 47}
    """
    db_path:    Path
    images_dir: Path

    @classmethod
    def open(
        cls,
        db_path:    str | Path,
        images_dir: str | Path,
    ) -> "CrossDocImageStore":
        db_path    = Path(db_path)
        images_dir = Path(images_dir)
        images_dir.mkdir(parents=True, exist_ok=True)

        with sqlite3.connect(str(db_path)) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS images (
                    hash    TEXT PRIMARY KEY,
                    format  TEXT,
                    width   INTEGER,
                    height  INTEGER,
                    path    TEXT
                );
                CREATE TABLE IF NOT EXISTS occurrences (
                    hash      TEXT,
                    document  TEXT,
                    page      INTEGER,
                    x0        REAL,
                    y0        REAL,
                    x1        REAL,
                    y1        REAL,
                    FOREIGN KEY (hash) REFERENCES images(hash)
                );
                CREATE INDEX IF NOT EXISTS idx_occ_hash ON occurrences(hash);
                CREATE INDEX IF NOT EXISTS idx_occ_doc  ON occurrences(document);
            """)
        return cls(db_path=db_path, images_dir=images_dir)

    def ingest_pdf(self, pdf_path: str | Path) -> dict[str, int]:
        """
        Ajouter toutes les images d'un PDF au store, sans doublons.

        Returns: {'new': N, 'duplicates': M}
        """
        pdf_path = Path(pdf_path)
        new_imgs = 0
        dups     = 0

        doc = fitz.open(str(pdf_path))
        try:
            with self._connect() as conn:
                for page_num, page in enumerate(doc, start=1):
                    for img_info in page.get_images(full=True):
                        xref = img_info[0]
                        try:
                            base = doc.extract_image(xref)
                        except Exception:
                            continue
                        img_bytes = base["image"]
                        img_hash  = hashlib.md5(img_bytes).hexdigest()
                        bbox      = self._image_bbox(page, xref)

                        existing = conn.execute(
                            "SELECT path FROM images WHERE hash = ?", (img_hash,)
                        ).fetchone()

                        if existing:
                            dups += 1
                        else:
                            fmt  = base["ext"]
                            path = self.images_dir / f"{img_hash[:12]}.{fmt}"
                            path.write_bytes(img_bytes)
                            from PIL import Image
                            import io
                            with Image.open(io.BytesIO(img_bytes)) as pil:
                                w, h = pil.size
                            conn.execute(
                                "INSERT INTO images (hash, format, width, height, path) "
                                "VALUES (?, ?, ?, ?, ?)",
                                (img_hash, fmt, w, h, str(path))
                            )
                            new_imgs += 1

                        conn.execute(
                            "INSERT INTO occurrences "
                            "(hash, document, page, x0, y0, x1, y1) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?)",
                            (img_hash, str(pdf_path.name), page_num,
                             *(bbox or (None, None, None, None)))
                        )
                conn.commit()
        finally:
            doc.close()

        logger.info("Ingest %s : new=%d, duplicates=%d", pdf_path.name, new_imgs, dups)
        return {"new": new_imgs, "duplicates": dups}

    def stats(self) -> dict[str, int]:
        """Retourne les compteurs globaux."""
        with self._connect() as conn:
            n_unique = conn.execute("SELECT COUNT(*) FROM images").fetchone()[0]
            n_occ    = conn.execute("SELECT COUNT(*) FROM occurrences").fetchone()[0]
            n_docs   = conn.execute(
                "SELECT COUNT(DISTINCT document) FROM occurrences"
            ).fetchone()[0]
        return {"unique_images": n_unique, "total_occurrences": n_occ, "documents": n_docs}

    def find_logo_candidates(self, min_documents: int = 2) -> list[dict]:
        """
        Identifier les images apparaissant dans plusieurs documents (= logos probables).
        """
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT i.hash, i.path, i.width, i.height,
                       COUNT(DISTINCT o.document) AS doc_count
                FROM images i
                JOIN occurrences o ON o.hash = i.hash
                GROUP BY i.hash
                HAVING doc_count >= ?
                ORDER BY doc_count DESC;
            """, (min_documents,)).fetchall()
        return [
            {"hash": h, "path": p, "width": w, "height": h2, "documents": d}
            for h, p, w, h2, d in rows
        ]

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(str(self.db_path))
        try:
            yield conn
        finally:
            conn.close()

    @staticmethod
    def _image_bbox(page: fitz.Page, xref: int) -> tuple | None:
        for img in page.get_image_info(xrefs=True):
            if img.get("xref") == xref:
                bbox = img["bbox"]
                return (round(bbox[0], 2), round(bbox[1], 2),
                        round(bbox[2], 2), round(bbox[3], 2))
        return None
