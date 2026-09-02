"use client";

import { useState, useMemo, useCallback } from "react";
import Link from "next/link";
import Header from "@/components/layout/Header";
import Card from "@/components/ui/Card";
import Button from "@/components/ui/Button";
import { cn, sequenceStatusConfig } from "@/lib/utils";
import { isDemoMode } from "@/lib/demo-mode";
import { useSequences } from "@/hooks/useSequences";
import {
  Workflow, Plus, X, ChevronRight, Mail, MessageSquare, Shuffle,
  Layers,
} from "lucide-react";
import type { Sequence, SequenceStatus, SequenceChannel } from "@/lib/types";

const STATUS_FILTERS: (SequenceStatus | "all")[] = ["all", "draft", "active", "archived"];

const channelIcon: Record<SequenceChannel, React.ReactNode> = {
  email: <Mail className="h-3 w-3" aria-hidden="true" />,
  sms: <MessageSquare className="h-3 w-3" aria-hidden="true" />,
  mixed: <Shuffle className="h-3 w-3" aria-hidden="true" />,
};

function StatusPill({ status }: { status: SequenceStatus }) {
  const cfg = sequenceStatusConfig[status] ?? sequenceStatusConfig.draft;
  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium", cfg.bg, cfg.color)}>
      <span className={cn("h-1.5 w-1.5 rounded-full", cfg.dot)} />
      {cfg.label}
    </span>
  );
}

interface NewSequenceForm {
  name: string;
  description: string;
  channel: SequenceChannel;
}

function NewSequenceModal({ onClose, onCreate }: { onClose: () => void; onCreate: (f: NewSequenceForm) => Promise<string | null> }) {
  const [form, setForm] = useState<NewSequenceForm>({ name: "", description: "", channel: "email" });
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
      setError(err instanceof Error && err.message ? err.message : "Couldn't create the sequence. Please try again.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-4" onClick={onClose}>
      <div className="w-full max-w-md rounded-2xl border border-zinc-800 bg-zinc-950 shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b border-zinc-800 px-5 py-4">
          <div className="flex items-center gap-2">
            <Workflow className="h-4 w-4 text-indigo-400" />
            <p className="text-sm font-semibold text-zinc-100">New Sequence</p>
          </div>
          <button onClick={onClose} className="text-zinc-400 hover:text-zinc-100 transition-colors cursor-pointer"><X className="h-4 w-4" /></button>
        </div>
        <form onSubmit={handleSubmit} className="p-5 space-y-4">
          <div>
            <label className="block text-xs font-medium text-zinc-400 mb-1.5">Sequence name *</label>
            <input
              type="text"
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              placeholder="Wedding Venue Warm-Up (3-step)"
              className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3.5 py-2.5 text-base sm:text-sm text-zinc-100 placeholder-zinc-600 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 transition"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-zinc-400 mb-1.5">Description</label>
            <textarea
              value={form.description}
              onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
              rows={2}
              placeholder="Intro → gallery → limited-date offer."
              className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3.5 py-2.5 text-base sm:text-sm text-zinc-100 placeholder-zinc-600 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 transition resize-none"
            />
          </div>
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
          {error && (
            <p role="alert" className="text-xs text-rose-400 bg-rose-500/10 border border-rose-500/20 rounded-lg px-3 py-2">{error}</p>
          )}
          <div className="flex gap-2 pt-1">
            <Button type="button" variant="secondary" className="flex-1 justify-center" onClick={onClose}>Cancel</Button>
            <Button type="submit" variant="primary" className="flex-1 justify-center" disabled={saving || !form.name.trim()}>
              {saving ? "Creating…" : "Create Sequence"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}

function SequenceCard({ sequence }: { sequence: Sequence }) {
  return (
    <Link href={`/sequences/${sequence.id}`} className="group block">
      <Card hover className="h-full space-y-3">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <p className="text-sm font-semibold text-zinc-100 truncate group-hover:text-white transition-colors">{sequence.name}</p>
            {sequence.description && (
              <p className="text-xs text-zinc-500 mt-0.5 line-clamp-2">{sequence.description}</p>
            )}
          </div>
          <ChevronRight className="h-4 w-4 text-zinc-700 group-hover:text-zinc-400 transition-colors flex-shrink-0 mt-0.5" />
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <StatusPill status={sequence.status} />
          <span className="inline-flex items-center gap-1 rounded-full bg-zinc-800 px-2 py-0.5 text-[10px] font-mono text-zinc-400 capitalize">
            {channelIcon[sequence.channel]} {sequence.channel}
          </span>
          <span className="inline-flex items-center gap-1 rounded-full bg-zinc-800 px-2 py-0.5 text-[10px] font-mono text-zinc-400">
            <Layers className="h-3 w-3" /> {sequence.stepCount} step{sequence.stepCount !== 1 ? "s" : ""}
          </span>
        </div>
      </Card>
    </Link>
  );
}

export default function SequencesPage() {
  const { sequences, loading, createSequence, refetch } = useSequences();
  const [filterStatus, setFilterStatus] = useState<SequenceStatus | "all">("all");
  const [newOpen, setNewOpen] = useState(false);

  const filtered = useMemo(
    () => (filterStatus === "all" ? sequences : sequences.filter((s) => s.status === filterStatus)),
    [sequences, filterStatus],
  );

  const handleCreate = useCallback(async (f: NewSequenceForm): Promise<string | null> => {
    const created = await createSequence({
      name: f.name,
      description: f.description || undefined,
      channel: f.channel,
    });
    // In demo mode refetch re-seeds the static fixture list, discarding the
    // optimistic insert (the source of truth there); reconcile only in live mode.
    if (!isDemoMode) await refetch();
    if (created && typeof created === "object" && "id" in created) return String((created as { id: string }).id);
    return null;
  }, [createSequence, refetch]);

  return (
    <div className="flex flex-col gap-6 p-4 md:p-6">
      <Header title="Sequences" subtitle={`${sequences.length} total · reusable drip recipes`} />

      {/* Status filter row */}
      <div className="grid grid-cols-4 gap-3">
        {STATUS_FILTERS.map((status) => {
          const count = status === "all" ? sequences.length : sequences.filter((s) => s.status === status).length;
          const label = status === "all" ? "All" : (sequenceStatusConfig[status]?.label ?? status);
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
          {filtered.length} sequence{filtered.length !== 1 ? "s" : ""}{filterStatus !== "all" ? ` · ${sequenceStatusConfig[filterStatus]?.label}` : ""}
        </p>
        <Button variant="cta" size="sm" onClick={() => setNewOpen(true)}>
          <Plus className="h-3.5 w-3.5" /> New Sequence
        </Button>
      </div>

      {/* Grid */}
      {loading ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {[1, 2, 3].map((i) => <div key={i} className="h-28 rounded-xl bg-zinc-800/40 animate-pulse" />)}
        </div>
      ) : filtered.length === 0 ? (
        <Card className="flex flex-col items-center gap-3 py-16 text-center">
          <Workflow className="h-8 w-8 text-zinc-700" />
          <p className="text-sm text-zinc-500">No sequences yet.</p>
          <Button variant="secondary" size="sm" onClick={() => setNewOpen(true)}>
            <Plus className="h-3.5 w-3.5" /> Create your first sequence
          </Button>
        </Card>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {filtered.map((s) => <SequenceCard key={s.id} sequence={s} />)}
        </div>
      )}

      {newOpen && <NewSequenceModal onClose={() => setNewOpen(false)} onCreate={handleCreate} />}
    </div>
  );
}
