"use client";

import { useState, useEffect, useCallback, useMemo } from "react";
import { useParams, useRouter } from "next/navigation";
import Header from "@/components/layout/Header";
import Card from "@/components/ui/Card";
import Badge from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import {
  cn, funnelStageConfig, funnelStageOrder,
  engagementScoreConfig, engagementLabelFromScore,
} from "@/lib/utils";
import { apiClient } from "@/lib/api-client";
import { createBrowserClient } from "@/lib/supabase";
import { isDemoMode } from "@/lib/demo-mode";
import { useJobPoller } from "@/hooks/useJobPoller";
import type { Lead, LeadStage, EngagementEvent } from "@/lib/types";
import {
  ArrowLeft, Loader2, AlertTriangle, Zap, UserPlus, ChevronRight,
  TrendingUp, Mail, Building2, Phone, CheckCircle2, Send, MousePointerClick,
  Reply, XCircle, Ban, Sparkles, Clock,
} from "lucide-react";
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid,
  Tooltip as RechartTooltip, ResponsiveContainer,
} from "recharts";

// ─── Normalizers (getLead/getLeadEvents return camelCase in demo, snake in live) ──

function normalizeLead(raw: unknown): Lead | null {
  if (!raw || typeof raw !== "object") return null;
  const r = raw as Record<string, unknown>;
  const get = <T,>(camel: string, snake: string, fallback: T): T =>
    (r[camel] ?? r[snake] ?? fallback) as T;
  const score = get<number>("score", "score", 0);
  const scoreDetail = (r.scoreDetail ?? r.score_detail) as Lead["scoreDetail"] | undefined;
  return {
    id: get<string>("id", "id", ""),
    workspaceId: get<string>("workspaceId", "workspace_id", ""),
    contactId: get<string | null>("contactId", "contact_id", null),
    name: get<string | null>("name", "name", null),
    email: get<string | null>("email", "email", null),
    phone: get<string | null>("phone", "phone", null),
    company: get<string | null>("company", "company", null),
    title: get<string | null>("title", "title", null),
    source: get<Lead["source"]>("source", "source", "import"),
    stage: get<LeadStage>("stage", "stage", "new"),
    score,
    scoreDetail: scoreDetail ?? { value: score, label: engagementLabelFromScore(score), signals: [] },
    ownerId: get<string | null>("ownerId", "owner_id", null),
    customFields: get<Record<string, unknown>>("customFields", "custom_fields", {}),
    externalId: get<string | null>("externalId", "external_id", null),
    lastEngagedAt: get<string | null>("lastEngagedAt", "last_engaged_at", null),
    createdAt: get<string | null>("createdAt", "created_at", null),
    updatedAt: get<string | null>("updatedAt", "updated_at", null),
  };
}

