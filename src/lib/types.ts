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
