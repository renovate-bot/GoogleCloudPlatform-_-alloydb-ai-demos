# pipeline/embed_videos.py
"""Embed pending videos and write vectors to AlloyDB (pgvector).

This pipeline:
  - Reads pending videos either from GCS (video_assets.gcs_uri) or BYTEA (video_blobs.video_data)
  - Samples ~N frames/sec, gets Vertex AI image embeddings, averages to one vector
  - Writes a single 1408-D vector per video_id to video_embeddings (idempotent)

Run:
  python -m pipeline.embed_videos \
    --schema alloydb_usecase \
    --frame-sample-per-sec 1.0 \
    --use-gcs true

Environment:
  PROJECT_ID / GCP_PROJECT    (required)
  LOCATION (default: us-central1)
"""

from __future__ import annotations

import argparse
import logging
import math
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Iterable, Optional, Tuple

import cv2
import numpy as np
import vertexai
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import DatabaseError

# Robust import across SDK variants
try:
    from vertexai.preview.vision_models import MultiModalEmbeddingModel, Image
except Exception:  # pragma: no cover
    from vertexai.vision_models import MultiModalEmbeddingModel, Image  # type: ignore

# Add project root
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from db import engine  # noqa: E402

# Optional GCS imports
try:
    from google.cloud import storage

    _HAS_GCS = True
except Exception:  # pragma: no cover
    _HAS_GCS = False


# ----------------------------
# Logging
# ----------------------------
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
)
LOGGER = logging.getLogger("embed_videos")


# ----------------------------
# Configuration
# ----------------------------
DEFAULT_LOCATION = os.getenv("LOCATION") or os.getenv("VERTEX_LOCATION", "us-central1")
DEFAULT_PROJECT = os.getenv("PROJECT_ID") or os.getenv("GCP_PROJECT")
DEFAULT_FPS_SAMPLE = float(os.getenv("FRAME_SAMPLE_PER_SEC", "1.0"))
EMBED_DIM = int(os.getenv("EMBED_DIM", "1408"))


# ----------------------------
# Utilities
# ----------------------------
def _set_search_path(conn: Connection, schema: str) -> None:
    """Ensure all queries hit the intended schema."""
    conn.exec_driver_sql(f"SET search_path TO {schema}, public")


def _retry(
    fn,
    *,
    attempts: int = 5,
    base_sleep_sec: float = 0.5,
    max_sleep_sec: float = 4.0,
    exceptions: Tuple[type, ...] = (Exception,),
):
    """Simple exponential backoff retry wrapper."""
    for i in range(attempts):
        try:
            return fn()
        except exceptions as exc:
            if i == attempts - 1:
                raise
            sleep = min(max_sleep_sec, base_sleep_sec * (2**i))
            LOGGER.warning("Retrying after error (%s): %s", type(exc).__name__, exc)
            time.sleep(sleep)


def _gcs_download_to_temp(gcs_uri: str) -> str:
    """Download object to a temp file and return its path."""
    if not _HAS_GCS:
        raise RuntimeError("google-cloud-storage not installed, cannot use GCS.")
    if not gcs_uri.startswith("gs://"):
        raise ValueError(f"Invalid GCS URI: {gcs_uri!r}")

    bucket_name, object_name = gcs_uri[5:].split("/", 1)
    client = storage.Client()

    def _do():
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
            client.bucket(bucket_name).blob(object_name).download_to_filename(tmp.name)
            return tmp.name

    return _retry(_do)


def _bytes_to_tempfile(video_bytes: bytes, suffix: str = ".mp4") -> str:
    """Write bytes to a temporary file and return the path."""
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(video_bytes)
        return tmp.name


def _init_vertex(project: str, location: str) -> MultiModalEmbeddingModel:
    vertexai.init(project=project, location=location)
    return MultiModalEmbeddingModel.from_pretrained("multimodalembedding@001")


def _sample_and_embed_video(
    model: MultiModalEmbeddingModel, video_path: str, *, frames_per_sec: float, fps_hint: Optional[float]
) -> Tuple[Optional[np.ndarray], int]:
    """Return (mean_embedding, sampled_frame_count)."""
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        LOGGER.warning("OpenCV cannot open: %s", video_path)
        return None, 0

    try:
        fps = float(cap.get(cv2.CAP_PROP_FPS)) or (fps_hint or 25.0)
        step = max(int(math.floor(fps / frames_per_sec)), 1)

        vectors: list[np.ndarray] = []
        f = 0
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if f % step == 0:
                ok2, buf = cv2.imencode(".jpg", frame)
                if not ok2:
                    f += 1
                    continue

                def _embed():
                    emb = model.get_embeddings(image=Image(image_bytes=buf.tobytes()))
                    return np.array(emb.image_embedding, dtype=np.float32)

                vec = _retry(_embed)
                if vec.size == EMBED_DIM:
                    vectors.append(vec)
            f += 1

        if not vectors:
            return None, 0
        mean_vec = np.mean(np.vstack(vectors), axis=0).astype(np.float32)
        return mean_vec, len(vectors)
    finally:
        cap.release()
        try:
            os.remove(video_path)
        except Exception:
            pass


