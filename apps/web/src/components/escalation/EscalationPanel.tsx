"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";
import { useEscalation, type StageMode, type CallOutcome, type QueueItem } from "@/hooks/useEscalation";

type EscalationApi = ReturnType<typeof useEscalation>;
import {
  ShieldCheck, Loader2, AlertCircle, AlertTriangle, Clock, Power, PhoneOutgoing, CheckCircle2,
} from "lucide-react";

// Autonomous Lead Engine — Increment 2 operator control-plane (R15).
// Three surfaces: the per-stage auto/ask/off caps + autonomy master switch, the
// escalation queue, and the post-call outcome form. Fail-closed semantics (R12)
// are surfaced in copy: with the master switch off, every stage is clamped to
// ask/off regardless of a per-stage 'auto'.

const STAGE_ORDER = ["new", "contacted", "engaged", "qualified", "converted", "lost"];
const STAGE_LABEL: Record<string, string> = {
  new: "New", contacted: "Contacted", engaged: "Engaged",
  qualified: "Qualified", converted: "Converted", lost: "Lost",
};

const MODES: { mode: StageMode; label: string; hint: string }[] = [
  { mode: "auto", label: "Auto", hint: "Send without asking" },
  { mode: "ask", label: "Ask", hint: "Park for approval" },
  { mode: "off", label: "Off", hint: "Hold — kill switch" },
];

const OUTCOMES: { value: CallOutcome; label: string }[] = [
  { value: "converted", label: "Converted / Won" },
  { value: "booked", label: "Meeting booked" },
  { value: "callback", label: "Callback / follow-up" },
  { value: "not_interested", label: "Not interested" },
  { value: "no_answer", label: "No answer" },
];

const SENTIMENT_TONE: Record<string, string> = {
  positive: "text-[#00C896] border-[#00C896]/30 bg-[#00C896]/5",
  booking: "text-[#00C896] border-[#00C896]/30 bg-[#00C896]/5",
  neutral: "text-zinc-400 border-zinc-700 bg-zinc-800/40",
  negative: "text-red-400 border-red-500/30 bg-red-500/5",
  objection: "text-amber-400 border-amber-500/30 bg-amber-500/5",
  unsubscribe: "text-red-400 border-red-500/30 bg-red-500/5",
};

function Card({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={cn("rounded-xl border border-zinc-800 bg-zinc-900/40 p-5", className)}>
      {children}
    </div>
  );
}

