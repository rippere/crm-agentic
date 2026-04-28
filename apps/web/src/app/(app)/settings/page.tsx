"use client";

import { useState, useEffect } from "react";
import Header from "@/components/layout/Header";
import Card from "@/components/ui/Card";
import Button from "@/components/ui/Button";
import Badge from "@/components/ui/Badge";
import { createBrowserClient } from "@/lib/supabase";
import { cn } from "@/lib/utils";
import {
  Settings, Layers, TrendingUp, CheckSquare,
  Plug, User, LogOut, Save, AlertTriangle,
} from "lucide-react";
import type { WorkspaceMode } from "@/lib/types";
import { useRouter } from "next/navigation";

const MODE_OPTIONS: { value: WorkspaceMode; label: string; description: string; icon: React.ElementType }[] = [
  { value: "sales", label: "Sales",              description: "CRM, pipeline, deal tracking",     icon: TrendingUp  },
  { value: "pm",    label: "Project Management", description: "Task tracking, inbox triage",       icon: CheckSquare },
  { value: "both",  label: "Both",               description: "Full platform — sales + PM",        icon: Layers      },
];

interface Toast { id: number; message: string; type: "success" | "error" }

export default function SettingsPage() {
  const router = useRouter();
  const [workspaceName, setWorkspaceName] = useState("");
  const [mode, setMode] = useState<WorkspaceMode>("sales");
  const [workspaceId, setWorkspaceId] = useState<string | null>(null);
  const [userEmail, setUserEmail] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [toasts, setToasts] = useState<Toast[]>([]);

  const addToast = (message: string, type: Toast["type"]) => {
    const id = Date.now();
    setToasts((prev) => [...prev, { id, message, type }]);
    setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), 4000);
  };

  useEffect(() => {
    const supabase = createBrowserClient();
    supabase.auth.getUser().then(async ({ data: { user } }) => {
      if (!user) return;
      setUserEmail(user.email ?? null);
      const wsId = user.user_metadata?.workspace_id as string | undefined;
      if (!wsId) return;
      setWorkspaceId(wsId);

      const { data: ws } = await supabase
        .from("workspaces")
        .select("name, mode")
        .eq("id", wsId)
        .single();
      if (ws) {
        setWorkspaceName(ws.name ?? "");
        setMode((ws.mode as WorkspaceMode) ?? "sales");
      }
    });
  }, []);

  const handleSave = async () => {
    if (!workspaceId || !workspaceName.trim()) return;
    setSaving(true);
    const supabase = createBrowserClient();
    const { error } = await supabase
      .from("workspaces")
      .update({ name: workspaceName.trim(), mode })
      .eq("id", workspaceId);
    setSaving(false);
    if (error) {
      addToast("Failed to save: " + error.message, "error");
    } else {
      addToast("Workspace settings saved.", "success");
    }
  };

  const handleSignOut = async () => {
    const supabase = createBrowserClient();
    await supabase.auth.signOut();
    router.push("/login");
  };

  return (
    <div className="flex flex-col gap-6 p-6 max-w-2xl">
      {/* Toast */}
      <div className="fixed top-4 right-4 z-50 flex flex-col gap-2 pointer-events-none">
        {toasts.map((t) => (
          <div
            key={t.id}
            className={`rounded-xl border px-4 py-3 text-sm font-medium shadow-xl pointer-events-auto ${
              t.type === "success"
                ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-300"
                : "border-rose-500/40 bg-rose-500/10 text-rose-300"
            }`}
          >
            {t.message}
          </div>
        ))}
      </div>

      <Header title="Settings" subtitle="Workspace configuration and preferences" />

      {/* Workspace */}
      <Card>
        <div className="flex items-center gap-2 mb-5">
          <Settings className="h-4 w-4 text-indigo-400" />
          <p className="text-sm font-semibold text-zinc-100">Workspace</p>
        </div>

        <div className="space-y-5">
          <div>
            <label className="block text-xs font-medium text-zinc-400 mb-1.5">
              Workspace name
            </label>
            <input
              type="text"
              value={workspaceName}
              onChange={(e) => setWorkspaceName(e.target.value)}
              placeholder="Acme Corp"
              className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3.5 py-2.5 text-sm text-zinc-100 placeholder-zinc-600 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 transition"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-zinc-400 mb-2.5">
              Workspace mode
            </label>
            <div className="grid grid-cols-3 gap-3">
              {MODE_OPTIONS.map(({ value, label, description, icon: Icon }) => (
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

          <Button variant="primary" onClick={handleSave} disabled={saving || !workspaceName.trim()}>
            <Save className="h-3.5 w-3.5" />
            {saving ? "Saving…" : "Save changes"}
          </Button>
        </div>
      </Card>

      {/* Integrations */}
      <Card>
        <div className="flex items-center gap-2 mb-4">
          <Plug className="h-4 w-4 text-indigo-400" />
          <p className="text-sm font-semibold text-zinc-100">Integrations</p>
        </div>
        <p className="text-xs text-zinc-500 mb-4">
          Connect Gmail and Slack to enable automatic message ingestion and contact enrichment.
        </p>
        <Button variant="secondary" onClick={() => router.push("/connectors")}>
          <Plug className="h-3.5 w-3.5" />
          Manage Connectors
        </Button>
      </Card>

      {/* Account */}
      <Card>
        <div className="flex items-center gap-2 mb-4">
          <User className="h-4 w-4 text-indigo-400" />
          <p className="text-sm font-semibold text-zinc-100">Account</p>
        </div>
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm text-zinc-200">{userEmail ?? "—"}</p>
            <Badge variant="indigo" size="sm" className="mt-1.5">Admin</Badge>
          </div>
          <Button variant="secondary" size="sm" onClick={handleSignOut}>
            <LogOut className="h-3.5 w-3.5" />
            Sign out
          </Button>
        </div>
      </Card>

      {/* Danger zone */}
      <Card className="border-rose-500/15">
        <div className="flex items-center gap-2 mb-3">
          <AlertTriangle className="h-4 w-4 text-rose-400" />
          <p className="text-sm font-semibold text-rose-400">Danger Zone</p>
        </div>
        <p className="text-xs text-zinc-500 mb-4">
          Deleting your workspace permanently removes all contacts, deals, messages, and agents.
          This action cannot be undone.
        </p>
        <Button variant="danger" size="sm" disabled>
          Delete Workspace
        </Button>
        <p className="text-[10px] text-zinc-600 mt-2 font-mono">Contact support to delete your workspace.</p>
      </Card>
    </div>
  );
}
