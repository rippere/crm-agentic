"use client";

import { useState, useEffect, useCallback, type KeyboardEvent } from "react";
import { useParams, useRouter } from "next/navigation";
import Header from "@/components/layout/Header";
import Card from "@/components/ui/Card";
import Badge from "@/components/ui/Badge";
import Avatar from "@/components/ui/Avatar";
import Button from "@/components/ui/Button";
import { cn, formatCurrency, leadScoreConfig, stageConfig } from "@/lib/utils";
import { apiClient } from "@/lib/api-client";
import { createBrowserClient } from "@/lib/supabase";
import { useJobPoller } from "@/hooks/useJobPoller";
import type { Contact, ContactStatus, LeadScore, Deal, DealStage } from "@/lib/types";
import {
  ArrowLeft, Mail, Brain, Zap, TrendingUp, TrendingDown, Minus,
  CheckCircle2, Clock, Building2, Briefcase, Tag, ListTodo,
  Loader2, AlertTriangle, FileText, XCircle, Phone, ChevronRight,
  Star, Calendar, X, Plus, Send, BarChart2, Download, Layers, Sparkles,
} from "lucide-react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip as RechartTooltip, ResponsiveContainer,
} from "recharts";

// ─── Helpers ─────────────────────────────────────────────────────────────────

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

const statusConfig: Record<ContactStatus, { label: string; variant: "indigo" | "emerald" | "amber" | "rose" | "zinc" }> = {
  lead: { label: "Lead", variant: "zinc" },
  prospect: { label: "Prospect", variant: "amber" },
  customer: { label: "Customer", variant: "emerald" },
  churned: { label: "Churned", variant: "rose" },
};

type TimelineEvent = {
  id: string;
  type: "message" | "call" | "deal_stage" | "activity";
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
  updated_at: string | null;
};

type DealRow = {
  id: string;
  title: string;
  company: string;
  value: number;
  stage: string;
  health_score: number;
  ml_win_probability: number;
  expected_close: string | null;
};

type HeatmapWeek = {
  week_start: string;
  messages: number;
  notes: number;
  total: number;
};

type EngagementScore = {
  score: number;
  message_count: number;
  note_count: number;
  tasks_total: number;
  tasks_done: number;
  components: { messages: number; notes: number; tasks: number };
};

type DealSummary = {
  total_pipeline_value: number;
  closed_won_value: number;
  open_deal_count: number;
  win_rate: number | null;
  avg_deal_size: number | null;
  total_deals: number;
};

type ResponseTime = {
  avg_response_hours: number | null;
  p50_response_hours: number | null;
  p90_response_hours: number | null;
  message_pairs_count: number;
  trend_30d: number | null;
};

type SentimentWeek = {
  week: string;
  score: number;
  message_count: number;
};

type WinRateQuarter = {
  quarter: string;
  won: number;
  lost: number;
  total: number;
  win_rate: number;
};

type DealStageStep = {
  stage: string;
  label: string;
  entered_at: string;
  days_in_stage: number;
  is_current: boolean;
};

type DealProgression = {
  id: string;
  title: string;
  stage: string;
  value: number;
  stages: DealStageStep[];
};

// ─── Sub-components ───────────────────────────────────────────────────────────

function StatusDot({ status }: { status: string }) {
  const colors: Record<string, string> = {
    open: "bg-amber-400",
    in_progress: "bg-indigo-400",
    done: "bg-emerald-400",
    cancelled: "bg-zinc-600",
  };
  return <span className={cn("h-2 w-2 rounded-full flex-shrink-0 mt-1.5", colors[status] ?? "bg-zinc-500")} />;
}

function TaskCard({ task }: { task: TaskRow }) {
  return (
    <div className="flex items-start gap-3 rounded-xl border border-zinc-800 bg-zinc-900 px-3.5 py-3">
      <StatusDot status={task.status} />
      <div className="flex-1 min-w-0">
        <p className={cn("text-sm text-zinc-200", task.status === "done" && "line-through text-zinc-500")}>
          {task.title}
        </p>
        {task.due_date && (
          <p className="text-[11px] text-zinc-500 mt-0.5 flex items-center gap-1">
            <Calendar className="h-3 w-3" />
            Due {task.due_date}
          </p>
        )}
      </div>
      <Badge
        variant={task.status === "done" ? "emerald" : task.status === "open" ? "amber" : "indigo"}
        size="sm"
      >
        {task.status.replace("_", " ")}
      </Badge>
    </div>
  );
}

function DealCard({ deal }: { deal: DealRow }) {
  const stage = deal.stage as DealStage;
  const cfg = stageConfig[stage] ?? { label: deal.stage, color: "text-zinc-400" };
  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900 px-3.5 py-3 space-y-2">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-sm font-medium text-zinc-100 truncate">{deal.title}</p>
          <p className="text-xs text-zinc-500 truncate">{deal.company}</p>
        </div>
        <span className={cn("text-xs font-mono font-semibold flex-shrink-0", cfg.color)}>
          {cfg.label}
        </span>
      </div>
      <div className="flex items-center gap-3 text-xs text-zinc-400">
        <span className="font-mono font-semibold text-zinc-200">{formatCurrency(deal.value)}</span>
        <span>·</span>
        <span>Win {deal.ml_win_probability}%</span>
        {deal.expected_close && (
          <>
            <span>·</span>
            <span>Closes {deal.expected_close}</span>
          </>
        )}
      </div>
      {/* Health bar */}
      <div className="flex items-center gap-2">
        <div className="flex-1 h-1 rounded-full bg-zinc-800">
          <div
            className={cn(
              "h-full rounded-full",
              deal.health_score >= 70 ? "bg-emerald-400" : deal.health_score >= 40 ? "bg-amber-400" : "bg-rose-400"
            )}
            style={{ width: `${deal.health_score}%` }}
          />
        </div>
        <span className="text-[11px] font-mono text-zinc-500">{deal.health_score} health</span>
      </div>
    </div>
  );
}

