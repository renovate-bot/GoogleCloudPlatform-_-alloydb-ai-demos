
from __future__ import annotations
import os
from dotenv import load_dotenv
from langchain_google_vertexai import VertexAIEmbeddings
from src.utils.sql_cloudsql import fetchall, get_conn

# Load environment variables from `.env` file if present.
load_dotenv()

# ---------------------------------------------------------------------------
# Configuration sourced from environment variables:
#   - PROJECT_ID: GCP project for Vertex AI.
#   - VERTEX_LOCATION / REGION: Vertex AI location; defaults to REGION or "us-central1".
#   - EMBEDDING_MODEL: Vertex model ID (default "text-embedding-004").
#   - EMBEDDING_DIM: Expected dimensionality of the embedding vector (default 768).
# ---------------------------------------------------------------------------
PROJECT = os.getenv("PROJECT_ID")
LOCATION = os.getenv("VERTEX_LOCATION", os.getenv("REGION", "us-central1"))
MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-004")
EMBED_DIM = int(os.getenv("EMBEDDING_DIM", "768"))


def get_items_to_embed(limit=5000):
    """
    Fetches product records that do not yet have embeddings.

    Args:
        limit (int, optional): Maximum number of rows to retrieve. Defaults to 5000.

    Returns:
        List[Dict[str, Any]]: Rows with keys:
            - sku (str): Product SKU.
            - text (str): Text to embed (description if available, else title).
    """
    return fetchall(
        "SELECT sku, COALESCE(description,title) AS text FROM retail.products WHERE embedding IS NULL LIMIT %s",
        (limit,)
    )


if __name__ == "__main__":
    """
    Batch-embeds product descriptions/titles using Vertex AI and updates the
    embeddings in CloudSQL.

    Workflow:
        1) Initialize VertexAIEmbeddings with configured model and location.
        2) Retrieve products missing embeddings via `get_items_to_embed()`.
        3) For each product:
           - Generate an embedding vector for the text field.
           - Validate embedding dimensionality against `EMBED_DIM`.
           - Update the `embedding` column and set `last_embedded_at` timestamp.
        4) Commit all updates and print a summary message.

    Notes:
        - `get_conn()` is assumed to provide a psycopg2-like connection with
          context manager support for both the connection and cursor.
        - Embeddings are stored directly in the database as a vector type.
    """
    # Initialize Vertex AI embeddings client.
    embeddings = VertexAIEmbeddings(model_name=MODEL, project=PROJECT, location=LOCATION)

    # Retrieve products that need embeddings.
    rows = get_items_to_embed()

    # -------------------------------------------------------------------------
    # Open a database connection and cursor; process each product sequentially.
    # Validate embedding size before persisting to ensure schema consistency.
    # -------------------------------------------------------------------------
    with get_conn() as conn, conn.cursor() as cur:
        for r in rows:
            # Generate embedding vector for the product text.
            vec = embeddings.embed_query(r["text"])  # list[float]

            # Validate embedding dimensionality; raise error if mismatch.
            if len(vec) != EMBED_DIM:
                raise ValueError("Embedding dim mismatch")

            # Update embedding and timestamp for the given SKU.
            cur.execute(
                               "UPDATE retail.products SET embedding=%s, last_embedded_at=now() WHERE sku=%s",
                (vec, r["sku"])
            )

        # Commit all updates after processing the batch.
        conn.commit()

    # Output completion message with count of embedded products.
