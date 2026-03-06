
# pipeline/embed_videos.py
from pathlib import Path
import sys

# Allow running as a module from project root or directly
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# --- load .env if present (optional) ---
try:
    from dotenv import load_dotenv  # pip install python-dotenv
    load_dotenv()
except Exception:
    pass

import os
import tempfile
import cv2
import numpy as np
import vertexai
from vertexai.vision_models import Image, MultiModalEmbeddingModel
from sqlalchemy import text
from sqlalchemy.exc import DatabaseError
from db import engine

# ---------- Config via environment (with safe defaults) ----------
PROJECT_ID = os.getenv("GCP_PROJECT") or os.getenv("PROJECT_ID")
LOCATION = os.getenv("VERTEX_LOCATION", "us-central1")
FRAME_SAMPLE_PER_SEC = float(os.getenv("FRAME_SAMPLE_PER_SEC", "1.0"))
EMBED_DIM = int(os.getenv("EMBED_DIM", "1408"))  # Vertex multimodal embeddings are 1408-D

USE_GCS = os.getenv("USE_GCS", "false").lower() == "true"

# ---------- Optional: GCS support ----------
_USE_GCS_IMPORTS = False
if USE_GCS:
    try:
        from google.cloud import storage  # pip install google-cloud-storage
        _USE_GCS_IMPORTS = True
    except Exception:
        _USE_GCS_IMPORTS = False
        USE_GCS = False

# ---------- Vertex init ----------
def init_vertex():
    if not PROJECT_ID:
        raise RuntimeError("PROJECT_ID / GCP_PROJECT not set in environment.")
    vertexai.init(project=PROJECT_ID, location=LOCATION)
    return MultiModalEmbeddingModel.from_pretrained("multimodalembedding@001")

# ---------- Video readers ----------
def _bytes_to_tempfile(video_bytes: bytes, suffix: str = ".mp4") -> str:
    """Write a BYTEA payload to a temp file and return the path."""
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(video_bytes)
        return tmp.name

def _download_gcs_to_temp(gcs_uri: str) -> str:
    """Download GCS URI (gs://bucket/object) to a temp file; requires ADC & google-cloud-storage."""
    if not USE_GCS or not _USE_GCS_IMPORTS:
        raise RuntimeError("GCS not enabled or google-cloud-storage not installed.")

    assert gcs_uri.startswith("gs://"), f"Invalid GCS URI: {gcs_uri}"
    bucket_name, object_name = gcs_uri[5:].split("/", 1)

    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(object_name)

    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
        blob.download_to_filename(tmp.name)
        return tmp.name

# ---------- Embedding ----------
def sample_and_embed_video(model, temp_video_path: str, fps_hint=None):
    """Sample frames ~1/sec, get Vertex image embeddings, and average to one vector."""
    try:
        cap = cv2.VideoCapture(temp_video_path)
        if not cap.isOpened():
            return None, 0

        fps = cap.get(cv2.CAP_PROP_FPS) or (fps_hint or 25.0)
        interval = max(int(fps / FRAME_SAMPLE_PER_SEC), 1)

        embeddings = []
        f = 0
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break
            if f % interval == 0:
                ok, buf = cv2.imencode(".jpg", frame)
                if not ok:
                    f += 1
                    continue
                emb = model.get_embeddings(image=Image(image_bytes=buf.tobytes()))
                if emb.image_embedding:
                    embeddings.append(emb.image_embedding)
            f += 1

        cap.release()
        if not embeddings:
            return None, 0

        mean_vec = np.mean(np.array(embeddings), axis=0).tolist()
        return mean_vec, len(embeddings)

    finally:
        # Always clean up temp file
        try:
            os.remove(temp_video_path)
        except Exception:
            pass

# ---------- Main pipeline ----------
def embed_pending():
    model = init_vertex()

    # Prefer GCS URIs when available
    sql_gcs = text("""
        SELECT m.id, a.gcs_uri, m.fps
          FROM video_meta m
          JOIN video_assets a ON a.video_id = m.id
          LEFT JOIN video_embeddings e ON e.video_id = m.id
        WHERE e.video_id IS NULL
    """)

    # Fallback: BYTEA blobs
    sql_bytes = text("""
        SELECT m.id, b.video_data, m.fps
          FROM video_meta m
          JOIN video_blobs b ON b.video_id = m.id
          LEFT JOIN video_embeddings e ON e.video_id = m.id
        WHERE e.video_id IS NULL
    """)

    # --- Phase 1: read pending videos on a single connection, then close it ---
    rows = []
    is_from_gcs = False

    with engine.connect() as read_conn:
        if USE_GCS:
            try:
                rows = read_conn.execute(sql_gcs).fetchall()
                is_from_gcs = True
            except DatabaseError:
                rows = []
                is_from_gcs = False

        if not rows:
            rows = read_conn.execute(sql_bytes).fetchall()
            is_from_gcs = False

    total = len(rows)
    print(f"Embedding {total} pending videos (source={'GCS' if is_from_gcs else 'BYTEA'})")

    # --- Phase 2: per-video transactional writes using engine.begin() ---
    for row in rows:
        try:
            vid = row[0]
            payload = row[1]
            fps = row[2]

            # Prepare temp file path from the source
            if is_from_gcs:
                temp_path = _download_gcs_to_temp(payload)
            else:
                temp_path = _bytes_to_tempfile(payload)

            vec, count = sample_and_embed_video(model, temp_path, fps_hint=fps)
            if not vec:
                print(f"[WARN] No embeddings for video_id={vid}")
                continue

            # Build pgvector text literal (e.g., "[0.12,0.34,...]")
            vec_literal = "[" + ",".join(str(x) for x in vec) + "]"

            # Use CAST(:embedding AS vector) to avoid :: parsing issues
            insert_sql = text("""
                INSERT INTO video_embeddings(video_id, embedding, frame_count)
                VALUES(:vid, CAST(:embedding AS vector), :count)
                ON CONFLICT (video_id) DO NOTHING
            """)

            # Write on a fresh transactional connection; auto-commit on success
            with engine.begin() as tx:
                tx.execute(insert_sql, {"vid": vid, "embedding": vec_literal, "count": count})

            print(f"[OK] Embedded video_id={vid} with {count} frames")

        except Exception as e:
            print(f"[ERROR] Failed to embed video_id={row[0]}: {e}")


if __name__ == "__main__":
    embed_pending()
