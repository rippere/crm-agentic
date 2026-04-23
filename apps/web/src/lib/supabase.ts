import { createBrowserClient as _createBrowserClient } from "@supabase/ssr";
import { createServerClient as _createServerClient } from "@supabase/ssr";
import type { CookieOptions } from "@supabase/ssr";
import type { ReadonlyRequestCookies } from "next/dist/server/web/spec-extension/adapters/request-cookies";

// ─── DB row types (snake_case, matches Supabase columns) ─────────────────────
export interface WorkspaceRow {
  id: string;
  name: string;
  slug: string;
  mode: "sales" | "pm" | "both";
  created_at: string;
}

export interface UserRow {
  id: string;
  supabase_uid: string;
  workspace_id: string;
  email: string;
  role: "admin" | "member";
  created_at: string;
}

export interface ContactRow {
  id: string;
  workspace_id: string;
  name: string;
  email: string;
  company: string;
  role: string;
  avatar: string;
  status: "lead" | "prospect" | "customer" | "churned";
  ml_score: {
    value: number;
    label: "hot" | "warm" | "cold";
    trend: "up" | "down" | "stable";
    signals: string[];
  };
  semantic_tags: Array<{
    label: string;
    confidence: number;
    color: "indigo" | "emerald" | "amber" | "rose";
  }>;
  last_activity: string;
  revenue: number;
  deal_count: number;
  created_at: string;
  updated_at: string;
}

export interface DealRow {
  id: string;
  workspace_id: string;
  title: string;
  company: string;
  contact_name: string;
  contact_id: string | null;
  value: number;
  stage: "discovery" | "qualified" | "proposal" | "negotiation" | "closed_won" | "closed_lost";
  ml_win_probability: number;
  expected_close: string;
  assigned_agent: string;
  notes: string;
  created_at: string;
  updated_at: string;
}

export interface AgentRow {
  id: string;
  workspace_id: string;
  name: string;
  type: string;
  status: "active" | "processing" | "idle" | "error";
  description: string;
  model: string;
  accuracy: number;
  tasks_today: number;
  last_run: string;
  workflow: Array<{
    id: string;
    label: string;
    type: "trigger" | "action" | "condition" | "output";
    position: { x: number; y: number };
    connected?: string[];
  }>;
  metrics: Array<{ label: string; value: string; delta?: string }>;
  created_at: string;
  updated_at: string;
}

export interface ActivityEventRow {
  id: string;
  workspace_id: string;
  type: string;
  agent_name: string;
  description: string;
  meta: string;
  severity: "info" | "success" | "warning";
  created_at: string;
}

export interface ConnectorRow {
  id: string;
  workspace_id: string;
  service: "gmail" | "slack" | "teams";
  encrypted_token: string;
  refresh_token: string | null;
  token_expiry: string | null;
  external_email: string | null;
  message_count: number;
  task_count: number;
  last_sync: string | null;
  created_at: string;
}

export interface MessageRow {
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

export interface TaskRow {
  id: string;
  workspace_id: string;
  message_id: string | null;
  contact_id: string | null;
  title: string;
  description: string;
  status: "open" | "in_progress" | "done" | "cancelled";
  due_date: string | null;
  assignee_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface MetricTemplateRow {
  id: string;
  workspace_id: string;
  name: string | null;
  description: string | null;
  data_type: "text" | "number" | "boolean" | "date" | null;
  created_at: string;
}

export interface ClarityScoreRow {
  id: string;
  workspace_id: string;
  message_id: string | null;
  score: number | null;
  rationale: string | null;
  model_used: string;
  created_at: string;
}

// ─── Supabase Database type (tells the client about our tables) ───────────────
export interface Database {
  public: {
    Tables: {
      workspaces: {
        Row: WorkspaceRow;
        Insert: Omit<WorkspaceRow, "id" | "created_at">;
        Update: Partial<Omit<WorkspaceRow, "id" | "created_at">>;
      };
      users: {
        Row: UserRow;
        Insert: Omit<UserRow, "id" | "created_at">;
        Update: Partial<Omit<UserRow, "id" | "created_at">>;
      };
      contacts: {
        Row: ContactRow;
        Insert: Omit<ContactRow, "id" | "created_at" | "updated_at">;
        Update: Partial<Omit<ContactRow, "id" | "created_at" | "updated_at">>;
      };
      deals: {
        Row: DealRow;
        Insert: Omit<DealRow, "id" | "created_at" | "updated_at">;
        Update: Partial<Omit<DealRow, "id" | "created_at" | "updated_at">>;
      };
      agents: {
        Row: AgentRow;
        Insert: Omit<AgentRow, "id" | "created_at" | "updated_at">;
        Update: Partial<Omit<AgentRow, "id" | "created_at" | "updated_at">>;
      };
      activity_events: {
        Row: ActivityEventRow;
        Insert: Omit<ActivityEventRow, "id" | "created_at">;
        Update: Partial<Omit<ActivityEventRow, "id" | "created_at">>;
      };
      connectors: {
        Row: ConnectorRow;
        Insert: Omit<ConnectorRow, "id" | "created_at">;
        Update: Partial<Omit<ConnectorRow, "id" | "created_at">>;
      };
      messages: {
        Row: MessageRow;
        Insert: Omit<MessageRow, "id" | "created_at">;
        Update: Partial<Omit<MessageRow, "id" | "created_at">>;
      };
      tasks: {
        Row: TaskRow;
        Insert: Omit<TaskRow, "id" | "created_at" | "updated_at">;
        Update: Partial<Omit<TaskRow, "id" | "created_at" | "updated_at">>;
      };
      metric_templates: {
        Row: MetricTemplateRow;
        Insert: Omit<MetricTemplateRow, "id" | "created_at">;
        Update: Partial<Omit<MetricTemplateRow, "id" | "created_at">>;
      };
      clarity_scores: {
        Row: ClarityScoreRow;
        Insert: Omit<ClarityScoreRow, "id" | "created_at">;
        Update: Partial<Omit<ClarityScoreRow, "id" | "created_at">>;
      };
    };
    Views: Record<string, never>;
    Functions: Record<string, never>;
    Enums: Record<string, never>;
  };
}

// ─── Browser client (singleton) ──────────────────────────────────────────────
let _browserClient: ReturnType<typeof _createBrowserClient<Database>> | null = null;

export function createBrowserClient() {
  if (_browserClient) return _browserClient;

  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

  if (!url || !key) {
    throw new Error(
      "Missing Supabase credentials.\n" +
      "Copy .env.example → .env.local and add your Project URL and anon key."
    );
  }

  _browserClient = _createBrowserClient<Database>(url, key);
  return _browserClient;
}

// ─── Server client (per-request, uses cookies) ───────────────────────────────
export function createServerClient(cookieStore: ReadonlyRequestCookies) {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL!;
  const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!;

  return _createServerClient<Database>(url, key, {
    cookies: {
      get(name: string) {
        return cookieStore.get(name)?.value;
      },
      set(_name: string, _value: string, _options: CookieOptions) {
        // Server components can't set cookies directly; handled by middleware
      },
      remove(_name: string, _options: CookieOptions) {
        // Server components can't remove cookies directly; handled by middleware
      },
    },
  });
}

// ─── Legacy export (kept for backward compat during migration) ───────────────
/** @deprecated Use createBrowserClient() instead */
export function getSupabase() {
  return createBrowserClient();
}
