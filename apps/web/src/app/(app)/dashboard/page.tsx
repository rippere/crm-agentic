"use client";

import { useState, useEffect } from "react";
import Header from "@/components/layout/Header";
import Card from "@/components/ui/Card";
import Badge from "@/components/ui/Badge";
import { mockKPIs, mockActivity, revenueChartData, agentAccuracyData, mockAgents } from "@/lib/mock-data";
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
  ListTodo, Mail, BarChart2, CheckSquare,
} from "lucide-react";
import type { KPI, ActivityEvent } from "@/lib/types";

interface PMKpis {
  tasksExtractedToday: number;
  avgClarityScore: number | null;
  openTasks: number;
  messagesIngested: number;
}

const kpiIcons: Record<string, React.ReactNode> = {
  dollar: <DollarSign className="h-4 w-4" />,
  briefcase: <Briefcase className="h-4 w-4" />,
  brain: <Brain className="h-4 w-4" />,
  bot: <Bot className="h-4 w-4" />,
};

const severityIcon: Record<ActivityEvent["severity"], React.ReactNode> = {
  success: <CheckCircle className="h-3.5 w-3.5 text-emerald-400 flex-shrink-0" />,
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
  return (
    <Card className="flex flex-col gap-4" hover>
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs text-zinc-500 font-medium">{kpi.label}</p>
          <p className="mt-1.5 text-2xl font-bold text-zinc-100 font-mono">{kpi.value}</p>
        </div>
        <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-indigo-500/10 border border-indigo-500/20 text-indigo-400">
          {kpiIcons[kpi.icon]}
        </div>
      </div>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          {delta === "positive" ? (
            <TrendingUp className="h-3.5 w-3.5 text-emerald-400" aria-hidden="true" />
          ) : delta === "negative" ? (
            <TrendingDown className="h-3.5 w-3.5 text-rose-400" aria-hidden="true" />
          ) : (
            <Minus className="h-3.5 w-3.5 text-zinc-400" aria-hidden="true" />
          )}
          <span
            className={`text-xs font-mono font-medium ${
              delta === "positive"
                ? "text-emerald-400"
                : delta === "negative"
                ? "text-rose-400"
                : "text-zinc-400"
            }`}
          >
            {kpi.delta}
          </span>
          <span className="text-xs text-zinc-600">vs last month</span>
        </div>
      </div>
      {/* Sparkline */}
      <div className="h-10 -mx-1">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={kpi.sparkData.map((v, i) => ({ v, i }))}>
            <defs>
              <linearGradient id={`spark-${kpi.id}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#6366F1" stopOpacity={0.3} />
                <stop offset="95%" stopColor="#6366F1" stopOpacity={0} />
              </linearGradient>
            </defs>
            <Area
              type="monotone"
              dataKey="v"
              stroke="#6366F1"
              strokeWidth={1.5}
              fill={`url(#spark-${kpi.id})`}
              dot={false}
            />
          </AreaChart>
        </ResponsiveContainer>
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
    <Card className="flex items-center gap-4">
      <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-indigo-500/10 border border-indigo-500/20 text-indigo-400 flex-shrink-0">
        {icon}
      </div>
      <div>
        <p className="text-2xl font-bold font-mono text-zinc-100">{value}</p>
        <p className="text-xs text-zinc-500 mt-0.5">{label}</p>
      </div>
    </Card>
  );
}

export default function DashboardPage() {
  const [activeAgents] = useState(mockAgents.filter((a) => a.status !== "idle"));
  const [pmKpis, setPmKpis] = useState<PMKpis | null>(null);
  const [workspaceMode, setWorkspaceMode] = useState<"sales" | "pm" | "both">("sales");

  useEffect(() => {
    const supabase = createBrowserClient();
    supabase.auth.getSession().then(async ({ data: { session } }) => {
      if (!session) return;
      const workspaceId: string | undefined = session.user.user_metadata?.workspace_id;

      // Fetch workspace mode
      if (workspaceId) {
        const { data: ws } = await supabase.from("workspaces").select("mode").eq("id", workspaceId).single();
        if (ws?.mode) setWorkspaceMode(ws.mode as "sales" | "pm" | "both");
      }

      // Fetch PM aggregate KPIs
      if (!workspaceId) return;
      try {
        const [tasksData, messagesData] = await Promise.all([
          apiClient.getTasks(workspaceId, session.access_token).catch(() => []),
          apiClient.getMessages(workspaceId, session.access_token).catch(() => []),
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
      } catch {
        // Non-critical — dashboard still renders with sales KPIs
      }
    });
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
          {mockKPIs.map((kpi) => (
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
              <AreaChart data={revenueChartData} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
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
                  className={`h-2 w-2 rounded-full flex-shrink-0 ${
                    agent.status === "active"
                      ? "bg-emerald-400 agent-pulse"
                      : agent.status === "processing"
                      ? "bg-indigo-400"
                      : "bg-zinc-500"
                  }`}
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
            {mockActivity.map((event) => (
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
