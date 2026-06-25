import { redirect } from "next/navigation";
import { cookies } from "next/headers";
import { createServerClient } from "@/lib/supabase";
import ClientShell from "@/components/layout/ClientShell";

const DEMO_MODE = process.env.NEXT_PUBLIC_DEMO_MODE === "true";

// Server-only allowlist for the owner-private /life page. Workspace ids never
// reach the client bundle — only the resolved boolean is threaded down.
function isLifeEnabled(workspaceId: string | undefined): boolean {
  return (process.env.LIFE_WORKSPACE_IDS ?? "")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean)
    .includes(workspaceId ?? "");
}

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  // In demo mode, bypass all auth checks. The demo workspace never matches the
  // allowlist, so Life stays hidden — intentional.
  if (DEMO_MODE) {
    return (
      <div className="flex h-screen overflow-hidden bg-zinc-950">
        <ClientShell mode="both" lifeEnabled={false}>{children}</ClientShell>
      </div>
    );
  }

  const cookieStore = await cookies();
  const supabase = createServerClient(cookieStore);

  const { data: { user } } = await supabase.auth.getUser();

  if (!user) {
    redirect("/login");
  }

  const workspaceId = (user.app_metadata?.workspace_id ?? user.user_metadata?.workspace_id) as string | undefined;

  if (!workspaceId) {
    redirect("/onboarding");
  }

  const { data: workspace } = await supabase
    .from("workspaces")
    .select("mode")
    .eq("id", workspaceId)
    .single();

  const mode = (workspace?.mode ?? "sales") as "sales" | "pm" | "both";
  const userEmail = user.email ?? "";
  const userName = (user.user_metadata?.full_name as string | undefined)
    ?? (user.user_metadata?.name as string | undefined)
    ?? userEmail.split("@")[0]
    ?? "User";
  const lifeEnabled = isLifeEnabled(workspaceId);

  return (
    <div className="flex h-screen overflow-hidden bg-zinc-950">
      <ClientShell mode={mode} userEmail={userEmail} userName={userName} lifeEnabled={lifeEnabled}>{children}</ClientShell>
    </div>
  );
}
