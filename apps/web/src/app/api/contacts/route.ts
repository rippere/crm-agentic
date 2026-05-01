import { NextRequest, NextResponse } from "next/server";
import { z } from "zod";
import { getSupabase } from "@/lib/supabase";
import type { ContactRow } from "@/lib/supabase";

const CreateContactSchema = z.object({
  name: z.string().min(1),
  email: z.string().email(),
  company: z.string().min(1),
  role: z.string().default(""),
  avatar: z.string().default(""),
  status: z.enum(["lead", "prospect", "customer", "churned"]).default("lead"),
  ml_score: z.object({
    value: z.number().min(0).max(100),
    label: z.enum(["hot", "warm", "cold"]),
    trend: z.enum(["up", "down", "stable"]),
    signals: z.array(z.string()),
  }).optional(),
  semantic_tags: z.array(z.object({
    label: z.string(),
    confidence: z.number().min(0).max(1),
    color: z.enum(["indigo", "emerald", "amber", "rose"]),
  })).optional(),
  revenue: z.number().default(0),
});

// GET /api/contacts
export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const status = searchParams.get("status");
  const search = searchParams.get("search");
  const score = searchParams.get("score"); // hot | warm | cold

  let query = getSupabase()
    .from("contacts")
    .select("*")
    .order("created_at", { ascending: false });

  if (status && status !== "all") {
    query = query.eq("status", status as ContactRow["status"]);
  }
  if (search) {
    query = query.or(
      `name.ilike.%${search}%,email.ilike.%${search}%,company.ilike.%${search}%`
    );
  }

  const { data, error } = await query;

  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }

  // Filter by ML score label (done in JS since it's JSONB)
  const filtered =
    score && score !== "all"
      ? data.filter((c) => c.ml_score?.label === score)
      : data;

  return NextResponse.json(filtered);
}

// POST /api/contacts
export async function POST(req: NextRequest) {
  const body = await req.json();
  const parsed = CreateContactSchema.safeParse(body);

  if (!parsed.success) {
    return NextResponse.json(
      { error: "Validation failed", issues: parsed.error.issues },
      { status: 400 }
    );
  }

  const { data, error } = await getSupabase()
    .from("contacts")
    .insert(parsed.data as any)
    .select()
    .single();

  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }

  return NextResponse.json(data, { status: 201 });
}
