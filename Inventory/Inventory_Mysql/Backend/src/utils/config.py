import os
from dotenv import load_dotenv

load_dotenv()


# Cloud SQL instance connection string
INSTANCE_CONNECTION_NAME = os.getenv("INSTANCE_CONNECTION_NAME")
# Choose PUBLIC or PRIVATE depending on your instance’s IP type
CLOUDSQL_IP_TYPE = os.getenv("CLOUDSQL_IP_TYPE")
# ---- Auth options ----
# A) Password Auth (traditional MySQL user/password)
MYSQL_HOST = os.getenv("MYSQL_HOST")
MYSQL_PORT = os.getenv("MYSQL_PORT")
MYSQL_USER = os.getenv("MYSQL_USER")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD")
MYSQL_DB_NAME = os.getenv("MYSQL_DB_NAME")
MYSQL_TABLE_SCHEMA = os.getenv("MYSQL_TABLE_SCHEMA")

# B) IAM DB Auth (no password needed if enabled)
# Set to "true" if your instance has IAM DB authentication enabled and
# you have an IAM-authenticated MySQL user (e.g., your GCP identity).
MYSQL_IAM_AUTH = os.getenv("MYSQL_IAM_AUTH")

# ---------- Google Cloud ----------
PROJECT_ID = os.getenv("PROJECT_ID")
REGION = os.getenv("REGION")
GCS_BUCKET = os.getenv("GCS_BUCKET")

MAX_ROWS = os.getenv("MAX_ROWS")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL")
EMBEDDING_DIM = os.getenv("EMBEDDING_DIM")

VERTEX_LOCATION = os.getenv("VERTEX_LOCATION")
INSTANCE = os.getenv("INSTANCE")
