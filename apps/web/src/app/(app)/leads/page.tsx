"use client";

import { useState, useMemo, useCallback, useRef, useEffect } from "react";
import Link from "next/link";
import Header from "@/components/layout/Header";
import Card from "@/components/ui/Card";
import Badge from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import {
  cn,
  funnelStageConfig,
  funnelStageOrder,
  engagementScoreConfig,
  engagementLabelFromScore,
} from "@/lib/utils";
import { useLeads } from "@/hooks/useLeads";
import { useJobPoller } from "@/hooks/useJobPoller";
import { isDemoMode } from "@/lib/demo-mode";
import {
  Search, X, Loader2, Plus, Upload, Filter, LayoutGrid, Table as TableIcon,
  CheckSquare, Square, ChevronRight, ExternalLink, Trash2,
  UserPlus, CheckCircle2, AlertCircle, Zap, Building2, Mail,
} from "lucide-react";
import type { Lead, LeadStage, LeadSource } from "@/lib/types";

// ─── Small helpers ───────────────────────────────────────────────────────────

const LEAD_SOURCES: LeadSource[] = ["import", "manual", "web", "api", "referral", "event"];

function ScoreBar({ score }: { score: number }) {
  const cfg = engagementScoreConfig[engagementLabelFromScore(score)];
  return (
    <div className="flex items-center gap-2 min-w-0">
      <div className="flex-1 h-1.5 rounded-full bg-zinc-800 overflow-hidden">
        <div
          className={cn("h-full rounded-full transition-all", cfg.dot)}
          style={{ width: `${score}%` }}
          role="progressbar"
          aria-valuenow={score}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label={`Engagement score: ${score}`}
        />
      </div>
      <span className={cn("text-xs font-mono font-medium w-8 flex-shrink-0", cfg.text)}>{score}</span>
    </div>
  );
}

function StagePill({ stage }: { stage: LeadStage }) {
  const cfg = funnelStageConfig[stage];
  return (
    <div className={cn("inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs", cfg.bg, cfg.color)}>
      <span className={cn("h-1.5 w-1.5 rounded-full", cfg.dot)} />
      {cfg.label}
    </div>
  );
}

// ─── Table row ───────────────────────────────────────────────────────────────

function LeadRow({
  lead, onClick, selected, onSelect,
}: {
  lead: Lead;
  onClick: () => void;
  selected: boolean;
  onSelect: (id: string, checked: boolean) => void;
}) {
  return (
    <tr
      className={cn(
        "group border-b border-zinc-800 hover:bg-zinc-800/40 transition-colors duration-150 cursor-pointer",
        selected && "bg-indigo-600/5"
      )}
      onClick={onClick}
      tabIndex={0}
      onKeyDown={(e) => e.key === "Enter" && onClick()}
      role="row"
    >
      <td className="pl-4 py-3 w-8" onClick={(e) => e.stopPropagation()}>
        <button
          onClick={() => onSelect(lead.id, !selected)}
          className="text-zinc-500 hover:text-indigo-400 transition-colors"
          aria-label={selected ? "Deselect lead" : "Select lead"}
        >
          {selected ? <CheckSquare className="h-4 w-4 text-indigo-400" /> : <Square className="h-4 w-4" />}
        </button>
      </td>
      <td className="px-4 py-3">
        <p className="text-sm font-medium text-zinc-100 truncate">{lead.name ?? "—"}</p>
        <p className="text-xs text-zinc-500 truncate">{lead.email ?? "no email"}</p>
      </td>
      <td className="px-4 py-3 hidden md:table-cell">
        <p className="text-sm text-zinc-300 truncate">{lead.company ?? "—"}</p>
        <p className="text-xs text-zinc-500 truncate">{lead.title ?? ""}</p>
      </td>
      <td className="px-4 py-3 hidden sm:table-cell">
        <StagePill stage={lead.stage} />
      </td>
      <td className="px-4 py-3 hidden lg:table-cell min-w-[140px]">
        <ScoreBar score={lead.score} />
      </td>
      <td className="px-4 py-3 hidden xl:table-cell">
        <Badge variant="zinc" size="sm" className="capitalize text-[10px]">{lead.source}</Badge>
      </td>
      <td className="px-4 py-3 text-right">
        <ChevronRight className="h-4 w-4 text-zinc-700 group-hover:text-zinc-400 transition-colors ml-auto" aria-hidden="true" />
      </td>
    </tr>
  );
}

// ─── Funnel board ────────────────────────────────────────────────────────────

