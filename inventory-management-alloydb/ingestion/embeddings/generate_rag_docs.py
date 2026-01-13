
from __future__ import annotations
import os, datetime
from google.cloud import storage
from dotenv import load_dotenv
from langchain_google_vertexai import VertexAIEmbeddings
from src.utils.sql import get_conn

# Load environment variables from a `.env` file if present.
load_dotenv()

# ---------------------------------------------------------------------------
# Configuration sourced from environment variables:
#   - PROJECT_ID: GCP project for Vertex AI.
#   - VERTEX_LOCATION / REGION: Vertex AI location; defaults to REGION or "us-central1".
#   - EMBEDDING_MODEL: Vertex model ID (default "text-embedding-004").
#   - EMBEDDING_DIM: Expected dimensionality of the embedding vector (default 768).
#   - GCS_BUCKET: Target Google Cloud Storage bucket to store text docs.
# ---------------------------------------------------------------------------
PROJECT = os.getenv("PROJECT_ID")
LOCATION = os.getenv("VERTEX_LOCATION", os.getenv("REGION", "us-central1"))
MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-004")
EMBED_DIM = int(os.getenv("EMBEDDING_DIM", "768"))
BUCKET = os.getenv("GCS_BUCKET")

# ---------------------------------------------------------------------------
# Seed documents to be uploaded to GCS and embedded.
# Each entry contains:
#   - doc_type: classification/category of the document.
#   - name: human-readable title used in the GCS object name.
#   - body: textual content that will be embedded and stored.
# ---------------------------------------------------------------------------
DOCS = [
 {"doc_type":"Policy","name":"Procurement Policy v1","body":"Category A: max single PO USD 25,000; monthly cap USD 250,000. Approvals: > USD 10,000 requires Category Manager; > USD 20,000 requires Finance sign-off. Urgent buys allowed if projected OOS in ≤5 days; document justification in PO notes."},
 {"doc_type":"SOP","name":"Replenishment SOP v2","body":"Formula: recommended_qty = forecast(horizon_days) + safety_stock - net_position. Round up to MOQ; if lead_time_days > 7 and promo within 10 days, prefer faster supplier. Edge cases: zero forecast days use 7-day MA; cap single PO by policy."},
 {"doc_type":"SupplierNote","name":"Supplier Holiday Calendar","body":"Supplier B: Lunar New Year +5–7 days (Week 6–7). Supplier A: No known seasonal delays. If Supplier B selected in Week 6–7, add buffer to expected_at."},
 {"doc_type":"Policy","name":"Supplier SLA & Escalation","body":"On-time delivery target 95% within promised lead time. Escalate if two consecutive late POs; consider temporary switch to alternate supplier."},
 {"doc_type":"Policy","name":"Substitution Policy","body":"Allowed within same category and price band if primary supplier lead time exceeds 7 days and projected OOS within horizon. Document substitution rationale in PO notes."},
 {"doc_type":"Policy","name":"Returns Policy (Ops)","body":"Online returns accepted within 30 days; expect 3–5% return rate typical. Forecast should consider net demand = gross − expected returns for Apparel/Footwear."},
 {"doc_type":"Guideline","name":"Promo Playbook","body":"Uplift vs baseline: Flash sale 1.3–1.6x; Payday weekend 1.2–1.4x; Seasonal 1.4–2.0x. Use conservative uplift if inventory risk flagged."},
 {"doc_type":"Policy","name":"Markdown Policy","body":"Markdowns permitted for long-hold SKUs (>90 days). Do not markdown during stockout risk window; coordinate with promo calendar."},
 {"doc_type":"Advisory","name":"DC Capacity Advisory","body":"Receiving slots 08:00–18:00 Mon–Sat. Max lines per PO: 200. Large inbound requires 48h scheduling; avoid Friday cutoffs."},
 {"doc_type":"Checklist","name":"Inventory Audit Checklist","body":"Cycle counts weekly for A SKUs, bi-weekly for B SKUs. Investigate large negative adjustments; reconcile ASN discrepancies within 24h."},
 {"doc_type":"SOP","name":"Stockout Handling SOP","body":"If OOS projected within 3 days: throttle demand; propose substitution SKU; communicate ETA; backorder if policy allows."},
 {"doc_type":"SOP","name":"Data Quality SOP","body":"If data latency >24h for channel X, switch to backup feed. Correct anomalies (qty>1000) before forecast; log corrections."}
]


