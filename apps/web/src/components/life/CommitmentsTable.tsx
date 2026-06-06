"use client";

import { useState } from "react";
import Card from "@/components/ui/Card";
import Button from "@/components/ui/Button";
import { cn } from "@/lib/utils";
import type { Commitment, CommitmentStatus } from "@/lib/types";
import {
  CheckCircle2, XCircle, CircleDashed, MinusCircle, ChevronDown, Plus,
  Bot, PenLine, FileText, X, Gavel,
} from "lucide-react";

const FACING_JUDGMENT_DAYS = 7;

// Whole days since an ISO datetime (floored). Used to flag open commitments that
// have aged past the judgment window.
function daysSince(iso: string): number {
  return Math.floor((Date.now() - new Date(iso).getTime()) / 86400000);
}

interface StatusMeta {
  label: string;
  className: string;
  icon: React.ReactNode;
}

const STATUS_META: Record<CommitmentStatus, StatusMeta> = {
  open:    { label: "Open",    className: "bg-indigo-500/10 text-indigo-400 border-indigo-500/20",  icon: <CircleDashed className="h-3 w-3" /> },
  kept:    { label: "Kept",    className: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20", icon: <CheckCircle2 className="h-3 w-3" /> },
  broken:  { label: "Broken",  className: "bg-rose-500/10 text-rose-400 border-rose-500/20",          icon: <XCircle className="h-3 w-3" /> },
  dropped: { label: "Dropped", className: "bg-zinc-700/50 text-zinc-400 border-zinc-700",             icon: <MinusCircle className="h-3 w-3" /> },
};

function statusMeta(status: string): StatusMeta {
  return STATUS_META[status as CommitmentStatus] ?? STATUS_META.open;
}

function StatusChip({ status }: { status: string }) {
  const m = statusMeta(status);
  return (
    <span className={cn("inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-mono font-medium", m.className)}>
      {m.icon}
      {m.label}
    </span>
  );
}

function KindBadge({ kind }: { kind: string }) {
  const explicit = kind === "explicit";
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[9px] font-mono font-semibold uppercase tracking-wide border",
        explicit
          ? "bg-violet-500/10 text-violet-400 border-violet-500/25"
          : "bg-zinc-800 text-zinc-500 border-zinc-700",
      )}
      title={explicit ? "Declared explicitly in the UI" : "Auto-harvested from session logs"}
    >
      {explicit ? <PenLine className="h-2.5 w-2.5" /> : <Bot className="h-2.5 w-2.5" />}
      {explicit ? "explicit" : "auto"}
    </span>
  );
}

function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

// Keep only the tail of a long source path so the row stays compact.
function truncSource(src: string | null): string {
  if (!src) return "";
  const parts = src.split("/");
  return parts.length > 2 ? `…/${parts.slice(-2).join("/")}` : src;
}

interface CommitmentsTableProps {
  commitments: Commitment[];
  /** PATCH status=dropped (optimistic). Resolves on success, rejects to trigger revert. */
  onDrop: (id: string) => Promise<void>;
  /** PUT by-external for an explicit declaration. */
  onDeclare: (title: string, dueDate: string | null) => Promise<void>;
  /** Hide the declare form + drop actions (e.g. when unauthenticated). */
  readOnly?: boolean;
}

