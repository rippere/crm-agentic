"use client";

import { useState, useMemo, useCallback } from "react";
import Link from "next/link";
import Header from "@/components/layout/Header";
import Card from "@/components/ui/Card";
import Button from "@/components/ui/Button";
import { cn, campaignStatusConfig } from "@/lib/utils";
import { useCampaigns } from "@/hooks/useCampaigns";
import { useSegments } from "@/hooks/useSegments";
import { useSequences } from "@/hooks/useSequences";
import {
  Send, Plus, X, Play, Pause, RotateCcw, ChevronRight, Loader2,
  Users, Workflow, Calendar, Mail, MessageSquare, Shuffle,
} from "lucide-react";
import type { Campaign, CampaignStatus, SequenceChannel } from "@/lib/types";

const STATUS_FILTERS: (CampaignStatus | "all")[] = ["all", "draft", "scheduled", "active", "paused", "completed"];

const channelIcon: Record<SequenceChannel, React.ReactNode> = {
  email: <Mail className="h-3 w-3" aria-hidden="true" />,
  sms: <MessageSquare className="h-3 w-3" aria-hidden="true" />,
  mixed: <Shuffle className="h-3 w-3" aria-hidden="true" />,
};

function StatusPill({ status }: { status: CampaignStatus }) {
  const cfg = campaignStatusConfig[status] ?? campaignStatusConfig.draft;
  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium", cfg.bg, cfg.color)}>
      <span className={cn("h-1.5 w-1.5 rounded-full", cfg.dot)} />
      {cfg.label}
    </span>
  );
}

interface NewCampaignForm {
  name: string;
  segmentId: string;
  sequenceId: string;
  channel: SequenceChannel;
  scheduledAt: string;
}

