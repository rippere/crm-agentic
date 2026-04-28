import { redirect } from "next/navigation";
import { cookies } from "next/headers";
import { createServerClient } from "@/lib/supabase";
import Sidebar from "@/components/layout/Sidebar";

const DEMO_MODE = process.env.NEXT_PUBLIC_DEMO_MODE === "true";

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  // In demo mode, bypass all auth checks and render with "both" sidebar
  if (DEMO_MODE) {
    return (
      <div className="flex h-screen overflow-hidden bg-zinc-950">
        <Sidebar mode="both" />
        <main className="ml-60 flex-1 overflow-y-auto min-h-screen">
          {children}
        </main>
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

  // Fetch workspace to get mode for sidebar gating
  const { data: workspace } = await supabase
    .from("workspaces")
    .select("mode")
    .eq("id", workspaceId)
    .single();

  const mode = (workspace?.mode ?? "sales") as "sales" | "pm" | "both";

  return (
    <div className="flex h-screen overflow-hidden bg-zinc-950">
      <Sidebar mode={mode} />
      <main className="ml-60 flex-1 overflow-y-auto min-h-screen">
        {children}
      </main>
    </div>
  );
}