export default function CommitmentsTable({ commitments, onDrop, onDeclare, readOnly = false }: CommitmentsTableProps) {
  const [expanded, setExpanded] = useState<string | null>(null);
  const [dropping, setDropping] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [title, setTitle] = useState("");
  const [due, setDue] = useState("");
  const [declaring, setDeclaring] = useState(false);

  const handleDrop = async (id: string) => {
    setDropping(id);
    try {
      await onDrop(id);
    } finally {
      setDropping(null);
    }
  };

  const handleDeclare = async () => {
    if (!title.trim()) return;
    setDeclaring(true);
    try {
      await onDeclare(title.trim(), due || null);
      setTitle("");
      setDue("");
      setShowForm(false);
    } catch {
      // surfaced via the page; keep the form open so the user can retry
    } finally {
      setDeclaring(false);
    }
  };

  // Partition: open commitments aged past the window "face judgment Sunday"
  // (oldest first, amber); the rest keep their incoming order.
  const facing: Array<{ commitment: Commitment; ageDays: number }> = [];
  const rest: Commitment[] = [];
  for (const c of commitments) {
    const age = daysSince(c.declared_at);
    if (c.status === "open" && age > FACING_JUDGMENT_DAYS) {
      facing.push({ commitment: c, ageDays: age });
    } else {
      rest.push(c);
    }
  }
  facing.sort((a, b) => b.ageDays - a.ageDays); // oldest (largest age) first

  // Single source of truth for a commitment row. `ageDays` (when provided)
  // renders the amber "Nd old" badge used in the facing-judgment block.
  const renderRow = (c: Commitment, ageDays?: number) => {
    const isOpen = expanded === c.id;
    const canDrop = !readOnly && c.status === "open";
    return (
      <li key={c.id} className="group">
        <div className="flex items-start gap-3 px-4 py-3 hover:bg-zinc-800/30 transition-colors">
          {/* Expand toggle (only if there's evidence/detail to show) */}
          <button
            onClick={() => setExpanded(isOpen ? null : c.id)}
            className={cn(
              "mt-0.5 flex-shrink-0 text-zinc-600 hover:text-zinc-300 transition-transform cursor-pointer",
              isOpen && "rotate-180",
            )}
            aria-label={isOpen ? "Collapse" : "Expand"}
            aria-expanded={isOpen}
          >
            <ChevronDown className="h-3.5 w-3.5" />
          </button>

          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <p className="text-sm text-zinc-100 leading-snug">{c.title}</p>
              <KindBadge kind={c.kind} />
              {ageDays != null && (
                <span
                  className="inline-flex items-center rounded px-1.5 py-0.5 text-[9px] font-mono font-semibold uppercase tracking-wide border bg-amber-500/10 text-amber-400 border-amber-500/25"
                  title={`Declared ${ageDays} days ago and still open`}
                >
                  {ageDays}d old
                </span>
              )}
            </div>
            <div className="flex items-center gap-3 mt-1 text-[10px] text-zinc-600 font-mono flex-wrap">
              <span>declared {fmtDate(c.declared_at)}</span>
              {c.due_date && <span>· due {fmtDate(c.due_date)}</span>}
              {c.source && (
                <span className="inline-flex items-center gap-1 truncate max-w-[180px]" title={c.source}>
                  <FileText className="h-2.5 w-2.5 flex-shrink-0" />
                  {truncSource(c.source)}
                </span>
              )}
            </div>
          </div>

          <div className="flex items-center gap-2 flex-shrink-0">
            <StatusChip status={c.status} />
            {canDrop && (
              <button
                onClick={() => handleDrop(c.id)}
                disabled={dropping === c.id}
                className="text-[10px] font-mono text-zinc-600 hover:text-rose-400 transition-colors cursor-pointer disabled:opacity-50 opacity-0 group-hover:opacity-100 focus:opacity-100"
                title="Drop this commitment (no longer pursuing)"
              >
                {dropping === c.id ? "dropping…" : "drop"}
              </button>
            )}
          </div>
        </div>

        {/* Expanded evidence / detail */}
        {isOpen && (
          <div className="px-4 pb-3 pl-10 -mt-1">
            <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 px-3 py-2.5 text-xs">
              {c.evidence ? (
                <>
                  <p className="text-[10px] font-mono uppercase tracking-wide text-zinc-600 mb-1">
                    Evidence{c.scored_at ? ` · scored ${fmtDate(c.scored_at)}` : ""}
                  </p>
                  <p className="text-zinc-300 leading-relaxed">{c.evidence}</p>
                </>
              ) : (
                <p className="text-zinc-600 italic">
                  {c.status === "open" ? "Not yet scored — awaiting the next weekly retro." : "No evidence recorded."}
                </p>
              )}
              {c.source && (
                <p className="text-[10px] text-zinc-600 font-mono mt-2 break-all">source: {c.source}</p>
              )}
            </div>
          </div>
        )}
      </li>
    );
  };

  return (
    <Card className="p-0 overflow-hidden">
      {/* Header + declare toggle */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800">
        <div>
          <p className="text-sm font-semibold text-zinc-100">Commitments</p>
          <p className="text-xs text-zinc-500 mt-0.5 font-mono">Recent {commitments.length} · promises tracked &amp; scored</p>
        </div>
        {!readOnly && (
          <Button variant="cta" size="sm" onClick={() => setShowForm((v) => !v)}>
            <Plus className="h-3.5 w-3.5" />
            Declare
          </Button>
        )}
      </div>

      {/* Declare form */}
      {!readOnly && showForm && (
        <div className="px-4 py-3 border-b border-zinc-800 bg-zinc-900/40 space-y-2.5">
          <div className="flex flex-col sm:flex-row gap-2">
            <input
              type="text"
              placeholder="What are you committing to?"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              autoFocus
              onKeyDown={(e) => { if (e.key === "Enter") handleDeclare(); }}
              className="flex-1 rounded-lg border border-zinc-800 bg-zinc-900 px-3 py-2 text-base sm:text-sm text-zinc-200 placeholder-zinc-600 outline-none focus:border-indigo-500/50"
            />
            <input
              type="date"
              value={due}
              onChange={(e) => setDue(e.target.value)}
              title="Optional due date"
              className="rounded-lg border border-zinc-800 bg-zinc-900 px-3 py-2 text-sm text-zinc-300 outline-none focus:border-indigo-500/50 [color-scheme:dark]"
            />
          </div>
          <div className="flex items-center gap-2">
            <Button variant="primary" size="sm" onClick={handleDeclare} disabled={declaring || !title.trim()}>
              {declaring ? "Declaring…" : "Declare commitment"}
            </Button>
            <Button variant="ghost" size="sm" onClick={() => { setShowForm(false); setTitle(""); setDue(""); }}>
              <X className="h-3.5 w-3.5" />
              Cancel
            </Button>
            <span className="text-[10px] text-zinc-600 font-mono ml-auto hidden sm:block">
              Recorded as an explicit commitment, scored next retro.
            </span>
          </div>
        </div>
      )}

      {/* Body */}
      {commitments.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-14 text-center px-4">
          <CircleDashed className="h-7 w-7 text-zinc-700 mb-3" aria-hidden="true" />
          <p className="text-sm text-zinc-400">No commitments yet</p>
          <p className="text-xs text-zinc-600 font-mono mt-1 max-w-sm">
            The weekly retro agent harvests promises from your session logs and scores them kept or broken. Declare one above to get started.
          </p>
        </div>
      ) : (
        <>
          {/* Facing judgment — open commitments aged past the window, oldest first */}
          {facing.length > 0 && (
            <div className="border-b border-amber-500/15 bg-amber-500/[0.04]">
              <div className="flex items-center gap-2 px-4 pt-3 pb-1.5">
                <Gavel className="h-3.5 w-3.5 text-amber-400 flex-shrink-0" aria-hidden="true" />
                <p className="text-[11px] font-mono font-semibold uppercase tracking-wider text-amber-400">
                  Facing judgment Sunday
                </p>
                <span className="text-[10px] text-zinc-500 font-mono">· open &gt; {FACING_JUDGMENT_DAYS}d, unresolved</span>
              </div>
              <ul className="divide-y divide-amber-500/10">
                {facing.map(({ commitment, ageDays }) => renderRow(commitment, ageDays))}
              </ul>
            </div>
          )}

          {/* Everything else — recent open + all scored/dropped, original order */}
          {rest.length > 0 && (
            <ul className="divide-y divide-zinc-800">
              {rest.map((c) => renderRow(c))}
            </ul>
          )}
        </>
      )}
    </Card>
  );
}
