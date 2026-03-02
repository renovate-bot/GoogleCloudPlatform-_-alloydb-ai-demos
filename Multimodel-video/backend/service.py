
"""
Multi-Model Video Semantic Search 

This application demonstrates text → video semantic search using:
- Vertex AI Multimodal Embeddings (1408-D vectors for text/images/video).
- AlloyDB (PostgreSQL-compatible) with pgvector for vector similarity.
- Session-level ANN tuning (IVFFlat / HNSW) via GUCs.
- Transparency features: server-side query snapshot (pg_stat_activity)
  and client-side parameterized SQL preview.

"""

import os
import io
import warnings
from typing import Optional, List, Dict, Any, Tuple, Union
import pandas as pd
import numpy as np
import vertexai
from vertexai.vision_models import MultiModalEmbeddingModel
from sqlalchemy import text
import traceback

from db import AlloyDBClient
from config import ALLOYDB_TABLE_SCHEMA, PROJECT_ID, VERTEX_LOCATION, TOP_K_DEFAULT, SIM_THRESHOLD_DEFAULT, IVF_FLAT_PROBES, HNSW_EF_SEARCH, logger
from utils import gcs_uri_to_public_url, preview_sql_for_display, check_public_url_head


def _init_vertex() -> MultiModalEmbeddingModel:
    """Initialize Vertex AI client and return the multimodal embedding model.

    Returns:
        MultiModalEmbeddingModel: The Vertex AI multimodal embedding model.

    Raises:
        RuntimeError: If PROJECT_ID is unset.
    """
    if not PROJECT_ID:
        raise RuntimeError("PROJECT_ID / GCP_PROJECT not set in environment or config.py.")
    vertexai.init(project=PROJECT_ID, location=VERTEX_LOCATION)
    return MultiModalEmbeddingModel.from_pretrained("multimodalembedding@001")

# --- Helper: parse pgvector output into float32 numpy array ---
def _parse_vector_to_float32(v) -> np.ndarray:
    """Normalize various pgvector formats to a NumPy float32 array.

    Supports:
      - list/tuple/ndarray (already numeric)
      - string literal "[...]" (comma separated)
      - bytes/memoryview (decoded to UTF-8 then parsed)

    Args:
        v: The value from the `vector` column.

    Returns:
        np.ndarray: Parsed float32 array of shape (d,).
    """
    # Already numeric sequences
    if isinstance(v, (list, tuple, np.ndarray)):
        arr = np.asarray(v, dtype=np.float32)
        return arr

    # Decode bytes-like values
    if isinstance(v, (bytes, bytearray, memoryview)):
        try:
            v = bytes(v).decode("utf-8", errors="ignore")
        except Exception:
            v = str(v)

    # Now treat as string form like "[0.1,0.2,...]"
    s = str(v).strip()
    if s.startswith("[") and s.endswith("]"):
        s = s[1:-1]  # strip brackets

    # Parse by commas; fallback to whitespace
    arr = np.fromstring(s, sep=",", dtype=np.float32)
    if arr.size == 0:
        arr = np.fromstring(s, sep=" ", dtype=np.float32)
    return arr

# --- MMR re-ranking: reduce redundancy while keeping relevance ---
def mmr_rerank(query_vec: np.ndarray, item_vecs: np.ndarray, k: int, lam: float = 0.7):
    """Apply Maximal Marginal Relevance (MMR) to reduce redundancy in results.

    MMR selects items that maximize relevance to the query while penalizing similarity
    to already selected items.

    Args:
        query_vec: (d,) query embedding.
        item_vecs: (N, d) candidate embeddings.
        k: Number of items to select.
        lam: Relevance-diversity tradeoff parameter in [0, 1].

    Returns:
        List[int]: Indices of selected items in MMR order.
    """
    def cos(a: np.ndarray, b: np.ndarray) -> float:
        return float((a @ b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-12))
    sims_to_query = np.array([cos(query_vec, v) for v in item_vecs], dtype=np.float32)
    selected, candidates = [], list(range(len(item_vecs)))
    while len(selected) < min(k, len(item_vecs)):
        if not selected:
            next_idx = int(np.argmax(sims_to_query))
        else:
            max_sim_to_sel = np.array([
                max(cos(item_vecs[i], item_vecs[j]) for j in selected)
                for i in candidates
            ], dtype=np.float32)
            scores = lam * sims_to_query[candidates] - (1.0 - lam) * max_sim_to_sel
            next_idx = candidates[int(np.argmax(scores))]
        selected.append(next_idx)
        candidates.remove(next_idx)
    return selected

