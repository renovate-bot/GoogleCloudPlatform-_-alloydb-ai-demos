--schema for multi model use case ----
-- ANN search
CREATE SCHEMA IF NOT EXISTS :"schema_name";
CREATE EXTENSION IF NOT EXISTS alloydb_scann;

CREATE EXTENSION IF NOT EXISTS vector;

-- Videos and metadata

CREATE TABLE IF NOT EXISTS :"schema_name".video_meta (
  id BIGSERIAL PRIMARY KEY,
  file_name TEXT NOT NULL UNIQUE,
  label TEXT,
  split TEXT,
  duration_sec INT,
  width INT,
  height INT,
  fps REAL
);

CREATE TABLE IF NOT EXISTS :"schema_name".video_blobs (
  video_id BIGINT PRIMARY KEY REFERENCES :"schema_name".video_meta(id) ON DELETE CASCADE,
  video_data BYTEA NOT NULL
);

CREATE TABLE IF NOT EXISTS :"schema_name".video_embeddings (
  video_id BIGINT PRIMARY KEY REFERENCES :"schema_name".video_meta(id) ON DELETE CASCADE,
  embedding vector(1408) NOT NULL,
  frame_count INT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_video_embeddings_ivfflat_cos
  ON :"schema_name".video_embeddings USING ivfflat (embedding vector_cosine_ops)
  WITH (lists = 100);