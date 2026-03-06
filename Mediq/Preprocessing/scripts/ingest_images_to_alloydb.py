"""
Ingest image captions/base64 CSV into AlloyDB and build disease name embeddings.
"""
from __future__ import annotations
import argparse
import logging
import time

from src.medical_preprocess.config import AppConfig
from src.medical_preprocess.db.alloydb_client import AlloyDBClient
from src.medical_preprocess.db.schema_manager import (
    ensure_extensions,
    ensure_images_table,
    create_scann_index,
)
from src.medical_preprocess.db.load_images import (
    load_image_rows_from_csv,
    insert_images,
    update_disease_name_embeddings,
)


def setup_logging(level: str = "INFO") -> None:
    """Configure root logger with timestamps and levels.

    Args:
        level: Logging level name (e.g., "DEBUG", "INFO").
    """
    logging.basicConfig(
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        level=getattr(logging, level.upper(), logging.INFO),
    )


def main() -> None:
    """Entry point for ingesting images & captions into AlloyDB."""
    p = argparse.ArgumentParser(
        description="Ingest image captions/base64 CSV into AlloyDB and (optionally) build embeddings"
    )
    p.add_argument(
        "--images",
        required=True,
        help="Path to images CSV produced by scripts/extract_images.py",
    )
    p.add_argument(
        "--schema",
        default=None,
        help="Target schema (default from env ALLOYDB_DEFAULT_SCHEMA)",
    )
    p.add_argument(
        "--table",
        default=None,
        help="Target images table (default from env ALLOYDB_IMAGES_TABLE)",
    )
    p.add_argument(
        "--populate-embeddings",
        action="store_true",
        help="Populate embeddings using google_ml.embedding",
    )
    p.add_argument(
        "--create-index",
        action="store_true",
        help="Create ScaNN index on caption_embedding",
    )
    p.add_argument(
        "--log-level",
        default="INFO",
        help="Logging level: DEBUG, INFO, WARNING, ERROR",
    )
    args = p.parse_args()

    setup_logging(args.log_level)
    log = logging.getLogger("ingest_images")
    t0 = time.perf_counter()

    # Load config from environment
    cfg = AppConfig.from_env()
    fq_schema = args.schema or cfg.defaults.schema
    fq_table = f"{fq_schema}.{args.table or cfg.defaults.images_table}"
    log.info("Target images table: %s", fq_table)

    # Create AlloyDB SQLAlchemy engine
    client = AlloyDBClient(cfg.alloydb)
    engine = client.create_engine()

    # Execute ingestion flow
    with engine.begin() as conn:
        log.info("[1/5] Ensuring extensions ...")
        ensure_extensions(conn)

        log.info("[2/5] Ensuring images table ... %s", fq_table)
        ensure_images_table(conn, fq_table)

        log.info("[3/5] Loading rows from CSV: %s", args.images)
        rows = load_image_rows_from_csv(args.images)
        log.info("Loaded %d rows.", len(rows))

        log.info("[4/5] Inserting image rows ...")
        t_ins = time.perf_counter()
        inserted = insert_images(conn, fq_table, rows)
        log.info("Inserted %d rows in %.2fs.", inserted, time.perf_counter() - t_ins)

        if args.populate_embeddings:
            log.info(
                "[5/5] Updating embeddings using model=%s ...",
                cfg.alloydb.embedding_model,
            )
            t_emb = time.perf_counter()
            updated = update_disease_name_embeddings(
                conn, fq_table, cfg.alloydb.embedding_model
            )
            log.info(
                "Embeddings updated for ~%d rows in %.2fs.",
                updated,
                time.perf_counter() - t_emb,
            )
        else:
            log.info("[5/5] Skipping embeddings (flag not set)")

        if args.create_index:
            log.info("[+] Creating ScaNN index on disease_name_embedding ...")
            try:
                create_scann_index(conn, fq_table)
                log.info("ScaNN index created.")
            except Exception as e:
                log.warning("ScaNN index skipped/failed: %s", e)

    client.close()
    log.info("Done. Total time: %.2fs", time.perf_counter() - t0)


if __name__ == "__main__":
    main()