function StageControls({ api }: { api: EscalationApi }) {
  const { controls, autonomyEnabled, loading, error, setStageMode, toggleAutonomy } = api;
  const [busy, setBusy] = useState<string | null>(null);

  const ordered = [...controls].sort(
    (a, b) => STAGE_ORDER.indexOf(a.stage) - STAGE_ORDER.indexOf(b.stage),
  );

  const onSetMode = async (stage: string, mode: StageMode) => {
    setBusy(`${stage}:${mode}`);
    try {
      await setStageMode(stage, mode);
    } finally {
      setBusy(null);
    }
  };

  return (
    <Card>
      <div className="flex items-start justify-between gap-4 mb-4">
        <div>
          <h2 className="text-sm font-semibold text-zinc-100 flex items-center gap-2">
            <ShieldCheck className="h-4 w-4 text-indigo-400" aria-hidden="true" /> Stage controls
          </h2>
          <p className="text-xs text-zinc-500 mt-1 max-w-xl leading-relaxed">
            Per-stage cap on what the engine may do on its own. <span className="text-zinc-400">Auto</span> sends,{" "}
            <span className="text-zinc-400">Ask</span> parks each send for your approval,{" "}
            <span className="text-zinc-400">Off</span> is a kill switch. New workspaces default every stage to Ask.
          </p>
        </div>

        {/* Autonomy master switch */}
        <button
          onClick={() => toggleAutonomy(!autonomyEnabled)}
          className={cn(
            "shrink-0 flex items-center gap-2 rounded-lg border px-3 py-2 text-xs font-medium transition-colors cursor-pointer",
            autonomyEnabled
              ? "border-[#00C896]/40 bg-[#00C896]/10 text-[#00C896]"
              : "border-zinc-700 bg-zinc-800/60 text-zinc-400 hover:text-zinc-200",
          )}
          aria-pressed={autonomyEnabled}
          title="Workspace autonomy master switch"
        >
          <Power className="h-3.5 w-3.5" aria-hidden="true" />
          Autonomy {autonomyEnabled ? "ON" : "OFF"}
        </button>
      </div>

      {!autonomyEnabled && (
        <div
          className="mb-4 flex items-start gap-2 rounded-lg border border-amber-500/20 bg-amber-500/5 px-3 py-2"
          role="status"
        >
          <AlertTriangle className="h-4 w-4 shrink-0 text-amber-400 mt-0.5" aria-hidden="true" />
          <p className="text-xs text-amber-300/90 leading-relaxed">
            Autonomy is off. Every stage is clamped to <strong>Ask</strong> (or Off) regardless of the caps below — a
            per-stage <strong>Auto</strong> only takes effect once you turn the master switch on.
          </p>
        </div>
      )}

      {error && (
        <div className="mb-4 flex items-center gap-2 text-red-400 text-xs" role="alert">
          <AlertCircle className="h-4 w-4" aria-hidden="true" /> {error}
        </div>
      )}

      {loading ? (
        <div className="flex items-center gap-2 text-zinc-500 text-sm py-6">
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> Loading controls…
        </div>
      ) : (
        <div className="space-y-1.5">
          {ordered.map((c) => (
            <div
              key={c.stage}
              className="flex items-center justify-between gap-4 rounded-lg border border-zinc-800/60 bg-zinc-900/30 px-3 py-2"
            >
              <span className="text-sm font-medium text-zinc-300 w-28">{STAGE_LABEL[c.stage] ?? c.stage}</span>
              <div className="flex gap-1" role="group" aria-label={`Cap for ${c.stage}`}>
                {MODES.map(({ mode, label, hint }) => {
                  const active = c.mode === mode;
                  const clampedOut = !autonomyEnabled && mode === "auto";
                  return (
                    <button
                      key={mode}
                      onClick={() => onSetMode(c.stage, mode)}
                      disabled={busy === `${c.stage}:${mode}`}
                      title={clampedOut ? `${hint} (inactive while autonomy is off)` : hint}
                      className={cn(
                        "rounded-md px-3 py-1 text-xs font-medium transition-colors cursor-pointer border",
                        active
                          ? mode === "off"
                            ? "border-red-500/40 bg-red-500/10 text-red-300"
                            : mode === "auto"
                            ? "border-[#00C896]/40 bg-[#00C896]/10 text-[#00C896]"
                            : "border-indigo-500/40 bg-indigo-500/10 text-indigo-300"
                          : "border-zinc-800 bg-zinc-900/60 text-zinc-500 hover:text-zinc-300",
                        active && clampedOut && "opacity-70",
                      )}
                      aria-pressed={active}
                    >
                      {busy === `${c.stage}:${mode}` ? "…" : label}
                    </button>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

function SentimentBadge({ sentiment }: { sentiment: string | null }) {
  if (!sentiment) return <span className="text-xs text-zinc-600">—</span>;
  return (
    <span className={cn("rounded px-1.5 py-0.5 text-[10px] font-mono border", SENTIMENT_TONE[sentiment] ?? SENTIMENT_TONE.neutral)}>
      {sentiment}
    </span>
  );
}

function EscalationQueue({ api, onPick }: { api: EscalationApi; onPick: (item: QueueItem) => void }) {
  const { queue, loading } = api;

  return (
    <Card>
      <h2 className="text-sm font-semibold text-zinc-100 flex items-center gap-2 mb-1">
        <Clock className="h-4 w-4 text-indigo-400" aria-hidden="true" /> Escalation queue
      </h2>
      <p className="text-xs text-zinc-500 mb-4">
        Enrollments waiting on you. <span className="text-amber-400">Needs judgment</span> means the engine escalated a
        reply to a human; the rest are routine approvals.
      </p>

      {loading ? (
        <div className="flex items-center gap-2 text-zinc-500 text-sm py-6">
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> Loading queue…
        </div>
      ) : queue.length === 0 ? (
        <p className="text-sm text-zinc-600 py-6 text-center">Nothing waiting — the queue is clear.</p>
      ) : (
        <div className="space-y-2">
          {queue.map((item) => (
            <div
              key={item.enrollment_id}
              className={cn(
                "rounded-lg border px-3 py-2.5",
                item.needs_judgment
                  ? "border-amber-500/30 bg-amber-500/5"
                  : "border-zinc-800/60 bg-zinc-900/30",
              )}
            >
              <div className="flex items-center justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-sm font-medium text-zinc-200 truncate">
                    {item.lead_name ?? "Unknown"}{" "}
                    {item.lead_company && <span className="text-zinc-500 font-normal">· {item.lead_company}</span>}
                  </p>
                  <p className="text-[11px] text-zinc-500 mt-0.5 truncate">{item.reason}</p>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  {item.needs_judgment && (
                    <span className="flex items-center gap-1 text-[10px] font-mono font-semibold text-amber-400 border border-amber-500/30 rounded px-1.5 py-0.5">
                      <AlertTriangle className="h-3 w-3" aria-hidden="true" /> JUDGMENT
                    </span>
                  )}
                  <SentimentBadge sentiment={item.sentiment} />
                  <button
                    onClick={() => onPick(item)}
                    className="rounded-md border border-indigo-500/30 bg-indigo-500/10 px-2.5 py-1 text-xs font-medium text-indigo-300 hover:bg-indigo-500/20 transition-colors cursor-pointer"
                  >
                    Log outcome
                  </button>
                </div>
              </div>
              <div className="flex items-center gap-3 mt-1.5 text-[10px] font-mono text-zinc-600">
                <span>stage: {item.stage ?? "—"}</span>
                <span>mode: {item.mode ?? "—"}</span>
                <span>score: {item.score ?? 0}</span>
                <span>{item.proposed_action} → {item.final_action}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

function CallOutcomeForm({ api, picked }: { api: EscalationApi; picked: QueueItem | null }) {
  const { queue, recordOutcome } = api;
  const [leadId, setLeadId] = useState<string>("");
  const [outcome, setOutcome] = useState<CallOutcome>("callback");
  const [notes, setNotes] = useState("");
  const [saving, setSaving] = useState(false);
  const [done, setDone] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  // When a queue row is picked, preselect its lead.
  const effectiveLeadId = picked?.lead_id ?? leadId;

  const submit = async () => {
    if (!effectiveLeadId) {
      setErr("Pick a lead first.");
      return;
    }
    setSaving(true);
    setErr(null);
    setDone(null);
    try {
      await recordOutcome(effectiveLeadId, outcome, notes || undefined);
      setDone("Outcome recorded — it re-entered the graph.");
      setNotes("");
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to record outcome");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card>
      <h2 className="text-sm font-semibold text-zinc-100 flex items-center gap-2 mb-1">
        <PhoneOutgoing className="h-4 w-4 text-indigo-400" aria-hidden="true" /> Post-call outcome
      </h2>
      <p className="text-xs text-zinc-500 mb-4">
        After a call, feed the result back in — it emits the right engagement event, moves the lead, and re-scores.
      </p>

      <div className="space-y-3">
        <div>
          <label htmlFor="esc-lead" className="block text-xs font-medium text-zinc-400 mb-1">Lead</label>
          <select
            id="esc-lead"
            value={effectiveLeadId}
            onChange={(e) => setLeadId(e.target.value)}
            disabled={!!picked}
            className="w-full rounded-lg border border-zinc-800 bg-zinc-900/60 px-3 py-2 text-sm text-zinc-200 focus:outline-none focus:ring-1 focus:ring-indigo-500 disabled:opacity-70"
          >
            <option value="">Select a lead…</option>
            {picked && (
              <option value={picked.lead_id}>
                {picked.lead_name ?? picked.lead_id}{picked.lead_company ? ` · ${picked.lead_company}` : ""}
              </option>
            )}
            {!picked && queue.map((q) => (
              <option key={q.lead_id} value={q.lead_id}>
                {q.lead_name ?? q.lead_id}{q.lead_company ? ` · ${q.lead_company}` : ""}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label htmlFor="esc-outcome" className="block text-xs font-medium text-zinc-400 mb-1">Outcome</label>
          <select
            id="esc-outcome"
            value={outcome}
            onChange={(e) => setOutcome(e.target.value as CallOutcome)}
            className="w-full rounded-lg border border-zinc-800 bg-zinc-900/60 px-3 py-2 text-sm text-zinc-200 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          >
            {OUTCOMES.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
        </div>

        <div>
          <label htmlFor="esc-notes" className="block text-xs font-medium text-zinc-400 mb-1">Notes (optional)</label>
          <textarea
            id="esc-notes"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            rows={3}
            placeholder="What happened on the call…"
            className="w-full rounded-lg border border-zinc-800 bg-zinc-900/60 px-3 py-2 text-sm text-zinc-200 placeholder:text-zinc-600 focus:outline-none focus:ring-1 focus:ring-indigo-500 resize-none"
          />
        </div>

        {err && (
          <div className="flex items-center gap-2 text-red-400 text-xs" role="alert">
            <AlertCircle className="h-4 w-4" aria-hidden="true" /> {err}
          </div>
        )}
        {done && (
          <div className="flex items-center gap-2 text-[#00C896] text-xs" role="status">
            <CheckCircle2 className="h-4 w-4" aria-hidden="true" /> {done}
          </div>
        )}

        <button
          onClick={submit}
          disabled={saving}
          className="w-full flex items-center justify-center gap-2 rounded-lg bg-indigo-600 px-3 py-2 text-sm font-medium text-white hover:bg-indigo-500 transition-colors cursor-pointer disabled:opacity-60"
        >
          {saving ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : null}
          Record outcome
        </button>
      </div>
    </Card>
  );
}

export default function EscalationPanel() {
  const [picked, setPicked] = useState<QueueItem | null>(null);
  const api = useEscalation();

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <div className="lg:col-span-2">
        <StageControls api={api} />
      </div>
      <EscalationQueue api={api} onPick={setPicked} />
      <CallOutcomeForm api={api} picked={picked} />
    </div>
  );
}
