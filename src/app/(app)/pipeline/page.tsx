"use client";

import { useState } from "react";
import Header from "@/components/layout/Header";
import Card from "@/components/ui/Card";
import Badge from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import { mockDeals } from "@/lib/mock-data";
import { cn, formatCurrency, stageConfig, dealStageOrder } from "@/lib/utils";
import { Brain, TrendingUp, Plus, BarChart3, DollarSign } from "lucide-react";
import type { Deal, DealStage } from "@/lib/types";

function WinProbabilityBar({ value }: { value: number }) {
  const color =
    value >= 70 ? "bg-emerald-400" : value >= 40 ? "bg-amber-400" : "bg-rose-400";
  return (
    <div className="flex items-center gap-2">
      <div
        className="h-1.5 flex-1 rounded-full bg-zinc-800 overflow-hidden"
        role="progressbar"
        aria-valuenow={value}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={`Win probability: ${value}%`}
      >
        <div className={cn("h-full rounded-full", color)} style={{ width: `${value}%` }} />
      </div>
      <span
        className={cn(
          "text-xs font-mono flex-shrink-0 w-9 text-right",
          value >= 70 ? "text-emerald-400" : value >= 40 ? "text-amber-400" : "text-rose-400"
        )}
      >
        {value}%
      </span>
    </div>
  );
}

function DealCard({ deal }: { deal: Deal }) {
  const stage = stageConfig[deal.stage];
  return (
    <div
      className="group rounded-xl border border-zinc-800 bg-zinc-900 p-3.5 hover:border-zinc-700 hover:bg-zinc-800/80 transition-all duration-200 cursor-pointer space-y-3"
      tabIndex={0}
      role="article"
      aria-label={`${deal.title} — ${formatCurrency(deal.value)}`}
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-2">
        <p className="text-sm font-semibold text-zinc-100 leading-snug group-hover:text-white transition-colors">
          {deal.title}
        </p>
        <span className="text-xs font-mono font-bold text-zinc-100 flex-shrink-0">
          {formatCurrency(deal.value)}
        </span>
      </div>

      {/* Company */}
      <div>
        <p className="text-xs text-zinc-400 truncate">{deal.company}</p>
        <p className="text-[10px] text-zinc-600 truncate">{deal.contactName}</p>
      </div>

      {/* Win probability */}
      {deal.stage !== "closed_won" && deal.stage !== "closed_lost" && (
        <div>
          <div className="flex items-center gap-1.5 mb-1.5">
            <Brain className="h-3 w-3 text-indigo-400" aria-hidden="true" />
            <span className="text-[10px] text-zinc-500 font-mono">ML Win Probability</span>
          </div>
          <WinProbabilityBar value={deal.mlWinProbability} />
        </div>
      )}

      {/* Footer */}
      <div className="flex items-center justify-between pt-1 border-t border-zinc-800">
        <span className="text-[10px] text-zinc-500 font-mono truncate">
          Closes {deal.expectedClose}
        </span>
        <span className="text-[10px] text-indigo-400 font-mono truncate flex-shrink-0">
          {deal.assignedAgent}
        </span>
      </div>
    </div>
  );
}

function StageColumn({ stage, deals }: { stage: DealStage; deals: Deal[] }) {
  const cfg = stageConfig[stage];
  const totalValue = deals.reduce((sum, d) => sum + d.value, 0);

  return (
    <div className="flex flex-col min-w-[240px] w-[240px] flex-shrink-0">
      {/* Column header */}
      <div className={cn("flex items-center justify-between rounded-xl border px-3 py-2.5 mb-3", cfg.bg, "border-zinc-800")}>
        <div className="flex items-center gap-2">
          <span className={cn("text-xs font-semibold", cfg.color)}>{cfg.label}</span>
          <span className="flex h-5 w-5 items-center justify-center rounded-full bg-zinc-800 text-[10px] font-mono text-zinc-400">
            {deals.length}
          </span>
        </div>
        {totalValue > 0 && (
          <span className="text-[10px] font-mono text-zinc-500">
            {formatCurrency(totalValue)}
          </span>
        )}
      </div>

      {/* Cards */}
      <div className="flex flex-col gap-2.5 min-h-[120px]">
        {deals.map((deal) => (
          <DealCard key={deal.id} deal={deal} />
        ))}
        {deals.length === 0 && (
          <div className="flex h-20 items-center justify-center rounded-xl border border-dashed border-zinc-800 text-xs text-zinc-600">
            No deals
          </div>
        )}
      </div>

      {/* Add deal */}
      {stage !== "closed_won" && stage !== "closed_lost" && (
        <button className="mt-2.5 flex items-center gap-2 rounded-xl border border-dashed border-zinc-800 px-3 py-2 text-xs text-zinc-600 hover:text-zinc-400 hover:border-zinc-700 transition-all duration-200 cursor-pointer focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 focus:ring-offset-zinc-950">
          <Plus className="h-3.5 w-3.5" aria-hidden="true" />
          Add deal
        </button>
      )}
    </div>
  );
}

