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
  workspace_id: string;
  name: string;
  email: string;
  company: string;
  role: string;
  avatar: string;
  status: ContactStatus;
  ml_score: MLScore;
  semantic_tags: SemanticTag[];
  last_activity: string;
  revenue: number;
  deal_count: number;
  created_at: string;
  updated_at: string;
}

// ─── Pipeline / Deals ─────────────────────────────────────────────────────────
export type DealStage =
  | "discovery"
  | "qualified"
  | "proposal"
  | "negotiation"
  | "closed_won"
  | "closed_lost";

export interface Deal {
  id: string;
  workspace_id: string;
  title: string;
  company: string;
  contact_name: string;
  contact_id: string | null;
  value: number;
  stage: DealStage;
  ml_win_probability: number; // 0-100
  expected_close: string;
  assigned_agent: string;
  notes: string;
  created_at: string;
  updated_at: string;
}

// ─── Agents ───────────────────────────────────────────────────────────────────
export type AgentStatus = "active" | "processing" | "idle" | "error";

export interface AgentMetric {
  label: string;
  value: string;
  delta?: string;
}

export interface WorkflowNode {
  id: string;
  label: string;
  type: "trigger" | "action" | "condition" | "output";
  position: { x: number; y: number };
  connected?: string[]; // node ids
}

export interface Agent {
  id: string;
  workspace_id: string;
  name: string;
  type: string;
  description: string;
  model: string;
  status: AgentStatus;
  accuracy: number;
  tasks_today: number;
  last_run: string;
  workflow: WorkflowNode[];
  metrics: AgentMetric[];
  created_at: string;
  updated_at: string;
}

// ─── Activity Feed ────────────────────────────────────────────────────────────
export interface ActivityEvent {
  id: string;
  workspace_id: string;
  type: string;
  agent_name: string;
  description: string;
  meta: string;
  severity: "info" | "success" | "warning";
  created_at: string;
}