# ----------------------------
# Session-level ANN tuning (pgvector) via driver-level SQL
# ----------------------------
def apply_ann_settings(conn, ivfflat_probes: int, hnsw_ef_search: int) -> Tuple[str, str]:
    """Apply ANN-related GUCs (`ivfflat.probes`, `hnsw.ef_search`) for the session.

    Uses `exec_driver_sql()` with DBAPI param style to avoid bind-parameter issues
    when setting session variables.

    Args:
        conn: Active SQLAlchemy connection.
        ivfflat_probes: Number of IVF lists to probe (0 to skip setting).
        hnsw_ef_search: HNSW search breadth (0 to skip setting).

    Returns:
        Tuple[str, str]: Effective values for (ivfflat.probes, hnsw.ef_search).
    """
    if ivfflat_probes > 0:
        conn.execute(
            # text("SELECT set_config('ivfflat.probes', :val::text, false)"),
            text("SELECT set_config('ivfflat.probes', :val, false)"),
            {"val": str(ivfflat_probes)},
        )
    if hnsw_ef_search > 0:
        conn.execute(
            # text("SELECT set_config('hnsw.ef_search', :val::text, false)"),
            text("SELECT set_config('hnsw.ef_search', :val, false)"),
            {"val": str(hnsw_ef_search)},
        )

    probes = conn.execute(text("SHOW ivfflat.probes")).scalar()
    ef_search = conn.execute(text("SHOW hnsw.ef_search")).scalar()
    return probes, ef_search

API_BASE = "/videos"  # adjust if you mount routers or have a base path

def multimodal_video_search(
    db_engine,
    query: Union[str, bytes],
    label_filter: Optional[str],
    duration: Optional[int],
    input_type: str,
) -> List[Dict[str, Any]]:
    """
    Multimodal video search:
      - Computes query embedding server-side in AlloyDB AI (no large vector params).
      - Applies filters and ANN tuning.
      - Thresholds by similarity, then MMR re-ranks results to reduce redundancy.
      - Returns JSON-safe search results and a SQL preview (for UI).

    Returns:
      A dict with "sql_query" and "multimodal_video_search" (list of hits),
      or an error dict in case of failure.
    """
    try:
        
        # 1) Duration bounds (use None → COALESCE will fall back to column)
        min_dur = 0
        max_dur = duration or 0

        # 2) Optional ANN tuning per session (keep if ivfflat/hnsw indexes are present)
        with db_engine.connect() as conn:
            _probes, _ef_search = apply_ann_settings(conn, IVF_FLAT_PROBES, HNSW_EF_SEARCH)

        # 3) Server-side embedding & filtered vector search in AlloyDB
        #    Avoid HTML entities; use the real "<=>"
        #  /*
        # Retrieves video metadata and embeddings for similarity search.
        # Computes cosine similarity between stored embeddings and a query embedding
        # generated by Google ML's multimodalembedding@001 model.
        # Filters by optional label and duration range, orders by similarity, and limits results.
        # */ 
        sql = ''
        if input_type == 'text':
            logger.info(f"Input type is identified as {input_type}, Constructing SQL query for the input type {input_type}" )
            sql = text(f"""
                WITH q AS (
                SELECT google_ml.text_embedding(
                        model_id => 'multimodalembedding@001',
                        content  => CAST(:q AS text)
                        )::vector AS qvec
                )
                SELECT
                    m.id,
                    m.file_name,
                    m.label,
                    m.duration_sec,
                    e.embedding,
                    1 - (e.embedding <=> q.qvec) AS cosine_similarity,
                    'gs://alloydb-multimodel/data/' || m.label || '/' ||
                    regexp_replace(m.file_name, '^.*[\\\/]', '') AS gcs_uri
                FROM {ALLOYDB_TABLE_SCHEMA}.video_embeddings e
                JOIN {ALLOYDB_TABLE_SCHEMA}.video_meta m
                ON m.id = e.video_id
                CROSS JOIN q
                WHERE
                    (CAST(:label AS text) IS NULL OR m.label ILIKE '%' || CAST(:label AS text) || '%')
                AND (CAST(:min_dur AS int) IS NULL OR (m.duration_sec IS NOT NULL AND m.duration_sec >= CAST(:min_dur AS int)))
                AND (CAST(:max_dur AS int) IS NULL OR (m.duration_sec IS NOT NULL AND m.duration_sec <= CAST(:max_dur AS int)))
                ORDER BY
                    e.embedding <=> q.qvec ASC
                LIMIT CAST(:k AS int);
            """)
            params = {
                "q": query,  # plain text prompt; AlloyDB computes embedding server-side
                "k": TOP_K_DEFAULT,
                "label": label_filter,
                "min_dur": int(min_dur),
                "max_dur": int(max_dur),
            }
            logger.info(f"Input parameters used:{params}")
        else:
            logger.info(f"Input type is identified as {input_type}, Constructing SQL query for the input type {input_type}" )
            sql = text(f"""WITH q AS (
                SELECT google_ml.image_embedding(
                        model_id => 'multimodalembedding@001',
                        image    => CAST(:image_base64 AS text),
                        mimetype => CAST(:mimetype AS text)
                    )::vector AS qvec
            )
            SELECT
                m.id,
                m.file_name,
                m.label,
                m.duration_sec,
                -- e.embedding,
                1 - (e.embedding <=> q.qvec) AS cosine_similarity,
                'gs://alloydb-multimodel/data/' || m.label || '/' ||
                regexp_replace(m.file_name, '^.*[\\\/]', '') AS gcs_uri
            FROM {ALLOYDB_TABLE_SCHEMA}.video_embeddings e
            JOIN {ALLOYDB_TABLE_SCHEMA}.video_meta m
            ON m.id = e.video_id
            CROSS JOIN q
            WHERE
                (CAST(:label AS text) IS NULL
                OR m.label ILIKE '%' || CAST(:label AS text) || '%')
            AND (CAST(:min_dur AS int) IS NULL
                OR (m.duration_sec IS NOT NULL AND m.duration_sec >= CAST(:min_dur AS int)))
            AND (CAST(:max_dur AS int) IS NULL
                OR (m.duration_sec IS NOT NULL AND m.duration_sec <= CAST(:max_dur AS int)))
            ORDER BY
                e.embedding <=> q.qvec ASC
            LIMIT CAST(:k AS int);
            """)
            params = {
                "image_base64": query,
                "mimetype": input_type,
                "k": TOP_K_DEFAULT,
                "label": label_filter,
                "min_dur": int(min_dur),
                "max_dur": int(max_dur),
            }


        with db_engine.connect() as conn:
            rows = conn.execute(sql, params).mappings().all()


        # 4) Threshold filter (keep JSON-safe)
        rows = [r for r in rows if float( r["cosine_similarity"]) >= SIM_THRESHOLD_DEFAULT]
        if not rows:
            # Provide preview for UI even if no hits
            sql_query = preview_sql_for_display(sql, params, db_engine)
            return {"sql_query": sql_query, "multimodal_video_search": []}

        logger.info(f"Query executed successfully")

        # 5) Build JSON-safe result: **do not include raw bytes**
        results: List[Dict[str, Any]] = []
        for dict_entry in rows:
            # Build public URL from gs:// path
            public_url = gcs_uri_to_public_url(dict_entry["file_name"])

            # HEAD check: public readability + Content-Type
            ok, ctype, status = check_public_url_head(public_url)
            if not ok:
                public_url = ""

            results.append({
                "id": int(dict_entry["id"]),
                "filename": dict_entry["file_name"],
                "similarity": float(dict_entry["cosine_similarity"]),
                "label": dict_entry["label"],
                "duration": int(dict_entry["duration_sec"]),
                # Keep the canonical API URL for proxy mode; frontend may switch to GCS signed URL instead.
                "url": f"{API_BASE}/{int(dict_entry["id"])}",     # e.g., "/videos/{id}"
                "public_url": public_url,            # direct GCS HTTP URL if public
            })

        # 6) SQL preview for UI (dialect-aware; uses bindparams + compiler)
        sql_query = preview_sql_for_display(sql, params, db_engine)

        search_results: Dict[str, Any] = {
            "sql_query": sql_query,
            "multimodal_video_search": results,
        }
        logger.info(f" Output Search results:{search_results}")
        return search_results

    except Exception as e:
        exception_message = str(e)
        traceback_details = traceback.format_exc()
        logger.error(f"Exception Message: {exception_message}")
        logger.error(f"Traceback Details: {traceback_details}")
        return {
            "error": f"Error processing the query. {exception_message}, Traceback: {traceback_details}"
        }