def upload_text(bucket: str, name: str, text: str) -> str:
    """
    Uploads plain text to a Google Cloud Storage bucket and returns the `gs://` URL.

    The object key is namespaced under `docs/` and includes a UTC timestamp and a
    sanitized file name derived from `name`.

    Args:
        bucket (str): Target GCS bucket name.
        name (str): Human-readable document name used to build the object key.
        text (str): Text content to upload.

    Returns:
        str: Publicly addressable GCS URL in the form `gs://{bucket}/{key}`.

    Notes:
        - Content type is set to `text/plain`.
        - Timestamp uses `datetime.UTC` to ensure consistency across environments.
    """
    # Instantiate a Storage client and bucket handle.
    client = storage.Client()
    b = client.bucket(bucket)

    # Build a unique object key with ISO timestamp and a safe file name.
    key = f"docs/{datetime.datetime.now(datetime.UTC).isoformat()}_{name.replace(' ','_')}.txt"

    # Create a blob and upload the text content.
    blob = b.blob(key)
    blob.upload_from_string(text, content_type='text/plain')

    # Return the `gs://` URL for reference/citation storage.
    return f"gs://{bucket}/{key}"


if __name__ == "__main__":
    """
    Seeds policy/SOP documents to GCS, generates embeddings via Vertex AI, and
    inserts records into `retail.docs` with source URLs and vectors.

    Workflow:
        1) Validate that `GCS_BUCKET` is set; exit if missing.
        2) Initialize VertexAIEmbeddings with the configured model and location.
        3) For each entry in `DOCS`:
           - Upload the `body` text to GCS and capture the `gs://` URL.
           - Generate an embedding vector for the `body`.
           - Assert the embedding dimensionality equals `EMBED_DIM`.
           - Insert a row into `retail.docs` with (doc_type, source_url, body, embedding).
        4) Commit all inserts and print a completion summary.

    Notes:
        - `get_conn()` is expected to provide a psycopg2-like connection with
          context manager support for both the connection and cursor.
        - Embeddings are generated from the raw text body; downstream retrieval
          uses the same model/config to ensure vector space consistency.
    """
    # Guard: ensure a target GCS bucket is configured.
    if not BUCKET:
        raise SystemExit("Set GCS_BUCKET")

    # Initialize Vertex AI embeddings client.
    embeddings = VertexAIEmbeddings(model_name=MODEL, project=PROJECT, location=LOCATION)

    # -------------------------------------------------------------------------
    # Open a DB connection and cursor, then process documents sequentially:
    #   - Upload to GCS for durable storage and citation.
    #   - Embed text via Vertex AI.
    #   - Persist source URL, body, and embedding to `retail.docs`.
    # -------------------------------------------------------------------------
    with get_conn() as conn, conn.cursor() as cur:
        for d in DOCS:
            # Upload text to GCS and obtain a `gs://` URL.
            gcs = upload_text(BUCKET, d['name'], d['body'])

            # Generate an embedding vector; validate dimensionality.
            vec = embeddings.embed_query(d['body'])
            assert len(vec) == EMBED_DIM

            # Insert document metadata and embedding into the database.
            cur.execute(
                "INSERT INTO retail.docs (doc_type, source_url, body, embedding) VALUES (%s,%s,%s,%s)",
                (d['doc_type'], gcs, d['body'], vec)
            )

        # Commit batched inserts after processing all documents.
        conn.commit()

    # Output completion message with the number of documents processed.
    print(f"✅ Generated & embedded {len(DOCS)} docs")