def _to_pgvector_literal(vec: np.ndarray) -> str:
    return "[" + ",".join(f"{float(x):.8f}" for x in vec.tolist()) + "]"


# ----------------------------
# Core
# ----------------------------
def _fetch_pending_rows(schema: str, use_gcs: bool) -> Tuple[list[tuple], bool]:
    """Return rows to process and whether source is GCS."""
    rows: list[tuple] = []
    is_gcs = False

    sql_gcs = text(
        """
        SELECT m.id, a.gcs_uri, m.fps
        FROM video_meta m
        JOIN video_assets a ON a.video_id = m.id
        LEFT JOIN video_embeddings e ON e.video_id = m.id
        WHERE e.video_id IS NULL
        """
    )

    sql_bytes = text(
        """
        SELECT m.id, b.video_data, m.fps
        FROM video_meta m
        JOIN video_blobs b ON b.video_id = m.id
        LEFT JOIN video_embeddings e ON e.video_id = m.id
        WHERE e.video_id IS NULL
        """
    )

    with engine.connect() as conn:
        _set_search_path(conn, schema)
        if use_gcs and _HAS_GCS:
            try:
                rows = conn.execute(sql_gcs).fetchall()
                is_gcs = True
            except DatabaseError:
                LOGGER.info("video_assets not present; falling back to video_blobs.")
                rows = []
                is_gcs = False

        if not rows:
            rows = conn.execute(sql_bytes).fetchall()
            is_gcs = False

    return list(rows), is_gcs


def _persist_embedding(schema: str, video_id: int, vec_literal: str, frame_count: int) -> None:
    sql = text(
        """
        INSERT INTO video_embeddings(video_id, embedding, frame_count)
        VALUES(:vid, CAST(:embedding AS vector), :count)
        ON CONFLICT (video_id) DO NOTHING
        """
    )
    with engine.begin() as tx:
        _set_search_path(tx, schema)
        tx.execute(sql, {"vid": video_id, "embedding": vec_literal, "count": frame_count})


def run(
    *,
    project: str,
    location: str,
    schema: str,
    frames_per_sec: float,
    use_gcs: bool,
) -> None:
    model = _init_vertex(project, location)
    rows, is_gcs = _fetch_pending_rows(schema, use_gcs)

    LOGGER.info("Embedding %d pending videos (source=%s)", len(rows), "GCS" if is_gcs else "BYTEA")

    for vid, payload, fps in rows:
        try:
            temp_path = _gcs_download_to_temp(payload) if is_gcs else _bytes_to_tempfile(payload)
            vec, sampled = _sample_and_embed_video(
                model, temp_path, frames_per_sec=frames_per_sec, fps_hint=float(fps) if fps else None
            )
            if vec is None or sampled == 0:
                LOGGER.warning("No embeddings produced for video_id=%s", vid)
                continue

            _persist_embedding(schema, int(vid), _to_pgvector_literal(vec), int(sampled))
            LOGGER.info("[OK] video_id=%s frames=%s", vid, sampled)
        except Exception as exc:
            LOGGER.exception("[ERROR] Failed video_id=%s: %s", vid, exc)


# ----------------------------
# CLI
# ----------------------------
def _parse_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Embed pending videos and store vectors.")
    p.add_argument("--project", default=DEFAULT_PROJECT, required=DEFAULT_PROJECT is None, help="GCP Project ID")
    p.add_argument("--location", default=DEFAULT_LOCATION, help="Vertex AI location (default: us-central1)")
    p.add_argument("--schema", default=os.getenv("PGSCHEMA", "alloydb_usecase"), help="Postgres schema")
    p.add_argument("--frame-sample-per-sec", type=float, default=DEFAULT_FPS_SAMPLE, help="Frames sampled per second")
    p.add_argument("--use-gcs", type=str, default=os.getenv("USE_GCS", "false"), help="true/false")
    return p.parse_args(argv)


if __name__ == "__main__":
    args = _parse_args()
    run(
        project=args.project,
        location=args.location,
        schema=args.schema,
        frames_per_sec=float(args.frame_sample_per_sec),
        use_gcs=str(args.use_gcs).lower() == "true",
    )