def categories_duration(db_engine) -> List[Dict[str, Any]]:
    """Return min/max video durations per label.

    Args:
        db_engine: SQLAlchemy engine connected to the DB.

    Returns:
        Mapping: {label: {"min_duration_sec": int, "max_duration_sec": int}}
    """
    sql = text(f"""
        SELECT
            label AS category,
            MIN(duration_sec) AS min_duration_sec,
            MAX(duration_sec) AS max_duration_sec
        FROM {ALLOYDB_TABLE_SCHEMA}.video_meta
        WHERE label IS NOT NULL
        AND label <> ''
        AND duration_sec IS NOT NULL
        GROUP BY label
        ORDER BY label ASC;
    """)
    try:
        with db_engine.connect() as conn:
            rows = conn.execute(sql).fetchall()
        result = {}
        
        for category, min_dur, max_dur in rows:
            result[category] = {
                "min_duration_sec": int(min_dur),
                "max_duration_sec": int(max_dur),
            }
        return result
    except Exception as e:
        exception_message = str(e)
        traceback_details = traceback.format_exc()
        logger.error(f"Exception Message: {exception_message}")
        logger.error(f"Traceback Details: {traceback_details}")
        return {
            "error": f"Error processing the query. {exception_message}, Traceback: {traceback_details}"
        }