function LeadCard({ lead, onSelect }: { lead: Lead; onSelect: () => void }) {
  const cfg = funnelStageConfig[lead.stage];
  const scoreCfg = engagementScoreConfig[engagementLabelFromScore(lead.score)];
  return (
    <div
      className="group w-full text-left rounded-xl border border-zinc-800/70 bg-zinc-900/70 p-3.5 transition-all duration-200 cursor-pointer space-y-2.5 border-l-2 hover:border-zinc-700/80 hover:bg-zinc-900"
      onClick={onSelect}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") onSelect(); }}
      aria-label={`${lead.name ?? "Lead"} — ${cfg.label}`}
    >
      <div className="flex items-start justify-between gap-2">
        <p className="text-sm font-semibold text-zinc-100 leading-snug truncate">{lead.name ?? "—"}</p>
        <span className={cn("text-xs font-mono font-bold flex-shrink-0", scoreCfg.text)}>{lead.score}</span>
      </div>
      <div>
        <p className="text-xs text-zinc-400 truncate flex items-center gap-1">
          <Building2 className="h-3 w-3 text-zinc-600 flex-shrink-0" /> {lead.company ?? "—"}
        </p>
        <p className="text-[10px] text-zinc-600 truncate">{lead.email ?? ""}</p>
      </div>
      <ScoreBar score={lead.score} />
      <div className="flex items-center justify-between pt-1 border-t border-zinc-800">
        <Badge variant="zinc" size="sm" className="capitalize text-[10px]">{lead.source}</Badge>
        <Link
          href={`/leads/${lead.id}`}
          onClick={(e) => e.stopPropagation()}
          className="opacity-0 group-hover:opacity-100 transition-opacity text-zinc-600 hover:text-zinc-400"
          aria-label="Open lead detail"
        >
          <ExternalLink className="h-3 w-3" />
        </Link>
      </div>
    </div>
  );
}

function FunnelColumn({ stage, leads, onSelect }: { stage: LeadStage; leads: Lead[]; onSelect: (l: Lead) => void }) {
  const cfg = funnelStageConfig[stage];
  const totalScore = leads.reduce((s, l) => s + l.score, 0);
  return (
    <div className="flex flex-col min-w-[240px] w-[240px] flex-shrink-0">
      <div className={cn("flex items-center justify-between rounded-xl border border-zinc-800 px-3 py-2.5 mb-3", cfg.bg)}>
        <div className="flex items-center gap-2">
          <span className={cn("h-1.5 w-1.5 rounded-full", cfg.dot)} />
          <span className={cn("text-xs font-semibold", cfg.color)}>{cfg.label}</span>
          <span className="flex h-5 w-5 items-center justify-center rounded-full bg-zinc-800 text-[10px] font-mono text-zinc-400">{leads.length}</span>
        </div>
        {totalScore > 0 && <span className="text-[10px] font-mono text-zinc-500">{totalScore} pts</span>}
      </div>
      <div className="flex flex-col gap-2.5 min-h-[120px]">
        {leads.map((lead) => <LeadCard key={lead.id} lead={lead} onSelect={() => onSelect(lead)} />)}
        {leads.length === 0 && (
          <div className="flex h-20 items-center justify-center rounded-xl border border-dashed border-zinc-800 text-xs text-zinc-600">No leads</div>
        )}
      </div>
    </div>
  );
}

// ─── Detail drawer ───────────────────────────────────────────────────────────

