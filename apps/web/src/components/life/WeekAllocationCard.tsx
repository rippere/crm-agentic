"use client";

import { useMemo, useState } from "react";
import Card from "@/components/ui/Card";
import Badge from "@/components/ui/Badge";
import { cn } from "@/lib/utils";
import type { KpiSnapshot } from "@/lib/types";
import {
  BarChart, Bar, XAxis, YAxis, Cell, LabelList, ResponsiveContainer, Tooltip,
} from "recharts";
import { FolderGit2 } from "lucide-react";

type Range = 30 | 90;

const DAY_MS = 86400000;
const TOP_N = 8;

// House palette, cycled across the repo bars.
const PALETTE = ["#6366F1", "#00C896", "#A78BFA", "#FBBF24", "#F43F5E", "#22D3EE", "#818CF8", "#34D399", "#FB923C"];

// git_commits `meta` carries per-project commit counts: { "crm-agentic": 4, ... }.
// It may arrive as an object or a JSON string — parse defensively, ignore junk.
function parseProjectCounts(meta: unknown): Record<string, number> {
  let obj: unknown = meta;
  if (typeof meta === "string") {
    try { obj = JSON.parse(meta); } catch { return {}; }
  }
  if (!obj || typeof obj !== "object" || Array.isArray(obj)) return {};
  const out: Record<string, number> = {};
  for (const [k, v] of Object.entries(obj as Record<string, unknown>)) {
    const n = typeof v === "number" ? v : typeof v === "string" ? Number(v) : NaN;
    if (Number.isFinite(n) && n > 0) out[k] = n;
  }
  return out;
}

interface Row {
  project: string;
  count: number;
  share: number;  // percent of total
  label: string;  // precomputed "count · share%" for the bar label (avoids value collisions)
}

function aggregate(snaps: KpiSnapshot[], range: Range): { rows: Row[]; total: number } {
  const cutoff = new Date(Date.now() - (range - 1) * DAY_MS).toISOString().slice(0, 10);
  const totals: Record<string, number> = {};
  for (const s of snaps) {
    if (s.metric !== "git_commits") continue;
    if (s.date < cutoff) continue;
    for (const [proj, n] of Object.entries(parseProjectCounts(s.meta))) {
      totals[proj] = (totals[proj] ?? 0) + n;
    }
  }
  const sorted = Object.entries(totals).sort((a, b) => b[1] - a[1]);
  const grand = sorted.reduce((acc, [, n]) => acc + n, 0);

  const top = sorted.slice(0, TOP_N);
  const rest = sorted.slice(TOP_N);
  const restSum = rest.reduce((acc, [, n]) => acc + n, 0);

  const mkRow = (project: string, count: number): Row => {
    const share = grand ? Math.round((count / grand) * 100) : 0;
    return { project, count, share, label: `${count} · ${share}%` };
  };
  const rows: Row[] = top.map(([project, count]) => mkRow(project, count));
  if (restSum > 0) rows.push(mkRow("other", restSum));
  return { rows, total: grand };
}

function AllocTooltip({ active, payload }: {
  active?: boolean;
  payload?: Array<{ payload: Row }>;
}) {
  if (!active || !payload?.length) return null;
  const row = payload[0]?.payload;
  if (!row) return null;
  return (
    <div className="rounded-xl border border-zinc-700 bg-zinc-900 p-3 shadow-xl text-xs">
      <p className="font-mono text-zinc-200 mb-1">{row.project}</p>
      <p className="text-zinc-400 font-mono">
        <span className="text-zinc-100 font-bold tabular-nums">{row.count}</span> commits · {row.share}%
      </p>
    </div>
  );
}

interface WeekAllocationCardProps {
  /** All snapshots (the card filters to git_commits itself). */
  snapshots: KpiSnapshot[];
}

export default function WeekAllocationCard({ snapshots }: WeekAllocationCardProps) {
  const [range, setRange] = useState<Range>(30);
  const { rows, total } = useMemo(() => aggregate(snapshots, range), [snapshots, range]);

  // Bar height scales with row count so labels stay legible.
  const chartHeight = Math.max(176, rows.length * 34 + 16);

  return (
    <Card accent="violet" className="flex flex-col">
      <div className="flex items-start justify-between mb-4 gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <span className="flex-shrink-0 text-indigo-400" aria-hidden="true"><FolderGit2 className="h-4 w-4" /></span>
          <div className="min-w-0">
            <p className="text-sm font-semibold text-zinc-100 truncate">Where the Week Went</p>
            <p className="text-xs text-zinc-500 mt-0.5 font-mono truncate">attention allocation by repo</p>
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

      {rows.length === 0 ? (
        <div className="flex h-44 flex-col items-center justify-center text-center">
          <FolderGit2 className="h-6 w-6 text-zinc-700 mb-2" aria-hidden="true" />
          <p className="text-xs text-zinc-500">No per-repo commit data in this window</p>
          <p className="text-[10px] text-zinc-600 font-mono mt-0.5">git_commits snapshots carry the per-project breakdown once the collector pushes it</p>
        </div>
      ) : (
        <div style={{ height: chartHeight }}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={rows}
              layout="vertical"
              margin={{ top: 0, right: 56, bottom: 0, left: 0 }}
              barCategoryGap={8}
            >
              <XAxis type="number" hide />
              <YAxis
                type="category"
                dataKey="project"
                tick={{ fill: "#A1A1AA", fontSize: 11 }}
                axisLine={false}
                tickLine={false}
                width={96}
              />
              <Tooltip content={<AllocTooltip />} cursor={{ fill: "rgba(99,102,241,0.06)" }} />
              <Bar dataKey="count" radius={[0, 4, 4, 0]} maxBarSize={22} isAnimationActive={false}>
                {rows.map((row, i) => (
                  <Cell key={row.project} fill={row.project === "other" ? "#52525B" : PALETTE[i % PALETTE.length]} />
                ))}
                <LabelList
                  dataKey="label"
                  position="right"
                  className="fill-zinc-400"
                  style={{ fontSize: 10, fontFamily: "var(--font-geist-mono, monospace)" }}
                />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {rows.length > 0 && (
        <p className="text-[10px] text-zinc-600 font-mono mt-3">
          {total} commits across {rows.length === TOP_N + 1 ? `${TOP_N}+` : rows.length} {rows.length === 1 ? "repo" : "repos"}. <Badge variant="zinc" size="sm">{range}-day window</Badge>
        </p>
      )}
    </Card>
  );
}
