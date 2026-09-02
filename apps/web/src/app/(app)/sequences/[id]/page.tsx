"use client";

import { useState, useEffect, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import Header from "@/components/layout/Header";
import Card from "@/components/ui/Card";
import Button from "@/components/ui/Button";
import { cn, sequenceStatusConfig } from "@/lib/utils";
import { useSequences } from "@/hooks/useSequences";
import {
  ArrowLeft, Plus, Trash2, ChevronUp, ChevronDown, Mail, MessageSquare,
  Clock, ShieldCheck, Sparkles, Save, Loader2, Workflow, CheckCircle2, Eye,
} from "lucide-react";
import type { Sequence, SequenceStep, SequenceStepChannel, SequenceStatus } from "@/lib/types";

// Local editable step shape (camelCase; mapped to snake_case at save time).
interface DraftStep {
  key: string;               // stable local key for React
  channel: SequenceStepChannel;
  delayHours: number;
  subject: string;
  bodyTemplate: string;
  requiresApproval: boolean;
  aiGenerate: boolean;
}

const TOKENS = ["{{name}}", "{{company}}", "{{title}}", "{{email}}"];

let keyCounter = 0;
const nextKey = () => `step-${Date.now()}-${keyCounter++}`;

function stepToDraft(s: SequenceStep): DraftStep {
  return {
    key: s.id ?? nextKey(),
    channel: s.channel,
    delayHours: s.delayHours,
    subject: s.subject ?? "",
    bodyTemplate: s.bodyTemplate,
    requiresApproval: s.requiresApproval,
    aiGenerate: s.aiGenerate,
  };
}

function emptyStep(): DraftStep {
  return { key: nextKey(), channel: "email", delayHours: 24, subject: "", bodyTemplate: "", requiresApproval: true, aiGenerate: false };
}

function StatusPill({ status }: { status: SequenceStatus }) {
  const cfg = sequenceStatusConfig[status] ?? sequenceStatusConfig.draft;
  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium", cfg.bg, cfg.color)}>
      <span className={cn("h-1.5 w-1.5 rounded-full", cfg.dot)} />
      {cfg.label}
    </span>
  );
}

function Toggle({ on, onClick, label, activeColor }: { on: boolean; onClick: () => void; label: React.ReactNode; activeColor: string }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-[11px] font-medium transition",
        on ? activeColor : "border-zinc-700 text-zinc-400 hover:border-zinc-600 hover:text-zinc-200",
      )}
      aria-pressed={on}
    >
      {label}
    </button>
  );
}

