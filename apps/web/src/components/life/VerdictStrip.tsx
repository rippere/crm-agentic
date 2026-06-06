"use client";

import { useMemo } from "react";
import Card from "@/components/ui/Card";
import { cn } from "@/lib/utils";
import type { KpiSnapshot } from "@/lib/types";
import {
  GitCommitHorizontal, Activity, Database, Brain,
  Trophy, CircleDashed, ArrowUp, ArrowDown, Minus,
} from "lucide-react";

const DAY_MS = 86400000;

// A snapshot belongs to weekly window `k` (0 = this week) when its date falls in
// [today - (7k+6) .. today - 7k]. We bucket by whole-day offset from today.
function dayOffset(dateIso: string, today: Date): number {
  const d = new Date(dateIso + "T00:00:00");
  const t = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  return Math.round((t.getTime() - d.getTime()) / DAY_MS);
}

export interface VerdictResult {
  thisWeek: number;
  baseline: number | null; // mean of prior-4 weekly sums, skipping no-coverage windows
  deltaPct: number | null; // null when no baseline
}

// Sum + baseline for snapshots matching `pred`. Baseline averages the prior 4
// 7-day windows; a window with no snapshots at all (zero coverage) is skipped,
// not counted as a zero — absence is unknown, not failure.
export function computeVerdict(snaps: KpiSnapshot[], pred: (s: KpiSnapshot) => boolean, today = new Date()): VerdictResult {
  const matched = snaps.filter(pred);
  // window index -> { sum, count }
  const windows = new Map<number, { sum: number; count: number }>();
  for (const s of matched) {
    const off = dayOffset(s.date, today);
    if (off < 0 || off > 34) continue; // only the 35-day frame (this week + 4 prior)
    const k = Math.floor(off / 7); // 0..4
    const w = windows.get(k) ?? { sum: 0, count: 0 };
    w.sum += s.value;
    w.count += 1;
    windows.set(k, w);
  }

  const thisWeek = windows.get(0)?.sum ?? 0;
  const priorSums: number[] = [];
  for (let k = 1; k <= 4; k++) {
    const w = windows.get(k);
    if (w && w.count > 0) priorSums.push(w.sum); // skip zero-coverage windows
  }
  const baseline = priorSums.length > 0
    ? priorSums.reduce((a, b) => a + b, 0) / priorSums.length
    : null;
  const deltaPct = baseline == null || baseline === 0
    ? null
    : Math.round(((thisWeek - baseline) / baseline) * 100);

  return { thisWeek, baseline, deltaPct };
}

// ─── Chip ─────────────────────────────────────────────────────────────────────
function VerdictChip({
  icon, label, result,
}: {
  icon: React.ReactNode;
  label: string;
  result: VerdictResult;
}) {
  const { thisWeek, baseline, deltaPct } = result;
  // Tone: up = green, down = red, no baseline = zinc. (More = good for all metrics.)
  const up = deltaPct != null && deltaPct > 0;
  const down = deltaPct != null && deltaPct < 0;
  const flat = deltaPct === 0;

  const tone = baseline == null
    ? "text-zinc-500"
    : up ? "text-[#00C896]" : down ? "text-rose-400" : "text-zinc-400";

  const arrow = baseline == null || flat
    ? <Minus className="h-3 w-3" aria-hidden="true" />
    : up ? <ArrowUp className="h-3 w-3" aria-hidden="true" /> : <ArrowDown className="h-3 w-3" aria-hidden="true" />;

  // A genuine zero this week against a real baseline reads as a loud "0 (was N/wk)".
  const droppedToZero = thisWeek === 0 && baseline != null && baseline > 0;

  return (
    <Card compact className="flex items-center gap-3">
      <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-zinc-800/60 border border-zinc-700 flex-shrink-0 text-indigo-400">
        {icon}
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline gap-2">
          <p className={cn("text-2xl font-bold font-mono tabular-nums leading-none", droppedToZero ? "text-rose-400" : "text-zinc-100")}>
            {thisWeek}
          </p>
          <span className={cn("inline-flex items-center gap-0.5 text-[11px] font-mono font-semibold", tone)}>
            {arrow}
            {baseline == null
              ? "no baseline"
              : droppedToZero
                ? `was ${Math.round(baseline)}/wk`
                : `${Math.abs(deltaPct as number)}%`}
          </span>
        </div>
        <p className="text-xs text-zinc-500 mt-1 truncate">{label}</p>
        <p className="text-[10px] text-zinc-600 font-mono mt-0.5 truncate">
          {baseline == null
            ? "no prior weeks to compare"
            : `this week vs ${Math.round(baseline)}/wk avg`}
        </p>
      </div>
    </Card>
  );
}

