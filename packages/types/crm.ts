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

// ─── Lead-Gen: Leads ──────────────────────────────────────────────────────────
export type LeadSource =
  | "import"
  | "manual"
  | "web"
  | "api"
  | "referral"
  | "event";

export type LeadStage =
  | "new"
  | "contacted"
  | "engaged"
  | "qualified"
  | "converted"
  | "lost";

export interface Lead {
  id: string;
  workspace_id: string;
  contact_id: string | null;
  name: string | null;
  email: string | null;
  phone: string | null;
  company: string | null;
  title: string | null;
  source: LeadSource;
  stage: LeadStage;
  score: number; // 0-100 denormalized latest
  score_detail: Record<string, unknown>;
  owner_id: string | null;
  custom_fields: Record<string, unknown>;
  external_id: string | null;
  last_engaged_at: string | null;
  created_at: string;
  updated_at: string;
}

// ─── Lead-Gen: Segments ───────────────────────────────────────────────────────
export type SegmentKind = "static" | "dynamic";

export interface LeadSegment {
  id: string;
  workspace_id: string;
  name: string;
  description: string | null;
  kind: SegmentKind;
  filter: Record<string, unknown>;
  member_count: number;
  created_at: string;
  updated_at: string;
}

// ─── Lead-Gen: Sequences ──────────────────────────────────────────────────────
export type SequenceChannel = "email" | "sms" | "mixed";
export type SequenceStatus = "draft" | "active" | "archived";

export interface Sequence {
  id: string;
  workspace_id: string;
  name: string;
  description: string | null;
  channel: SequenceChannel;
  status: SequenceStatus;
  step_count: number;
  settings: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface SequenceStep {
  id: string;
  workspace_id: string;
  sequence_id: string;
  step_order: number;
  channel: "email" | "sms";
  delay_hours: number;
  subject: string | null;
  body_template: string;
  requires_approval: boolean;
  ai_generate: boolean;
  created_at: string;
  updated_at: string;
}

// ─── Lead-Gen: Campaigns ──────────────────────────────────────────────────────
export type CampaignStatus =
  | "draft"
  | "scheduled"
  | "active"
  | "paused"
  | "completed"
  | "archived";

export interface Campaign {
  id: string;
  workspace_id: string;
  segment_id: string | null;
  sequence_id: string | null;
  name: string;
  status: CampaignStatus;
  channel: SequenceChannel;
  scheduled_at: string | null;
  started_at: string | null;
  completed_at: string | null;
  stats: Record<string, unknown>;
  settings: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

// ─── Lead-Gen: Enrollments ────────────────────────────────────────────────────
export type EnrollmentStatus =
  | "active"
  | "waiting"
  | "paused"
  | "completed"
  | "stopped"
  | "bounced";

export interface SequenceEnrollment {
  id: string;
  workspace_id: string;
  campaign_id: string;
  sequence_id: string;
  lead_id: string;
  current_step: number;
  status: EnrollmentStatus;
  next_run_at: string | null;
  last_sent_at: string | null;
  created_at: string;
  updated_at: string;
}

// ─── Lead-Gen: Engagement Events ──────────────────────────────────────────────
export type EngagementEventType =
  | "queued"
  | "sent"
  | "delivered"
  | "opened"
  | "clicked"
  | "replied"
  | "bounced"
  | "unsubscribed"
  | "converted"
  | "approved"
  | "rejected";

export interface EngagementEvent {
  id: string;
  workspace_id: string;
  lead_id: string;
  campaign_id: string | null;
  enrollment_id: string | null;
  step_id: string | null;
  type: EngagementEventType;
  channel: "email" | "sms" | null;
  weight: number;
  metadata: Record<string, unknown>;
  occurred_at: string;
  created_at: string;
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
