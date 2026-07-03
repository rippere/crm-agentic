"use client";

import { useMemo, useState, useEffect } from "react";
import Header from "@/components/layout/Header";
import Card from "@/components/ui/Card";
import Badge from "@/components/ui/Badge";
import { useDeals } from "@/hooks/useDeals";
import { cn, formatCurrency, stageConfig, dealStageOrder } from "@/lib/utils";
import { apiClient } from "@/lib/api-client";
import { createBrowserClient } from "@/lib/supabase";
import {
  BarChart, Bar, PieChart, Pie, Cell, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Legend, ComposedChart, Line,
  LineChart, AreaChart, Area,
} from "recharts";
import {
  TrendingUp, DollarSign, Target, BarChart2, AlertTriangle, Trophy, Clock, Timer, Filter, Bot,
  CalendarOff, Users, Activity, Zap, ArrowUp, ArrowDown, Minus, Medal,
} from "lucide-react";

const DEMO_MODE = process.env.NEXT_PUBLIC_DEMO_MODE === "true";

const STAGE_COLORS: Record<string, string> = {
  discovery:   "#52525B",
  qualified:   "#6366F1",
  proposal:    "#FBBF24",
  negotiation: "#A78BFA",
  closed_won:  "#00C896",
  closed_lost: "#F43F5E",
};

const CustomTooltip = ({ active, payload, label }: { active?: boolean; payload?: { value: number; name: string }[]; label?: string }) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-xl border border-zinc-700 bg-zinc-900 p-3 shadow-xl text-xs">
      <p className="font-mono text-zinc-400 mb-2">{label}</p>
      {payload.map((p) => (
        <div key={p.name} className="text-zinc-200">{p.name}: {formatCurrency(p.value)}</div>
      ))}
    </div>
  );
};

const VelocityTooltip = ({ active, payload, label }: { active?: boolean; payload?: { value: number; payload: { deal_count: number } }[]; label?: string }) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-xl border border-zinc-700 bg-zinc-900 p-3 shadow-xl text-xs">
      <p className="font-mono text-zinc-400 mb-1">{label}</p>
      <p className="text-zinc-200">Avg: <span className="font-mono text-indigo-300">{payload[0].value}d</span></p>
      <p className="text-zinc-500">{payload[0].payload.deal_count} deal{payload[0].payload.deal_count !== 1 ? "s" : ""}</p>
    </div>
  );
};

type FunnelRow = { stage: string; deal_count: number; conversion_rate: number | null; label: string };

type OutcomeReasonRow = { reason: string; label: string; won: number; lost: number };

