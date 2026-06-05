"use client";

import { useState, useEffect, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import Header from "@/components/layout/Header";
import Card from "@/components/ui/Card";
import Badge from "@/components/ui/Badge";
import Avatar from "@/components/ui/Avatar";
import Button from "@/components/ui/Button";
import { cn, formatCurrency, stageConfig, dealStageOrder } from "@/lib/utils";
import { apiClient } from "@/lib/api-client";
import { createBrowserClient } from "@/lib/supabase";
import { useJobPoller } from "@/hooks/useJobPoller";
import type { DealStage } from "@/lib/types";
import {
  ArrowLeft, Brain, Heart, AlertTriangle, TrendingUp,
  Building2, Calendar, ChevronRight, Mail, Zap,
  ListTodo, Loader2, XCircle, Trash2, CheckCircle2,
  ExternalLink, DollarSign, Clock, User,
} from "lucide-react";
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid,
  Tooltip as RechartTooltip, ResponsiveContainer,
} from "recharts";

// ─── Types ───────────────────────────────────────────────────────────────────

type DealDetail = {
  id: string;
  workspace_id: string;
  title: string | null;
  company: string | null;
  contact_name: string | null;
  contact_id: string | null;
  value: number;
  stage: string;
  ml_win_probability: number;
  health_score: number;
  expected_close: string | null;
  assigned_agent: string | null;
  notes: string | null;
  created_at: string | null;
};

type TimelineEvent = {
  id: string;
  type: string;
  title: string;
  body: string;
  ts: string | null;
  meta?: Record<string, unknown>;
};

type TaskRow = {
  id: string;
  title: string;
  status: string;
  due_date: string | null;
};

type EmailDraft = { subject: string; body: string };

// ─── Helpers ─────────────────────────────────────────────────────────────────

function formatRelative(iso: string | null): string {
  if (!iso) return "—";
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "Just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

function renderMarkdown(text: string): string {
  return text
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/^- (.+)$/gm, '<li class="ml-4 list-disc">$1</li>')
    .replace(/(<li[^>]*>.*<\/li>\n?)+/g, (m) => `<ul class="space-y-0.5 my-1">${m}</ul>`)
    .replace(/\n\n/g, '</p><p class="mt-3">')
    .replace(/^/, "<p>")
    .replace(/$/, "</p>")
    .replace(/\n/g, "<br/>");
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function WinBar({ value }: { value: number }) {
  const color = value >= 70 ? "bg-emerald-400" : value >= 40 ? "bg-amber-400" : "bg-rose-400";
  const text = value >= 70 ? "text-emerald-400" : value >= 40 ? "text-amber-400" : "text-rose-400";
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1.5 rounded-full bg-zinc-800 overflow-hidden">
        <div className={cn("h-full rounded-full transition-all", color)} style={{ width: `${value}%` }} />
      </div>
      <span className={cn("text-xs font-mono font-bold w-8 text-right", text)}>{value}%</span>
    </div>
  );
}

function HealthBar({ score }: { score: number }) {
  const color = score >= 70 ? "bg-emerald-400" : score >= 40 ? "bg-amber-400" : "bg-rose-400";
  const text = score >= 70 ? "text-emerald-400" : score >= 40 ? "text-amber-400" : "text-rose-400";
  const Icon = score >= 70 ? Heart : AlertTriangle;
  return (
    <div className="flex items-center gap-2">
      <Icon className={cn("h-3.5 w-3.5 flex-shrink-0", text)} />
      <div className="flex-1 h-1.5 rounded-full bg-zinc-800 overflow-hidden">
        <div className={cn("h-full rounded-full transition-all", color)} style={{ width: `${score}%` }} />
      </div>
      <span className={cn("text-xs font-mono font-bold w-8 text-right", text)}>{score}</span>
    </div>
  );
}

