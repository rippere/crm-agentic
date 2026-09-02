import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";
import type {
  LeadScore,
  AgentStatus,
  DealStage,
  LeadStage,
  CampaignStatus,
  SequenceStatus,
  EngagementLabel,
} from "./types";

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

// ─── Lead-Gen funnel + outbound config maps ──────────────────────────────────
// Same idiom as stageConfig / leadScoreConfig so the leads board, campaign
// badges, sequence badges, and score pills all pull colours/labels from one map.

export const funnelStageConfig: Record<LeadStage, { label: string; color: string; bg: string; dot: string }> = {
  new:       { label: "New",       color: "text-zinc-400",    bg: "bg-zinc-700/50",     dot: "bg-zinc-400" },
  contacted: { label: "Contacted", color: "text-sky-400",     bg: "bg-sky-500/10",      dot: "bg-sky-400" },
  engaged:   { label: "Engaged",   color: "text-indigo-400",  bg: "bg-indigo-500/10",   dot: "bg-indigo-400" },
  qualified: { label: "Qualified", color: "text-violet-400",  bg: "bg-violet-500/10",   dot: "bg-violet-400" },
  converted: { label: "Converted", color: "text-[#00C896]",   bg: "bg-[#00C896]/8",     dot: "bg-[#00C896]" },
  lost:      { label: "Lost",      color: "text-rose-400",    bg: "bg-rose-500/10",     dot: "bg-rose-400" },
};

export const funnelStageOrder: LeadStage[] = [
  "new",
  "contacted",
  "engaged",
  "qualified",
  "converted",
  "lost",
];

export const campaignStatusConfig: Record<CampaignStatus, { label: string; color: string; bg: string; dot: string }> = {
  draft:     { label: "Draft",     color: "text-zinc-400",    bg: "bg-zinc-700/50",    dot: "bg-zinc-400" },
  scheduled: { label: "Scheduled", color: "text-amber-400",   bg: "bg-amber-500/10",   dot: "bg-amber-400" },
  active:    { label: "Active",    color: "text-emerald-400", bg: "bg-emerald-500/10", dot: "bg-emerald-400" },
  paused:    { label: "Paused",    color: "text-orange-400",  bg: "bg-orange-500/10",  dot: "bg-orange-400" },
  completed: { label: "Completed", color: "text-indigo-400",  bg: "bg-indigo-500/10",  dot: "bg-indigo-400" },
  archived:  { label: "Archived",  color: "text-zinc-500",    bg: "bg-zinc-800/50",    dot: "bg-zinc-500" },
};

export const sequenceStatusConfig: Record<SequenceStatus, { label: string; color: string; bg: string; dot: string }> = {
  draft:    { label: "Draft",    color: "text-zinc-400",    bg: "bg-zinc-700/50",    dot: "bg-zinc-400" },
  active:   { label: "Active",   color: "text-emerald-400", bg: "bg-emerald-500/10", dot: "bg-emerald-400" },
  archived: { label: "Archived", color: "text-zinc-500",    bg: "bg-zinc-800/50",    dot: "bg-zinc-500" },
};

// Engagement-score band pill (mirrors leadScoreConfig hot/warm/cold).
export const engagementScoreConfig: Record<EngagementLabel, { bg: string; text: string; dot: string; label: string }> = {
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

// Map a 0-100 engagement score to its band (matches the scoring worker's
// thresholds: ≥70 hot, ≥40 warm, else cold).
export function engagementLabelFromScore(score: number): EngagementLabel {
  if (score >= 70) return "hot";
  if (score >= 40) return "warm";
  return "cold";
}

export const SIGNAL = "#10B981";
