"use client";

import { useState, useMemo, useCallback, useRef, useEffect } from "react";
import Header from "@/components/layout/Header";
import Card from "@/components/ui/Card";
import Button from "@/components/ui/Button";
import Badge from "@/components/ui/Badge";
import { useOutreach } from "@/hooks/useOutreach";
import { useCampaigns } from "@/hooks/useCampaigns";
import { useSequences } from "@/hooks/useSequences";
import { cn } from "@/lib/utils";
import {
  Inbox,
  Mail,
  MessageSquare,
  Sparkles,
  Check,
  X,
  RefreshCw,
  Loader2,
  User,
  Send,
  CheckCircle2,
} from "lucide-react";
import type { PendingOutreach } from "@/lib/types";

// Draft the bot has queued and a human must approve before it sends. The card
// is self-editing (subject + body) — mirrors the LogActivityModal/drawer
// pattern — and drives approve / regenerate / reject through the outreach hook.
function PendingDraftCard({
  draft,
  campaignName,
  stepLabel,
  channel,
  onApprove,
  onRegenerate,
  onReject,
}: {
  draft: PendingOutreach;
  campaignName: string | null;
  stepLabel: string;
  channel: "email" | "sms";
  onApprove: (enrollmentId: string, edited: { subject: string | null; body: string }) => Promise<void>;
  onRegenerate: (enrollmentId: string) => Promise<{ subject: string | null; body: string; aiGenerated: boolean }>;
  onReject: (enrollmentId: string) => Promise<void>;
}) {
  const [subject, setSubject] = useState<string>(draft.subject ?? "");
  const [body, setBody] = useState<string>(draft.body ?? "");
  const [aiGenerated, setAiGenerated] = useState<boolean>(draft.aiGenerated ?? false);
  const [busy, setBusy] = useState<null | "approve" | "regenerate" | "reject">(null);
  const [error, setError] = useState<string | null>(null);
  const [resolved, setResolved] = useState<null | "approved" | "rejected">(null);

  // The parent removes this card from the queue on refetch, so an approve/reject
  // that resolves after unmount must not setState. Track mount status.
  const mountedRef = useRef(true);
  useEffect(() => () => { mountedRef.current = false; }, []);

  const isEmail = channel === "email";
  const dirty = subject !== (draft.subject ?? "") || body !== (draft.body ?? "");

  const run = useCallback(
    async (kind: "approve" | "regenerate" | "reject", fn: () => Promise<void>) => {
      setBusy(kind);
      setError(null);
      try {
        await fn();
      } catch (err) {
        if (!mountedRef.current) return;
        setError(err instanceof Error && err.message ? err.message : "Something went wrong. Please try again.");
        setBusy(null);
      }
    },
    [],
  );

  const handleApprove = () =>
    run("approve", async () => {
      await onApprove(draft.enrollmentId, { subject: isEmail ? subject.trim() || null : null, body: body.trim() });
      if (mountedRef.current) setResolved("approved");
    });

  const handleReject = () =>
    run("reject", async () => {
      await onReject(draft.enrollmentId);
      if (mountedRef.current) setResolved("rejected");
    });

  const handleRegenerate = () =>
    run("regenerate", async () => {
      const next = await onRegenerate(draft.enrollmentId);
      if (!mountedRef.current) return;
      setSubject(next.subject ?? "");
      setBody(next.body ?? "");
      setAiGenerated(next.aiGenerated);
      setBusy(null);
    });

  // After approve/reject the row leaves the queue on refetch, but show a brief
  // resolved state in case the parent keeps it mounted momentarily.
  if (resolved) {
    return (
      <Card className={cn("border", resolved === "approved" ? "border-emerald-500/30 bg-emerald-500/5" : "border-zinc-800")}>
        <div className="flex items-center gap-3 py-2">
          {resolved === "approved" ? (
            <CheckCircle2 className="h-4 w-4 text-emerald-400 flex-shrink-0" />
          ) : (
            <X className="h-4 w-4 text-zinc-500 flex-shrink-0" />
          )}
          <p className="text-sm text-zinc-300">
            {resolved === "approved" ? "Approved — queued to send." : "Rejected — step skipped."}
            <span className="text-zinc-500"> {draft.leadName ?? draft.leadId}</span>
          </p>
        </div>
      </Card>
    );
  }

  return (
    <Card className="border border-zinc-800 space-y-4">
      {/* Attribution: which lead + campaign + step this draft belongs to */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-start gap-3 min-w-0">
          <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-xl bg-zinc-800/70 border border-zinc-700">
            <User className="h-4 w-4 text-zinc-400" />
          </div>
          <div className="min-w-0">
            <p className="text-sm font-semibold text-zinc-100 truncate">{draft.leadName ?? "Unknown lead"}</p>
            <p className="text-[11px] text-zinc-500 truncate">{draft.leadCompany ?? "—"}</p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          {campaignName && <Badge variant="indigo">{campaignName}</Badge>}
          <Badge variant="zinc">{stepLabel}</Badge>
          <Badge variant={isEmail ? "indigo" : "amber"} dot>
            {isEmail ? "Email" : "SMS"}
          </Badge>
          {aiGenerated && (
            <Badge variant="emerald">
              <Sparkles className="h-3 w-3" /> AI
            </Badge>
          )}
        </div>
      </div>

      {/* Editable subject (email only) */}
      {isEmail && (
        <div>
          <label className="block text-[11px] font-medium text-zinc-500 uppercase tracking-wider mb-1.5">Subject</label>
          <input
            type="text"
            value={subject}
            onChange={(e) => setSubject(e.target.value)}
            placeholder="Subject line…"
            className="w-full rounded-lg border border-zinc-700 bg-zinc-800/70 px-3.5 py-2.5 text-base sm:text-sm text-zinc-100 placeholder-zinc-600 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 transition"
          />
        </div>
      )}

      {/* Editable body */}
      <div>
        <label className="block text-[11px] font-medium text-zinc-500 uppercase tracking-wider mb-1.5">
          {isEmail ? "Body" : "Message"}
        </label>
        <textarea
          value={body}
          onChange={(e) => setBody(e.target.value)}
          rows={isEmail ? 8 : 4}
          placeholder="Message body…"
          className="w-full resize-y rounded-lg border border-zinc-700 bg-zinc-800/70 px-3.5 py-3 text-base sm:text-sm text-zinc-200 placeholder-zinc-600 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 transition leading-relaxed font-mono"
        />
        <div className="mt-1 flex items-center justify-between">
          <span className="text-[10px] text-zinc-600 font-mono">
            {isEmail ? <Mail className="inline h-3 w-3 mr-1" /> : <MessageSquare className="inline h-3 w-3 mr-1" />}
            {body.length} chars
          </span>
          {dirty && <span className="text-[10px] text-amber-500/80 font-mono">edited</span>}
        </div>
      </div>

      {error && (
        <p role="alert" className="text-xs text-rose-400 bg-rose-500/10 border border-rose-500/20 rounded-lg px-3 py-2">
          {error}
        </p>
      )}

      {/* Actions */}
      <div className="flex flex-wrap items-center gap-2 border-t border-zinc-800/70 pt-3">
        <Button variant="cta" size="sm" onClick={handleApprove} disabled={busy !== null || !body.trim()}>
          {busy === "approve" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />}
          Approve &amp; Send
        </Button>
        <Button variant="secondary" size="sm" onClick={handleRegenerate} disabled={busy !== null}>
          {busy === "regenerate" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
          Regenerate
        </Button>
        <button
          onClick={handleReject}
          disabled={busy !== null}
          className="ml-auto flex items-center gap-1.5 rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-1.5 text-xs font-medium text-rose-400 transition-all hover:bg-rose-500/20 disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
        >
          {busy === "reject" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <X className="h-3.5 w-3.5" />}
          Reject
        </button>
      </div>
    </Card>
  );
}

export default function OutreachPage() {
  const { pending, loading, error, draft, approve, reject } = useOutreach();
  const { campaigns } = useCampaigns();
  const { sequences } = useSequences();

  const campaignName = useCallback(
    (id: string | null) => (id ? campaigns.find((c) => c.id === id)?.name ?? null : null),
    [campaigns],
  );

  // Resolve the step this draft is waiting on → a human-readable label + channel.
  const stepInfo = useCallback(
    (p: PendingOutreach): { label: string; channel: "email" | "sms" } => {
      const seq = p.sequenceId ? sequences.find((s) => s.id === p.sequenceId) : undefined;
      const total = seq?.steps?.length ?? seq?.stepCount ?? 0;
      const step = seq?.steps?.find((s) => s.stepOrder === p.currentStep);
      const channel: "email" | "sms" = step?.channel === "sms" ? "sms" : "email";
      const label = total ? `Step ${p.currentStep + 1} of ${total}` : `Step ${p.currentStep + 1}`;
      return { label, channel };
    },
    [sequences],
  );

  const handleRegenerate = useCallback(
    async (enrollmentId: string) => {
      const res = await draft(enrollmentId);
      return { subject: res.subject, body: res.body, aiGenerated: res.ai_generated };
    },
    [draft],
  );

  const handleApprove = useCallback(
    async (enrollmentId: string, edited: { subject: string | null; body: string }) => {
      await approve(enrollmentId, edited);
    },
    [approve],
  );

  const handleReject = useCallback(
    async (enrollmentId: string) => {
      await reject(enrollmentId);
    },
    [reject],
  );

  const aiCount = useMemo(() => pending.filter((p) => p.aiGenerated).length, [pending]);
  const emailCount = useMemo(() => pending.filter((p) => stepInfo(p).channel === "email").length, [pending, stepInfo]);

  return (
    <div className="flex flex-col gap-6 p-4 md:p-6 min-h-screen">
      <Header
        title="Outreach"
        subtitle={`${pending.length} draft${pending.length !== 1 ? "s" : ""} awaiting approval · bot → human handoff`}
      />

      {/* Summary tiles */}
      <div className="grid grid-cols-3 gap-3">
        <Card className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-indigo-500/10 border border-indigo-500/20 flex-shrink-0">
            <Inbox className="h-4 w-4 text-indigo-400" />
          </div>
          <div>
            <p className="text-xs text-zinc-500">Pending</p>
            <p className="text-base font-bold font-mono text-zinc-100">{pending.length}</p>
          </div>
        </Card>
        <Card className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-zinc-700/50 border border-zinc-700 flex-shrink-0">
            <Mail className="h-4 w-4 text-zinc-400" />
          </div>
          <div>
            <p className="text-xs text-zinc-500">Email drafts</p>
            <p className="text-base font-bold font-mono text-zinc-100">{emailCount}</p>
          </div>
        </Card>
        <Card className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-emerald-500/10 border border-emerald-500/20 flex-shrink-0">
            <Sparkles className="h-4 w-4 text-emerald-400" />
          </div>
          <div>
            <p className="text-xs text-zinc-500">AI-generated</p>
            <p className="text-base font-bold font-mono text-emerald-400">{aiCount}</p>
          </div>
        </Card>
      </div>

      {error && (
        <Card className="border-rose-500/20 bg-rose-500/5">
          <p className="text-sm text-rose-400">{error}</p>
        </Card>
      )}

      {/* Queue */}
      {loading ? (
        <div className="space-y-4">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-56 rounded-2xl bg-zinc-800/30 animate-pulse" />
          ))}
        </div>
      ) : pending.length === 0 ? (
        <Card className="flex flex-col items-center justify-center gap-3 py-16 text-center">
          <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-zinc-800/70 border border-zinc-700">
            <Send className="h-5 w-5 text-zinc-500" />
          </div>
          <div>
            <p className="text-sm font-semibold text-zinc-200">Approval queue is clear</p>
            <p className="text-xs text-zinc-500 mt-1">
              When a sequence step needs a human sign-off, its draft lands here for review before it sends.
            </p>
          </div>
        </Card>
      ) : (
        <div className="space-y-4" role="region" aria-label="Outreach approval queue">
          {pending.map((p) => {
            const { label, channel } = stepInfo(p);
            return (
              <PendingDraftCard
                key={p.enrollmentId}
                draft={p}
                campaignName={campaignName(p.campaignId)}
                stepLabel={label}
                channel={channel}
                onApprove={handleApprove}
                onRegenerate={handleRegenerate}
                onReject={handleReject}
              />
            );
          })}
        </div>
      )}
    </div>
  );
}
