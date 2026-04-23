// ─── Contact & Lead ───────────────────────────────────────────────────────────
export type LeadScore = "hot" | "warm" | "cold";
export type ContactStatus = "lead" | "prospect" | "customer" | "churned";

export interface SemanticTag {
  label: string;
  confidence: number; // 0-1
  color: "indigo" | "emerald" | "amber" | "rose";
}

export interface MLScore {
  value: number;      // 0-100
  label: LeadScore;
  trend: "up" | "down" | "stable";
  signals: string[];
}

export interface Contact {
  id: string;
  name: string;
  email: string;
  company: string;
  role: string;
  avatar: string;
  status: ContactStatus;
  mlScore: MLScore;
  semanticTags: SemanticTag[];
  lastActivity: string;
  deals: number;
  revenue: number;
  createdAt: string;
}

// ─── Pipeline / Deals ─────────────────────────────────────────────────────────
export type DealStage = "discovery" | "qualified" | "proposal" | "negotiation" | "closed_won" | "closed_lost";

export interface Deal {
  id: string;
  title: string;
  company: string;
  contactName: string;
  value: number;
  stage: DealStage;
  mlWinProbability: number; // 0-100
  expectedClose: string;
  assignedAgent: string;
  notes: string;
  createdAt: string;
}

// ─── Agents ───────────────────────────────────────────────────────────────────
export type AgentStatus = "active" | "processing" | "idle" | "error";
export type AgentType =
  | "semantic_sorter"
  | "lead_scorer"
  | "email_composer"
  | "call_summarizer"
  | "pipeline_optimizer"
  | "sentiment_analyzer";

export interface AgentMetric {
  label: string;
  value: string;
  delta?: string;
}

export interface Agent {
  id: string;
  name: string;
  type: AgentType;
  status: AgentStatus;
  description: string;
  model: string;
  accuracy: number; // 0-100
  tasksToday: number;
  metrics: AgentMetric[];
  lastRun: string;
  workflow: WorkflowNode[];
}

export interface WorkflowNode {
  id: string;
  label: string;
  type: "trigger" | "action" | "condition" | "output";
  position: { x: number; y: number };
  connected?: string[]; // node ids
}

// ─── Activity Feed ────────────────────────────────────────────────────────────
export type ActivityType =
  | "agent_run"
  | "contact_scored"
  | "deal_moved"
  | "email_sent"
  | "call_summarized"
  | "tag_applied"
  | "model_updated";

export interface ActivityEvent {
  id: string;
  type: ActivityType;
  agentName: string;
  description: string;
  meta?: string;
  timestamp: string;
  severity: "info" | "success" | "warning";
}

// ─── Dashboard KPIs ──────────────────────────────────────────────────────────
export interface KPI {
  id: string;
  label: string;
  value: string;
  delta: string;
  deltaType: "positive" | "negative" | "neutral";
  icon: string;
  sparkData: number[];
}

// ─── Workspace ────────────────────────────────────────────────────────────────
export type WorkspaceMode = "sales" | "pm" | "both";

export interface Workspace {
  id: string;
  name: string;
  slug: string;
  mode: WorkspaceMode;
  created_at: string;
}

// ─── App User ─────────────────────────────────────────────────────────────────
export interface AppUser {
  id: string;
  supabase_uid: string;
  workspace_id: string;
  email: string;
  role: "admin" | "member";
  created_at: string;
}

// ─── Connector ────────────────────────────────────────────────────────────────
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

// ─── Message ──────────────────────────────────────────────────────────────────
export interface Message {
  id: string;
  workspace_id: string;
  connector_id: string | null;
  external_id: string;
  subject: string | null;
  body_plain: string;
  sender_email: string | null;
  received_at: string | null;
  contact_id: string | null;
  processed: boolean;
  created_at: string;
}

// ─── Task ─────────────────────────────────────────────────────────────────────
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

// ─── Clarity Score ────────────────────────────────────────────────────────────
export interface ClarityScore {
  id: string;
  workspace_id: string;
  message_id: string | null;
  score: number | null;
  rationale: string | null;
  model_used: string;
  created_at: string;
}

// ─── Metric Template ──────────────────────────────────────────────────────────
export type MetricDataType = "text" | "number" | "boolean" | "date";

export interface MetricTemplate {
  id: string;
  workspace_id: string;
  name: string | null;
  description: string | null;
  data_type: MetricDataType | null;
  created_at: string;
}
