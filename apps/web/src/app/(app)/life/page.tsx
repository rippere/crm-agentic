"use client";

import { useEffect, useMemo, useState } from "react";
import Header from "@/components/layout/Header";
import Card from "@/components/ui/Card";
import Badge from "@/components/ui/Badge";
import { apiClient } from "@/lib/api-client";
import { createBrowserClient } from "@/lib/supabase";
import KpiTrendCard from "@/components/life/KpiTrendCard";
import CommitmentsTable from "@/components/life/CommitmentsTable";
import RetroCard from "@/components/life/RetroCard";
import VerdictStrip from "@/components/life/VerdictStrip";
import WeekAllocationCard from "@/components/life/WeekAllocationCard";
import type { KpiSnapshot, Commitment, CommitmentWeekStats, RetroMeta } from "@/lib/types";
import {
  ComposedChart, Bar, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Legend,
} from "recharts";
import {
  Target, GitCommitHorizontal, Brain, Package, Activity, TrendingUp,
} from "lucide-react";

const isDemoMode = process.env.NEXT_PUBLIC_DEMO_MODE === "true";

const WEEKS = 12;
// Fetch 90d once; the trend + allocation cards toggle 30/90 client-side, and the
// verdict strip windows the most recent 35d (this week + 4 prior) out of it.
const KPI_WINDOW_DAYS = 90;

function slug(s: string): string {
  return s
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 60) || "commitment";
}

function yyyymmdd(d: Date): string {
  return `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, "0")}${String(d.getDate()).padStart(2, "0")}`;
}

function isoDaysAgo(days: number): string {
  return new Date(Date.now() - days * 86400000).toISOString().slice(0, 10);
}

// The retro event's `meta` may arrive as a parsed object OR a JSON string (the
// API stores activity_events.meta as text). Parse both shapes; never throw.
function parseRetroMeta(meta: unknown): RetroMeta | null {
  let obj: unknown = meta;
  if (typeof meta === "string") {
    const trimmed = meta.trim();
    if (!trimmed) return null;
    try { obj = JSON.parse(trimmed); } catch { return null; }
  }
  if (!obj || typeof obj !== "object" || Array.isArray(obj)) return null;
  const m = obj as Record<string, unknown>;
  const judgment = Array.isArray(m.judgment)
    ? m.judgment.filter((x): x is string => typeof x === "string")
    : undefined;
  const num = (v: unknown): number | undefined => (typeof v === "number" && Number.isFinite(v) ? v : undefined);
  return {
    week: typeof m.week === "string" ? m.week : undefined,
    kept_rate: m.kept_rate === null ? null : num(m.kept_rate),
    kept: num(m.kept),
    broken: num(m.broken),
    dropped: num(m.dropped),
    harvested: num(m.harvested),
    open: num(m.open),
    judgment,
  };
}

// ─── Kept-rate weekly trend chart ─────────────────────────────────────────────
function KeptRateTooltip({
  active, payload, label,
}: {
  active?: boolean;
  payload?: Array<{ value: number | null; dataKey: string; color: string; payload: ChartWeek }>;
  label?: string;
}) {
  if (!active || !payload?.length) return null;
  const row = payload[0]?.payload;
  if (!row) return null;
  return (
    <div className="rounded-xl border border-zinc-700 bg-zinc-900 p-3 shadow-xl text-xs space-y-1">
      <p className="font-mono text-zinc-400 mb-1.5">week of {label}</p>
      <div className="flex items-center justify-between gap-4">
        <span className="text-zinc-400">Kept rate</span>
        <span className="font-mono font-bold" style={{ color: "#00C896" }}>
          {row.keptRatePct == null ? "—" : `${row.keptRatePct}%`}
        </span>
      </div>
      <div className="flex items-center gap-3 text-[11px] text-zinc-500 font-mono pt-1 border-t border-zinc-800 mt-1">
        <span className="text-emerald-400">{row.kept} kept</span>
        <span className="text-rose-400">{row.broken} broken</span>
        <span className="text-zinc-500">{row.declared} declared</span>
      </div>
    </div>
  );
}

interface ChartWeek {
  week: string;
  keptRatePct: number | null;
  declared: number;
  kept: number;
  broken: number;
  dropped: number;
  open: number;
}

function toChartWeeks(stats: CommitmentWeekStats[]): ChartWeek[] {
  return stats.map((w) => ({
    week: new Date(w.week_start).toLocaleDateString("en-US", { month: "short", day: "numeric" }),
    keptRatePct: w.kept_rate == null ? null : Math.round(w.kept_rate * 100),
    declared: w.declared,
    kept: w.kept,
    broken: w.broken,
    dropped: w.dropped,
    open: w.open,
  }));
}

