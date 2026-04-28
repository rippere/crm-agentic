import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";
import type { LeadScore, AgentStatus, DealStage } from "./types";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatCurrency(value: number): string {
  if (value >= 1_000_000) return `$${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `$${(value / 1_000).toFixed(0)}K`;
  return `$${value}`;
}

export const leadScoreConfig: Record<LeadScore, { bg: string; text: string; dot: string; label: string }> = {
  hot: {
    bg: "bg-emerald-500/10",
    text: "text-emerald-400",
    dot: "bg-emerald-400",
    label: "Hot",
  },
  warm: {
    bg: "bg-amber-500/10",
    text: "text-amber-400",
    dot: "bg-amber-400",
    label: "Warm",
  },
  cold: {
    bg: "bg-zinc-700/50",
    text: "text-zinc-400",
    dot: "bg-zinc-400",
    label: "Cold",
  },
};

export const agentStatusConfig: Record<AgentStatus, { bg: string; text: string; dot: string; label: string }> = {
  active: {
    bg: "bg-emerald-500/10",
    text: "text-emerald-400",
    dot: "bg-emerald-400",
    label: "Active",
  },
  processing: {
    bg: "bg-indigo-500/10",
    text: "text-indigo-400",
    dot: "bg-indigo-400",
    label: "Processing",
  },
  idle: {
    bg: "bg-zinc-700/50",
    text: "text-zinc-400",
    dot: "bg-zinc-500",
    label: "Idle",
  },
  error: {
    bg: "bg-rose-500/10",
    text: "text-rose-400",
    dot: "bg-rose-400",
    label: "Error",
  },
};

export const stageConfig: Record<DealStage, { label: string; color: string; bg: string }> = {
  discovery: { label: "Discovery", color: "text-zinc-400", bg: "bg-zinc-700/50" },
  qualified: { label: "Qualified", color: "text-indigo-400", bg: "bg-indigo-500/10" },
  proposal: { label: "Proposal", color: "text-amber-400", bg: "bg-amber-500/10" },
  negotiation: { label: "Negotiation", color: "text-violet-400", bg: "bg-violet-500/10" },
  closed_won: { label: "Closed Won", color: "text-[#00C896]", bg: "bg-[#00C896]/8" },
  closed_lost: { label: "Closed Lost", color: "text-rose-400", bg: "bg-rose-500/10" },
};

export const dealStageOrder: DealStage[] = [
  "discovery",
  "qualified",
  "proposal",
  "negotiation",
  "closed_won",
  "closed_lost",
];
