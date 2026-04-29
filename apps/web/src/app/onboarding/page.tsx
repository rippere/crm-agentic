"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { createBrowserClient } from "@/lib/supabase";
import { Zap, TrendingUp, CheckSquare, Layers, Mail, MessageSquare, Users, ArrowRight, Check, Loader2 } from "lucide-react";
import type { WorkspaceMode } from "@/lib/types";
import { cn } from "@/lib/utils";

const STEPS = ["Workspace", "Mode", "Integrations", "Team"] as const;
type Step = 1 | 2 | 3 | 4;

const modeOptions: { value: WorkspaceMode; label: string; description: string; icon: React.ElementType }[] = [
  { value: "sales", label: "Sales", description: "CRM, pipeline, contact intelligence, and deal tracking.", icon: TrendingUp },
  { value: "pm", label: "Project Management", description: "Task tracking, inbox triage, and team collaboration.", icon: CheckSquare },
  { value: "both", label: "Both", description: "Full platform — sales + PM features in one unified workspace.", icon: Layers },
];

function StepIndicator({ current }: { current: Step }) {
  return (
    <div className="flex items-center gap-0 mb-8">
      {STEPS.map((label, i) => {
        const step = (i + 1) as Step;
        const done = current > step;
        const active = current === step;
        return (
          <div key={label} className="flex items-center flex-1 last:flex-none">
            <div className={cn(
              "flex h-7 w-7 items-center justify-center rounded-full text-xs font-semibold border transition-all",
              done ? "bg-indigo-600 border-indigo-600 text-white" :
              active ? "border-indigo-500 text-indigo-400 bg-indigo-500/10" :
              "border-zinc-700 text-zinc-600"
            )}>
              {done ? <Check className="h-3.5 w-3.5" /> : step}
            </div>
            <p className={cn("ml-2 text-xs font-medium hidden sm:block", active ? "text-zinc-200" : done ? "text-zinc-400" : "text-zinc-600")}>
              {label}
            </p>
            {i < STEPS.length - 1 && (
              <div className={cn("flex-1 h-px mx-3 transition-colors", done ? "bg-indigo-600" : "bg-zinc-800")} />
            )}
          </div>
        );
      })}
    </div>
  );
}

