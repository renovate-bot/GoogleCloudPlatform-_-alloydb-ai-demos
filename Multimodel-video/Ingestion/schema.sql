
-- optional: improves ANN search
CREATE EXTENSION IF NOT EXISTS alloydb_scann;

CREATE EXTENSION IF NOT EXISTS vector;

-- Videos and metadata
CREATE TABLE IF NOT EXISTS video_meta (
  id BIGSERIAL PRIMARY KEY,
  file_name TEXT NOT NULL UNIQUE,
  label TEXT,
  split TEXT,
  duration_sec INT,
  width INT,
  height INT,
  fps REAL
);

CREATE TABLE IF NOT EXISTS video_blobs (
  video_id BIGINT PRIMARY KEY REFERENCES video_meta(id) ON DELETE CASCADE,
  video_data BYTEA NOT NULL
);

CREATE TABLE IF NOT EXISTS video_embeddings (
  video_id BIGINT PRIMARY KEY REFERENCES video_meta(id) ON DELETE CASCADE,
  embedding vector(1408) NOT NULL,
  frame_count INT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_video_embeddings_ivfflat_cos
  ON video_embeddings USING ivfflat (embedding vector_cosine_ops)
  WITH (lists = 100);



-- Store object-storage URIs for videos (instead of BYTEA)
CREATE TABLE IF NOT EXISTS video_assets (
  video_id   BIGINT PRIMARY KEY REFERENCES video_meta(id) ON DELETE CASCADE,
  gcs_uri    TEXT NOT NULL,
  size_bytes BIGINT,
  mime_type  TEXT DEFAULT 'video/mp4'
);

