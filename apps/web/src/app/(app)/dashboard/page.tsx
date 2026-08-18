"use client";

import { useState, useEffect } from "react";
import Header from "@/components/layout/Header";
import Card from "@/components/ui/Card";
import Badge from "@/components/ui/Badge";
import { mockAgents, mockActivity } from "@/lib/mock-data";
import { demoDashboard } from "@/lib/demo-data";
import { useDeals } from "@/hooks/useDeals";
import { formatCurrency } from "@/lib/utils";
import { apiClient } from "@/lib/api-client";
import { createBrowserClient } from "@/lib/supabase";
import {
  AreaChart, Area, BarChart, Bar, LineChart, Line,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend, Cell,
} from "recharts";
import Link from "next/link";
import {
  DollarSign, Briefcase, Brain, Bot, TrendingUp, TrendingDown,
  Minus, Activity, CheckCircle, AlertTriangle, Info,
  ListTodo, Mail, BarChart2, CheckSquare, ExternalLink, Bell,
  Sparkles, RefreshCw, Target, ChevronDown, Zap, Phone, Calendar,
} from "lucide-react";
import { cn, SIGNAL } from "@/lib/utils";
import type { KPI, ActivityEvent, Deal } from "@/lib/types";

interface PMKpis {
  tasksExtractedToday: number;
  avgClarityScore: number | null;
  openTasks: number;
  messagesIngested: number;
}

interface StaleDeal {
  id: string;
  title: string;
  company: string;
  stage: string;
  value: number;
  health_score: number;
  signals: string[];
}

interface OverdueAction {
  id: string;
  title: string | null;
  company: string | null;
  stage: string;
  value: number;
  next_action: string | null;
  next_action_date: string;
  days_overdue: number;
}

const kpiIcons: Record<string, React.ReactNode> = {
  dollar: <DollarSign className="h-4 w-4" />,
  briefcase: <Briefcase className="h-4 w-4" />,
  brain: <Brain className="h-4 w-4" />,
  bot: <Bot className="h-4 w-4" />,
  barChart: <BarChart2 className="h-4 w-4" />,
};

const severityIcon: Record<ActivityEvent["severity"], React.ReactNode> = {
  success: <CheckCircle className="h-3.5 w-3.5 flex-shrink-0" style={{ color: SIGNAL }} />,
  warning: <AlertTriangle className="h-3.5 w-3.5 text-amber-400 flex-shrink-0" />,
  info: <Info className="h-3.5 w-3.5 text-indigo-400 flex-shrink-0" />,
};

const CustomTooltip = ({ active, payload, label }: { active?: boolean; payload?: { value: number; dataKey: string; color: string }[]; label?: string }) => {
  if (active && payload && payload.length) {
    return (
      <div className="rounded-xl border border-zinc-700 bg-zinc-900 p-3 shadow-xl text-xs">
        <p className="font-mono text-zinc-400 mb-2">{label}</p>
        {payload.map((p) => (
          <div key={p.dataKey} className="flex items-center gap-2">
            <span className="h-2 w-2 rounded-full flex-shrink-0" style={{ background: p.color }} />
            <span className="text-zinc-300">
              {p.dataKey === "revenue" ? formatCurrency(p.value) : `${p.value}%`}
            </span>
          </div>
        ))}
      </div>
    );
  }
  return null;
};

function KPICard({ kpi }: { kpi: KPI }) {
  const delta = kpi.deltaType;
  const accent = delta === "positive" ? "signal" : delta === "negative" ? "rose" : undefined;
  const sparkColor = delta === "positive" ? SIGNAL : delta === "negative" ? "#F43F5E" : "#6366F1";
  const sparkId = `spark-${kpi.id}`;

  return (
    <Card compact hover accent={accent as "signal" | "rose" | undefined} className="flex flex-col gap-3">
      {/* Label + inline icon */}
      <div className="flex items-center gap-1.5">
        <span
          className={cn(
            "h-3.5 w-3.5 flex-shrink-0",
            delta === "positive" ? "text-[#00C896]" : delta === "negative" ? "text-rose-400" : "text-zinc-600"
          )}
          aria-hidden="true"
        >
          {kpiIcons[kpi.icon]}
        </span>
        <p className="text-[11px] text-zinc-500 font-medium tracking-wide">{kpi.label}</p>
      </div>

      {/* Value */}
      <p className="text-[26px] font-bold text-zinc-100 font-mono tabular-nums leading-none">
        {kpi.value}
      </p>

      {/* Sparkline */}
      <div className="h-8 -mx-1">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={kpi.sparkData.map((v, i) => ({ v, i }))}>
            <defs>
              <linearGradient id={sparkId} x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor={sparkColor} stopOpacity={0.22} />
                <stop offset="95%" stopColor={sparkColor} stopOpacity={0} />
              </linearGradient>
            </defs>
            <Area
              type="monotone"
              dataKey="v"
              stroke={sparkColor}
              strokeWidth={1.5}
              fill={`url(#${sparkId})`}
              dot={false}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      {/* Delta row */}
      <div className="flex items-center gap-1.5">
        {delta === "positive" ? (
          <TrendingUp className="h-3 w-3 flex-shrink-0" style={{ color: SIGNAL }} aria-hidden="true" />
        ) : delta === "negative" ? (
          <TrendingDown className="h-3 w-3 text-rose-400 flex-shrink-0" aria-hidden="true" />
        ) : (
          <Minus className="h-3 w-3 text-zinc-600 flex-shrink-0" aria-hidden="true" />
        )}
        <span
          className={cn(
            "text-[10px] font-mono font-semibold",
            delta === "positive" ? "text-[#00C896]" : delta === "negative" ? "text-rose-400" : "text-zinc-500"
          )}
        >
          {kpi.delta}
        </span>
        <span className="text-[10px] text-zinc-700">vs last mo</span>
      </div>
    </Card>
  );
}

function PMKpiCard({
  icon,
  label,
  value,
  deltaLabel,
  deltaType = "neutral",
}: {
  icon: React.ReactNode;
  label: string;
  value: string | number;
  deltaLabel?: string;
  deltaType?: "positive" | "negative" | "warning" | "neutral";
}) {
  const deltaColor = {
    positive: "text-[#00C896]",
    negative: "text-rose-400",
    warning:  "text-amber-400",
    neutral:  "text-zinc-600",
  }[deltaType];

  return (
    <Card compact accent="violet" className="flex flex-col gap-2">
      <div className="flex items-center gap-3">
        <span className="flex-shrink-0 text-indigo-400" aria-hidden="true">{icon}</span>
        <div>
          <p className="text-xl font-bold font-mono tabular-nums text-zinc-100 leading-none">{value}</p>
          <p className="text-[11px] text-zinc-500 mt-1 font-medium">{label}</p>
        </div>
      </div>
      {deltaLabel && (
        <p className={cn("text-[10px] font-mono pl-7", deltaColor)}>{deltaLabel}</p>
      )}
    </Card>
  );
}

const DEMO_MODE = process.env.NEXT_PUBLIC_DEMO_MODE === "true";

