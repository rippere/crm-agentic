import { NextRequest, NextResponse } from "next/server";
import { z } from "zod";
import { getSupabase } from "@/lib/supabase";
import type { DealRow } from "@/lib/supabase";

const CreateDealSchema = z.object({
  title: z.string().min(1),
  company: z.string().default(""),
  contact_name: z.string().default(""),
  contact_id: z.string().uuid().nullable().optional(),
  value: z.number().min(0).default(0),
  stage: z.enum(["discovery", "qualified", "proposal", "negotiation", "closed_won", "closed_lost"]).default("discovery"),
  ml_win_probability: z.number().min(0).max(100).default(50),
  expected_close: z.string().default(""),
  assigned_agent: z.string().default(""),
  notes: z.string().default(""),
});

// GET /api/deals
export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const stage = searchParams.get("stage");
  const contact_id = searchParams.get("contact_id");

  let query = getSupabase()
    .from("deals")
    .select("*")
    .order("created_at", { ascending: false });

  if (stage && stage !== "all") query = query.eq("stage", stage as DealRow["stage"]);
  if (contact_id) query = query.eq("contact_id", contact_id);

  const { data, error } = await query;

  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }

  return NextResponse.json(data);
}

// POST /api/deals
export async function POST(req: NextRequest) {
  const body = await req.json();
  const parsed = CreateDealSchema.safeParse(body);

  if (!parsed.success) {
    return NextResponse.json(
      { error: "Validation failed", issues: parsed.error.issues },
      { status: 400 }
    );
  }

  const { data, error } = await getSupabase()
    .from("deals")
    .insert(parsed.data as any)
    .select()
    .single();

  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }

  return NextResponse.json(data, { status: 201 });
}
