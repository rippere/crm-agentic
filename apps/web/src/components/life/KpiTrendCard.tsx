"use client";

import { useMemo, useState } from "react";
import Card from "@/components/ui/Card";
import Badge from "@/components/ui/Badge";
import { cn } from "@/lib/utils";
import type { KpiSnapshot } from "@/lib/types";
import {
  AreaChart, Area, LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Legend,
} from "recharts";

type Range = 30 | 90;

export interface SeriesDef {
  /** KPI metric key, e.g. "git_commits" */
  metric: string;
  /** Legend / tooltip label */
  label: string;
  color: string;
}

export interface KpiTrendCardProps {
  title: string;
  subtitle?: string;
  icon: React.ReactNode;
  /** All snapshots for this card's domain (already filtered by domain). */
  snapshots: KpiSnapshot[];
  /** Line series to render (engineering, product, life). */
  lines?: SeriesDef[];
  /** Stacked-area series to render (knowledge). Stacked + has an extra line overlay. */
  stacked?: SeriesDef[];
  /** Optional single line drawn on top of a stacked area (e.g. topics_distilled). */
  overlayLine?: SeriesDef;
  accent?: "violet" | "signal" | "amber" | "rose" | "emerald";
}

const DAY_MS = 86400000;

// Build one row per calendar day in the window. A metric is `null` on days with
// no snapshot — Recharts skips nulls (connectNulls), so genuine gaps stay honest
// rather than being fabricated as zero.
function buildRows(snapshots: KpiSnapshot[], metrics: string[], range: Range) {
  const wanted = new Set(metrics);
  const byDate = new Map<string, Record<string, number>>();
  for (const s of snapshots) {
    if (!wanted.has(s.metric)) continue;
    const row = byDate.get(s.date) ?? {};
    row[s.metric] = s.value;
    byDate.set(s.date, row);
  }

  const today = new Date();
  const rows: Array<Record<string, number | string | null>> = [];
  for (let i = range - 1; i >= 0; i--) {
    const d = new Date(today.getTime() - i * DAY_MS);
    const key = d.toISOString().slice(0, 10);
    const found = byDate.get(key);
    const row: Record<string, number | string | null> = {
      date: d.toLocaleDateString("en-US", { month: "short", day: "numeric" }),
    };
    for (const m of metrics) row[m] = found?.[m] ?? null;
    rows.push(row);
  }
  return rows;
}

function TrendTooltip({
  active, payload, label, series,
}: {
  active?: boolean;
  payload?: { value: number | null; dataKey: string; color: string }[];
  label?: string;
  series: SeriesDef[];
}) {
  if (!active || !payload?.length) return null;
  const labelFor = (key: string) => series.find((s) => s.metric === key)?.label ?? key;
  const shown = payload.filter((p) => p.value != null);
  return (
    <div className="rounded-xl border border-zinc-700 bg-zinc-900 p-3 shadow-xl text-xs">
      <p className="font-mono text-zinc-400 mb-2">{label}</p>
      {shown.length === 0 ? (
        <p className="text-zinc-600 italic">no data</p>
      ) : (
        shown.map((p) => (
          <div key={p.dataKey} className="flex items-center gap-2">
            <span className="h-2 w-2 rounded-full flex-shrink-0" style={{ background: p.color }} />
            <span className="text-zinc-400">{labelFor(p.dataKey)}</span>
            <span className="text-zinc-200 font-mono ml-auto tabular-nums">{p.value}</span>
          </div>
        ))
      )}
    </div>
  );
}

