import { redirect } from "next/navigation";
import { cookies } from "next/headers";
import { createServerClient } from "@/lib/supabase";
import Sidebar from "@/components/layout/Sidebar";

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  const cookieStore = await cookies();
  const supabase = createServerClient(cookieStore);

  const { data: { session } } = await supabase.auth.getSession();

  if (!session) {
    redirect("/login");
  }

  const workspaceId = session.user.user_metadata?.workspace_id as string | undefined;

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
