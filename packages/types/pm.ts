// ─── PM / Workspace Types ─────────────────────────────────────────────────────
export type WorkspaceMode = "sales" | "pm" | "both";

export interface Workspace {
  id: string;
  name: string;
  slug: string;
  mode: WorkspaceMode;
  created_at: string;
}

export interface User {
  id: string;
  supabase_uid: string;
  workspace_id: string;
  email: string;
  role: "admin" | "member";
  created_at: string;
}

export type TaskStatus = "open" | "in_progress" | "done" | "cancelled";

export interface Task {
  id: string;
  workspace_id: string;
  message_id: string | null;
  contact_id: string | null;
  title: string;
  description: string;
  status: TaskStatus;
  due_date: string | null;
  assignee_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface Message {
  id: string;
  workspace_id: string;
  connector_id: string;
  external_id: string;
  subject: string;
  body_plain: string;
  sender_email: string;
  received_at: string;
  contact_id: string | null;
  processed: boolean;
  created_at: string;
}

export interface ClarityScore {
  id: string;
  workspace_id: string;
  message_id: string;
  score: number; // 0-100
  rationale: string;
  model_used: string;
  created_at: string;
}

export type ConnectorService = "gmail" | "slack" | "teams";

export interface Connector {
  id: string;
  workspace_id: string;
  service: ConnectorService;
  encrypted_token: string;
  refresh_token: string | null;
  token_expiry: string | null;
  external_email: string | null;
  message_count: number;
  task_count: number;
  last_sync: string | null;
  created_at: string;
}

export type MetricDataType = "text" | "number" | "boolean" | "date";

export interface MetricTemplate {
  id: string;
  workspace_id: string;
  name: string;
  description: string;
  data_type: MetricDataType;
  created_at: string;
}
