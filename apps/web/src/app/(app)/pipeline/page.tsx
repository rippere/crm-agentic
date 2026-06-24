"use client";

import { useState, useCallback, useEffect } from "react";
import Header from "@/components/layout/Header";
import Card from "@/components/ui/Card";
import Button from "@/components/ui/Button";
import { useDeals } from "@/hooks/useDeals";
import { apiClient } from "@/lib/api-client";
import { createBrowserClient } from "@/lib/supabase";
import { cn, formatCurrency, stageConfig, dealStageOrder, SIGNAL } from "@/lib/utils";
import Link from "next/link";
import { Brain, TrendingUp, Plus, BarChart3, DollarSign, Heart, AlertTriangle, X, ChevronRight, Zap, ExternalLink, Download, Loader2, CheckSquare, Square, Trash2, ArrowRight, Search } from "lucide-react";
import type { Deal, DealStage } from "@/lib/types";

interface PipelineSuggestion {
  deal_id: string;
  title: string;
  company: string;
  stage: string;
  value: number;
  action: string;
  reason: string;
  priority: "high" | "medium";
}

interface AtRiskDeal {
  id: string;
  title: string | null;
  company: string | null;
  stage: string;
  value: number;
  ml_win_probability: number;
  days_since_activity: number;
  risk_reasons: string[];
}

function WinProbabilityBar({ value }: { value: number }) {
  const gradient =
    value >= 70
      ? `linear-gradient(90deg, #059669, ${SIGNAL})`
      : value >= 40
      ? "linear-gradient(90deg, #D97706, #FBBF24)"
      : "linear-gradient(90deg, #BE123C, #FB7185)";
  const textColor = value >= 70 ? SIGNAL : value >= 40 ? "#FBBF24" : "#FB7185";
  return (
    <div className="flex items-center gap-2">
      <div className="h-1 flex-1 rounded-full bg-zinc-800/80 overflow-hidden" role="progressbar" aria-valuenow={value} aria-valuemin={0} aria-valuemax={100}>
        <div className="h-full rounded-full" style={{ width: `${value}%`, background: gradient }} />
      </div>
      <span className="text-[10px] font-mono flex-shrink-0 w-8 text-right font-semibold" style={{ color: textColor }}>{value}%</span>
    </div>
  );
}

const stageBorderColor: Record<string, string> = {
  discovery:   "#52525B",
  qualified:   "#6366F1",
  proposal:    "#FBBF24",
  negotiation: "#A78BFA",
  closed_won:  "#00C896",
  closed_lost: "#F43F5E",
};

