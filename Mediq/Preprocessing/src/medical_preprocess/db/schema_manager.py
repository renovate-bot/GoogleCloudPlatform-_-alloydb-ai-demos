from __future__ import annotations
from typing import Sequence
from sqlalchemy import text
from sqlalchemy.engine import Connection

EXTENSIONS_SQL: Sequence[str] = (
    "CREATE EXTENSION IF NOT EXISTS google_ml_integration;",
    "CREATE EXTENSION IF NOT EXISTS vector;",
    "CREATE EXTENSION IF NOT EXISTS alloydb_scann;",
)

def ensure_extensions(conn: Connection) -> None:
    for sql in EXTENSIONS_SQL:
        try:
            conn.execute(text(sql))
        except Exception as e:
            if "alloydb_scann" in sql:
                print(f"[note] alloydb_scann extension not available: {e}")
            else:
                raise


def ensure_table_and_columns(conn: Connection, fq_table: str) -> None:
    ddl = (
        f"""
        CREATE TABLE IF NOT EXISTS {fq_table} (
            id BIGSERIAL PRIMARY KEY,
            disease_name TEXT,
            chunk_content TEXT,
            chunk_num INTEGER,
            chunk_page_no INTEGER,
            chunk_embedding VECTOR(768)
        );
        """,
    )
    for sql in ddl:
        conn.execute(text(sql))


def ensure_images_table(conn: Connection, fq_table: str) -> None:
    """
    Create the disease_images_info table .
    Columns:
      - disease_name TEXT
      - caption_text TEXT
      - disease_image_base64 TEXT
      - disease_name_embedding VECTOR(768)  
    """
    sql = f"""
    CREATE TABLE IF NOT EXISTS {fq_table} (
      disease_name TEXT,
      caption_text TEXT,
      disease_image_base64 TEXT,
      disease_name_embedding VECTOR(768)
    );
    """
    conn.execute(text(sql))


def create_scann_index(conn: Connection, fq_table: str) -> None:
    idx = f"{fq_table.replace('.', '_')}_chunk_embed_idx"
    conn.execute(text(
        f"CREATE INDEX IF NOT EXISTS {idx} ON {fq_table} USING scann (chunk_embedding cosine) WITH (num_leaves=20);"
    ))
