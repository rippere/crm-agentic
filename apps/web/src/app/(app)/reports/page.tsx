"use client";

import { useMemo } from "react";
import Header from "@/components/layout/Header";
import Card from "@/components/ui/Card";
import Badge from "@/components/ui/Badge";
import { useDeals } from "@/hooks/useDeals";
import { cn, formatCurrency, stageConfig, dealStageOrder } from "@/lib/utils";
import {
  BarChart, Bar, PieChart, Pie, Cell, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Legend, ComposedChart, Line,
} from "recharts";
import {
  TrendingUp, DollarSign, Target, BarChart2, AlertTriangle, Trophy,
} from "lucide-react";

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

export default function ReportsPage() {
  const { deals, loading } = useDeals();

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

    // Monthly revenue from closed_won deals (last 6 months)
    const now = new Date();
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
      const dt = new Date(d.createdAt);
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

    return { won, lost, active, winRate, wonValue, pipelineValue, avgDealSize, stale, byStage, topDeals, healthBuckets, revenueChart };
  }, [deals]);

  if (loading) {
    return (
      <div className="flex flex-col gap-6 p-6">
        <Header title="Reports" subtitle="Pipeline analytics and win rate" />
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          {[1, 2, 3, 4].map((i) => <div key={i} className="h-24 rounded-xl bg-zinc-800/50 animate-pulse" />)}
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6 p-6">
      <Header title="Reports" subtitle={`${deals.length} total deals · win rate ${stats.winRate}%`} />

      {/* KPI row */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-2 lg:grid-cols-4">
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
