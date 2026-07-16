"use client";

import { useState, useEffect, useCallback, type KeyboardEvent } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import Header from "@/components/layout/Header";
import Card from "@/components/ui/Card";
import Badge from "@/components/ui/Badge";
import Avatar from "@/components/ui/Avatar";
import Button from "@/components/ui/Button";
import { cn, formatCurrency, stageConfig, dealStageOrder } from "@/lib/utils";
import { apiClient } from "@/lib/api-client";
import { createBrowserClient } from "@/lib/supabase";
import { useJobPoller } from "@/hooks/useJobPoller";
import type { DealStage } from "@/lib/types";
import {
  ArrowLeft, Brain, Heart, AlertTriangle, TrendingUp,
  Building2, Calendar, ChevronRight, Mail, Zap,
  ListTodo, Loader2, XCircle, Trash2, CheckCircle2,
  ExternalLink, DollarSign, Clock, User,
  FileText, Send, BarChart2, History, Swords, Plus, X, Bell, Target, Users, Sparkles, RefreshCw,
} from "lucide-react";
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid,
  Tooltip as RechartTooltip, ResponsiveContainer,
} from "recharts";

// ─── Types ───────────────────────────────────────────────────────────────────

type DealDetail = {
  id: string;
  workspace_id: string;
  title: string | null;
  company: string | null;
  contact_name: string | null;
  contact_id: string | null;
  value: number;
  stage: string;
  ml_win_probability: number;
  health_score: number;
  expected_close: string | null;
  assigned_agent: string | null;
  notes: string | null;
  win_loss_reason: string | null;
  next_action: string | null;
  next_action_date: string | null;
  created_at: string | null;
};

const OUTCOME_REASONS = [
  { value: "price",         label: "Price" },
  { value: "competition",   label: "Competition" },
  { value: "timing",        label: "Timing" },
  { value: "fit",           label: "Product Fit" },
  { value: "champion_left", label: "Champion Left" },
  { value: "other",         label: "Other" },
];

type TimelineEvent = {
  id: string;
  type: string;
  title: string;
  body: string;
  ts: string | null;
  meta?: Record<string, unknown>;
};

type TaskRow = {
  id: string;
  title: string;
  status: string;
  due_date: string | null;
};

type EmailDraft = { subject: string; body: string };

type StageHistoryEntry = {
  stage: string;
  label: string;
  entered_at: string;
  days_in_stage: number;
  is_current: boolean;
};

type PredictedClose = {
  predicted_date: string;
  lower_bound: string;
  upper_bound: string;
  confidence_level: string;
  confidence_pct: number;
  data_points: number;
  avg_cycle_days: number | null;
};

// ─── Helpers ─────────────────────────────────────────────────────────────────

function formatRelative(iso: string | null): string {
  if (!iso) return "—";
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "Just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

function renderMarkdown(text: string): string {
  return text
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/^- (.+)$/gm, '<li class="ml-4 list-disc">$1</li>')
    .replace(/(<li[^>]*>.*<\/li>\n?)+/g, (m) => `<ul class="space-y-0.5 my-1">${m}</ul>`)
    .replace(/\n\n/g, '</p><p class="mt-3">')
    .replace(/^/, "<p>")
    .replace(/$/, "</p>")
    .replace(/\n/g, "<br/>");
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function WinBar({ value }: { value: number }) {
  const color = value >= 70 ? "bg-emerald-400" : value >= 40 ? "bg-amber-400" : "bg-rose-400";
  const text = value >= 70 ? "text-emerald-400" : value >= 40 ? "text-amber-400" : "text-rose-400";
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1.5 rounded-full bg-zinc-800 overflow-hidden">
        <div className={cn("h-full rounded-full transition-all", color)} style={{ width: `${value}%` }} />
      </div>
      <span className={cn("text-xs font-mono font-bold w-8 text-right", text)}>{value}%</span>
    </div>
  );
}

function HealthBar({ score }: { score: number }) {
  const color = score >= 70 ? "bg-emerald-400" : score >= 40 ? "bg-amber-400" : "bg-rose-400";
  const text = score >= 70 ? "text-emerald-400" : score >= 40 ? "text-amber-400" : "text-rose-400";
  const Icon = score >= 70 ? Heart : AlertTriangle;
  return (
    <div className="flex items-center gap-2">
      <Icon className={cn("h-3.5 w-3.5 flex-shrink-0", text)} />
      <div className="flex-1 h-1.5 rounded-full bg-zinc-800 overflow-hidden">
        <div className={cn("h-full rounded-full transition-all", color)} style={{ width: `${score}%` }} />
      </div>
      <span className={cn("text-xs font-mono font-bold w-8 text-right", text)}>{score}</span>
    </div>
  );
}

function StageBadge({ stage }: { stage: string }) {
  const variant =
    stage === "closed_won" ? "emerald" :
    stage === "closed_lost" ? "rose" :
    stage === "negotiation" ? "indigo" :
    stage === "proposal" ? "amber" :
    "zinc";
  const cfg = stageConfig[stage as DealStage] ?? { label: stage };
  return <Badge variant={variant} size="sm">{cfg.label}</Badge>;
}

// ─── Deal Notes Thread ─────────────────────────────────────────────────────────

type DealNote = {
  id: string;
  workspace_id: string;
  deal_id: string;
  body: string;
  author: string | null;
  created_at: string;
};

interface DealNotesThreadProps {
  dealId: string;
  workspaceId: string;
  token: string;
}

function authorInitials(author: string | null): string {
  if (!author) return "?";
  const parts = author.replace(/@.*/, "").replace(/[._-]+/g, " ").trim().split(/\s+/);
  return parts.map((p) => p[0]).join("").slice(0, 2).toUpperCase() || "?";
}

