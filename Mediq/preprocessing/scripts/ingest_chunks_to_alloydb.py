"""
Ingest chunk CSV into AlloyDB and build embeddings.
"""

from __future__ import annotations
import argparse
import logging   
import sys       
from medical_preprocess.config import AppConfig
from medical_preprocess.db.alloydb_client import AlloyDBClient
from medical_preprocess.db.schema_manager import ensure_extensions, ensure_table_and_columns, create_scann_index
from medical_preprocess.db.load_chunks import load_records_from_csv, insert_chunks, update_embeddings
import inspect   


def _setup_logging() -> logging.Logger:
    """ Configure root logger and return module logger."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
    return logging.getLogger("ingest_chunks")


def main() -> None:
    p = argparse.ArgumentParser(description="Ingest chunk CSV into AlloyDB and build embeddings")
    p.add_argument('--chunks', required=True, help='Path to chunks CSV')
    p.add_argument('--schema', required=False, default=None, help='Target schema (default from env)')
    p.add_argument('--table', required=False, default=None, help='Target table (default from env)')
    p.add_argument('--create-index', action='store_true', help='Create ScaNN index')
    # p.add_argument('--stream', action='store_true', help='(Optional) Stream CSV in batches to limit memory')  # OPTIONAL
    args = p.parse_args()

    log = _setup_logging()  

    try:
        cfg = AppConfig.from_env()
        fq_schema = args.schema or cfg.defaults.schema
        if not fq_schema:
            log.error("Schema is required (pass --schema or set defaults.schema in env)")
            sys.exit(1)

        fq_table = f"{fq_schema}.{args.table or cfg.defaults.details_table}"
        if fq_table.endswith(".") or fq_table.split(".")[-1] == "":
            log.error("Table is required (pass --table or set defaults.details_table in env)")
            sys.exit(1)

        client = AlloyDBClient(cfg.alloydb)
        engine = client.create_engine()

        with engine.begin() as conn:
            log.info("[1/5] Ensuring extensions...")
            ensure_extensions(conn)
            log.info("[2/5] Ensuring table & columns...")
            ensure_table_and_columns(conn, fq_table)

        # --- Loading & inserting rows ---
        log.info("[3/5] Loading rows from CSV...")
        rows = load_records_from_csv(args.chunks)
        log.info("  Loaded %d rows.", len(rows))

        log.info("[4/5] Inserting rows...")
        with engine.begin() as conn:
            inserted = insert_chunks(conn, fq_table, rows)  # NOTE: consider UPSERT in helper to be idempotent
        log.info("  Inserted %d rows.", inserted)

        # --- Embeddings update ---
        log.info("[5/5] Updating embeddings...")
        updated_total = 0

        # Feature-detect whether update_embeddings supports a 'limit' param.
        sig = inspect.signature(update_embeddings)
        supports_limit = 'limit' in sig.parameters  # type: ignore[attr-defined]

        if supports_limit:
            # Batch updates to avoid timeouts/long transactions.
            BATCH = 1000
            while True:
                with engine.begin() as conn:
                    updated = update_embeddings(conn, fq_table, cfg.alloydb.embedding_model, limit=BATCH)  # type: ignore[arg-type]
                if updated == 0:
                    break
                updated_total += updated
                log.info("  Updated embeddings for %d rows (cumulative: %d)...", updated, updated_total)
        else:
            # Fallback: call the original signature (may process all pending rows).
            with engine.begin() as conn:
                updated_total = update_embeddings(conn, fq_table, cfg.alloydb.embedding_model)
        log.info("  Embeddings updated for ~%d rows.", updated_total)

        if args.create_index:
            log.info("[+] Creating ScaNN index...")
            try:
                with engine.begin() as conn:
                    create_scann_index(conn, fq_table)
                log.info("  ScaNN index created.")
            except Exception as e:
                log.warning("  ScaNN index skipped/failed: %s", e)

        client.close()
        log.info("Done.")
        sys.exit(0)

    except Exception as e:
        log.exception("Chunk ingestion failed: %s", e)
        sys.exit(1)


if __name__ == '__main__':
    main()
 