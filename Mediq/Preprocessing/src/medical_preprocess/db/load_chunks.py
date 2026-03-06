from __future__ import annotations
from typing import Dict, List
import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Connection

EXPECTED_COLUMNS = ["disease_name", "chunk_content", "chunk_num", "chunk_page_no"]

def load_records_from_csv(csv_path: str) -> List[Dict[str, object]]:
    df = pd.read_csv(csv_path)
    missing = [c for c in EXPECTED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"CSV missing required columns: {missing}")
    df["disease_name"] = df["disease_name"].astype(str)
    df["chunk_content"] = df["chunk_content"].astype(str)
    df["chunk_num"] = pd.to_numeric(df["chunk_num"], errors="coerce").fillna(0).astype(int)
    df["chunk_page_no"] = pd.to_numeric(df["chunk_page_no"], errors="coerce").fillna(0).astype(int)
    return df.to_dict(orient="records")


def insert_chunks(conn: Connection, fq_table: str, rows: List[Dict[str, object]]) -> int:
    if not rows:
        return 0
    rows = sorted(rows, key=lambda r: (r["disease_name"], r["chunk_page_no"], r["chunk_num"]))
    sql = text(
        f"""
        INSERT INTO {fq_table} (disease_name, chunk_content, chunk_num, chunk_page_no)
        VALUES (:disease_name, :chunk_content, :chunk_num, :chunk_page_no);
        """
    )
    total = 0
    for i in range(0, len(rows), 1000):
        batch = rows[i:i+1000]
        conn.execute(sql, batch)
        total += len(batch)
    return total


def update_embeddings(conn: Connection, fq_table: str, model_id: str = "text-embedding-005") -> int:
    sql = text(
        f"""
        UPDATE {fq_table}
        SET chunk_embedding = google_ml.embedding(model_id => :model_id, content => chunk_content)
        WHERE chunk_content IS NOT NULL AND chunk_content <> '' AND chunk_embedding IS NULL;
        """
    )
    res = conn.execute(sql, {"model_id": model_id})
    try:
        return res.rowcount or 0
    except Exception:
        return 0