function DealCard({ deal, onSelect, selected, onToggleSelect, selectionActive }: {
  deal: Deal;
  onSelect: () => void;
  selected: boolean;
  onToggleSelect: (e: React.MouseEvent) => void;
  selectionActive: boolean;
}) {
  const borderColor = stageBorderColor[deal.stage] ?? "#52525B";
  return (
    <div
      className={cn(
        "group w-full text-left rounded-xl border bg-zinc-900/70 p-3.5 transition-all duration-200 cursor-pointer space-y-2.5 border-l-2",
        selected
          ? "border-indigo-500/60 bg-indigo-500/5"
          : "border-zinc-800/70 hover:border-zinc-700/80 hover:bg-zinc-900",
      )}
      style={{ borderLeftColor: selected ? "#6366F1" : borderColor }}
      onClick={selectionActive ? onToggleSelect : onSelect}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") selectionActive ? onToggleSelect(e as unknown as React.MouseEvent) : onSelect(); }}
      aria-label={`${deal.title} — ${formatCurrency(deal.value)}`}
      aria-pressed={selectionActive ? selected : undefined}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <button
            onClick={(e) => { e.stopPropagation(); onToggleSelect(e); }}
            className={cn(
              "flex-shrink-0 transition-opacity",
              selectionActive ? "opacity-100" : "opacity-0 group-hover:opacity-60",
            )}
            aria-label={selected ? "Deselect deal" : "Select deal"}
          >
            {selected
              ? <CheckSquare className="h-3.5 w-3.5 text-indigo-400" />
              : <Square className="h-3.5 w-3.5 text-zinc-500" />}
          </button>
          <p className="text-sm font-semibold text-zinc-100 leading-snug group-hover:text-white transition-colors truncate">{deal.title}</p>
        </div>
        <div className="flex items-center gap-1.5 flex-shrink-0">
          <Link
            href={`/pipeline/${deal.id}`}
            onClick={(e) => e.stopPropagation()}
            className="opacity-0 group-hover:opacity-100 transition-opacity text-zinc-600 hover:text-zinc-400 p-0.5"
            aria-label="Open deal detail"
          >
            <ExternalLink className="h-3 w-3" />
          </Link>
          <span className="text-xs font-mono font-bold text-zinc-100">{formatCurrency(deal.value)}</span>
        </div>
      </div>
      <div>
        <p className="text-xs text-zinc-400 truncate">{deal.company}</p>
        <p className="text-[10px] text-zinc-600 truncate">{deal.contactName}</p>
      </div>
      {deal.stage !== "closed_won" && deal.stage !== "closed_lost" && (
        <>
          <div>
            <div className="flex items-center gap-1.5 mb-1.5">
              <Brain className="h-3 w-3 text-indigo-400" />
              <span className="text-[10px] text-zinc-500 font-mono">ML Win Probability</span>
            </div>
            <WinProbabilityBar value={deal.mlWinProbability} />
          </div>
          <div className="flex items-center gap-1.5">
            {deal.healthScore >= 70
              ? <Heart className="h-3 w-3 text-emerald-400" />
              : <AlertTriangle className={cn("h-3 w-3", deal.healthScore >= 40 ? "text-amber-400" : "text-rose-400")} />}
            <div className="flex-1 h-1 rounded-full bg-zinc-800 overflow-hidden">
              <div
                className={cn("h-full rounded-full", deal.healthScore >= 70 ? "bg-emerald-400" : deal.healthScore >= 40 ? "bg-amber-400" : "bg-rose-500")}
                style={{ width: `${deal.healthScore}%` }}
              />
            </div>
            <span className={cn("text-[10px] font-mono w-6 text-right flex-shrink-0",
              deal.healthScore >= 70 ? "text-emerald-400" : deal.healthScore >= 40 ? "text-amber-400" : "text-rose-400"
            )}>{deal.healthScore}</span>
          </div>
        </>
      )}
      <div className="flex items-center justify-between pt-1 border-t border-zinc-800">
        <span className="text-[10px] text-zinc-500 font-mono truncate">Closes {deal.expectedClose}</span>
        <span className="text-[10px] text-indigo-400 font-mono truncate flex-shrink-0">{deal.assignedAgent}</span>
      </div>
    </div>
  );
}

function StageColumn({
  stage,
  deals,
  onSelect,
  onAddDeal,
  selectedIds,
  onToggleSelect,
}: {
  stage: DealStage;
  deals: Deal[];
  onSelect: (d: Deal) => void;
  onAddDeal: (stage: DealStage) => void;
  selectedIds: Set<string>;
  onToggleSelect: (id: string) => void;
}) {
  const cfg = stageConfig[stage];
  const totalValue = deals.reduce((sum, d) => sum + d.value, 0);
  const selectionActive = selectedIds.size > 0;
  return (
    <div className="flex flex-col min-w-[240px] w-[240px] flex-shrink-0">
      <div className={cn("flex items-center justify-between rounded-xl border px-3 py-2.5 mb-3", cfg.bg, "border-zinc-800")}>
        <div className="flex items-center gap-2">
          <span className={cn("text-xs font-semibold", cfg.color)}>{cfg.label}</span>
          <span className="flex h-5 w-5 items-center justify-center rounded-full bg-zinc-800 text-[10px] font-mono text-zinc-400">{deals.length}</span>
        </div>
        {totalValue > 0 && <span className="text-[10px] font-mono text-zinc-500">{formatCurrency(totalValue)}</span>}
      </div>
      <div className="flex flex-col gap-2.5 min-h-[120px]">
        {deals.map((deal) => (
          <DealCard
            key={deal.id}
            deal={deal}
            onSelect={() => onSelect(deal)}
            selected={selectedIds.has(deal.id)}
            onToggleSelect={(e) => { e.stopPropagation(); onToggleSelect(deal.id); }}
            selectionActive={selectionActive}
          />
        ))}
        {deals.length === 0 && (
          <div className="flex h-20 items-center justify-center rounded-xl border border-dashed border-zinc-800 text-xs text-zinc-600">No deals</div>
        )}
      </div>
      {stage !== "closed_won" && stage !== "closed_lost" && (
        <button
          onClick={() => onAddDeal(stage)}
          className="mt-2.5 flex items-center gap-2 rounded-xl border border-dashed border-zinc-800 px-3 py-2 text-xs text-zinc-600 hover:text-zinc-400 hover:border-zinc-700 transition-all duration-200 cursor-pointer"
        >
          <Plus className="h-3.5 w-3.5" /> Add deal
        </button>
      )}
    </div>
  );
}

