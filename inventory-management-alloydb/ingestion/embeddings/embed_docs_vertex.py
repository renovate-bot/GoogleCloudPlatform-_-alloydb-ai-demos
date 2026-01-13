
from __future__ import annotations
import os
from dotenv import load_dotenv
from langchain_google_vertexai import VertexAIEmbeddings
from src.utils.sql import fetchall, get_conn

# Load environment variables from a `.env` file if present.
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


def get_docs():
    """
    Fetches all documents from `retail.docs` that do not yet have embeddings.

    Returns:
        List[Dict[str, Any]]: Rows with keys:
            - doc_id: Unique identifier of the document.
            - body: Text content to be embedded.
    """
    return fetchall("SELECT doc_id, body FROM retail.docs WHERE embedding IS NULL")


if __name__ == "__main__":
    """
    Batch-embeds documents using Vertex AI and writes vectors back to AlloyDB.

    Workflow:
        1) Instantiate VertexAIEmbeddings with configured model, project, and location.
        2) Retrieve all docs missing embeddings via `get_docs()`.
        3) For each document:
           - Generate a query embedding (list[float]) from `body`.
           - Assert the vector length equals `EMBED_DIM` (sanity check).
           - Update the `embedding` column for that `doc_id`.
        4) Commit the transaction and print a summary.

    Notes:
        - `get_conn()` is assumed to provide a psycopg2-like connection with
          context manager support for both the connection and cursor.
        - Embeddings are stored directly as a vector type compatible with the DB.
    """
    # Initialize Vertex AI embeddings client with the selected model and location.
    embeddings = VertexAIEmbeddings(model_name=MODEL, project=PROJECT, location=LOCATION)

    # Retrieve documents that need embedding.
    rows = get_docs()

    # -------------------------------------------------------------------------
    # Open a database connection and cursor; process each document sequentially.
    # The `assert` ensures embedding dimensionality matches the expected shape.
    # -------------------------------------------------------------------------
    with get_conn() as conn, conn.cursor() as cur:
        for r in rows:
            # Generate embedding vector for the document body.
            v = embeddings.embed_query(r["body"])  # list[float]

            # Sanity check: ensure vector length matches configured dimension.
            assert len(v) == EMBED_DIM

            # Persist the embedding to the database for the given document.
            cur.execute(
                "UPDATE retail.docs SET embedding=%s WHERE doc_id=%s",
                (v, r["doc_id"])
            )

        # Commit all updates after processing the batch.
        conn.commit()

    # Output a concise completion message with the number of embedded docs.
    print(f"✅ Embedded {len(rows)} docs via Vertex AI")