function StepCard({
  step,
  index,
  total,
  onChange,
  onRemove,
  onMoveUp,
  onMoveDown,
}: {
  step: DraftStep;
  index: number;
  total: number;
  onChange: (patch: Partial<DraftStep>) => void;
  onRemove: () => void;
  onMoveUp: () => void;
  onMoveDown: () => void;
}) {
  const isEmail = step.channel === "email";

  const insertToken = (token: string) => {
    onChange({ bodyTemplate: `${step.bodyTemplate}${step.bodyTemplate && !step.bodyTemplate.endsWith(" ") ? " " : ""}${token}` });
  };

  return (
    <Card className="space-y-3 border-l-2 border-l-indigo-500/60">
      {/* Header row */}
      <div className="flex items-center gap-2">
        <span className="flex h-6 w-6 items-center justify-center rounded-full bg-indigo-500/15 text-[11px] font-mono font-bold text-indigo-300 flex-shrink-0">
          {index + 1}
        </span>
        <div className="flex items-center gap-1.5 rounded-lg border border-zinc-700 bg-zinc-800 p-0.5">
          {(["email", "sms"] as SequenceStepChannel[]).map((ch) => (
            <button
              key={ch}
              type="button"
              onClick={() => onChange({ channel: ch })}
              className={cn(
                "flex items-center gap-1 rounded-md px-2 py-1 text-[11px] font-medium transition capitalize",
                step.channel === ch ? "bg-indigo-600 text-white" : "text-zinc-400 hover:text-zinc-200",
              )}
            >
              {ch === "email" ? <Mail className="h-3 w-3" /> : <MessageSquare className="h-3 w-3" />} {ch}
            </button>
          ))}
        </div>
        <div className="flex-1" />
        <div className="flex items-center gap-1">
          <button type="button" onClick={onMoveUp} disabled={index === 0} className="text-zinc-600 hover:text-zinc-300 disabled:opacity-30 disabled:cursor-not-allowed p-1" aria-label="Move up">
            <ChevronUp className="h-4 w-4" />
          </button>
          <button type="button" onClick={onMoveDown} disabled={index === total - 1} className="text-zinc-600 hover:text-zinc-300 disabled:opacity-30 disabled:cursor-not-allowed p-1" aria-label="Move down">
            <ChevronDown className="h-4 w-4" />
          </button>
          <button type="button" onClick={onRemove} className="text-zinc-600 hover:text-rose-400 p-1" aria-label="Remove step">
            <Trash2 className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Delay */}
      <div className="flex items-center gap-2">
        <Clock className="h-3.5 w-3.5 text-zinc-500 flex-shrink-0" />
        <span className="text-xs text-zinc-400">
          {index === 0 ? "Send immediately on enroll, or wait" : "Wait after previous step"}
        </span>
        <input
          type="number"
          min={0}
          value={step.delayHours}
          onChange={(e) => onChange({ delayHours: Math.max(0, parseInt(e.target.value || "0", 10)) })}
          className="w-20 rounded-lg border border-zinc-700 bg-zinc-800 px-2.5 py-1.5 text-xs text-zinc-100 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 transition [color-scheme:dark]"
        />
        <span className="text-xs text-zinc-500">hours</span>
      </div>

      {/* Subject (email only) */}
      {isEmail && (
        <div>
          <label className="block text-[10px] font-mono uppercase tracking-widest text-zinc-500 mb-1">Subject</label>
          <input
            type="text"
            value={step.subject}
            onChange={(e) => onChange({ subject: e.target.value })}
            placeholder="Photo booth magic for {{company}} events?"
            className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-100 placeholder-zinc-600 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 transition"
          />
        </div>
      )}

      {/* Body template + token chips */}
      <div>
        <div className="flex items-center justify-between mb-1">
          <label className="text-[10px] font-mono uppercase tracking-widest text-zinc-500">Body template</label>
          <div className="flex items-center gap-1 flex-wrap justify-end">
            {TOKENS.map((t) => (
              <button
                key={t}
                type="button"
                onClick={() => insertToken(t)}
                className="rounded-full border border-indigo-500/30 bg-indigo-500/10 px-2 py-0.5 text-[10px] font-mono text-indigo-300 hover:bg-indigo-500/20 transition"
              >
                {t}
              </button>
            ))}
          </div>
        </div>
        <textarea
          value={step.bodyTemplate}
          onChange={(e) => onChange({ bodyTemplate: e.target.value })}
          rows={5}
          placeholder="Hi {{name}},&#10;&#10;…"
          className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-xs text-zinc-200 placeholder-zinc-600 outline-none resize-y focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition leading-relaxed font-mono"
        />
      </div>

      {/* Toggles */}
      <div className="flex items-center gap-2 flex-wrap">
        <Toggle
          on={step.requiresApproval}
          onClick={() => onChange({ requiresApproval: !step.requiresApproval })}
          activeColor="border-amber-500/40 bg-amber-500/10 text-amber-300"
          label={<><ShieldCheck className="h-3.5 w-3.5" /> Requires approval</>}
        />
        <Toggle
          on={step.aiGenerate}
          onClick={() => onChange({ aiGenerate: !step.aiGenerate })}
          activeColor="border-indigo-500/40 bg-indigo-500/10 text-indigo-300"
          label={<><Sparkles className="h-3.5 w-3.5" /> AI-generate at send</>}
        />
      </div>
    </Card>
  );
}

