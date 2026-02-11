"""
Create merged medical table and TVF in AlloyDB.
"""
from __future__ import annotations

import argparse
import logging  
import sys     
from pathlib import Path
from typing import Optional

from medical_preprocess.config import AppConfig
from medical_preprocess.db.alloydb_client import AlloyDBClient
from medical_preprocess.db.ddl_ops import (
    create_schema,
    create_disease_info_merged,
    create_tvf_from_file,
)


def _setup_logging() -> logging.Logger:
    """# NEW: Configure root logger and return module logger."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    return logging.getLogger("create_merged_and_tvf")


def _resolve_tvf_path(tvf_sql: Path) -> Path:
    """
    # NEW: Resolve TVF SQL path robustly.
    Try the provided path (CWD-based or absolute). If not found, try relative to script directory.
    """
    if tvf_sql.exists():
        return tvf_sql.resolve()

    script_dir = Path(__file__).resolve().parent
    alt = (script_dir / tvf_sql).resolve()
    if alt.exists():
        return alt

    raise FileNotFoundError(
        f"TVF SQL not found: '{tvf_sql}'. Tried CWD: '{Path.cwd()}', script dir: '{script_dir}'."
    )


def main() -> None:
    p = argparse.ArgumentParser(description='Create merged table and TVF.')
    p.add_argument('--schema', default=None, help='Schema name (defaults from env)')
    p.add_argument('--details-table', default=None, help='Details table name (default from env)')
    p.add_argument('--tests-table', default='disease_tests_info', help='Tests table name')
    p.add_argument('--images-table', default='disease_images_info', help='Images table name')
    p.add_argument('--merged-table', default='disease_info_merged', help='Merged table name to create')
    p.add_argument('--drop-existing-merged', action='store_true', help='Drop existing merged table before creating')
    p.add_argument('--tvf-sql', type=Path, default=Path('sql/search_medical_info.sql'), help='Path to TVF SQL file')
    args = p.parse_args()

    log = _setup_logging()  # NEW

    try:
        cfg = AppConfig.from_env()
        schema = args.schema or cfg.defaults.schema
        details = args.details_table or cfg.defaults.details_table

        # NEW: Fail fast on missing required inputs.
        if not schema:
            log.error("Schema is required (pass --schema or set defaults.schema in env)")
            sys.exit(1)
        if not details:
            log.error("Details table is required (pass --details-table or set defaults.details_table in env)")
            sys.exit(1)

        # NEW: Resolve TVF file path robustly before opening DB transaction.
        tvf_sql_path = _resolve_tvf_path(args.tvf_sql)
        log.info("Using TVF SQL file: %s", tvf_sql_path)

        client = AlloyDBClient(cfg.alloydb)
        engine = client.create_engine()

        # NOTE: Rely on ddl_ops to use safe quoting and idempotent DDL.
        with engine.begin() as conn:
            log.info("[1/3] Ensuring schema '%s' exists...", schema)
            create_schema(conn, schema)

            log.info("[2/3] Creating merged table '%s.%s' (replace=%s)...",
                     schema, args.merged_table, args.drop_existing_merged)
            create_disease_info_merged(
                conn,
                schema=schema,
                details_table=details,
                tests_table=args.tests_table,
                images_table=args.images_table,
                merged_table=args.merged_table,
                replace=args.drop_existing_merged,
            )
            log.info("Merged table created or up to date.")

            log.info("[3/3] Creating/updating TVF from %s ...", tvf_sql_path)
            create_tvf_from_file(conn, tvf_sql_path)
            log.info("TVF created/updated.")

        client.close()
        log.info("Done.")
        sys.exit(0)

    except FileNotFoundError as e:
        log.error("File error: %s", e)
        sys.exit(1)
    except Exception as e:
        # NEW: Bubble clear stack trace for troubleshooting in CI.
        logging.exception("Unexpected error: %s", e)
        sys.exit(1)


if __name__ == '__main__':
    main()
 