// ─── Standalone kept-rate / open chips (kept from v1, unchanged semantics) ──────
function StatChip({
  icon, iconTone, label, value, sublabel, valueTone,
}: {
  icon: React.ReactNode;
  iconTone: string;
  label: string;
  value: string;
  sublabel: string;
  valueTone: string;
}) {
  return (
    <Card compact className="flex items-center gap-3">
      <div className={cn("flex h-9 w-9 items-center justify-center rounded-xl bg-zinc-800/60 border border-zinc-700 flex-shrink-0", iconTone)}>
        {icon}
      </div>
      <div className="min-w-0 flex-1">
        <p className={cn("text-2xl font-bold font-mono tabular-nums leading-none", valueTone)}>{value}</p>
        <p className="text-xs text-zinc-500 mt-1 truncate">{label}</p>
        <p className="text-[10px] text-zinc-600 font-mono mt-0.5 truncate">{sublabel}</p>
      </div>
    </Card>
  );
}

interface VerdictStripProps {
  snapshots: KpiSnapshot[];
  keptRatePct: number | null;
  keptRateSub: string;
  openCount: number;
}

export default function VerdictStrip({ snapshots, keptRatePct, keptRateSub, openCount }: VerdictStripProps) {
  const verdicts = useMemo(() => {
    const today = new Date();
    return {
      commits: computeVerdict(snapshots, (s) => s.metric === "git_commits", today),
      sessions: computeVerdict(snapshots, (s) => s.metric === "sessions", today),
      // Records total across the knowledge + life domains (all records.* metrics).
      records: computeVerdict(
        snapshots,
        (s) => (s.domain === "knowledge" || s.domain === "life") && s.metric.startsWith("records."),
        today,
      ),
      topics: computeVerdict(snapshots, (s) => s.metric === "topics_distilled", today),
    };
  }, [snapshots]);

  return (
    <div className="grid grid-cols-2 gap-4 lg:grid-cols-3 xl:grid-cols-6">
      <StatChip
        icon={<Trophy className="h-4 w-4" />}
        iconTone="text-[#00C896]"
        label="Kept rate (latest week)"
        value={keptRatePct != null ? `${keptRatePct}%` : "—"}
        sublabel={keptRateSub}
        valueTone={keptRatePct == null ? "text-zinc-500" : "text-[#00C896]"}
      />
      <StatChip
        icon={<CircleDashed className="h-4 w-4" />}
        iconTone="text-indigo-400"
        label="Open commitments"
        value={String(openCount)}
        sublabel={openCount === 0 ? "all resolved" : "awaiting outcome"}
        valueTone="text-zinc-100"
      />
      <VerdictChip icon={<GitCommitHorizontal className="h-4 w-4" />} label="Commits this week" result={verdicts.commits} />
      <VerdictChip icon={<Activity className="h-4 w-4" />} label="Sessions this week" result={verdicts.sessions} />
      <VerdictChip icon={<Database className="h-4 w-4" />} label="Records this week" result={verdicts.records} />
      <VerdictChip icon={<Brain className="h-4 w-4" />} label="Topics distilled" result={verdicts.topics} />
    </div>
  );
}
