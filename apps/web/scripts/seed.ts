/**
 * Seed script — populates Supabase with demo data (multi-tenant schema)
 * Run: npx tsx scripts/seed.ts
 *
 * Requires .env.local to be set up first.
 * NOTE: Run the unified schema (001_unified_schema.sql) in Supabase SQL editor first.
 */

import { createClient } from "@supabase/supabase-js";
import * as dotenv from "dotenv";
import * as path from "path";

dotenv.config({ path: path.resolve(process.cwd(), ".env.local") });

const supabase = createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL!,
  // Use service role key for seeding so RLS doesn't block inserts
  process.env.SUPABASE_SERVICE_ROLE_KEY ?? process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!
);

// ─── Run ─────────────────────────────────────────────────────────────────────
async function seed() {
  console.log("Seeding Supabase (multi-tenant schema)...\n");

  // ── 1. Create (or reuse) Demo Workspace ────────────────────────────────────
  console.log("  Creating demo workspace...");
  let workspaceId: string;

  const { data: existing } = await supabase
    .from("workspaces")
    .select("id")
    .eq("slug", "demo")
    .single();

  if (existing) {
    workspaceId = existing.id;
    console.log(`  Reusing existing workspace: ${workspaceId}`);
  } else {
    const { data: ws, error: wsErr } = await supabase
      .from("workspaces")
      .insert({ name: "Demo Workspace", slug: "demo", mode: "both" })
      .select()
      .single();
    if (wsErr || !ws) { console.error("  Workspace:", wsErr?.message); process.exit(1); }
    workspaceId = ws.id;
    console.log(`  Created workspace: ${workspaceId}`);
  }

  // TODO: create a real user row — requires a Supabase auth user to exist first.
  // Example (run after auth.signUp):
  //   await supabase.from("users").insert({ supabase_uid: "<auth-user-id>", workspace_id: workspaceId, email: "you@example.com", role: "admin" })

  // ── 2. Clear existing seeded data for this workspace ──────────────────────
  console.log("  Clearing existing workspace data...");
  await supabase.from("activity_events").delete().eq("workspace_id", workspaceId);
  await supabase.from("deals").delete().eq("workspace_id", workspaceId);
  await supabase.from("agents").delete().eq("workspace_id", workspaceId);
  await supabase.from("contacts").delete().eq("workspace_id", workspaceId);

  // ── 3. Contacts ────────────────────────────────────────────────────────────
  const contacts = [
    {
      workspace_id: workspaceId,
      name: "Sarah Chen", email: "s.chen@nexlabs.io", company: "NexLabs",
      role: "VP of Engineering", avatar: "SC", status: "customer",
      ml_score: { value: 92, label: "hot", trend: "up", signals: ["High engagement", "Recent demo request", "Budget confirmed"] },
      semantic_tags: [
        { label: "Enterprise Buyer", confidence: 0.97, color: "indigo" },
        { label: "Decision Maker", confidence: 0.91, color: "emerald" },
        { label: "Technical", confidence: 0.88, color: "indigo" },
      ],
      last_activity: "2 hours ago", revenue: 48000, deal_count: 3,
    },
    {
      workspace_id: workspaceId,
      name: "Marcus Webb", email: "m.webb@strataform.com", company: "StrataForm",
      role: "CEO", avatar: "MW", status: "prospect",
      ml_score: { value: 78, label: "warm", trend: "up", signals: ["Multiple page visits", "Downloaded whitepaper"] },
      semantic_tags: [
        { label: "C-Suite", confidence: 0.99, color: "amber" },
        { label: "Growth Stage", confidence: 0.82, color: "emerald" },
      ],
      last_activity: "Yesterday", revenue: 0, deal_count: 1,
    },
    {
      workspace_id: workspaceId,
      name: "Priya Nair", email: "priya@cloudvault.ai", company: "CloudVault AI",
      role: "Head of Ops", avatar: "PN", status: "lead",
      ml_score: { value: 61, label: "warm", trend: "stable", signals: ["Email opened x4", "LinkedIn profile viewed"] },
      semantic_tags: [
        { label: "Operations Focus", confidence: 0.85, color: "indigo" },
        { label: "AI-Adjacent", confidence: 0.79, color: "emerald" },
      ],
      last_activity: "3 days ago", revenue: 0, deal_count: 0,
    },
    {
      workspace_id: workspaceId,
      name: "James Okafor", email: "jokafor@meridian-cap.com", company: "Meridian Capital",
      role: "CFO", avatar: "JO", status: "customer",
      ml_score: { value: 88, label: "hot", trend: "stable", signals: ["Annual contract", "Referral source", "High NPS"] },
      semantic_tags: [
        { label: "Finance Sector", confidence: 0.96, color: "amber" },
        { label: "Expansion Ready", confidence: 0.73, color: "emerald" },
        { label: "Decision Maker", confidence: 0.94, color: "indigo" },
      ],
      last_activity: "1 day ago", revenue: 120000, deal_count: 2,
    },
    {
      workspace_id: workspaceId,
      name: "Lena Kovacs", email: "lena.k@solvio.eu", company: "Solvio EU",
      role: "Product Director", avatar: "LK", status: "prospect",
      ml_score: { value: 44, label: "cold", trend: "down", signals: ["No reply in 14 days", "Unsubscribed from one campaign"] },
      semantic_tags: [
        { label: "European Market", confidence: 0.91, color: "indigo" },
        { label: "Risk: Churn", confidence: 0.65, color: "rose" },
      ],
      last_activity: "2 weeks ago", revenue: 0, deal_count: 1,
    },
    {
      workspace_id: workspaceId,
      name: "Dmitri Volkov", email: "d.volkov@axion-sys.com", company: "Axion Systems",
      role: "CTO", avatar: "DV", status: "customer",
      ml_score: { value: 95, label: "hot", trend: "up", signals: ["Upsell candidate", "High feature adoption", "Champion user"] },
      semantic_tags: [
        { label: "Power User", confidence: 0.98, color: "emerald" },
        { label: "Technical", confidence: 0.95, color: "indigo" },
        { label: "Upsell Ready", confidence: 0.88, color: "emerald" },
      ],
      last_activity: "30 min ago", revenue: 240000, deal_count: 4,
    },
  ];

  console.log("  Inserting contacts...");
  const { error: cErr } = await supabase.from("contacts").insert(contacts);
  if (cErr) { console.error("  Contacts:", cErr.message); process.exit(1); }
  console.log(`  ${contacts.length} contacts`);

  // ── 4. Deals ───────────────────────────────────────────────────────────────
  const deals = [
    { workspace_id: workspaceId, title: "NexLabs Enterprise Suite", company: "NexLabs", contact_name: "Sarah Chen", value: 48000, stage: "negotiation", ml_win_probability: 87, expected_close: "Apr 30, 2026", assigned_agent: "Pipeline Optimizer", notes: "Legal review in progress. Champion confirmed budget." },
    { workspace_id: workspaceId, title: "StrataForm Pilot", company: "StrataForm", contact_name: "Marcus Webb", value: 12000, stage: "proposal", ml_win_probability: 62, expected_close: "May 15, 2026", assigned_agent: "Email Composer", notes: "Proposal sent. Awaiting feedback from board." },
    { workspace_id: workspaceId, title: "Meridian Capital Renewal", company: "Meridian Capital", contact_name: "James Okafor", value: 120000, stage: "qualified", ml_win_probability: 91, expected_close: "Jun 1, 2026", assigned_agent: "Lead Scorer", notes: "Annual renewal. Expansion to 5 more seats discussed." },
    { workspace_id: workspaceId, title: "Axion Systems Upsell", company: "Axion Systems", contact_name: "Dmitri Volkov", value: 65000, stage: "discovery", ml_win_probability: 74, expected_close: "May 30, 2026", assigned_agent: "Semantic Sorter", notes: "Interested in analytics add-on module." },
    { workspace_id: workspaceId, title: "CloudVault AI Starter", company: "CloudVault AI", contact_name: "Priya Nair", value: 8400, stage: "discovery", ml_win_probability: 45, expected_close: "Jun 20, 2026", assigned_agent: "Sentiment Analyzer", notes: "Early stage. Needs more qualification." },
    { workspace_id: workspaceId, title: "Solvio EU Enterprise", company: "Solvio EU", contact_name: "Lena Kovacs", value: 30000, stage: "closed_lost", ml_win_probability: 0, expected_close: "Mar 31, 2026", assigned_agent: "Pipeline Optimizer", notes: "Lost to competitor. Price was the primary objection." },
    { workspace_id: workspaceId, title: "NexLabs Analytics Module", company: "NexLabs", contact_name: "Sarah Chen", value: 18000, stage: "closed_won", ml_win_probability: 100, expected_close: "Apr 5, 2026", assigned_agent: "Pipeline Optimizer", notes: "Signed. Onboarding scheduled for Apr 12." },
  ];

  console.log("  Inserting deals...");
  const { error: dErr } = await supabase.from("deals").insert(deals);
  if (dErr) { console.error("  Deals:", dErr.message); process.exit(1); }
  console.log(`  ${deals.length} deals`);

  // ── 5. Agents ──────────────────────────────────────────────────────────────
  const agents = [
    {
      workspace_id: workspaceId,
      name: "Semantic Sorter", type: "semantic_sorter", status: "active",
      description: "Uses sentence-transformer embeddings to classify and tag contacts by intent, industry, role, and buying signals. Continuously re-ranks your contact list.",
      model: "all-MiniLM-L6-v2 + GPT-4o", accuracy: 96.4, tasks_today: 312, last_run: "2 min ago",
      metrics: [{ label: "Tags Applied Today", value: "1,204", delta: "+89" }, { label: "Avg Confidence", value: "94.1%", delta: "+0.3%" }, { label: "Reclassifications", value: "47" }],
      workflow: [
        { id: "w1", label: "New Contact Trigger", type: "trigger", position: { x: 0, y: 0 } },
        { id: "w2", label: "Embed Text (MiniLM)", type: "action", position: { x: 200, y: 0 }, connected: ["w1"] },
        { id: "w3", label: "Cosine Similarity Rank", type: "action", position: { x: 400, y: 0 }, connected: ["w2"] },
        { id: "w4", label: "Confidence > 0.85?", type: "condition", position: { x: 600, y: 0 }, connected: ["w3"] },
        { id: "w5", label: "Apply Semantic Tag", type: "output", position: { x: 800, y: -60 }, connected: ["w4"] },
        { id: "w6", label: "Queue for Review", type: "output", position: { x: 800, y: 60 }, connected: ["w4"] },
      ],
    },
    {
      workspace_id: workspaceId,
      name: "Lead Scorer", type: "lead_scorer", status: "active",
      description: "XGBoost model trained on historical deal outcomes. Scores every contact 0–100 using behavioral signals, firmographic data, and engagement patterns.",
      model: "XGBoost v2 + Feature Store", accuracy: 94.7, tasks_today: 524, last_run: "8 min ago",
      metrics: [{ label: "Scores Updated", value: "524", delta: "+112" }, { label: "Hot Leads", value: "23", delta: "+5" }, { label: "Model F1 Score", value: "0.947" }],
      workflow: [
        { id: "w1", label: "Behavior Event", type: "trigger", position: { x: 0, y: 0 } },
        { id: "w2", label: "Feature Extraction", type: "action", position: { x: 200, y: 0 }, connected: ["w1"] },
        { id: "w3", label: "XGBoost Inference", type: "action", position: { x: 400, y: 0 }, connected: ["w2"] },
        { id: "w4", label: "Update Contact Score", type: "output", position: { x: 600, y: 0 }, connected: ["w3"] },
      ],
    },
    {
      workspace_id: workspaceId,
      name: "Email Composer", type: "email_composer", status: "processing",
      description: "Generates hyper-personalized outreach emails using contact context, semantic tags, and deal stage. Adapts tone to role and industry.",
      model: "GPT-4o (fine-tuned)", accuracy: 91.2, tasks_today: 87, last_run: "Just now",
      metrics: [{ label: "Emails Drafted", value: "87", delta: "+22" }, { label: "Open Rate (7d)", value: "48.3%", delta: "+6.1%" }, { label: "Reply Rate (7d)", value: "22.1%", delta: "+3.4%" }],
      workflow: [
        { id: "w1", label: "Deal Stage Change", type: "trigger", position: { x: 0, y: 0 } },
        { id: "w2", label: "Fetch Contact Context", type: "action", position: { x: 200, y: 0 }, connected: ["w1"] },
        { id: "w3", label: "Compose with GPT-4o", type: "action", position: { x: 400, y: 0 }, connected: ["w2"] },
        { id: "w4", label: "Human Review?", type: "condition", position: { x: 600, y: 0 }, connected: ["w3"] },
        { id: "w5", label: "Send via Gmail API", type: "output", position: { x: 800, y: -60 }, connected: ["w4"] },
        { id: "w6", label: "Hold for Approval", type: "output", position: { x: 800, y: 60 }, connected: ["w4"] },
      ],
    },
    {
      workspace_id: workspaceId,
      name: "Call Summarizer", type: "call_summarizer", status: "idle",
      description: "Transcribes and summarizes sales calls. Extracts action items, objections, sentiment, and next steps. Updates contact timeline automatically.",
      model: "Whisper Large v3 + Claude 3.5", accuracy: 97.1, tasks_today: 14, last_run: "1 hour ago",
      metrics: [{ label: "Calls Processed", value: "14", delta: "+3" }, { label: "Avg Summary Time", value: "23s" }, { label: "Action Items Extracted", value: "41", delta: "+8" }],
      workflow: [
        { id: "w1", label: "Call Recording Upload", type: "trigger", position: { x: 0, y: 0 } },
        { id: "w2", label: "Whisper Transcription", type: "action", position: { x: 200, y: 0 }, connected: ["w1"] },
        { id: "w3", label: "Extract Key Points", type: "action", position: { x: 400, y: 0 }, connected: ["w2"] },
        { id: "w4", label: "Update Contact Timeline", type: "output", position: { x: 600, y: 0 }, connected: ["w3"] },
      ],
    },
    {
      workspace_id: workspaceId,
      name: "Pipeline Optimizer", type: "pipeline_optimizer", status: "active",
      description: "Monitors deal velocity and predicts stalls. Recommends next best actions using reinforcement learning from historical pipeline data.",
      model: "RL Policy + LightGBM", accuracy: 89.3, tasks_today: 201, last_run: "15 min ago",
      metrics: [{ label: "Stalls Detected", value: "7", delta: "+2" }, { label: "Actions Recommended", value: "201" }, { label: "Win Rate Lift", value: "+14.2%" }],
      workflow: [
        { id: "w1", label: "Daily Pipeline Scan", type: "trigger", position: { x: 0, y: 0 } },
        { id: "w2", label: "Velocity Analysis", type: "action", position: { x: 200, y: 0 }, connected: ["w1"] },
        { id: "w3", label: "Stall Prediction", type: "action", position: { x: 400, y: 0 }, connected: ["w2"] },
        { id: "w4", label: "Generate Action Plan", type: "output", position: { x: 600, y: 0 }, connected: ["w3"] },
      ],
    },
    {
      workspace_id: workspaceId,
      name: "Sentiment Analyzer", type: "sentiment_analyzer", status: "active",
      description: "Analyzes email threads, call transcripts, and support tickets to gauge contact sentiment. Flags at-risk accounts before churn occurs.",
      model: "RoBERTa fine-tuned + GPT-4o-mini", accuracy: 93.8, tasks_today: 388, last_run: "5 min ago",
      metrics: [{ label: "Signals Analyzed", value: "388", delta: "+54" }, { label: "At-Risk Flagged", value: "3", delta: "+1" }, { label: "Avg Sentiment Score", value: "0.74" }],
      workflow: [
        { id: "w1", label: "New Email / Ticket", type: "trigger", position: { x: 0, y: 0 } },
        { id: "w2", label: "RoBERTa Inference", type: "action", position: { x: 200, y: 0 }, connected: ["w1"] },
        { id: "w3", label: "Sentiment < 0.4?", type: "condition", position: { x: 400, y: 0 }, connected: ["w2"] },
        { id: "w4", label: "Flag At-Risk + Alert", type: "output", position: { x: 600, y: -60 }, connected: ["w3"] },
        { id: "w5", label: "Update Sentiment Log", type: "output", position: { x: 600, y: 60 }, connected: ["w3"] },
      ],
    },
  ];

  console.log("  Inserting agents...");
  const { error: aErr } = await supabase.from("agents").insert(agents);
  if (aErr) { console.error("  Agents:", aErr.message); process.exit(1); }
  console.log(`  ${agents.length} agents`);

  // ── 6. Activity Events ─────────────────────────────────────────────────────
  const activity = [
    { workspace_id: workspaceId, type: "contact_scored", agent_name: "Lead Scorer", description: "Re-scored Dmitri Volkov → 95 (was 88)", meta: "Upsell signals detected", severity: "success" },
    { workspace_id: workspaceId, type: "tag_applied", agent_name: "Semantic Sorter", description: "Tagged 12 new contacts with 'Enterprise Buyer'", meta: "Avg confidence: 93.4%", severity: "info" },
    { workspace_id: workspaceId, type: "email_sent", agent_name: "Email Composer", description: "Drafted follow-up for Marcus Webb", meta: "Proposal stage · Human review pending", severity: "info" },
    { workspace_id: workspaceId, type: "deal_moved", agent_name: "Pipeline Optimizer", description: "NexLabs Enterprise Suite → Negotiation", meta: "Win probability: 87%", severity: "success" },
    { workspace_id: workspaceId, type: "agent_run", agent_name: "Sentiment Analyzer", description: "Flagged Lena Kovacs as at-risk", meta: "Sentiment score dropped to 0.31", severity: "warning" },
    { workspace_id: workspaceId, type: "call_summarized", agent_name: "Call Summarizer", description: "Processed 38-min call with James Okafor", meta: "3 action items extracted", severity: "info" },
    { workspace_id: workspaceId, type: "model_updated", agent_name: "Lead Scorer", description: "XGBoost model retrained on 1,204 new samples", meta: "F1: 0.947 → 0.951 (+0.4%)", severity: "success" },
  ];

  console.log("  Inserting activity events...");
  const { error: evErr } = await supabase.from("activity_events").insert(activity);
  if (evErr) { console.error("  Activity:", evErr.message); process.exit(1); }
  console.log(`  ${activity.length} events`);

  console.log(`\nSeed complete! Workspace ID: ${workspaceId}`);
  console.log("Next: create a Supabase auth user, then insert a users row with the workspace_id above.");
}

seed().catch(console.error);
