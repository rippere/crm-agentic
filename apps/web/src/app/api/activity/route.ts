import { NextRequest, NextResponse } from "next/server";
import { z } from "zod";
import { getSupabase, type Database } from "@/lib/supabase";

type ActivityInsert = Database["public"]["Tables"]["activity_events"]["Insert"];

const CreateEventSchema = z.object({
  type: z.string().min(1),
  agent_name: z.string().min(1),
  description: z.string().min(1),
  meta: z.string().default(""),
  severity: z.enum(["info", "success", "warning"]).default("info"),
});

// GET /api/activity
export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const limit = parseInt(searchParams.get("limit") ?? "50");

  const { data, error } = await getSupabase()
    .from("activity_events")
    .select("*")
    .order("created_at", { ascending: false })
    .limit(limit);

  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }

  return NextResponse.json(data);
}

// POST /api/activity  — called by agents to log events
export async function POST(req: NextRequest) {
  const body = await req.json();
  const parsed = CreateEventSchema.safeParse(body);

  if (!parsed.success) {
    return NextResponse.json(
      { error: "Validation failed", issues: parsed.error.issues },
      { status: 400 }
    );
  }

  const { data, error } = await getSupabase()
    .from("activity_events")
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    .insert(parsed.data as any)
    .select()
    .single();

  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }

  return NextResponse.json(data, { status: 201 });
}