function DealNotesThread({ dealId, workspaceId, token }: DealNotesThreadProps) {
  const [notes, setNotes]     = useState<DealNote[]>([]);
  const [loading, setLoading] = useState(true);
  const [draft, setDraft]     = useState("");
  const [saving, setSaving]   = useState(false);
  const [error, setError]     = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    apiClient
      .getDealNotes(workspaceId, dealId, token)
      .then((data) => { if (!cancelled) setNotes(Array.isArray(data) ? (data as DealNote[]) : []); })
      .catch(() => { if (!cancelled) setNotes([]); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [workspaceId, dealId, token]);

  const handleAdd = async () => {
    const body = draft.trim();
    if (!body || saving) return;
    setSaving(true);
    setError(false);
    try {
      const created = (await apiClient.createDealNote(workspaceId, dealId, body, token)) as DealNote;
      setNotes((prev) => [...prev, created]);
      setDraft("");
    } catch {
      setError(true);
    } finally {
      setSaving(false);
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
      e.preventDefault();
      handleAdd();
    }
  };

  return (
    <Card className="p-4 space-y-3">
      <div className="flex items-center gap-2">
        <FileText className="h-4 w-4 text-zinc-500" aria-hidden />
        <p className="text-sm font-semibold text-zinc-200">Notes</p>
        {notes.length > 0 && (
          <span className="ml-auto text-xs font-mono text-zinc-500">{notes.length}</span>
        )}
      </div>

      {/* Thread */}
      {loading ? (
        <div className="space-y-2">
          {[1, 2].map((i) => (
            <div key={i} className="h-14 rounded-xl border border-zinc-800 bg-zinc-900 animate-pulse" />
          ))}
        </div>
      ) : notes.length === 0 ? (
        <p className="text-xs text-zinc-600 italic py-1">No notes yet. Add the first one below.</p>
      ) : (
        <div className="space-y-2.5">
          {notes.map((note) => (
            <div key={note.id} className="flex gap-2.5">
              <Avatar initials={authorInitials(note.author)} size="sm" />
              <div className="flex-1 min-w-0 rounded-xl border border-zinc-800 bg-zinc-900/60 px-3 py-2">
                <div className="flex items-center gap-2 mb-0.5">
                  <span className="text-xs font-medium text-zinc-300 truncate">{note.author ?? "Unknown"}</span>
                  <span className="text-[10px] text-zinc-600 ml-auto flex-shrink-0">{formatRelative(note.created_at)}</span>
                </div>
                <div
                  className="text-xs text-zinc-400 leading-relaxed prose-notes break-words"
                  dangerouslySetInnerHTML={{ __html: renderMarkdown(note.body) }}
                />
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Add-note composer */}
      <div className="space-y-2 pt-1 border-t border-zinc-800">
        <textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={handleKeyDown}
          rows={3}
          placeholder={"Add a note…  Supports **bold**, - lists. ⌘↵ to post."}
          className="w-full rounded-lg border border-zinc-700/60 bg-zinc-800/40 px-3 py-2.5 text-xs text-zinc-200 placeholder:text-zinc-600 outline-none resize-none focus:border-indigo-500/50 transition-colors leading-relaxed font-mono mt-2"
        />
        <div className="flex items-center gap-2">
          <button
            onClick={handleAdd}
            disabled={saving || !draft.trim()}
            className={cn(
              "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all",
              saving || !draft.trim()
                ? "bg-zinc-700 text-zinc-500 cursor-not-allowed"
                : "bg-indigo-600 hover:bg-indigo-500 text-white cursor-pointer"
            )}
          >
            {saving ? <Loader2 className="h-3 w-3 animate-spin" /> : <Send className="h-3 w-3" />}
            {saving ? "Posting…" : "Add note"}
          </button>
          {error && <span className="text-[11px] text-rose-400">Failed to add note — try again.</span>}
        </div>
      </div>
    </Card>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function DealDetailPage() {
  const params = useParams();
  const router = useRouter();
  const dealId = params?.id as string;

  const [deal, setDeal] = useState<DealDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [token, setToken] = useState<string | null>(null);
  const [workspaceId, setWorkspaceId] = useState<string | null>(null);

  const [timeline, setTimeline] = useState<TimelineEvent[]>([]);
  const [timelineLoading, setTimelineLoading] = useState(false);
  const [tasks, setTasks] = useState<TaskRow[]>([]);
  const [tasksLoading, setTasksLoading] = useState(false);
  const [probTrend, setProbTrend] = useState<{ date: string; probability: number }[]>([]);
  const [probLoading, setProbLoading] = useState(false);
  const [timelineSummary, setTimelineSummary] = useState<{ week: string; events: number }[]>([]);
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [dealHeatmap, setDealHeatmap] = useState<{ week_start: string; events: number; messages: number; notes: number; total: number }[]>([]);
  const [heatmapLoading, setHeatmapLoading] = useState(false);
  const [stageHistory, setStageHistory] = useState<StageHistoryEntry[]>([]);
  const [stageHistoryLoading, setStageHistoryLoading] = useState(false);

  const [responseLag, setResponseLag] = useState<{ cells: { dow: number; hour: number; avg_lag_hours: number; count: number }[]; max_lag_hours: number } | null>(null);
  const [responseLagLoading, setResponseLagLoading] = useState(false);

  const [predictedClose, setPredictedClose] = useState<PredictedClose | null>(null);
  const [predictedCloseLoading, setPredictedCloseLoading] = useState(false);

  const [healthHistory, setHealthHistory] = useState<{ recorded_at: string; score: number }[]>([]);
  const [healthHistoryLoading, setHealthHistoryLoading] = useState(false);

  type EngagementScore = {
    score: number;
    message_count: number;
    note_count: number;
    tasks_total: number;
    tasks_done: number;
    components: { messages: number; notes: number; tasks: number };
  };
  const [engagementScore, setEngagementScore] = useState<EngagementScore | null>(null);
  const [engagementLoading, setEngagementLoading] = useState(false);

  const [competitors, setCompetitors] = useState<string[]>([]);
  const [competitorsLoading, setCompetitorsLoading] = useState(false);
  const [competitorInput, setCompetitorInput] = useState("");
  const [competitorSaving, setCompetitorSaving] = useState(false);

  type DealMention = { name: string; type: string };
  const [mentions, setMentions] = useState<DealMention[]>([]);
  const [mentionsLoading, setMentionsLoading] = useState(false);
  const [mentionInput, setMentionInput] = useState("");
  const [mentionType, setMentionType] = useState<"teammate" | "contact">("teammate");
  const [mentionSaving, setMentionSaving] = useState(false);

  const [nextActionText, setNextActionText] = useState("");
  const [nextActionDate, setNextActionDate] = useState("");
  const [nextActionSaving, setNextActionSaving] = useState(false);
  const [bannerDismissed, setBannerDismissed] = useState(false);

  const [moveSaving, setMoveSaving] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState(false);
  const [deleteText, setDeleteText] = useState("");
  const [deleting, setDeleting] = useState(false);

  const [emailDraft, setEmailDraft] = useState<EmailDraft | null>(null);
  const [emailLoading, setEmailLoading] = useState(false);

  const [outcomePickerOpen, setOutcomePickerOpen] = useState(false);
  const [outcomeSaving, setOutcomeSaving] = useState(false);

  type CoachData = { urgency: "low" | "medium" | "high"; bullets: string[]; generated_at: string };
  const [coachData, setCoachData] = useState<CoachData | null>(null);
  const [coachLoading, setCoachLoading] = useState(false);
  const [coachGenerating, setCoachGenerating] = useState(false);

  const optimizePoller = useJobPoller();

  // ── Auth init ──────────────────────────────────────────────────────────────
  useEffect(() => {
    if (process.env.NEXT_PUBLIC_DEMO_MODE === "true") {
      setToken("demo-token");
      setWorkspaceId("demo-workspace-1");
      return;
    }
    const supabase = createBrowserClient();
    supabase.auth.getSession().then(({ data: { session } }) => {
      if (session) {
        setToken(session.access_token);
        setWorkspaceId((session.user.app_metadata?.workspace_id ?? session.user.user_metadata?.workspace_id) ?? null);
      }
    });
  }, []);

  // ── Load deal ──────────────────────────────────────────────────────────────
  useEffect(() => {
    if (!token || !workspaceId) return;
    setLoading(true);
    apiClient
      .getDeal(workspaceId, dealId, token)
      .then((data) => {
        const d = (data as DealDetail) ?? null;
        setDeal(d);
        if (d) {
          setNextActionText(d.next_action ?? "");
          setNextActionDate(d.next_action_date ?? "");
          setBannerDismissed(
            typeof sessionStorage !== "undefined"
              ? sessionStorage.getItem(`na_dismissed_${dealId}`) === "1"
              : false
          );
        }
      })
      .catch(() => setDeal(null))
      .finally(() => setLoading(false));
  }, [token, workspaceId, dealId]);

  // ── Load side data ─────────────────────────────────────────────────────────
  const loadSideData = useCallback(async () => {
    if (!token || !workspaceId || !deal) return;

    setTimelineLoading(true);
    setTasksLoading(true);

    apiClient
      .getDealTimeline(workspaceId, dealId, token)
      .then((data) => setTimeline(Array.isArray(data) ? (data as TimelineEvent[]) : []))
      .catch(() => setTimeline([]))
      .finally(() => setTimelineLoading(false));

    setProbLoading(true);
    apiClient
      .getDealProbabilityTrend(workspaceId, dealId, token)
      .then((data) => setProbTrend(Array.isArray(data) ? data : []))
      .catch(() => setProbTrend([]))
      .finally(() => setProbLoading(false));

    setSummaryLoading(true);
    apiClient
      .getDealTimelineSummary(workspaceId, dealId, token)
      .then((data) => setTimelineSummary(Array.isArray(data) ? data : []))
      .catch(() => setTimelineSummary([]))
      .finally(() => setSummaryLoading(false));

    setHeatmapLoading(true);
    apiClient
      .getDealActivityHeatmap(workspaceId, dealId, token)
      .then((data) => setDealHeatmap(Array.isArray(data) ? data : []))
      .catch(() => setDealHeatmap([]))
      .finally(() => setHeatmapLoading(false));

    setStageHistoryLoading(true);
    apiClient
      .getDealStageHistory(workspaceId, dealId, token)
      .then((data) => setStageHistory(Array.isArray(data) ? (data as StageHistoryEntry[]) : []))
      .catch(() => setStageHistory([]))
      .finally(() => setStageHistoryLoading(false));

    setResponseLagLoading(true);
    apiClient
      .getDealResponseLag(workspaceId, dealId, token)
      .then((data) => setResponseLag(data ?? null))
      .catch(() => setResponseLag(null))
      .finally(() => setResponseLagLoading(false));

    setPredictedCloseLoading(true);
    apiClient
      .getPredictedClose(workspaceId, dealId, token)
      .then((data) => setPredictedClose(data ?? null))
      .catch(() => setPredictedClose(null))
      .finally(() => setPredictedCloseLoading(false));

    setEngagementLoading(true);
    apiClient
      .getDealEngagementScore(workspaceId, dealId, token)
      .then((data) => setEngagementScore(data ?? null))
      .catch(() => setEngagementScore(null))
      .finally(() => setEngagementLoading(false));

    setCompetitorsLoading(true);
    apiClient
      .getDealCompetitors(workspaceId, dealId, token)
      .then((data) => setCompetitors(data.competitors ?? []))
      .catch(() => setCompetitors([]))
      .finally(() => setCompetitorsLoading(false));

    setMentionsLoading(true);
    apiClient
      .getDealMentions(workspaceId, dealId, token)
      .then((data) => setMentions(data.mentions ?? []))
      .catch(() => setMentions([]))
      .finally(() => setMentionsLoading(false));

    setHealthHistoryLoading(true);
    apiClient
      .getDealHealthScoreHistory(workspaceId, dealId, token)
      .then((data) => setHealthHistory(Array.isArray(data) ? data : []))
      .catch(() => setHealthHistory([]))
      .finally(() => setHealthHistoryLoading(false));

    setCoachLoading(true);
    apiClient
      .getDealCoaching(workspaceId, dealId, token)
      .then((data) => setCoachData(data ?? null))
      .catch(() => setCoachData(null))
      .finally(() => setCoachLoading(false));

    if (deal.contact_id) {
      apiClient
        .getTasks(workspaceId, token, { contactId: deal.contact_id })
        .then((data) => setTasks(Array.isArray(data) ? (data as TaskRow[]) : []))
        .catch(() => setTasks([]))
        .finally(() => setTasksLoading(false));
    } else {
      setTasks([]);
      setTasksLoading(false);
    }
  }, [token, workspaceId, dealId, deal]);

  useEffect(() => {
    if (deal) loadSideData();
  }, [deal, loadSideData]);

  // ── Actions ────────────────────────────────────────────────────────────────

  const handleMoveStage = async (stage: DealStage) => {
    if (!token || !workspaceId || !deal) return;
    setMoveSaving(true);
    try {
      const updated = (await apiClient.updateDeal(workspaceId, deal.id, { stage }, token)) as DealDetail;
      setDeal((prev) => (prev ? { ...prev, stage: updated.stage ?? stage } : null));
    } catch { /* ignore */ }
    finally { setMoveSaving(false); }
  };

  const handleComposeEmail = async () => {
    if (!token || !workspaceId || !deal?.contact_id) return;
    setEmailLoading(true);
    try {
      const data = await apiClient.composeEmail(workspaceId, deal.contact_id, token);
      setEmailDraft(data as EmailDraft);
    } catch { /* ignore */ }
    finally { setEmailLoading(false); }
  };

  const handleOptimize = async () => {
    if (!token || !workspaceId) return;
    try {
      const res = await apiClient.triggerAgent("pipeline_optimizer", token) as { job_id?: string };
      if (res?.job_id) optimizePoller.start(res.job_id);
    } catch { /* ignore */ }
  };

  const handleSetOutcome = async (reason: string) => {
    if (!token || !workspaceId || !deal) return;
    const outcomeStage = deal.stage === "closed_won" || deal.stage === "closed_lost"
      ? (deal.stage as "closed_won" | "closed_lost")
      : "closed_lost";
    setOutcomeSaving(true);
    try {
      const updated = (await apiClient.setDealOutcome(workspaceId, deal.id, outcomeStage, reason, token)) as DealDetail;
      setDeal((prev) => prev ? { ...prev, win_loss_reason: updated.win_loss_reason ?? reason } : null);
      setOutcomePickerOpen(false);
    } catch { /* ignore */ }
    finally { setOutcomeSaving(false); }
  };

  const handleAddCompetitor = async (name: string) => {
    const label = name.trim();
    if (!label || !token || !workspaceId || competitorSaving) return;
    if (competitors.includes(label)) { setCompetitorInput(""); return; }
    const next = [...competitors, label];
    setCompetitorSaving(true);
    try {
      const data = await apiClient.updateDealCompetitors(workspaceId, dealId, next, token);
      setCompetitors(data.competitors ?? next);
      setCompetitorInput("");
    } catch { /* revert silently */ }
    finally { setCompetitorSaving(false); }
  };

  const handleRemoveCompetitor = async (name: string) => {
    if (!token || !workspaceId || competitorSaving) return;
    const next = competitors.filter((c) => c !== name);
    setCompetitorSaving(true);
    try {
      const data = await apiClient.updateDealCompetitors(workspaceId, dealId, next, token);
      setCompetitors(data.competitors ?? next);
    } catch { /* revert silently */ }
    finally { setCompetitorSaving(false); }
  };

  const handleAddMention = async (name: string) => {
    const label = name.trim();
    if (!label || !token || !workspaceId || mentionSaving) return;
    if (mentions.some((m) => m.name === label)) { setMentionInput(""); return; }
    const next = [...mentions, { name: label, type: mentionType }];
    setMentionSaving(true);
    try {
      const data = await apiClient.updateDealMentions(workspaceId, dealId, next, token);
      setMentions(data.mentions ?? next);
      setMentionInput("");
    } catch { /* revert silently */ }
    finally { setMentionSaving(false); }
  };

  const handleRemoveMention = async (name: string) => {
    if (!token || !workspaceId || mentionSaving) return;
    const next = mentions.filter((m) => m.name !== name);
    setMentionSaving(true);
    try {
      const data = await apiClient.updateDealMentions(workspaceId, dealId, next, token);
      setMentions(data.mentions ?? next);
    } catch { /* revert silently */ }
    finally { setMentionSaving(false); }
  };

  const handleDelete = async () => {
    if (!token || !workspaceId || deleteText !== (deal?.title ?? "")) return;
    setDeleting(true);
    try {
      await apiClient.deleteDeal(workspaceId, dealId, token);
      router.push("/pipeline");
    } catch { /* ignore */ }
    finally { setDeleting(false); }
  };

  const handleSaveNextAction = async () => {
    if (!token || !workspaceId || !deal || nextActionSaving) return;
    setNextActionSaving(true);
    try {
      const updated = (await apiClient.updateDeal(workspaceId, deal.id, {
        next_action: nextActionText.trim() || null,
        next_action_date: nextActionDate || null,
      }, token)) as DealDetail;
      setDeal((prev) => prev ? { ...prev, next_action: updated.next_action ?? null, next_action_date: updated.next_action_date ?? null } : null);
      if (nextActionDate) setBannerDismissed(false);
    } catch { /* ignore */ }
    finally { setNextActionSaving(false); }
  };

  const handleClearNextAction = async () => {
    if (!token || !workspaceId || !deal || nextActionSaving) return;
    setNextActionSaving(true);
    try {
      await apiClient.updateDeal(workspaceId, deal.id, { next_action: null, next_action_date: null }, token);
      setDeal((prev) => prev ? { ...prev, next_action: null, next_action_date: null } : null);
      setNextActionText("");
      setNextActionDate("");
      setBannerDismissed(false);
    } catch { /* ignore */ }
    finally { setNextActionSaving(false); }
  };

  const handleRegenerateCoach = async () => {
    if (!token || !workspaceId || coachGenerating) return;
    setCoachGenerating(true);
    try {
      const data = await apiClient.getDealCoaching(workspaceId, dealId, token);
      setCoachData(data ?? null);
    } catch { /* ignore */ }
    finally { setCoachGenerating(false); }
  };

  // ── Render guards ──────────────────────────────────────────────────────────

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-6 w-6 text-indigo-400 animate-spin" />
      </div>
    );
  }

  if (!deal) {
    return (
      <div className="flex flex-col items-center justify-center h-64 gap-4">
        <AlertTriangle className="h-8 w-8 text-zinc-600" />
        <p className="text-sm text-zinc-500">Deal not found.</p>
        <Button variant="secondary" onClick={() => router.push("/pipeline")}>
          <ArrowLeft className="h-3.5 w-3.5" /> Back to Pipeline
        </Button>
      </div>
    );
  }

  const stage = deal.stage as DealStage;
  const stageCfg = stageConfig[stage] ?? { label: deal.stage, color: "text-zinc-400", bg: "bg-zinc-700/50" };
  const isClosedStage = stage === "closed_won" || stage === "closed_lost";
  const otherStages = dealStageOrder.filter((s) => s !== stage);
  const openTasks = tasks.filter((t) => t.status === "open" || t.status === "in_progress");
  const doneTasks = tasks.filter((t) => t.status === "done" || t.status === "cancelled");
  const contactInitials = deal.contact_name
    ? deal.contact_name.split(" ").map((n) => n[0]).join("").slice(0, 2).toUpperCase()
    : "??";

  return (
    <div className="flex flex-col gap-6 p-4 md:p-6">
      <Header
        title={deal.title ?? "Untitled Deal"}
        subtitle={`${deal.company ?? "—"} · ${stageCfg.label}`}
      />

      {/* ── Actions bar ── */}
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="secondary" onClick={() => router.push("/pipeline")} className="gap-1.5">
          <ArrowLeft className="h-3.5 w-3.5" /> Pipeline
        </Button>

        <div className="flex-1" />

        {deal.contact_id && (
          <Button
            variant="secondary"
            onClick={() => router.push(`/contacts/${deal.contact_id}`)}
            className="gap-1.5"
          >
            <User className="h-3.5 w-3.5" /> Contact
          </Button>
        )}

        {deal.contact_id && (
          <Button
            variant="secondary"
            onClick={handleComposeEmail}
            disabled={emailLoading}
            className="gap-1.5"
          >
            {emailLoading ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Mail className="h-3.5 w-3.5" />
            )}
            Compose Email
          </Button>
        )}

        <Button
          variant="secondary"
          onClick={handleOptimize}
          disabled={optimizePoller.state === "pending" || optimizePoller.state === "started"}
          className="gap-1.5"
        >
          {optimizePoller.state === "pending" || optimizePoller.state === "started" ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : optimizePoller.state === "success" ? (
            <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />
          ) : (
            <Zap className="h-3.5 w-3.5" />
          )}
          Optimize
        </Button>

        <Button
          variant="secondary"
          onClick={() => setDeleteConfirm(true)}
          className="gap-1.5 text-rose-400 border-rose-500/20 hover:border-rose-500/40 hover:text-rose-300"
        >
          <Trash2 className="h-3.5 w-3.5" /> Delete
        </Button>
      </div>

      {/* ── Overdue next-action banner ── */}
      {!isClosedStage && deal.next_action_date && !bannerDismissed && (() => {
        const dueDate = new Date(deal.next_action_date + "T00:00:00");
        const today = new Date(); today.setHours(0, 0, 0, 0);
        const daysOverdue = Math.floor((today.getTime() - dueDate.getTime()) / 86400000);
        if (daysOverdue < 0) return null;
        return (
          <div className="flex items-start gap-3 rounded-xl border border-amber-500/30 bg-amber-500/8 px-4 py-3">
            <Bell className="h-4 w-4 text-amber-400 flex-shrink-0 mt-0.5" aria-hidden />
            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold text-amber-300">
                {daysOverdue === 0 ? "Action due today" : `Action overdue by ${daysOverdue} day${daysOverdue !== 1 ? "s" : ""}`}
              </p>
              {deal.next_action && (
                <p className="text-xs text-amber-200/70 mt-0.5 truncate">{deal.next_action}</p>
              )}
            </div>
            <div className="flex items-center gap-2 flex-shrink-0">
              <button
                onClick={handleClearNextAction}
                disabled={nextActionSaving}
                className="text-[11px] font-medium text-amber-400 hover:text-amber-200 underline underline-offset-2 transition-colors disabled:opacity-50"
              >
                {nextActionSaving ? <Loader2 className="h-3 w-3 animate-spin inline" /> : "Clear"}
              </button>
              <button
                onClick={() => {
                  setBannerDismissed(true);
                  if (typeof sessionStorage !== "undefined") sessionStorage.setItem(`na_dismissed_${dealId}`, "1");
                }}
                aria-label="Dismiss"
                className="text-amber-500 hover:text-amber-300 transition-colors"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>
        );
      })()}

      {/* ── Main grid ── */}
      <div className="grid grid-cols-1 lg:grid-cols-[320px_1fr] gap-6">

        {/* Left: Deal profile */}
        <div className="flex flex-col gap-4">

          {/* Identity card */}
          <Card className="p-5 space-y-4">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <h2 className="text-base font-semibold text-zinc-100 leading-snug">{deal.title}</h2>
                <div className="flex items-center gap-1.5 mt-1 text-zinc-400">
                  <Building2 className="h-3.5 w-3.5 text-zinc-600 flex-shrink-0" />
                  <span className="text-sm truncate">{deal.company}</span>
                </div>
              </div>
              <StageBadge stage={stage} />
            </div>

            {/* Value chip */}
            <div className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-3.5 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <DollarSign className="h-4 w-4 text-indigo-400" />
                <span className="text-xs text-zinc-400">Deal Value</span>
              </div>
              <span className="text-xl font-bold font-mono text-zinc-100">{formatCurrency(deal.value)}</span>
            </div>

            {/* Health */}
            {!isClosedStage && (
              <div className="space-y-2">
                <p className="text-[10px] font-mono text-zinc-500 uppercase tracking-widest">Deal Health</p>
                <HealthBar score={deal.health_score} />
              </div>
            )}

            {/* ML win prob */}
            {!isClosedStage && (
              <div className="space-y-2">
                <div className="flex items-center gap-1.5">
                  <Brain className="h-3.5 w-3.5 text-indigo-400" />
                  <p className="text-[10px] font-mono text-zinc-500 uppercase tracking-widest">ML Win Probability</p>
                </div>
                <WinBar value={deal.ml_win_probability} />
              </div>
            )}

            {isClosedStage && (
              <div className="space-y-2">
                <div className={cn(
                  "rounded-xl border px-4 py-3 text-center",
                  stage === "closed_won"
                    ? "border-emerald-500/20 bg-emerald-500/5 text-emerald-400"
                    : "border-rose-500/20 bg-rose-500/5 text-rose-400"
                )}>
                  <span className="text-sm font-semibold">
                    {stage === "closed_won" ? "🏆 Closed Won" : "✗ Closed Lost"}
                  </span>
                </div>

                {/* Outcome reason chip */}
                {deal.win_loss_reason ? (
                  <div className="flex items-center gap-2">
                    <span className={cn(
                      "flex-1 text-center text-xs font-mono font-medium rounded-lg px-3 py-1.5 border",
                      stage === "closed_won"
                        ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-300"
                        : "border-rose-500/20 bg-rose-500/10 text-rose-300"
                    )}>
                      {OUTCOME_REASONS.find((r) => r.value === deal.win_loss_reason)?.label ?? deal.win_loss_reason}
                    </span>
                    <button
                      onClick={() => setOutcomePickerOpen((v) => !v)}
                      className="text-[10px] text-zinc-500 hover:text-zinc-300 underline transition-colors"
                    >
                      change
                    </button>
                  </div>
                ) : (
                  <button
                    onClick={() => setOutcomePickerOpen((v) => !v)}
                    className="w-full rounded-lg border border-dashed border-zinc-700 px-3 py-2 text-xs text-zinc-500 hover:border-zinc-500 hover:text-zinc-300 transition-all"
                  >
                    + Tag reason
                  </button>
                )}

                {/* Inline reason picker */}
                {outcomePickerOpen && (
                  <div className="grid grid-cols-2 gap-1 pt-1">
                    {OUTCOME_REASONS.map((r) => (
                      <button
                        key={r.value}
                        onClick={() => handleSetOutcome(r.value)}
                        disabled={outcomeSaving}
                        className={cn(
                          "rounded-lg border px-2 py-1.5 text-[11px] font-medium transition-all",
                          deal.win_loss_reason === r.value
                            ? stage === "closed_won"
                              ? "border-emerald-500/40 bg-emerald-500/15 text-emerald-300"
                              : "border-rose-500/40 bg-rose-500/15 text-rose-300"
                            : "border-zinc-700 text-zinc-400 hover:border-zinc-600 hover:text-zinc-200",
                          outcomeSaving && "opacity-50 cursor-not-allowed"
                        )}
                      >
                        {outcomeSaving && deal.win_loss_reason === r.value
                          ? <Loader2 className="h-3 w-3 animate-spin mx-auto" />
                          : r.label}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}
          </Card>

          {/* Metadata card */}
          <Card className="p-4 space-y-3">
            <p className="text-[10px] font-mono text-zinc-500 uppercase tracking-widest">Deal Info</p>
            <div className="space-y-2.5">
              {deal.expected_close && (
                <div className="flex items-center gap-2.5">
                  <Calendar className="h-3.5 w-3.5 text-zinc-600 flex-shrink-0" />
                  <span className="text-xs text-zinc-400">Expected close</span>
                  <span className="text-xs font-mono text-zinc-200 ml-auto">{deal.expected_close}</span>
                </div>
              )}
              {deal.created_at && (
                <div className="flex items-center gap-2.5">
                  <Clock className="h-3.5 w-3.5 text-zinc-600 flex-shrink-0" />
                  <span className="text-xs text-zinc-400">Created</span>
                  <span className="text-xs font-mono text-zinc-200 ml-auto">
                    {new Date(deal.created_at).toLocaleDateString("en-US", {
                      month: "short", day: "numeric", year: "numeric",
                    })}
                  </span>
                </div>
              )}
              {deal.assigned_agent && (
                <div className="flex items-center gap-2.5">
                  <Zap className="h-3.5 w-3.5 text-zinc-600 flex-shrink-0" />
                  <span className="text-xs text-zinc-400">Agent</span>
                  <span className="text-xs font-mono text-indigo-400 ml-auto">{deal.assigned_agent}</span>
                </div>
              )}
            </div>
          </Card>

          {/* Associated contact */}
          {deal.contact_id && deal.contact_name && (
            <Card className="p-4 space-y-3">
              <p className="text-[10px] font-mono text-zinc-500 uppercase tracking-widest">Associated Contact</p>
              <div className="flex items-center gap-3">
                <Avatar initials={contactInitials} size="md" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-zinc-100">{deal.contact_name}</p>
                </div>
                <Link
                  href={`/contacts/${deal.contact_id}`}
                  className="text-zinc-500 hover:text-indigo-400 transition-colors p-1"
                  aria-label="Open contact detail"
                >
                  <ExternalLink className="h-4 w-4" />
                </Link>
              </div>
            </Card>
          )}

          {/* Deal Engagement Score */}
          <Card className="p-4 space-y-3">
            <div className="flex items-center gap-2">
              <TrendingUp className="h-4 w-4 text-indigo-400" aria-hidden />
              <p className="text-sm font-semibold text-zinc-200">Engagement Score</p>
              <span className="ml-auto text-[10px] font-mono text-zinc-500">Last 90 days</span>
            </div>
            {engagementLoading ? (
              <div className="flex items-center justify-center py-4">
                <Loader2 className="h-4 w-4 text-indigo-400 animate-spin" />
              </div>
            ) : engagementScore === null ? (
              <p className="text-xs text-zinc-600 italic py-2">Unable to load engagement data.</p>
            ) : (() => {
              const s = engagementScore.score;
              const circumference = 2 * Math.PI * 36;
              const dash = (s / 100) * circumference;
              const scoreColor = s >= 80 ? "#34d399" : s >= 60 ? "#818cf8" : s >= 30 ? "#fbbf24" : "#f87171";
              const scoreLabel = s >= 80 ? "High" : s >= 60 ? "Good" : s >= 30 ? "Low" : "Minimal";
              return (
                <div className="flex items-center gap-4">
                  <div className="relative flex-shrink-0">
                    <svg width="88" height="88" viewBox="0 0 88 88">
                      <circle cx="44" cy="44" r="36" fill="none" stroke="#27272a" strokeWidth="8" />
                      <circle
                        cx="44" cy="44" r="36" fill="none"
                        stroke={scoreColor} strokeWidth="8"
                        strokeLinecap="round"
                        strokeDasharray={`${dash} ${circumference}`}
                        transform="rotate(-90 44 44)"
                        style={{ transition: "stroke-dasharray 0.5s ease" }}
                      />
                    </svg>
                    <div className="absolute inset-0 flex flex-col items-center justify-center">
                      <span className="text-lg font-bold font-mono" style={{ color: scoreColor }}>{s}</span>
                      <span className="text-[9px] text-zinc-500 uppercase tracking-wide">{scoreLabel}</span>
                    </div>
                  </div>
                  <div className="flex-1 space-y-1.5">
                    {[
                      { label: "Messages", value: engagementScore.components.messages, max: 40, count: engagementScore.message_count },
                      { label: "Notes", value: engagementScore.components.notes, max: 30, count: engagementScore.note_count },
                      { label: "Tasks", value: engagementScore.components.tasks, max: 30, count: `${engagementScore.tasks_done}/${engagementScore.tasks_total}` },
                    ].map(({ label, value, max, count }) => (
                      <div key={label}>
                        <div className="flex justify-between text-[10px] text-zinc-500 mb-0.5">
                          <span>{label}</span>
                          <span className="font-mono">{count}</span>
                        </div>
                        <div className="h-1 rounded-full bg-zinc-800 overflow-hidden">
                          <div
                            className="h-full rounded-full bg-indigo-500"
                            style={{ width: `${(value / max) * 100}%` }}
                          />
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              );
            })()}
          </Card>

          {/* Competitors */}
          <Card className="p-4 space-y-3">
            <div className="flex items-center gap-2">
              <Swords className="h-4 w-4 text-rose-400" aria-hidden />
              <p className="text-sm font-semibold text-zinc-200">Competitors</p>
              {competitors.length > 0 && (
                <span className="ml-auto text-xs font-mono text-zinc-500">{competitors.length}</span>
              )}
            </div>

            {competitorsLoading ? (
              <div className="h-7 rounded-lg bg-zinc-800/50 animate-pulse" />
            ) : (
              <div className="flex flex-wrap gap-1.5">
                {competitors.map((c) => (
                  <span
                    key={c}
                    className="flex items-center gap-1 rounded-full border border-rose-500/20 bg-rose-500/10 px-2.5 py-0.5 text-[11px] font-medium text-rose-300"
                  >
                    {c}
                    <button
                      onClick={() => handleRemoveCompetitor(c)}
                      disabled={competitorSaving}
                      aria-label={`Remove ${c}`}
                      className="ml-0.5 text-rose-400 hover:text-rose-200 disabled:opacity-40 cursor-pointer transition-colors"
                    >
                      <X className="h-2.5 w-2.5" />
                    </button>
                  </span>
                ))}

                {/* Inline add */}
                <div className="flex items-center gap-1">
                  <input
                    type="text"
                    value={competitorInput}
                    onChange={(e) => setCompetitorInput(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === ",") {
                        e.preventDefault();
                        handleAddCompetitor(competitorInput);
                      }
                    }}
                    placeholder="+ Add competitor"
                    className="h-6 rounded-full border border-dashed border-zinc-600 bg-transparent px-2.5 text-[11px] text-zinc-400 placeholder:text-zinc-600 outline-none focus:border-rose-500/50 focus:text-zinc-200 transition-colors w-32"
                  />
                  {competitorInput.trim() && (
                    <button
                      onClick={() => handleAddCompetitor(competitorInput)}
                      disabled={competitorSaving}
                      className="flex-shrink-0 text-zinc-500 hover:text-rose-300 disabled:opacity-40 cursor-pointer transition-colors"
                      aria-label="Add competitor"
                    >
                      {competitorSaving
                        ? <Loader2 className="h-3 w-3 animate-spin" />
                        : <Plus className="h-3 w-3" />}
                    </button>
                  )}
                </div>
              </div>
            )}
          </Card>

          {/* Mentions */}
          <Card className="p-4 space-y-3">
            <div className="flex items-center gap-2">
              <Users className="h-4 w-4 text-indigo-400" aria-hidden />
              <p className="text-sm font-semibold text-zinc-200">Mentions</p>
              {mentions.length > 0 && (
                <span className="ml-auto text-xs font-mono text-zinc-500">{mentions.length}</span>
              )}
            </div>

            {mentionsLoading ? (
              <div className="h-7 rounded-lg bg-zinc-800/50 animate-pulse" />
            ) : (
              <div className="flex flex-wrap gap-1.5">
                {mentions.map((m) => {
                  const initials = m.name.replace(/^@/, "").slice(0, 2).toUpperCase();
                  const isTeammate = m.type === "teammate";
                  return (
                    <span
                      key={m.name}
                      className={`flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[11px] font-medium ${
                        isTeammate
                          ? "border-indigo-500/20 bg-indigo-500/10 text-indigo-300"
                          : "border-emerald-500/20 bg-emerald-500/10 text-emerald-300"
                      }`}
                    >
                      <span className={`flex h-4 w-4 items-center justify-center rounded-full text-[9px] font-bold ${
                        isTeammate ? "bg-indigo-500/30 text-indigo-200" : "bg-emerald-500/30 text-emerald-200"
                      }`}>
                        {initials}
                      </span>
                      {m.name}
                      <button
                        onClick={() => handleRemoveMention(m.name)}
                        disabled={mentionSaving}
                        aria-label={`Remove ${m.name}`}
                        className={`ml-0.5 hover:opacity-80 disabled:opacity-40 cursor-pointer transition-opacity ${
                          isTeammate ? "text-indigo-400" : "text-emerald-400"
                        }`}
                      >
                        <X className="h-2.5 w-2.5" />
                      </button>
                    </span>
                  );
                })}

                {/* Inline add */}
                <div className="flex items-center gap-1">
                  <select
                    value={mentionType}
                    onChange={(e) => setMentionType(e.target.value as "teammate" | "contact")}
                    className="h-6 rounded-full border border-zinc-700 bg-zinc-800 px-1.5 text-[10px] text-zinc-400 outline-none cursor-pointer"
                    aria-label="Mention type"
                  >
                    <option value="teammate">Teammate</option>
                    <option value="contact">Contact</option>
                  </select>
                  <input
                    type="text"
                    value={mentionInput}
                    onChange={(e) => setMentionInput(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === ",") {
                        e.preventDefault();
                        handleAddMention(mentionInput);
                      }
                    }}
                    placeholder="+ Add mention"
                    className="h-6 rounded-full border border-dashed border-zinc-600 bg-transparent px-2.5 text-[11px] text-zinc-400 placeholder:text-zinc-600 outline-none focus:border-indigo-500/50 focus:text-zinc-200 transition-colors w-28"
                  />
                  {mentionInput.trim() && (
                    <button
                      onClick={() => handleAddMention(mentionInput)}
                      disabled={mentionSaving}
                      className="flex-shrink-0 text-zinc-500 hover:text-indigo-300 disabled:opacity-40 cursor-pointer transition-colors"
                      aria-label="Add mention"
                    >
                      {mentionSaving
                        ? <Loader2 className="h-3 w-3 animate-spin" />
                        : <Plus className="h-3 w-3" />}
                    </button>
                  )}
                </div>
              </div>
            )}
          </Card>

          {/* Next Action */}
          {!isClosedStage && (
            <Card className="p-4 space-y-3">
              <div className="flex items-center gap-2">
                <Bell className="h-4 w-4 text-amber-400" aria-hidden />
                <p className="text-sm font-semibold text-zinc-200">Next Action</p>
              </div>
              <div className="space-y-2">
                <input
                  type="text"
                  value={nextActionText}
                  onChange={(e) => setNextActionText(e.target.value)}
                  placeholder="What needs to happen next?"
                  className="w-full rounded-lg border border-zinc-700/60 bg-zinc-800/40 px-3 py-2 text-xs text-zinc-200 placeholder:text-zinc-600 outline-none focus:border-amber-500/50 transition-colors"
                />
                <div className="flex items-center gap-2">
                  <input
                    type="date"
                    value={nextActionDate}
                    onChange={(e) => setNextActionDate(e.target.value)}
                    className="flex-1 rounded-lg border border-zinc-700/60 bg-zinc-800/40 px-3 py-2 text-xs text-zinc-200 outline-none focus:border-amber-500/50 transition-colors [color-scheme:dark]"
                  />
                  <button
                    onClick={handleSaveNextAction}
                    disabled={nextActionSaving}
                    className={cn(
                      "flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-medium transition-all flex-shrink-0",
                      nextActionSaving
                        ? "bg-zinc-700 text-zinc-500 cursor-not-allowed"
                        : "bg-amber-600 hover:bg-amber-500 text-white cursor-pointer"
                    )}
                  >
                    {nextActionSaving ? <Loader2 className="h-3 w-3 animate-spin" /> : <CheckCircle2 className="h-3 w-3" />}
                    Save
                  </button>
                </div>
                {deal.next_action && (
                  <button
                    onClick={handleClearNextAction}
                    disabled={nextActionSaving}
                    className="text-[11px] text-zinc-500 hover:text-rose-400 transition-colors disabled:opacity-50 flex items-center gap-1"
                  >
                    <XCircle className="h-3 w-3" /> Clear next action
                  </button>
                )}
              </div>
            </Card>
          )}

          {/* Notes thread */}
          {token && workspaceId && (
            <DealNotesThread
              dealId={deal.id}
              workspaceId={workspaceId}
              token={token}
            />
          )}
        </div>

        {/* Right: Stage mover + Tasks + Timeline */}
        <div className="flex flex-col gap-6">

          {/* Stage mover */}
          {!isClosedStage && (
            <Card className="p-4 space-y-3">
              <div className="flex items-center gap-2">
                <TrendingUp className="h-4 w-4 text-indigo-400" />
                <p className="text-sm font-semibold text-zinc-200">Move to Stage</p>
                {moveSaving && <Loader2 className="h-3.5 w-3.5 text-zinc-500 animate-spin ml-auto" />}
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-1.5">
                {otherStages.map((s) => {
                  const cfg = stageConfig[s];
                  return (
                    <button
                      key={s}
                      onClick={() => handleMoveStage(s)}
                      disabled={moveSaving}
                      className={cn(
                        "flex items-center justify-between rounded-lg border border-zinc-800 px-3 py-2.5 text-xs transition-all hover:border-zinc-700 text-left",
                        cfg.bg,
                        moveSaving && "opacity-50 cursor-not-allowed cursor-default",
                        !moveSaving && "cursor-pointer"
                      )}
                    >
                      <span className={cn("font-medium", cfg.color)}>{cfg.label}</span>
                      <ChevronRight className="h-3 w-3 text-zinc-600 flex-shrink-0" />
                    </button>
                  );
                })}
              </div>
            </Card>
          )}

          {/* Win probability trend */}
          {!isClosedStage && (
            <Card className="p-4 space-y-3">
              <div className="flex items-center gap-2">
                <Brain className="h-4 w-4 text-indigo-400" />
                <p className="text-sm font-semibold text-zinc-200">Win Probability Trend</p>
                <span className="ml-auto text-[10px] font-mono text-zinc-500">Last 30 days</span>
              </div>
              {probLoading ? (
                <div className="h-28 rounded-xl bg-zinc-800/50 animate-pulse" />
              ) : probTrend.length > 0 ? (
                <div className="h-28">
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={probTrend} margin={{ top: 4, right: 4, bottom: 0, left: -24 }}>
                      <defs>
                        <linearGradient id="probGrad" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="#6366F1" stopOpacity={0.25} />
                          <stop offset="95%" stopColor="#6366F1" stopOpacity={0} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid strokeDasharray="3 3" stroke="#27272A" vertical={false} />
                      <XAxis
                        dataKey="date"
                        tick={{ fill: "#71717A", fontSize: 9 }}
                        axisLine={false}
                        tickLine={false}
                        interval="preserveStartEnd"
                      />
                      <YAxis
                        domain={[0, 100]}
                        tick={{ fill: "#71717A", fontSize: 9 }}
                        axisLine={false}
                        tickLine={false}
                        tickFormatter={(v) => `${v}%`}
                        width={36}
                      />
                      <RechartTooltip
                        formatter={(v) => [`${v ?? 0}%`, "Win Prob"]}
                        contentStyle={{ background: "#18181B", border: "1px solid #27272A", borderRadius: 8, fontSize: 11 }}
                      />
                      <Area
                        type="monotone"
                        dataKey="probability"
                        stroke="#6366F1"
                        strokeWidth={2}
                        fill="url(#probGrad)"
                        dot={false}
                        activeDot={{ r: 4, fill: "#6366F1" }}
                      />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              ) : (
                <p className="text-xs text-zinc-500 text-center py-4">No trend data available.</p>
              )}
            </Card>
          )}

          {/* Health score history */}
          <Card className="p-4 space-y-3">
            <div className="flex items-center gap-2">
              <Heart className="h-4 w-4 text-emerald-400" aria-hidden />
              <p className="text-sm font-semibold text-zinc-200">Health Score History</p>
              <span className="ml-auto text-[10px] font-mono text-zinc-500">0–100</span>
            </div>
            {healthHistoryLoading ? (
              <div className="h-28 rounded-xl bg-zinc-800/50 animate-pulse" />
            ) : healthHistory.length > 0 ? (
              <div className="h-28">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={healthHistory} margin={{ top: 4, right: 4, bottom: 0, left: -24 }}>
                    <defs>
                      <linearGradient id="healthGrad" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%"  stopColor="#10B981" stopOpacity={0.25} />
                        <stop offset="95%" stopColor="#10B981" stopOpacity={0}   />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="#27272A" vertical={false} />
                    <XAxis
                      dataKey="recorded_at"
                      tick={{ fill: "#71717A", fontSize: 9 }}
                      axisLine={false}
                      tickLine={false}
                      interval="preserveStartEnd"
                      tickFormatter={(v) =>
                        new Date(v).toLocaleDateString("en-US", { month: "short", day: "numeric" })
                      }
                    />
                    <YAxis
                      domain={[0, 100]}
                      tick={{ fill: "#71717A", fontSize: 9 }}
                      axisLine={false}
                      tickLine={false}
                      width={28}
                    />
                    <RechartTooltip
                      formatter={(v) => [`${v ?? 0}`, "Health"]}
                      labelFormatter={(l) =>
                        new Date(l).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })
                      }
                      contentStyle={{ background: "#18181B", border: "1px solid #27272A", borderRadius: 8, fontSize: 11 }}
                    />
                    <Area
                      type="monotone"
                      dataKey="score"
                      stroke="#10B981"
                      strokeWidth={2}
                      fill="url(#healthGrad)"
                      dot={false}
                      activeDot={{ r: 4, fill: "#10B981" }}
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <p className="text-xs text-zinc-500 text-center py-4">No snapshots recorded yet.</p>
            )}
          </Card>

          {/* Activity sparkline — 12-week event intensity */}
          <Card className="p-4 space-y-3">
            <div className="flex items-center gap-2">
              <Zap className="h-4 w-4 text-indigo-400" />
              <p className="text-sm font-semibold text-zinc-200">Activity (12 wks)</p>
              <span className="ml-auto text-[10px] font-mono text-zinc-500">Events / week</span>
            </div>
            {summaryLoading ? (
              <div className="h-16 rounded-xl bg-zinc-800/50 animate-pulse" />
            ) : timelineSummary.length > 0 ? (
              <div className="h-16">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={timelineSummary} margin={{ top: 2, right: 2, bottom: 0, left: -32 }}>
                    <defs>
                      <linearGradient id="activityGrad" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%"  stopColor="#6366F1" stopOpacity={0.3} />
                        <stop offset="95%" stopColor="#6366F1" stopOpacity={0}   />
                      </linearGradient>
                    </defs>
                    <XAxis
                      dataKey="week"
                      tick={{ fill: "#71717A", fontSize: 8 }}
                      axisLine={false}
                      tickLine={false}
                      interval="preserveStartEnd"
                    />
                    <YAxis hide domain={[0, "auto"]} />
                    <RechartTooltip
                      formatter={(v) => [`${v ?? 0}`, "Events"]}
                      contentStyle={{ background: "#18181B", border: "1px solid #27272A", borderRadius: 8, fontSize: 11 }}
                    />
                    <Area
                      type="monotone"
                      dataKey="events"
                      stroke="#6366F1"
                      strokeWidth={1.5}
                      fill="url(#activityGrad)"
                      dot={false}
                      activeDot={{ r: 3, fill: "#6366F1" }}
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <p className="text-xs text-zinc-500 text-center py-3">No activity data yet.</p>
            )}
          </Card>

          {/* 12-Week Activity Heatmap */}
          <Card className="p-4 space-y-3">
            <div className="flex items-center gap-2">
              <BarChart2 className="h-4 w-4 text-indigo-400" />
              <p className="text-sm font-semibold text-zinc-200">12-Week Heatmap</p>
            </div>
            {heatmapLoading ? (
              <div className="flex gap-1">
                {Array.from({ length: 12 }).map((_, i) => (
                  <div key={i} className="flex-1 h-8 rounded bg-zinc-800 animate-pulse" />
                ))}
              </div>
            ) : dealHeatmap.length === 0 ? (
              <div className="flex flex-col items-center gap-2 py-4 text-center">
                <BarChart2 className="h-6 w-6 text-zinc-700" />
                <p className="text-xs text-zinc-500">No activity data.</p>
              </div>
            ) : (
              <div className="space-y-1.5">
                <div className="flex gap-1">
                  {dealHeatmap.map((w) => {
                    const bg =
                      w.total === 0 ? "bg-zinc-800" :
                      w.total === 1 ? "bg-indigo-900" :
                      w.total <= 3 ? "bg-indigo-700" :
                      w.total <= 5 ? "bg-indigo-500" : "bg-indigo-400";
                    return (
                      <div
                        key={w.week_start}
                        title={`${w.week_start}: ${w.total} event${w.total !== 1 ? "s" : ""} (${w.events} activity, ${w.messages} msg, ${w.notes} note${w.notes !== 1 ? "s" : ""})`}
                        className={cn("flex-1 h-8 rounded cursor-default transition-opacity hover:opacity-75", bg)}
                      />
                    );
                  })}
                </div>
                <div className="flex justify-between">
                  <span className="text-[10px] text-zinc-600">{dealHeatmap[0]?.week_start}</span>
                  <span className="text-[10px] text-zinc-600">This week</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <span className="text-[10px] text-zinc-500">Less</span>
                  {(["bg-zinc-800", "bg-indigo-900", "bg-indigo-700", "bg-indigo-500", "bg-indigo-400"] as const).map((c, i) => (
                    <span key={i} className={cn("h-3 w-3 rounded-sm", c)} />
                  ))}
                  <span className="text-[10px] text-zinc-500">More</span>
                </div>
              </div>
            )}
          </Card>

          {/* Response Lag Heatmap — 7×24 grid by day-of-week × hour */}
          {(() => {
            const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
            const HOUR_LABELS = ["12a", "3a", "6a", "9a", "12p", "3p", "6p", "9p"];

            const cellMap = new Map<string, { avg_lag_hours: number; count: number }>();
            (responseLag?.cells ?? []).forEach((c) => cellMap.set(`${c.dow}-${c.hour}`, c));
            const maxLag = responseLag?.max_lag_hours ?? 1;

            function lagColor(avgLag: number): string {
              if (avgLag <= 2) return "bg-emerald-700";
              if (avgLag <= 8) return "bg-amber-600";
              if (avgLag <= 24) return "bg-rose-700";
              return "bg-rose-500";
            }

            return (
              <Card className="p-4 space-y-3">
                <div className="flex items-center gap-2">
                  <Clock className="h-4 w-4 text-indigo-400" />
                  <p className="text-sm font-semibold text-zinc-200">Response Lag</p>
                  <span className="ml-auto text-[10px] font-mono text-zinc-500">Day × Hour</span>
                </div>
                {responseLagLoading ? (
                  <div className="h-24 rounded-xl bg-zinc-800/50 animate-pulse" />
                ) : !responseLag || responseLag.cells.length === 0 ? (
                  <p className="text-xs text-zinc-500 text-center py-3">No message data for this contact.</p>
                ) : (
                  <div className="space-y-1.5">
                    {/* Hour axis labels */}
                    <div className="flex ml-8">
                      {HOUR_LABELS.map((l, i) => (
                        <span key={i} className="flex-1 text-[9px] text-zinc-600 text-center"
                          style={{ marginLeft: i === 0 ? 0 : undefined }}>{l}</span>
                      ))}
                    </div>
                    {/* Grid rows */}
                    {DAYS.map((day, dow) => (
                      <div key={dow} className="flex items-center gap-1">
                        <span className="w-7 text-[9px] text-zinc-500 text-right flex-shrink-0">{day}</span>
                        <div className="flex flex-1 gap-px">
                          {Array.from({ length: 24 }, (_, h) => {
                            const cell = cellMap.get(`${dow}-${h}`);
                            const bg = cell ? lagColor(cell.avg_lag_hours) : "bg-zinc-800";
                            const tip = cell
                              ? `${day} ${h}:00 — avg ${cell.avg_lag_hours}h (${cell.count} msg${cell.count !== 1 ? "s" : ""})`
                              : `${day} ${h}:00 — no data`;
                            return (
                              <div
                                key={h}
                                title={tip}
                                className={cn("flex-1 h-4 rounded-sm cursor-default transition-opacity hover:opacity-75", bg)}
                              />
                            );
                          })}
                        </div>
                      </div>
                    ))}
                    {/* Legend */}
                    <div className="flex items-center gap-2 pt-0.5">
                      <span className="text-[9px] text-zinc-500">Fast</span>
                      {(["bg-emerald-700", "bg-amber-600", "bg-rose-700", "bg-rose-500"] as const).map((c, i) => (
                        <span key={i} className={cn("h-2.5 w-2.5 rounded-sm", c)} />
                      ))}
                      <span className="text-[9px] text-zinc-500">Slow</span>
                      <span className="ml-auto text-[9px] text-zinc-600">Max {maxLag.toFixed(1)}h</span>
                    </div>
                  </div>
                )}
              </Card>
            );
          })()}

          {/* Stage History */}
          <Card className="p-4 space-y-3">
            <div className="flex items-center gap-2">
              <History className="h-4 w-4 text-indigo-400" />
              <p className="text-sm font-semibold text-zinc-200">Stage History</p>
              {stageHistory.length > 0 && (
                <span className="ml-auto text-[10px] font-mono text-zinc-500">
                  {stageHistory.length} stage{stageHistory.length !== 1 ? "s" : ""}
                </span>
              )}
            </div>
            {stageHistoryLoading ? (
              <div className="space-y-2">
                {[1, 2, 3].map((i) => (
                  <div key={i} className="h-10 rounded-xl bg-zinc-800/50 animate-pulse" />
                ))}
              </div>
            ) : stageHistory.length === 0 ? (
              <p className="text-xs text-zinc-500 text-center py-3">No stage history available.</p>
            ) : (
              <div className="relative">
                {stageHistory.map((entry, i) => {
                  const cfg = stageConfig[entry.stage as DealStage] ?? {
                    label: entry.label, color: "text-zinc-400", bg: "bg-zinc-700/50",
                  };
                  return (
                    <div key={i} className="flex gap-3">
                      <div className="flex flex-col items-center flex-shrink-0">
                        <span className={cn(
                          "mt-1 h-2.5 w-2.5 rounded-full border-2 flex-shrink-0",
                          entry.is_current
                            ? "border-indigo-400 bg-indigo-400"
                            : "border-zinc-600 bg-zinc-800"
                        )} />
                        {i < stageHistory.length - 1 && (
                          <span className="flex-1 w-px bg-zinc-800 mt-1" />
                        )}
                      </div>
                      <div className="pb-3 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className={cn(
                            "text-xs font-medium",
                            entry.is_current ? cfg.color : "text-zinc-400"
                          )}>
                            {entry.label}
                          </span>
                          {entry.is_current && (
                            <span className="text-[10px] font-mono bg-indigo-500/20 text-indigo-300 px-1.5 py-0.5 rounded">
                              current
                            </span>
                          )}
                        </div>
                        <div className="flex items-center gap-3 mt-0.5">
                          <span className="text-[11px] text-zinc-500">
                            {new Date(entry.entered_at).toLocaleDateString("en-US", {
                              month: "short", day: "numeric", year: "numeric",
                            })}
                          </span>
                          <span className="text-[11px] font-mono text-zinc-600">
                            {entry.days_in_stage === 0 ? "< 1d" : `${entry.days_in_stage}d`}
                          </span>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </Card>

          {/* Predicted Close */}
          {!isClosedStage && (
            <Card className="p-4 space-y-3">
              <div className="flex items-center gap-2">
                <Target className="h-4 w-4 text-indigo-400" />
                <p className="text-sm font-semibold text-zinc-200">Predicted Close</p>
                {predictedClose && (
                  <span className={cn(
                    "ml-auto text-[10px] font-mono px-1.5 py-0.5 rounded",
                    predictedClose.confidence_level === "high"
                      ? "bg-emerald-500/20 text-emerald-300"
                      : predictedClose.confidence_level === "medium"
                      ? "bg-amber-500/20 text-amber-300"
                      : predictedClose.confidence_level === "none"
                      ? "bg-zinc-700 text-zinc-400"
                      : "bg-rose-500/20 text-rose-300"
                  )}>
                    {predictedClose.confidence_level === "none" ? "estimated" : `${predictedClose.confidence_pct}% conf`}
                  </span>
                )}
              </div>
              {predictedCloseLoading ? (
                <div className="h-16 rounded-xl bg-zinc-800/50 animate-pulse" />
              ) : !predictedClose ? (
                <p className="text-xs text-zinc-500 text-center py-3">Could not load prediction.</p>
              ) : (
                <div className="space-y-2.5">
                  <div className="flex items-center gap-2.5">
                    <Calendar className="h-3.5 w-3.5 text-indigo-400 flex-shrink-0" />
                    <span className="text-xs text-zinc-400">Predicted date</span>
                    <span className="text-xs font-mono text-zinc-100 ml-auto font-semibold">
                      {new Date(predictedClose.predicted_date + "T00:00:00").toLocaleDateString("en-US", {
                        month: "short", day: "numeric", year: "numeric",
                      })}
                    </span>
                  </div>
                  <div className="flex items-center gap-2.5">
                    <span className="h-3.5 w-3.5 flex-shrink-0" />
                    <span className="text-xs text-zinc-500">Range</span>
                    <span className="text-[11px] font-mono text-zinc-400 ml-auto">
                      {new Date(predictedClose.lower_bound + "T00:00:00").toLocaleDateString("en-US", { month: "short", day: "numeric" })}
                      {" – "}
                      {new Date(predictedClose.upper_bound + "T00:00:00").toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}
                    </span>
                  </div>
                  {predictedClose.avg_cycle_days !== null && (
                    <div className="flex items-center gap-2.5">
                      <span className="h-3.5 w-3.5 flex-shrink-0" />
                      <span className="text-xs text-zinc-500">Avg cycle</span>
                      <span className="text-[11px] font-mono text-zinc-400 ml-auto">
                        {predictedClose.avg_cycle_days}d
                        {predictedClose.data_points > 0 && (
                          <span className="text-zinc-600"> ({predictedClose.data_points} deals)</span>
                        )}
                      </span>
                    </div>
                  )}
                </div>
              )}
            </Card>
          )}

          {/* AI Coach */}
          {!isClosedStage && (
            <Card className="p-4 space-y-3">
              <div className="flex items-center gap-2">
                <Sparkles className="h-4 w-4 text-indigo-400" aria-hidden />
                <p className="text-sm font-semibold text-zinc-200">AI Coach</p>
                {coachData && (() => {
                  const urgency = coachData.urgency;
                  const urgencyColor = urgency === "high" ? "text-rose-300 border-rose-500/30 bg-rose-500/10"
                    : urgency === "medium" ? "text-amber-300 border-amber-500/30 bg-amber-500/10"
                    : "text-emerald-300 border-emerald-500/30 bg-emerald-500/10";
                  return (
                    <span className={`ml-1 rounded-full border px-2 py-0.5 text-[10px] font-mono font-semibold uppercase tracking-wide ${urgencyColor}`}>
                      {urgency}
                    </span>
                  );
                })()}
                <button
                  onClick={handleRegenerateCoach}
                  disabled={coachLoading || coachGenerating}
                  className="ml-auto text-zinc-500 hover:text-indigo-400 disabled:opacity-40 transition-colors cursor-pointer"
                  aria-label="Regenerate coaching"
                  title="Regenerate"
                >
                  {coachGenerating ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <RefreshCw className="h-3.5 w-3.5" />
                  )}
                </button>
              </div>

              {coachLoading ? (
                <div className="space-y-2">
                  {[1, 2, 3].map((i) => (
                    <div key={i} className="h-10 rounded-lg bg-zinc-800/50 animate-pulse" />
                  ))}
                </div>
              ) : coachData === null ? (
                <p className="text-xs text-zinc-600 italic py-2">Unable to load coaching advice.</p>
              ) : coachData.bullets.length === 0 ? (
                <p className="text-xs text-zinc-500 italic py-2">No coaching advice available.</p>
              ) : (
                <ul className="space-y-2">
                  {coachData.bullets.map((bullet, i) => (
                    <li key={i} className="flex items-start gap-2.5 rounded-lg border border-zinc-800 bg-zinc-900/60 px-3 py-2.5">
                      <span className="flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-full bg-indigo-500/15 text-[10px] font-bold text-indigo-400 mt-0.5">
                        {i + 1}
                      </span>
                      <p className="text-xs text-zinc-300 leading-relaxed">{bullet}</p>
                    </li>
                  ))}
                </ul>
              )}

              {coachData && (
                <p className="text-[10px] text-zinc-600 text-right">
                  Generated {new Date(coachData.generated_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                </p>
              )}
            </Card>
          )}

          {/* Tasks */}
          <Card className="p-4 space-y-3">
            <div className="flex items-center gap-2">
              <ListTodo className="h-4 w-4 text-indigo-400" />
              <p className="text-sm font-semibold text-zinc-200">Tasks</p>
              {tasks.length > 0 && (
                <span className="ml-auto text-xs font-mono text-zinc-500">{openTasks.length} open</span>
              )}
            </div>

            {tasksLoading ? (
              <div className="space-y-2">
                {[1, 2].map((i) => (
                  <div key={i} className="h-12 rounded-xl border border-zinc-800 bg-zinc-900 animate-pulse" />
                ))}
              </div>
            ) : !deal.contact_id ? (
              <p className="text-xs text-zinc-500 py-4 text-center">
                No contact linked — associate a contact to see tasks.
              </p>
            ) : tasks.length === 0 ? (
              <div className="flex flex-col items-center gap-2 py-6 text-center">
                <ListTodo className="h-6 w-6 text-zinc-700" />
                <p className="text-xs text-zinc-500">No tasks for this contact.</p>
              </div>
            ) : (
              <div className="space-y-2">
                {openTasks.map((task) => (
                  <div
                    key={task.id}
                    className="flex items-start gap-3 rounded-xl border border-zinc-800 bg-zinc-900 px-3.5 py-3"
                  >
                    <span
                      className={cn(
                        "h-2 w-2 rounded-full flex-shrink-0 mt-1.5",
                        task.status === "in_progress" ? "bg-indigo-400" : "bg-amber-400"
                      )}
                    />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm text-zinc-200">{task.title}</p>
                      {task.due_date && (
                        <p className="text-[11px] text-zinc-500 mt-0.5 flex items-center gap-1">
                          <Calendar className="h-3 w-3" /> Due {task.due_date}
                        </p>
                      )}
                    </div>
                    <Badge
                      variant={task.status === "in_progress" ? "indigo" : "amber"}
                      size="sm"
                    >
                      {task.status.replace("_", " ")}
                    </Badge>
                  </div>
                ))}
                {doneTasks.length > 0 && openTasks.length > 0 && (
                  <div className="border-t border-zinc-800 pt-2 mt-1">
                    <p className="text-[10px] font-mono text-zinc-600 uppercase tracking-widest mb-2">
                      Completed ({doneTasks.length})
                    </p>
                    {doneTasks.slice(0, 3).map((task) => (
                      <div
                        key={task.id}
                        className="flex items-start gap-3 rounded-xl border border-zinc-800 bg-zinc-900 px-3.5 py-3 mb-2"
                      >
                        <span className="h-2 w-2 rounded-full flex-shrink-0 mt-1.5 bg-emerald-400" />
                        <p className="text-sm text-zinc-500 line-through">{task.title}</p>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </Card>

          {/* Timeline */}
          <Card className="p-4 space-y-3">
            <div className="flex items-center gap-2">
              <Zap className="h-4 w-4 text-indigo-400" />
              <p className="text-sm font-semibold text-zinc-200">Activity Timeline</p>
            </div>

            {timelineLoading ? (
              <div className="space-y-2">
                {[1, 2, 3].map((i) => (
                  <div key={i} className="h-14 rounded-xl border border-zinc-800 bg-zinc-900 animate-pulse" />
                ))}
              </div>
            ) : timeline.length === 0 ? (
              <div className="flex flex-col items-center gap-2 py-6 text-center">
                <Zap className="h-6 w-6 text-zinc-700" />
                <p className="text-xs text-zinc-500">No activity recorded yet.</p>
              </div>
            ) : (
              <div className="relative">
                {timeline.map((evt, i) => {
                  const dotColor =
                    evt.type === "message" ? "bg-indigo-400" :
                    evt.type === "deal_moved" || evt.type === "deal_stage" ? "bg-amber-400" :
                    evt.type === "call" ? "bg-emerald-400" :
                    "bg-zinc-600";
                  const typeLabel =
                    evt.type === "message" ? "Email" :
                    evt.type === "deal_moved" || evt.type === "deal_stage" ? "Stage" :
                    evt.type === "call" ? "Call" :
                    "Activity";
                  return (
                    <div key={evt.id} className="flex gap-3">
                      <div className="flex flex-col items-center flex-shrink-0">
                        <span className={cn("mt-1.5 h-2.5 w-2.5 rounded-full", dotColor)} />
                        {i < timeline.length - 1 && (
                          <span className="flex-1 w-px bg-zinc-800 mt-1" />
                        )}
                      </div>
                      <div className="pb-4 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="text-[10px] font-mono text-zinc-500 uppercase tracking-widest">
                            {typeLabel}
                          </span>
                          <span className="text-[10px] text-zinc-600">{formatRelative(evt.ts)}</span>
                        </div>
                        <p className="text-xs font-medium text-zinc-300 mt-0.5">{evt.title}</p>
                        {evt.body && (
                          <p className="text-xs text-zinc-500 mt-0.5 line-clamp-2">{evt.body}</p>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </Card>
        </div>
      </div>

      {/* ── Email draft modal ── */}
      {emailDraft && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4"
          onClick={() => setEmailDraft(null)}
        >
          <div
            className="w-full max-w-lg rounded-2xl border border-zinc-800 bg-zinc-950 overflow-hidden shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between border-b border-zinc-800 px-5 py-4">
              <div className="flex items-center gap-2">
                <Mail className="h-4 w-4 text-indigo-400" />
                <p className="text-sm font-semibold text-zinc-100">AI-Generated Draft</p>
              </div>
              <button
                onClick={() => setEmailDraft(null)}
                className="text-zinc-400 hover:text-zinc-100 cursor-pointer transition-colors"
                aria-label="Close draft"
              >
                <XCircle className="h-4 w-4" />
              </button>
            </div>
            <div className="p-5 space-y-4">
              <div>
                <p className="text-[10px] font-mono text-zinc-500 uppercase tracking-widest mb-1">Subject</p>
                <p className="text-sm text-zinc-100 rounded-lg border border-zinc-800 bg-zinc-900 px-3 py-2">
                  {emailDraft.subject}
                </p>
              </div>
              <div>
                <p className="text-[10px] font-mono text-zinc-500 uppercase tracking-widest mb-1">Body</p>
                <div className="rounded-lg border border-zinc-800 bg-zinc-900 px-3 py-3 max-h-64 overflow-y-auto">
                  <div
                    className="text-sm text-zinc-200 leading-relaxed [&_strong]:font-semibold [&_ul]:my-1 [&_li]:ml-4 [&_li]:list-disc [&_p]:mt-2 first:[&_p]:mt-0"
                    dangerouslySetInnerHTML={{ __html: renderMarkdown(emailDraft.body) }}
                  />
                </div>
              </div>
              <Button
                variant="primary"
                className="w-full justify-center"
                onClick={() => {
                  navigator.clipboard.writeText(
                    `Subject: ${emailDraft.subject}\n\n${emailDraft.body}`
                  );
                }}
              >
                <Mail className="h-3.5 w-3.5" /> Copy to Clipboard
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* ── Delete confirm modal ── */}
      {deleteConfirm && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4"
          onClick={() => { setDeleteConfirm(false); setDeleteText(""); }}
        >
          <div
            className="w-full max-w-md rounded-2xl border border-zinc-800 bg-zinc-950 overflow-hidden shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between border-b border-zinc-800 px-5 py-4">
              <div className="flex items-center gap-2">
                <Trash2 className="h-4 w-4 text-rose-400" />
                <p className="text-sm font-semibold text-zinc-100">Delete Deal</p>
              </div>
              <button
                onClick={() => { setDeleteConfirm(false); setDeleteText(""); }}
                className="text-zinc-400 hover:text-zinc-100 cursor-pointer transition-colors"
                aria-label="Close"
              >
                <XCircle className="h-4 w-4" />
              </button>
            </div>
            <div className="p-5 space-y-4">
              <p className="text-sm text-zinc-400">
                This action cannot be undone. Type{" "}
                <span className="font-mono text-zinc-200">{deal.title}</span> to confirm.
              </p>
              <input
                type="text"
                value={deleteText}
                onChange={(e) => setDeleteText(e.target.value)}
                placeholder={deal.title ?? "Deal title"}
                autoFocus
                className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3.5 py-2.5 text-sm text-zinc-100 placeholder-zinc-600 focus:border-rose-500 focus:outline-none focus:ring-1 focus:ring-rose-500 transition"
              />
              <div className="flex gap-2">
                <Button
                  variant="secondary"
                  className="flex-1 justify-center"
                  onClick={() => { setDeleteConfirm(false); setDeleteText(""); }}
                >
                  Cancel
                </Button>
                <Button
                  variant="primary"
                  className="flex-1 justify-center bg-rose-600 hover:bg-rose-500 border-rose-600 focus:ring-rose-500 disabled:opacity-40"
                  disabled={deleteText !== (deal.title ?? "") || deleting}
                  onClick={handleDelete}
                >
                  {deleting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Trash2 className="h-3.5 w-3.5" />}
                  Delete Deal
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