function computeKPIs(deals: Deal[]): KPI[] {
  const won = deals.filter((d) => d.stage === "closed_won");
  const active = deals.filter((d) => d.stage !== "closed_won" && d.stage !== "closed_lost");
  const wonValue = won.reduce((s, d) => s + d.value, 0);
  const closed = won.length + deals.filter((d) => d.stage === "closed_lost").length;
  const winRate = closed > 0 ? Math.round((won.length / closed) * 100) : 0;
  const avgProb = active.length > 0
    ? Math.round(active.reduce((s, d) => s + (d.mlWinProbability ?? 50), 0) / active.length)
    : 0;

  return [
    {
      id: "k1", label: "Closed Won", icon: "dollar",
      value: wonValue >= 1000000 ? `$${(wonValue / 1000000).toFixed(1)}M` : `$${Math.round(wonValue / 1000)}K`,
      delta: `${won.length} deal${won.length !== 1 ? "s" : ""} closed`,
      deltaType: won.length > 0 ? "positive" : "neutral",
      sparkData: won.slice(-7).map((d) => d.value),
    },
    {
      id: "k2", label: "Active Deals", icon: "briefcase",
      value: String(active.length),
      delta: `${deals.length} total`,
      deltaType: "neutral",
      sparkData: [active.length],
    },
    {
      id: "k3", label: "Avg Win Probability", icon: "brain",
      value: `${avgProb}%`,
      delta: winRate > 0 ? `${winRate}% win rate` : "No closed deals",
      deltaType: winRate >= 50 ? "positive" : winRate > 0 ? "negative" : "neutral",
      sparkData: active.map((d) => d.mlWinProbability ?? 50),
    },
    {
      id: "k4", label: "Pipeline Value", icon: "barChart",
      value: (() => { const v = active.reduce((s, d) => s + d.value, 0); return v >= 1000000 ? `$${(v / 1000000).toFixed(1)}M` : `$${Math.round(v / 1000)}K`; })(),
      delta: `${active.length} open deal${active.length !== 1 ? "s" : ""}`,
      deltaType: "neutral",
      sparkData: active.map((d) => d.value),
    },
  ];
}

