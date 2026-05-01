import { redirect } from "next/navigation";
import { cookies } from "next/headers";
import { createServerClient } from "@/lib/supabase";
import ClientShell from "@/components/layout/ClientShell";

const DEMO_MODE = process.env.NEXT_PUBLIC_DEMO_MODE === "true";

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  // In demo mode, bypass all auth checks
  if (DEMO_MODE) {
    return (
      <div className="flex h-screen overflow-hidden bg-zinc-950">
        <ClientShell mode="both">{children}</ClientShell>
      </div>
    );
  }

  const cookieStore = await cookies();
  const supabase = createServerClient(cookieStore);

  const { data: { user } } = await supabase.auth.getUser();

  if (!user) {
    redirect("/login");
  }

  const workspaceId = user.user_metadata?.workspace_id as string | undefined;

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

  return (
    <div className="flex h-screen overflow-hidden bg-zinc-950">
      <ClientShell mode={mode} userEmail={userEmail} userName={userName}>{children}</ClientShell>
    </div>
  );
}