function PreviewBody({ template }: { template: string }) {
  const rendered = template
    .replace(/\{\{name\}\}/g, "Sarah")
    .replace(/\{\{company\}\}/g, "The Ivory Rose Venue")
    .replace(/\{\{title\}\}/g, "Events Manager")
    .replace(/\{\{email\}\}/g, "sarah@ivoryrose.com");
  return <p className="text-xs text-zinc-300 whitespace-pre-wrap leading-relaxed">{rendered || <span className="text-zinc-600 italic">Empty body</span>}</p>;
}

export default function SequenceDetailPage() {
  const params = useParams();
  const router = useRouter();
  const sequenceId = params?.id as string;

  const { getSequence, saveSteps, updateSequence, refetch } = useSequences();

  const [sequence, setSequence] = useState<Sequence | null>(null);
  const [loading, setLoading] = useState(true);
  const [steps, setSteps] = useState<DraftStep[]>([]);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [previewOpen, setPreviewOpen] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getSequence(sequenceId)
      .then((seq) => {
        if (cancelled) return;
        setSequence(seq);
        setSteps((seq?.steps ?? []).slice().sort((a, b) => a.stepOrder - b.stepOrder).map(stepToDraft));
      })
      .catch(() => { if (!cancelled) setSequence(null); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sequenceId]);

  const patchStep = useCallback((key: string, patch: Partial<DraftStep>) => {
    setSteps((prev) => prev.map((s) => (s.key === key ? { ...s, ...patch } : s)));
    setSaved(false);
  }, []);

  const addStep = useCallback(() => {
    setSteps((prev) => [...prev, emptyStep()]);
    setSaved(false);
  }, []);

  const removeStep = useCallback((key: string) => {
    setSteps((prev) => prev.filter((s) => s.key !== key));
    setSaved(false);
  }, []);

  const move = useCallback((index: number, dir: -1 | 1) => {
    setSteps((prev) => {
      const next = prev.slice();
      const target = index + dir;
      if (target < 0 || target >= next.length) return prev;
      [next[index], next[target]] = [next[target], next[index]];
      return next;
    });
    setSaved(false);
  }, []);

  const handleSave = useCallback(async () => {
    setSaving(true);
    setError(null);
    try {
      await saveSteps(sequenceId, steps.map((s, i) => ({
        step_order: i,
        channel: s.channel,
        delay_hours: s.delayHours,
        subject: s.channel === "email" ? (s.subject || null) : null,
        body_template: s.bodyTemplate,
        requires_approval: s.requiresApproval,
        ai_generate: s.aiGenerate,
      })));
      await refetch();
      setSaved(true);
      setSequence((prev) => (prev ? { ...prev, stepCount: steps.length } : prev));
      setTimeout(() => setSaved(false), 3000);
    } catch (err) {
      setError(err instanceof Error && err.message ? err.message : "Couldn't save steps. Please try again.");
    } finally {
      setSaving(false);
    }
  }, [saveSteps, sequenceId, steps, refetch]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-6 w-6 text-indigo-400 animate-spin" />
      </div>
    );
  }

  if (!sequence) {
    return (
      <div className="flex flex-col items-center justify-center h-64 gap-4">
        <Workflow className="h-8 w-8 text-zinc-600" />
        <p className="text-sm text-zinc-500">Sequence not found.</p>
        <Button variant="secondary" onClick={() => router.push("/sequences")}>
          <ArrowLeft className="h-3.5 w-3.5" /> Back to Sequences
        </Button>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6 p-4 md:p-6">
      <Header title={sequence.name} subtitle={`Step builder · ${steps.length} step${steps.length !== 1 ? "s" : ""}`} />

      {/* Actions bar */}
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="secondary" onClick={() => router.push("/sequences")} className="gap-1.5">
          <ArrowLeft className="h-3.5 w-3.5" /> Sequences
        </Button>
        <StatusPill status={sequence.status} />
        {sequence.status !== "active" && (
          <Button
            variant="secondary"
            className="gap-1.5"
            onClick={async () => { try { await updateSequence(sequenceId, { status: "active" }); setSequence((p) => (p ? { ...p, status: "active" } : p)); await refetch(); } catch { /* silent */ } }}
          >
            <CheckCircle2 className="h-3.5 w-3.5" /> Activate
          </Button>
        )}
        <div className="flex-1" />
        <Button variant="secondary" className="gap-1.5" onClick={() => setPreviewOpen((v) => !v)}>
          <Eye className="h-3.5 w-3.5" /> {previewOpen ? "Hide preview" : "Preview"}
        </Button>
        <Button variant="cta" className="gap-1.5" onClick={handleSave} disabled={saving}>
          {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : saved ? <CheckCircle2 className="h-3.5 w-3.5" /> : <Save className="h-3.5 w-3.5" />}
          {saving ? "Saving…" : saved ? "Saved" : "Save Steps"}
        </Button>
      </div>

      {error && (
        <p role="alert" className="text-xs text-rose-400 bg-rose-500/10 border border-rose-500/20 rounded-lg px-3 py-2">{error}</p>
      )}

      <div className={cn("grid gap-6", previewOpen ? "lg:grid-cols-[1fr_360px]" : "grid-cols-1")}>
        {/* Builder */}
        <div className="flex flex-col gap-3">
          {steps.length === 0 ? (
            <Card className="flex flex-col items-center gap-3 py-12 text-center">
              <Workflow className="h-8 w-8 text-zinc-700" />
              <p className="text-sm text-zinc-500">No steps yet. Add the first message node.</p>
            </Card>
          ) : (
            steps.map((step, i) => (
              <StepCard
                key={step.key}
                step={step}
                index={i}
                total={steps.length}
                onChange={(patch) => patchStep(step.key, patch)}
                onRemove={() => removeStep(step.key)}
                onMoveUp={() => move(i, -1)}
                onMoveDown={() => move(i, 1)}
              />
            ))
          )}
          <button
            type="button"
            onClick={addStep}
            className="flex items-center justify-center gap-2 rounded-xl border border-dashed border-zinc-700 px-3 py-3 text-xs text-zinc-500 hover:text-zinc-300 hover:border-zinc-600 transition-all cursor-pointer"
          >
            <Plus className="h-4 w-4" /> Add step
          </button>
        </div>

        {/* Preview panel */}
        {previewOpen && (
          <div className="flex flex-col gap-3">
            <Card className="space-y-3 sticky top-4">
              <div className="flex items-center gap-2">
                <Eye className="h-4 w-4 text-indigo-400" />
                <p className="text-sm font-semibold text-zinc-200">Preview</p>
                <span className="ml-auto text-[10px] font-mono text-zinc-500">tokens filled</span>
              </div>
              {steps.length === 0 ? (
                <p className="text-xs text-zinc-600 italic py-4 text-center">Add a step to preview.</p>
              ) : (
                <div className="space-y-3">
                  {steps.map((s, i) => (
                    <div key={s.key} className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-3 space-y-1.5">
                      <div className="flex items-center gap-2 text-[10px] font-mono text-zinc-500">
                        <span className="flex h-4 w-4 items-center justify-center rounded-full bg-indigo-500/15 text-indigo-300">{i + 1}</span>
                        {s.channel === "email" ? <Mail className="h-3 w-3" /> : <MessageSquare className="h-3 w-3" />}
                        <span className="capitalize">{s.channel}</span>
                        <span className="ml-auto">+{s.delayHours}h</span>
                      </div>
                      {s.channel === "email" && s.subject && (
                        <p className="text-xs font-medium text-zinc-100">{s.subject.replace(/\{\{company\}\}/g, "The Ivory Rose Venue").replace(/\{\{name\}\}/g, "Sarah")}</p>
                      )}
                      <PreviewBody template={s.bodyTemplate} />
                    </div>
                  ))}
                </div>
              )}
            </Card>
          </div>
        )}
      </div>
    </div>
  );
}