export default function DashboardPage() {
  const { deals } = useDeals();
  const [activeAgents, setActiveAgents] = useState<typeof mockAgents>([]);
  const [pmKpis, setPmKpis] = useState<PMKpis | null>(null);
  const [pmError, setPmError] = useState(false);
  const [workspaceMode, setWorkspaceMode] = useState<"sales" | "pm" | "both">("sales");
  const [staleDeals, setStaleDeals] = useState<StaleDeal[]>([]);
  const [overdueActions, setOverdueActions] = useState<OverdueAction[]>([]);
  const [liveActivity, setLiveActivity] = useState<ActivityEvent[]>([]);
  const [revenueHistory, setRevenueHistory] = useState<{ month: string; revenue: number }[]>([]);
  const [forecastData, setForecastData] = useState<{ month: string; value: number; deal_count: number }[]>([]);
  const [pollToken, setPollToken] = useState<string | null>(null);
  const [pollWorkspaceId, setPollWorkspaceId] = useState<string | null>(null);
  const [mounted, setMounted] = useState(false);
  const [digest, setDigest] = useState<string | null>(null);
  const [digestGeneratedAt, setDigestGeneratedAt] = useState<string | null>(null);
  const [digestLoading, setDigestLoading] = useState(false);
  const [contactHealthOverview, setContactHealthOverview] = useState<{
    at_risk_count: number;
    strong_count: number;
    summary_sentence: string;
    contacts: Array<{ id: string; name: string; health: 'strong' | 'neutral' | 'at_risk'; days_since_touch: number | null; top_action: string; engagement_score: number }>;
    generated_at: string;
  } | null>(null);
  const [contactHealthLoading, setContactHealthLoading] = useState(false);
  const [goalTracker, setGoalTracker] = useState<{
    goals: Array<{ name: string; target_description: string; progress_pct: number; status: 'on_track' | 'at_risk' | 'behind'; insight: string }>;
    overall_health: 'on_track' | 'at_risk' | 'behind';
    generated_at: string;
  } | null>(null);
  const [goalTrackerLoading, setGoalTrackerLoading] = useState(false);
  const [goalTrackerOpen, setGoalTrackerOpen] = useState(true);
  const [nextBestActions, setNextBestActions] = useState<{
    actions: Array<{
      rank: number;
      action_type: 'contact_outreach' | 'deal_followup' | 'task_complete' | 'deal_review';
      entity_id: string;
      entity_name: string;
      description: string;
      urgency: 'critical' | 'high' | 'medium' | 'low';
    }>;
    generated_at: string;
  } | null>(null);
  const [nbaLoading, setNbaLoading] = useState(false);
  const [nbaOpen, setNbaOpen] = useState(true);
  useEffect(() => setMounted(true), []);

  useEffect(() => {
    if (DEMO_MODE) {
      setWorkspaceMode("both");
      setPmKpis({
        tasksExtractedToday: demoDashboard.tasksExtractedToday,
        avgClarityScore: demoDashboard.avgClarityScore,
        openTasks: demoDashboard.openTasks,
        messagesIngested: demoDashboard.messagesIngested,
      });
      apiClient.getStaleDeals("demo-workspace-1", "demo-token").then((data) => {
        setStaleDeals(Array.isArray(data) ? data : []);
      }).catch(() => {});
      apiClient.getOverdueActions("demo-workspace-1", "demo-token").then((data) => {
        setOverdueActions(Array.isArray(data) ? data : []);
      }).catch(() => {});
      apiClient.getDealHistory("demo-workspace-1", "demo-token", 6).then((data) => {
        if (Array.isArray(data)) setRevenueHistory(data);
      }).catch(() => {});
      apiClient.getDealForecast("demo-workspace-1", "demo-token", 6).then((data) => {
        if (Array.isArray(data)) setForecastData(data);
      }).catch(() => {});
      setDigestLoading(true);
      apiClient.getWorkspaceDigest("demo-workspace-1", "demo-token").then((data) => {
        setDigest(data.digest);
        setDigestGeneratedAt(data.generated_at);
      }).catch(() => {}).finally(() => setDigestLoading(false));
      setContactHealthLoading(true);
      apiClient.getContactHealthOverview("demo-workspace-1", "demo-token").then((data) => {
        setContactHealthOverview(data);
      }).catch(() => {}).finally(() => setContactHealthLoading(false));
      setGoalTrackerLoading(true);
      apiClient.getWorkspaceGoalTracker("demo-workspace-1", "demo-token").then((data) => {
        setGoalTracker(data);
      }).catch(() => {}).finally(() => setGoalTrackerLoading(false));
      setNbaLoading(true);
      apiClient.getWorkspaceNextBestActions("demo-workspace-1", "demo-token").then((data) => {
        setNextBestActions(data);
      }).catch(() => {}).finally(() => setNbaLoading(false));
      return;
    }

    const supabase = createBrowserClient();
    let realtimeChannelRef: ReturnType<typeof supabase.channel> | null = null;
    supabase.auth.getSession().then(async ({ data: { session } }) => {
      if (!session) return;
      const workspaceId: string | undefined = (session.user.app_metadata?.workspace_id ?? session.user.user_metadata?.workspace_id);
      setPollToken(session.access_token);
      if (workspaceId) setPollWorkspaceId(workspaceId);

      // Seed activity feed with recent events, then subscribe to Realtime
      if (workspaceId) {
        apiClient.listActivity(workspaceId, session.access_token, { limit: 20 })
          .then((data) => {
            if (!Array.isArray(data)) return;
            setLiveActivity(data.map((e) => ({
              id: e.id,
              type: e.type as ActivityEvent["type"],
              agentName: e.agent_name ?? "",
              description: e.description ?? "",
              meta: e.meta ?? "",
              severity: e.severity as ActivityEvent["severity"],
              timestamp: (() => {
                const diff = Date.now() - new Date(e.created_at).getTime();
                const mins = Math.floor(diff / 60000);
                if (mins < 1) return "Just now";
                if (mins < 60) return `${mins}m ago`;
                const hrs = Math.floor(mins / 60);
                if (hrs < 24) return `${hrs}h ago`;
                return `${Math.floor(hrs / 24)}d ago`;
              })(),
            })));
          })
          .catch(() => {});
      }

      // Fetch workspace mode
      if (workspaceId) {
        apiClient.getWorkspace(workspaceId, session.access_token)
          .then((ws: { mode?: string }) => { if (ws?.mode) setWorkspaceMode(ws.mode as "sales" | "pm" | "both"); })
          .catch(() => {});
      }

      if (!workspaceId) return;

      // Fetch revenue history + forecast + initial digest
      apiClient.getDealHistory(workspaceId, session.access_token, 6)
        .then((data) => { if (Array.isArray(data)) setRevenueHistory(data); })
        .catch(() => {});
      apiClient.getDealForecast(workspaceId, session.access_token, 6)
        .then((data) => { if (Array.isArray(data)) setForecastData(data); })
        .catch(() => {});
      setDigestLoading(true);
      apiClient.getWorkspaceDigest(workspaceId, session.access_token)
        .then((data) => { setDigest(data.digest); setDigestGeneratedAt(data.generated_at); })
        .catch(() => {})
        .finally(() => setDigestLoading(false));
      setContactHealthLoading(true);
      apiClient.getContactHealthOverview(workspaceId, session.access_token)
        .then((data) => { setContactHealthOverview(data); })
        .catch(() => {})
        .finally(() => setContactHealthLoading(false));
      setGoalTrackerLoading(true);
      apiClient.getWorkspaceGoalTracker(workspaceId, session.access_token)
        .then((data) => { setGoalTracker(data); })
        .catch(() => {})
        .finally(() => setGoalTrackerLoading(false));
      setNbaLoading(true);
      apiClient.getWorkspaceNextBestActions(workspaceId, session.access_token)
        .then((data) => { setNextBestActions(data); })
        .catch(() => {})
        .finally(() => setNbaLoading(false));

      // Subscribe to Supabase Realtime for live activity feed
      const channel = supabase
        .channel(`activity-feed:${workspaceId}`)
        .on(
          "postgres_changes" as Parameters<ReturnType<typeof supabase.channel>["on"]>[0],
          {
            event: "INSERT",
            schema: "public",
            table: "activity_events",
            filter: `workspace_id=eq.${workspaceId}`,
          },
          (payload: { new: Record<string, unknown> }) => {
            const ev = payload.new as { id: string; type: string; agent_name: string; description: string; meta?: string; severity: string };
            const mapped: ActivityEvent = {
              id: ev.id,
              type: ev.type as ActivityEvent["type"],
              agentName: ev.agent_name,
              description: ev.description,
              meta: ev.meta,
              severity: ev.severity as ActivityEvent["severity"],
              timestamp: "Just now",
            };
            setLiveActivity((prev) => [mapped, ...prev].slice(0, 50));
          }
        )
        .subscribe();
      realtimeChannelRef = channel;

      // Fetch PM aggregate KPIs + stale deals in parallel. Use allSettled so one
      // failing endpoint surfaces a "some metrics unavailable" notice instead of
      // silently zeroing the affected KPI.
      try {
        const [tasksResult, messagesResult, staleResult, overdueResult] = await Promise.allSettled([
          apiClient.getTasks(workspaceId, session.access_token),
          apiClient.getMessages(workspaceId, session.access_token),
          apiClient.getStaleDeals(workspaceId, session.access_token),
          apiClient.getOverdueActions(workspaceId, session.access_token),
        ]);

        const anyFailed =
          tasksResult.status === "rejected" ||
          messagesResult.status === "rejected" ||
          staleResult.status === "rejected";
        setPmError(anyFailed);

        const tasksData = tasksResult.status === "fulfilled" ? tasksResult.value : [];
        const messagesData = messagesResult.status === "fulfilled" ? messagesResult.value : [];
        const staleData = staleResult.status === "fulfilled" ? staleResult.value : [];

        const today = new Date().toISOString().slice(0, 10);
        const tasks: Array<{ status: string; created_at?: string; clarity_score?: { score: number } | null }> =
          Array.isArray(tasksData) ? tasksData : [];
        const messages: Array<unknown> = Array.isArray(messagesData) ? messagesData : [];

        const tasksExtractedToday = tasks.filter(
          (t) => t.created_at?.startsWith(today)
        ).length;
        const openTasks = tasks.filter((t) => t.status === "open").length;
        const scoredTasks = tasks.filter((t) => t.clarity_score?.score != null);
        const avgClarityScore =
          scoredTasks.length > 0
            ? Math.round(
                scoredTasks.reduce((s, t) => s + (t.clarity_score?.score ?? 0), 0) /
                  scoredTasks.length
              )
            : null;

        setPmKpis({
          tasksExtractedToday,
          avgClarityScore,
          openTasks,
          messagesIngested: messages.length,
        });
        setStaleDeals(Array.isArray(staleData) ? staleData : []);

        const overdueData = overdueResult.status === "fulfilled" ? overdueResult.value : [];
        setOverdueActions(Array.isArray(overdueData) ? overdueData : []);
      } catch {
        // Total failure of the PM block — still render sales KPIs, but flag it.
        setPmError(true);
      }
    });
    return () => {
      if (realtimeChannelRef) supabase.removeChannel(realtimeChannelRef);
    };
  }, []);

  // 30s polling for stale deal health (live mode only)
  useEffect(() => {
    if (DEMO_MODE || !pollWorkspaceId || !pollToken) return;
    const id = setInterval(() => {
      apiClient.getStaleDeals(pollWorkspaceId, pollToken).then((data) => {
        setStaleDeals(Array.isArray(data) ? data : []);
      }).catch(() => {});
    }, 30_000);
    return () => clearInterval(id);
  }, [pollWorkspaceId, pollToken]);

  async function regenerateDigest() {
    if (digestLoading) return;
    setDigestLoading(true);
    try {
      if (DEMO_MODE) {
        const data = await apiClient.getWorkspaceDigest("demo-workspace-1", "demo-token");
        setDigest(data.digest);
        setDigestGeneratedAt(data.generated_at);
      } else {
        const supabase = createBrowserClient();
        const { data: { session } } = await supabase.auth.getSession();
        if (!session) return;
        const workspaceId: string | undefined = session.user.app_metadata?.workspace_id ?? session.user.user_metadata?.workspace_id;
        if (!workspaceId) return;
        const data = await apiClient.getWorkspaceDigest(workspaceId, session.access_token);
        setDigest(data.digest);
        setDigestGeneratedAt(data.generated_at);
      }
    } catch { /* silently ignore */ } finally {
      setDigestLoading(false);
    }
  }

  async function regenerateGoalTracker() {
    if (goalTrackerLoading) return;
    setGoalTrackerLoading(true);
    try {
      if (DEMO_MODE) {
        const data = await apiClient.getWorkspaceGoalTracker("demo-workspace-1", "demo-token");
        setGoalTracker(data);
      } else {
        const supabase = createBrowserClient();
        const { data: { session } } = await supabase.auth.getSession();
        if (!session) return;
        const workspaceId: string | undefined = session.user.app_metadata?.workspace_id ?? session.user.user_metadata?.workspace_id;
        if (!workspaceId) return;
        const data = await apiClient.getWorkspaceGoalTracker(workspaceId, session.access_token);
        setGoalTracker(data);
      }
    } catch { /* silently ignore */ } finally {
      setGoalTrackerLoading(false);
    }
  }

  async function regenerateNextBestActions() {
    if (nbaLoading) return;
    setNbaLoading(true);
    try {
      if (DEMO_MODE) {
        const data = await apiClient.getWorkspaceNextBestActions("demo-workspace-1", "demo-token");
        setNextBestActions(data);
      } else {
        const supabase = createBrowserClient();
        const { data: { session } } = await supabase.auth.getSession();
        if (!session) return;
        const workspaceId: string | undefined = session.user.app_metadata?.workspace_id ?? session.user.user_metadata?.workspace_id;
        if (!workspaceId) return;
        const data = await apiClient.getWorkspaceNextBestActions(workspaceId, session.access_token);
        setNextBestActions(data);
      }
    } catch { /* silently ignore */ } finally {
      setNbaLoading(false);
    }
  }

  function renderDigestMarkdown(text: string) {
    return text.split("\n").map((line, i) => {
      if (line.startsWith("**") && line.endsWith("**")) {
        return (
          <p key={i} className="text-xs font-semibold text-zinc-300 mt-3 first:mt-0">
            {line.replace(/\*\*/g, "")}
          </p>
        );
      }
      if (line.startsWith("- ")) {
        return (
          <p key={i} className="text-xs text-zinc-400 pl-3 mt-1 leading-relaxed">
            <span className="text-indigo-500 mr-1.5">•</span>{line.slice(2)}
          </p>
        );
      }
      return line ? <p key={i} className="text-xs text-zinc-400 mt-1">{line}</p> : null;
    });
  }

  return (
    <div className="flex flex-col gap-6 p-4 md:p-6">
      <Header
        title="Dashboard"
        subtitle={`Real-time overview · ${activeAgents.length} agents active`}
      />

      {/* KPI Grid */}
      <section aria-labelledby="kpi-heading">
        <h2 id="kpi-heading" className="sr-only">Key Performance Indicators</h2>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {computeKPIs(deals).map((kpi) => (
            <KPICard key={kpi.id} kpi={kpi} />
          ))}
        </div>
      </section>

      {/* PM KPI Cards — only visible in pm or both modes */}
      {(workspaceMode === "pm" || workspaceMode === "both") && (pmKpis || pmError) && (
        <section aria-labelledby="pm-kpi-heading">
          <div className="flex items-center gap-2 mb-3">
            <h2 id="pm-kpi-heading" className="text-xs font-semibold text-zinc-400 uppercase tracking-widest font-mono">
              PM Intelligence
            </h2>
            <Badge variant="indigo" size="sm" dot>Live</Badge>
            {pmError && (
              <span className="flex items-center gap-1.5 text-[11px] text-amber-400">
                <AlertTriangle className="h-3 w-3 flex-shrink-0" aria-hidden="true" />
                Some metrics unavailable
              </span>
            )}
          </div>
          {pmKpis && (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <PMKpiCard
              icon={<ListTodo className="h-4 w-4" />}
              label="Tasks Extracted Today"
              value={pmKpis.tasksExtractedToday}
              deltaLabel="Extracted today"
              deltaType="neutral"
            />
            <PMKpiCard
              icon={<BarChart2 className="h-4 w-4" />}
              label="Avg Clarity Score"
              value={pmKpis.avgClarityScore !== null ? pmKpis.avgClarityScore : "—"}
              deltaLabel={
                pmKpis.avgClarityScore === null ? undefined
                  : pmKpis.avgClarityScore >= 70 ? "High clarity"
                  : pmKpis.avgClarityScore >= 40 ? "Needs review"
                  : "Low clarity"
              }
              deltaType={
                pmKpis.avgClarityScore === null ? "neutral"
                  : pmKpis.avgClarityScore >= 70 ? "positive"
                  : pmKpis.avgClarityScore >= 40 ? "warning"
                  : "negative"
              }
            />
            <PMKpiCard
              icon={<CheckSquare className="h-4 w-4" />}
              label="Open Tasks"
              value={pmKpis.openTasks}
              deltaLabel={pmKpis.openTasks === 0 ? "All clear" : "Need attention"}
              deltaType={pmKpis.openTasks === 0 ? "positive" : pmKpis.openTasks > 10 ? "warning" : "neutral"}
            />
            <PMKpiCard
              icon={<Mail className="h-4 w-4" />}
              label="Messages Ingested"
              value={pmKpis.messagesIngested}
              deltaLabel="Total processed"
              deltaType="neutral"
            />
          </div>
          )}
        </section>
      )}

      {/* AI Weekly Digest */}
      {(digest !== null || digestLoading) && (
        <section aria-labelledby="digest-heading">
          <div className="flex items-center gap-2 mb-3">
            <h2 id="digest-heading" className="text-xs font-semibold text-zinc-400 uppercase tracking-widest font-mono">
              Weekly Digest
            </h2>
            <Badge variant="indigo" size="sm" dot>Nova AI</Badge>
            {digestGeneratedAt && (
              <span className="text-[11px] text-zinc-600 font-mono ml-auto">
                {new Date(digestGeneratedAt).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}
              </span>
            )}
          </div>
          <Card className="relative">
            {/* Regenerate button */}
            <button
              onClick={regenerateDigest}
              disabled={digestLoading}
              className="absolute top-3 right-3 flex items-center gap-1.5 rounded-lg border border-zinc-700 bg-zinc-800 px-2.5 py-1.5 text-[11px] text-zinc-400 hover:text-indigo-400 hover:border-indigo-500/40 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              title="Regenerate digest"
            >
              <RefreshCw className={cn("h-3 w-3", digestLoading && "animate-spin")} />
              {digestLoading ? "Generating…" : "Regenerate"}
            </button>

            {/* Digest header */}
            <div className="flex items-center gap-2 mb-4 pr-28">
              <Sparkles className="h-4 w-4 text-indigo-400 flex-shrink-0" aria-hidden />
              <p className="text-sm font-semibold text-zinc-100">AI Workspace Summary</p>
            </div>

            {digestLoading && !digest ? (
              <div className="space-y-2 animate-pulse">
                <div className="h-3 bg-zinc-800 rounded w-1/3" />
                <div className="h-3 bg-zinc-800 rounded w-full" />
                <div className="h-3 bg-zinc-800 rounded w-5/6" />
                <div className="h-3 bg-zinc-800 rounded w-1/3 mt-3" />
                <div className="h-3 bg-zinc-800 rounded w-full" />
                <div className="h-3 bg-zinc-800 rounded w-4/5" />
              </div>
            ) : digest ? (
              <div className={cn("transition-opacity", digestLoading && "opacity-50")}>
                {renderDigestMarkdown(digest)}
              </div>
            ) : null}
          </Card>
        </section>
      )}

      {/* Contact Health Overview */}
      {(contactHealthOverview !== null || contactHealthLoading) && (
        <section aria-labelledby="contact-health-heading">
          <div className="flex items-center gap-2 mb-3">
            <h2 id="contact-health-heading" className="text-xs font-semibold text-zinc-400 uppercase tracking-widest font-mono">
              Contact Health
            </h2>
            <Badge variant="indigo" size="sm" dot>Nova AI</Badge>
            {contactHealthOverview && (
              <>
                {contactHealthOverview.at_risk_count > 0 && (
                  <Badge variant="rose" size="sm" dot>{contactHealthOverview.at_risk_count} at risk</Badge>
                )}
                {contactHealthOverview.strong_count > 0 && (
                  <Badge variant="emerald" size="sm" dot>{contactHealthOverview.strong_count} strong</Badge>
                )}
              </>
            )}
          </div>
          <Card className="p-0 overflow-hidden">
            {contactHealthLoading && !contactHealthOverview ? (
              <div className="space-y-2 animate-pulse p-4">
                <div className="h-3 bg-zinc-800 rounded w-2/3" />
                <div className="h-3 bg-zinc-800 rounded w-full" />
                <div className="h-3 bg-zinc-800 rounded w-1/2" />
              </div>
            ) : contactHealthOverview ? (
              <div className={cn("transition-opacity", contactHealthLoading && "opacity-50")}>
                {/* Summary sentence */}
                <div className="flex items-start gap-2 px-4 pt-4 pb-3 border-b border-zinc-800">
                  <Sparkles className="h-4 w-4 text-indigo-400 flex-shrink-0 mt-0.5" aria-hidden />
                  <p className="text-sm text-zinc-300">{contactHealthOverview.summary_sentence}</p>
                </div>
                {/* Contact rows */}
                <div className="divide-y divide-zinc-800/60">
                  {contactHealthOverview.contacts.map((c) => (
                    <div key={c.id} className="flex items-center gap-3 px-4 py-2.5 hover:bg-zinc-800/40 transition-colors">
                      {/* Health dot */}
                      <span
                        className={cn(
                          "h-2 w-2 rounded-full flex-shrink-0",
                          c.health === "strong" && "bg-emerald-400",
                          c.health === "neutral" && "bg-amber-400",
                          c.health === "at_risk" && "bg-rose-500",
                        )}
                        title={c.health.replace("_", " ")}
                      />
                      {/* Name + action */}
                      <div className="flex-1 min-w-0">
                        <Link
                          href={`/contacts/${c.id}`}
                          className="text-sm font-medium text-zinc-100 hover:text-indigo-400 transition-colors truncate block"
                        >
                          {c.name}
                        </Link>
                        <p className="text-[11px] text-zinc-500 truncate">{c.top_action}</p>
                      </div>
                      {/* Days since touch */}
                      <div className="flex-shrink-0 text-right hidden sm:block">
                        {c.days_since_touch !== null ? (
                          <span className={cn(
                            "text-xs font-mono",
                            c.days_since_touch > 30 ? "text-rose-400" : c.days_since_touch > 14 ? "text-amber-400" : "text-zinc-400",
                          )}>
                            {c.days_since_touch}d ago
                          </span>
                        ) : (
                          <span className="text-xs font-mono text-zinc-600">no touch</span>
                        )}
                      </div>
                      {/* Engagement score */}
                      <div className="flex items-center gap-1.5 flex-shrink-0 w-16 hidden lg:flex">
                        <div className="flex-1 h-1.5 rounded-full bg-zinc-800 overflow-hidden">
                          <div
                            className={cn(
                              "h-full rounded-full",
                              c.engagement_score >= 60 ? "bg-emerald-400" : c.engagement_score >= 40 ? "bg-amber-400" : "bg-rose-500",
                            )}
                            style={{ width: `${c.engagement_score}%` }}
                          />
                        </div>
                        <span className="text-[10px] font-mono text-zinc-500 w-5 text-right">{c.engagement_score}</span>
                      </div>
                      {/* Link */}
                      <Link
                        href={`/contacts/${c.id}`}
                        className="flex-shrink-0 text-zinc-600 hover:text-indigo-400 transition-colors"
                        title="View contact"
                      >
                        <ExternalLink className="h-3 w-3" />
                      </Link>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
          </Card>
        </section>
      )}

      {/* AI Goal Tracker */}
      {(goalTracker !== null || goalTrackerLoading) && (
        <section aria-labelledby="goal-tracker-heading">
          <div className="flex items-center gap-2 mb-3">
            <h2 id="goal-tracker-heading" className="text-xs font-semibold text-zinc-400 uppercase tracking-widest font-mono">
              Workspace Goals
            </h2>
            <Badge variant="indigo" size="sm" dot>Nova AI</Badge>
            {goalTracker && (
              <Badge
                variant={goalTracker.overall_health === "on_track" ? "emerald" : goalTracker.overall_health === "at_risk" ? "amber" : "rose"}
                size="sm"
              >
                {goalTracker.overall_health.replace("_", " ")}
              </Badge>
            )}
            {goalTracker && (
              <span className="text-[11px] text-zinc-600 font-mono ml-auto">
                {new Date(goalTracker.generated_at).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}
              </span>
            )}
          </div>
          <Card className="relative">
            <div className="flex items-center gap-2 mb-4 pr-40">
              <Target className="h-4 w-4 text-indigo-400 flex-shrink-0" aria-hidden />
              <p className="text-sm font-semibold text-zinc-100">Goal Progress Tracker</p>
            </div>
            <div className="absolute top-3 right-3 flex items-center gap-2">
              <button
                onClick={regenerateGoalTracker}
                disabled={goalTrackerLoading}
                className="flex items-center gap-1.5 rounded-lg border border-zinc-700 bg-zinc-800 px-2.5 py-1.5 text-[11px] text-zinc-400 hover:text-indigo-400 hover:border-indigo-500/40 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                title="Regenerate goals"
              >
                <RefreshCw className={cn("h-3 w-3", goalTrackerLoading && "animate-spin")} />
                {goalTrackerLoading ? "Generating…" : "Regenerate"}
              </button>
              <button
                onClick={() => setGoalTrackerOpen((o) => !o)}
                className="flex items-center gap-1 rounded-lg border border-zinc-700 bg-zinc-800 px-2 py-1.5 text-zinc-400 hover:text-zinc-200 transition-colors"
                title={goalTrackerOpen ? "Collapse" : "Expand"}
              >
                <ChevronDown className={cn("h-3.5 w-3.5 transition-transform", !goalTrackerOpen && "-rotate-90")} />
              </button>
            </div>
            {goalTrackerOpen && (
              <>
                {goalTrackerLoading && !goalTracker ? (
                  <div className="space-y-3 animate-pulse">
                    {[1, 2, 3, 4].map((i) => (
                      <div key={i} className="space-y-1.5">
                        <div className="h-2.5 bg-zinc-800 rounded w-1/4" />
                        <div className="h-1.5 bg-zinc-800 rounded w-full" />
                        <div className="h-2 bg-zinc-800 rounded w-2/3" />
                      </div>
                    ))}
                  </div>
                ) : goalTracker ? (
                  <div className={cn("space-y-4 transition-opacity", goalTrackerLoading && "opacity-50")}>
                    {goalTracker.goals.map((goal, idx) => (
                      <div key={idx} className="space-y-1.5">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-medium text-zinc-100">{goal.name}</span>
                          <span className={cn(
                            "px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wide flex-shrink-0",
                            goal.status === "on_track" && "bg-emerald-400/10 text-emerald-400",
                            goal.status === "at_risk" && "bg-amber-400/10 text-amber-400",
                            goal.status === "behind" && "bg-rose-400/10 text-rose-400",
                          )}>
                            {goal.status.replace("_", " ")}
                          </span>
                          <span className="text-xs font-mono text-zinc-400 ml-auto">{goal.progress_pct}%</span>
                        </div>
                        <div className="h-1.5 rounded-full bg-zinc-800 overflow-hidden">
                          <div
                            className={cn(
                              "h-full rounded-full transition-all",
                              goal.status === "on_track" && "bg-emerald-400",
                              goal.status === "at_risk" && "bg-amber-400",
                              goal.status === "behind" && "bg-rose-500",
                            )}
                            style={{ width: `${goal.progress_pct}%` }}
                          />
                        </div>
                        <p className="text-[11px] text-zinc-500 leading-relaxed">{goal.insight}</p>
                      </div>
                    ))}
                  </div>
                ) : null}
              </>
            )}
          </Card>
        </section>
      )}

      {/* AI Next Best Actions */}
      {(nextBestActions !== null || nbaLoading) && (
        <section aria-labelledby="nba-heading">
          <div className="flex items-center gap-2 mb-3">
            <h2 id="nba-heading" className="text-xs font-semibold text-zinc-400 uppercase tracking-widest font-mono">
              Today&apos;s Priorities
            </h2>
            <Badge variant="indigo" size="sm" dot>Nova AI</Badge>
            {nextBestActions && (
              <span className="text-[11px] text-zinc-600 font-mono ml-auto">
                {new Date(nextBestActions.generated_at).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}
              </span>
            )}
          </div>
          <Card className="relative">
            <div className="flex items-center gap-2 mb-4 pr-40">
              <Zap className="h-4 w-4 text-violet-400 flex-shrink-0" aria-hidden />
              <p className="text-sm font-semibold text-zinc-100">Next Best Actions</p>
            </div>
            <div className="absolute top-3 right-3 flex items-center gap-2">
              <button
                onClick={regenerateNextBestActions}
                disabled={nbaLoading}
                className="flex items-center gap-1.5 rounded-lg border border-zinc-700 bg-zinc-800 px-2.5 py-1.5 text-[11px] text-zinc-400 hover:text-violet-400 hover:border-violet-500/40 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                title="Regenerate actions"
              >
                <RefreshCw className={cn("h-3 w-3", nbaLoading && "animate-spin")} />
                {nbaLoading ? "Generating…" : "Regenerate"}
              </button>
              <button
                onClick={() => setNbaOpen((o) => !o)}
                className="flex items-center gap-1 rounded-lg border border-zinc-700 bg-zinc-800 px-2 py-1.5 text-zinc-400 hover:text-zinc-200 transition-colors"
                title={nbaOpen ? "Collapse" : "Expand"}
              >
                <ChevronDown className={cn("h-3.5 w-3.5 transition-transform", !nbaOpen && "-rotate-90")} />
              </button>
            </div>
            {nbaOpen && (
              <>
                {nbaLoading && !nextBestActions ? (
                  <div className="space-y-3 animate-pulse">
                    {[1, 2, 3].map((i) => (
                      <div key={i} className="flex items-start gap-3">
                        <div className="h-5 w-5 rounded-full bg-zinc-800 flex-shrink-0 mt-0.5" />
                        <div className="flex-1 space-y-1.5">
                          <div className="h-2.5 bg-zinc-800 rounded w-1/3" />
                          <div className="h-2 bg-zinc-800 rounded w-full" />
                        </div>
                      </div>
                    ))}
                  </div>
                ) : nextBestActions ? (
                  <div className={cn("space-y-3 transition-opacity", nbaLoading && "opacity-50")}>
                    {nextBestActions.actions.map((action) => {
                      const urgencyColor = {
                        critical: "bg-rose-400/10 text-rose-400 border-rose-500/20",
                        high: "bg-amber-400/10 text-amber-400 border-amber-500/20",
                        medium: "bg-indigo-400/10 text-indigo-400 border-indigo-500/20",
                        low: "bg-zinc-400/10 text-zinc-400 border-zinc-600/20",
                      }[action.urgency];
                      const typeIcon = {
                        contact_outreach: <Phone className="h-3 w-3" />,
                        deal_followup: <Mail className="h-3 w-3" />,
                        task_complete: <CheckSquare className="h-3 w-3" />,
                        deal_review: <Calendar className="h-3 w-3" />,
                      }[action.action_type];
                      const entityPath = action.action_type === 'contact_outreach'
                        ? `/contacts/${action.entity_id}`
                        : action.action_type === 'task_complete'
                        ? `/tasks`
                        : `/pipeline/${action.entity_id}`;
                      return (
                        <div key={action.rank} className="flex items-start gap-3 group">
                          <span className={cn(
                            "mt-0.5 flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-full border text-[10px] font-bold",
                            urgencyColor,
                          )}>
                            {action.rank}
                          </span>
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 flex-wrap">
                              <span className={cn("flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded border", urgencyColor)}>
                                {typeIcon}
                                {action.urgency}
                              </span>
                              <Link
                                href={entityPath}
                                className="text-xs font-medium text-zinc-200 hover:text-violet-400 truncate transition-colors max-w-[200px]"
                              >
                                {action.entity_name}
                              </Link>
                              <ExternalLink className="h-3 w-3 text-zinc-600 opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0" />
                            </div>
                            <p className="text-[11px] text-zinc-500 mt-1 leading-relaxed">{action.description}</p>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                ) : null}
              </>
            )}
          </Card>
        </section>
      )}

      {/* Deal Health Alerts — only show when stale deals exist */}
      {staleDeals.length > 0 && (
        <section aria-labelledby="health-heading">
          <div className="flex items-center gap-2 mb-3">
            <h2 id="health-heading" className="text-xs font-semibold text-zinc-400 uppercase tracking-widest font-mono">
              Deal Health Alerts
            </h2>
            <Badge variant="rose" size="sm" dot>{staleDeals.length} at risk</Badge>
          </div>
          <Card className="border-rose-500/10 overflow-hidden p-0">
            <div className="divide-y divide-zinc-800">
              {staleDeals.slice(0, 3).map((deal) => (
                <div key={deal.id} className="flex items-center gap-4 px-4 py-3 hover:bg-zinc-800/40 transition-colors">
                  {/* Health bar */}
                  <div className="flex items-center gap-2 w-28 flex-shrink-0">
                    <div className="flex-1 h-1.5 rounded-full bg-zinc-800 overflow-hidden">
                      <div
                        className={cn(
                          "h-full rounded-full",
                          deal.health_score >= 40 ? "bg-amber-400" : "bg-rose-500"
                        )}
                        style={{ width: `${deal.health_score}%` }}
                      />
                    </div>
                    <span className={cn(
                      "text-xs font-mono font-bold w-6 text-right flex-shrink-0",
                      deal.health_score >= 40 ? "text-amber-400" : "text-rose-400"
                    )}>
                      {deal.health_score}
                    </span>
                  </div>

                  {/* Deal info */}
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-zinc-100 truncate">{deal.title}</p>
                    <p className="text-xs text-zinc-500 truncate">{deal.company}</p>
                  </div>

                  {/* Stage + value */}
                  <div className="text-right flex-shrink-0 hidden sm:block">
                    <p className="text-xs text-zinc-400 capitalize">{deal.stage.replace("_", " ")}</p>
                    <p className="text-xs font-mono text-zinc-300">${(deal.value / 1000).toFixed(0)}K</p>
                  </div>

                  {/* Top signal */}
                  <div className="hidden lg:flex items-center gap-1.5 flex-shrink-0 max-w-xs">
                    <AlertTriangle className="h-3 w-3 text-rose-400 flex-shrink-0" />
                    <span className="text-[11px] text-zinc-500 truncate">{deal.signals[0]}</span>
                  </div>

                  {/* View link */}
                  <Link
                    href="/pipeline"
                    className="flex-shrink-0 flex items-center gap-1 text-[11px] text-zinc-500 hover:text-indigo-400 transition-colors font-mono"
                    title="View in pipeline"
                  >
                    <ExternalLink className="h-3 w-3" />
                    View
                  </Link>
                </div>
              ))}
            </div>
            {staleDeals.length > 3 && (
              <div className="border-t border-zinc-800 px-4 py-2.5 text-center">
                <Link href="/pipeline" className="text-xs text-zinc-500 hover:text-indigo-400 transition-colors font-mono">
                  +{staleDeals.length - 3} more at-risk deals · View all in Pipeline →
                </Link>
              </div>
            )}
          </Card>
        </section>
      )}

      {/* Overdue Next Actions Widget */}
      {overdueActions.length > 0 && (
        <section aria-labelledby="overdue-heading">
          <div className="flex items-center gap-2 mb-3">
            <h2 id="overdue-heading" className="text-xs font-semibold text-zinc-400 uppercase tracking-widest font-mono">
              Overdue Actions
            </h2>
            <Badge variant="amber" size="sm" dot>{overdueActions.length} overdue</Badge>
          </div>
          <Card className="border-amber-500/10 overflow-hidden p-0">
            <div className="divide-y divide-zinc-800">
              {overdueActions.slice(0, 5).map((item) => (
                <div key={item.id} className="flex items-center gap-4 px-4 py-3 hover:bg-zinc-800/40 transition-colors">
                  <Bell className="h-3.5 w-3.5 text-amber-400 flex-shrink-0" aria-hidden />

                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-zinc-100 truncate">{item.title}</p>
                    {item.next_action && (
                      <p className="text-xs text-amber-200/60 truncate">{item.next_action}</p>
                    )}
                  </div>

                  <div className="text-right flex-shrink-0 hidden sm:block">
                    <p className={cn(
                      "text-xs font-mono font-semibold",
                      item.days_overdue >= 3 ? "text-rose-400" : "text-amber-400"
                    )}>
                      {item.days_overdue === 0 ? "Due today" : `${item.days_overdue}d overdue`}
                    </p>
                    <p className="text-[11px] text-zinc-500 capitalize">{item.stage.replace("_", " ")}</p>
                  </div>

                  <Link
                    href={`/pipeline/${item.id}`}
                    className="flex-shrink-0 flex items-center gap-1 text-[11px] text-zinc-500 hover:text-amber-400 transition-colors font-mono"
                    title="Open deal"
                  >
                    <ExternalLink className="h-3 w-3" />
                    View
                  </Link>
                </div>
              ))}
            </div>
            {overdueActions.length > 5 && (
              <div className="border-t border-zinc-800 px-4 py-2.5 text-center">
                <Link href="/pipeline" className="text-xs text-zinc-500 hover:text-amber-400 transition-colors font-mono">
                  +{overdueActions.length - 5} more overdue · View all in Pipeline →
                </Link>
              </div>
            )}
          </Card>
        </section>
      )}

      {/* Deal Forecast Widget */}
      {forecastData.length > 0 && (
        <section aria-labelledby="forecast-heading">
          <div className="flex items-center gap-2 mb-3">
            <h2 id="forecast-heading" className="text-xs font-semibold text-zinc-400 uppercase tracking-widest font-mono">
              Pipeline Forecast
            </h2>
            <Badge variant="indigo" size="sm">next 6 months</Badge>
          </div>
          <Card>
            <div className="flex items-center justify-between mb-4">
              <div>
                <p className="text-sm font-semibold text-zinc-100">Expected Deal Closings</p>
                <p className="text-xs text-zinc-500 mt-0.5 font-mono">
                  Grouped by expected_close · {forecastData.reduce((s, d) => s + d.deal_count, 0)} open deals
                </p>
              </div>
              <p className="text-sm font-mono font-bold text-indigo-400">
                ${(forecastData.reduce((s, d) => s + d.value, 0) / 1000).toFixed(0)}K total
              </p>
            </div>
            <div className="h-48">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={forecastData} margin={{ top: 4, right: 8, bottom: 0, left: 0 }} barSize={28}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#27272A" vertical={false} />
                  <XAxis dataKey="month" tick={{ fill: "#71717A", fontSize: 11 }} axisLine={false} tickLine={false} />
                  <YAxis
                    tick={{ fill: "#71717A", fontSize: 11 }}
                    axisLine={false}
                    tickLine={false}
                    tickFormatter={(v) => v >= 1000 ? `$${(v / 1000).toFixed(0)}K` : `$${v}`}
                    width={44}
                  />
                  <Tooltip
                    content={({ active, payload, label }) => {
                      if (!active || !payload?.length) return null;
                      const d = payload[0];
                      return (
                        <div className="rounded-xl border border-zinc-700 bg-zinc-900 p-3 shadow-xl text-xs space-y-1">
                          <p className="font-mono text-zinc-400">{label}</p>
                          <p className="text-zinc-200">
                            <span className="text-indigo-400 font-bold">${((d.value as number) / 1000).toFixed(0)}K</span>
                            {" "}expected
                          </p>
                          <p className="text-zinc-500">
                            {payload[0]?.payload?.deal_count ?? 0} deal{payload[0]?.payload?.deal_count !== 1 ? "s" : ""}
                          </p>
                        </div>
                      );
                    }}
                  />
                  <Bar dataKey="value" radius={[4, 4, 0, 0]}>
                    {forecastData.map((entry, i) => (
                      <Cell
                        key={entry.month}
                        fill={entry.deal_count === 0 ? "#27272A" : i === 0 ? "#6366F1" : `rgba(99,102,241,${0.9 - i * 0.12})`}
                      />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </Card>
        </section>
      )}

      {/* Charts Row */}
      <section aria-labelledby="charts-heading" className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <h2 id="charts-heading" className="sr-only">Analytics Charts</h2>

        {/* Revenue chart — 2/3 width */}
        <Card className="lg:col-span-2">
          <div className="flex items-center justify-between mb-4">
            <div>
              <p className="text-sm font-semibold text-zinc-100">Revenue Pipeline</p>
              <p className="text-xs text-zinc-500 mt-0.5 font-mono">6-month trend · Agent-assisted</p>
            </div>
            <Badge variant="emerald" dot>Live</Badge>
          </div>
          <div className="h-52">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={revenueHistory.length > 0 ? revenueHistory : []} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
                <defs>
                  <linearGradient id="grad-revenue" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#6366F1" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#6366F1" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#27272A" vertical={false} />
                <XAxis dataKey="month" tick={{ fill: "#71717A", fontSize: 11 }} axisLine={false} tickLine={false} />
                <YAxis
                  tick={{ fill: "#71717A", fontSize: 11 }}
                  axisLine={false}
                  tickLine={false}
                  tickFormatter={(v) => `$${v / 1000}K`}
                  width={40}
                />
                <Tooltip content={<CustomTooltip />} />
                <Area
                  type="monotone"
                  dataKey="revenue"
                  stroke="#6366F1"
                  strokeWidth={2}
                  fill="url(#grad-revenue)"
                  dot={{ fill: "#6366F1", r: 3 }}
                  activeDot={{ r: 5, fill: "#818CF8" }}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </Card>

        {/* Agent accuracy chart — 1/3 width */}
        <Card>
          <div className="flex items-center justify-between mb-4">
            <div>
              <p className="text-sm font-semibold text-zinc-100">ML Accuracy</p>
              <p className="text-xs text-zinc-500 mt-0.5 font-mono">7-day rolling avg</p>
            </div>
          </div>
          <div className="h-52">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={[]} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#27272A" vertical={false} />
                <XAxis dataKey="day" tick={{ fill: "#71717A", fontSize: 11 }} axisLine={false} tickLine={false} />
                <YAxis
                  domain={[88, 98]}
                  tick={{ fill: "#71717A", fontSize: 11 }}
                  axisLine={false}
                  tickLine={false}
                  tickFormatter={(v) => `${v}%`}
                  width={38}
                />
                <Tooltip content={<CustomTooltip />} />
                <Legend
                  iconType="circle"
                  iconSize={6}
                  wrapperStyle={{ fontSize: "10px", color: "#71717A" }}
                />
                <Line type="monotone" dataKey="semantic" stroke="#6366F1" strokeWidth={2} dot={false} name="Semantic" />
                <Line type="monotone" dataKey="leadScore" stroke="#10B981" strokeWidth={2} dot={false} name="Lead Score" />
                <Line type="monotone" dataKey="sentiment" stroke="#F59E0B" strokeWidth={2} dot={false} name="Sentiment" />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Card>
      </section>

      {/* Bottom row: Active agents + Activity feed */}
      <section aria-labelledby="activity-heading" className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <h2 id="activity-heading" className="sr-only">Active Agents and Activity Feed</h2>

        {/* Active Agents */}
        <Card>
          <div className="flex items-center justify-between mb-4">
            <p className="text-sm font-semibold text-zinc-100">Active Agents</p>
            <Badge variant="indigo">{activeAgents.length} running</Badge>
          </div>
          <div className="space-y-3">
            {activeAgents.map((agent) => (
              <div
                key={agent.id}
                className="flex items-center gap-3 rounded-xl border border-zinc-800 bg-zinc-900/50 px-3 py-2.5 transition-all duration-200 hover:border-zinc-700 cursor-pointer"
              >
                <div
                  className={cn(
                    "h-2 w-2 rounded-full flex-shrink-0",
                    agent.status === "active" && "agent-pulse",
                    agent.status === "processing" ? "bg-indigo-400" : "bg-zinc-600"
                  )}
                  style={agent.status === "active" ? { backgroundColor: SIGNAL } : undefined}
                  aria-hidden="true"
                />
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-semibold text-zinc-200 truncate">{agent.name}</p>
                  <p className="text-[10px] text-zinc-500 font-mono truncate">{agent.model}</p>
                </div>
                <div className="text-right flex-shrink-0">
                  <p className="text-xs font-mono text-emerald-400">{agent.accuracy}%</p>
                  {/* Per-agent daily task counts aren't tracked yet — don't show a
                      seeded/fabricated number. The live Activity feed below is the
                      honest signal of what agents are doing. */}
                  <p className="text-[10px] text-zinc-600 capitalize">{agent.status}</p>
                </div>
              </div>
            ))}
          </div>
        </Card>

        {/* Activity Feed */}
        <Card>
          <div className="flex items-center justify-between mb-4">
            <p className="text-sm font-semibold text-zinc-100">Agent Activity</p>
            <div className="flex items-center gap-1.5 text-xs text-zinc-500 font-mono">
              <Activity className="h-3 w-3 text-emerald-400" aria-hidden="true" />
              Live feed
            </div>
          </div>
          <div className="space-y-2 max-h-72 overflow-y-auto pr-1" aria-live="polite" aria-label="Agent activity feed">
            {liveActivity.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-8 text-center">
                <Activity className="h-6 w-6 text-zinc-700 mb-2" aria-hidden="true" />
                <p className="text-xs text-zinc-500">No activity yet</p>
                <p className="text-[10px] text-zinc-600 font-mono mt-0.5">Events will appear here as agents run</p>
              </div>
            ) : liveActivity.map((event) => (
              <div
                key={event.id}
                className="flex items-start gap-2.5 rounded-lg px-2.5 py-2 hover:bg-zinc-800/50 transition-colors duration-150 cursor-default"
              >
                {severityIcon[event.severity]}
                <div className="flex-1 min-w-0">
                  <p className="text-xs text-zinc-200 leading-snug">
                    <span className="font-medium text-indigo-400">{event.agentName}</span>{" "}
                    {event.description}
                  </p>
                  {event.meta && (
                    <p className="text-[10px] text-zinc-500 font-mono mt-0.5">{event.meta}</p>
                  )}
                </div>
                <span className="text-[10px] text-zinc-600 flex-shrink-0 font-mono whitespace-nowrap">
                  {event.timestamp}
                </span>
              </div>
            ))}
          </div>
        </Card>
      </section>
    </div>
  );
}
