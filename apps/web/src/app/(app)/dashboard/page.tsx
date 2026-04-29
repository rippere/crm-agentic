"use client";

import { useState, useEffect, useRef } from "react";
import Header from "@/components/layout/Header";
import Card from "@/components/ui/Card";
import Badge from "@/components/ui/Badge";
import { agentAccuracyData, mockAgents, mockActivity } from "@/lib/mock-data";
import { demoDashboard } from "@/lib/demo-data";
import { useDeals } from "@/hooks/useDeals";
import { formatCurrency } from "@/lib/utils";
import { apiClient } from "@/lib/api-client";
import { createBrowserClient } from "@/lib/supabase";
import {
  AreaChart, Area, LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Legend,
} from "recharts";
import {
  DollarSign, Briefcase, Brain, Bot, TrendingUp, TrendingDown,
  Minus, Activity, CheckCircle, AlertTriangle, Info,
  ListTodo, Mail, BarChart2, CheckSquare, Heart,
} from "lucide-react";
import { cn } from "@/lib/utils";
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

const kpiIcons: Record<string, React.ReactNode> = {
  dollar: <DollarSign className="h-4 w-4" />,
  briefcase: <Briefcase className="h-4 w-4" />,
  brain: <Brain className="h-4 w-4" />,
  bot: <Bot className="h-4 w-4" />,
};

const SIGNAL = "#00C896";

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
}: {
  icon: React.ReactNode;
  label: string;
  value: string | number;
}) {
  return (
    <Card compact accent="violet" className="flex items-center gap-3">
      <span className="flex-shrink-0 text-indigo-400" aria-hidden="true">{icon}</span>
      <div>
        <p className="text-xl font-bold font-mono tabular-nums text-zinc-100 leading-none">{value}</p>
        <p className="text-[11px] text-zinc-500 mt-1 font-medium">{label}</p>
      </div>
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
      id: "k4", label: "Pipeline Value", icon: "bot",
      value: (() => { const v = active.reduce((s, d) => s + d.value, 0); return v >= 1000000 ? `$${(v / 1000000).toFixed(1)}M` : `$${Math.round(v / 1000)}K`; })(),
      delta: `${active.length} open deal${active.length !== 1 ? "s" : ""}`,
      deltaType: "neutral",
      sparkData: active.map((d) => d.value),
    },
  ];
}

export default function DashboardPage() {
  const { deals } = useDeals();
  const [activeAgents] = useState(mockAgents.filter((a) => a.status !== "idle"));
  const [pmKpis, setPmKpis] = useState<PMKpis | null>(null);
  const [workspaceMode, setWorkspaceMode] = useState<"sales" | "pm" | "both">("sales");
  const [staleDeals, setStaleDeals] = useState<StaleDeal[]>([]);
  const [liveActivity, setLiveActivity] = useState<ActivityEvent[]>([]);
  const [revenueHistory, setRevenueHistory] = useState<{ month: string; revenue: number }[]>([]);
  const esRef = useRef<EventSource | null>(null);

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
      apiClient.getDealHistory("demo-workspace-1", "demo-token", 6).then((data) => {
        if (Array.isArray(data)) setRevenueHistory(data);
      }).catch(() => {});
      return;
    }

    // Seed activity feed with recent events, then switch to SSE
    fetch("/api/activity?limit=20")
      .then((r) => r.json())
      .then((data: Array<{ id: string; type: string; agent_name: string; description: string; meta?: string; severity: string; created_at: string }>) => {
        if (!Array.isArray(data)) return;
        setLiveActivity(data.map((e) => ({
          id: e.id,
          type: e.type as ActivityEvent["type"],
          agentName: e.agent_name,
          description: e.description,
          meta: e.meta,
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

    const supabase = createBrowserClient();
    supabase.auth.getSession().then(async ({ data: { session } }) => {
      if (!session) return;
      const workspaceId: string | undefined = session.user.user_metadata?.workspace_id;

      // Fetch workspace mode
      if (workspaceId) {
        const { data: ws } = await supabase.from("workspaces").select("mode").eq("id", workspaceId).single();
        if (ws?.mode) setWorkspaceMode(ws.mode as "sales" | "pm" | "both");
      }

      if (!workspaceId) return;

      // Fetch revenue history
      apiClient.getDealHistory(workspaceId, session.access_token, 6)
        .then((data) => { if (Array.isArray(data)) setRevenueHistory(data); })
        .catch(() => {});

      // Open SSE stream for live activity updates
      if (esRef.current) esRef.current.close();
      const es = new EventSource(`/api/events?workspaceId=${workspaceId}`);
      esRef.current = es;
      es.onmessage = (e) => {
        try {
          const ev = JSON.parse(e.data) as { id: string; type: string; agent_name: string; description: string; meta?: string; severity: string; created_at: string };
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
        } catch { /* ignore malformed */ }
      };

      // Fetch PM aggregate KPIs + stale deals in parallel
      try {
        const [tasksData, messagesData, staleData] = await Promise.all([
          apiClient.getTasks(workspaceId, session.access_token).catch(() => []),
          apiClient.getMessages(workspaceId, session.access_token).catch(() => []),
          apiClient.getStaleDeals(workspaceId, session.access_token).catch(() => []),
        ]);

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
      } catch {
        // Non-critical — dashboard still renders with sales KPIs
      }
    });
    return () => { esRef.current?.close(); };
  }, []);

  return (
    <div className="flex flex-col gap-6 p-6">
      <Header
        title="Dashboard"
        subtitle="Real-time overview · 6 agents active"
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
      {(workspaceMode === "pm" || workspaceMode === "both") && pmKpis && (
        <section aria-labelledby="pm-kpi-heading">
          <div className="flex items-center gap-2 mb-3">
            <h2 id="pm-kpi-heading" className="text-xs font-semibold text-zinc-400 uppercase tracking-widest font-mono">
              PM Intelligence
            </h2>
            <Badge variant="indigo" size="sm" dot>Live</Badge>
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <PMKpiCard
              icon={<ListTodo className="h-4 w-4" />}
              label="Tasks Extracted Today"
              value={pmKpis.tasksExtractedToday}
            />
            <PMKpiCard
              icon={<BarChart2 className="h-4 w-4" />}
              label="Avg Clarity Score"
              value={pmKpis.avgClarityScore !== null ? pmKpis.avgClarityScore : "—"}
            />
            <PMKpiCard
              icon={<CheckSquare className="h-4 w-4" />}
              label="Open Tasks"
              value={pmKpis.openTasks}
            />
            <PMKpiCard
              icon={<Mail className="h-4 w-4" />}
              label="Messages Ingested"
              value={pmKpis.messagesIngested}
            />
          </div>
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
              {staleDeals.map((deal) => (
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
                </div>
              ))}
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
              <LineChart data={agentAccuracyData} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
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
                  <p className="text-[10px] text-zinc-600">{agent.tasksToday} tasks</p>
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
          <div className="space-y-2 max-h-72 overflow-y-auto pr-1">
            {(liveActivity.length > 0 ? liveActivity : mockActivity).map((event) => (
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
