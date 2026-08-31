-- Migration 020: add mentions JSONB column to deals
ALTER TABLE deals
  ADD COLUMN IF NOT EXISTS mentions JSONB NOT NULL DEFAULT '[]'::jsonb;
