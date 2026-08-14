"use client";

import { useState, useEffect } from "react";
import Header from "@/components/layout/Header";
import Card from "@/components/ui/Card";
import Button from "@/components/ui/Button";
import Badge from "@/components/ui/Badge";
import { createBrowserClient } from "@/lib/supabase";
import { apiClient } from "@/lib/api-client";
import { cn } from "@/lib/utils";
import {
  Settings, Layers, TrendingUp, CheckSquare,
  Plug, User, LogOut, Save, AlertTriangle, Users, Mail, Webhook, ChevronRight,
  Sparkles, RefreshCw, ChevronDown, CheckCircle2,
} from "lucide-react";
import type { WorkspaceMode } from "@/lib/types";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useRole } from "@/hooks/useRole";
import ConfirmDialog from "@/components/ui/ConfirmDialog";

const MODE_OPTIONS: { value: WorkspaceMode; label: string; description: string; icon: React.ElementType }[] = [
  { value: "sales", label: "Sales",              description: "CRM, pipeline, deal tracking",     icon: TrendingUp  },
  { value: "pm",    label: "Project Management", description: "Task tracking, inbox triage",       icon: CheckSquare },
  { value: "both",  label: "Both",               description: "Full platform — sales + PM",        icon: Layers      },
];

interface Toast { id: number; message: string; type: "success" | "error" }