function LeadDetailPanel({
  lead, onClose, onStageChange, onPromote, promoting,
}: {
  lead: Lead;
  onClose: () => void;
  onStageChange: (stage: LeadStage) => Promise<void>;
  onPromote: () => Promise<void>;
  promoting: boolean;
}) {
  const [saving, setSaving] = useState(false);
  const scoreCfg = engagementScoreConfig[engagementLabelFromScore(lead.score)];
  const stages = funnelStageOrder.filter((s) => s !== lead.stage);

  const move = async (stage: LeadStage) => {
    setSaving(true);
    await onStageChange(stage);
    setSaving(false);
  };

  return (
    <aside className="fixed right-0 top-0 h-full w-full max-w-96 border-l border-zinc-800 bg-zinc-950 z-40 overflow-y-auto" aria-label={`Lead details for ${lead.name ?? "lead"}`}>
      <div className="sticky top-0 flex items-center justify-between border-b border-zinc-800 bg-zinc-950/90 backdrop-blur px-5 py-4">
        <div className="min-w-0">
          <p className="text-sm font-semibold text-zinc-100 truncate">{lead.name ?? "Unnamed lead"}</p>
          <p className="text-[10px] text-zinc-500 font-mono truncate">{lead.company ?? "—"}</p>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          <Link href={`/leads/${lead.id}`} className="text-zinc-500 hover:text-indigo-400 transition-colors" aria-label="Open full lead page">
            <ExternalLink className="h-4 w-4" />
          </Link>
          <button onClick={onClose} className="text-zinc-400 hover:text-zinc-100 cursor-pointer transition-colors" aria-label="Close">
            <X className="h-4 w-4" />
          </button>
        </div>
      </div>

      <div className="p-5 space-y-5">
        {/* Score */}
        <Card className="space-y-3">
          <div className="flex items-center gap-2">
            <Zap className="h-4 w-4 text-indigo-400" aria-hidden="true" />
            <p className="text-xs font-semibold text-zinc-300">Engagement Score</p>
          </div>
          <div className="flex items-center justify-between">
            <span className={cn("text-2xl font-bold font-mono", scoreCfg.text)}>{lead.score}</span>
            <div className={cn("flex items-center gap-1 rounded-full px-2 py-0.5 text-xs", scoreCfg.bg, scoreCfg.text)}>
              <span className={cn("h-1.5 w-1.5 rounded-full", scoreCfg.dot)} />
              {scoreCfg.label}
            </div>
          </div>
          {lead.scoreDetail.signals.length > 0 && (
            <div className="space-y-1">
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
        <div className="space-y-2">
          {lead.email && (
            <div className="flex items-center gap-2 text-xs">
              <Mail className="h-3.5 w-3.5 text-zinc-600 flex-shrink-0" />
              <span className="text-zinc-300 truncate">{lead.email}</span>
            </div>
          )}
          {lead.phone && (
            <div className="flex items-center justify-between text-xs">
              <span className="text-zinc-500">Phone</span>
              <span className="text-zinc-200 font-mono">{lead.phone}</span>
            </div>
          )}
          {lead.title && (
            <div className="flex items-center justify-between text-xs">
              <span className="text-zinc-500">Title</span>
              <span className="text-zinc-200">{lead.title}</span>
            </div>
          )}
          <div className="flex items-center justify-between text-xs">
            <span className="text-zinc-500">Source</span>
            <Badge variant="zinc" size="sm" className="capitalize">{lead.source}</Badge>
          </div>
        </div>

        {/* Promote */}
        {lead.stage !== "converted" && (
          <Button variant="primary" className="w-full justify-center" onClick={onPromote} disabled={promoting}>
            {promoting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <UserPlus className="h-3.5 w-3.5" />}
            {lead.contactId ? "Re-sync Contact" : "Promote to Contact"}
          </Button>
        )}

        {/* Stage stepper */}
        <div>
          <p className="text-[11px] text-zinc-500 uppercase tracking-widest font-mono mb-2">Move to stage</p>
          <div className="flex flex-col gap-1.5">
            {stages.map((s) => {
              const cfg = funnelStageConfig[s];
              return (
                <button
                  key={s}
                  onClick={() => move(s)}
                  disabled={saving}
                  className={cn(
                    "flex items-center justify-between rounded-lg border border-zinc-800 px-3 py-2.5 text-xs transition-all hover:border-zinc-700",
                    cfg.bg, saving && "opacity-50 cursor-not-allowed"
                  )}
                >
                  <span className={cn("font-medium", cfg.color)}>{cfg.label}</span>
                  <ChevronRight className="h-3 w-3 text-zinc-600" />
                </button>
              );
            })}
          </div>
        </div>
      </div>
    </aside>
  );
}

// ─── Bulk action bar ─────────────────────────────────────────────────────────

function BulkActionBar({
  count, onSetStage, onDelete, onClear, busy,
}: {
  count: number;
  onSetStage: (stage: LeadStage) => void;
  onDelete: () => void;
  onClear: () => void;
  busy: boolean;
}) {
  const [stageMenuOpen, setStageMenuOpen] = useState(false);
  return (
    <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 flex flex-col sm:flex-row items-center gap-3 rounded-2xl border border-indigo-500/30 bg-zinc-900/95 backdrop-blur px-5 py-3 shadow-2xl w-[calc(100vw-2rem)] sm:w-auto">
      <span className="text-sm font-medium text-indigo-300 whitespace-nowrap">{count} selected</span>
      <div className="hidden sm:block w-px h-4 bg-zinc-700 flex-shrink-0" />
      <div className="relative">
        <button
          onClick={() => setStageMenuOpen((v) => !v)}
          disabled={busy}
          className="flex items-center gap-1.5 rounded-lg border border-zinc-700 px-3 py-1.5 text-xs font-medium text-zinc-300 hover:border-zinc-600 hover:text-zinc-100 disabled:opacity-50 transition"
        >
          <Filter className="h-3.5 w-3.5" /> Set Stage
        </button>
        {stageMenuOpen && (
          <div className="absolute bottom-full mb-2 left-0 rounded-xl border border-zinc-800 bg-zinc-950 shadow-xl overflow-hidden min-w-36">
            {funnelStageOrder.map((s) => (
              <button
                key={s}
                onClick={() => { onSetStage(s); setStageMenuOpen(false); }}
                className={cn("w-full px-4 py-2 text-left text-xs hover:bg-zinc-800 transition", funnelStageConfig[s].color)}
              >
                {funnelStageConfig[s].label}
              </button>
            ))}
          </div>
        )}
      </div>
      <button
        onClick={onDelete}
        disabled={busy}
        className="flex items-center gap-1.5 rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-1.5 text-xs font-medium text-rose-400 hover:bg-rose-500/20 disabled:opacity-50 transition"
      >
        {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Trash2 className="h-3.5 w-3.5" />} Delete
      </button>
      <div className="w-px h-4 bg-zinc-700 flex-shrink-0" />
      <button onClick={onClear} className="text-zinc-500 hover:text-zinc-300 transition"><X className="h-4 w-4" /></button>
    </div>
  );
}

// ─── New lead modal ──────────────────────────────────────────────────────────

interface NewLeadForm { name: string; email: string; company: string; title: string; phone: string; source: LeadSource; }

function NewLeadModal({ onClose, onCreate }: { onClose: () => void; onCreate: (f: NewLeadForm) => Promise<void> }) {
  const [form, setForm] = useState<NewLeadForm>({ name: "", email: "", company: "", title: "", phone: "", source: "manual" });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.name.trim() && !form.email.trim()) return;
    setSaving(true);
    setError(null);
    try {
      await onCreate(form);
      onClose();
    } catch (err) {
      setError(err instanceof Error && err.message ? err.message : "Couldn't create the lead.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-4" onClick={onClose}>
      <div className="w-full max-w-md rounded-2xl border border-zinc-800 bg-zinc-950 shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b border-zinc-800 px-5 py-4">
          <p className="text-sm font-semibold text-zinc-100">New Lead</p>
          <button onClick={onClose} className="text-zinc-400 hover:text-zinc-100 transition-colors cursor-pointer"><X className="h-4 w-4" /></button>
        </div>
        <form onSubmit={submit} className="p-5 space-y-4">
          {([
            { label: "Name", key: "name", placeholder: "Jordan Rivera" },
            { label: "Email", key: "email", placeholder: "jordan@venue.com" },
            { label: "Company", key: "company", placeholder: "Ivory Rose Venue" },
            { label: "Title", key: "title", placeholder: "Events Manager" },
            { label: "Phone", key: "phone", placeholder: "+1 (555) 200-1000" },
          ] as const).map(({ label, key, placeholder }) => (
            <div key={key}>
              <label className="block text-xs font-medium text-zinc-400 mb-1.5">{label}</label>
              <input
                type={key === "email" ? "email" : "text"}
                value={form[key]}
                onChange={(e) => setForm((f) => ({ ...f, [key]: e.target.value }))}
                placeholder={placeholder}
                className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3.5 py-2.5 text-base sm:text-sm text-zinc-100 placeholder-zinc-600 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 transition"
              />
            </div>
          ))}
          <div>
            <label className="block text-xs font-medium text-zinc-400 mb-1.5">Source</label>
            <select
              value={form.source}
              onChange={(e) => setForm((f) => ({ ...f, source: e.target.value as LeadSource }))}
              className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3.5 py-2.5 text-base sm:text-sm text-zinc-100 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 transition capitalize"
            >
              {LEAD_SOURCES.map((s) => <option key={s} value={s}>{s.charAt(0).toUpperCase() + s.slice(1)}</option>)}
            </select>
          </div>
          {error && <p role="alert" className="text-xs text-rose-400 bg-rose-500/10 border border-rose-500/20 rounded-lg px-3 py-2">{error}</p>}
          <div className="flex gap-2 pt-1">
            <Button type="button" variant="secondary" className="flex-1 justify-center" onClick={onClose}>Cancel</Button>
            <Button type="submit" variant="primary" className="flex-1 justify-center" disabled={saving || (!form.name.trim() && !form.email.trim())}>
              {saving ? "Creating…" : "Create Lead"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ─── CSV import modal ────────────────────────────────────────────────────────

const LEAD_FIELDS = ["name", "email", "company", "title", "phone", "external_id"] as const;
type LeadField = (typeof LEAD_FIELDS)[number];

// Minimal CSV parser — handles quoted fields and commas within quotes.
function parseCsv(text: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [];
  let field = "";
  let inQuotes = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (inQuotes) {
      if (c === '"') {
        if (text[i + 1] === '"') { field += '"'; i++; } else { inQuotes = false; }
      } else { field += c; }
    } else if (c === '"') {
      inQuotes = true;
    } else if (c === ",") {
      row.push(field); field = "";
    } else if (c === "\n" || c === "\r") {
      if (c === "\r" && text[i + 1] === "\n") i++;
      row.push(field); field = "";
      if (row.some((v) => v.trim() !== "")) rows.push(row);
      row = [];
    } else { field += c; }
  }
  if (field !== "" || row.length > 0) { row.push(field); if (row.some((v) => v.trim() !== "")) rows.push(row); }
  return rows;
}

function autoMap(header: string): LeadField | "" {
  const h = header.toLowerCase().replace(/[^a-z]/g, "");
  if (h.includes("email") || h.includes("mail")) return "email";
  if (h.includes("name") && !h.includes("company")) return "name";
  if (h.includes("company") || h.includes("org") || h.includes("venue")) return "company";
  if (h.includes("title") || h.includes("role") || h.includes("position")) return "title";
  if (h.includes("phone") || h.includes("cell") || h.includes("mobile")) return "phone";
  // Only match a header that *is* an external id — not any header that merely
  // contains "id" (e.g. "candidate", "paid", "video", "guid").
  if (h === "id" || h === "externalid") return "external_id";
  return "";
}

function ImportLeadsModal({
  onClose, onImport,
}: {
  onClose: () => void;
  onImport: (rows: Array<Record<string, unknown>>) => Promise<void>;
}) {
  const [step, setStep] = useState<"upload" | "map">("upload");
  const [headers, setHeaders] = useState<string[]>([]);
  const [dataRows, setDataRows] = useState<string[][]>([]);
  const [mapping, setMapping] = useState<Record<number, LeadField | "">>({});
  const [importing, setImporting] = useState(false);
  const [parseError, setParseError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement | null>(null);

  const handleFile = async (file: File) => {
    setParseError(null);
    try {
      const text = await file.text();
      const parsed = parseCsv(text);
      if (parsed.length < 2) { setParseError("CSV needs a header row and at least one data row."); return; }
      const hdr = parsed[0];
      setHeaders(hdr);
      setDataRows(parsed.slice(1));
      const init: Record<number, LeadField | ""> = {};
      hdr.forEach((h, i) => { init[i] = autoMap(h); });
      setMapping(init);
      setStep("map");
    } catch {
      setParseError("Couldn't read that file.");
    }
  };

  const mappedRows = useMemo(() => {
    return dataRows.map((cells) => {
      const rec: Record<string, unknown> = {};
      headers.forEach((_, i) => {
        const field = mapping[i];
        if (field && cells[i] != null && cells[i].trim() !== "") rec[field] = cells[i].trim();
      });
      return rec;
    }).filter((r) => Object.keys(r).length > 0);
  }, [dataRows, headers, mapping]);

  const runImport = async () => {
    if (!mappedRows.length || importing) return;
    setImporting(true);
    try {
      await onImport(mappedRows);
    } finally {
      setImporting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-4" onClick={onClose}>
      <div className="w-full max-w-lg rounded-2xl border border-zinc-800 bg-zinc-950 shadow-2xl max-h-[85vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b border-zinc-800 px-5 py-4 sticky top-0 bg-zinc-950">
          <div className="flex items-center gap-2">
            <Upload className="h-4 w-4 text-indigo-400" />
            <p className="text-sm font-semibold text-zinc-100">Import Leads (CSV)</p>
          </div>
          <button onClick={onClose} className="text-zinc-400 hover:text-zinc-100 cursor-pointer"><X className="h-4 w-4" /></button>
        </div>

        {step === "upload" && (
          <div className="p-5 space-y-4">
            <button
              onClick={() => fileRef.current?.click()}
              className="w-full rounded-xl border border-dashed border-zinc-700 bg-zinc-900/40 px-4 py-10 flex flex-col items-center gap-3 hover:border-indigo-500/50 hover:bg-indigo-500/5 transition-colors"
            >
              <Upload className="h-8 w-8 text-zinc-600" />
              <p className="text-sm text-zinc-300">Click to choose a CSV file</p>
              <p className="text-xs text-zinc-600">Up to 10,000 rows · dedupes on email</p>
            </button>
            <input
              ref={fileRef}
              type="file"
              accept=".csv,text/csv"
              className="hidden"
              onChange={(e) => { const f = e.target.files?.[0]; if (f) handleFile(f); }}
            />
            {parseError && <p className="text-xs text-rose-400 flex items-center gap-1.5"><AlertCircle className="h-3.5 w-3.5" /> {parseError}</p>}
          </div>
        )}

        {step === "map" && (
          <div className="p-5 space-y-4">
            <p className="text-xs text-zinc-500">
              Map each CSV column to a lead field. <span className="text-zinc-300">{dataRows.length}</span> rows detected.
            </p>
            <div className="space-y-2">
              {headers.map((h, i) => (
                <div key={i} className="flex items-center gap-3">
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-medium text-zinc-200 truncate">{h || `Column ${i + 1}`}</p>
                    <p className="text-[10px] text-zinc-600 truncate font-mono">{dataRows[0]?.[i] ?? ""}</p>
                  </div>
                  <ChevronRight className="h-3.5 w-3.5 text-zinc-700 flex-shrink-0" />
                  <select
                    value={mapping[i] ?? ""}
                    onChange={(e) => setMapping((m) => ({ ...m, [i]: e.target.value as LeadField | "" }))}
                    className="w-40 flex-shrink-0 rounded-lg border border-zinc-700 bg-zinc-800 px-2.5 py-1.5 text-xs text-zinc-100 focus:border-indigo-500 focus:outline-none"
                  >
                    <option value="">— skip —</option>
                    {LEAD_FIELDS.map((f) => <option key={f} value={f}>{f}</option>)}
                  </select>
                </div>
              ))}
            </div>
            <div className="flex gap-2 pt-1">
              <Button type="button" variant="secondary" className="flex-1 justify-center" onClick={() => setStep("upload")}>Back</Button>
              <Button type="button" variant="primary" className="flex-1 justify-center" onClick={runImport} disabled={importing || !mappedRows.length}>
                {importing ? <><Loader2 className="h-3.5 w-3.5 animate-spin" /> Importing…</> : <>Import {mappedRows.length} leads</>}
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Page ────────────────────────────────────────────────────────────────────

type ViewMode = "table" | "board";

export default function LeadsPage() {
  const { leads, loading, createLead, deleteLead, updateStage, promoteLead, importLeads, refetch } = useLeads();
  const [view, setView] = useState<ViewMode>("table");
  const [search, setSearch] = useState("");
  const [filterStage, setFilterStage] = useState<LeadStage | "all">("all");
  const [selected, setSelected] = useState<Lead | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [bulkBusy, setBulkBusy] = useState(false);
  const [newLeadOpen, setNewLeadOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [promoting, setPromoting] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const importPoller = useJobPoller();

  const showToast = useCallback((msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(null), 5000);
  }, []);

  // When a real (non-demo) CSV import job finishes, pull the freshly-created
  // rows into the list. Demo imports never start the poller (handleImport
  // returns early) because importLeads already updated state optimistically.
  const { state: importState, reset: resetImportPoller } = importPoller;
  useEffect(() => {
    if (importState === "success") {
      refetch();
      resetImportPoller();
      showToast("Import complete — leads refreshed.");
    } else if (importState === "failure") {
      resetImportPoller();
      showToast("Import failed — check the API connection.");
    }
  }, [importState, refetch, resetImportPoller, showToast]);

  const filtered = useMemo(() => {
    return leads.filter((l) => {
      const q = search.toLowerCase();
      const matchSearch = !q ||
        (l.name ?? "").toLowerCase().includes(q) ||
        (l.company ?? "").toLowerCase().includes(q) ||
        (l.email ?? "").toLowerCase().includes(q);
      const matchStage = filterStage === "all" || l.stage === filterStage;
      return matchSearch && matchStage;
    });
  }, [leads, search, filterStage]);

  const handleSelect = useCallback((id: string, checked: boolean) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (checked) next.add(id); else next.delete(id);
      return next;
    });
  }, []);

  const handleBulkStage = useCallback(async (stage: LeadStage) => {
    if (bulkBusy) return;
    setBulkBusy(true);
    await Promise.allSettled([...selectedIds].map((id) => updateStage(id, stage)));
    setSelectedIds(new Set());
    setBulkBusy(false);
  }, [selectedIds, bulkBusy, updateStage]);

  const handleBulkDelete = useCallback(async () => {
    if (bulkBusy) return;
    setBulkBusy(true);
    await Promise.allSettled([...selectedIds].map((id) => deleteLead(id)));
    setSelectedIds(new Set());
    setBulkBusy(false);
  }, [selectedIds, bulkBusy, deleteLead]);

  const handleStageChange = useCallback(async (stage: LeadStage) => {
    if (!selected) return;
    await updateStage(selected.id, stage);
    setSelected((prev) => (prev ? { ...prev, stage } : null));
  }, [selected, updateStage]);

  const handlePromote = useCallback(async () => {
    if (!selected || promoting) return;
    setPromoting(true);
    try {
      await promoteLead(selected.id, { create_deal: false });
      showToast(`Promoted ${selected.name ?? "lead"} to a contact.`);
      setSelected(null);
    } catch {
      showToast("Promote failed — check the API connection.");
    } finally {
      setPromoting(false);
    }
  }, [selected, promoting, promoteLead, showToast]);

  const handleCreate = useCallback(async (f: NewLeadForm) => {
    await createLead({ name: f.name || undefined, email: f.email || undefined, company: f.company || undefined, title: f.title || undefined, phone: f.phone || undefined, source: f.source });
    showToast("Lead created.");
  }, [createLead, showToast]);

  const handleImport = useCallback(async (rows: Array<Record<string, unknown>>) => {
    const res = await importLeads(rows, undefined, "email");
    setImportOpen(false);
    // Demo jobs don't hit the real /jobs endpoint — skip polling, toast directly.
    if (isDemoMode || !res?.job_id || res.job_id.startsWith("demo")) {
      showToast(`Queued ${rows.length} leads for import.`);
      return;
    }
    importPoller.start(res.job_id);
    showToast(`Import queued (${rows.length} rows) — processing…`);
  }, [importLeads, importPoller, showToast]);

  const stageCounts = useMemo(() => {
    const m: Record<string, number> = { all: leads.length };
    for (const s of funnelStageOrder) m[s] = leads.filter((l) => l.stage === s).length;
    return m;
  }, [leads]);

  return (
    <div className="flex flex-col gap-6 p-4 md:p-6 min-h-screen">
      <Header title="Leads" subtitle={`${leads.length} in funnel · engagement-scored`} />

      {/* Stat-tile filter row */}
      <div className="grid grid-cols-3 gap-3 sm:grid-cols-4 lg:grid-cols-7">
        <button
          onClick={() => setFilterStage("all")}
          className={cn(
            "rounded-xl border px-4 py-3 text-left transition-all duration-200 cursor-pointer",
            filterStage === "all" ? "border-indigo-500/40 bg-indigo-600/10" : "border-zinc-800 bg-zinc-900 hover:border-zinc-700"
          )}
        >
          <p className="text-xl font-bold font-mono text-zinc-100">{stageCounts.all}</p>
          <p className="text-xs text-zinc-500 mt-0.5">Total</p>
        </button>
        {funnelStageOrder.map((s) => {
          const cfg = funnelStageConfig[s];
          return (
            <button
              key={s}
              onClick={() => setFilterStage(s)}
              className={cn(
                "rounded-xl border px-4 py-3 text-left transition-all duration-200 cursor-pointer",
                filterStage === s ? "border-indigo-500/40 bg-indigo-600/10" : "border-zinc-800 bg-zinc-900 hover:border-zinc-700"
              )}
            >
              <p className={cn("text-xl font-bold font-mono", cfg.color)}>{stageCounts[s]}</p>
              <p className="text-xs text-zinc-500 mt-0.5">{cfg.label}</p>
            </button>
          );
        })}
      </div>

      {/* Controls */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2 flex-1 min-w-48 max-w-xs">
          <Search className="h-3.5 w-3.5 text-zinc-500 flex-shrink-0" />
          <input
            type="search"
            placeholder="Search leads…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full rounded-lg border border-zinc-800 bg-zinc-900 py-1.5 px-2.5 text-xs text-zinc-300 placeholder-zinc-600 outline-none focus:border-indigo-500/50 transition"
            aria-label="Search leads"
          />
          {search && (
            <button onClick={() => setSearch("")} className="text-zinc-600 hover:text-zinc-300 flex-shrink-0"><X className="h-3.5 w-3.5" /></button>
          )}
        </div>

        {/* View toggle */}
        <div className="flex items-center rounded-lg border border-zinc-800 bg-zinc-900 p-0.5 ml-auto">
          <button
            onClick={() => setView("table")}
            className={cn("flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-medium transition", view === "table" ? "bg-zinc-800 text-zinc-100" : "text-zinc-500 hover:text-zinc-300")}
            aria-pressed={view === "table"}
          >
            <TableIcon className="h-3.5 w-3.5" /> Table
          </button>
          <button
            onClick={() => setView("board")}
            className={cn("flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-medium transition", view === "board" ? "bg-zinc-800 text-zinc-100" : "text-zinc-500 hover:text-zinc-300")}
            aria-pressed={view === "board"}
          >
            <LayoutGrid className="h-3.5 w-3.5" /> Funnel
          </button>
        </div>

        <button
          onClick={() => setImportOpen(true)}
          className="flex items-center gap-1.5 rounded-lg border border-zinc-800 bg-zinc-900 px-3 py-1.5 text-xs font-medium text-zinc-400 hover:border-zinc-700 hover:text-zinc-300 transition cursor-pointer"
        >
          <Upload className="h-3 w-3" /> Import CSV
        </button>
        <Button variant="cta" size="sm" onClick={() => setNewLeadOpen(true)}>
          <Plus className="h-3.5 w-3.5" /> New Lead
        </Button>
      </div>

      {/* Content */}
      {loading ? (
        <div className="space-y-2">
          {[1, 2, 3, 4, 5].map((i) => <div key={i} className="h-14 rounded-xl bg-zinc-800/30 animate-pulse" />)}
        </div>
      ) : view === "table" ? (
        <Card className="p-0 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-zinc-800 text-left">
                  <th className="pl-4 py-3 w-8" />
                  <th className="px-4 py-3 text-[10px] font-mono uppercase tracking-widest text-zinc-500">Lead</th>
                  <th className="px-4 py-3 text-[10px] font-mono uppercase tracking-widest text-zinc-500 hidden md:table-cell">Company</th>
                  <th className="px-4 py-3 text-[10px] font-mono uppercase tracking-widest text-zinc-500 hidden sm:table-cell">Stage</th>
                  <th className="px-4 py-3 text-[10px] font-mono uppercase tracking-widest text-zinc-500 hidden lg:table-cell">Score</th>
                  <th className="px-4 py-3 text-[10px] font-mono uppercase tracking-widest text-zinc-500 hidden xl:table-cell">Source</th>
                  <th className="px-4 py-3" />
                </tr>
              </thead>
              <tbody>
                {filtered.map((lead) => (
                  <LeadRow
                    key={lead.id}
                    lead={lead}
                    onClick={() => { if (!selectedIds.size) setSelected(lead); }}
                    selected={selectedIds.has(lead.id)}
                    onSelect={handleSelect}
                  />
                ))}
              </tbody>
            </table>
            {filtered.length === 0 && (
              <div className="flex flex-col items-center gap-3 py-16 text-center">
                <Filter className="h-8 w-8 text-zinc-700" />
                <p className="text-sm text-zinc-500">No leads match your filters.</p>
              </div>
            )}
          </div>
        </Card>
      ) : (
        <div className="flex gap-4 overflow-x-auto pb-4" role="region" aria-label="Leads funnel board">
          {funnelStageOrder.map((stage) => (
            <FunnelColumn
              key={stage}
              stage={stage}
              leads={filtered.filter((l) => l.stage === stage)}
              onSelect={(l) => setSelected(l)}
            />
          ))}
        </div>
      )}

      {/* Bulk bar */}
      {selectedIds.size > 0 && (
        <BulkActionBar
          count={selectedIds.size}
          onSetStage={handleBulkStage}
          onDelete={handleBulkDelete}
          onClear={() => setSelectedIds(new Set())}
          busy={bulkBusy}
        />
      )}

      {/* Detail drawer */}
      {selected && !selectedIds.size && (
        <>
          <div className="fixed inset-0 bg-black/40 z-30" onClick={() => setSelected(null)} />
          <LeadDetailPanel
            lead={selected}
            onClose={() => setSelected(null)}
            onStageChange={handleStageChange}
            onPromote={handlePromote}
            promoting={promoting}
          />
        </>
      )}

      {/* Modals */}
      {newLeadOpen && <NewLeadModal onClose={() => setNewLeadOpen(false)} onCreate={handleCreate} />}
      {importOpen && <ImportLeadsModal onClose={() => setImportOpen(false)} onImport={handleImport} />}

      {/* Toast */}
      {toast && (
        <div className="fixed bottom-6 right-6 z-[60] flex items-center gap-2 rounded-xl border border-indigo-500/30 bg-zinc-900/95 backdrop-blur px-4 py-3 shadow-2xl animate-slide-up">
          <CheckCircle2 className="h-4 w-4 text-emerald-400 flex-shrink-0" />
          <span className="text-sm text-zinc-200">{toast}</span>
        </div>
      )}
    </div>
  );
}
