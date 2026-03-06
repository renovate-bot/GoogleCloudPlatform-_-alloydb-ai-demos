
# pipeline/ingest_videos.py


from pathlib import Path
import sys

import os
from pathlib import Path
import cv2
from sqlalchemy import text
from db import engine
from config import UCF_DIR  



# Add project root (parent of 'pipeline' folder) to Python path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# -------- utilities --------

def probe_video(path: Path):
    """Return basic video metadata using OpenCV."""
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        return None
    fps = cap.get(cv2.CAP_PROP_FPS) or 0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    duration = int(frame_count / fps) if fps > 0 else None
    cap.release()
    return {"fps": fps, "width": width, "height": height, "duration": duration}

def parse_label_from_path(path: Path):
    """
    HWID12 (Highway Incidents Detection Dataset). The HWAD12 consists of 11 distinct highway 
    incidents categories, and one additional category for negative samples representing normal traffic. 
    The proposed dataset also includes 230+ video segments of 3 to 8 seconds on average each.
    """
    try:
        return path.parent.name or None
    except Exception:
        return None

def is_video_file(fn: str) -> bool:
    return fn.lower().endswith((".mp4", ".avi", ".mov", ".mkv"))

# -------- main ingest --------

def ingest(
    source_dir: Path = None,
    dedupe_on_basename: bool = False,
    dry_run: bool = False,
):
    
    # Resolve source directory
    if source_dir is None:
        if UCF_DIR is None:
            raise RuntimeError("UCF_DIR is not set in config.py or environment.")
        source_dir = Path(UCF_DIR)

    assert source_dir.is_dir(), f"Dir not found: {source_dir}"

    # Choose duplicate key: full path vs basename
    def dup_key(p: Path) -> str:
        return (p.name if dedupe_on_basename else str(p))

    total_files = 0
    inserted = 0
    skipped = 0
    failed = 0

    with engine.connect() as conn:
        with conn.begin():
            for root, _, files in os.walk(source_dir):
                root_path = Path(root)
                for fn in files:
                    total_files += 1
                    if not is_video_file(fn):
                        continue

                    full = root_path / fn
                    label = parse_label_from_path(full)
                    meta = probe_video(full) or {}

                    # duplicate check
                    key_val = dup_key(full)
                    exists_sql = text("SELECT id FROM video_meta WHERE file_name=:f")
                    if conn.execute(exists_sql, {"f": key_val}).fetchone():
                        skipped += 1
                        continue

                    # insert meta
                    try:
                        if dry_run:
                            print(f"[DRY-RUN] Would insert meta for: {full}")
                        else:
                            res = conn.execute(text("""
                                INSERT INTO video_meta(file_name, label, split, duration_sec, width, height, fps)
                                VALUES(:f, :label, NULL, :duration, :w, :h, :fps)
                                RETURNING id
                            """), {
                                "f": key_val,
                                "label": label,
                                "duration": meta.get("duration"),
                                "w": meta.get("width"),
                                "h": meta.get("height"),
                                "fps": meta.get("fps"),
                            })
                            vid = res.fetchone()[0]

                            # insert blob
                            with open(full, "rb") as vf:
                                data = vf.read()
                            conn.execute(text("""
                                INSERT INTO video_blobs(video_id, video_data)
                                VALUES(:vid, :data)
                            """), {"vid": vid, "data": data})
                            inserted += 1

                    except Exception as e:
                        failed += 1
                        # Log but continue to next file
                        print(f"[ERROR] Failed to ingest {full}: {e}")

    print(f"Completed. Total: {total_files}, Inserted: {inserted}, Skipped: {skipped}, Failed: {failed}")


if __name__ == "__main__":
    # Default run with config.UCF_DIR; set flags here as needed:
    # - dedupe_on_basename=True to avoid duplicates when moved across subfolders
    # - dry_run=True to preview without DB inserts
    ingest(
        source_dir=None,             # use config.UCF_DIR
        dedupe_on_basename=False,    # set True if you want basename-based de-dupe
        dry_run=False,               # set True to preview
    )