function normalizeEvent(raw: unknown): EngagementEvent {
  const r = raw as Record<string, unknown>;
  return {
    id: (r.id as string) ?? "",
    workspaceId: (r.workspaceId ?? r.workspace_id ?? "") as string,
    leadId: (r.leadId ?? r.lead_id ?? "") as string,
    campaignId: (r.campaignId ?? r.campaign_id ?? null) as string | null,
    enrollmentId: (r.enrollmentId ?? r.enrollment_id ?? null) as string | null,
    stepId: (r.stepId ?? r.step_id ?? null) as string | null,
    type: (r.type as EngagementEvent["type"]) ?? "queued",
    channel: (r.channel ?? null) as EngagementEvent["channel"],
    weight: (r.weight as number) ?? 0,
    metadata: (r.metadata as Record<string, unknown>) ?? {},
    occurredAt: (r.occurredAt ?? r.occurred_at ?? new Date().toISOString()) as string,
    createdAt: (r.createdAt ?? r.created_at ?? null) as string | null,
  };
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

const EVENT_META: Record<string, { label: string; icon: React.ElementType; color: string }> = {
  queued:       { label: "Queued",       icon: Clock,               color: "text-zinc-400" },
  sent:         { label: "Sent",         icon: Send,                color: "text-sky-400" },
  delivered:    { label: "Delivered",    icon: CheckCircle2,        color: "text-sky-400" },
  opened:       { label: "Opened",       icon: Mail,                color: "text-indigo-400" },
  clicked:      { label: "Clicked",      icon: MousePointerClick,   color: "text-violet-400" },
  replied:      { label: "Replied",      icon: Reply,               color: "text-emerald-400" },
  bounced:      { label: "Bounced",      icon: Ban,                 color: "text-rose-400" },
  unsubscribed: { label: "Unsubscribed", icon: XCircle,             color: "text-rose-400" },
  converted:    { label: "Converted",    icon: Sparkles,            color: "text-[#00C896]" },
  approved:     { label: "Approved",     icon: CheckCircle2,        color: "text-emerald-400" },
  rejected:     { label: "Rejected",     icon: XCircle,             color: "text-rose-400" },
};

// ─── Score gauge (semicircle) ────────────────────────────────────────────────

function ScoreGauge({ score }: { score: number }) {
  const cfg = engagementScoreConfig[engagementLabelFromScore(score)];
  const clamped = Math.max(0, Math.min(100, score));
  const R = 52;
  const C = Math.PI * R; // semicircle circumference
  const dash = (clamped / 100) * C;
  const strokeColor = clamped >= 70 ? "#34D399" : clamped >= 40 ? "#FBBF24" : "#71717A";
  return (
    <div className="flex flex-col items-center">
      <svg viewBox="0 0 120 66" className="w-40 h-[88px]">
        <path d="M 8 60 A 52 52 0 0 1 112 60" fill="none" stroke="#27272A" strokeWidth="8" strokeLinecap="round" />
        <path
          d="M 8 60 A 52 52 0 0 1 112 60"
          fill="none"
          stroke={strokeColor}
          strokeWidth="8"
          strokeLinecap="round"
          strokeDasharray={`${dash} ${C}`}
          className="transition-all duration-700"
        />
      </svg>
      <div className="-mt-6 flex flex-col items-center">
        <span className={cn("text-3xl font-bold font-mono", cfg.text)}>{clamped}</span>
        <div className={cn("mt-1 flex items-center gap-1 rounded-full px-2 py-0.5 text-xs", cfg.bg, cfg.text)}>
          <span className={cn("h-1.5 w-1.5 rounded-full", cfg.dot)} /> {cfg.label}
        </div>
      </div>
    </div>
  );
}

// ─── Page ────────────────────────────────────────────────────────────────────

export default function LeadDetailPage() {
  const params = useParams();
  const router = useRouter();
  const leadId = params?.id as string;

  const [lead, setLead] = useState<Lead | null>(null);
  const [loading, setLoading] = useState(true);
  const [token, setToken] = useState<string | null>(null);
  const [workspaceId, setWorkspaceId] = useState<string | null>(null);

  const [events, setEvents] = useState<EngagementEvent[]>([]);
  const [eventsLoading, setEventsLoading] = useState(false);

  const [moveSaving, setMoveSaving] = useState(false);
  const [promoting, setPromoting] = useState(false);
  const [promoteResult, setPromoteResult] = useState<{ contactId: string; dealId: string | null } | null>(null);
  const scorePoller = useJobPoller();

  // Auth
  useEffect(() => {
    if (isDemoMode) {
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

  const loadLead = useCallback(() => {
    if (!token || !workspaceId) return;
    setLoading(true);
    apiClient.getLead(workspaceId, leadId, token)
      .then((data) => setLead(normalizeLead(data)))
      .catch(() => setLead(null))
      .finally(() => setLoading(false));
  }, [token, workspaceId, leadId]);

  useEffect(() => { loadLead(); }, [loadLead]);

  useEffect(() => {
    if (!token || !workspaceId || !lead) return;
    setEventsLoading(true);
    apiClient.getLeadEvents(workspaceId, leadId, token)
      .then((data) => setEvents(Array.isArray(data) ? data.map(normalizeEvent) : []))
      .catch(() => setEvents([]))
      .finally(() => setEventsLoading(false));
  }, [token, workspaceId, leadId, lead]);

  // Re-load lead when a score recompute finishes.
  useEffect(() => {
    if (scorePoller.state === "success") loadLead();
  }, [scorePoller.state, loadLead]);

  // Score-trend series: cumulative weighted signal clamped 0-100, oldest→newest.
  const trend = useMemo(() => {
    const asc = [...events].sort((a, b) => new Date(a.occurredAt).getTime() - new Date(b.occurredAt).getTime());
    let running = 0;
    return asc.map((e) => {
      running = Math.max(0, Math.min(100, running + e.weight));
      return {
        date: new Date(e.occurredAt).toLocaleDateString("en-US", { month: "short", day: "numeric" }),
        score: running,
      };
    });
  }, [events]);

  // Derived enrollment rollup (no per-lead enrollment endpoint — group events).
  const enrollments = useMemo(() => {
    const byEnroll = new Map<string, { enrollmentId: string; campaignId: string | null; sent: number; lastAt: string; lastType: string }>();
    for (const e of events) {
      const key = e.enrollmentId ?? "unenrolled";
      const existing = byEnroll.get(key);
      const isSend = e.type === "sent";
      if (!existing) {
        byEnroll.set(key, { enrollmentId: key, campaignId: e.campaignId, sent: isSend ? 1 : 0, lastAt: e.occurredAt, lastType: e.type });
      } else {
        existing.sent += isSend ? 1 : 0;
        if (new Date(e.occurredAt).getTime() > new Date(existing.lastAt).getTime()) {
          existing.lastAt = e.occurredAt;
          existing.lastType = e.type;
        }
      }
    }
    return [...byEnroll.values()].filter((x) => x.enrollmentId !== "unenrolled");
  }, [events]);

  const handleMoveStage = async (stage: LeadStage) => {
    if (!token || !workspaceId || !lead) return;
    setMoveSaving(true);
    try {
      await apiClient.updateLeadStage(workspaceId, lead.id, stage, token);
      setLead((prev) => (prev ? { ...prev, stage } : null));
    } catch { /* ignore */ }
    finally { setMoveSaving(false); }
  };

  const handlePromote = async (createDeal: boolean) => {
    if (!token || !workspaceId || !lead || promoting) return;
    setPromoting(true);
    try {
      const res = await apiClient.promoteLead(workspaceId, lead.id, { create_deal: createDeal }, token);
      setPromoteResult({ contactId: res.contact_id, dealId: res.deal_id });
      setLead((prev) => (prev ? { ...prev, contactId: res.contact_id, stage: createDeal ? "converted" : "qualified" } : null));
    } catch { /* ignore */ }
    finally { setPromoting(false); }
  };

  const handleScore = async () => {
    if (!token || !workspaceId || !lead) return;
    try {
      const res = await apiClient.scoreLead(workspaceId, lead.id, token);
      if (res?.job_id && !res.job_id.startsWith("demo")) scorePoller.start(res.job_id);
    } catch { /* ignore */ }
  };

  if (loading) {
    return <div className="flex items-center justify-center h-64"><Loader2 className="h-6 w-6 text-indigo-400 animate-spin" /></div>;
  }

  if (!lead) {
    return (
      <div className="flex flex-col items-center justify-center h-64 gap-4">
        <AlertTriangle className="h-8 w-8 text-zinc-600" />
        <p className="text-sm text-zinc-500">Lead not found.</p>
        <Button variant="secondary" onClick={() => router.push("/leads")}>
          <ArrowLeft className="h-3.5 w-3.5" /> Back to Leads
        </Button>
      </div>
    );
  }

  const stageCfg = funnelStageConfig[lead.stage];
  const otherStages = funnelStageOrder.filter((s) => s !== lead.stage);
  const isConverted = lead.stage === "converted";

  return (
    <div className="flex flex-col gap-6 p-4 md:p-6">
      <Header title={lead.name ?? "Unnamed lead"} subtitle={`${lead.company ?? "—"} · ${stageCfg.label}`} />

      {/* Actions bar */}
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="secondary" onClick={() => router.push("/leads")} className="gap-1.5">
          <ArrowLeft className="h-3.5 w-3.5" /> Leads
        </Button>
        <div className="flex-1" />
        <Button
          variant="secondary"
          onClick={handleScore}
          disabled={scorePoller.state === "pending" || scorePoller.state === "started"}
          className="gap-1.5"
        >
          {scorePoller.state === "pending" || scorePoller.state === "started" ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : scorePoller.state === "success" ? (
            <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />
          ) : (
            <Zap className="h-3.5 w-3.5" />
          )}
          Recompute Score
        </Button>
        {!isConverted && (
          <Button variant="primary" onClick={() => handlePromote(false)} disabled={promoting} className="gap-1.5">
            {promoting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <UserPlus className="h-3.5 w-3.5" />}
            Promote to Contact
          </Button>
        )}
        {!isConverted && (
          <Button variant="cta" size="sm" onClick={() => handlePromote(true)} disabled={promoting} className="gap-1.5">
            <TrendingUp className="h-3.5 w-3.5" /> Promote + Deal
          </Button>
        )}
      </div>

      {promoteResult && (
        <div className="flex items-center gap-3 rounded-xl border border-emerald-500/30 bg-emerald-500/5 px-4 py-3">
          <CheckCircle2 className="h-4 w-4 text-emerald-400 flex-shrink-0" />
          <p className="text-sm text-emerald-300">
            Promoted — contact <span className="font-mono">{promoteResult.contactId.slice(0, 12)}</span>
            {promoteResult.dealId && <> · deal <span className="font-mono">{promoteResult.dealId.slice(0, 12)}</span></>} created.
          </p>
        </div>
      )}

      {/* Main grid */}
      <div className="grid grid-cols-1 lg:grid-cols-[320px_1fr] gap-6">

        {/* Left: overview + gauge + stage stepper */}
        <div className="flex flex-col gap-4">
          <Card className="p-5 space-y-4">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <h2 className="text-base font-semibold text-zinc-100 leading-snug truncate">{lead.name ?? "Unnamed lead"}</h2>
                <div className="flex items-center gap-1.5 mt-1 text-zinc-400">
                  <Building2 className="h-3.5 w-3.5 text-zinc-600 flex-shrink-0" />
                  <span className="text-sm truncate">{lead.company ?? "—"}</span>
                </div>
              </div>
              <div className={cn("inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs flex-shrink-0", stageCfg.bg, stageCfg.color)}>
                <span className={cn("h-1.5 w-1.5 rounded-full", stageCfg.dot)} /> {stageCfg.label}
              </div>
            </div>

            {/* Gauge */}
            <div className="flex justify-center py-2">
              <ScoreGauge score={lead.score} />
            </div>

            {lead.scoreDetail.signals.length > 0 && (
              <div className="space-y-1 border-t border-zinc-800 pt-3">
                <p className="text-[10px] text-zinc-500 font-mono uppercase tracking-widest">Signals</p>
                {lead.scoreDetail.signals.map((sig) => (
                  <div key={sig} className="flex items-center gap-2 text-xs text-zinc-300">
                    <span className="h-1 w-1 rounded-full bg-indigo-400 flex-shrink-0" /> {sig}
                  </div>
                ))}
              </div>
            )}
          </Card>

          {/* Contact info */}
          <Card className="p-4 space-y-3">
            <p className="text-[10px] font-mono text-zinc-500 uppercase tracking-widest">Lead Info</p>
            <div className="space-y-2.5">
              {lead.email && (
                <div className="flex items-center gap-2.5">
                  <Mail className="h-3.5 w-3.5 text-zinc-600 flex-shrink-0" />
                  <span className="text-xs text-zinc-300 truncate">{lead.email}</span>
                </div>
              )}
              {lead.phone && (
                <div className="flex items-center gap-2.5">
                  <Phone className="h-3.5 w-3.5 text-zinc-600 flex-shrink-0" />
                  <span className="text-xs text-zinc-300 font-mono">{lead.phone}</span>
                </div>
              )}
              {lead.title && (
                <div className="flex items-center justify-between">
                  <span className="text-xs text-zinc-500">Title</span>
                  <span className="text-xs text-zinc-200">{lead.title}</span>
                </div>
              )}
              <div className="flex items-center justify-between">
                <span className="text-xs text-zinc-500">Source</span>
                <Badge variant="zinc" size="sm" className="capitalize">{lead.source}</Badge>
              </div>
              {lead.contactId && (
                <div className="flex items-center justify-between">
                  <span className="text-xs text-zinc-500">Linked contact</span>
                  <span className="text-xs font-mono text-indigo-400 truncate max-w-[8rem]">{lead.contactId}</span>
                </div>
              )}
              {lead.lastEngagedAt && (
                <div className="flex items-center justify-between">
                  <span className="text-xs text-zinc-500">Last engaged</span>
                  <span className="text-xs font-mono text-zinc-300">{formatRelative(lead.lastEngagedAt)}</span>
                </div>
              )}
            </div>
          </Card>

          {/* Stage stepper */}
          {!isConverted && (
            <Card className="p-4 space-y-3">
              <div className="flex items-center gap-2">
                <TrendingUp className="h-4 w-4 text-indigo-400" />
                <p className="text-sm font-semibold text-zinc-200">Move to Stage</p>
                {moveSaving && <Loader2 className="h-3.5 w-3.5 text-zinc-500 animate-spin ml-auto" />}
              </div>
              <div className="grid grid-cols-2 gap-1.5">
                {otherStages.map((s) => {
                  const cfg = funnelStageConfig[s];
                  return (
                    <button
                      key={s}
                      onClick={() => handleMoveStage(s)}
                      disabled={moveSaving}
                      className={cn(
                        "flex items-center justify-between rounded-lg border border-zinc-800 px-3 py-2.5 text-xs transition-all hover:border-zinc-700 text-left",
                        cfg.bg, moveSaving && "opacity-50 cursor-not-allowed"
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
        </div>

        {/* Right: score trend + enrollments + timeline */}
        <div className="flex flex-col gap-6">

          {/* Score trend */}
          <Card className="p-4 space-y-3">
            <div className="flex items-center gap-2">
              <TrendingUp className="h-4 w-4 text-indigo-400" />
              <p className="text-sm font-semibold text-zinc-200">Engagement Score Trend</p>
              <span className="ml-auto text-[10px] font-mono text-zinc-500">Cumulative signal</span>
            </div>
            {eventsLoading ? (
              <div className="h-28 rounded-xl bg-zinc-800/50 animate-pulse" />
            ) : trend.length > 0 ? (
              <div className="h-28">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={trend} margin={{ top: 4, right: 4, bottom: 0, left: -24 }}>
                    <defs>
                      <linearGradient id="leadScoreGrad" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#6366F1" stopOpacity={0.25} />
                        <stop offset="95%" stopColor="#6366F1" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="#27272A" vertical={false} />
                    <XAxis dataKey="date" tick={{ fill: "#71717A", fontSize: 9 }} axisLine={false} tickLine={false} interval="preserveStartEnd" />
                    <YAxis domain={[0, 100]} tick={{ fill: "#71717A", fontSize: 9 }} axisLine={false} tickLine={false} width={36} />
                    <RechartTooltip
                      formatter={(v) => [`${v ?? 0}`, "Score"]}
                      contentStyle={{ background: "#18181B", border: "1px solid #27272A", borderRadius: 8, fontSize: 11 }}
                    />
                    <Area type="monotone" dataKey="score" stroke="#6366F1" strokeWidth={2} fill="url(#leadScoreGrad)" dot={false} activeDot={{ r: 4, fill: "#6366F1" }} />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <p className="text-xs text-zinc-500 text-center py-4">No engagement events yet.</p>
            )}
          </Card>

          {/* Enrollments */}
          <Card className="p-4 space-y-3">
            <div className="flex items-center gap-2">
              <Send className="h-4 w-4 text-indigo-400" />
              <p className="text-sm font-semibold text-zinc-200">Sequence Enrollments</p>
              {enrollments.length > 0 && <span className="ml-auto text-xs font-mono text-zinc-500">{enrollments.length}</span>}
            </div>
            {eventsLoading ? (
              <div className="space-y-2">{[1, 2].map((i) => <div key={i} className="h-12 rounded-xl bg-zinc-800/50 animate-pulse" />)}</div>
            ) : enrollments.length === 0 ? (
              <p className="text-xs text-zinc-500 text-center py-4">Not enrolled in any campaign yet.</p>
            ) : (
              <div className="space-y-2">
                {enrollments.map((en) => {
                  const meta = EVENT_META[en.lastType] ?? EVENT_META.queued;
                  return (
                    <div key={en.enrollmentId} className="flex items-center gap-3 rounded-xl border border-zinc-800 bg-zinc-900 px-3.5 py-3">
                      <div className="flex-1 min-w-0">
                        <p className="text-xs font-medium text-zinc-200 truncate">
                          Campaign <span className="font-mono text-zinc-400">{en.campaignId ?? "—"}</span>
                        </p>
                        <p className="text-[11px] text-zinc-500">{en.sent} sent · last {formatRelative(en.lastAt)}</p>
                      </div>
                      <Badge variant="zinc" size="sm" className={cn("capitalize", meta.color)}>{meta.label}</Badge>
                    </div>
                  );
                })}
              </div>
            )}
          </Card>

          {/* Timeline */}
          <Card className="p-4 space-y-3">
            <div className="flex items-center gap-2">
              <Zap className="h-4 w-4 text-indigo-400" />
              <p className="text-sm font-semibold text-zinc-200">Engagement Timeline</p>
              {events.length > 0 && <span className="ml-auto text-xs font-mono text-zinc-500">{events.length} events</span>}
            </div>
            {eventsLoading ? (
              <div className="space-y-2">{[1, 2, 3].map((i) => <div key={i} className="h-14 rounded-xl bg-zinc-800/50 animate-pulse" />)}</div>
            ) : events.length === 0 ? (
              <div className="flex flex-col items-center gap-2 py-6 text-center">
                <Zap className="h-6 w-6 text-zinc-700" />
                <p className="text-xs text-zinc-500">No engagement events recorded yet.</p>
              </div>
            ) : (
              <div className="relative">
                {events.map((evt, i) => {
                  const meta = EVENT_META[evt.type] ?? EVENT_META.queued;
                  const Icon = meta.icon;
                  return (
                    <div key={evt.id} className="flex gap-3">
                      <div className="flex flex-col items-center flex-shrink-0">
                        <span className="mt-1 flex h-6 w-6 items-center justify-center rounded-full border border-zinc-800 bg-zinc-900">
                          <Icon className={cn("h-3 w-3", meta.color)} />
                        </span>
                        {i < events.length - 1 && <span className="flex-1 w-px bg-zinc-800 mt-1" />}
                      </div>
                      <div className="pb-4 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className={cn("text-xs font-medium", meta.color)}>{meta.label}</span>
                          {evt.weight !== 0 && (
                            <span className={cn("text-[10px] font-mono", evt.weight > 0 ? "text-emerald-500" : "text-rose-500")}>
                              {evt.weight > 0 ? "+" : ""}{evt.weight}
                            </span>
                          )}
                          <span className="text-[10px] text-zinc-600">{formatRelative(evt.occurredAt)}</span>
                        </div>
                        {typeof evt.metadata.subject === "string" && (
                          <p className="text-xs text-zinc-400 mt-0.5 truncate">{evt.metadata.subject}</p>
                        )}
                        {typeof evt.metadata.snippet === "string" && (
                          <p className="text-xs text-zinc-500 mt-0.5 line-clamp-2 italic">&ldquo;{evt.metadata.snippet}&rdquo;</p>
                        )}
                        {typeof evt.metadata.url === "string" && (
                          <p className="text-[11px] text-indigo-400/80 mt-0.5 truncate font-mono">{evt.metadata.url}</p>
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
    </div>
  );
}