function StageBadge({ stage }: { stage: string }) {
  const variant =
    stage === "closed_won" ? "emerald" :
    stage === "closed_lost" ? "rose" :
    stage === "negotiation" ? "indigo" :
    stage === "proposal" ? "amber" :
    "zinc";
  const cfg = stageConfig[stage as DealStage] ?? { label: stage };
  return <Badge variant={variant} size="sm">{cfg.label}</Badge>;
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function DealDetailPage() {
  const params = useParams();
  const router = useRouter();
  const dealId = params?.id as string;

  const [deal, setDeal] = useState<DealDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [token, setToken] = useState<string | null>(null);
  const [workspaceId, setWorkspaceId] = useState<string | null>(null);

  const [timeline, setTimeline] = useState<TimelineEvent[]>([]);
  const [timelineLoading, setTimelineLoading] = useState(false);
  const [tasks, setTasks] = useState<TaskRow[]>([]);
  const [tasksLoading, setTasksLoading] = useState(false);
  const [probTrend, setProbTrend] = useState<{ date: string; probability: number }[]>([]);
  const [probLoading, setProbLoading] = useState(false);

  const [moveSaving, setMoveSaving] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState(false);
  const [deleteText, setDeleteText] = useState("");
  const [deleting, setDeleting] = useState(false);

  const [emailDraft, setEmailDraft] = useState<EmailDraft | null>(null);
  const [emailLoading, setEmailLoading] = useState(false);

  const optimizePoller = useJobPoller();

  // ── Auth init ──────────────────────────────────────────────────────────────
  useEffect(() => {
    if (process.env.NEXT_PUBLIC_DEMO_MODE === "true") {
      setToken("demo-token");
      setWorkspaceId("demo-workspace-1");
      return;
    }
    const supabase = createBrowserClient();
    supabase.auth.getSession().then(({ data: { session } }) => {
      if (session) {
        setToken(session.access_token);
        setWorkspaceId(session.user.user_metadata?.workspace_id ?? null);
      }
    });
  }, []);

  // ── Load deal ──────────────────────────────────────────────────────────────
  useEffect(() => {
    if (!token || !workspaceId) return;
    setLoading(true);
    apiClient
      .getDeal(workspaceId, dealId, token)
      .then((data) => setDeal((data as DealDetail) ?? null))
      .catch(() => setDeal(null))
      .finally(() => setLoading(false));
  }, [token, workspaceId, dealId]);

  // ── Load side data ─────────────────────────────────────────────────────────
  const loadSideData = useCallback(async () => {
    if (!token || !workspaceId || !deal) return;

    setTimelineLoading(true);
    setTasksLoading(true);

    apiClient
      .getDealTimeline(workspaceId, dealId, token)
      .then((data) => setTimeline(Array.isArray(data) ? (data as TimelineEvent[]) : []))
      .catch(() => setTimeline([]))
      .finally(() => setTimelineLoading(false));

    setProbLoading(true);
    apiClient
      .getDealProbabilityTrend(workspaceId, dealId, token)
      .then((data) => setProbTrend(Array.isArray(data) ? data : []))
      .catch(() => setProbTrend([]))
      .finally(() => setProbLoading(false));

    if (deal.contact_id) {
      apiClient
        .getTasks(workspaceId, token, { contactId: deal.contact_id })
        .then((data) => setTasks(Array.isArray(data) ? (data as TaskRow[]) : []))
        .catch(() => setTasks([]))
        .finally(() => setTasksLoading(false));
    } else {
      setTasks([]);
      setTasksLoading(false);
    }
  }, [token, workspaceId, dealId, deal]);

  useEffect(() => {
    if (deal) loadSideData();
  }, [deal, loadSideData]);

  // ── Actions ────────────────────────────────────────────────────────────────

  const handleMoveStage = async (stage: DealStage) => {
    if (!token || !workspaceId || !deal) return;
    setMoveSaving(true);
    try {
      const updated = (await apiClient.updateDeal(workspaceId, deal.id, { stage }, token)) as DealDetail;
      setDeal((prev) => (prev ? { ...prev, stage: updated.stage ?? stage } : null));
    } catch { /* ignore */ }
    finally { setMoveSaving(false); }
  };

  const handleComposeEmail = async () => {
    if (!token || !workspaceId || !deal?.contact_id) return;
    setEmailLoading(true);
    try {
      const data = await apiClient.composeEmail(workspaceId, deal.contact_id, token);
      setEmailDraft(data as EmailDraft);
    } catch { /* ignore */ }
    finally { setEmailLoading(false); }
  };

  const handleOptimize = async () => {
    if (!token || !workspaceId) return;
    try {
      const res = await apiClient.triggerAgent("pipeline_optimizer", token) as { job_id?: string };
      if (res?.job_id) optimizePoller.start(res.job_id);
    } catch { /* ignore */ }
  };

  const handleDelete = async () => {
    if (!token || !workspaceId || deleteText !== (deal?.title ?? "")) return;
    setDeleting(true);
    try {
      await apiClient.deleteDeal(workspaceId, dealId, token);
      router.push("/pipeline");
    } catch { /* ignore */ }
    finally { setDeleting(false); }
  };

  // ── Render guards ──────────────────────────────────────────────────────────

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-6 w-6 text-indigo-400 animate-spin" />
      </div>
    );
  }

  if (!deal) {
    return (
      <div className="flex flex-col items-center justify-center h-64 gap-4">
        <AlertTriangle className="h-8 w-8 text-zinc-600" />
        <p className="text-sm text-zinc-500">Deal not found.</p>
        <Button variant="secondary" onClick={() => router.push("/pipeline")}>
          <ArrowLeft className="h-3.5 w-3.5" /> Back to Pipeline
        </Button>
      </div>
    );
  }

  const stage = deal.stage as DealStage;
  const stageCfg = stageConfig[stage] ?? { label: deal.stage, color: "text-zinc-400", bg: "bg-zinc-700/50" };
  const isClosedStage = stage === "closed_won" || stage === "closed_lost";
  const otherStages = dealStageOrder.filter((s) => s !== stage);
  const openTasks = tasks.filter((t) => t.status === "open" || t.status === "in_progress");
  const doneTasks = tasks.filter((t) => t.status === "done" || t.status === "cancelled");
  const contactInitials = deal.contact_name
    ? deal.contact_name.split(" ").map((n) => n[0]).join("").slice(0, 2).toUpperCase()
    : "??";

  return (
    <div className="flex flex-col gap-6 p-4 md:p-6">
      <Header
        title={deal.title ?? "Untitled Deal"}
        subtitle={`${deal.company ?? "—"} · ${stageCfg.label}`}
      />

      {/* ── Actions bar ── */}
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="secondary" onClick={() => router.push("/pipeline")} className="gap-1.5">
          <ArrowLeft className="h-3.5 w-3.5" /> Pipeline
        </Button>

        <div className="flex-1" />

        {deal.contact_id && (
          <Button
            variant="secondary"
            onClick={() => router.push(`/contacts/${deal.contact_id}`)}
            className="gap-1.5"
          >
            <User className="h-3.5 w-3.5" /> Contact
          </Button>
        )}

        {deal.contact_id && (
          <Button
            variant="secondary"
            onClick={handleComposeEmail}
            disabled={emailLoading}
            className="gap-1.5"
          >
            {emailLoading ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Mail className="h-3.5 w-3.5" />
            )}
            Compose Email
          </Button>
        )}

        <Button
          variant="secondary"
          onClick={handleOptimize}
          disabled={optimizePoller.state === "pending" || optimizePoller.state === "started"}
          className="gap-1.5"
        >
          {optimizePoller.state === "pending" || optimizePoller.state === "started" ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : optimizePoller.state === "success" ? (
            <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />
          ) : (
            <Zap className="h-3.5 w-3.5" />
          )}
          Optimize
        </Button>

        <Button
          variant="secondary"
          onClick={() => setDeleteConfirm(true)}
          className="gap-1.5 text-rose-400 border-rose-500/20 hover:border-rose-500/40 hover:text-rose-300"
        >
          <Trash2 className="h-3.5 w-3.5" /> Delete
        </Button>
      </div>

      {/* ── Main grid ── */}
      <div className="grid grid-cols-1 lg:grid-cols-[320px_1fr] gap-6">

        {/* Left: Deal profile */}
        <div className="flex flex-col gap-4">

          {/* Identity card */}
          <Card className="p-5 space-y-4">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <h2 className="text-base font-semibold text-zinc-100 leading-snug">{deal.title}</h2>
                <div className="flex items-center gap-1.5 mt-1 text-zinc-400">
                  <Building2 className="h-3.5 w-3.5 text-zinc-600 flex-shrink-0" />
                  <span className="text-sm truncate">{deal.company}</span>
                </div>
              </div>
              <StageBadge stage={stage} />
            </div>

            {/* Value chip */}
            <div className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-3.5 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <DollarSign className="h-4 w-4 text-indigo-400" />
                <span className="text-xs text-zinc-400">Deal Value</span>
              </div>
              <span className="text-xl font-bold font-mono text-zinc-100">{formatCurrency(deal.value)}</span>
            </div>

            {/* Health */}
            {!isClosedStage && (
              <div className="space-y-2">
                <p className="text-[10px] font-mono text-zinc-500 uppercase tracking-widest">Deal Health</p>
                <HealthBar score={deal.health_score} />
              </div>
            )}

            {/* ML win prob */}
            {!isClosedStage && (
              <div className="space-y-2">
                <div className="flex items-center gap-1.5">
                  <Brain className="h-3.5 w-3.5 text-indigo-400" />
                  <p className="text-[10px] font-mono text-zinc-500 uppercase tracking-widest">ML Win Probability</p>
                </div>
                <WinBar value={deal.ml_win_probability} />
              </div>
            )}

            {isClosedStage && (
              <div className={cn(
                "rounded-xl border px-4 py-3 text-center",
                stage === "closed_won"
                  ? "border-emerald-500/20 bg-emerald-500/5 text-emerald-400"
                  : "border-rose-500/20 bg-rose-500/5 text-rose-400"
              )}>
                <span className="text-sm font-semibold">
                  {stage === "closed_won" ? "🏆 Closed Won" : "✗ Closed Lost"}
                </span>
              </div>
            )}
          </Card>

          {/* Metadata card */}
          <Card className="p-4 space-y-3">
            <p className="text-[10px] font-mono text-zinc-500 uppercase tracking-widest">Deal Info</p>
            <div className="space-y-2.5">
              {deal.expected_close && (
                <div className="flex items-center gap-2.5">
                  <Calendar className="h-3.5 w-3.5 text-zinc-600 flex-shrink-0" />
                  <span className="text-xs text-zinc-400">Expected close</span>
                  <span className="text-xs font-mono text-zinc-200 ml-auto">{deal.expected_close}</span>
                </div>
              )}
              {deal.created_at && (
                <div className="flex items-center gap-2.5">
                  <Clock className="h-3.5 w-3.5 text-zinc-600 flex-shrink-0" />
                  <span className="text-xs text-zinc-400">Created</span>
                  <span className="text-xs font-mono text-zinc-200 ml-auto">
                    {new Date(deal.created_at).toLocaleDateString("en-US", {
                      month: "short", day: "numeric", year: "numeric",
                    })}
                  </span>
                </div>
              )}
              {deal.assigned_agent && (
                <div className="flex items-center gap-2.5">
                  <Zap className="h-3.5 w-3.5 text-zinc-600 flex-shrink-0" />
                  <span className="text-xs text-zinc-400">Agent</span>
                  <span className="text-xs font-mono text-indigo-400 ml-auto">{deal.assigned_agent}</span>
                </div>
              )}
            </div>
          </Card>

          {/* Associated contact */}
          {deal.contact_id && deal.contact_name && (
            <Card className="p-4 space-y-3">
              <p className="text-[10px] font-mono text-zinc-500 uppercase tracking-widest">Associated Contact</p>
              <div className="flex items-center gap-3">
                <Avatar initials={contactInitials} size="md" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-zinc-100">{deal.contact_name}</p>
                </div>
                <Link
                  href={`/contacts/${deal.contact_id}`}
                  className="text-zinc-500 hover:text-indigo-400 transition-colors p-1"
                  aria-label="Open contact detail"
                >
                  <ExternalLink className="h-4 w-4" />
                </Link>
              </div>
            </Card>
          )}

          {/* Notes */}
          {deal.notes && (
            <Card className="p-4 space-y-2">
              <p className="text-[10px] font-mono text-zinc-500 uppercase tracking-widest">Notes</p>
              <p className="text-xs text-zinc-400 leading-relaxed">{deal.notes}</p>
            </Card>
          )}
        </div>

        {/* Right: Stage mover + Tasks + Timeline */}
        <div className="flex flex-col gap-6">

          {/* Stage mover */}
          {!isClosedStage && (
            <Card className="p-4 space-y-3">
              <div className="flex items-center gap-2">
                <TrendingUp className="h-4 w-4 text-indigo-400" />
                <p className="text-sm font-semibold text-zinc-200">Move to Stage</p>
                {moveSaving && <Loader2 className="h-3.5 w-3.5 text-zinc-500 animate-spin ml-auto" />}
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-1.5">
                {otherStages.map((s) => {
                  const cfg = stageConfig[s];
                  return (
                    <button
                      key={s}
                      onClick={() => handleMoveStage(s)}
                      disabled={moveSaving}
                      className={cn(
                        "flex items-center justify-between rounded-lg border border-zinc-800 px-3 py-2.5 text-xs transition-all hover:border-zinc-700 text-left",
                        cfg.bg,
                        moveSaving && "opacity-50 cursor-not-allowed cursor-default",
                        !moveSaving && "cursor-pointer"
                      )}
                    >
                      <span className={cn("font-medium", cfg.color)}>{cfg.label}</span>
                      <ChevronRight className="h-3 w-3 text-zinc-600 flex-shrink-0" />
                    </button>
                  );
                })}
              </div>
            </Card>
          )}

          {/* Win probability trend */}
          {!isClosedStage && (
            <Card className="p-4 space-y-3">
              <div className="flex items-center gap-2">
                <Brain className="h-4 w-4 text-indigo-400" />
                <p className="text-sm font-semibold text-zinc-200">Win Probability Trend</p>
                <span className="ml-auto text-[10px] font-mono text-zinc-500">Last 30 days</span>
              </div>
              {probLoading ? (
                <div className="h-28 rounded-xl bg-zinc-800/50 animate-pulse" />
              ) : probTrend.length > 0 ? (
                <div className="h-28">
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={probTrend} margin={{ top: 4, right: 4, bottom: 0, left: -24 }}>
                      <defs>
                        <linearGradient id="probGrad" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="#6366F1" stopOpacity={0.25} />
                          <stop offset="95%" stopColor="#6366F1" stopOpacity={0} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid strokeDasharray="3 3" stroke="#27272A" vertical={false} />
                      <XAxis
                        dataKey="date"
                        tick={{ fill: "#71717A", fontSize: 9 }}
                        axisLine={false}
                        tickLine={false}
                        interval="preserveStartEnd"
                      />
                      <YAxis
                        domain={[0, 100]}
                        tick={{ fill: "#71717A", fontSize: 9 }}
                        axisLine={false}
                        tickLine={false}
                        tickFormatter={(v) => `${v}%`}
                        width={36}
                      />
                      <RechartTooltip
                        formatter={(v) => [`${v ?? 0}%`, "Win Prob"]}
                        contentStyle={{ background: "#18181B", border: "1px solid #27272A", borderRadius: 8, fontSize: 11 }}
                      />
                      <Area
                        type="monotone"
                        dataKey="probability"
                        stroke="#6366F1"
                        strokeWidth={2}
                        fill="url(#probGrad)"
                        dot={false}
                        activeDot={{ r: 4, fill: "#6366F1" }}
                      />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              ) : (
                <p className="text-xs text-zinc-500 text-center py-4">No trend data available.</p>
              )}
            </Card>
          )}

          {/* Tasks */}
          <Card className="p-4 space-y-3">
            <div className="flex items-center gap-2">
              <ListTodo className="h-4 w-4 text-indigo-400" />
              <p className="text-sm font-semibold text-zinc-200">Tasks</p>
              {tasks.length > 0 && (
                <span className="ml-auto text-xs font-mono text-zinc-500">{openTasks.length} open</span>
              )}
            </div>

            {tasksLoading ? (
              <div className="space-y-2">
                {[1, 2].map((i) => (
                  <div key={i} className="h-12 rounded-xl border border-zinc-800 bg-zinc-900 animate-pulse" />
                ))}
              </div>
            ) : !deal.contact_id ? (
              <p className="text-xs text-zinc-500 py-4 text-center">
                No contact linked — associate a contact to see tasks.
              </p>
            ) : tasks.length === 0 ? (
              <div className="flex flex-col items-center gap-2 py-6 text-center">
                <ListTodo className="h-6 w-6 text-zinc-700" />
                <p className="text-xs text-zinc-500">No tasks for this contact.</p>
              </div>
            ) : (
              <div className="space-y-2">
                {openTasks.map((task) => (
                  <div
                    key={task.id}
                    className="flex items-start gap-3 rounded-xl border border-zinc-800 bg-zinc-900 px-3.5 py-3"
                  >
                    <span
                      className={cn(
                        "h-2 w-2 rounded-full flex-shrink-0 mt-1.5",
                        task.status === "in_progress" ? "bg-indigo-400" : "bg-amber-400"
                      )}
                    />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm text-zinc-200">{task.title}</p>
                      {task.due_date && (
                        <p className="text-[11px] text-zinc-500 mt-0.5 flex items-center gap-1">
                          <Calendar className="h-3 w-3" /> Due {task.due_date}
                        </p>
                      )}
                    </div>
                    <Badge
                      variant={task.status === "in_progress" ? "indigo" : "amber"}
                      size="sm"
                    >
                      {task.status.replace("_", " ")}
                    </Badge>
                  </div>
                ))}
                {doneTasks.length > 0 && openTasks.length > 0 && (
                  <div className="border-t border-zinc-800 pt-2 mt-1">
                    <p className="text-[10px] font-mono text-zinc-600 uppercase tracking-widest mb-2">
                      Completed ({doneTasks.length})
                    </p>
                    {doneTasks.slice(0, 3).map((task) => (
                      <div
                        key={task.id}
                        className="flex items-start gap-3 rounded-xl border border-zinc-800 bg-zinc-900 px-3.5 py-3 mb-2"
                      >
                        <span className="h-2 w-2 rounded-full flex-shrink-0 mt-1.5 bg-emerald-400" />
                        <p className="text-sm text-zinc-500 line-through">{task.title}</p>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </Card>

          {/* Timeline */}
          <Card className="p-4 space-y-3">
            <div className="flex items-center gap-2">
              <Zap className="h-4 w-4 text-indigo-400" />
              <p className="text-sm font-semibold text-zinc-200">Activity Timeline</p>
            </div>

            {timelineLoading ? (
              <div className="space-y-2">
                {[1, 2, 3].map((i) => (
                  <div key={i} className="h-14 rounded-xl border border-zinc-800 bg-zinc-900 animate-pulse" />
                ))}
              </div>
            ) : timeline.length === 0 ? (
              <div className="flex flex-col items-center gap-2 py-6 text-center">
                <Zap className="h-6 w-6 text-zinc-700" />
                <p className="text-xs text-zinc-500">No activity recorded yet.</p>
              </div>
            ) : (
              <div className="relative">
                {timeline.map((evt, i) => {
                  const dotColor =
                    evt.type === "message" ? "bg-indigo-400" :
                    evt.type === "deal_moved" || evt.type === "deal_stage" ? "bg-amber-400" :
                    evt.type === "call" ? "bg-emerald-400" :
                    "bg-zinc-600";
                  const typeLabel =
                    evt.type === "message" ? "Email" :
                    evt.type === "deal_moved" || evt.type === "deal_stage" ? "Stage" :
                    evt.type === "call" ? "Call" :
                    "Activity";
                  return (
                    <div key={evt.id} className="flex gap-3">
                      <div className="flex flex-col items-center flex-shrink-0">
                        <span className={cn("mt-1.5 h-2.5 w-2.5 rounded-full", dotColor)} />
                        {i < timeline.length - 1 && (
                          <span className="flex-1 w-px bg-zinc-800 mt-1" />
                        )}
                      </div>
                      <div className="pb-4 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="text-[10px] font-mono text-zinc-500 uppercase tracking-widest">
                            {typeLabel}
                          </span>
                          <span className="text-[10px] text-zinc-600">{formatRelative(evt.ts)}</span>
                        </div>
                        <p className="text-xs font-medium text-zinc-300 mt-0.5">{evt.title}</p>
                        {evt.body && (
                          <p className="text-xs text-zinc-500 mt-0.5 line-clamp-2">{evt.body}</p>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </Card>
        </div>
      </div>

      {/* ── Email draft modal ── */}
      {emailDraft && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4"
          onClick={() => setEmailDraft(null)}
        >
          <div
            className="w-full max-w-lg rounded-2xl border border-zinc-800 bg-zinc-950 overflow-hidden shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between border-b border-zinc-800 px-5 py-4">
              <div className="flex items-center gap-2">
                <Mail className="h-4 w-4 text-indigo-400" />
                <p className="text-sm font-semibold text-zinc-100">AI-Generated Draft</p>
              </div>
              <button
                onClick={() => setEmailDraft(null)}
                className="text-zinc-400 hover:text-zinc-100 cursor-pointer transition-colors"
                aria-label="Close draft"
              >
                <XCircle className="h-4 w-4" />
              </button>
            </div>
            <div className="p-5 space-y-4">
              <div>
                <p className="text-[10px] font-mono text-zinc-500 uppercase tracking-widest mb-1">Subject</p>
                <p className="text-sm text-zinc-100 rounded-lg border border-zinc-800 bg-zinc-900 px-3 py-2">
                  {emailDraft.subject}
                </p>
              </div>
              <div>
                <p className="text-[10px] font-mono text-zinc-500 uppercase tracking-widest mb-1">Body</p>
                <div className="rounded-lg border border-zinc-800 bg-zinc-900 px-3 py-3 max-h-64 overflow-y-auto">
                  <div
                    className="text-sm text-zinc-200 leading-relaxed [&_strong]:font-semibold [&_ul]:my-1 [&_li]:ml-4 [&_li]:list-disc [&_p]:mt-2 first:[&_p]:mt-0"
                    dangerouslySetInnerHTML={{ __html: renderMarkdown(emailDraft.body) }}
                  />
                </div>
              </div>
              <Button
                variant="primary"
                className="w-full justify-center"
                onClick={() => {
                  navigator.clipboard.writeText(
                    `Subject: ${emailDraft.subject}\n\n${emailDraft.body}`
                  );
                }}
              >
                <Mail className="h-3.5 w-3.5" /> Copy to Clipboard
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* ── Delete confirm modal ── */}
      {deleteConfirm && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4"
          onClick={() => { setDeleteConfirm(false); setDeleteText(""); }}
        >
          <div
            className="w-full max-w-md rounded-2xl border border-zinc-800 bg-zinc-950 overflow-hidden shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between border-b border-zinc-800 px-5 py-4">
              <div className="flex items-center gap-2">
                <Trash2 className="h-4 w-4 text-rose-400" />
                <p className="text-sm font-semibold text-zinc-100">Delete Deal</p>
              </div>
              <button
                onClick={() => { setDeleteConfirm(false); setDeleteText(""); }}
                className="text-zinc-400 hover:text-zinc-100 cursor-pointer transition-colors"
                aria-label="Close"
              >
                <XCircle className="h-4 w-4" />
              </button>
            </div>
            <div className="p-5 space-y-4">
              <p className="text-sm text-zinc-400">
                This action cannot be undone. Type{" "}
                <span className="font-mono text-zinc-200">{deal.title}</span> to confirm.
              </p>
              <input
                type="text"
                value={deleteText}
                onChange={(e) => setDeleteText(e.target.value)}
                placeholder={deal.title ?? "Deal title"}
                autoFocus
                className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3.5 py-2.5 text-sm text-zinc-100 placeholder-zinc-600 focus:border-rose-500 focus:outline-none focus:ring-1 focus:ring-rose-500 transition"
              />
              <div className="flex gap-2">
                <Button
                  variant="secondary"
                  className="flex-1 justify-center"
                  onClick={() => { setDeleteConfirm(false); setDeleteText(""); }}
                >
                  Cancel
                </Button>
                <Button
                  variant="primary"
                  className="flex-1 justify-center bg-rose-600 hover:bg-rose-500 border-rose-600 focus:ring-rose-500 disabled:opacity-40"
                  disabled={deleteText !== (deal.title ?? "") || deleting}
                  onClick={handleDelete}
                >
                  {deleting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Trash2 className="h-3.5 w-3.5" />}
                  Delete Deal
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
