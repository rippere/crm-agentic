import { createClient } from "@supabase/supabase-js";

// ─── DB row types (snake_case, matches Supabase columns) ─────
export interface ContactRow {
  id: string;
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
  type: string;
  agent_name: string;
  description: string;
  meta: string;
  severity: "info" | "success" | "warning";
  created_at: string;
}

// ─── Supabase Database type (tells the client about our tables) ─
export interface Database {
  public: {
    Tables: {
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
    };
    Views: Record<string, never>;
    Functions: Record<string, never>;
    Enums: Record<string, never>;
  };
}

// ─── Lazy singleton client ────────────────────────────────────
// We don't pass the Database generic to createClient — the newer SDK's
// overload resolution fights manual Database types. Zod validates inputs;
// we cast outputs to our typed interfaces at the call site.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
let _client: ReturnType<typeof createClient<any>> | null = null;

export function getSupabase() {
  if (_client) return _client;

  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

  if (!url || !key) {
    throw new Error(
      "Missing Supabase credentials.\n" +
      "Copy .env.local.example → .env.local and add your Project URL and anon key."
    );
  }

  _client = createClient(url, key);
  return _client;
}
