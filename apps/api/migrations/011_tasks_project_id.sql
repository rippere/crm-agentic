-- 011: add the missing tasks.project_id column.
-- The Task model has declared project_id (FK -> projects) for a while, but no
-- migration ever added it to the tasks table, so any insert/select referencing
-- project_id 500'd in prod — tasks were effectively uninsertable. Idempotent.

ALTER TABLE tasks ADD COLUMN IF NOT EXISTS project_id UUID REFERENCES projects(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks (project_id);
