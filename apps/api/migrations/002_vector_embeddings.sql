-- ─── 002_vector_embeddings.sql ────────────────────────────────────────────────
-- Adds semantic embedding column to contacts (384-dim, all-MiniLM-L6-v2)

CREATE EXTENSION IF NOT EXISTS vector;

ALTER TABLE contacts
  ADD COLUMN IF NOT EXISTS embedding vector(384);

-- HNSW index for fast approximate nearest-neighbor search
CREATE INDEX IF NOT EXISTS idx_contacts_embedding
  ON contacts
  USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);