export default function SettingsPage() {
  const router = useRouter();
  const { isAdmin, role } = useRole();
  const [workspaceName, setWorkspaceName] = useState("");
  const [mode, setMode] = useState<WorkspaceMode>("sales");
  const [workspaceId, setWorkspaceId] = useState<string | null>(null);
  const [userEmail, setUserEmail] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviting, setInviting] = useState(false);
  const [token, setToken] = useState<string | null>(null);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);

  const [digest, setDigest] = useState<{
    health_rating: 'excellent' | 'good' | 'needs_attention' | 'critical'
    summary: string
    highlights: string[]
    warnings: string[]
    recommended_actions: string[]
    metrics: {
      total_contacts: number
      going_dark_count: number
      open_deal_count: number
      total_pipeline: number
      at_risk_deals: number
      closed_won_count: number
      closed_won_value: number
      open_task_count: number
      overdue_task_count: number
      agent_run_count: number
    }
    generated_at: string
  } | null>(null);
  const [digestLoading, setDigestLoading] = useState(false);
  const [digestExpanded, setDigestExpanded] = useState(true);

  const addToast = (message: string, type: Toast["type"]) => {
    const id = Date.now();
    setToasts((prev) => [...prev, { id, message, type }]);
    setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), 4000);
  };

  useEffect(() => {
    const supabase = createBrowserClient();
    supabase.auth.getSession().then(async ({ data: { session } }) => {
      if (!session) return;
      setToken(session.access_token);
      const user = session.user;
      setUserEmail(user.email ?? null);
      const wsId = (user.app_metadata?.workspace_id ?? user.user_metadata?.workspace_id) as string | undefined;
      if (!wsId) return;
      setWorkspaceId(wsId);

      const ws = await apiClient.getWorkspace(wsId, session.access_token).catch(() => null);
      if (ws) {
        setWorkspaceName((ws as { name: string; mode: string }).name ?? "");
        setMode(((ws as { name: string; mode: string }).mode as WorkspaceMode) ?? "sales");
      }
      loadDigest(wsId, session.access_token);
    });
  }, []);

  const loadDigest = async (wsId: string, tok: string) => {
    setDigestLoading(true);
    try {
      const data = await apiClient.getWorkspaceDigest(wsId, tok);
      setDigest(data);
    } catch {
      // silently fail — digest is non-critical
    } finally {
      setDigestLoading(false);
    }
  };

  const handleSave = async () => {
    if (!workspaceId || !workspaceName.trim() || !token) return;
    setSaving(true);
    try {
      await apiClient.updateWorkspace(workspaceId, { name: workspaceName.trim(), mode }, token);
      addToast("Workspace settings saved.", "success");
    } catch (err) {
      addToast("Failed to save: " + (err instanceof Error ? err.message : "unknown error"), "error");
    } finally {
      setSaving(false);
    }
  };

  const handleSignOut = async () => {
    const supabase = createBrowserClient();
    await supabase.auth.signOut();
    router.push("/login");
  };

  return (
    <div className="flex flex-col gap-6 p-4 md:p-6 max-w-2xl">
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

      {/* AI Workspace Digest */}
      <Card>
        <div className="flex items-center justify-between mb-1">
          <div className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-violet-400" />
            <p className="text-sm font-semibold text-zinc-100">Workspace Digest</p>
            {digest && (
              <span className={cn(
                "text-[10px] font-semibold px-2 py-0.5 rounded-full border",
                digest.health_rating === "excellent" ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-300"
                  : digest.health_rating === "good" ? "border-indigo-500/40 bg-indigo-500/10 text-indigo-300"
                  : digest.health_rating === "needs_attention" ? "border-amber-500/40 bg-amber-500/10 text-amber-300"
                  : "border-rose-500/40 bg-rose-500/10 text-rose-300"
              )}>
                {digest.health_rating === "needs_attention" ? "Needs Attention"
                  : digest.health_rating.charAt(0).toUpperCase() + digest.health_rating.slice(1)}
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            {workspaceId && token && (
              <button
                onClick={() => loadDigest(workspaceId, token)}
                disabled={digestLoading}
                className="flex items-center gap-1 text-xs text-zinc-500 hover:text-zinc-300 transition"
              >
                <RefreshCw className={cn("h-3 w-3", digestLoading && "animate-spin")} />
                {digestLoading ? "Generating…" : "Regenerate"}
              </button>
            )}
            <button onClick={() => setDigestExpanded((v) => !v)} className="text-zinc-500 hover:text-zinc-300 transition">
              <ChevronDown className={cn("h-4 w-4 transition-transform", digestExpanded && "rotate-180")} />
            </button>
          </div>
        </div>

        {digestExpanded && (
          <div className="mt-4 space-y-4">
            {digestLoading && !digest && (
              <div className="space-y-2">
                {[60, 80, 50].map((w) => (
                  <div key={w} className={`h-3 bg-zinc-800 rounded animate-pulse w-${w === 60 ? '[60%]' : w === 80 ? '[80%]' : '[50%]'}`} />
                ))}
              </div>
            )}

            {digest && (
              <>
                {/* Summary */}
                <p className="text-sm text-zinc-300 leading-relaxed">{digest.summary}</p>

                {/* Metrics grid */}
                <div className="grid grid-cols-3 gap-2">
                  {[
                    { label: "Contacts", value: digest.metrics.total_contacts },
                    { label: "Open Deals", value: digest.metrics.open_deal_count },
                    { label: "Pipeline", value: `$${(digest.metrics.total_pipeline / 1000).toFixed(0)}K` },
                    { label: "Tasks Open", value: digest.metrics.open_task_count },
                    { label: "Overdue Tasks", value: digest.metrics.overdue_task_count },
                    { label: "Agent Runs", value: digest.metrics.agent_run_count },
                  ].map(({ label, value }) => (
                    <div key={label} className="rounded-lg bg-zinc-800/60 border border-zinc-700/50 px-3 py-2">
                      <p className="text-[10px] text-zinc-500 mb-0.5">{label}</p>
                      <p className="text-sm font-semibold text-zinc-100">{value}</p>
                    </div>
                  ))}
                </div>

                {/* Two-column: Highlights + Warnings */}
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <p className="text-[10px] font-semibold text-emerald-400 uppercase tracking-wider mb-2">Highlights</p>
                    <ul className="space-y-1.5">
                      {digest.highlights.map((h, i) => (
                        <li key={i} className="flex items-start gap-1.5">
                          <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400 mt-0.5 shrink-0" />
                          <span className="text-xs text-zinc-300">{h}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                  <div>
                    <p className="text-[10px] font-semibold text-amber-400 uppercase tracking-wider mb-2">Watch Out</p>
                    <ul className="space-y-1.5">
                      {digest.warnings.map((w, i) => (
                        <li key={i} className="flex items-start gap-1.5">
                          <AlertTriangle className="h-3.5 w-3.5 text-amber-400 mt-0.5 shrink-0" />
                          <span className="text-xs text-zinc-300">{w}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>

                {/* Recommended Actions */}
                <div>
                  <p className="text-[10px] font-semibold text-violet-400 uppercase tracking-wider mb-2">Recommended Actions</p>
                  <ol className="space-y-1">
                    {digest.recommended_actions.map((a, i) => (
                      <li key={i} className="flex items-start gap-2 text-xs text-zinc-300">
                        <span className="text-[10px] font-bold text-violet-400 mt-0.5 w-4 shrink-0">{i + 1}.</span>
                        {a}
                      </li>
                    ))}
                  </ol>
                </div>

                <p className="text-[10px] text-zinc-600">Generated {new Date(digest.generated_at).toLocaleString()}</p>
              </>
            )}

            {!digest && !digestLoading && (
              <p className="text-xs text-zinc-500">Digest will generate once workspace data is loaded.</p>
            )}
          </div>
        )}
      </Card>

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
              className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3.5 py-2.5 text-base sm:text-sm text-zinc-100 placeholder-zinc-600 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 transition"
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

          <Button variant="primary" onClick={handleSave} disabled={saving || !workspaceName.trim() || !isAdmin}>
            <Save className="h-3.5 w-3.5" />
            {saving ? "Saving…" : "Save changes"}
          </Button>
          {!isAdmin && (
            <p className="text-xs text-zinc-600 mt-2">Admin role required to modify workspace settings.</p>
          )}
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

      {/* Team */}
      {isAdmin && (
        <Card>
          <div className="flex items-center gap-2 mb-4">
            <Users className="h-4 w-4 text-indigo-400" />
            <p className="text-sm font-semibold text-zinc-100">Invite Teammates</p>
          </div>
          <p className="text-xs text-zinc-500 mb-4">
            Send a Supabase invite email to add a new member to this workspace.
          </p>
          <form
            onSubmit={async (e) => {
              e.preventDefault();
              if (!workspaceId || !token || !inviteEmail.trim()) return;
              setInviting(true);
              try {
                await apiClient.inviteTeammate(workspaceId, inviteEmail.trim(), token);
                addToast(`Invite sent to ${inviteEmail}`, "success");
                setInviteEmail("");
              } catch {
                addToast("Failed to send invite — check admin permissions", "error");
              } finally {
                setInviting(false);
              }
            }}
            className="flex gap-2"
          >
            <div className="flex-1 flex items-center gap-2 rounded-lg border border-zinc-700 bg-zinc-800 px-3.5">
              <Mail className="h-4 w-4 text-zinc-500 flex-shrink-0" />
              <input
                type="email"
                value={inviteEmail}
                onChange={(e) => setInviteEmail(e.target.value)}
                placeholder="teammate@company.com"
                className="flex-1 bg-transparent py-2.5 text-sm text-zinc-100 placeholder-zinc-600 focus:outline-none"
              />
            </div>
            <Button type="submit" variant="secondary" disabled={inviting || !inviteEmail.trim()}>
              {inviting ? "Sending…" : "Send Invite"}
            </Button>
          </form>
        </Card>
      )}

      {/* Developer */}
      <Card>
        <div className="flex items-center gap-2 mb-4">
          <Webhook className="h-4 w-4 text-indigo-400" />
          <p className="text-sm font-semibold text-zinc-100">Developer</p>
        </div>
        <p className="text-xs text-zinc-500 mb-4">
          Inspect incoming webhook events from Gmail Pub/Sub and Slack Events API.
        </p>
        <Link href="/settings/webhooks">
          <Button variant="secondary" className="w-full justify-between">
            <div className="flex items-center gap-2">
              <Webhook className="h-3.5 w-3.5" />
              Webhook Logs
            </div>
            <ChevronRight className="h-3.5 w-3.5 text-zinc-500" />
          </Button>
        </Link>
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
            {role && <Badge variant="indigo" size="sm" className="mt-1.5">{role.charAt(0).toUpperCase() + role.slice(1)}</Badge>}
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
        <Button
          variant="danger"
          size="sm"
          disabled={!isAdmin}
          onClick={() => setDeleteConfirmOpen(true)}
        >
          Delete Workspace
        </Button>
        {!isAdmin && (
          <p className="text-[10px] text-zinc-600 mt-2 font-mono">Admin role required to delete workspace.</p>
        )}
      </Card>

      {/* Delete workspace confirmation modal */}
      {deleteConfirmOpen && (
        <ConfirmDialog
          title="Delete this workspace?"
          description="This will permanently delete all contacts, deals, messages, tasks, and agents. This action cannot be undone."
          confirmText={workspaceName || "delete"}
          actionLabel="Delete Workspace"
          variant="danger"
          onConfirm={async () => {
            setDeleteConfirmOpen(false);
            addToast("Workspace deletion requested — contact support to complete.", "error");
          }}
          onClose={() => setDeleteConfirmOpen(false)}
        />
      )}
    </div>
  );
}