// ─── Contact Notes Thread ─────────────────────────────────────────────────────

type ContactNote = {
  id: string;
  workspace_id: string;
  contact_id: string;
  body: string;
  author: string | null;
  created_at: string;
};

interface ContactNotesThreadProps {
  contactId: string;
  workspaceId: string;
  token: string;
}

function noteAuthorInitials(author: string | null): string {
  if (!author) return "?";
  const parts = author.replace(/@.*/, "").replace(/[._-]+/g, " ").trim().split(/\s+/);
  return parts.map((p) => p[0]).join("").slice(0, 2).toUpperCase() || "?";
}

function ContactNotesThread({ contactId, workspaceId, token }: ContactNotesThreadProps) {
  const [notes, setNotes]     = useState<ContactNote[]>([]);
  const [loading, setLoading] = useState(true);
  const [draft, setDraft]     = useState("");
  const [saving, setSaving]   = useState(false);
  const [error, setError]     = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    apiClient
      .getContactNotes(workspaceId, contactId, token)
      .then((data) => { if (!cancelled) setNotes(Array.isArray(data) ? (data as ContactNote[]) : []); })
      .catch(() => { if (!cancelled) setNotes([]); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [workspaceId, contactId, token]);

  const handleAdd = async () => {
    const body = draft.trim();
    if (!body || saving) return;
    setSaving(true);
    setError(false);
    try {
      const created = (await apiClient.createContactNote(workspaceId, contactId, body, token)) as ContactNote;
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
              <Avatar initials={noteAuthorInitials(note.author)} size="sm" />
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

const TAG_COLORS = ["indigo", "emerald", "amber", "rose"] as const;

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function ContactDetailPage() {
  const params = useParams();
  const router = useRouter();
  const contactId = params?.id as string;

  const [contact, setContact] = useState<Contact | null>(null);
  const [loading, setLoading] = useState(true);
  const [token, setToken] = useState<string | null>(null);
  const [workspaceId, setWorkspaceId] = useState<string | null>(null);

  const [timeline, setTimeline] = useState<TimelineEvent[]>([]);
  const [timelineLoading, setTimelineLoading] = useState(false);
  const [deals, setDeals] = useState<DealRow[]>([]);
  const [dealsLoading, setDealsLoading] = useState(false);
  const [tasks, setTasks] = useState<TaskRow[]>([]);
  const [tasksLoading, setTasksLoading] = useState(false);
  const [heatmap, setHeatmap] = useState<HeatmapWeek[]>([]);
  const [heatmapLoading, setHeatmapLoading] = useState(false);
  const [engagementScore, setEngagementScore] = useState<EngagementScore | null>(null);
  const [engagementLoading, setEngagementLoading] = useState(false);
  const [dealSummary, setDealSummary] = useState<DealSummary | null>(null);
  const [responseTime, setResponseTime] = useState<ResponseTime | null>(null);
  const [sentimentTrend, setSentimentTrend] = useState<SentimentWeek[] | null>(null);
  const [sentimentLoading, setSentimentLoading] = useState(false);
  const [winRateTrend, setWinRateTrend] = useState<WinRateQuarter[] | null>(null);
  const [dealProgression, setDealProgression] = useState<DealProgression[] | null>(null);

  const [brief, setBrief] = useState<{ contact_name: string; brief: string } | null>(null);
  const [briefLoading, setBriefLoading] = useState(false);
  const [briefOpen, setBriefOpen] = useState(false);

  const [emailDraft, setEmailDraft] = useState<{ subject: string; body: string } | null>(null);
  const [emailLoading, setEmailLoading] = useState(false);

  const [outreachDraft, setOutreachDraft] = useState<{ subject: string; body: string } | null>(null);
  const [outreachLoading, setOutreachLoading] = useState(false);

  const scorePoller = useJobPoller();
  const enrichPoller = useJobPoller();
  const [exportLoading, setExportLoading] = useState(false);

  // Tag editor state
  const [addingTag, setAddingTag] = useState(false);
  const [tagInput, setTagInput] = useState("");
  const [savingTags, setSavingTags] = useState(false);

  const persistTags = useCallback(async (updated: Contact["semanticTags"]) => {
    if (!token || !workspaceId) return;
    setSavingTags(true);
    try {
      await apiClient.updateContactTags(workspaceId, contactId, updated, token);
    } finally {
      setSavingTags(false);
    }
  }, [token, workspaceId, contactId]);

  const removeTag = useCallback((index: number) => {
    if (!contact) return;
    const prev = contact.semanticTags;
    const updated = prev.filter((_, i) => i !== index);
    setContact(c => c ? { ...c, semanticTags: updated } : c);
    persistTags(updated).catch(() => setContact(c => c ? { ...c, semanticTags: prev } : c));
  }, [contact, persistTags]);

  const commitTag = useCallback(() => {
    const label = tagInput.trim().toLowerCase().replace(/[^a-z0-9-]/g, "-").replace(/^-+|-+$/g, "");
    setAddingTag(false);
    setTagInput("");
    if (!label || !contact) return;
    if (contact.semanticTags.some(t => t.label === label)) return;
    const color = TAG_COLORS[contact.semanticTags.length % TAG_COLORS.length];
    const updated = [...contact.semanticTags, { label, confidence: 1.0, color }];
    setContact(c => c ? { ...c, semanticTags: updated } : c);
    persistTags(updated).catch(() =>
      setContact(c => c ? { ...c, semanticTags: updated.slice(0, -1) } : c)
    );
  }, [tagInput, contact, persistTags]);

  // Auth init
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

  // Load contact
  useEffect(() => {
    if (!token || !workspaceId) return;
    setLoading(true);

    if (process.env.NEXT_PUBLIC_DEMO_MODE === "true") {
      const { demoContacts } = require("@/lib/demo-data");
      const found = demoContacts.find((c: Contact) => c.id === contactId);
      setContact(found ?? null);
      setLoading(false);
      return;
    }

    apiClient
      .listContacts(workspaceId, token)
      .then((data: Contact[]) => {
        const found = (Array.isArray(data) ? data : []).find((c) => c.id === contactId);
        setContact(found ?? null);
      })
      .catch(() => setContact(null))
      .finally(() => setLoading(false));
  }, [token, workspaceId, contactId]);

  // Load timeline, deals, tasks in parallel once auth is ready
  const loadSideData = useCallback(async () => {
    if (!token || !workspaceId) return;

    setTimelineLoading(true);
    setDealsLoading(true);
    setTasksLoading(true);
    setHeatmapLoading(true);
    setEngagementLoading(true);

    apiClient
      .getContactTimeline(workspaceId, contactId, token)
      .then((data: TimelineEvent[]) => setTimeline(Array.isArray(data) ? data : []))
      .catch(() => setTimeline([]))
      .finally(() => setTimelineLoading(false));

    apiClient
      .listDeals(workspaceId, token, { contactId })
      .then((data: DealRow[]) => setDeals(Array.isArray(data) ? data : []))
      .catch(() => setDeals([]))
      .finally(() => setDealsLoading(false));

    apiClient
      .getTasks(workspaceId, token, { contactId })
      .then((data: TaskRow[]) => setTasks(Array.isArray(data) ? data : []))
      .catch(() => setTasks([]))
      .finally(() => setTasksLoading(false));

    apiClient
      .getContactActivityHeatmap(workspaceId, contactId, token)
      .then((data: HeatmapWeek[]) => setHeatmap(Array.isArray(data) ? data : []))
      .catch(() => setHeatmap([]))
      .finally(() => setHeatmapLoading(false));

    apiClient
      .getContactEngagementScore(workspaceId, contactId, token)
      .then((data: EngagementScore) => setEngagementScore(data))
      .catch(() => setEngagementScore(null))
      .finally(() => setEngagementLoading(false));

    apiClient
      .getContactDealSummary(workspaceId, contactId, token)
      .then((data: DealSummary) => setDealSummary(data))
      .catch(() => setDealSummary(null));

    apiClient
      .getContactResponseTime(workspaceId, contactId, token)
      .then((data: ResponseTime) => setResponseTime(data))
      .catch(() => setResponseTime(null));

    setSentimentLoading(true);
    apiClient
      .getSentimentTrend(workspaceId, contactId, token)
      .then((data) => setSentimentTrend(data?.weeks ?? null))
      .catch(() => setSentimentTrend(null))
      .finally(() => setSentimentLoading(false));

    apiClient
      .getContactWinRateTrend(workspaceId, contactId, token)
      .then((data) => setWinRateTrend(data?.quarters ?? null))
      .catch(() => setWinRateTrend(null));

    apiClient
      .getContactDealStageProgression(workspaceId, contactId, token)
      .then((data) => setDealProgression(data?.deals ?? null))
      .catch(() => setDealProgression(null));
  }, [token, workspaceId, contactId]);

  useEffect(() => {
    loadSideData();
  }, [loadSideData]);

  const handleGetBrief = async () => {
    if (!token || !workspaceId) return;
    setBriefLoading(true);
    setBriefOpen(true);
    try {
      const data = await apiClient.getMeetingBrief(workspaceId, contactId, token);
      setBrief(data as { contact_name: string; brief: string });
    } catch {
      setBrief(null);
    } finally {
      setBriefLoading(false);
    }
  };

  const handleComposeEmail = async () => {
    if (!token || !workspaceId) return;
    setEmailLoading(true);
    try {
      const data = await apiClient.composeEmail(workspaceId, contactId, token);
      setEmailDraft(data as { subject: string; body: string });
    } catch {
      // ignore
    } finally {
      setEmailLoading(false);
    }
  };

  const handleDraftOutreach = async () => {
    if (!token || !workspaceId) return;
    setOutreachLoading(true);
    try {
      const data = await apiClient.getDraftOutreach(workspaceId, contactId, token);
      setOutreachDraft({ subject: data.subject, body: data.body });
    } catch {
      // ignore
    } finally {
      setOutreachLoading(false);
    }
  };

  const handleScoreContact = async () => {
    if (!token || !workspaceId) return;
    try {
      const res = await apiClient.scoreContact(workspaceId, contactId, token) as { job_id?: string };
      if (res?.job_id) scorePoller.start(res.job_id);
    } catch { /* ignore */ }
  };

  const handleEnrichContact = async () => {
    if (!token || !workspaceId) return;
    try {
      const res = await apiClient.enrichContact(workspaceId, contactId, token) as { job_id?: string };
      if (res?.job_id) enrichPoller.start(res.job_id);
    } catch { /* ignore */ }
  };

  const handleExportTimeline = async () => {
    if (!token || !workspaceId) return;
    setExportLoading(true);
    try {
      const blob = await apiClient.exportContactTimeline(workspaceId, contactId, token);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `timeline_${contactId}.csv`;
      a.click();
      URL.revokeObjectURL(url);
    } catch { /* ignore */ } finally {
      setExportLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-6 w-6 text-indigo-400 animate-spin" />
      </div>
    );
  }

  if (!contact) {
    return (
      <div className="flex flex-col items-center justify-center h-64 gap-4">
        <AlertTriangle className="h-8 w-8 text-zinc-600" />
        <p className="text-sm text-zinc-500">Contact not found.</p>
        <Button variant="secondary" onClick={() => router.push("/contacts")}>
          <ArrowLeft className="h-3.5 w-3.5" /> Back to Contacts
        </Button>
      </div>
    );
  }

  const leadCfg = leadScoreConfig[contact.mlScore.label as LeadScore];
  const statusCfg = statusConfig[contact.status];
  const trendIcon =
    contact.mlScore.trend === "up" ? (
      <TrendingUp className="h-3.5 w-3.5 text-emerald-400" />
    ) : contact.mlScore.trend === "down" ? (
      <TrendingDown className="h-3.5 w-3.5 text-rose-400" />
    ) : (
      <Minus className="h-3.5 w-3.5 text-zinc-400" />
    );

  const openTasks = tasks.filter((t) => t.status === "open" || t.status === "in_progress");
  const doneTasks = tasks.filter((t) => t.status === "done" || t.status === "cancelled");

  return (
    <div className="flex flex-col gap-6 p-4 md:p-6">
      {/* Page header */}
      <Header
        title={contact.name}
        subtitle={`${contact.role} · ${contact.company}`}
      />

      {/* Back + Actions */}
      <div className="flex flex-wrap items-center gap-2">
        <Button
          variant="secondary"
          onClick={() => router.push("/contacts")}
          className="gap-1.5"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          Contacts
        </Button>

        <div className="flex-1" />

        <Button
          variant="secondary"
          onClick={handleGetBrief}
          disabled={briefLoading}
          className="gap-1.5"
        >
          {briefLoading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <FileText className="h-3.5 w-3.5" />}
          Meeting Brief
        </Button>

        <Button
          variant="secondary"
          onClick={handleComposeEmail}
          disabled={emailLoading}
          className="gap-1.5"
        >
          {emailLoading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Mail className="h-3.5 w-3.5" />}
          Compose Email
        </Button>

        <Button
          variant="secondary"
          onClick={handleDraftOutreach}
          disabled={outreachLoading}
          className="gap-1.5"
        >
          {outreachLoading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5" />}
          Draft Outreach
        </Button>

        <Button
          variant="secondary"
          onClick={handleScoreContact}
          disabled={scorePoller.state === "pending" || scorePoller.state === "started"}
          className="gap-1.5"
        >
          {scorePoller.state === "pending" || scorePoller.state === "started" ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : scorePoller.state === "success" ? (
            <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />
          ) : (
            <Brain className="h-3.5 w-3.5" />
          )}
          Score
        </Button>

        <Button
          variant="secondary"
          onClick={handleEnrichContact}
          disabled={enrichPoller.state === "pending" || enrichPoller.state === "started"}
          className="gap-1.5"
        >
          {enrichPoller.state === "pending" || enrichPoller.state === "started" ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : enrichPoller.state === "success" ? (
            <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />
          ) : (
            <Zap className="h-3.5 w-3.5" />
          )}
          Enrich
        </Button>

        <Button
          variant="secondary"
          onClick={handleExportTimeline}
          disabled={exportLoading}
          className="gap-1.5"
        >
          {exportLoading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Download className="h-3.5 w-3.5" />}
          Export Timeline
        </Button>
      </div>

      {/* Main layout: left profile + right content */}
      <div className="grid grid-cols-1 lg:grid-cols-[320px_1fr] gap-6">

        {/* ── Left: Contact profile ── */}
        <div className="flex flex-col gap-4">

          {/* Identity card */}
          <Card className="p-5 space-y-4">
            <div className="flex items-start gap-4">
              <Avatar initials={contact.avatar} size="lg" />
              <div className="min-w-0">
                <h2 className="text-base font-semibold text-zinc-100">{contact.name}</h2>
                <p className="text-sm text-zinc-400 truncate">{contact.email}</p>
                <div className="flex items-center gap-2 mt-2">
                  <Badge variant={statusCfg.variant} size="sm">{statusCfg.label}</Badge>
                </div>
              </div>
            </div>

            <div className="space-y-2.5 text-sm">
              <div className="flex items-center gap-2.5 text-zinc-400">
                <Building2 className="h-3.5 w-3.5 flex-shrink-0 text-zinc-600" />
                <span className="text-zinc-300">{contact.company}</span>
              </div>
              <div className="flex items-center gap-2.5 text-zinc-400">
                <Briefcase className="h-3.5 w-3.5 flex-shrink-0 text-zinc-600" />
                <span className="text-zinc-300">{contact.role}</span>
              </div>
              <div className="flex items-center gap-2.5 text-zinc-400">
                <Mail className="h-3.5 w-3.5 flex-shrink-0 text-zinc-600" />
                <a href={`mailto:${contact.email}`} className="text-indigo-400 hover:text-indigo-300 truncate transition-colors">
                  {contact.email}
                </a>
              </div>
              <div className="flex items-center gap-2.5 text-zinc-400">
                <Clock className="h-3.5 w-3.5 flex-shrink-0 text-zinc-600" />
                <span className="text-zinc-500 text-xs">{contact.lastActivity}</span>
              </div>
            </div>
          </Card>

          {/* ML Score card */}
          <Card className="p-4 space-y-3">
            <div className="flex items-center gap-2">
              <Brain className="h-4 w-4 text-indigo-400" />
              <p className="text-xs font-semibold text-zinc-300">Lead Intelligence</p>
            </div>

            <div className="flex items-center gap-3">
              {trendIcon}
              <div className="flex-1">
                <div className="h-2 rounded-full bg-zinc-800 overflow-hidden">
                  <div
                    className={cn(
                      "h-full rounded-full transition-all",
                      contact.mlScore.label === "hot"
                        ? "bg-emerald-400"
                        : contact.mlScore.label === "warm"
                        ? "bg-amber-400"
                        : "bg-zinc-500"
                    )}
                    style={{ width: `${contact.mlScore.value}%` }}
                  />
                </div>
              </div>
              <span className={cn("text-sm font-mono font-bold", leadCfg?.text)}>
                {contact.mlScore.value}
              </span>
              <Badge
                variant={contact.mlScore.label === "hot" ? "emerald" : contact.mlScore.label === "warm" ? "amber" : "zinc"}
                size="sm"
              >
                {contact.mlScore.label}
              </Badge>
            </div>

            {contact.mlScore.signals.length > 0 && (
              <div className="space-y-1">
                <p className="text-[10px] font-mono text-zinc-500 uppercase tracking-widest">Signals</p>
                {contact.mlScore.signals.map((sig, i) => (
                  <div key={i} className="flex items-center gap-1.5 text-xs text-zinc-400">
                    <ChevronRight className="h-3 w-3 text-zinc-600 flex-shrink-0" />
                    {sig}
                  </div>
                ))}
              </div>
            )}
          </Card>

          {/* Engagement Score */}
          <Card className="p-4 space-y-3">
            <div className="flex items-center gap-2">
              <TrendingUp className="h-4 w-4 text-indigo-400" />
              <p className="text-xs font-semibold text-zinc-300">Engagement Score</p>
              <span className="ml-auto text-[10px] text-zinc-500">90 days</span>
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
                  {/* SVG ring */}
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
                  {/* Breakdown */}
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

          {/* Semantic tags — inline chip editor */}
          <Card className="p-4 space-y-3">
            <div className="flex items-center gap-2">
              <Tag className="h-4 w-4 text-indigo-400" />
              <p className="text-xs font-semibold text-zinc-300">Semantic Tags</p>
              {savingTags && <Loader2 className="h-3 w-3 animate-spin text-zinc-500 ml-auto" />}
            </div>
            <div className="flex flex-wrap gap-1.5">
              {contact.semanticTags.map((tag, i) => (
                <span
                  key={i}
                  className={cn(
                    "inline-flex items-center gap-1 rounded-lg border px-2.5 py-0.5 text-xs font-medium",
                    tag.color === "indigo" && "border-indigo-500/30 bg-indigo-500/10 text-indigo-300",
                    tag.color === "emerald" && "border-emerald-500/30 bg-emerald-500/10 text-emerald-300",
                    tag.color === "amber" && "border-amber-500/30 bg-amber-500/10 text-amber-300",
                    tag.color === "rose" && "border-rose-500/30 bg-rose-500/10 text-rose-300",
                  )}
                >
                  {tag.label}
                  <button
                    onClick={() => removeTag(i)}
                    className="ml-0.5 rounded-full text-current opacity-50 hover:opacity-100 transition-opacity"
                    aria-label={`Remove tag ${tag.label}`}
                  >
                    <X className="h-2.5 w-2.5" />
                  </button>
                </span>
              ))}
              {addingTag ? (
                <input
                  autoFocus
                  value={tagInput}
                  onChange={e => setTagInput(e.target.value)}
                  onKeyDown={e => {
                    if (e.key === "Enter" || e.key === ",") { e.preventDefault(); commitTag(); }
                    if (e.key === "Escape") { setAddingTag(false); setTagInput(""); }
                  }}
                  onBlur={commitTag}
                  className="text-xs bg-zinc-800 border border-zinc-600 rounded-lg px-2.5 py-0.5 text-zinc-100 focus:outline-none focus:border-indigo-500 w-24"
                  placeholder="tag name"
                />
              ) : (
                <button
                  onClick={() => setAddingTag(true)}
                  className="inline-flex items-center gap-1 rounded-lg border border-dashed border-zinc-700 px-2.5 py-0.5 text-xs text-zinc-500 hover:border-zinc-500 hover:text-zinc-300 transition-colors"
                >
                  <Plus className="h-3 w-3" />
                  Add tag
                </button>
              )}
            </div>
          </Card>

          {/* Revenue snapshot */}
          <Card className="p-4">
            <div className="flex items-center justify-between">
              <p className="text-xs font-semibold text-zinc-400">Revenue</p>
              <span className="text-lg font-mono font-bold text-zinc-100">{formatCurrency(contact.revenue)}</span>
            </div>
            <div className="flex items-center justify-between mt-2">
              <p className="text-xs text-zinc-500">Active deals</p>
              <span className="text-sm font-mono text-zinc-300">{contact.deals}</span>
            </div>
          </Card>

          {/* Deal value summary */}
          {dealSummary && dealSummary.total_deals > 0 && (
            <Card className="p-4 space-y-3">
              <p className="text-xs font-semibold text-zinc-400">Deal Value Summary</p>
              <div className="grid grid-cols-2 gap-x-4 gap-y-3">
                <div>
                  <p className="text-[10px] text-zinc-500 uppercase tracking-wider mb-0.5">Pipeline</p>
                  <p className="text-sm font-mono font-semibold text-zinc-100">{formatCurrency(dealSummary.total_pipeline_value)}</p>
                </div>
                <div>
                  <p className="text-[10px] text-zinc-500 uppercase tracking-wider mb-0.5">Closed Won</p>
                  <p className="text-sm font-mono font-semibold text-emerald-400">{formatCurrency(dealSummary.closed_won_value)}</p>
                </div>
                <div>
                  <p className="text-[10px] text-zinc-500 uppercase tracking-wider mb-0.5">Win Rate</p>
                  <p className="text-sm font-mono font-semibold text-zinc-100">
                    {dealSummary.win_rate != null ? `${dealSummary.win_rate}%` : "—"}
                  </p>
                </div>
                <div>
                  <p className="text-[10px] text-zinc-500 uppercase tracking-wider mb-0.5">Avg Deal</p>
                  <p className="text-sm font-mono font-semibold text-zinc-100">
                    {dealSummary.avg_deal_size != null ? formatCurrency(dealSummary.avg_deal_size) : "—"}
                  </p>
                </div>
              </div>
              <div className="border-t border-zinc-800 pt-2 flex items-center justify-between">
                <p className="text-[10px] text-zinc-600">{dealSummary.total_deals} deal{dealSummary.total_deals !== 1 ? "s" : ""} total</p>
                <p className="text-[10px] text-zinc-600">{dealSummary.open_deal_count} open</p>
              </div>
            </Card>
          )}

          {/* Response Time */}
          {responseTime !== null && (
            <Card className="p-4 space-y-3">
              <div className="flex items-center gap-2">
                <Clock className="h-4 w-4 text-indigo-400" />
                <p className="text-xs font-semibold text-zinc-300">Response Time</p>
                {responseTime.message_pairs_count > 0 && (
                  <span className="ml-auto text-[10px] text-zinc-500">{responseTime.message_pairs_count} pairs</span>
                )}
              </div>

              {responseTime.message_pairs_count === 0 ? (
                <p className="text-xs text-zinc-600 italic py-1">No message pairs to analyze yet.</p>
              ) : (
                <div className="space-y-2">
                  {[
                    { label: "Avg", value: responseTime.avg_response_hours },
                    { label: "Median", value: responseTime.p50_response_hours },
                    { label: "P90", value: responseTime.p90_response_hours },
                  ].map(({ label, value }) => {
                    const hrs = value ?? 0;
                    const display = hrs < 1 ? `${Math.round(hrs * 60)}m` : hrs < 24 ? `${hrs}h` : `${(hrs / 24).toFixed(1)}d`;
                    const color = hrs <= 4 ? "text-emerald-400" : hrs <= 24 ? "text-amber-400" : "text-rose-400";
                    return (
                      <div key={label} className="flex items-center justify-between">
                        <span className="text-[11px] text-zinc-500">{label}</span>
                        <span className={cn("text-sm font-mono font-semibold", color)}>{display}</span>
                      </div>
                    );
                  })}
                  {responseTime.trend_30d !== null && (
                    <div className="border-t border-zinc-800 pt-2 flex items-center justify-between">
                      <span className="text-[10px] text-zinc-600">30-day avg</span>
                      <span className="text-[11px] font-mono text-zinc-400">
                        {responseTime.trend_30d < 1
                          ? `${Math.round(responseTime.trend_30d * 60)}m`
                          : responseTime.trend_30d < 24
                          ? `${responseTime.trend_30d}h`
                          : `${(responseTime.trend_30d / 24).toFixed(1)}d`}
                      </span>
                    </div>
                  )}
                </div>
              )}
            </Card>
          )}
        </div>

        {/* ── Right: Timeline, Deals, Tasks ── */}
        <div className="flex flex-col gap-6">

          {/* Deals */}
          <Card className="p-4 space-y-3">
            <div className="flex items-center gap-2">
              <TrendingUp className="h-4 w-4 text-indigo-400" />
              <p className="text-sm font-semibold text-zinc-200">Deals</p>
              {deals.length > 0 && (
                <span className="ml-auto text-xs font-mono text-zinc-500">{deals.length} total</span>
              )}
            </div>

            {dealsLoading ? (
              <div className="space-y-2">
                {[1, 2].map((i) => (
                  <div key={i} className="h-16 rounded-xl border border-zinc-800 bg-zinc-900 animate-pulse" />
                ))}
              </div>
            ) : deals.length === 0 ? (
              <div className="flex flex-col items-center gap-2 py-6 text-center">
                <TrendingUp className="h-6 w-6 text-zinc-700" />
                <p className="text-xs text-zinc-500">No deals for this contact yet.</p>
              </div>
            ) : (
              <div className="space-y-2">
                {deals.map((deal) => (
                  <DealCard key={deal.id} deal={deal} />
                ))}
              </div>
            )}
          </Card>

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
            ) : tasks.length === 0 ? (
              <div className="flex flex-col items-center gap-2 py-6 text-center">
                <ListTodo className="h-6 w-6 text-zinc-700" />
                <p className="text-xs text-zinc-500">No tasks for this contact.</p>
              </div>
            ) : (
              <div className="space-y-2">
                {openTasks.map((task) => (
                  <TaskCard key={task.id} task={task} />
                ))}
                {doneTasks.length > 0 && openTasks.length > 0 && (
                  <div className="border-t border-zinc-800 pt-2 mt-1">
                    <p className="text-[10px] font-mono text-zinc-600 uppercase tracking-widest mb-2">
                      Completed ({doneTasks.length})
                    </p>
                    {doneTasks.slice(0, 3).map((task) => (
                      <TaskCard key={task.id} task={task} />
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
                    evt.type === "call" ? "bg-emerald-400" :
                    evt.type === "deal_stage" ? "bg-amber-400" :
                    "bg-zinc-600";
                  const typeLabel =
                    evt.type === "message" ? "Email" :
                    evt.type === "call" ? "Call" :
                    evt.type === "deal_stage" ? "Deal" :
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

          {/* Sentiment Trend Sparkline */}
          {(sentimentLoading || (sentimentTrend !== null && sentimentTrend.length > 0)) && (
            <Card className="p-4 space-y-3">
              <div className="flex items-center gap-2">
                <TrendingUp className="h-4 w-4 text-indigo-400" />
                <p className="text-sm font-semibold text-zinc-200">Sentiment Trend</p>
                <span className="ml-auto text-[10px] font-mono text-zinc-500">12 weeks</span>
              </div>
              {sentimentLoading ? (
                <div className="flex gap-1 items-end h-8">
                  {Array.from({ length: 12 }).map((_, i) => (
                    <div key={i} className="flex-1 rounded-sm bg-zinc-800 animate-pulse" style={{ height: "32px" }} />
                  ))}
                </div>
              ) : (
                <div className="space-y-2">
                  <div className="flex gap-1 items-end h-10">
                    {(sentimentTrend ?? []).map((w) => {
                      const pct = Math.round(((w.score + 1) / 2) * 100);
                      const color =
                        w.score > 0.2
                          ? "bg-emerald-600"
                          : w.score < -0.2
                          ? "bg-rose-600"
                          : "bg-amber-500";
                      return (
                        <div
                          key={w.week}
                          title={`${w.week}: ${w.score > 0 ? "+" : ""}${w.score.toFixed(2)} (${w.message_count} msg)`}
                          className={cn("flex-1 rounded-sm cursor-default transition-opacity hover:opacity-75", color)}
                          style={{ height: `${Math.max(10, pct)}%` }}
                        />
                      );
                    })}
                  </div>
                  <div className="flex justify-between">
                    <span className="text-[10px] text-zinc-600">{sentimentTrend?.[0]?.week ?? ""}</span>
                    <span className="text-[10px] text-zinc-600">This week</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="h-2 w-2 rounded-sm bg-rose-600" />
                    <span className="text-[10px] text-zinc-500">Negative</span>
                    <span className="h-2 w-2 rounded-sm bg-amber-500 ml-2" />
                    <span className="text-[10px] text-zinc-500">Neutral</span>
                    <span className="h-2 w-2 rounded-sm bg-emerald-600 ml-2" />
                    <span className="text-[10px] text-zinc-500">Positive</span>
                  </div>
                </div>
              )}
            </Card>
          )}

          {/* Quarterly Win Rate Trend */}
          {winRateTrend !== null && winRateTrend.length > 0 && (
            <Card className="p-4 space-y-3">
              <div className="flex items-center gap-2">
                <TrendingUp className="h-4 w-4 text-indigo-400" />
                <p className="text-sm font-semibold text-zinc-200">Win Rate by Quarter</p>
                <span className="ml-auto text-[10px] font-mono text-zinc-500">2 years</span>
              </div>
              <ResponsiveContainer width="100%" height={110}>
                <LineChart data={winRateTrend} margin={{ top: 4, right: 4, left: -28, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
                  <XAxis
                    dataKey="quarter"
                    tick={{ fontSize: 9, fill: "#71717a" }}
                    tickLine={false}
                    axisLine={false}
                  />
                  <YAxis
                    domain={[0, 100]}
                    tick={{ fontSize: 9, fill: "#71717a" }}
                    tickLine={false}
                    axisLine={false}
                    tickFormatter={(v) => `${v}%`}
                  />
                  <RechartTooltip
                    contentStyle={{ background: "#18181b", border: "1px solid #3f3f46", borderRadius: 6, fontSize: 11 }}
                    labelStyle={{ color: "#e4e4e7", marginBottom: 4 }}
                    formatter={(v, _n, props) => {
                      const q = props.payload as WinRateQuarter | undefined;
                      return [`${v ?? 0}% (${q?.won ?? 0}W / ${q?.total ?? 0} deals)`, "Win rate"];
                    }}
                  />
                  <Line
                    type="monotone"
                    dataKey="win_rate"
                    stroke="#6366f1"
                    strokeWidth={2}
                    dot={{ r: 3, fill: "#6366f1", strokeWidth: 0 }}
                    activeDot={{ r: 5 }}
                  />
                </LineChart>
              </ResponsiveContainer>
            </Card>
          )}

          {/* Deal Stage Progression */}
          {dealProgression !== null && dealProgression.length > 0 && (
            <Card className="p-4 space-y-3">
              <div className="flex items-center gap-2">
                <Layers className="h-4 w-4 text-indigo-400" />
                <p className="text-sm font-semibold text-zinc-200">Deal Stage Journeys</p>
                <span className="ml-auto text-[10px] font-mono text-zinc-500">
                  {dealProgression.length} deal{dealProgression.length !== 1 ? "s" : ""}
                </span>
              </div>
              <div className="space-y-3">
                {dealProgression.map((deal) => {
                  const stageColors: Record<string, string> = {
                    discovery: "bg-zinc-600",
                    qualified: "bg-sky-700",
                    proposal: "bg-indigo-600",
                    negotiation: "bg-violet-600",
                    closed_won: "bg-emerald-600",
                    closed_lost: "bg-rose-700",
                  };
                  return (
                    <div key={deal.id} className="space-y-1.5">
                      <div className="flex items-center justify-between">
                        <p className="text-xs font-medium text-zinc-300 truncate max-w-[60%]">{deal.title}</p>
                        <span className="text-[10px] text-zinc-500">{formatCurrency(deal.value)}</span>
                      </div>
                      <div className="flex gap-0.5 items-center">
                        {deal.stages.map((s, i) => (
                          <div key={s.stage} className="flex items-center gap-0.5 flex-1 min-w-0">
                            <div
                              title={`${s.label}: ${s.days_in_stage}d`}
                              className={cn(
                                "h-4 w-full rounded-sm transition-opacity cursor-default",
                                stageColors[s.stage] ?? "bg-zinc-600",
                                s.is_current ? "opacity-100 ring-1 ring-white/30" : "opacity-50",
                              )}
                            />
                            {i < deal.stages.length - 1 && (
                              <ChevronRight className="h-2.5 w-2.5 text-zinc-700 flex-shrink-0" />
                            )}
                          </div>
                        ))}
                      </div>
                      <div className="flex gap-1 flex-wrap">
                        {deal.stages.map((s) => (
                          <span
                            key={s.stage}
                            className={cn(
                              "text-[9px] font-mono px-1 rounded",
                              s.is_current
                                ? "text-zinc-100 bg-zinc-700"
                                : "text-zinc-500 bg-zinc-900",
                            )}
                          >
                            {s.label} {s.days_in_stage}d
                          </span>
                        ))}
                      </div>
                    </div>
                  );
                })}
              </div>
            </Card>
          )}

          {/* 12-Week Activity Heatmap */}
          <Card className="p-4 space-y-3">
            <div className="flex items-center gap-2">
              <BarChart2 className="h-4 w-4 text-indigo-400" />
              <p className="text-sm font-semibold text-zinc-200">12-Week Activity</p>
            </div>

            {heatmapLoading ? (
              <div className="flex gap-1">
                {Array.from({ length: 12 }).map((_, i) => (
                  <div key={i} className="flex-1 h-8 rounded bg-zinc-800 animate-pulse" />
                ))}
              </div>
            ) : heatmap.length === 0 ? (
              <div className="flex flex-col items-center gap-2 py-4 text-center">
                <BarChart2 className="h-6 w-6 text-zinc-700" />
                <p className="text-xs text-zinc-500">No activity data.</p>
              </div>
            ) : (
              <div className="space-y-1.5">
                <div className="flex gap-1">
                  {heatmap.map((w) => {
                    const bg =
                      w.total === 0 ? "bg-zinc-800" :
                      w.total === 1 ? "bg-indigo-900" :
                      w.total <= 3 ? "bg-indigo-700" :
                      w.total <= 5 ? "bg-indigo-500" : "bg-indigo-400";
                    return (
                      <div
                        key={w.week_start}
                        title={`${w.week_start}: ${w.total} event${w.total !== 1 ? "s" : ""} (${w.messages} msg, ${w.notes} note${w.notes !== 1 ? "s" : ""})`}
                        className={cn("flex-1 h-8 rounded cursor-default transition-opacity hover:opacity-75", bg)}
                      />
                    );
                  })}
                </div>
                <div className="flex justify-between">
                  <span className="text-[10px] text-zinc-600">{heatmap[0]?.week_start}</span>
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

          {/* Notes */}
          {workspaceId && token && (
            <ContactNotesThread
              contactId={contactId}
              workspaceId={workspaceId}
              token={token}
            />
          )}
        </div>
      </div>

      {/* ── Meeting Brief Panel ── */}
      {briefOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4"
          onClick={() => setBriefOpen(false)}
        >
          <div
            className="w-full max-w-xl rounded-2xl border border-zinc-800 bg-zinc-950 overflow-hidden shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between border-b border-zinc-800 px-5 py-4">
              <div className="flex items-center gap-2">
                <Star className="h-4 w-4 text-amber-400" />
                <p className="text-sm font-semibold text-zinc-100">Meeting Brief</p>
              </div>
              <button
                onClick={() => setBriefOpen(false)}
                className="text-zinc-400 hover:text-zinc-100 cursor-pointer transition-colors"
                aria-label="Close brief"
              >
                <XCircle className="h-4 w-4" />
              </button>
            </div>
            <div className="p-5 max-h-[70vh] overflow-y-auto">
              {briefLoading ? (
                <div className="flex items-center justify-center py-12">
                  <Loader2 className="h-5 w-5 text-indigo-400 animate-spin" />
                </div>
              ) : brief ? (
                <div
                  className="text-sm text-zinc-200 leading-relaxed [&_strong]:text-zinc-100 [&_strong]:font-semibold [&_ul]:my-2 [&_li]:ml-4 [&_li]:list-disc [&_p]:mt-3 first:[&_p]:mt-0"
                  dangerouslySetInnerHTML={{ __html: renderMarkdown(brief.brief) }}
                />
              ) : (
                <p className="text-sm text-zinc-500 text-center py-8">Failed to generate brief.</p>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ── Email Draft Panel ── */}
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
                  navigator.clipboard.writeText(`Subject: ${emailDraft.subject}\n\n${emailDraft.body}`);
                }}
              >
                <Phone className="h-3.5 w-3.5" />
                Copy to Clipboard
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* ── Outreach Draft Panel ── */}
      {outreachDraft && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4"
          onClick={() => setOutreachDraft(null)}
        >
          <div
            className="w-full max-w-lg rounded-2xl border border-zinc-800 bg-zinc-950 overflow-hidden shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between border-b border-zinc-800 px-5 py-4">
              <div className="flex items-center gap-2">
                <Sparkles className="h-4 w-4 text-indigo-400" />
                <p className="text-sm font-semibold text-zinc-100">Outreach Draft</p>
              </div>
              <button
                onClick={() => setOutreachDraft(null)}
                className="text-zinc-400 hover:text-zinc-100 cursor-pointer transition-colors"
                aria-label="Close outreach draft"
              >
                <XCircle className="h-4 w-4" />
              </button>
            </div>
            <div className="p-5 space-y-4">
              <div>
                <p className="text-[10px] font-mono text-zinc-500 uppercase tracking-widest mb-1">Subject</p>
                <p className="text-sm text-zinc-100 rounded-lg border border-zinc-800 bg-zinc-900 px-3 py-2">
                  {outreachDraft.subject}
                </p>
              </div>
              <div>
                <p className="text-[10px] font-mono text-zinc-500 uppercase tracking-widest mb-1">Body</p>
                <div className="rounded-lg border border-zinc-800 bg-zinc-900 px-3 py-3 max-h-64 overflow-y-auto">
                  <div
                    className="text-sm text-zinc-200 leading-relaxed [&_strong]:font-semibold [&_ul]:my-1 [&_li]:ml-4 [&_li]:list-disc [&_p]:mt-2 first:[&_p]:mt-0"
                    dangerouslySetInnerHTML={{ __html: renderMarkdown(outreachDraft.body) }}
                  />
                </div>
              </div>
              <Button
                variant="primary"
                className="w-full justify-center"
                onClick={() => {
                  navigator.clipboard.writeText(`Subject: ${outreachDraft.subject}\n\n${outreachDraft.body}`);
                }}
              >
                <Phone className="h-3.5 w-3.5" />
                Copy to Clipboard
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