function DealDetailPanel({ deal, onClose, onStageChange }: { deal: Deal; onClose: () => void; onStageChange: (stage: DealStage) => void }) {
  const [saving, setSaving] = useState(false);
  const stages = dealStageOrder.filter((s) => s !== deal.stage);

  const handleMove = async (stage: DealStage) => {
    setSaving(true);
    await onStageChange(stage);
    setSaving(false);
  };

  return (
    <aside className="fixed right-0 top-0 h-full w-full max-w-[400px] border-l border-zinc-800 bg-zinc-950 z-40 overflow-y-auto">
      <div className="sticky top-0 flex items-center justify-between border-b border-zinc-800 bg-zinc-950/90 backdrop-blur px-5 py-4">
        <div>
          <p className="text-sm font-semibold text-zinc-100 truncate">{deal.title}</p>
          <p className="text-[10px] text-zinc-500 font-mono">{deal.company}</p>
        </div>
        <button onClick={onClose} className="text-zinc-400 hover:text-zinc-100 transition-colors cursor-pointer" aria-label="Close">
          <X className="h-4 w-4" />
        </button>
      </div>

      <div className="p-5 space-y-5">
        {/* Value + stage */}
        <div className="grid grid-cols-2 gap-3">
          <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-3">
            <p className="text-[10px] text-zinc-500 mb-1">Value</p>
            <p className="text-lg font-bold font-mono text-zinc-100">{formatCurrency(deal.value)}</p>
          </div>
          <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-3">
            <p className="text-[10px] text-zinc-500 mb-1">Health</p>
            <p className={cn("text-lg font-bold font-mono",
              deal.healthScore >= 70 ? "text-emerald-400" : deal.healthScore >= 40 ? "text-amber-400" : "text-rose-400"
            )}>{deal.healthScore}/100</p>
          </div>
        </div>

        {/* ML win probability */}
        {deal.stage !== "closed_won" && deal.stage !== "closed_lost" && (
          <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-4">
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2">
                <Brain className="h-3.5 w-3.5 text-indigo-400" />
                <span className="text-xs text-zinc-400">ML Win Probability</span>
              </div>
              <span className="text-sm font-bold font-mono text-indigo-300">{deal.mlWinProbability}%</span>
            </div>
            <WinProbabilityBar value={deal.mlWinProbability} />
          </div>
        )}

        {/* Info */}
        <div className="space-y-2">
          {deal.contactName && (
            <div className="flex items-center justify-between text-xs">
              <span className="text-zinc-500">Contact</span>
              <span className="text-zinc-200">{deal.contactName}</span>
            </div>
          )}
          {deal.expectedClose && (
            <div className="flex items-center justify-between text-xs">
              <span className="text-zinc-500">Expected close</span>
              <span className="text-zinc-200 font-mono">{deal.expectedClose}</span>
            </div>
          )}
          {deal.assignedAgent && (
            <div className="flex items-center justify-between text-xs">
              <span className="text-zinc-500">Assigned agent</span>
              <span className="text-indigo-400 font-mono">{deal.assignedAgent}</span>
            </div>
          )}
        </div>

        {/* Move stage */}
        <div>
          <p className="text-[11px] text-zinc-500 uppercase tracking-widest font-mono mb-2">Move to stage</p>
          <div className="flex flex-col gap-1.5">
            {stages.map((s) => {
              const cfg = stageConfig[s];
              return (
                <button
                  key={s}
                  onClick={() => handleMove(s)}
                  disabled={saving}
                  className={cn(
                    "flex items-center justify-between rounded-lg border border-zinc-800 px-3 py-2.5 text-xs transition-all hover:border-zinc-700",
                    cfg.bg, saving && "opacity-50 cursor-not-allowed"
                  )}
                >
                  <span className={cn("font-medium", cfg.color)}>{cfg.label}</span>
                  <ChevronRight className="h-3 w-3 text-zinc-600" />
                </button>
              );
            })}
          </div>
        </div>

        {deal.notes && (
          <div>
            <p className="text-[11px] text-zinc-500 uppercase tracking-widest font-mono mb-2">Notes</p>
            <p className="text-xs text-zinc-400 leading-relaxed">{deal.notes}</p>
          </div>
        )}
      </div>
    </aside>
  );
}

