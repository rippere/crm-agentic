"use client";

import Card from "@/components/ui/Card";
import { cn } from "@/lib/utils";
import type { RetroMeta } from "@/lib/types";
import { Gavel, Trophy, Sprout, CheckCircle2, XCircle, CircleDashed } from "lucide-react";

interface RetroCardProps {
  /** Parsed `meta` of the latest `life_retro` event, or null when none exists. */
  retro: RetroMeta | null;
}

function CountChip({
  icon, label, value, tone,
}: {
  icon: React.ReactNode;
  label: string;
  value: number | undefined;
  tone: string;
}) {
  return (
    <div className="flex items-center gap-1.5">
      <span className={cn("flex-shrink-0", tone)} aria-hidden="true">{icon}</span>
      <span className="font-mono text-sm font-bold tabular-nums text-zinc-200">{value ?? 0}</span>
      <span className="text-[10px] text-zinc-500 font-mono uppercase tracking-wide">{label}</span>
    </div>
  );
}

export default function RetroCard({ retro }: RetroCardProps) {
  // ── Empty state — no retro event has ever landed ──
  if (!retro) {
    return (
      <Card accent="signal" className="flex flex-col items-center justify-center text-center py-10">
        <Gavel className="h-7 w-7 text-zinc-700 mb-3" aria-hidden="true" />
        <p className="text-sm font-semibold text-zinc-300">No retro yet</p>
        <p className="text-xs text-zinc-600 font-mono mt-1">Runs Sundays 18:00 — the agent harvests the week, scores it, and writes its verdict here.</p>
      </Card>
    );
  }

  const keptRatePct = retro.kept_rate == null ? null : Math.round(retro.kept_rate * 100);
  const judgment = (retro.judgment ?? []).filter((j) => typeof j === "string" && j.trim().length > 0);

  return (
    <Card accent="signal" className="flex flex-col gap-5">
      {/* Header + kept-rate headline */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-2.5 min-w-0">
          <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-[#00C896]/10 border border-[#00C896]/25 flex-shrink-0">
            <Gavel className="h-4 w-4 text-[#00C896]" aria-hidden="true" />
          </span>
          <div className="min-w-0">
            <p className="text-sm font-semibold text-zinc-100">
              Retro{retro.week ? ` — Week ${retro.week}` : ""}
            </p>
            <p className="text-xs text-zinc-500 mt-0.5 font-mono">the week, judged</p>
          </div>
        </div>
        <div className="text-right">
          {keptRatePct == null ? (
            <>
              <p className="text-2xl font-bold font-mono tabular-nums leading-none text-zinc-500">—</p>
              <p className="text-[10px] text-zinc-600 font-mono mt-1">first scored week lands Jun 14</p>
            </>
          ) : (
            <>
              <p className="text-3xl font-bold font-mono tabular-nums leading-none text-[#00C896] flex items-center gap-1.5 justify-end">
                <Trophy className="h-5 w-5" aria-hidden="true" />
                {keptRatePct}%
              </p>
              <p className="text-[10px] text-zinc-500 font-mono mt-1">kept this week</p>
            </>
          )}
        </div>
      </div>

      {/* Judgment — the dominant element. Readable prose, not a chart. */}
      {judgment.length > 0 ? (
        <ul className="space-y-3">
          {judgment.map((line, i) => (
            <li key={i} className="flex gap-3">
              <span className="mt-2 h-1.5 w-1.5 rounded-full bg-[#00C896] flex-shrink-0" aria-hidden="true" />
              <p className="text-sm text-zinc-200 leading-relaxed">{line}</p>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-zinc-500 italic">The retro ran but wrote no judgment for this week.</p>
      )}

      {/* Small counts row */}
      <div className="flex items-center gap-x-5 gap-y-2 flex-wrap pt-3 border-t border-zinc-800">
        <CountChip icon={<Sprout className="h-3.5 w-3.5" />}        label="harvested" value={retro.harvested} tone="text-zinc-400" />
        <CountChip icon={<CheckCircle2 className="h-3.5 w-3.5" />}  label="kept"      value={retro.kept}      tone="text-emerald-400" />
        <CountChip icon={<XCircle className="h-3.5 w-3.5" />}       label="broken"    value={retro.broken}    tone="text-rose-400" />
        <CountChip icon={<CircleDashed className="h-3.5 w-3.5" />}  label="open"      value={retro.open}      tone="text-indigo-400" />
      </div>
    </Card>
  );
}
