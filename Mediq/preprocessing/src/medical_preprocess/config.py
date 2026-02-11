from __future__ import annotations
import os
from dataclasses import dataclass

@dataclass(frozen=True)
class GCPConfig:
    """Google Cloud configuration.

    Attributes:
        project_id: GCP project ID.
        location: Default region for Vertex AI and datasets.
    """
    project_id: str
    location: str = "us-central1"

@dataclass(frozen=True)
class AlloyDBConfig:
    """AlloyDB connection config for the connector.

    Attributes:
        instance_uri: AlloyDB instance URI.
        user: Database user.
        password: Database password.
        database: Target database name.
        embedding_model: Model ID for google_ml.embedding.
    """
    instance_uri: str
    user: str
    password: str
    database: str
    embedding_model: str = "text-embedding-005"

@dataclass(frozen=True)
class Defaults:
    schema: str = "alloydb_demo"
    details_table: str = "disease_details_info"
    images_table: str = "disease_images_info"

@dataclass(frozen=True)
class AppConfig:
    gcp: GCPConfig
    alloydb: AlloyDBConfig
    defaults: Defaults

    @staticmethod
    def from_env() -> "AppConfig":
        gcp = GCPConfig(
            project_id=os.getenv("GCP_PROJECT_ID", ""),
            location=os.getenv("GCP_LOCATION", "us-central1"),
        )
        alloy = AlloyDBConfig(
            instance_uri=os.getenv("ALLOYDB_INSTANCE_URI", ""),
            user=os.getenv("ALLOYDB_USER", ""),
            password=os.getenv("ALLOYDB_PASSWORD", ""),
            database=os.getenv("ALLOYDB_DB", "postgres"),
            embedding_model=os.getenv("ALLOYDB_EMBEDDING_MODEL", "text-embedding-005"),
        )
        defaults = Defaults(
            schema=os.getenv("ALLOYDB_DEFAULT_SCHEMA", "alloydb_demo"),
            details_table=os.getenv("ALLOYDB_DETAILS_TABLE", "disease_details_info"),
            images_table=os.getenv("ALLOYDB_IMAGES_TABLE", "disease_images_info"),
        )
        return AppConfig(gcp=gcp, alloydb=alloy, defaults=defaults)
