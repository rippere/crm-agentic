import { NextRequest, NextResponse } from "next/server";
import { z } from "zod";
import { getSupabase } from "@/lib/supabase";

const UpdateContactSchema = z.object({
  name: z.string().min(1).optional(),
  email: z.string().email().optional(),
  company: z.string().optional(),
  role: z.string().optional(),
  status: z.enum(["lead", "prospect", "customer", "churned"]).optional(),
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
  last_activity: z.string().optional(),
  revenue: z.number().optional(),
  deal_count: z.number().optional(),
});

// GET /api/contacts/[id]
export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const { data, error } = await getSupabase()
    .from("contacts")
    .select("*")
    .eq("id", id)
    .single();

  if (error) {
    return NextResponse.json({ error: error.message }, { status: 404 });
  }

  return NextResponse.json(data);
}

// PUT /api/contacts/[id]
export async function PUT(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const body = await req.json();
  const parsed = UpdateContactSchema.safeParse(body);

  if (!parsed.success) {
    return NextResponse.json(
      { error: "Validation failed", issues: parsed.error.issues },
      { status: 400 }
    );
  }

  const { data, error } = await getSupabase()
    .from("contacts")
    .update(parsed.data as any)
    .eq("id", id)
    .select()
    .single();

  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }

  return NextResponse.json(data);
}

// DELETE /api/contacts/[id]
export async function DELETE(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const { error } = await getSupabase().from("contacts").delete().eq("id", id);

  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }

  return NextResponse.json({ success: true });
}
