from __future__ import annotations
from pathlib import Path
from sqlalchemy.engine import Connection
from sqlalchemy import text


def create_schema(conn: Connection, schema: str) -> None:
    """Create schema if it doesn't exist."""
    conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema};"))


def create_disease_info_merged(
    conn: Connection,
    schema: str,
    details_table: str = 'disease_details_info',
    tests_table: str = 'disease_tests_info',
    images_table: str = 'disease_images_info',
    merged_table: str = 'disease_info_merged',
    replace: bool = True,
) -> None:
    """Create the merged table by joining the three source tables (CTAS).

    This mirrors the user's SQL and executes through Python/SQLAlchemy.
    """
    fq_details = f"{schema}.{details_table}"
    fq_tests = f"{schema}.{tests_table}"
    fq_images = f"{schema}.{images_table}"
    fq_merged = f"{schema}.{merged_table}"

    if replace:
        conn.execute(text(f"DROP TABLE IF EXISTS {fq_merged};"))

    sql = f"""
    CREATE TABLE {fq_merged} AS
        SELECT
            ddi.id,
            ddi.disease_name,
            ddi.chunk_content AS chunk_content,
            ddi.chunk_num,
            ddi.chunk_page_no AS pages,
            ddi.chunk_embedding,
            dti.test_name,
            dti.disease_name_embedding,
            dii.caption_text,
            dii.disease_image_base64
        FROM {fq_details} AS ddi
        LEFT JOIN {fq_tests}  AS dti ON ddi.disease_name = dti.disease_name
        LEFT JOIN {fq_images} AS dii ON ddi.disease_name = dii.disease_name;
    """
    conn.exec_driver_sql(sql)


def create_tvf_from_file(conn: Connection, sql_file: Path) -> None:
    sql_text = Path(sql_file).read_text(encoding='utf-8')
    create_tvf_from_string(conn, sql_text)


def create_tvf_from_string(conn: Connection, sql_text: str) -> None:
    conn.exec_driver_sql(sql_text)