interface NewDealForm {
  title: string;
  company: string;
  value: string;
  stage: DealStage;
  expectedClose: string;
}

function NewDealModal({ defaultStage, onClose, onCreate }: { defaultStage: DealStage; onClose: () => void; onCreate: (f: NewDealForm) => Promise<void> }) {
  const [form, setForm] = useState<NewDealForm>({ title: "", company: "", value: "", stage: defaultStage, expectedClose: "" });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.title.trim()) return;
    setSaving(true);
    setError(null);
    try {
      await onCreate(form);
      onClose();
    } catch (err) {
      // Surface the failure instead of hanging on "Creating…" forever.
      setError(err instanceof Error && err.message ? err.message : "Couldn't create the deal. Please try again.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-4" onClick={onClose}>
      <div className="w-full max-w-md rounded-2xl border border-zinc-800 bg-zinc-950 shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b border-zinc-800 px-5 py-4">
          <p className="text-sm font-semibold text-zinc-100">New Deal</p>
          <button onClick={onClose} className="text-zinc-400 hover:text-zinc-100 transition-colors cursor-pointer"><X className="h-4 w-4" /></button>
        </div>
        <form onSubmit={handleSubmit} className="p-5 space-y-4">
          {[
            { label: "Deal title *", key: "title", placeholder: "Enterprise Plan — Acme Corp", type: "text" },
            { label: "Company", key: "company", placeholder: "Acme Corp", type: "text" },
            { label: "Value ($)", key: "value", placeholder: "50000", type: "number" },
            { label: "Expected close", key: "expectedClose", placeholder: "Q3 2026", type: "text" },
          ].map(({ label, key, placeholder, type }) => (
            <div key={key}>
              <label className="block text-xs font-medium text-zinc-400 mb-1.5">{label}</label>
              <input
                type={type}
                value={form[key as keyof NewDealForm]}
                onChange={(e) => setForm((f) => ({ ...f, [key]: e.target.value }))}
                placeholder={placeholder}
                className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3.5 py-2.5 text-base sm:text-sm text-zinc-100 placeholder-zinc-600 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 transition"
              />
            </div>
          ))}
          <div>
            <label className="block text-xs font-medium text-zinc-400 mb-1.5">Stage</label>
            <select
              value={form.stage}
              onChange={(e) => setForm((f) => ({ ...f, stage: e.target.value as DealStage }))}
              className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3.5 py-2.5 text-base sm:text-sm text-zinc-100 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 transition"
            >
              {dealStageOrder.filter((s) => s !== "closed_won" && s !== "closed_lost").map((s) => (
                <option key={s} value={s}>{stageConfig[s].label}</option>
              ))}
            </select>
          </div>
          {error && (
            <p role="alert" className="text-xs text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">
              {error}
            </p>
          )}
          <div className="flex gap-2 pt-1">
            <Button type="button" variant="secondary" className="flex-1 justify-center" onClick={onClose}>Cancel</Button>
            <Button type="submit" variant="primary" className="flex-1 justify-center" disabled={saving || !form.title.trim()}>
              {saving ? "Creating…" : "Create Deal"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}

const LS_PIPELINE_SEARCH_KEY = "pipeline_search";

export default function PipelinePage() {
  const { deals, loading, createDeal, updateDeal, refetch } = useDeals();
  const [selectedDeal, setSelectedDeal] = useState<Deal | null>(null);
  const [newDealStage, setNewDealStage] = useState<DealStage | null>(null);
  const [dealSearch, setDealSearch] = useState(() => {
    if (typeof window === "undefined") return "";
    return localStorage.getItem(LS_PIPELINE_SEARCH_KEY) ?? "";
  });
  const [suggestions, setSuggestions] = useState<PipelineSuggestion[]>([]);
  const [suggestionsDismissed, setSuggestionsDismissed] = useState(false);
  const [atRiskDeals, setAtRiskDeals] = useState<AtRiskDeal[]>([]);
  const [atRiskDismissed, setAtRiskDismissed] = useState(false);
  const [exportLoading, setExportLoading] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [bulkStageTarget, setBulkStageTarget] = useState<DealStage | null>(null);
  const [bulkLoading, setBulkLoading] = useState(false);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setSelectedDeal(null); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    const isDemoMode = process.env.NEXT_PUBLIC_DEMO_MODE === "true";
    if (isDemoMode) {
      apiClient.getPipelineSuggestions("demo-workspace-1", "demo-token")
        .then((data) => { if (Array.isArray(data)) setSuggestions(data as PipelineSuggestion[]); })
        .catch(() => {});
      return;
    }
    const supabase = createBrowserClient();
    supabase.auth.getSession().then(({ data: { session } }) => {
      if (!session) return;
      const workspaceId: string | undefined = (session.user.app_metadata?.workspace_id ?? session.user.user_metadata?.workspace_id);
      if (!workspaceId) return;
      apiClient.getPipelineSuggestions(workspaceId, session.access_token)
        .then((data) => { if (Array.isArray(data)) setSuggestions(data as PipelineSuggestion[]); })
        .catch(() => {});
    });
  }, []);

  useEffect(() => {
    const isDemoMode = process.env.NEXT_PUBLIC_DEMO_MODE === "true";
    if (isDemoMode) {
      apiClient.getAtRiskDeals("demo-workspace-1", "demo-token")
        .then((data) => { if (Array.isArray(data)) setAtRiskDeals(data); })
        .catch(() => {});
      return;
    }
    const supabase = createBrowserClient();
    supabase.auth.getSession().then(({ data: { session } }) => {
      if (!session) return;
      const workspaceId: string | undefined = (session.user.app_metadata?.workspace_id ?? session.user.user_metadata?.workspace_id);
      if (!workspaceId) return;
      apiClient.getAtRiskDeals(workspaceId, session.access_token)
        .then((data) => { if (Array.isArray(data)) setAtRiskDeals(data); })
        .catch(() => {});
    });
  }, []);

  // Persist search to localStorage
  useEffect(() => { localStorage.setItem(LS_PIPELINE_SEARCH_KEY, dealSearch); }, [dealSearch]);

  const filteredDeals = dealSearch.trim()
    ? deals.filter((d) => {
        const q = dealSearch.toLowerCase();
        return (
          (d.title ?? "").toLowerCase().includes(q) ||
          (d.company ?? "").toLowerCase().includes(q)
        );
      })
    : deals;

  const totalPipelineValue = deals.filter((d) => d.stage !== "closed_lost").reduce((s, d) => s + d.value, 0);
  const wonValue = deals.filter((d) => d.stage === "closed_won").reduce((s, d) => s + d.value, 0);
  const activDeals = deals.filter((d) => d.stage !== "closed_won" && d.stage !== "closed_lost");
  const avgWinProb = activDeals.length > 0 ? activDeals.reduce((s, d) => s + d.mlWinProbability, 0) / activDeals.length : 0;
  const staleCount = activDeals.filter((d) => d.healthScore < 40).length;

  const handleStageChange = useCallback(async (stage: DealStage) => {
    if (!selectedDeal) return;
    await updateDeal(selectedDeal.id, { stage, stage_changed_at: new Date().toISOString() } as Partial<Deal> & { stage_changed_at?: string });
    setSelectedDeal((prev) => prev ? { ...prev, stage } : null);
  }, [selectedDeal, updateDeal]);

  const handleCreate = useCallback(async (form: NewDealForm) => {
    await createDeal({
      title: form.title,
      company: form.company,
      value: form.value ? parseFloat(form.value) : 0,
      stage: form.stage,
      // Supabase column is expected_close (snake_case) — cast through unknown
      ...({ expected_close: form.expectedClose || null } as unknown as Partial<Deal>),
    });
  }, [createDeal]);

  const handleToggleSelect = useCallback((id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }, []);

  const handleClearSelection = useCallback(() => setSelectedIds(new Set()), []);

  const handleBulkDelete = useCallback(async () => {
    if (!selectedIds.size || bulkLoading) return;
    setBulkLoading(true);
    try {
      const isDemoMode = process.env.NEXT_PUBLIC_DEMO_MODE === "true";
      if (!isDemoMode) {
        const supabase = createBrowserClient();
        const { data: { session } } = await supabase.auth.getSession();
        const workspaceId = (session?.user?.app_metadata?.workspace_id ?? session?.user?.user_metadata?.workspace_id) ?? "";
        const token = session?.access_token ?? "";
        if (workspaceId && token) {
          await apiClient.bulkDealAction(workspaceId, { action: "delete", deal_ids: Array.from(selectedIds) }, token);
        }
      }
      setSelectedIds(new Set());
      await refetch();
    } catch { /* silent */ }
    finally { setBulkLoading(false); }
  }, [selectedIds, bulkLoading, refetch]);

  const handleBulkMoveStage = useCallback(async (stage: DealStage) => {
    if (!selectedIds.size || bulkLoading) return;
    setBulkLoading(true);
    try {
      const isDemoMode = process.env.NEXT_PUBLIC_DEMO_MODE === "true";
      if (!isDemoMode) {
        const supabase = createBrowserClient();
        const { data: { session } } = await supabase.auth.getSession();
        const workspaceId = (session?.user?.app_metadata?.workspace_id ?? session?.user?.user_metadata?.workspace_id) ?? "";
        const token = session?.access_token ?? "";
        if (workspaceId && token) {
          await apiClient.bulkDealAction(workspaceId, { action: "move_stage", deal_ids: Array.from(selectedIds), stage }, token);
        }
      }
      setSelectedIds(new Set());
      setBulkStageTarget(null);
      await (refetch as () => Promise<void>)();
    } catch { /* silent */ }
    finally { setBulkLoading(false); }
  }, [selectedIds, bulkLoading, refetch]);

  const handleExportCsv = useCallback(async () => {
    if (exportLoading) return;
    setExportLoading(true);
    try {
      const isDemoMode = process.env.NEXT_PUBLIC_DEMO_MODE === "true";
      let workspaceId = "demo-workspace-1";
      let token = "demo-token";
      if (!isDemoMode) {
        const supabase = createBrowserClient();
        const { data: { session } } = await supabase.auth.getSession();
        workspaceId = (session?.user?.app_metadata?.workspace_id ?? session?.user?.user_metadata?.workspace_id) ?? "";
        token = session?.access_token ?? "";
      }
      if (!workspaceId || !token) return;
      const blob = await apiClient.exportDealsCsv(workspaceId, token);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "deals.csv";
      a.click();
      URL.revokeObjectURL(url);
    } catch { /* silent */ }
    finally { setExportLoading(false); }
  }, [exportLoading]);

  return (
    <div className="flex flex-col gap-6 p-4 md:p-6 min-h-screen">
      <Header title="Pipeline" subtitle={`${deals.length} deals · ML win prediction active`} />

      {/* Pipeline Optimizer Suggestions */}
      {suggestions.length > 0 && !suggestionsDismissed && (
        <Card className="border-indigo-500/20 bg-indigo-500/5">
          <div className="flex items-start gap-3">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-indigo-500/10 border border-indigo-500/20">
              <Zap className="h-4 w-4 text-indigo-400" />
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center justify-between mb-2">
                <p className="text-sm font-semibold text-zinc-100">
                  Pipeline Optimizer — {suggestions.length} suggestion{suggestions.length !== 1 ? "s" : ""}
                </p>
                <button
                  onClick={() => setSuggestionsDismissed(true)}
                  className="text-zinc-600 hover:text-zinc-400 transition-colors"
                  aria-label="Dismiss suggestions"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
              <div className="space-y-2">
                {suggestions.slice(0, 3).map((s) => (
                  <div key={s.deal_id} className="flex items-center gap-3 rounded-lg bg-zinc-900/60 px-3 py-2">
                    <span className={cn(
                      "h-1.5 w-1.5 rounded-full flex-shrink-0",
                      s.priority === "high" ? "bg-rose-400" : "bg-amber-400"
                    )} />
                    <div className="flex-1 min-w-0">
                      <span className="text-xs font-medium text-zinc-200">{s.title}</span>
                      <span className="text-xs text-zinc-500 ml-2">· {s.reason}</span>
                    </div>
                    <span className="text-[10px] font-mono text-zinc-500 flex-shrink-0">{formatCurrency(s.value)}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </Card>
      )}

      {/* At-risk early warning banner */}
      {atRiskDeals.length > 0 && !atRiskDismissed && (
        <Card className="border-amber-500/20 bg-amber-500/5">
          <div className="flex items-start gap-3">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-amber-500/10 border border-amber-500/20">
              <AlertTriangle className="h-4 w-4 text-amber-400" />
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center justify-between mb-2">
                <p className="text-sm font-semibold text-zinc-100">
                  At-Risk Deals — {atRiskDeals.length} deal{atRiskDeals.length !== 1 ? "s" : ""} need attention
                </p>
                <button
                  onClick={() => setAtRiskDismissed(true)}
                  className="text-zinc-600 hover:text-zinc-400 transition-colors"
                  aria-label="Dismiss at-risk warning"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
              <div className="space-y-2">
                {atRiskDeals.slice(0, 4).map((d) => (
                  <div key={d.id} className="flex items-center gap-3 rounded-lg bg-zinc-900/60 px-3 py-2">
                    <span className="h-1.5 w-1.5 rounded-full flex-shrink-0 bg-amber-400" />
                    <div className="flex-1 min-w-0">
                      <span className="text-xs font-medium text-zinc-200">{d.title}</span>
                      <span className="text-xs text-zinc-500 ml-2">·&nbsp;
                        {d.risk_reasons.map((r) =>
                          r === "low_win_probability" ? `${d.ml_win_probability}% win prob` :
                          r === "no_recent_activity" ? `${d.days_since_activity}d no activity` :
                          "overdue action"
                        ).join(", ")}
                      </span>
                    </div>
                    <Link
                      href={`/pipeline/${d.id}`}
                      className="text-[10px] font-mono text-zinc-500 hover:text-indigo-400 transition-colors flex-shrink-0 flex items-center gap-1"
                    >
                      {formatCurrency(d.value)}
                      <ChevronRight className="h-3 w-3" />
                    </Link>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </Card>
      )}

      {/* Summary bar */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        <Card className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-indigo-500/10 border border-indigo-500/20 flex-shrink-0">
            <DollarSign className="h-4 w-4 text-indigo-400" />
          </div>
          <div>
            <p className="text-xs text-zinc-500">Pipeline Value</p>
            <p className="text-base font-bold font-mono text-zinc-100">{formatCurrency(totalPipelineValue)}</p>
          </div>
        </Card>
        <Card className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-emerald-500/10 border border-emerald-500/20 flex-shrink-0">
            <TrendingUp className="h-4 w-4 text-emerald-400" />
          </div>
          <div>
            <p className="text-xs text-zinc-500">Closed Won</p>
            <p className="text-base font-bold font-mono text-emerald-400">{formatCurrency(wonValue)}</p>
          </div>
        </Card>
        <Card className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-amber-500/10 border border-amber-500/20 flex-shrink-0">
            <Brain className="h-4 w-4 text-amber-400" />
          </div>
          <div>
            <p className="text-xs text-zinc-500">Avg Win Prob</p>
            <p className="text-base font-bold font-mono text-amber-400">{avgWinProb.toFixed(0)}%</p>
          </div>
        </Card>
        <Card className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-zinc-700/50 border border-zinc-700 flex-shrink-0">
            <BarChart3 className="h-4 w-4 text-zinc-400" />
          </div>
          <div>
            <p className="text-xs text-zinc-500">Active Deals</p>
            <p className="text-base font-bold font-mono text-zinc-100">{activDeals.length}</p>
          </div>
        </Card>
        <Card className={cn("flex items-center gap-3", staleCount > 0 && "border-rose-500/20 bg-rose-500/5")}>
          <div className={cn("flex h-9 w-9 items-center justify-center rounded-xl flex-shrink-0",
            staleCount > 0 ? "bg-rose-500/10 border border-rose-500/20" : "bg-zinc-700/50 border border-zinc-700"
          )}>
            <AlertTriangle className={cn("h-4 w-4", staleCount > 0 ? "text-rose-400" : "text-zinc-400")} />
          </div>
          <div>
            <p className="text-xs text-zinc-500">Stale Deals</p>
            <p className={cn("text-base font-bold font-mono", staleCount > 0 ? "text-rose-400" : "text-zinc-100")}>{staleCount}</p>
          </div>
        </Card>
      </div>

      {/* Pipeline Board */}
      <div className="flex-1">
        <div className="flex flex-wrap items-center gap-3 mb-4">
          <div className="flex items-center gap-2 flex-1 min-w-48 max-w-xs">
            <Search className="h-3.5 w-3.5 text-zinc-500 flex-shrink-0" />
            <input
              type="search"
              placeholder="Filter deals by title or company…"
              value={dealSearch}
              onChange={(e) => setDealSearch(e.target.value)}
              className="w-full rounded-lg border border-zinc-800 bg-zinc-900 py-1.5 px-2.5 text-xs text-zinc-300 placeholder-zinc-600 outline-none focus:border-indigo-500/50 transition"
              aria-label="Filter deals"
            />
            {dealSearch && (
              <button onClick={() => setDealSearch("")} className="text-zinc-600 hover:text-zinc-300 flex-shrink-0">
                <X className="h-3.5 w-3.5" />
              </button>
            )}
          </div>
          <div className="flex items-center gap-2 text-xs text-zinc-500 ml-auto">
            <Brain className="h-3.5 w-3.5 text-indigo-400 flex-shrink-0" />
            <span className="font-mono hidden sm:inline">ML win probability · Deal health</span>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handleExportCsv}
              disabled={exportLoading}
              className="flex items-center gap-1.5 rounded-lg border border-zinc-800 bg-zinc-900 px-3 py-1.5 text-xs font-medium text-zinc-400 transition-all hover:border-zinc-700 hover:text-zinc-300 disabled:opacity-50 cursor-pointer disabled:cursor-not-allowed"
              title="Export deals as CSV"
            >
              {exportLoading ? <Loader2 className="h-3 w-3 animate-spin" /> : <Download className="h-3 w-3" />}
              Export CSV
            </button>
            <Button variant="cta" size="sm" onClick={() => setNewDealStage("discovery")}>
              <Plus className="h-3.5 w-3.5" /> New Deal
            </Button>
          </div>
        </div>

        {loading ? (
          <div className="flex gap-4 overflow-x-auto pb-4">
            {dealStageOrder.map((s) => (
              <div key={s} className="flex flex-col min-w-[240px] w-[240px] gap-3">
                <div className="h-10 rounded-xl bg-zinc-800/50 animate-pulse" />
                {[1, 2].map((i) => <div key={i} className="h-32 rounded-xl bg-zinc-800/30 animate-pulse" />)}
              </div>
            ))}
          </div>
        ) : (
          <div className="flex gap-4 overflow-x-auto pb-4" role="region" aria-label="Deals pipeline board">
            {dealStageOrder.map((stage) => (
              <StageColumn
                key={stage}
                stage={stage}
                deals={filteredDeals.filter((d) => d.stage === stage)}
                onSelect={(d) => { if (!selectedIds.size) setSelectedDeal(d); }}
                onAddDeal={setNewDealStage}
                selectedIds={selectedIds}
                onToggleSelect={handleToggleSelect}
              />
            ))}
          </div>
        )}
      </div>

      {/* Bulk action toolbar */}
      {selectedIds.size > 0 && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 flex items-center gap-3 rounded-2xl border border-indigo-500/30 bg-zinc-950/95 backdrop-blur px-5 py-3 shadow-2xl shadow-black/60">
          <span className="text-sm font-medium text-zinc-300">
            {selectedIds.size} deal{selectedIds.size !== 1 ? "s" : ""} selected
          </span>
          <div className="h-4 w-px bg-zinc-700" />
          <div className="relative">
            <button
              onClick={() => setBulkStageTarget(bulkStageTarget ? null : "qualified")}
              className="flex items-center gap-1.5 rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-1.5 text-xs text-zinc-200 hover:border-indigo-500/50 hover:bg-zinc-700 transition-all"
              disabled={bulkLoading}
            >
              <ArrowRight className="h-3 w-3" />
              Move stage
            </button>
            {bulkStageTarget !== null && (
              <div className="absolute bottom-full mb-2 left-0 w-44 rounded-xl border border-zinc-700 bg-zinc-900 py-1 shadow-xl">
                {dealStageOrder.map((s) => {
                  const cfg = stageConfig[s];
                  return (
                    <button
                      key={s}
                      onClick={() => handleBulkMoveStage(s)}
                      disabled={bulkLoading}
                      className={cn("w-full text-left px-3 py-2 text-xs hover:bg-zinc-800 transition-colors", cfg.color)}
                    >
                      {cfg.label}
                    </button>
                  );
                })}
              </div>
            )}
          </div>
          <button
            onClick={handleBulkDelete}
            disabled={bulkLoading}
            className="flex items-center gap-1.5 rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-1.5 text-xs text-rose-400 hover:bg-rose-500/20 transition-all disabled:opacity-50"
          >
            {bulkLoading ? <Loader2 className="h-3 w-3 animate-spin" /> : <Trash2 className="h-3 w-3" />}
            Delete
          </button>
          <button
            onClick={handleClearSelection}
            className="text-zinc-500 hover:text-zinc-300 transition-colors"
            aria-label="Clear selection"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      )}

      {/* Deal detail panel */}
      {selectedDeal && !selectedIds.size && (
        <>
          <div className="fixed inset-0 bg-black/40 z-30" onClick={() => setSelectedDeal(null)} />
          <DealDetailPanel deal={selectedDeal} onClose={() => setSelectedDeal(null)} onStageChange={handleStageChange} />
        </>
      )}

      {/* New deal modal */}
      {newDealStage && (
        <NewDealModal
          defaultStage={newDealStage}
          onClose={() => setNewDealStage(null)}
          onCreate={handleCreate}
        />
      )}

    </div>
  );
}
