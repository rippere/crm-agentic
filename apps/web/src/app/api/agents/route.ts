import { NextResponse } from "next/server";
import { getSupabase } from "@/lib/supabase";

// GET /api/agents
export async function GET() {
  const { data, error } = await getSupabase()
    .from("agents")
    .select("*")
    .order("name", { ascending: true });

  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }

  return NextResponse.json(data);
}