export default function OnboardingPage() {
  const router = useRouter();
  const [step, setStep] = useState<Step>(1);
  const [workspaceName, setWorkspaceName] = useState("");
  const [mode, setMode] = useState<WorkspaceMode>("sales");
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteSent, setInviteSent] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [workspaceId, setWorkspaceId] = useState<string | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [gmailConnected, setGmailConnected] = useState(false);
  const [slackConnected, setSlackConnected] = useState(false);

  const slug = workspaceName.toLowerCase().replace(/\s+/g, "-").replace(/[^a-z0-9-]/g, "");

  const createWorkspace = async () => {
    setLoading(true);
    setError(null);
    const supabase = createBrowserClient();
    const { data: { user }, error: userError } = await supabase.auth.getUser();
    if (userError || !user) {
      setError("Not authenticated. Please sign in first.");
      setLoading(false);
      return false;
    }
    const { data: workspace, error: wsError } = await supabase
      .from("workspaces").insert({ name: workspaceName.trim(), slug, mode }).select().single();
    if (wsError || !workspace) {
      setError(wsError?.message ?? "Failed to create workspace.");
      setLoading(false);
      return false;
    }
    await supabase.from("users").insert({ supabase_uid: user.id, workspace_id: workspace.id, email: user.email ?? "", role: "admin" });
    await supabase.auth.updateUser({ data: { workspace_id: workspace.id } });
    const { data: { session } } = await supabase.auth.getSession();
    setWorkspaceId(workspace.id);
    setToken(session?.access_token ?? null);
    setLoading(false);
    return true;
  };

  const handleStep1 = (e: React.FormEvent) => {
    e.preventDefault();
    if (!workspaceName.trim()) return;
    setStep(2);
  };

  const handleStep2 = async () => {
    const ok = await createWorkspace();
    if (ok) setStep(3);
  };

  const handleConnectGmail = async () => {
    if (!workspaceId || !token) return;
    const res = await fetch(`${process.env.NEXT_PUBLIC_FASTAPI_URL}/workspaces/${workspaceId}/connectors/gmail/auth`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (res.ok) {
      const { auth_url } = await res.json();
      if (auth_url && auth_url !== "#") {
        window.open(auth_url, "_blank");
        setGmailConnected(true);
      }
    }
  };

  const handleConnectSlack = async () => {
    if (!workspaceId || !token) return;
    const res = await fetch(`${process.env.NEXT_PUBLIC_FASTAPI_URL}/workspaces/${workspaceId}/connectors/slack/auth`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (res.ok) {
      const { auth_url } = await res.json();
      if (auth_url && auth_url !== "#") {
        window.open(auth_url, "_blank");
        setSlackConnected(true);
      }
    }
  };

  const handleInvite = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inviteEmail.trim()) return;
    setInviteSent(true);
  };

  return (
    <div className="min-h-screen bg-[#09090B] flex items-center justify-center px-4 py-12">
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

        <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-8">
          <StepIndicator current={step} />

          {error && (
            <div className="mb-5 rounded-lg bg-rose-500/10 border border-rose-500/20 px-4 py-3 text-sm text-rose-400">
              {error}
            </div>
          )}

          {/* Step 1: Workspace name */}
          {step === 1 && (
            <form onSubmit={handleStep1} className="space-y-6">
              <div>
                <h1 className="text-xl font-semibold text-zinc-100 mb-1">Name your workspace</h1>
                <p className="text-sm text-zinc-500 mb-6">This is how your team will identify the workspace.</p>
                <label className="block text-xs font-medium text-zinc-400 mb-1.5">Workspace name</label>
                <input
                  type="text"
                  value={workspaceName}
                  onChange={(e) => setWorkspaceName(e.target.value)}
                  placeholder="Acme Corp"
                  required
                  autoFocus
                  className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3.5 py-2.5 text-sm text-zinc-100 placeholder-zinc-600 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 transition"
                />
                {slug && (
                  <p className="mt-1.5 text-[11px] text-zinc-600 font-mono">slug: <span className="text-zinc-500">{slug}</span></p>
                )}
              </div>
              <button
                type="submit"
                disabled={!workspaceName.trim()}
                className="w-full flex items-center justify-center gap-2 rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed transition"
              >
                Continue <ArrowRight className="h-4 w-4" />
              </button>
            </form>
          )}

          {/* Step 2: Mode */}
          {step === 2 && (
            <div className="space-y-6">
              <div>
                <h1 className="text-xl font-semibold text-zinc-100 mb-1">Choose your mode</h1>
                <p className="text-sm text-zinc-500 mb-6">Select how you&apos;ll primarily use NovaCRM.</p>
                <div className="grid grid-cols-1 gap-3">
                  {modeOptions.map(({ value, label, description, icon: Icon }) => (
                    <button
                      key={value}
                      type="button"
                      onClick={() => setMode(value)}
                      className={cn(
                        "flex items-start gap-4 rounded-lg border p-4 text-left transition-all",
                        mode === value
                          ? "border-indigo-500 bg-indigo-600/10"
                          : "border-zinc-700 bg-zinc-800 hover:border-zinc-600"
                      )}
                    >
                      <Icon className={cn("h-5 w-5 mt-0.5 flex-shrink-0", mode === value ? "text-indigo-400" : "text-zinc-500")} />
                      <div>
                        <p className={cn("text-sm font-semibold mb-0.5", mode === value ? "text-indigo-300" : "text-zinc-300")}>{label}</p>
                        <p className="text-xs text-zinc-500 leading-snug">{description}</p>
                      </div>
                      {mode === value && <Check className="h-4 w-4 text-indigo-400 ml-auto flex-shrink-0 mt-0.5" />}
                    </button>
                  ))}
                </div>
              </div>
              <div className="flex gap-3">
                <button
                  onClick={() => setStep(1)}
                  className="flex-1 rounded-lg border border-zinc-700 px-4 py-2.5 text-sm font-medium text-zinc-400 hover:text-zinc-200 hover:border-zinc-600 transition"
                >
                  Back
                </button>
                <button
                  onClick={handleStep2}
                  disabled={loading}
                  className="flex-1 flex items-center justify-center gap-2 rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-indigo-500 disabled:opacity-50 transition"
                >
                  {loading ? <><Loader2 className="h-4 w-4 animate-spin" /> Creating…</> : <>Continue <ArrowRight className="h-4 w-4" /></>}
                </button>
              </div>
            </div>
          )}

          {/* Step 3: Integrations */}
          {step === 3 && (
            <div className="space-y-6">
              <div>
                <h1 className="text-xl font-semibold text-zinc-100 mb-1">Connect your tools</h1>
                <p className="text-sm text-zinc-500 mb-6">Connect Gmail and Slack to unlock AI-powered email drafting and messaging intelligence.</p>
                <div className="space-y-3">
                  <div className={cn(
                    "flex items-center gap-4 rounded-lg border p-4 transition-all",
                    gmailConnected ? "border-emerald-500/30 bg-emerald-500/5" : "border-zinc-700 bg-zinc-800"
                  )}>
                    <Mail className={cn("h-5 w-5 flex-shrink-0", gmailConnected ? "text-emerald-400" : "text-zinc-400")} />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-semibold text-zinc-200">Gmail</p>
                      <p className="text-xs text-zinc-500">Sync emails and send AI-drafted replies</p>
                    </div>
                    {gmailConnected ? (
                      <span className="flex items-center gap-1 text-xs text-emerald-400 font-medium"><Check className="h-3.5 w-3.5" /> Connected</span>
                    ) : (
                      <button
                        onClick={handleConnectGmail}
                        className="rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-indigo-500 transition"
                      >
                        Connect
                      </button>
                    )}
                  </div>

                  <div className={cn(
                    "flex items-center gap-4 rounded-lg border p-4 transition-all",
                    slackConnected ? "border-emerald-500/30 bg-emerald-500/5" : "border-zinc-700 bg-zinc-800"
                  )}>
                    <MessageSquare className={cn("h-5 w-5 flex-shrink-0", slackConnected ? "text-emerald-400" : "text-zinc-400")} />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-semibold text-zinc-200">Slack</p>
                      <p className="text-xs text-zinc-500">Import Slack conversations and enable HITL alerts</p>
                    </div>
                    {slackConnected ? (
                      <span className="flex items-center gap-1 text-xs text-emerald-400 font-medium"><Check className="h-3.5 w-3.5" /> Connected</span>
                    ) : (
                      <button
                        onClick={handleConnectSlack}
                        className="rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-indigo-500 transition"
                      >
                        Connect
                      </button>
                    )}
                  </div>
                </div>
              </div>
              <div className="flex gap-3">
                <button
                  onClick={() => setStep(4)}
                  className="flex-1 rounded-lg border border-zinc-700 px-4 py-2.5 text-sm font-medium text-zinc-400 hover:text-zinc-200 hover:border-zinc-600 transition"
                >
                  Skip for now
                </button>
                <button
                  onClick={() => setStep(4)}
                  className="flex-1 flex items-center justify-center gap-2 rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-indigo-500 transition"
                >
                  Continue <ArrowRight className="h-4 w-4" />
                </button>
              </div>
            </div>
          )}

          {/* Step 4: Invite team */}
          {step === 4 && (
            <div className="space-y-6">
              <div>
                <h1 className="text-xl font-semibold text-zinc-100 mb-1">Invite your team</h1>
                <p className="text-sm text-zinc-500 mb-6">Add teammates to your workspace. You can always invite more from Settings.</p>

                {inviteSent ? (
                  <div className="flex items-center gap-3 rounded-lg border border-emerald-500/30 bg-emerald-500/5 px-4 py-3">
                    <Check className="h-4 w-4 text-emerald-400 flex-shrink-0" />
                    <p className="text-sm text-emerald-300">Invite sent to <span className="font-mono">{inviteEmail}</span></p>
                  </div>
                ) : (
                  <form onSubmit={handleInvite} className="flex gap-2">
                    <div className="flex-1 flex items-center gap-2 rounded-lg border border-zinc-700 bg-zinc-800 px-3.5">
                      <Users className="h-4 w-4 text-zinc-500 flex-shrink-0" />
                      <input
                        type="email"
                        value={inviteEmail}
                        onChange={(e) => setInviteEmail(e.target.value)}
                        placeholder="teammate@company.com"
                        className="flex-1 bg-transparent py-2.5 text-sm text-zinc-100 placeholder-zinc-600 focus:outline-none"
                      />
                    </div>
                    <button
                      type="submit"
                      className="rounded-lg bg-zinc-700 px-4 py-2.5 text-sm font-medium text-zinc-200 hover:bg-zinc-600 transition"
                    >
                      Invite
                    </button>
                  </form>
                )}
              </div>

              <button
                onClick={() => router.push("/dashboard")}
                className="w-full flex items-center justify-center gap-2 rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-indigo-500 transition"
              >
                Go to Dashboard <ArrowRight className="h-4 w-4" />
              </button>
              <p className="text-center text-xs text-zinc-600">
                Your workspace is ready. You can configure integrations anytime in Settings.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
