"use client";

import { useState, useEffect, useMemo } from "react";
import { useParams, useRouter } from "next/navigation";
import Header from "@/components/layout/Header";
import Card from "@/components/ui/Card";
import Button from "@/components/ui/Button";
import { cn, campaignStatusConfig } from "@/lib/utils";
import { useCampaigns } from "@/hooks/useCampaigns";
import { useSegments } from "@/hooks/useSegments";
import { useSequences } from "@/hooks/useSequences";
import {
  ArrowLeft, Play, Pause, RotateCcw, Loader2, Users, Workflow,
  Send, MailOpen, MousePointerClick, MessageSquare, Trophy, UserPlus,
} from "lucide-react";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip as RechartTooltip, ResponsiveContainer, Cell,
} from "recharts";
import type { Campaign, CampaignStatus, Enrollment, EnrollmentStatus } from "@/lib/types";

// Loose shape for the stats rollup (snake_case from the API / demo stub).
type StatsResponse = {
  campaign_id?: string;
  status?: string;
  stats?: Record<string, number | undefined>;
  events_by_type?: Record<string, number>;
  total_events?: number;
};

const enrollmentStatusColor: Record<EnrollmentStatus, string> = {
  active: "text-emerald-400 bg-emerald-500/10",
  waiting: "text-amber-400 bg-amber-500/10",
  paused: "text-orange-400 bg-orange-500/10",
  completed: "text-indigo-400 bg-indigo-500/10",
  stopped: "text-zinc-400 bg-zinc-700/50",
  bounced: "text-rose-400 bg-rose-500/10",
};

const TILES: { key: string; label: string; icon: React.ReactNode; color: string }[] = [
  { key: "enrolled", label: "Enrolled", icon: <UserPlus className="h-4 w-4" />, color: "text-zinc-300" },
  { key: "sent", label: "Sent", icon: <Send className="h-4 w-4" />, color: "text-sky-400" },
  { key: "opened", label: "Opened", icon: <MailOpen className="h-4 w-4" />, color: "text-indigo-400" },
  { key: "clicked", label: "Clicked", icon: <MousePointerClick className="h-4 w-4" />, color: "text-violet-400" },
  { key: "replied", label: "Replied", icon: <MessageSquare className="h-4 w-4" />, color: "text-amber-400" },
  { key: "converted", label: "Converted", icon: <Trophy className="h-4 w-4" />, color: "text-[#00C896]" },
];

const FUNNEL_COLORS = ["#71717A", "#38BDF8", "#6366F1", "#A78BFA", "#FBBF24", "#00C896"];

function StatusPill({ status }: { status: CampaignStatus }) {
  const cfg = campaignStatusConfig[status] ?? campaignStatusConfig.draft;
  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium", cfg.bg, cfg.color)}>
      <span className={cn("h-1.5 w-1.5 rounded-full", cfg.dot)} />
      {cfg.label}
    </span>
  );
}

