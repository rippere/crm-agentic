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
  healthScore: number;      // 0-100, 100 = healthy
  expectedClose: string | null;
  assignedAgent: string | null;
  notes: string | null;
  createdAt: string | null;
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

// ─── Life / Accountability Ledger ─────────────────────────────────────────────
// Daily KPI snapshots pushed by the local collector, keyed on (date, metric).
// `meta` is metric-specific (e.g. git_commits carries per-project counts).
export type KpiDomain = "engineering" | "knowledge" | "product" | "life";

export interface KpiSnapshot {
  id: string;
  workspace_id: string;
  date: string;        // ISO date (YYYY-MM-DD)
  domain: KpiDomain | string;
  metric: string;
  value: number;
  meta: Record<string, unknown>;
  updated_at?: string | null;
}

// Commitments harvested from work-session logs (kind 'auto') or declared in the
// UI (kind 'explicit'), scored kept/broken with evidence by the weekly retro agent.
export type CommitmentKind = "auto" | "explicit";
export type CommitmentStatus = "open" | "kept" | "broken" | "dropped";

export interface Commitment {
  id: string;
  workspace_id: string;
  external_id: string | null;
  title: string;
  kind: CommitmentKind | string;
  source: string | null;
  declared_at: string;        // ISO datetime
  due_date: string | null;    // ISO date
  status: CommitmentStatus | string;
  evidence: string | null;
  scored_at: string | null;   // ISO datetime
  created_at?: string | null;
  updated_at?: string | null;
}

// Shape of the `meta` payload carried by a `life_retro` activity event, written
// by the weekly retro agent. Arrives JSON-encoded (activity_events.meta is text)
// and is parsed defensively on the client — every field may be absent.
export interface RetroMeta {
  week?: string;              // ISO date of the retro's week (Monday or Sunday anchor)
  kept_rate?: number | null;  // 0-1, null on the first week before anything is scored
  kept?: number;
  broken?: number;
  dropped?: number;
  harvested?: number;
  open?: number;
  judgment?: string[];        // prose conclusions — the centrepiece of the retro card
}

// Per ISO-week (Monday-anchored) rollup over the last N weeks. `kept_rate` is
// null when no outcomes were scored that week (denominator 0) — a gap, not a zero.
export interface CommitmentWeekStats {
  week_start: string;         // ISO date (Monday)
  declared: number;
  kept: number;
  broken: number;
  dropped: number;
  open: number;
  kept_rate: number | null;
}

// ─── Lead-Gen / Outbound Engagement module (camelCase app types) ─────────────
// Client-facing shapes for the funnel engine: leads → segments → campaigns →
// sequences → enrollments → engagement events. Mirrors the `Deal`/`Contact`
// convention (camelCase fields; timestamps as ISO strings; JSONB as typed
// records). Snake_case DB rows live in `supabase.ts`; hooks map row → app type.

// The six funnel stages (mirror the SQL CHECK on leads.stage).
export type LeadStage =
  | "new"
  | "contacted"
  | "engaged"
  | "qualified"
  | "converted"
  | "lost";

// How a lead entered the funnel (mirror the SQL CHECK on leads.source).
export type LeadSource =
  | "import"
  | "manual"
  | "web"
  | "api"
  | "referral"
  | "event";

// Engagement-score band, derived by the scoring worker. Mirrors LeadScore
// (cold/warm/hot) so the same score-config idiom applies.
export type EngagementLabel = "cold" | "warm" | "hot";

// Denormalized latest engagement score detail (mirrors contact ml_score shape).
export interface LeadScoreDetail {
  value: number;              // 0-100
  label: EngagementLabel;
  signals: string[];
}

export interface Lead {
  id: string;
  workspaceId: string;
  contactId: string | null;   // set once promoted to a contact
  name: string | null;
  email: string | null;
  phone: string | null;
  company: string | null;
  title: string | null;
  source: LeadSource;
  stage: LeadStage;
  score: number;              // 0-100 denormalized latest
  scoreDetail: LeadScoreDetail;
  ownerId: string | null;
  customFields: Record<string, unknown>;
  externalId: string | null;
  lastEngagedAt: string | null;
  createdAt: string | null;
  updatedAt: string | null;
}

// One row of the funnel rollup: count + summed score per stage.
export interface LeadFunnelStage {
  stage: LeadStage;
  count: number;
  value: number;
}

// ─── Segments ────────────────────────────────────────────────────────────────
export type SegmentKind = "static" | "dynamic";

// Stored filter for a dynamic segment (evaluated at launch). All optional.
export interface SegmentFilter {
  stage?: LeadStage;
  source?: LeadSource;
  minScore?: number;
  tags?: string[];
  [key: string]: unknown;
}

