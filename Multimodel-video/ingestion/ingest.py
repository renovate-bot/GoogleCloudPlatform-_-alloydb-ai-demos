# pipeline/ingest_videos.py
"""Ingest local videos into AlloyDB (video_meta + video_blobs).

Run:
  python -m pipeline.ingest_videos \
    --source-dir /path/to/videos \
    --schema alloydb_usecase \
    --dedupe-on-basename true \
    --dry-run false
"""

from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path
from typing import Dict, Optional

import cv2
from sqlalchemy import text

# Add project root
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from db import engine  # noqa: E402
from config import UCF_DIR  # noqa: E402

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
)
LOGGER = logging.getLogger("ingest_videos")


def _set_search_path(conn, schema: str) -> None:
    conn.exec_driver_sql(f"SET search_path TO {schema}, public")


def _is_video_file(fn: str) -> bool:
    return fn.lower().endswith((".mp4", ".avi", ".mov", ".mkv"))


def _probe_video(path: Path) -> Optional[Dict[str, float]]:
    """Return basic metadata using OpenCV or None if unreadable."""
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        LOGGER.warning("Cannot open video: %s", path)
        return None
    try:
        fps = float(cap.get(cv2.CAP_PROP_FPS)) or 0.0
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        duration = int(frame_count / fps) if fps > 0 else None
        return {"fps": fps, "width": width, "height": height, "duration": duration}
    finally:
        cap.release()


def _label_from_path(path: Path) -> Optional[str]:
    """Derive label as the immediate parent folder name."""
    try:
        return path.parent.name or None
    except Exception:
        return None


def _dup_key(p: Path, dedupe_on_basename: bool) -> str:
    return p.name if dedupe_on_basename else str(p)


def run(
    *,
    source_dir: Optional[Path],
    schema: str,
    dedupe_on_basename: bool,
    dry_run: bool,
) -> None:
    # Resolve source directory
    if source_dir is None:
        if not UCF_DIR:
            raise RuntimeError("UCF_DIR not set in config.py and --source-dir not provided.")
        source_dir = Path(UCF_DIR)
    assert source_dir.is_dir(), f"Directory not found: {source_dir}"

    total_files = 0
    inserted = 0
    skipped = 0
    failed = 0

    with engine.connect() as conn:
        _set_search_path(conn, schema)
        with conn.begin():
            for root, _, files in os.walk(source_dir):
                root_path = Path(root)
                for fn in files:
                    total_files += 1
                    if not _is_video_file(fn):
                        continue

                    full = root_path / fn
                    label = _label_from_path(full)
                    meta = _probe_video(full) or {}
                    key_val = _dup_key(full, dedupe_on_basename)

                    # Store ONLY the basename in file_name (UI and search rely on this)
                    file_name = full.name

                    # Duplicate check (by file_name)
                    exists = conn.execute(text("SELECT 1 FROM video_meta WHERE file_name = :f"), {"f": file_name}).fetchone()
                    if exists:
                        skipped += 1
                        continue

                    try:
                        if dry_run:
                            LOGGER.info("[DRY-RUN] Would insert: %s", full)
                            continue

                        # Insert meta and get id
                        vid_row = conn.execute(
                            text(
                                """
                                INSERT INTO video_meta(file_name, label, split, duration_sec, width, height, fps)
                                VALUES(:f, :label, NULL, :duration, :w, :h, :fps)
                                RETURNING id
                                """
                            ),
                            {
                                "f": file_name,
                                "label": label,
                                "duration": meta.get("duration"),
                                "w": meta.get("width"),
                                "h": meta.get("height"),
                                "fps": meta.get("fps"),
                            },
                        ).fetchone()
                        vid = int(vid_row[0])

                        # Insert blob
                        with open(full, "rb") as vf:
                            data = vf.read()
                        conn.execute(
                            text("INSERT INTO video_blobs(video_id, video_data) VALUES(:vid, :data)"),
                            {"vid": vid, "data": data},
                        )

                        inserted += 1
                        LOGGER.info("[OK] Ingested %s → id=%s", file_name, vid)

                    except Exception as exc:
                        failed += 1
                        LOGGER.exception("[ERROR] Failed to ingest %s: %s", full, exc)

    LOGGER.info("Completed. Total=%d Inserted=%d Skipped=%d Failed=%d", total_files, inserted, skipped, failed)


# ----------------------------
# CLI
# ----------------------------
def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Ingest local videos into AlloyDB.")
    p.add_argument("--source-dir", type=Path, default=None, help="Directory containing class folders/videos")
    p.add_argument("--schema", default=os.getenv("PGSCHEMA", "alloydb_usecase"), help="Postgres schema")
    p.add_argument("--dedupe-on-basename", type=str, default="true", help="true/false: de-duplicate by basename")
    p.add_argument("--dry-run", type=str, default="false", help="true/false: preview without DB inserts")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    run(
        source_dir=args.source_dir,
        schema=args.schema,
        dedupe_on_basename=str(args.dedupe_on_basename).lower() == "true",
        dry_run=str(args.dry_run).lower() == "true",
    )