function fmtRelative(iso: string | null): string {
  if (!iso) return "—";
  const diff = new Date(iso).getTime() - Date.now();
  const abs = Math.abs(diff);
  const mins = Math.round(abs / 60000);
  const suffix = diff >= 0 ? "from now" : "ago";
  if (mins < 60) return `${mins}m ${suffix}`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs}h ${suffix}`;
  return `${Math.round(hrs / 24)}d ${suffix}`;
}

export default function CampaignDetailPage() {
  const params = useParams();
  const router = useRouter();
  const campaignId = params?.id as string;

  const { campaigns, loading: listLoading, launchCampaign, pauseCampaign, resumeCampaign, getStats, getEnrollments, refetch } = useCampaigns();
  const { segments } = useSegments();
  const { sequences } = useSequences();

  const [stats, setStats] = useState<StatsResponse | null>(null);
  const [enrollments, setEnrollments] = useState<Enrollment[]>([]);
  const [dataLoading, setDataLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  const campaign: Campaign | undefined = useMemo(
    () => campaigns.find((c) => c.id === campaignId),
    [campaigns, campaignId],
  );

  useEffect(() => {
    let cancelled = false;
    setDataLoading(true);
    Promise.all([getStats(campaignId), getEnrollments(campaignId)])
      .then(([s, e]) => {
        if (cancelled) return;
        setStats((s as StatsResponse) ?? null);
        setEnrollments(Array.isArray(e) ? (e as Enrollment[]) : []);
      })
      .catch(() => { if (!cancelled) { setStats(null); setEnrollments([]); } })
      .finally(() => { if (!cancelled) setDataLoading(false); });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [campaignId]);

  const statValues = stats?.stats ?? campaign?.stats ?? {};

  const funnelData = useMemo(
    () => TILES.map((t) => ({ name: t.label, value: Number(statValues[t.key] ?? 0) })),
    [statValues],
  );

  const handleAction = async (fn: (id: string) => Promise<unknown>) => {
    setBusy(true);
    try {
      await fn(campaignId);
      await refetch();
      const s = await getStats(campaignId);
      setStats((s as StatsResponse) ?? null);
    } catch { /* silent */ }
    finally { setBusy(false); }
  };

  if (listLoading && !campaign) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-6 w-6 text-indigo-400 animate-spin" />
      </div>
    );
  }

  if (!campaign) {
    return (
      <div className="flex flex-col items-center justify-center h-64 gap-4">
        <Send className="h-8 w-8 text-zinc-600" />
        <p className="text-sm text-zinc-500">Campaign not found.</p>
        <Button variant="secondary" onClick={() => router.push("/campaigns")}>
          <ArrowLeft className="h-3.5 w-3.5" /> Back to Campaigns
        </Button>
      </div>
    );
  }

  const segmentName = segments.find((s) => s.id === campaign.segmentId)?.name ?? "—";
  const sequenceName = sequences.find((s) => s.id === campaign.sequenceId)?.name ?? "—";
  const canLaunch = campaign.status === "draft" || campaign.status === "scheduled";
  const canPause = campaign.status === "active";
  const canResume = campaign.status === "paused";

  return (
    <div className="flex flex-col gap-6 p-4 md:p-6">
      <Header title={campaign.name} subtitle={`Campaign · ${campaignStatusConfig[campaign.status]?.label ?? campaign.status}`} />

      {/* Actions bar */}
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="secondary" onClick={() => router.push("/campaigns")} className="gap-1.5">
          <ArrowLeft className="h-3.5 w-3.5" /> Campaigns
        </Button>
        <div className="flex-1" />
        <StatusPill status={campaign.status} />
        {canLaunch && (
          <Button variant="cta" onClick={() => handleAction(launchCampaign)} disabled={busy} className="gap-1.5">
            {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />} Launch
          </Button>
        )}
        {canPause && (
          <Button variant="secondary" onClick={() => handleAction(pauseCampaign)} disabled={busy} className="gap-1.5 text-orange-400 border-orange-500/30 hover:border-orange-500/50">
            {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Pause className="h-3.5 w-3.5" />} Pause
          </Button>
        )}
        {canResume && (
          <Button variant="cta" onClick={() => handleAction(resumeCampaign)} disabled={busy} className="gap-1.5">
            {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RotateCcw className="h-3.5 w-3.5" />} Resume
          </Button>
        )}
      </div>

      {/* Binding info */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <Card className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-indigo-500/10 border border-indigo-500/20 flex-shrink-0">
            <Users className="h-4 w-4 text-indigo-400" />
          </div>
          <div className="min-w-0">
            <p className="text-xs text-zinc-500">Segment</p>
            <p className="text-sm font-medium text-zinc-100 truncate">{segmentName}</p>
          </div>
        </Card>
        <Card className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-violet-500/10 border border-violet-500/20 flex-shrink-0">
            <Workflow className="h-4 w-4 text-violet-400" />
          </div>
          <div className="min-w-0">
            <p className="text-xs text-zinc-500">Sequence</p>
            <p className="text-sm font-medium text-zinc-100 truncate">{sequenceName}</p>
          </div>
        </Card>
        <Card className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-amber-500/10 border border-amber-500/20 flex-shrink-0">
            <Send className="h-4 w-4 text-amber-400" />
          </div>
          <div className="min-w-0">
            <p className="text-xs text-zinc-500">Scheduled</p>
            <p className="text-sm font-medium text-zinc-100 truncate">{fmtRelative(campaign.scheduledAt)}</p>
          </div>
        </Card>
      </div>

      {/* Stat tiles */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        {TILES.map((t) => (
          <Card key={t.key} className="text-center">
            <div className={cn("flex items-center justify-center gap-1.5 mb-1", t.color)}>{t.icon}</div>
            <p className="text-2xl font-bold font-mono text-zinc-100">{Number(statValues[t.key] ?? 0)}</p>
            <p className="text-xs text-zinc-500 mt-0.5">{t.label}</p>
          </Card>
        ))}
      </div>

      {/* Conversion funnel chart */}
      <Card className="p-4 space-y-3">
        <div className="flex items-center gap-2">
          <MousePointerClick className="h-4 w-4 text-indigo-400" />
          <p className="text-sm font-semibold text-zinc-200">Conversion Funnel</p>
          <span className="ml-auto text-[10px] font-mono text-zinc-500">enrolled → converted</span>
        </div>
        <div className="h-56">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={funnelData} margin={{ top: 8, right: 8, bottom: 0, left: -20 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#27272A" vertical={false} />
              <XAxis dataKey="name" tick={{ fill: "#71717A", fontSize: 10 }} axisLine={false} tickLine={false} />
              <YAxis allowDecimals={false} tick={{ fill: "#71717A", fontSize: 10 }} axisLine={false} tickLine={false} width={36} />
              <RechartTooltip
                cursor={{ fill: "#ffffff08" }}
                contentStyle={{ background: "#18181B", border: "1px solid #27272A", borderRadius: 8, fontSize: 11 }}
              />
              <Bar dataKey="value" radius={[4, 4, 0, 0]}>
                {funnelData.map((_, i) => <Cell key={i} fill={FUNNEL_COLORS[i]} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Card>

      {/* Enrollment table */}
      <Card className="p-0 overflow-hidden">
        <div className="flex items-center gap-2 px-4 py-3 border-b border-zinc-800">
          <UserPlus className="h-4 w-4 text-indigo-400" />
          <p className="text-sm font-semibold text-zinc-200">Enrollments</p>
          {enrollments.length > 0 && <span className="ml-auto text-xs font-mono text-zinc-500">{enrollments.length}</span>}
        </div>
        {dataLoading ? (
          <div className="p-4 space-y-2">
            {[1, 2, 3].map((i) => <div key={i} className="h-11 rounded-xl bg-zinc-800/40 animate-pulse" />)}
          </div>
        ) : enrollments.length === 0 ? (
          <div className="flex flex-col items-center gap-2 py-12 text-center">
            <UserPlus className="h-7 w-7 text-zinc-700" />
            <p className="text-xs text-zinc-500">No leads enrolled yet. Launch the campaign to enroll the segment.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[560px]">
              <thead>
                <tr className="border-b border-zinc-800 text-left">
                  <th className="px-4 py-2.5 text-[10px] font-mono uppercase tracking-widest text-zinc-500">Lead</th>
                  <th className="px-4 py-2.5 text-[10px] font-mono uppercase tracking-widest text-zinc-500">Status</th>
                  <th className="px-4 py-2.5 text-[10px] font-mono uppercase tracking-widest text-zinc-500">Step</th>
                  <th className="px-4 py-2.5 text-[10px] font-mono uppercase tracking-widest text-zinc-500 hidden sm:table-cell">Next run</th>
                  <th className="px-4 py-2.5 text-[10px] font-mono uppercase tracking-widest text-zinc-500 hidden md:table-cell text-right">Last sent</th>
                </tr>
              </thead>
              <tbody>
                {enrollments.map((e) => (
                  <tr key={e.id} className="border-b border-zinc-800 hover:bg-zinc-800/40 transition-colors">
                    <td className="px-4 py-3">
                      <span className="text-xs font-mono text-zinc-300">{e.leadId}</span>
                    </td>
                    <td className="px-4 py-3">
                      <span className={cn("inline-flex rounded-full px-2 py-0.5 text-[11px] font-medium capitalize", enrollmentStatusColor[e.status] ?? "text-zinc-400 bg-zinc-700/50")}>
                        {e.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-xs font-mono text-zinc-300">#{e.currentStep}</td>
                    <td className="px-4 py-3 text-xs text-zinc-400 hidden sm:table-cell">{fmtRelative(e.nextRunAt)}</td>
                    <td className="px-4 py-3 text-xs text-zinc-500 hidden md:table-cell text-right">{fmtRelative(e.lastSentAt)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