export default function PipelinePage() {
  const [deals] = useState(mockDeals);

  const totalPipelineValue = deals
    .filter((d) => d.stage !== "closed_lost")
    .reduce((sum, d) => sum + d.value, 0);

  const wonValue = deals
    .filter((d) => d.stage === "closed_won")
    .reduce((sum, d) => sum + d.value, 0);

  const avgWinProb = deals
    .filter((d) => d.stage !== "closed_won" && d.stage !== "closed_lost")
    .reduce((sum, d, _, arr) => sum + d.mlWinProbability / arr.length, 0);

  return (
    <div className="flex flex-col gap-6 p-6 min-h-screen">
      <Header
        title="Pipeline"
        subtitle={`${deals.length} deals · ML win prediction active`}
      />

      {/* Summary bar */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Card className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-indigo-500/10 border border-indigo-500/20 flex-shrink-0">
            <DollarSign className="h-4 w-4 text-indigo-400" aria-hidden="true" />
          </div>
          <div>
            <p className="text-xs text-zinc-500">Pipeline Value</p>
            <p className="text-base font-bold font-mono text-zinc-100">{formatCurrency(totalPipelineValue)}</p>
          </div>
        </Card>
        <Card className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-emerald-500/10 border border-emerald-500/20 flex-shrink-0">
            <TrendingUp className="h-4 w-4 text-emerald-400" aria-hidden="true" />
          </div>
          <div>
            <p className="text-xs text-zinc-500">Closed Won</p>
            <p className="text-base font-bold font-mono text-emerald-400">{formatCurrency(wonValue)}</p>
          </div>
        </Card>
        <Card className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-amber-500/10 border border-amber-500/20 flex-shrink-0">
            <Brain className="h-4 w-4 text-amber-400" aria-hidden="true" />
          </div>
          <div>
            <p className="text-xs text-zinc-500">Avg Win Prob</p>
            <p className="text-base font-bold font-mono text-amber-400">{avgWinProb.toFixed(0)}%</p>
          </div>
        </Card>
        <Card className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-zinc-700/50 border border-zinc-700 flex-shrink-0">
            <BarChart3 className="h-4 w-4 text-zinc-400" aria-hidden="true" />
          </div>
          <div>
            <p className="text-xs text-zinc-500">Active Deals</p>
            <p className="text-base font-bold font-mono text-zinc-100">
              {deals.filter((d) => d.stage !== "closed_won" && d.stage !== "closed_lost").length}
            </p>
          </div>
        </Card>
      </div>

      {/* Pipeline Board */}
      <div className="flex-1">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Brain className="h-4 w-4 text-indigo-400" aria-hidden="true" />
            <span className="text-xs text-zinc-400 font-mono">
              ML win probability scored by Lead Scorer agent
            </span>
          </div>
          <Button variant="cta" size="sm">
            <Plus className="h-3.5 w-3.5" aria-hidden="true" />
            New Deal
          </Button>
        </div>

        <div
          className="flex gap-4 overflow-x-auto pb-4"
          role="region"
          aria-label="Deals pipeline board"
        >
          {dealStageOrder.map((stage) => (
            <StageColumn
              key={stage}
              stage={stage}
              deals={deals.filter((d) => d.stage === stage)}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
