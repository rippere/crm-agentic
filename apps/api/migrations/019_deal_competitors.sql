-- Migration 019: add competitors JSONB column to deals
ALTER TABLE deals
  ADD COLUMN IF NOT EXISTS competitors JSONB NOT NULL DEFAULT '[]'::jsonb;
