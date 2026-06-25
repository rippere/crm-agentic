import { redirect } from "next/navigation";
import { cookies } from "next/headers";
import { createServerClient } from "@/lib/supabase";

const DEMO_MODE = process.env.NEXT_PUBLIC_DEMO_MODE === "true";

// Server-side allowlist for the owner-private /life page. The (app) layout hides
// the nav item; this guards direct-URL access. Same allowlist, same source.
function isLifeEnabled(workspaceId: string | undefined): boolean {
  return (process.env.LIFE_WORKSPACE_IDS ?? "")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean)
    .includes(workspaceId ?? "");
}

export default async function LifeLayout({ children }: { children: React.ReactNode }) {
  // Demo's fake workspace never matches the allowlist — Life is off in demo.
  if (DEMO_MODE) redirect("/dashboard");

  const cookieStore = await cookies();
  const supabase = createServerClient(cookieStore);
  const { data: { user } } = await supabase.auth.getUser();
  const workspaceId = (user?.app_metadata?.workspace_id ?? user?.user_metadata?.workspace_id) as string | undefined;

  if (!isLifeEnabled(workspaceId)) redirect("/dashboard");

  return <>{children}</>;
}
