
from __future__ import annotations
from typing import Dict, List
import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Connection

EXPECTED_COLUMNS = ["disease_name", "caption_text", "disease_image_base64"]

def load_image_rows_from_csv(csv_path: str) -> List[Dict[str, object]]:
    df = pd.read_csv(csv_path)
    missing = [c for c in EXPECTED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"CSV missing required columns: {missing}")
    for c in EXPECTED_COLUMNS:
        df[c] = df[c].astype(str).where(df[c].notna(), None)
    return df.to_dict(orient="records")


def insert_images(conn: Connection, fq_table: str, rows: List[Dict[str, object]]) -> int:
    if not rows:
        return 0
    rows = sorted(rows, key=lambda r: (r.get("disease_name") or "", r.get("caption_text") or ""))
    sql = text(
        f"""
        INSERT INTO {fq_table} (disease_name, caption_text, disease_image_base64)
        VALUES (:disease_name, :caption_text, :disease_image_base64);
        """
    )
    batch = 1000
    total = 0
    for i in range(0, len(rows), batch):
        part = rows[i:i+batch]
        conn.execute(sql, part)
        total += len(part)
    return total


def update_disease_name_embeddings(conn: Connection, fq_table: str, model_id: str = "text-embedding-005") -> int:
    sql = text(
        f"""
        UPDATE {fq_table}
           SET disease_name_embedding = google_ml.embedding(model_id => :model_id, content => disease_name);
        """
    )
    res = conn.execute(sql, {"model_id": model_id})
    try:
        return res.rowcount or 0
    except Exception:
        return 0
