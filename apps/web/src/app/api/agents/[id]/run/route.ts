import { NextRequest, NextResponse } from "next/server";
import { getSupabase } from "@/lib/supabase";

// POST /api/agents/[id]/run
// Marks the agent as processing, logs an activity event.
// Your real ML pipeline would call this endpoint to start the agent,
// then call PUT /api/agents/[id] to update status/metrics when done.
export async function POST(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;

  // Fetch the agent
  const { data: agent, error: fetchError } = await getSupabase()
    .from("agents")
    .select("id, name, status")
    .eq("id", id)
    .single();

  if (fetchError || !agent) {
    return NextResponse.json({ error: "Agent not found" }, { status: 404 });
  }

  if (agent.status === "processing") {
    return NextResponse.json({ error: "Agent is already processing" }, { status: 409 });
  }

  // Set agent to processing
  await getSupabase()
    .from("agents")
    .update({ status: "processing", last_run: "Just now" })
    .eq("id", id);

  // Log activity event
  await getSupabase().from("activity_events").insert({
    type: "agent_run",
    agent_name: agent.name,
    description: `${agent.name} manually triggered`,
    meta: "Manual run · processing",
    severity: "info",
  });

  return NextResponse.json({
    success: true,
    message: `${agent.name} is now processing`,
  });
}
