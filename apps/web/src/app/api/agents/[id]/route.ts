import { NextRequest, NextResponse } from "next/server";
import { z } from "zod";
import { getSupabase } from "@/lib/supabase";

const UpdateAgentSchema = z.object({
  status: z.enum(["active", "processing", "idle", "error"]).optional(),
  accuracy: z.number().min(0).max(100).optional(),
  tasks_today: z.number().optional(),
  last_run: z.string().optional(),
  metrics: z.array(z.object({
    label: z.string(),
    value: z.string(),
    delta: z.string().optional(),
  })).optional(),
});

// GET /api/agents/[id]
export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const { data, error } = await getSupabase()
    .from("agents")
    .select("*")
    .eq("id", id)
    .single();

  if (error) {
    return NextResponse.json({ error: error.message }, { status: 404 });
  }

  return NextResponse.json(data);
}

// PUT /api/agents/[id]  — update status, metrics, accuracy
export async function PUT(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const body = await req.json();
  const parsed = UpdateAgentSchema.safeParse(body);

  if (!parsed.success) {
    return NextResponse.json(
      { error: "Validation failed", issues: parsed.error.issues },
      { status: 400 }
    );
  }

  const { data, error } = await getSupabase()
    .from("agents")
    .update(parsed.data as any)
    .eq("id", id)
    .select()
    .single();

  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }

  return NextResponse.json(data);
}
