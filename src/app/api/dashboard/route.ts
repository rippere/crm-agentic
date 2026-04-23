import { NextResponse } from "next/server";
import { getSupabase } from "@/lib/supabase";

// GET /api/dashboard
// Aggregates KPIs from contacts, deals, and agents in parallel
export async function GET() {
  const [contactsRes, dealsRes, agentsRes] = await Promise.all([
    getSupabase().from("contacts").select("revenue, status"),
    getSupabase().from("deals").select("value, stage, ml_win_probability"),
    getSupabase().from("agents").select("status, accuracy, tasks_today"),
  ]);

  if (contactsRes.error || dealsRes.error || agentsRes.error) {
    return NextResponse.json(
      { error: "Failed to fetch dashboard data" },
      { status: 500 }
    );
  }

  const contacts = contactsRes.data;
  const deals = dealsRes.data;
  const agents = agentsRes.data;

  // Total revenue (customers only)
  const totalRevenue = contacts
    .filter((c) => c.status === "customer")
    .reduce((sum, c) => sum + (c.revenue ?? 0), 0);

  // Active deals (not closed)
  const activeDeals = deals.filter(
    (d) => d.stage !== "closed_won" && d.stage !== "closed_lost"
  ).length;

  // Avg ML accuracy across all agents
  const avgAccuracy =
    agents.length > 0
      ? agents.reduce((sum, a) => sum + (a.accuracy ?? 0), 0) / agents.length
      : 0;

  // Active / total agents
  const activeAgents = agents.filter((a) => a.status === "active" || a.status === "processing").length;
  const totalAgents = agents.length;

  // Total tasks today
  const tasksToday = agents.reduce((sum, a) => sum + (a.tasks_today ?? 0), 0);

  return NextResponse.json({
    totalRevenue,
    activeDeals,
    totalDeals: deals.length,
    avgAccuracy: parseFloat(avgAccuracy.toFixed(1)),
    activeAgents,
    totalAgents,
    tasksToday,
    closedWonValue: deals
      .filter((d) => d.stage === "closed_won")
      .reduce((sum, d) => sum + (d.value ?? 0), 0),
    avgWinProbability: activeDeals > 0
      ? parseFloat(
          (deals
            .filter((d) => d.stage !== "closed_won" && d.stage !== "closed_lost")
            .reduce((sum, d, _, arr) => sum + d.ml_win_probability / arr.length, 0)
          ).toFixed(0)
        )
      : 0,
  });
}
