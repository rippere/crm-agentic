/**
 * Seed a demo login user — creates a Supabase auth user (email+password,
 * pre-confirmed) and links it to the demo workspace via a users row.
 * Run from apps/web:  npx tsx scripts/seed-user.ts
 *
 * Requires .env.local with SUPABASE_SERVICE_ROLE_KEY (admin API).
 * Idempotent: re-running reuses the workspace, and resets the demo user's
 * password if it already exists.
 */

import { createClient } from "@supabase/supabase-js";
import * as dotenv from "dotenv";
import * as path from "path";

dotenv.config({ path: path.resolve(process.cwd(), ".env.local") });

const DEMO_EMAIL = process.env.DEMO_USER_EMAIL ?? "demo@novacrm.io";
const DEMO_PASSWORD = process.env.DEMO_USER_PASSWORD ?? "BetsonDemo2026!";

const url = process.env.NEXT_PUBLIC_SUPABASE_URL!;
const serviceKey = process.env.SUPABASE_SERVICE_ROLE_KEY!;
if (!url || !serviceKey) {
  console.error("Missing NEXT_PUBLIC_SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY in .env.local");
  process.exit(1);
}

const admin = createClient(url, serviceKey, {
  auth: { autoRefreshToken: false, persistSession: false },
});

async function findAuthUserByEmail(email: string): Promise<string | null> {
  // Admin listUsers is paginated; scan until found or exhausted.
  for (let page = 1; page <= 20; page++) {
    const { data, error } = await admin.auth.admin.listUsers({ page, perPage: 200 });
    if (error) throw error;
    const hit = data.users.find((u) => u.email?.toLowerCase() === email.toLowerCase());
    if (hit) return hit.id;
    if (data.users.length < 200) break;
  }
  return null;
}

async function main() {
  // 1. Demo workspace (reuse the one seed.ts creates).
  let workspaceId: string;
  const { data: existingWs } = await admin
    .from("workspaces")
    .select("id")
    .eq("slug", "demo")
    .single();
  if (existingWs) {
    workspaceId = existingWs.id;
    console.log(`Reusing demo workspace: ${workspaceId}`);
  } else {
    const { data: ws, error } = await admin
      .from("workspaces")
      .insert({ name: "Demo Workspace", slug: "demo", mode: "both" })
      .select()
      .single();
    if (error || !ws) { console.error("Workspace:", error?.message); process.exit(1); }
    workspaceId = ws.id;
    console.log(`Created demo workspace: ${workspaceId}`);
  }

  // 2. Supabase auth user (create pre-confirmed, or reset password if present).
  let uid = await findAuthUserByEmail(DEMO_EMAIL);
  if (uid) {
    const { error } = await admin.auth.admin.updateUserById(uid, {
      password: DEMO_PASSWORD,
      email_confirm: true,
    });
    if (error) { console.error("Update auth user:", error.message); process.exit(1); }
    console.log(`Reset password for existing auth user: ${uid}`);
  } else {
    const { data, error } = await admin.auth.admin.createUser({
      email: DEMO_EMAIL,
      password: DEMO_PASSWORD,
      email_confirm: true,
    });
    if (error || !data.user) { console.error("Create auth user:", error?.message); process.exit(1); }
    uid = data.user.id;
    console.log(`Created auth user: ${uid}`);
  }

  // 3. Link users row → workspace (upsert on supabase_uid).
  const { error: uErr } = await admin
    .from("users")
    .upsert(
      { supabase_uid: uid, workspace_id: workspaceId, email: DEMO_EMAIL, role: "admin" },
      { onConflict: "supabase_uid" },
    );
  if (uErr) { console.error("Link users row:", uErr.message); process.exit(1); }

  console.log("\nDemo login ready:");
  console.log(`  Email:    ${DEMO_EMAIL}`);
  console.log(`  Password: ${DEMO_PASSWORD}`);
  console.log(`  Workspace: ${workspaceId} (admin)`);
}

main().catch((e) => { console.error(e); process.exit(1); });
