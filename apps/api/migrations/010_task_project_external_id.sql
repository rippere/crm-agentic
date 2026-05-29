-- 010: external_id for idempotent vault -> NovaCRM sync.
-- Mirrors the existing messages.external_id dedup pattern. Nullable so existing
-- rows are unaffected; partial-unique per (workspace_id, external_id) enforces
-- one row per external key without colliding on the many NULLs. Idempotent.

ALTER TABLE tasks    ADD COLUMN IF NOT EXISTS external_id TEXT;
ALTER TABLE projects ADD COLUMN IF NOT EXISTS external_id TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS uq_tasks_workspace_external
    ON tasks (workspace_id, external_id) WHERE external_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_projects_workspace_external
    ON projects (workspace_id, external_id) WHERE external_id IS NOT NULL;