export default function KpiTrendCard({
  title, subtitle, icon, snapshots, lines, stacked, overlayLine, accent = "violet",
}: KpiTrendCardProps) {
  const [range, setRange] = useState<Range>(30);

  const allSeries = useMemo<SeriesDef[]>(
    () => [...(stacked ?? []), ...(lines ?? []), ...(overlayLine ? [overlayLine] : [])],
    [lines, stacked, overlayLine],
  );

  const rows = useMemo(
    () => buildRows(snapshots, allSeries.map((s) => s.metric), range),
    [snapshots, allSeries, range],
  );

  // Has any non-null value at all in the window?
  const hasData = useMemo(
    () => rows.some((r) => allSeries.some((s) => r[s.metric] != null)),
    [rows, allSeries],
  );

  return (
    <Card accent={accent} className="flex flex-col">
      <div className="flex items-start justify-between mb-4 gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <span className="flex-shrink-0 text-indigo-400" aria-hidden="true">{icon}</span>
          <div className="min-w-0">
            <p className="text-sm font-semibold text-zinc-100 truncate">{title}</p>
            {subtitle && <p className="text-xs text-zinc-500 mt-0.5 font-mono truncate">{subtitle}</p>}
          </div>
        </div>
        <div className="flex items-center gap-1 flex-shrink-0">
          {([30, 90] as const).map((r) => (
            <button
              key={r}
              onClick={() => setRange(r)}
              className={cn(
                "rounded-md border px-2 py-1 text-[10px] font-mono font-semibold transition-all cursor-pointer",
                range === r
                  ? "border-indigo-500/40 bg-indigo-600/10 text-indigo-400"
                  : "border-zinc-800 bg-zinc-900 text-zinc-500 hover:border-zinc-700 hover:text-zinc-300",
              )}
              aria-pressed={range === r}
            >
              {r}d
            </button>
          ))}
        </div>
      </div>

      <div className="h-44">
        {!hasData ? (
          <div className="flex h-full flex-col items-center justify-center text-center">
            <span className="h-6 w-6 text-zinc-700 mb-2" aria-hidden="true">{icon}</span>
            <p className="text-xs text-zinc-500">No snapshots in this window</p>
            <p className="text-[10px] text-zinc-600 font-mono mt-0.5">The collector hasn&apos;t pushed {title.toLowerCase()} metrics yet</p>
          </div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            {stacked && stacked.length > 0 ? (
              <AreaChart data={rows} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
                <defs>
                  {stacked.map((s) => (
                    <linearGradient key={s.metric} id={`grad-${s.metric}`} x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor={s.color} stopOpacity={0.4} />
                      <stop offset="95%" stopColor={s.color} stopOpacity={0.05} />
                    </linearGradient>
                  ))}
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#27272A" vertical={false} />
                <XAxis dataKey="date" tick={{ fill: "#71717A", fontSize: 10 }} axisLine={false} tickLine={false} minTickGap={24} />
                <YAxis tick={{ fill: "#71717A", fontSize: 10 }} axisLine={false} tickLine={false} width={28} allowDecimals={false} />
                <Tooltip content={<TrendTooltip series={allSeries} />} />
                <Legend iconType="circle" iconSize={6} wrapperStyle={{ fontSize: "10px", color: "#71717A" }} />
                {stacked.map((s) => (
                  <Area
                    key={s.metric}
                    type="monotone"
                    dataKey={s.metric}
                    name={s.label}
                    stackId="1"
                    stroke={s.color}
                    strokeWidth={1.5}
                    fill={`url(#grad-${s.metric})`}
                    connectNulls
                    dot={false}
                  />
                ))}
                {overlayLine && (
                  <Area
                    type="monotone"
                    dataKey={overlayLine.metric}
                    name={overlayLine.label}
                    stroke={overlayLine.color}
                    strokeWidth={2}
                    strokeDasharray="4 3"
                    fill="none"
                    connectNulls
                    dot={false}
                  />
                )}
              </AreaChart>
            ) : (
              <LineChart data={rows} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#27272A" vertical={false} />
                <XAxis dataKey="date" tick={{ fill: "#71717A", fontSize: 10 }} axisLine={false} tickLine={false} minTickGap={24} />
                <YAxis tick={{ fill: "#71717A", fontSize: 10 }} axisLine={false} tickLine={false} width={28} allowDecimals={false} />
                <Tooltip content={<TrendTooltip series={allSeries} />} />
                <Legend iconType="circle" iconSize={6} wrapperStyle={{ fontSize: "10px", color: "#71717A" }} />
                {(lines ?? []).map((s) => (
                  <Line
                    key={s.metric}
                    type="monotone"
                    dataKey={s.metric}
                    name={s.label}
                    stroke={s.color}
                    strokeWidth={2}
                    dot={false}
                    activeDot={{ r: 4, fill: s.color }}
                    connectNulls
                  />
                ))}
              </LineChart>
            )}
          </ResponsiveContainer>
        )}
      </div>

      {hasData && (
        <p className="text-[10px] text-zinc-600 font-mono mt-3">
          Gaps are days with no snapshot — not zero. <Badge variant="zinc" size="sm">{range}-day window</Badge>
        </p>
      )}
    </Card>
  );
}
