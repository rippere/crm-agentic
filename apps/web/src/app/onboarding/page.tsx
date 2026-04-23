"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { createBrowserClient } from "@/lib/supabase";
import { Zap, TrendingUp, CheckSquare, Layers } from "lucide-react";
import type { WorkspaceMode } from "@/lib/types";
import { cn } from "@/lib/utils";

const modeOptions: { value: WorkspaceMode; label: string; description: string; icon: React.ElementType }[] = [
  {
    value: "sales",
    label: "Sales",
    description: "CRM, pipeline management, contact intelligence, and deal tracking.",
    icon: TrendingUp,
  },
  {
    value: "pm",
    label: "Project Management",
    description: "Task tracking, inbox triage, and team collaboration.",
    icon: CheckSquare,
  },
  {
    value: "both",
    label: "Both",
    description: "Full platform — sales + PM features in one unified workspace.",
    icon: Layers,
  },
];

export default function OnboardingPage() {
  const router = useRouter();
  const [workspaceName, setWorkspaceName] = useState("");
  const [mode, setMode] = useState<WorkspaceMode>("sales");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const slug = workspaceName.toLowerCase().replace(/\s+/g, "-").replace(/[^a-z0-9-]/g, "");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!workspaceName.trim()) return;
    setLoading(true);
    setError(null);

    const supabase = createBrowserClient();

    const { data: { user }, error: userError } = await supabase.auth.getUser();
    if (userError || !user) {
      setError("Not authenticated. Please sign in first.");
      setLoading(false);
      return;
    }

    // Create workspace
    const { data: workspace, error: wsError } = await supabase
      .from("workspaces")
      .insert({ name: workspaceName.trim(), slug, mode })
      .select()
      .single();

    if (wsError || !workspace) {
      setError(wsError?.message ?? "Failed to create workspace.");
      setLoading(false);
      return;
    }

    // Create user row
    const { error: userRowError } = await supabase.from("users").insert({
      supabase_uid: user.id,
      workspace_id: workspace.id,
      email: user.email ?? "",
      role: "admin",
    });

    if (userRowError) {
      setError(userRowError.message);
      setLoading(false);
      return;
    }

    // Store workspace_id in user metadata
    await supabase.auth.updateUser({ data: { workspace_id: workspace.id } });

    router.push("/dashboard");
  };

  return (
    <div className="min-h-screen bg-[#09090B] flex items-center justify-center px-4">
      <div className="w-full max-w-lg">
        {/* Logo */}
        <div className="flex items-center gap-3 mb-10 justify-center">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-indigo-600">
            <Zap className="h-5 w-5 text-white" />
          </div>
          <div>
            <p className="text-base font-semibold text-zinc-100 leading-none">NovaCRM</p>
            <p className="text-[10px] text-zinc-500 mt-0.5 font-mono">Agentic Intelligence</p>
          </div>
        </div>

        {/* Card */}
        <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-8">
          <h1 className="text-xl font-semibold text-zinc-100 mb-1">Set up your workspace</h1>
          <p className="text-sm text-zinc-500 mb-7">
            Choose a name and mode. You can change these later in settings.
          </p>

          {error && (
            <div className="mb-5 rounded-lg bg-rose-500/10 border border-rose-500/20 px-4 py-3 text-sm text-rose-400">
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-6">
            {/* Workspace name */}
            <div>
              <label className="block text-xs font-medium text-zinc-400 mb-1.5">
                Workspace name
              </label>
              <input
                type="text"
                value={workspaceName}
                onChange={(e) => setWorkspaceName(e.target.value)}
                placeholder="Acme Corp"
                required
                className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3.5 py-2.5 text-sm text-zinc-100 placeholder-zinc-600 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 transition"
              />
              {slug && (
                <p className="mt-1.5 text-[11px] text-zinc-600 font-mono">
                  slug: <span className="text-zinc-500">{slug}</span>
                </p>
              )}
            </div>

            {/* Mode selector */}
            <div>
              <label className="block text-xs font-medium text-zinc-400 mb-2.5">
                Workspace mode
              </label>
              <div className="grid grid-cols-3 gap-3">
                {modeOptions.map(({ value, label, description, icon: Icon }) => (
                  <button
                    key={value}
                    type="button"
                    onClick={() => setMode(value)}
                    className={cn(
                      "flex flex-col items-start gap-2 rounded-lg border p-4 text-left transition-all",
                      mode === value
                        ? "border-indigo-500 bg-indigo-600/10 text-indigo-300"
                        : "border-zinc-700 bg-zinc-800 text-zinc-400 hover:border-zinc-600 hover:text-zinc-200"
                    )}
                  >
                    <Icon className={cn("h-5 w-5", mode === value ? "text-indigo-400" : "text-zinc-500")} />
                    <div>
                      <p className="text-xs font-semibold leading-none mb-1">{label}</p>
                      <p className="text-[10px] leading-snug opacity-70">{description}</p>
                    </div>
                  </button>
                ))}
              </div>
            </div>

            <button
              type="submit"
              disabled={loading || !workspaceName.trim()}
              className="w-full rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed transition"
            >
              {loading ? "Creating workspace..." : "Create workspace"}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