export interface Segment {
  id: string;
  workspaceId: string;
  name: string;
  description: string | null;
  kind: SegmentKind;
  filter: SegmentFilter;
  memberCount: number;
  createdAt: string | null;
  updatedAt: string | null;
}

// ─── Campaigns ───────────────────────────────────────────────────────────────
export type CampaignStatus =
  | "draft"
  | "scheduled"
  | "active"
  | "paused"
  | "completed"
  | "archived";

// email/sms/mixed — shared by campaigns and sequences.
export type SequenceChannel = "email" | "sms" | "mixed";

// Denormalized campaign rollup counters.
export interface CampaignStats {
  enrolled?: number;
  sent?: number;
  opened?: number;
  clicked?: number;
  replied?: number;
  converted?: number;
  [key: string]: number | undefined;
}

export interface Campaign {
  id: string;
  workspaceId: string;
  segmentId: string | null;
  sequenceId: string | null;
  name: string;
  status: CampaignStatus;
  channel: SequenceChannel;
  scheduledAt: string | null;
  startedAt: string | null;
  completedAt: string | null;
  stats: CampaignStats;
  settings: Record<string, unknown>;
  createdAt: string | null;
  updatedAt: string | null;
}

// Live campaign stats rollup (from GET …/campaigns/{id}/stats).
export interface CampaignStatsResponse {
  campaignId: string;
  status: CampaignStatus | string;
  stats: CampaignStats;
  eventsByType: Record<string, number>;
  totalEvents: number;
}

// ─── Sequences & steps ───────────────────────────────────────────────────────
export type SequenceStatus = "draft" | "active" | "archived";

// A single step's delivery channel (no 'mixed' at the step level).
export type SequenceStepChannel = "email" | "sms";

export interface SequenceStep {
  id: string;
  workspaceId: string;
  sequenceId: string;
  stepOrder: number;          // 0-based position
  channel: SequenceStepChannel;
  delayHours: number;         // wait since the previous step
  subject: string | null;     // email only
  bodyTemplate: string;       // supports {{name}}, {{company}} tokens
  requiresApproval: boolean;  // HITL gate (bot → human)
  aiGenerate: boolean;        // draft via Claude at send time
  createdAt: string | null;
  updatedAt: string | null;
}

export interface Sequence {
  id: string;
  workspaceId: string;
  name: string;
  description: string | null;
  channel: SequenceChannel;
  status: SequenceStatus;
  stepCount: number;
  settings: Record<string, unknown>;
  createdAt: string | null;
  updatedAt: string | null;
  steps?: SequenceStep[];     // present on the detail endpoint
}

// Editable step shape used by the builder's PUT …/steps save.
export interface SequenceStepInput {
  stepOrder?: number;
  channel: SequenceStepChannel;
  delayHours: number;
  subject?: string | null;
  bodyTemplate: string;
  requiresApproval: boolean;
  aiGenerate: boolean;
}

// ─── Enrollments ─────────────────────────────────────────────────────────────
export type EnrollmentStatus =
  | "active"
  | "waiting"
  | "paused"
  | "completed"
  | "stopped"
  | "bounced";

export interface Enrollment {
  id: string;
  workspaceId: string;
  campaignId: string;
  sequenceId: string;
  leadId: string;
  currentStep: number;
  status: EnrollmentStatus;
  nextRunAt: string | null;
  lastSentAt: string | null;
  createdAt: string | null;
  updatedAt: string | null;
}

// ─── Engagement events ───────────────────────────────────────────────────────
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
  workspaceId: string;
  leadId: string;
  campaignId: string | null;
  enrollmentId: string | null;
  stepId: string | null;
  type: EngagementEventType;
  channel: SequenceStepChannel | null;
  weight: number;
  metadata: Record<string, unknown>;
  occurredAt: string;
  createdAt: string | null;
}

// ─── Outreach approval queue (bot → human HITL handoff) ──────────────────────
export interface PendingOutreach {
  enrollmentId: string;
  leadId: string;
  campaignId: string | null;
  sequenceId: string | null;
  currentStep: number;
  status: EnrollmentStatus | string;
  subject: string | null;
  body: string;
  // Display conveniences carried by the demo fixtures / enriched responses.
  leadName?: string | null;
  leadCompany?: string | null;
  aiGenerated?: boolean;
}

// Editable draft returned by POST …/outreach/{id}/draft.
export interface OutreachDraft {
  enrollmentId: string;
  subject: string | null;
  body: string;
  aiGenerated: boolean;
}