function NewCampaignModal({
  segments,
  sequences,
  onClose,
  onCreate,
}: {
  segments: { id: string; name: string; memberCount: number }[];
  sequences: { id: string; name: string; channel: SequenceChannel }[];
  onClose: () => void;
  onCreate: (f: NewCampaignForm) => Promise<void>;
}) {
  const [form, setForm] = useState<NewCampaignForm>({
    name: "",
    segmentId: segments[0]?.id ?? "",
    sequenceId: sequences[0]?.id ?? "",
    channel: "email",
    scheduledAt: "",
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.name.trim()) return;
    setSaving(true);
    setError(null);
    try {
      await onCreate(form);
      onClose();
    } catch (err) {
      setError(err instanceof Error && err.message ? err.message : "Couldn't create the campaign. Please try again.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-4" onClick={onClose}>
      <div className="w-full max-w-md rounded-2xl border border-zinc-800 bg-zinc-950 shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b border-zinc-800 px-5 py-4">
          <div className="flex items-center gap-2">
            <Send className="h-4 w-4 text-indigo-400" />
            <p className="text-sm font-semibold text-zinc-100">New Campaign</p>
          </div>
          <button onClick={onClose} className="text-zinc-400 hover:text-zinc-100 transition-colors cursor-pointer"><X className="h-4 w-4" /></button>
        </div>
        <form onSubmit={handleSubmit} className="p-5 space-y-4">
          <div>
            <label className="block text-xs font-medium text-zinc-400 mb-1.5">Campaign name *</label>
            <input
              type="text"
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              placeholder="Fall Wedding Season Blast"
              className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3.5 py-2.5 text-base sm:text-sm text-zinc-100 placeholder-zinc-600 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 transition"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-zinc-400 mb-1.5">Target segment</label>
            <select
              value={form.segmentId}
              onChange={(e) => setForm((f) => ({ ...f, segmentId: e.target.value }))}
              className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3.5 py-2.5 text-base sm:text-sm text-zinc-100 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 transition"
            >
              {segments.length === 0 && <option value="">No segments yet</option>}
              {segments.map((s) => (
                <option key={s.id} value={s.id}>{s.name} · {s.memberCount} leads</option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-xs font-medium text-zinc-400 mb-1.5">Sequence</label>
            <select
              value={form.sequenceId}
              onChange={(e) => {
                const seq = sequences.find((s) => s.id === e.target.value);
                setForm((f) => ({ ...f, sequenceId: e.target.value, channel: seq?.channel ?? f.channel }));
              }}
              className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3.5 py-2.5 text-base sm:text-sm text-zinc-100 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 transition"
            >
              {sequences.length === 0 && <option value="">No sequences yet</option>}
              {sequences.map((s) => (
                <option key={s.id} value={s.id}>{s.name}</option>
              ))}
            </select>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-zinc-400 mb-1.5">Channel</label>
              <select
                value={form.channel}
                onChange={(e) => setForm((f) => ({ ...f, channel: e.target.value as SequenceChannel }))}
                className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3.5 py-2.5 text-base sm:text-sm text-zinc-100 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 transition"
              >
                {(["email", "sms", "mixed"] as SequenceChannel[]).map((c) => (
                  <option key={c} value={c}>{c.charAt(0).toUpperCase() + c.slice(1)}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-zinc-400 mb-1.5">Schedule (optional)</label>
              <input
                type="datetime-local"
                value={form.scheduledAt}
                onChange={(e) => setForm((f) => ({ ...f, scheduledAt: e.target.value }))}
                className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3.5 py-2.5 text-base sm:text-sm text-zinc-100 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 transition [color-scheme:dark]"
              />
            </div>
          </div>

          {error && (
            <p role="alert" className="text-xs text-rose-400 bg-rose-500/10 border border-rose-500/20 rounded-lg px-3 py-2">{error}</p>
          )}

          <div className="flex gap-2 pt-1">
            <Button type="button" variant="secondary" className="flex-1 justify-center" onClick={onClose}>Cancel</Button>
            <Button type="submit" variant="primary" className="flex-1 justify-center" disabled={saving || !form.name.trim()}>
              {saving ? "Creating…" : "Create Campaign"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}

function CampaignRow({
  campaign,
  segmentName,
  sequenceName,
  onLaunch,
  onPause,
  onResume,
  busy,
}: {
  campaign: Campaign;
  segmentName: string;
  sequenceName: string;
  onLaunch: () => void;
  onPause: () => void;
  onResume: () => void;
  busy: boolean;
}) {
  const stats = campaign.stats ?? {};
  const canLaunch = campaign.status === "draft" || campaign.status === "scheduled";
  const canPause = campaign.status === "active";
  const canResume = campaign.status === "paused";

  return (
    <tr className="group border-b border-zinc-800 hover:bg-zinc-800/40 transition-colors duration-150">
      <td className="px-4 py-3">
        <Link href={`/campaigns/${campaign.id}`} className="block min-w-0">
          <p className="text-sm font-medium text-zinc-100 truncate group-hover:text-white transition-colors">{campaign.name}</p>
          <div className="flex items-center gap-1.5 mt-0.5 text-[10px] text-zinc-500 font-mono">
            {channelIcon[campaign.channel]}
            <span className="capitalize">{campaign.channel}</span>
          </div>
        </Link>
      </td>
      <td className="px-4 py-3"><StatusPill status={campaign.status} /></td>
      <td className="px-4 py-3 hidden md:table-cell">
        <div className="flex items-center gap-1.5 text-xs text-zinc-300 truncate">
          <Users className="h-3 w-3 text-zinc-600 flex-shrink-0" />
          <span className="truncate">{segmentName}</span>
        </div>
      </td>
      <td className="px-4 py-3 hidden lg:table-cell">
        <div className="flex items-center gap-1.5 text-xs text-zinc-300 truncate">
          <Workflow className="h-3 w-3 text-zinc-600 flex-shrink-0" />
          <span className="truncate">{sequenceName}</span>
        </div>
      </td>
      <td className="px-4 py-3 hidden sm:table-cell">
        <div className="flex items-center gap-3 text-[11px] font-mono text-zinc-400">
          <span title="Enrolled" className="text-zinc-300">{stats.enrolled ?? 0}<span className="text-zinc-600 ml-0.5">enr</span></span>
          <span title="Sent">{stats.sent ?? 0}<span className="text-zinc-600 ml-0.5">snt</span></span>
          <span title="Replied" className="text-indigo-400">{stats.replied ?? 0}<span className="text-zinc-600 ml-0.5">rpl</span></span>
        </div>
      </td>
      <td className="px-4 py-3 text-right">
        <div className="flex items-center justify-end gap-1.5">
          {canLaunch && (
            <button
              onClick={onLaunch}
              disabled={busy}
              className="flex items-center gap-1 rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-2.5 py-1 text-[11px] font-medium text-emerald-400 hover:bg-emerald-500/20 disabled:opacity-50 transition"
            >
              {busy ? <Loader2 className="h-3 w-3 animate-spin" /> : <Play className="h-3 w-3" />} Launch
            </button>
          )}
          {canPause && (
            <button
              onClick={onPause}
              disabled={busy}
              className="flex items-center gap-1 rounded-lg border border-orange-500/30 bg-orange-500/10 px-2.5 py-1 text-[11px] font-medium text-orange-400 hover:bg-orange-500/20 disabled:opacity-50 transition"
            >
              {busy ? <Loader2 className="h-3 w-3 animate-spin" /> : <Pause className="h-3 w-3" />} Pause
            </button>
          )}
          {canResume && (
            <button
              onClick={onResume}
              disabled={busy}
              className="flex items-center gap-1 rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-2.5 py-1 text-[11px] font-medium text-emerald-400 hover:bg-emerald-500/20 disabled:opacity-50 transition"
            >
              {busy ? <Loader2 className="h-3 w-3 animate-spin" /> : <RotateCcw className="h-3 w-3" />} Resume
            </button>
          )}
          <Link
            href={`/campaigns/${campaign.id}`}
            className="text-zinc-700 group-hover:text-zinc-400 transition-colors"
            aria-label="Open campaign detail"
          >
            <ChevronRight className="h-4 w-4" />
          </Link>
        </div>
      </td>
    </tr>
  );
}

export default function CampaignsPage() {
  const { campaigns, loading, createCampaign, scheduleCampaign, launchCampaign, pauseCampaign, resumeCampaign, refetch } = useCampaigns();
  const { segments } = useSegments();
  const { sequences } = useSequences();

  const [filterStatus, setFilterStatus] = useState<CampaignStatus | "all">("all");
  const [newOpen, setNewOpen] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);

  const segmentName = useCallback((id: string | null) => segments.find((s) => s.id === id)?.name ?? "—", [segments]);
  const sequenceName = useCallback((id: string | null) => sequences.find((s) => s.id === id)?.name ?? "—", [sequences]);

  const filtered = useMemo(
    () => (filterStatus === "all" ? campaigns : campaigns.filter((c) => c.status === filterStatus)),
    [campaigns, filterStatus],
  );

  const handleCreate = useCallback(async (f: NewCampaignForm) => {
    const created = await createCampaign({
      name: f.name,
      segment_id: f.segmentId || undefined,
      sequence_id: f.sequenceId || undefined,
      channel: f.channel,
    });
    if (f.scheduledAt && created && typeof created === "object" && "id" in created) {
      try { await scheduleCampaign(String((created as { id: string }).id), new Date(f.scheduledAt).toISOString()); } catch { /* silent */ }
    }
    await refetch();
  }, [createCampaign, scheduleCampaign, refetch]);

  const wrap = useCallback(async (id: string, fn: (id: string) => Promise<unknown>) => {
    setBusyId(id);
    try { await fn(id); } catch { /* silent */ }
    finally { setBusyId(null); }
  }, []);

  return (
    <div className="flex flex-col gap-6 p-4 md:p-6">
      <Header title="Campaigns" subtitle={`${campaigns.length} total · segment → sequence → send`} />

      {/* Status filter row */}
      <div className="grid grid-cols-3 gap-3 sm:grid-cols-6">
        {STATUS_FILTERS.map((status) => {
          const count = status === "all" ? campaigns.length : campaigns.filter((c) => c.status === status).length;
          const label = status === "all" ? "All" : (campaignStatusConfig[status]?.label ?? status);
          return (
            <button
              key={status}
              onClick={() => setFilterStatus(status)}
              className={cn(
                "rounded-xl border px-4 py-3 text-left transition-all duration-200 cursor-pointer focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 focus:ring-offset-zinc-950",
                filterStatus === status ? "border-indigo-500/40 bg-indigo-600/10" : "border-zinc-800 bg-zinc-900 hover:border-zinc-700",
              )}
            >
              <p className="text-xl font-bold font-mono text-zinc-100">{count}</p>
              <p className="text-xs text-zinc-500 mt-0.5">{label}</p>
            </button>
          );
        })}
      </div>

      {/* Toolbar */}
      <div className="flex items-center justify-between gap-3">
        <p className="text-xs text-zinc-500">
          {filtered.length} campaign{filtered.length !== 1 ? "s" : ""}{filterStatus !== "all" ? ` · ${campaignStatusConfig[filterStatus]?.label}` : ""}
        </p>
        <Button variant="cta" size="sm" onClick={() => setNewOpen(true)}>
          <Plus className="h-3.5 w-3.5" /> New Campaign
        </Button>
      </div>

      {/* Table */}
      <Card className="p-0 overflow-hidden">
        {loading ? (
          <div className="p-4 space-y-2">
            {[1, 2, 3].map((i) => <div key={i} className="h-14 rounded-xl bg-zinc-800/40 animate-pulse" />)}
          </div>
        ) : filtered.length === 0 ? (
          <div className="flex flex-col items-center gap-3 py-16 text-center">
            <Send className="h-8 w-8 text-zinc-700" />
            <p className="text-sm text-zinc-500">No campaigns yet.</p>
            <Button variant="secondary" size="sm" onClick={() => setNewOpen(true)}>
              <Plus className="h-3.5 w-3.5" /> Create your first campaign
            </Button>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px]">
              <thead>
                <tr className="border-b border-zinc-800 text-left">
                  <th className="px-4 py-2.5 text-[10px] font-mono uppercase tracking-widest text-zinc-500">Campaign</th>
                  <th className="px-4 py-2.5 text-[10px] font-mono uppercase tracking-widest text-zinc-500">Status</th>
                  <th className="px-4 py-2.5 text-[10px] font-mono uppercase tracking-widest text-zinc-500 hidden md:table-cell">Segment</th>
                  <th className="px-4 py-2.5 text-[10px] font-mono uppercase tracking-widest text-zinc-500 hidden lg:table-cell">Sequence</th>
                  <th className="px-4 py-2.5 text-[10px] font-mono uppercase tracking-widest text-zinc-500 hidden sm:table-cell">Stats</th>
                  <th className="px-4 py-2.5 text-[10px] font-mono uppercase tracking-widest text-zinc-500 text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((c) => (
                  <CampaignRow
                    key={c.id}
                    campaign={c}
                    segmentName={segmentName(c.segmentId)}
                    sequenceName={sequenceName(c.sequenceId)}
                    onLaunch={() => wrap(c.id, launchCampaign)}
                    onPause={() => wrap(c.id, pauseCampaign)}
                    onResume={() => wrap(c.id, resumeCampaign)}
                    busy={busyId === c.id}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {newOpen && (
        <NewCampaignModal
          segments={segments}
          sequences={sequences}
          onClose={() => setNewOpen(false)}
          onCreate={handleCreate}
        />
      )}
    </div>
  );
}