export default function LifePage() {
  const [token, setToken] = useState<string | null>(null);
  const [workspaceId, setWorkspaceId] = useState<string | null>(null);
  const [authResolved, setAuthResolved] = useState(false);

  const [snapshots, setSnapshots] = useState<KpiSnapshot[]>([]);
  const [commitments, setCommitments] = useState<Commitment[]>([]);
  const [weekStats, setWeekStats] = useState<CommitmentWeekStats[]>([]);
  const [retro, setRetro] = useState<RetroMeta | null>(null);
  const [loading, setLoading] = useState(true);

  // ── Auth / workspace acquisition (mirrors dashboard + tasks pages) ──
  useEffect(() => {
    if (isDemoMode) {
      setWorkspaceId("demo-workspace-1");
      setToken("demo-token");
      setAuthResolved(true);
      return;
    }
    const supabase = createBrowserClient();
    supabase.auth.getSession().then(({ data: { session } }) => {
      if (session) {
        setToken(session.access_token);
        setWorkspaceId((session.user.app_metadata?.workspace_id ?? session.user.user_metadata?.workspace_id) ?? null);
      }
      setAuthResolved(true);
    });
  }, []);

  // ── Data fetch ──
  useEffect(() => {
    if (!authResolved) return;
    if (!isDemoMode && (!workspaceId || !token)) {
      setLoading(false);
      return;
    }
    const wid = workspaceId ?? "demo-workspace-1";
    const tok = token ?? "demo-token";
    let cancelled = false;

    Promise.all([
      apiClient.getKpi(wid, tok, { fromDate: isoDaysAgo(KPI_WINDOW_DAYS - 1) }).catch(() => [] as KpiSnapshot[]),
      apiClient.getCommitments(wid, tok).catch(() => [] as Commitment[]),
      apiClient.getCommitmentStats(wid, tok, WEEKS).catch(() => [] as CommitmentWeekStats[]),
      apiClient.getActivity(wid, tok, { eventType: "life_retro", limit: 1 }).catch(() => []),
    ]).then(([kpi, commits, stats, activity]) => {
      if (cancelled) return;
      setSnapshots(Array.isArray(kpi) ? kpi : []);
      setCommitments(Array.isArray(commits) ? commits.slice(0, 25) : []);
      setWeekStats(Array.isArray(stats) ? stats : []);
      setRetro(Array.isArray(activity) && activity.length > 0 ? parseRetroMeta(activity[0].meta) : null);
      setLoading(false);
    });

    return () => { cancelled = true; };
  }, [authResolved, workspaceId, token]);

  // ── Derived ──
  const byDomain = useMemo(() => {
    const map: Record<string, KpiSnapshot[]> = { engineering: [], knowledge: [], product: [], life: [] };
    for (const s of snapshots) {
      if (map[s.domain]) map[s.domain].push(s);
    }
    return map;
  }, [snapshots]);

  const chartWeeks = useMemo(() => toChartWeeks(weekStats), [weekStats]);

  const headline = useMemo(() => {
    // Latest week with a scored outcome -> the personal "win rate".
    const scored = weekStats.filter((w) => w.kept_rate != null);
    const latest = scored.length ? scored[scored.length - 1] : null;
    const keptRatePct = latest?.kept_rate != null ? Math.round(latest.kept_rate * 100) : null;
    const openCount = commitments.filter((c) => c.status === "open").length;
    return { keptRatePct, openCount, latestWeek: latest };
  }, [weekStats, commitments]);

  const hasAnyData = snapshots.length > 0 || commitments.length > 0 || weekStats.some((w) => w.declared > 0) || retro != null;

  // ── Write actions (optimistic) ──
  const handleDrop = async (id: string) => {
    if (!workspaceId || !token) return;
    const prev = commitments;
    setCommitments((cs) => cs.map((c) => (c.id === id ? { ...c, status: "dropped" } : c)));
    try {
      await apiClient.patchCommitment(workspaceId, id, { status: "dropped" }, token);
    } catch {
      setCommitments(prev); // revert
    }
  };

  const handleDeclare = async (title: string, dueDate: string | null) => {
    if (!workspaceId || !token) return;
    const now = new Date();
    const externalId = `explicit-${slug(title)}-${yyyymmdd(now)}`;
    // Optimistic insert at the top.
    const optimistic: Commitment = {
      id: `pending-${externalId}`,
      workspace_id: workspaceId,
      external_id: externalId,
      title,
      kind: "explicit",
      source: null,
      declared_at: now.toISOString(),
      due_date: dueDate,
      status: "open",
      evidence: null,
      scored_at: null,
    };
    setCommitments((cs) => [optimistic, ...cs].slice(0, 25));
    try {
      const res = await apiClient.upsertCommitmentByExternal(
        workspaceId,
        externalId,
        {
          title,
          kind: "explicit",
          declared_at: now.toISOString(),
          due_date: dueDate,
          status: "open",
        },
        token,
      );
      // Replace the optimistic row with the server's canonical record.
      setCommitments((cs) => cs.map((c) => (c.id === optimistic.id ? res.commitment : c)));
    } catch (err) {
      setCommitments((cs) => cs.filter((c) => c.id !== optimistic.id));
      throw err;
    }
  };

  const unauthenticated = authResolved && !isDemoMode && (!workspaceId || !token);

  // ── Loading skeleton ──
  if (loading && !unauthenticated) {
    return (
      <div className="flex flex-col gap-6 p-4 md:p-6">
        <Header title="Life" subtitle="Personal accountability ledger" />
        <div className="h-48 rounded-xl bg-zinc-800/40 animate-pulse" />
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-3 xl:grid-cols-6">
          {[1, 2, 3, 4, 5, 6].map((i) => <div key={i} className="h-20 rounded-xl bg-zinc-800/50 animate-pulse" />)}
        </div>
        <div className="h-64 rounded-xl bg-zinc-800/40 animate-pulse" />
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {[1, 2, 3, 4].map((i) => <div key={i} className="h-64 rounded-xl bg-zinc-800/40 animate-pulse" />)}
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6 p-4 md:p-6">
      <Header
        title="Life"
        subtitle={
          headline.keptRatePct != null
            ? `Personal accountability · ${headline.keptRatePct}% kept this week`
            : "Personal accountability ledger"
        }
      />

      {unauthenticated && (
        <Card className="border-amber-500/15 flex items-center gap-3">
          <Activity className="h-4 w-4 text-amber-400 flex-shrink-0" />
          <p className="text-sm text-zinc-300">
            Sign in to load your accountability ledger. The collector pushes daily KPIs and the weekly retro agent scores your commitments.
          </p>
        </Card>
      )}

      {/* ── RETRO JUDGMENT — the verdict on the week ── */}
      <section aria-labelledby="retro-heading">
        <h2 id="retro-heading" className="sr-only">Weekly retro judgment</h2>
        <RetroCard retro={retro} />
      </section>

      {/* ── VERDICT STRIP — this week vs the trailing baseline ── */}
      <section aria-labelledby="verdict-heading">
        <h2 id="verdict-heading" className="sr-only">This week, judged against baseline</h2>
        <VerdictStrip
          snapshots={snapshots}
          keptRatePct={headline.keptRatePct}
          keptRateSub={headline.latestWeek
            ? `${headline.latestWeek.kept} kept · ${headline.latestWeek.broken} broken`
            : "no scored week yet"}
          openCount={headline.openCount}
        />
      </section>

      {/* ── KEPT-RATE TREND ── */}
      <section aria-labelledby="keptrate-heading">
        <Card>
          <div className="flex items-center justify-between mb-4">
            <div>
              <p id="keptrate-heading" className="text-sm font-semibold text-zinc-100">Kept-Rate Trend</p>
              <p className="text-xs text-zinc-500 mt-0.5 font-mono">{WEEKS}-week win rate · kept ÷ (kept + broken)</p>
            </div>
            <div className="flex items-center gap-4 text-[10px] text-zinc-500">
              <span className="flex items-center gap-1.5"><span className="inline-block h-2 w-2 rounded-sm bg-[#00C896]" /> kept</span>
              <span className="flex items-center gap-1.5"><span className="inline-block h-2 w-2 rounded-sm bg-[#F43F5E]" /> broken</span>
              <span className="flex items-center gap-1.5"><span className="inline-block h-0.5 w-4 border-t-2 border-[#FBBF24]" /> kept rate</span>
            </div>
          </div>
          {chartWeeks.length === 0 || chartWeeks.every((w) => w.declared === 0) ? (
            <div className="flex h-56 flex-col items-center justify-center text-center">
              <TrendingUp className="h-7 w-7 text-zinc-700 mb-2" aria-hidden="true" />
              <p className="text-sm text-zinc-400">No retro data yet</p>
              <p className="text-xs text-zinc-600 font-mono mt-1">Kept-rate appears once the weekly retro agent scores its first commitments.</p>
            </div>
          ) : (
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={chartWeeks} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#27272A" vertical={false} />
                  <XAxis dataKey="week" tick={{ fill: "#71717A", fontSize: 10 }} axisLine={false} tickLine={false} minTickGap={12} />
                  <YAxis
                    yAxisId="count"
                    tick={{ fill: "#71717A", fontSize: 10 }}
                    axisLine={false}
                    tickLine={false}
                    width={28}
                    allowDecimals={false}
                  />
                  <YAxis
                    yAxisId="rate"
                    orientation="right"
                    domain={[0, 100]}
                    tick={{ fill: "#71717A", fontSize: 10 }}
                    axisLine={false}
                    tickLine={false}
                    width={34}
                    tickFormatter={(v) => `${v}%`}
                  />
                  <Tooltip content={<KeptRateTooltip />} cursor={{ fill: "rgba(99,102,241,0.06)" }} />
                  <Legend iconType="circle" iconSize={6} wrapperStyle={{ fontSize: "10px", color: "#71717A" }} />
                  <Bar yAxisId="count" dataKey="kept" name="Kept" stackId="o" fill="#00C896" radius={[0, 0, 0, 0]} maxBarSize={26} />
                  <Bar yAxisId="count" dataKey="broken" name="Broken" stackId="o" fill="#F43F5E" radius={[3, 3, 0, 0]} maxBarSize={26} />
                  <Line
                    yAxisId="rate"
                    type="monotone"
                    dataKey="keptRatePct"
                    name="Kept rate"
                    stroke="#FBBF24"
                    strokeWidth={2}
                    dot={{ fill: "#FBBF24", r: 3 }}
                    activeDot={{ r: 5, fill: "#FDE68A" }}
                    connectNulls={false}
                  />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          )}
          {chartWeeks.length > 0 && (
            <p className="text-[10px] text-zinc-600 font-mono mt-3">
              Weeks with no scored outcome leave a gap in the rate line (not a zero).
            </p>
          )}
        </Card>
      </section>

      {/* ── KPI TREND CARDS ── */}
      <section aria-labelledby="kpi-heading">
        <div className="flex items-center gap-2 mb-3">
          <h2 id="kpi-heading" className="text-xs font-semibold text-zinc-400 uppercase tracking-widest font-mono">
            KPI Trends
          </h2>
          <Badge variant="indigo" size="sm" dot>daily snapshots</Badge>
        </div>
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <KpiTrendCard
            title="Engineering"
            subtitle="commits + work sessions"
            icon={<GitCommitHorizontal className="h-4 w-4" />}
            snapshots={byDomain.engineering}
            accent="violet"
            lines={[
              { metric: "git_commits", label: "Commits", color: "#6366F1" },
              { metric: "sessions", label: "Sessions", color: "#A78BFA" },
            ]}
          />
          {/* Where-the-week-went sits beside Engineering — same git_commits source, judged by repo. */}
          <WeekAllocationCard snapshots={byDomain.engineering} />
          <KpiTrendCard
            title="Knowledge"
            subtitle="records distilled by vault"
            icon={<Brain className="h-4 w-4" />}
            snapshots={byDomain.knowledge}
            accent="emerald"
            stacked={[
              { metric: "records.main", label: "Main", color: "#6366F1" },
              { metric: "records.neuroscience", label: "Neuro", color: "#00C896" },
              { metric: "records.content", label: "Content", color: "#A78BFA" },
            ]}
            overlayLine={{ metric: "topics_distilled", label: "Topics distilled", color: "#FBBF24" }}
          />
          <KpiTrendCard
            title="Product"
            subtitle="CRM users + tribe corpus"
            icon={<Package className="h-4 w-4" />}
            snapshots={byDomain.product}
            accent="amber"
            lines={[
              { metric: "crm_users", label: "CRM users", color: "#00C896" },
              { metric: "tribe_corpus_videos", label: "Tribe videos", color: "#6366F1" },
            ]}
          />
          <KpiTrendCard
            title="Life"
            subtitle="personal + finance records"
            icon={<Target className="h-4 w-4" />}
            snapshots={byDomain.life}
            accent="rose"
            lines={[
              { metric: "records.personal", label: "Personal", color: "#A78BFA" },
              { metric: "records.finance", label: "Finance", color: "#FBBF24" },
            ]}
          />
        </div>
      </section>

      {/* ── COMMITMENTS ── */}
      <section aria-labelledby="commitments-heading">
        <h2 id="commitments-heading" className="sr-only">Commitments</h2>
        <CommitmentsTable
          commitments={commitments}
          onDrop={handleDrop}
          onDeclare={handleDeclare}
          readOnly={unauthenticated}
        />
      </section>

      {/* Whole-page empty hint (only when truly nothing has arrived and we're authed) */}
      {!loading && !unauthenticated && !hasAnyData && (
        <Card className="border-indigo-500/15 flex items-center gap-3">
          <Activity className="h-4 w-4 text-indigo-400 flex-shrink-0" />
          <p className="text-sm text-zinc-300">
            Nothing here yet. Once the daily collector pushes KPI snapshots and the weekly retro agent scores its first commitments, this page fills in.
          </p>
        </Card>
      )}
    </div>
  );
}