export default function ReportsPage() {
  const { deals, loading } = useDeals();
  const [velocityData, setVelocityData] = useState<{ stage: string; avg_days: number; deal_count: number; label: string }[]>([]);
  const [funnelData, setFunnelData] = useState<FunnelRow[]>([]);
  const [outcomeReasons, setOutcomeReasons] = useState<OutcomeReasonRow[]>([]);
  const [agentRunStats, setAgentRunStats] = useState<{ agent_name: string; success: number; failure: number }[]>([]);
  const [velocityTrends, setVelocityTrends] = useState<{ month: string; avg_cycle_days: number | null; deal_count: number }[]>([]);
  const [revenueForecast, setRevenueForecast] = useState<{ month: string; expected_revenue: number; deal_count: number; total_value: number }[]>([]);
  const [stageAging, setStageAging] = useState<{ id: string; title: string; company: string; stage: string; value: number; days_in_stage: number }[]>([]);
  const [winProbByStage, setWinProbByStage] = useState<{ stage: string; avg_probability: number; deal_count: number; total_value: number }[]>([]);
  const [concentrationRisk, setConcentrationRisk] = useState<{ top3_pct: number; risk_level: string; top_deals: { id: string; title: string; company: string; stage: string; value: number; pct_of_pipeline: number }[]; total_pipeline_value: number } | null>(null);
  const [closeDateAccuracy, setCloseDateAccuracy] = useState<{ id: string; title: string; company: string; expected_close: string; actual_close: string; days_delta: number; outcome: string }[]>([]);
  const [closeDateSlipped, setCloseDateSlipped] = useState<{ id: string; title: string; company: string; stage: string; value: number; expected_close: string; days_overdue: number }[]>([]);
  const [activityTrends, setActivityTrends] = useState<{ week_start: string; deals: number; contacts: number; agents: number; messages: number }[]>([]);
  const [reengagementSummary, setReengagementSummary] = useState<{ week_start: string; reengagement_count: number }[]>([]);
  const [pipelineContribution, setPipelineContribution] = useState<{ contact_id: string; name: string; email: string | null; company: string; pipeline_value: number; closed_won_value: number; deal_count: number; win_rate: number }[]>([]);
  const [revenueCohort, setRevenueCohort] = useState<{ cohort_month: string; initial_revenue: number; months: { month_offset: number; revenue: number; deal_count: number; pct_of_initial: number | null }[] }[]>([]);
  const [leaderboard, setLeaderboard] = useState<Array<{ rank: number; id: string; title: string | null; company: string | null; stage: string; value: number; ml_win_probability: number; score: number; trend: "up" | "neutral" | "down"; health_score: number }>>([]);
  const [contactLeaderboard, setContactLeaderboard] = useState<Array<{ rank: number; contact_id: string; name: string | null; email: string | null; company: string | null; score: number; message_count: number; note_count: number; task_completion_rate: number }>>([]);

  useEffect(() => {
    const WS = DEMO_MODE ? "demo-workspace-1" : null;
    const TK = DEMO_MODE ? "demo-token" : null;

    const fetchAll = (workspaceId: string, token: string) => {
      apiClient.getDealVelocity(workspaceId, token).then((data) => {
        setVelocityData(data.map((v) => ({ ...v, label: stageConfig[v.stage as keyof typeof stageConfig]?.label ?? v.stage })));
      }).catch(() => {});
      apiClient.getDealFunnel(workspaceId, token).then((data) => {
        setFunnelData(data.map((r) => ({ ...r, label: stageConfig[r.stage as keyof typeof stageConfig]?.label ?? r.stage })));
      }).catch(() => {});
      apiClient.getDealOutcomeReasons(workspaceId, token).then(setOutcomeReasons).catch(() => {});
      apiClient.getAgentRunStats(workspaceId, token).then(setAgentRunStats).catch(() => {});
      apiClient.getDealVelocityTrends(workspaceId, token).then(setVelocityTrends).catch(() => {});
      apiClient.getDealRevenueForecast(workspaceId, token).then(setRevenueForecast).catch(() => {});
      apiClient.getDealStageAging(workspaceId, token).then(setStageAging).catch(() => {});
      apiClient.getDealWinProbabilityByStage(workspaceId, token).then(setWinProbByStage).catch(() => {});
      apiClient.getDealConcentrationRisk(workspaceId, token).then(setConcentrationRisk).catch(() => {});
      apiClient.getDealCloseDateAccuracy(workspaceId, token).then(setCloseDateAccuracy).catch(() => {});
      apiClient.getDealCloseDateSlipped(workspaceId, token).then(setCloseDateSlipped).catch(() => {});
      apiClient.getActivityTrends(workspaceId, token).then(setActivityTrends).catch(() => {});
      apiClient.getContactReengagementSummary(workspaceId, token).then(setReengagementSummary).catch(() => {});
      apiClient.getContactPipelineContribution(workspaceId, token).then(setPipelineContribution).catch(() => {});
      apiClient.getRevenueCohort(workspaceId, token).then(setRevenueCohort).catch(() => {});
      apiClient.getDealLeaderboard(workspaceId, token).then(setLeaderboard).catch(() => {});
      apiClient.getContactEngagementLeaderboard(workspaceId, token).then(setContactLeaderboard).catch(() => {});
    };

    if (DEMO_MODE && WS && TK) {
      fetchAll(WS, TK);
      return;
    }
    const supabase = createBrowserClient();
    supabase.auth.getSession().then(({ data: { session } }) => {
      if (!session) return;
      const workspaceId: string | undefined = session.user.app_metadata?.workspace_id ?? session.user.user_metadata?.workspace_id;
      if (!workspaceId) return;
      fetchAll(workspaceId, session.access_token);
    });
  }, []);

  const stats = useMemo(() => {
    const won = deals.filter((d) => d.stage === "closed_won");
    const lost = deals.filter((d) => d.stage === "closed_lost");
    const active = deals.filter((d) => d.stage !== "closed_won" && d.stage !== "closed_lost");
    const closed = won.length + lost.length;
    const winRate = closed > 0 ? Math.round((won.length / closed) * 100) : 0;
    const wonValue = won.reduce((s, d) => s + d.value, 0);
    const pipelineValue = active.reduce((s, d) => s + d.value, 0);
    const avgDealSize = won.length > 0 ? wonValue / won.length : 0;
    const stale = active.filter((d) => d.healthScore < 40).length;

    // Avg cycle time: days from deal creation to close (approximated as days since created)
    const now = new Date();
    const cycleTimes = won
      .map((d) => {
        if (!d.createdAt) return null;
        return Math.max(1, Math.round((now.getTime() - new Date(d.createdAt).getTime()) / 86400000));
      })
      .filter((v): v is number => v !== null);
    const avgCycleTime = cycleTimes.length > 0
      ? Math.round(cycleTimes.reduce((s, v) => s + v, 0) / cycleTimes.length)
      : null;

    const byStage = dealStageOrder.map((stage) => {
      const stageDeals = deals.filter((d) => d.stage === stage);
      return {
        name: stageConfig[stage].label,
        value: stageDeals.reduce((s, d) => s + d.value, 0),
        count: stageDeals.length,
        stage,
      };
    }).filter((s) => s.value > 0 || s.count > 0);

    const topDeals = [...won]
      .sort((a, b) => b.value - a.value)
      .slice(0, 5);

    const healthBuckets = [
      { label: "Healthy (70-100)", count: active.filter((d) => d.healthScore >= 70).length, color: "#00C896" },
      { label: "At risk (40-69)",  count: active.filter((d) => d.healthScore >= 40 && d.healthScore < 70).length, color: "#FBBF24" },
      { label: "Critical (<40)",   count: active.filter((d) => d.healthScore < 40).length, color: "#F43F5E" },
    ];

    // Monthly revenue from closed_won deals (last 6 months) — reuses `now` from above
    const abbr = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
    const historyMonths = 6;
    const monthKeys: string[] = [];
    for (let i = historyMonths - 1; i >= 0; i--) {
      const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
      monthKeys.push(`${d.getFullYear()}-${d.getMonth()}`);
    }
    const monthBuckets: Record<string, { month: string; actual: number }> = {};
    monthKeys.forEach((key) => {
      const [y, m] = key.split('-').map(Number);
      monthBuckets[key] = { month: abbr[m], actual: 0 };
    });
    won.forEach((d) => {
      const dt = new Date(d.createdAt ?? "");
      const key = `${dt.getFullYear()}-${dt.getMonth()}`;
      if (monthBuckets[key]) monthBuckets[key].actual += d.value;
    });
    const history = monthKeys.map((k) => monthBuckets[k]);

    // Linear regression over history to project 3 forecast months
    const n = history.length;
    const sumX = history.reduce((s, _, i) => s + i, 0);
    const sumY = history.reduce((s, h) => s + h.actual, 0);
    const sumXY = history.reduce((s, h, i) => s + i * h.actual, 0);
    const sumX2 = history.reduce((s, _, i) => s + i * i, 0);
    const denom = n * sumX2 - sumX * sumX;
    const slope = denom !== 0 ? (n * sumXY - sumX * sumY) / denom : 0;
    const intercept = (sumY - slope * sumX) / n;

    const forecastCount = 3;
    const revenueChart = [
      ...history.map((h, i) => ({
        month: h.month,
        actual: Math.round(h.actual),
        forecast: null as number | null,
        trend: Math.max(0, Math.round(intercept + slope * i)),
      })),
      ...Array.from({ length: forecastCount }, (_, i) => {
        const dt = new Date(now.getFullYear(), now.getMonth() + 1 + i, 1);
        return {
          month: abbr[dt.getMonth()],
          actual: null as number | null,
          forecast: Math.max(0, Math.round(intercept + slope * (n + i))),
          trend: null as number | null,
        };
      }),
    ];

    return { won, lost, active, winRate, wonValue, pipelineValue, avgDealSize, stale, byStage, topDeals, healthBuckets, revenueChart, avgCycleTime };
  }, [deals]);

  if (loading) {
    return (
      <div className="flex flex-col gap-6 p-4 md:p-6">
        <Header title="Reports" subtitle="Pipeline analytics and win rate" />
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          {[1, 2, 3, 4].map((i) => <div key={i} className="h-24 rounded-xl bg-zinc-800/50 animate-pulse" />)}
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6 p-4 md:p-6">
      <Header title="Reports" subtitle={`${deals.length} total deals · win rate ${stats.winRate}%`} />

      {/* KPI row */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-2 lg:grid-cols-5">
        <Card compact accent="signal" className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-[#00C896]/10 border border-[#00C896]/20 flex-shrink-0">
            <Trophy className="h-4 w-4 text-[#00C896]" />
          </div>
          <div>
            <p className="text-2xl font-bold font-mono text-[#00C896]">{stats.winRate}%</p>
            <p className="text-xs text-zinc-500">Win Rate</p>
          </div>
        </Card>
        <Card compact accent="violet" className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-indigo-500/10 border border-indigo-500/20 flex-shrink-0">
            <DollarSign className="h-4 w-4 text-indigo-400" />
          </div>
          <div>
            <p className="text-2xl font-bold font-mono text-zinc-100">{formatCurrency(stats.wonValue)}</p>
            <p className="text-xs text-zinc-500">Closed Won</p>
          </div>
        </Card>
        <Card compact className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-amber-500/10 border border-amber-500/20 flex-shrink-0">
            <TrendingUp className="h-4 w-4 text-amber-400" />
          </div>
          <div>
            <p className="text-2xl font-bold font-mono text-amber-400">{formatCurrency(stats.pipelineValue)}</p>
            <p className="text-xs text-zinc-500">Pipeline Value</p>
          </div>
        </Card>
        <Card compact className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-zinc-700/50 border border-zinc-700 flex-shrink-0">
            <Target className="h-4 w-4 text-zinc-400" />
          </div>
          <div>
            <p className="text-2xl font-bold font-mono text-zinc-100">{formatCurrency(stats.avgDealSize)}</p>
            <p className="text-xs text-zinc-500">Avg Deal Size</p>
          </div>
        </Card>
        <Card compact className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-violet-500/10 border border-violet-500/20 flex-shrink-0">
            <Clock className="h-4 w-4 text-violet-400" />
          </div>
          <div>
            <p className="text-2xl font-bold font-mono text-zinc-100">
              {stats.avgCycleTime !== null ? `${stats.avgCycleTime}d` : "—"}
            </p>
            <p className="text-xs text-zinc-500">Avg Cycle Time</p>
          </div>
        </Card>
      </div>

      {/* Charts row */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        {/* Pipeline by stage bar chart */}
        <Card className="lg:col-span-2">
          <div className="flex items-center justify-between mb-4">
            <div>
              <p className="text-sm font-semibold text-zinc-100">Pipeline Value by Stage</p>
              <p className="text-xs text-zinc-500 mt-0.5 font-mono">Active + closed deals</p>
            </div>
            <Badge variant="indigo">{deals.length} deals</Badge>
          </div>
          <div className="h-56">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={stats.byStage} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#27272A" vertical={false} />
                <XAxis dataKey="name" tick={{ fill: "#71717A", fontSize: 10 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: "#71717A", fontSize: 10 }} axisLine={false} tickLine={false} tickFormatter={(v) => `$${v / 1000}K`} width={40} />
                <Tooltip content={<CustomTooltip />} />
                <Bar dataKey="value" name="Value" radius={[4, 4, 0, 0]}>
                  {stats.byStage.map((entry) => (
                    <Cell key={entry.stage} fill={STAGE_COLORS[entry.stage] ?? "#52525B"} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>

        {/* Deal health donut */}
        <Card>
          <div className="flex items-center justify-between mb-4">
            <p className="text-sm font-semibold text-zinc-100">Deal Health</p>
            {stats.stale > 0 && (
              <Badge variant="rose" dot size="sm">{stats.stale} critical</Badge>
            )}
          </div>
          {stats.active.length === 0 ? (
            <div className="flex h-48 items-center justify-center text-xs text-zinc-600">No active deals</div>
          ) : (
            <>
              <div className="h-36">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={stats.healthBuckets.filter((b) => b.count > 0)}
                      dataKey="count"
                      nameKey="label"
                      cx="50%"
                      cy="50%"
                      innerRadius={38}
                      outerRadius={58}
                      paddingAngle={3}
                    >
                      {stats.healthBuckets.filter((b) => b.count > 0).map((b) => (
                        <Cell key={b.label} fill={b.color} />
                      ))}
                    </Pie>
                    <Tooltip formatter={(v) => [`${v} deals`, ""]} contentStyle={{ background: "#18181B", border: "1px solid #27272A", borderRadius: 8, fontSize: 11 }} />
                  </PieChart>
                </ResponsiveContainer>
              </div>
              <div className="space-y-1.5 mt-2">
                {stats.healthBuckets.map((b) => (
                  <div key={b.label} className="flex items-center justify-between text-xs">
                    <div className="flex items-center gap-2">
                      <span className="h-2 w-2 rounded-full flex-shrink-0" style={{ background: b.color }} />
                      <span className="text-zinc-400">{b.label}</span>
                    </div>
                    <span className="font-mono text-zinc-200">{b.count}</span>
                  </div>
                ))}
              </div>
            </>
          )}
        </Card>
      </div>

      {/* Win/Loss summary + Top deals */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* Win vs Loss */}
        <Card>
          <div className="flex items-center gap-2 mb-4">
            <BarChart2 className="h-4 w-4 text-indigo-400" />
            <p className="text-sm font-semibold text-zinc-100">Win / Loss Summary</p>
          </div>
          <div className="space-y-3">
            {[
              { label: "Won", count: stats.won.length, value: stats.wonValue, color: "bg-[#00C896]", text: "text-[#00C896]" },
              { label: "Lost", count: stats.lost.length, value: stats.lost.reduce((s, d) => s + d.value, 0), color: "bg-rose-500", text: "text-rose-400" },
              { label: "Active", count: stats.active.length, value: stats.pipelineValue, color: "bg-indigo-500", text: "text-indigo-400" },
            ].map(({ label, count, value, color, text }) => (
              <div key={label} className="flex items-center gap-3">
                <div className="w-16 flex-shrink-0">
                  <span className={cn("text-xs font-medium", text)}>{label}</span>
                </div>
                <div className="flex-1 h-2 rounded-full bg-zinc-800 overflow-hidden">
                  <div
                    className={cn("h-full rounded-full", color)}
                    style={{ width: deals.length > 0 ? `${(count / deals.length) * 100}%` : "0%" }}
                  />
                </div>
                <div className="w-24 text-right flex-shrink-0">
                  <span className="text-xs font-mono text-zinc-400">{count} · {formatCurrency(value)}</span>
                </div>
              </div>
            ))}
          </div>
        </Card>

        {/* Top closed-won deals */}
        <Card>
          <div className="flex items-center gap-2 mb-4">
            <Trophy className="h-4 w-4 text-[#00C896]" />
            <p className="text-sm font-semibold text-zinc-100">Top Closed Deals</p>
          </div>
          {stats.topDeals.length === 0 ? (
            <div className="flex h-24 items-center justify-center text-xs text-zinc-600">No closed deals yet</div>
          ) : (
            <div className="space-y-2">
              {stats.topDeals.map((deal, i) => (
                <div key={deal.id} className="flex items-center gap-3 rounded-lg px-3 py-2.5 bg-zinc-800/40">
                  <span className="text-[10px] font-mono text-zinc-600 w-4 flex-shrink-0">{i + 1}</span>
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-medium text-zinc-200 truncate">{deal.title}</p>
                    <p className="text-[10px] text-zinc-600 truncate">{deal.company}</p>
                  </div>
                  <span className="text-xs font-mono font-bold text-[#00C896] flex-shrink-0">{formatCurrency(deal.value)}</span>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>

      {/* Revenue forecast chart */}
      <Card>
        <div className="flex items-center justify-between mb-4">
          <div>
            <p className="text-sm font-semibold text-zinc-100">Revenue Trend &amp; Forecast</p>
            <p className="text-xs text-zinc-500 mt-0.5 font-mono">6-month history · 3-month projection (linear trend)</p>
          </div>
          <div className="flex items-center gap-4 text-[10px] text-zinc-500">
            <span className="flex items-center gap-1.5">
              <span className="inline-block h-2 w-4 rounded-sm bg-[#6366F1]" /> Actual
            </span>
            <span className="flex items-center gap-1.5">
              <span className="inline-block h-0.5 w-4 border-t-2 border-dashed border-[#00C896]" /> Forecast
            </span>
          </div>
        </div>
        <div className="h-56">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={stats.revenueChart} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#27272A" vertical={false} />
              <XAxis dataKey="month" tick={{ fill: "#71717A", fontSize: 10 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: "#71717A", fontSize: 10 }} axisLine={false} tickLine={false} tickFormatter={(v) => `$${v / 1000}K`} width={40} />
              <Tooltip content={<CustomTooltip />} />
              <Bar dataKey="actual" name="Actual" fill="#6366F1" radius={[4, 4, 0, 0]} maxBarSize={40} />
              <Bar dataKey="forecast" name="Forecast" fill="#00C896" radius={[4, 4, 0, 0]} maxBarSize={40} opacity={0.35} />
              <Line dataKey="trend" name="Trend" stroke="#00C896" strokeWidth={1.5} strokeDasharray="5 3" dot={false} connectNulls />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </Card>

      {/* Pipeline velocity — avg days in stage */}
      {velocityData.length > 0 && (
        <Card>
          <div className="flex items-center justify-between mb-4">
            <div>
              <p className="text-sm font-semibold text-zinc-100">Pipeline Velocity</p>
              <p className="text-xs text-zinc-500 mt-0.5 font-mono">Avg days each deal has spent in current stage</p>
            </div>
            <div className="flex items-center gap-1.5 text-xs text-zinc-500">
              <Timer className="h-3.5 w-3.5" />
              <span>{velocityData.reduce((s, v) => s + v.deal_count, 0)} deals measured</span>
            </div>
          </div>
          <div className="h-52">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={velocityData} layout="vertical" margin={{ top: 4, right: 48, bottom: 0, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#27272A" horizontal={false} />
                <XAxis
                  type="number"
                  tick={{ fill: "#71717A", fontSize: 10 }}
                  axisLine={false}
                  tickLine={false}
                  tickFormatter={(v) => `${v}d`}
                />
                <YAxis
                  type="category"
                  dataKey="label"
                  tick={{ fill: "#71717A", fontSize: 10 }}
                  axisLine={false}
                  tickLine={false}
                  width={80}
                />
                <Tooltip content={<VelocityTooltip />} />
                <Bar dataKey="avg_days" name="Avg days" radius={[0, 4, 4, 0]} maxBarSize={18} label={{ position: "right", fill: "#71717A", fontSize: 10, formatter: (v) => `${v}d` }}>
                  {velocityData.map((entry) => (
                    <Cell key={entry.stage} fill={STAGE_COLORS[entry.stage] ?? "#52525B"} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
      )}

      {/* Stage conversion funnel */}
      {funnelData.length > 0 && (() => {
        const maxCount = Math.max(...funnelData.map((r) => r.deal_count), 1);
        return (
          <Card>
            <div className="flex items-center justify-between mb-5">
              <div>
                <p className="text-sm font-semibold text-zinc-100">Stage Conversion Funnel</p>
                <p className="text-xs text-zinc-500 mt-0.5 font-mono">Deal count per stage · % converted from previous</p>
              </div>
              <div className="flex items-center gap-1.5 text-xs text-zinc-500">
                <Filter className="h-3.5 w-3.5" />
                <span>{funnelData.reduce((s, r) => s + r.deal_count, 0)} total deals</span>
              </div>
            </div>
            <div className="space-y-0.5">
              {funnelData.map((row, i) => (
                <div key={row.stage}>
                  {i > 0 && (
                    <div className="flex items-center gap-2 pl-28 py-1">
                      <span className="text-[10px] font-mono text-zinc-600">
                        {row.conversion_rate !== null && row.conversion_rate > 0
                          ? `↓ ${row.conversion_rate.toFixed(1)}% converted`
                          : "↓ 0% converted"}
                      </span>
                    </div>
                  )}
                  <div className="flex items-center gap-3">
                    <div className="w-24 flex-shrink-0 text-right">
                      <span className="text-[11px] text-zinc-400">{row.label}</span>
                    </div>
                    <div className="flex-1 h-7 bg-zinc-800/40 rounded-md overflow-hidden">
                      <div
                        className="h-full rounded-md flex items-center pl-2 transition-all duration-500"
                        style={{
                          width: row.deal_count > 0 ? `${Math.max(4, (row.deal_count / maxCount) * 100)}%` : "3px",
                          background: STAGE_COLORS[row.stage] ?? "#52525B",
                          opacity: row.deal_count === 0 ? 0.25 : 1,
                        }}
                      >
                        {row.deal_count > 0 && (
                          <span className="text-[10px] font-mono font-bold text-white/80 select-none">
                            {row.deal_count}
                          </span>
                        )}
                      </div>
                    </div>
                    <div className="w-8 flex-shrink-0">
                      <span className="text-xs font-mono text-zinc-500">{row.deal_count}</span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </Card>
        );
      })()}

      {/* Win/Loss Reason Breakdown */}
      {outcomeReasons.length > 0 && (
        <Card>
          <div className="flex items-center justify-between mb-5">
            <div>
              <p className="text-sm font-semibold text-zinc-100">Win / Loss Reasons</p>
              <p className="text-xs text-zinc-500 mt-0.5 font-mono">Closed deal count by tagged outcome reason</p>
            </div>
            <div className="flex items-center gap-3 text-xs">
              <span className="flex items-center gap-1.5 text-[#00C896]">
                <span className="inline-block w-2.5 h-2.5 rounded-sm bg-[#00C896]" /> Won
              </span>
              <span className="flex items-center gap-1.5 text-[#F43F5E]">
                <span className="inline-block w-2.5 h-2.5 rounded-sm bg-[#F43F5E]" /> Lost
              </span>
            </div>
          </div>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={outcomeReasons} margin={{ top: 0, right: 8, left: -24, bottom: 0 }} barCategoryGap="30%">
              <CartesianGrid strokeDasharray="3 3" stroke="#27272A" vertical={false} />
              <XAxis dataKey="label" tick={{ fill: "#71717A", fontSize: 11 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: "#71717A", fontSize: 11 }} axisLine={false} tickLine={false} allowDecimals={false} />
              <Tooltip
                content={({ active, payload, label }) => {
                  if (!active || !payload?.length) return null;
                  return (
                    <div className="rounded-xl border border-zinc-700 bg-zinc-900 p-3 shadow-xl text-xs">
                      <p className="font-mono text-zinc-400 mb-2">{label}</p>
                      {payload.map((p) => (
                        <div key={p.name} className="flex items-center gap-2" style={{ color: p.color }}>
                          <span>{p.name === "won" ? "Won" : "Lost"}:</span>
                          <span className="font-mono font-bold">{p.value}</span>
                        </div>
                      ))}
                    </div>
                  );
                }}
              />
              <Bar dataKey="won" name="won" fill="#00C896" radius={[4, 4, 0, 0]} maxBarSize={28} />
              <Bar dataKey="lost" name="lost" fill="#F43F5E" radius={[4, 4, 0, 0]} maxBarSize={28} />
            </BarChart>
          </ResponsiveContainer>
        </Card>
      )}

      {/* Agent run success/failure chart */}
      {agentRunStats.length > 0 && (
        <Card>
          <div className="flex items-center justify-between mb-5">
            <div>
              <p className="text-sm font-semibold text-zinc-100">Agent Run Success Rate</p>
              <p className="text-xs text-zinc-500 mt-0.5 font-mono">Last 30 days · runs per agent</p>
            </div>
            <div className="flex items-center gap-3 text-xs">
              <span className="flex items-center gap-1.5 text-emerald-400">
                <span className="inline-block w-2.5 h-2.5 rounded-sm bg-emerald-500" /> Success
              </span>
              <span className="flex items-center gap-1.5 text-rose-400">
                <span className="inline-block w-2.5 h-2.5 rounded-sm bg-rose-500" /> Failure
              </span>
              <Bot className="h-3.5 w-3.5 text-zinc-500" />
            </div>
          </div>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart
              data={agentRunStats.map((r) => ({
                ...r,
                label: r.agent_name.replace(" ", "\n"),
              }))}
              margin={{ top: 0, right: 8, left: -24, bottom: 0 }}
              barCategoryGap="30%"
            >
              <CartesianGrid strokeDasharray="3 3" stroke="#27272A" vertical={false} />
              <XAxis
                dataKey="agent_name"
                tick={{ fill: "#71717A", fontSize: 10 }}
                axisLine={false}
                tickLine={false}
                tickFormatter={(v: string) => v.split(" ").slice(0, 2).join(" ")}
              />
              <YAxis tick={{ fill: "#71717A", fontSize: 11 }} axisLine={false} tickLine={false} allowDecimals={false} />
              <Tooltip
                content={({ active, payload, label }) => {
                  if (!active || !payload?.length) return null;
                  return (
                    <div className="rounded-xl border border-zinc-700 bg-zinc-900 p-3 shadow-xl text-xs">
                      <p className="font-mono text-zinc-400 mb-2">{label}</p>
                      {payload.map((p) => (
                        <div key={p.name} className="flex items-center gap-2" style={{ color: p.color }}>
                          <span className="capitalize">{p.name}:</span>
                          <span className="font-mono font-bold">{p.value}</span>
                        </div>
                      ))}
                      {payload.length === 2 && (
                        <div className="mt-1.5 pt-1.5 border-t border-zinc-700 text-zinc-500">
                          Total: {(payload[0].value as number) + (payload[1].value as number)} runs
                        </div>
                      )}
                    </div>
                  );
                }}
              />
              <Bar dataKey="success" name="success" fill="#10B981" radius={[4, 4, 0, 0]} maxBarSize={28} />
              <Bar dataKey="failure" name="failure" fill="#F43F5E" radius={[4, 4, 0, 0]} maxBarSize={28} />
            </BarChart>
          </ResponsiveContainer>
        </Card>
      )}

      {/* Deal velocity trends — avg cycle time month-over-month (13d) */}
      {velocityTrends.length > 0 && (
        <Card>
          <div className="flex items-center justify-between mb-4">
            <div>
              <p className="text-sm font-semibold text-zinc-100">Deal Velocity Trends</p>
              <p className="text-xs text-zinc-500 mt-0.5 font-mono">Avg days from creation to close per month</p>
            </div>
            <Timer className="h-4 w-4 text-violet-400" />
          </div>
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={velocityTrends} margin={{ top: 4, right: 8, left: -16, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#27272A" vertical={false} />
              <XAxis dataKey="month" tick={{ fill: "#71717A", fontSize: 10 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: "#71717A", fontSize: 10 }} axisLine={false} tickLine={false} tickFormatter={(v) => `${v}d`} width={36} />
              <Tooltip
                content={({ active, payload, label }) => {
                  if (!active || !payload?.length) return null;
                  const d = payload[0]?.payload as { avg_cycle_days: number | null; deal_count: number };
                  return (
                    <div className="rounded-xl border border-zinc-700 bg-zinc-900 p-3 shadow-xl text-xs">
                      <p className="font-mono text-zinc-400 mb-1">{label}</p>
                      <p className="text-zinc-200">Avg: <span className="font-mono text-violet-300">{d.avg_cycle_days !== null ? `${d.avg_cycle_days}d` : "—"}</span></p>
                      <p className="text-zinc-500">{d.deal_count} deal{d.deal_count !== 1 ? "s" : ""} closed</p>
                    </div>
                  );
                }}
              />
              <Line type="monotone" dataKey="avg_cycle_days" stroke="#A78BFA" strokeWidth={2} dot={{ r: 3, fill: "#A78BFA" }} connectNulls />
            </LineChart>
          </ResponsiveContainer>
        </Card>
      )}

      {/* Expected revenue forecast (12u) */}
      {revenueForecast.length > 0 && (
        <Card>
          <div className="flex items-center justify-between mb-4">
            <div>
              <p className="text-sm font-semibold text-zinc-100">Expected Revenue Forecast</p>
              <p className="text-xs text-zinc-500 mt-0.5 font-mono">Probability-weighted revenue by close month</p>
            </div>
            <TrendingUp className="h-4 w-4 text-emerald-400" />
          </div>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={revenueForecast} margin={{ top: 4, right: 8, left: -8, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#27272A" vertical={false} />
              <XAxis dataKey="month" tick={{ fill: "#71717A", fontSize: 10 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: "#71717A", fontSize: 10 }} axisLine={false} tickLine={false} tickFormatter={(v) => `$${v / 1000}k`} width={44} />
              <Tooltip
                content={({ active, payload, label }) => {
                  if (!active || !payload?.length) return null;
                  const d = payload[0]?.payload as { expected_revenue: number; total_value: number; deal_count: number };
                  return (
                    <div className="rounded-xl border border-zinc-700 bg-zinc-900 p-3 shadow-xl text-xs">
                      <p className="font-mono text-zinc-400 mb-1">{label}</p>
                      <p className="text-emerald-300">Expected: {formatCurrency(d.expected_revenue)}</p>
                      <p className="text-zinc-400">Pipeline: {formatCurrency(d.total_value)}</p>
                      <p className="text-zinc-500">{d.deal_count} deal{d.deal_count !== 1 ? "s" : ""}</p>
                    </div>
                  );
                }}
              />
              <Bar dataKey="expected_revenue" name="Expected Revenue" fill="#10B981" radius={[4, 4, 0, 0]} maxBarSize={48} />
            </BarChart>
          </ResponsiveContainer>
        </Card>
      )}

      {/* Win probability by stage (12w) + Concentration risk (12y) */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {winProbByStage.length > 0 && (
          <Card>
            <div className="flex items-center justify-between mb-4">
              <div>
                <p className="text-sm font-semibold text-zinc-100">Win Probability by Stage</p>
                <p className="text-xs text-zinc-500 mt-0.5 font-mono">Avg ML probability for open deals</p>
              </div>
              <Target className="h-4 w-4 text-indigo-400" />
            </div>
            <ResponsiveContainer width="100%" height={160}>
              <BarChart data={winProbByStage.map((d) => ({ ...d, label: stageConfig[d.stage as keyof typeof stageConfig]?.label ?? d.stage }))} margin={{ top: 4, right: 8, left: -16, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#27272A" vertical={false} />
                <XAxis dataKey="label" tick={{ fill: "#71717A", fontSize: 10 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: "#71717A", fontSize: 10 }} axisLine={false} tickLine={false} domain={[0, 100]} tickFormatter={(v) => `${v}%`} width={36} />
                <Tooltip
                  content={({ active, payload, label }) => {
                    if (!active || !payload?.length) return null;
                    const d = payload[0]?.payload as { avg_probability: number; deal_count: number; total_value: number };
                    return (
                      <div className="rounded-xl border border-zinc-700 bg-zinc-900 p-3 shadow-xl text-xs">
                        <p className="font-mono text-zinc-400 mb-1">{label}</p>
                        <p className="text-indigo-300">Avg prob: {d.avg_probability}%</p>
                        <p className="text-zinc-400">{d.deal_count} deals · {formatCurrency(d.total_value)}</p>
                      </div>
                    );
                  }}
                />
                <Bar dataKey="avg_probability" radius={[4, 4, 0, 0]}>
                  {winProbByStage.map((entry) => (
                    <Cell key={entry.stage} fill={STAGE_COLORS[entry.stage] ?? "#6366F1"} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </Card>
        )}

        {concentrationRisk && (
          <Card>
            <div className="flex items-center justify-between mb-3">
              <div>
                <p className="text-sm font-semibold text-zinc-100">Pipeline Concentration Risk</p>
                <p className="text-xs text-zinc-500 mt-0.5 font-mono">Top-3 deal share of pipeline</p>
              </div>
              <span className={cn(
                "text-xs font-semibold px-2 py-0.5 rounded-full",
                concentrationRisk.risk_level === "high"   ? "bg-rose-500/20 text-rose-300" :
                concentrationRisk.risk_level === "medium" ? "bg-amber-500/20 text-amber-300" :
                                                            "bg-emerald-500/20 text-emerald-300"
              )}>
                {concentrationRisk.risk_level.toUpperCase()} · {concentrationRisk.top3_pct}%
              </span>
            </div>
            <div className="space-y-2 mt-2">
              {concentrationRisk.top_deals.map((d) => (
                <div key={d.id} className="flex items-center gap-2">
                  <div className="w-28 text-xs text-zinc-400 truncate">{d.company}</div>
                  <div className="flex-1 h-1.5 rounded-full bg-zinc-800 overflow-hidden">
                    <div className="h-full rounded-full bg-indigo-500" style={{ width: `${Math.min(100, d.pct_of_pipeline)}%` }} />
                  </div>
                  <div className="text-xs font-mono text-zinc-400 w-10 text-right">{d.pct_of_pipeline}%</div>
                </div>
              ))}
            </div>
            <p className="mt-3 text-[10px] text-zinc-600 font-mono">Total pipeline: {formatCurrency(concentrationRisk.total_pipeline_value)}</p>
          </Card>
        )}
      </div>

      {/* Deal stage aging (12v) */}
      {stageAging.length > 0 && (
        <Card>
          <div className="flex items-center justify-between mb-4">
            <div>
              <p className="text-sm font-semibold text-zinc-100">Deal Aging by Stage</p>
              <p className="text-xs text-zinc-500 mt-0.5 font-mono">Days each open deal has spent in current stage</p>
            </div>
            <Clock className="h-4 w-4 text-amber-400" />
          </div>
          <div className="divide-y divide-zinc-800">
            {stageAging.slice(0, 8).map((d) => (
              <div key={d.id} className="flex items-center gap-3 py-2">
                <span className={cn(
                  "text-xs px-1.5 py-0.5 rounded font-mono",
                  d.days_in_stage > 30 ? "bg-rose-900/30 text-rose-300" :
                  d.days_in_stage > 14 ? "bg-amber-900/30 text-amber-300" :
                                         "bg-emerald-900/20 text-emerald-400"
                )}>{d.days_in_stage}d</span>
                <div className="flex-1 min-w-0">
                  <p className="text-xs text-zinc-200 truncate">{d.title}</p>
                  <p className="text-[10px] text-zinc-500">{d.company} · {stageConfig[d.stage as keyof typeof stageConfig]?.label ?? d.stage}</p>
                </div>
                <p className="text-xs font-mono text-zinc-400">{formatCurrency(d.value)}</p>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* Close date accuracy (12z) + Close date slipped (12q) */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {closeDateAccuracy.length > 0 && (
          <Card>
            <div className="flex items-center justify-between mb-3">
              <div>
                <p className="text-sm font-semibold text-zinc-100">Close Date Accuracy</p>
                <p className="text-xs text-zinc-500 mt-0.5 font-mono">Expected vs actual close for won deals</p>
              </div>
            </div>
            <div className="divide-y divide-zinc-800">
              {closeDateAccuracy.slice(0, 5).map((d) => (
                <div key={d.id} className="flex items-center gap-3 py-2">
                  <span className={cn(
                    "text-xs px-1.5 py-0.5 rounded font-mono min-w-[52px] text-center",
                    d.outcome === "late"    ? "bg-rose-900/30 text-rose-300"    :
                    d.outcome === "early"   ? "bg-emerald-900/20 text-emerald-400" :
                                             "bg-zinc-800 text-zinc-400"
                  )}>
                    {d.days_delta > 0 ? `+${d.days_delta}d` : d.days_delta === 0 ? "on time" : `${d.days_delta}d`}
                  </span>
                  <div className="flex-1 min-w-0">
                    <p className="text-xs text-zinc-200 truncate">{d.title}</p>
                    <p className="text-[10px] text-zinc-500">{d.expected_close} → {d.actual_close}</p>
                  </div>
                </div>
              ))}
            </div>
          </Card>
        )}

        {closeDateSlipped.length > 0 && (
          <Card>
            <div className="flex items-center justify-between mb-3">
              <div>
                <p className="text-sm font-semibold text-zinc-100">Close Date Slipped</p>
                <p className="text-xs text-zinc-500 mt-0.5 font-mono">Open deals past their expected close date</p>
              </div>
              <CalendarOff className="h-4 w-4 text-rose-400" />
            </div>
            <div className="divide-y divide-zinc-800">
              {closeDateSlipped.map((d) => (
                <div key={d.id} className="flex items-center gap-3 py-2">
                  <span className="text-xs px-1.5 py-0.5 rounded bg-rose-900/30 text-rose-300 font-mono min-w-[44px] text-center">
                    +{d.days_overdue}d
                  </span>
                  <div className="flex-1 min-w-0">
                    <p className="text-xs text-zinc-200 truncate">{d.title}</p>
                    <p className="text-[10px] text-zinc-500">{d.company} · due {d.expected_close}</p>
                  </div>
                  <p className="text-xs font-mono text-zinc-400">{formatCurrency(d.value)}</p>
                </div>
              ))}
            </div>
          </Card>
        )}
      </div>

      {/* Activity trends (13a) */}
      {activityTrends.length > 0 && (
        <Card>
          <div className="flex items-center justify-between mb-4">
            <div>
              <p className="text-sm font-semibold text-zinc-100">Activity Trends</p>
              <p className="text-xs text-zinc-500 mt-0.5 font-mono">Weekly event counts by category</p>
            </div>
            <Activity className="h-4 w-4 text-violet-400" />
          </div>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={activityTrends.map((w) => ({ ...w, week: w.week_start.slice(0, 10) }))} margin={{ top: 4, right: 8, left: -16, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#27272A" vertical={false} />
              <XAxis dataKey="week" tick={{ fill: "#71717A", fontSize: 9 }} axisLine={false} tickLine={false} interval={2} />
              <YAxis tick={{ fill: "#71717A", fontSize: 10 }} axisLine={false} tickLine={false} allowDecimals={false} />
              <Tooltip
                content={({ active, payload, label }) => {
                  if (!active || !payload?.length) return null;
                  return (
                    <div className="rounded-xl border border-zinc-700 bg-zinc-900 p-3 shadow-xl text-xs">
                      <p className="font-mono text-zinc-400 mb-2">{label}</p>
                      {payload.map((p) => (
                        <div key={p.name} className="flex items-center gap-2" style={{ color: p.color }}>
                          <span className="capitalize">{p.name}:</span>
                          <span className="font-mono font-bold">{p.value}</span>
                        </div>
                      ))}
                    </div>
                  );
                }}
              />
              <Bar dataKey="deals"    name="deals"    stackId="a" fill="#6366F1" />
              <Bar dataKey="contacts" name="contacts" stackId="a" fill="#A78BFA" />
              <Bar dataKey="agents"   name="agents"   stackId="a" fill="#00C896" />
              <Bar dataKey="messages" name="messages" stackId="a" fill="#FBBF24" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </Card>
      )}

      {/* Contact re-engagement summary (13b) */}
      {reengagementSummary.length > 0 && reengagementSummary.some((w) => w.reengagement_count > 0) && (
        <Card>
          <div className="flex items-center justify-between mb-4">
            <div>
              <p className="text-sm font-semibold text-zinc-100">Contact Re-engagement</p>
              <p className="text-xs text-zinc-500 mt-0.5 font-mono">Contacts re-touched after 30+ day silence, by week</p>
            </div>
            <Zap className="h-4 w-4 text-emerald-400" />
          </div>
          <ResponsiveContainer width="100%" height={160}>
            <BarChart data={reengagementSummary.map((w) => ({ ...w, week: w.week_start.slice(0, 10) }))} margin={{ top: 4, right: 8, left: -16, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#27272A" vertical={false} />
              <XAxis dataKey="week" tick={{ fill: "#71717A", fontSize: 9 }} axisLine={false} tickLine={false} interval={2} />
              <YAxis tick={{ fill: "#71717A", fontSize: 10 }} axisLine={false} tickLine={false} allowDecimals={false} />
              <Tooltip
                content={({ active, payload, label }) => {
                  if (!active || !payload?.length) return null;
                  return (
                    <div className="rounded-xl border border-zinc-700 bg-zinc-900 p-3 shadow-xl text-xs">
                      <p className="font-mono text-zinc-400 mb-1">{label}</p>
                      <p className="text-emerald-300">{payload[0]?.value} re-engagement{(payload[0]?.value as number) !== 1 ? "s" : ""}</p>
                    </div>
                  );
                }}
              />
              <Bar dataKey="reengagement_count" name="Re-engagements" fill="#10B981" radius={[4, 4, 0, 0]} maxBarSize={32} />
            </BarChart>
          </ResponsiveContainer>
        </Card>
      )}

      {/* Contact pipeline contribution (12x) */}
      {pipelineContribution.length > 0 && (
        <Card>
          <div className="flex items-center justify-between mb-4">
            <div>
              <p className="text-sm font-semibold text-zinc-100">Contact Pipeline Contribution</p>
              <p className="text-xs text-zinc-500 mt-0.5 font-mono">Pipeline and won revenue by contact</p>
            </div>
            <Users className="h-4 w-4 text-indigo-400" />
          </div>
          <div className="divide-y divide-zinc-800">
            {pipelineContribution.slice(0, 8).map((c) => (
              <div key={c.contact_id} className="flex items-center gap-3 py-2">
                <div className="flex-1 min-w-0">
                  <p className="text-xs text-zinc-200 truncate">{c.name}</p>
                  <p className="text-[10px] text-zinc-500">{c.company} · {c.deal_count} deal{c.deal_count !== 1 ? "s" : ""} · {c.win_rate}% win</p>
                </div>
                <div className="text-right">
                  <p className="text-xs font-mono text-indigo-300">{formatCurrency(c.pipeline_value)}</p>
                  {c.closed_won_value > 0 && <p className="text-[10px] font-mono text-emerald-400">{formatCurrency(c.closed_won_value)} won</p>}
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* Revenue cohort heatmap (13c) */}
      {revenueCohort.length > 0 && (
        <Card>
          <div className="flex items-center justify-between mb-4">
            <div>
              <p className="text-sm font-semibold text-zinc-100">Revenue Cohort Analysis</p>
              <p className="text-xs text-zinc-500 mt-0.5 font-mono">Expansion revenue as % of initial by acquisition cohort</p>
            </div>
            <BarChart2 className="h-4 w-4 text-indigo-400" />
          </div>
          <div className="overflow-x-auto">
            <table className="text-xs w-full min-w-[480px]">
              <thead>
                <tr>
                  <th className="text-left pr-4 pb-2 text-zinc-500 font-mono">Cohort</th>
                  <th className="text-right pr-4 pb-2 text-zinc-500 font-mono">Initial</th>
                  {revenueCohort[0]?.months.map((_, i) => (
                    <th key={i} className="text-center px-1 pb-2 text-zinc-500 font-mono">M+{i}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {revenueCohort.map((cohort) => (
                  <tr key={cohort.cohort_month}>
                    <td className="pr-4 py-1 text-zinc-300">{cohort.cohort_month}</td>
                    <td className="pr-4 py-1 text-right text-zinc-300">{formatCurrency(cohort.initial_revenue)}</td>
                    {cohort.months.map((m) => {
                      const pct = m.pct_of_initial;
                      const bg =
                        pct === null ? "bg-zinc-800/30" :
                        pct === 0   ? "bg-zinc-800/50" :
                        pct >= 80   ? "bg-emerald-900/70" :
                        pct >= 50   ? "bg-emerald-900/50" :
                        pct >= 25   ? "bg-emerald-900/30" :
                                      "bg-emerald-900/15";
                      const textColor =
                        pct === null ? "text-zinc-700" :
                        pct === 0   ? "text-zinc-600" :
                        pct >= 50   ? "text-emerald-300" :
                                      "text-emerald-500";
                      return (
                        <td key={m.month_offset} className={`px-1 py-1 text-center rounded ${bg}`}>
                          <span className={textColor}>
                            {pct === null ? "—" : pct === 0 ? "0%" : `${pct}%`}
                          </span>
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-3 text-[10px] text-zinc-600 font-mono">
            Each row = contacts first acquired that month. Later columns show expansion revenue from those contacts as % of initial.
          </p>
        </Card>
      )}

      {/* Deal Scoring Leaderboard — Phase 13e */}
      {leaderboard.length > 0 && (
        <Card>
          <div className="flex items-center gap-2 mb-4">
            <Medal className="h-4 w-4 text-amber-400" />
            <h3 className="text-sm font-semibold text-zinc-200">Deal Scoring Leaderboard</h3>
            <span className="ml-auto text-xs text-zinc-500">top open deals · probability × value</span>
          </div>
          <table className="w-full text-xs font-mono">
            <thead>
              <tr>
                <th className="text-left text-zinc-500 pb-2 font-normal w-8">#</th>
                <th className="text-left text-zinc-500 pb-2 font-normal">Deal</th>
                <th className="text-left text-zinc-500 pb-2 font-normal hidden sm:table-cell">Stage</th>
                <th className="text-right text-zinc-500 pb-2 font-normal">Value</th>
                <th className="text-right text-zinc-500 pb-2 font-normal">Win%</th>
                <th className="text-right text-zinc-500 pb-2 font-normal">Score</th>
                <th className="text-center text-zinc-500 pb-2 font-normal w-8"></th>
              </tr>
            </thead>
            <tbody>
              {leaderboard.map((row) => {
                const rankColor = row.rank === 1 ? "text-amber-400" : row.rank === 2 ? "text-zinc-300" : row.rank === 3 ? "text-amber-700" : "text-zinc-600";
                const TrendIcon = row.trend === "up" ? ArrowUp : row.trend === "down" ? ArrowDown : Minus;
                const trendColor = row.trend === "up" ? "text-emerald-400" : row.trend === "down" ? "text-rose-400" : "text-zinc-600";
                return (
                  <tr key={row.id} className="border-t border-zinc-800/60">
                    <td className={`py-2 pr-2 font-bold ${rankColor}`}>{row.rank}</td>
                    <td className="py-2 pr-3">
                      <p className="text-zinc-200 truncate max-w-[160px]">{row.title ?? "—"}</p>
                      <p className="text-zinc-600 text-[10px]">{row.company ?? ""}</p>
                    </td>
                    <td className="py-2 pr-3 hidden sm:table-cell">
                      <span className="px-1.5 py-0.5 rounded text-[10px]" style={{ background: (STAGE_COLORS[row.stage] ?? "#52525B") + "33", color: STAGE_COLORS[row.stage] ?? "#71717A" }}>
                        {stageConfig[row.stage as keyof typeof stageConfig]?.label ?? row.stage}
                      </span>
                    </td>
                    <td className="py-2 pr-3 text-right text-zinc-300">{formatCurrency(row.value)}</td>
                    <td className="py-2 pr-3 text-right text-indigo-300">{row.ml_win_probability}%</td>
                    <td className="py-2 pr-3 text-right text-zinc-200 font-semibold">{(row.score / 1_000_000).toFixed(1)}M</td>
                    <td className="py-2 text-center">
                      <TrendIcon className={`h-3 w-3 ${trendColor} inline-block`} />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <p className="mt-3 text-[10px] text-zinc-600 font-mono">Score = value × win probability. Trend: ↑ active last 7d, ↓ stale or health &lt; 50.</p>
        </Card>
      )}

      {/* Contact Engagement Leaderboard — Phase 13f */}
      {contactLeaderboard.length > 0 && (
        <Card>
          <div className="flex items-center gap-2 mb-4">
            <Users className="h-4 w-4 text-emerald-400" />
            <h3 className="text-sm font-semibold text-zinc-200">Contact Engagement Leaderboard</h3>
            <span className="ml-auto text-xs text-zinc-500">top contacts · last 90 days</span>
          </div>
          <table className="w-full text-xs font-mono">
            <thead>
              <tr>
                <th className="text-left text-zinc-500 pb-2 font-normal w-8">#</th>
                <th className="text-left text-zinc-500 pb-2 font-normal">Contact</th>
                <th className="text-right text-zinc-500 pb-2 font-normal hidden sm:table-cell">Msgs</th>
                <th className="text-right text-zinc-500 pb-2 font-normal hidden sm:table-cell">Notes</th>
                <th className="text-right text-zinc-500 pb-2 font-normal">Tasks</th>
                <th className="text-right text-zinc-500 pb-2 font-normal">Score</th>
              </tr>
            </thead>
            <tbody>
              {contactLeaderboard.map((row) => {
                const rankColor = row.rank === 1 ? "text-amber-400" : row.rank === 2 ? "text-zinc-300" : row.rank === 3 ? "text-amber-700" : "text-zinc-600";
                return (
                  <tr key={row.contact_id} className="border-t border-zinc-800/60">
                    <td className={`py-2 pr-2 font-bold ${rankColor}`}>{row.rank}</td>
                    <td className="py-2 pr-3">
                      <p className="text-zinc-200 truncate max-w-[160px]">{row.name ?? "—"}</p>
                      <p className="text-zinc-600 text-[10px]">{row.company ?? row.email ?? ""}</p>
                    </td>
                    <td className="py-2 pr-3 text-right text-zinc-400 hidden sm:table-cell">{row.message_count}</td>
                    <td className="py-2 pr-3 text-right text-zinc-400 hidden sm:table-cell">{row.note_count}</td>
                    <td className="py-2 pr-3 text-right text-zinc-400">{Math.round(row.task_completion_rate * 100)}%</td>
                    <td className="py-2 text-right text-emerald-300 font-semibold">{row.score.toFixed(1)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <p className="mt-3 text-[10px] text-zinc-600 font-mono">Score = messages × 2 + notes × 3 + task completion rate × 20 (last 90 days)</p>
        </Card>
      )}

      {/* Stale alert */}
      {stats.stale > 0 && (
        <Card className="border-rose-500/15 flex items-center gap-3">
          <AlertTriangle className="h-4 w-4 text-rose-400 flex-shrink-0" />
          <p className="text-sm text-zinc-300">
            <span className="font-semibold text-rose-400">{stats.stale} deal{stats.stale !== 1 ? "s" : ""}</span> with health score below 40 — check Deal Health Alerts on the Dashboard or review each deal in the Pipeline.
          </p>
        </Card>
      )}
    </div>
  );
}
