"use client";

import { useState, useMemo, useEffect, useCallback, useRef } from "react";
import Header from "@/components/layout/Header";
import Card from "@/components/ui/Card";
import Badge from "@/components/ui/Badge";
import Avatar from "@/components/ui/Avatar";
import Button from "@/components/ui/Button";
import LogActivityModal from "@/components/ui/LogActivityModal";
import ConfirmDialog from "@/components/ui/ConfirmDialog";
import { cn, formatCurrency, leadScoreConfig } from "@/lib/utils";
import { useContacts } from "@/hooks/useContacts";
import { useJobPoller } from "@/hooks/useJobPoller";
import { apiClient } from "@/lib/api-client";
import { createBrowserClient } from "@/lib/supabase";
import {
  Search, SlidersHorizontal, Brain, Sparkles, TrendingUp,
  TrendingDown, Minus, ChevronRight, Filter, UserPlus, Mail,
  Copy, X, Loader2, Zap, ClipboardList, CheckSquare, Square, Tag,
} from "lucide-react";
import type { Contact, ContactStatus, LeadScore } from "@/lib/types";

interface EmailDraft {
  subject: string;
  body: string;
}

interface IngestedMessage {
  id: string;
  subject: string | null;
  received_at: string | null;
  clarity_score?: { score: number } | null;
  contact_id: string | null;
}

function formatRelative(dateStr: string | null): string {
  if (!dateStr) return "";
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "Just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

const statusConfig: Record<ContactStatus, { label: string; variant: "indigo" | "emerald" | "amber" | "rose" | "zinc" }> = {
  lead: { label: "Lead", variant: "zinc" },
  prospect: { label: "Prospect", variant: "amber" },
  customer: { label: "Customer", variant: "emerald" },
  churned: { label: "Churned", variant: "rose" },
};

const trendIcon = {
  up: <TrendingUp className="h-3 w-3 text-emerald-400" aria-hidden="true" />,
  down: <TrendingDown className="h-3 w-3 text-rose-400" aria-hidden="true" />,
  stable: <Minus className="h-3 w-3 text-zinc-400" aria-hidden="true" />,
};

function MLScoreBar({ score, label }: { score: number; label: LeadScore }) {
  const cfg = leadScoreConfig[label];
  return (
    <div className="flex items-center gap-2 min-w-0">
      <div className="flex-1 h-1.5 rounded-full bg-zinc-800 overflow-hidden">
        <div
          className={cn(
            "h-full rounded-full transition-all",
            label === "hot" ? "bg-emerald-400" : label === "warm" ? "bg-amber-400" : "bg-zinc-500"
          )}
          style={{ width: `${score}%` }}
          role="progressbar"
          aria-valuenow={score}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label={`ML score: ${score}`}
        />
      </div>
      <span className={cn("text-xs font-mono font-medium w-8 flex-shrink-0", cfg.text)}>
        {score}
      </span>
    </div>
  );
}

function ContactRow({
  contact, onClick, similarity, selected, onSelect,
}: {
  contact: Contact;
  onClick: () => void;
  similarity?: number | null;
  selected?: boolean;
  onSelect?: (id: string, checked: boolean) => void;
}) {
  const statusCfg = statusConfig[contact.status];
  const leadCfg = leadScoreConfig[contact.mlScore.label];

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
      {/* Checkbox */}
      <td className="pl-4 py-3 w-8" onClick={(e) => e.stopPropagation()}>
        <button
          onClick={() => onSelect?.(contact.id, !selected)}
          className="text-zinc-500 hover:text-indigo-400 transition-colors"
          aria-label={selected ? "Deselect contact" : "Select contact"}
        >
          {selected
            ? <CheckSquare className="h-4 w-4 text-indigo-400" />
            : <Square className="h-4 w-4" />}
        </button>
      </td>
      {/* Contact */}
      <td className="px-4 py-3">
        <div className="flex items-center gap-3">
          <Avatar initials={contact.avatar} size="sm" />
          <div className="min-w-0">
            <p className="text-sm font-medium text-zinc-100 truncate">{contact.name}</p>
            <p className="text-xs text-zinc-500 truncate">{contact.email}</p>
          </div>
        </div>
      </td>

      {/* Company + Role */}
      <td className="px-4 py-3 hidden md:table-cell">
        <p className="text-sm text-zinc-300 truncate">{contact.company}</p>
        <p className="text-xs text-zinc-500 truncate">{contact.role}</p>
      </td>

      {/* Status */}
      <td className="px-4 py-3 hidden sm:table-cell">
        <Badge variant={statusCfg.variant} size="sm">
          {statusCfg.label}
        </Badge>
      </td>

      {/* ML Score */}
      <td className="px-4 py-3 hidden lg:table-cell min-w-[140px]">
        <div className="flex items-center gap-2">
          {trendIcon[contact.mlScore.trend]}
          <MLScoreBar score={contact.mlScore.value} label={contact.mlScore.label} />
        </div>
      </td>

      {/* Semantic Tags */}
      <td className="px-4 py-3 hidden xl:table-cell max-w-xs">
        <div className="flex flex-wrap gap-1">
          {contact.semanticTags.slice(0, 2).map((tag) => (
            <Badge key={tag.label} variant={tag.color} size="sm" className="text-[10px]">
              {tag.label}
            </Badge>
          ))}
          {contact.semanticTags.length > 2 && (
            <span className="text-[10px] text-zinc-600 self-center">
              +{contact.semanticTags.length - 2}
            </span>
          )}
        </div>
      </td>

      {/* Revenue */}
      <td className="px-4 py-3 hidden md:table-cell text-right">
        <p className="text-sm font-mono text-zinc-200">
          {contact.revenue > 0 ? formatCurrency(contact.revenue) : "—"}
        </p>
        <p className="text-xs text-zinc-600">{contact.deals} deals</p>
      </td>

      {/* Last Activity / Similarity */}
      <td className="px-4 py-3 text-right">
        {similarity != null ? (
          <span className={cn(
            "text-xs font-mono font-medium",
            similarity >= 0.7 ? "text-emerald-400" : similarity >= 0.5 ? "text-amber-400" : "text-zinc-400"
          )}>
            {Math.round(similarity * 100)}%
          </span>
        ) : (
          <p className="text-xs text-zinc-500 font-mono">{contact.lastActivity}</p>
        )}
        <ChevronRight
          className="h-4 w-4 text-zinc-700 group-hover:text-zinc-400 transition-colors ml-auto mt-1"
          aria-hidden="true"
        />
      </td>
    </tr>
  );
}

function BulkActionBar({
  count,
  onStatusChange,
  onEnrich,
  onClear,
  busy,
}: {
  count: number;
  onStatusChange: (status: ContactStatus) => void;
  onEnrich: () => void;
  onClear: () => void;
  busy: boolean;
}) {
  const [statusMenuOpen, setStatusMenuOpen] = useState(false);
  return (
    <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 flex items-center gap-3 rounded-2xl border border-indigo-500/30 bg-zinc-900/95 backdrop-blur px-5 py-3 shadow-2xl animate-slide-up">
      <span className="text-sm font-medium text-indigo-300 whitespace-nowrap">
        {count} selected
      </span>
      <div className="w-px h-4 bg-zinc-700 flex-shrink-0" />
      <div className="relative">
        <button
          onClick={() => setStatusMenuOpen((v) => !v)}
          disabled={busy}
          className="flex items-center gap-1.5 rounded-lg border border-zinc-700 px-3 py-1.5 text-xs font-medium text-zinc-300 hover:border-zinc-600 hover:text-zinc-100 disabled:opacity-50 transition"
        >
          <Tag className="h-3.5 w-3.5" /> Set Status
        </button>
        {statusMenuOpen && (
          <div className="absolute bottom-full mb-2 left-0 rounded-xl border border-zinc-800 bg-zinc-950 shadow-xl overflow-hidden min-w-36">
            {(["lead", "prospect", "customer", "churned"] as ContactStatus[]).map((s) => (
              <button
                key={s}
                onClick={() => { onStatusChange(s); setStatusMenuOpen(false); }}
                className="w-full px-4 py-2 text-left text-xs text-zinc-300 hover:bg-zinc-800 transition capitalize"
              >
                {s}
              </button>
            ))}
          </div>
        )}
      </div>
      <button
        onClick={onEnrich}
        disabled={busy}
        className="flex items-center gap-1.5 rounded-lg border border-zinc-700 px-3 py-1.5 text-xs font-medium text-zinc-300 hover:border-zinc-600 hover:text-zinc-100 disabled:opacity-50 transition"
      >
        {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5" />}
        Enrich All
      </button>
      <div className="w-px h-4 bg-zinc-700 flex-shrink-0" />
      <button onClick={onClear} className="text-zinc-500 hover:text-zinc-300 transition">
        <X className="h-4 w-4" />
      </button>
    </div>
  );
}

function EmailComposerModal({
  draft,
  contact,
  onClose,
  hasGmailConnector,
  workspaceId,
  token,
}: {
  draft: EmailDraft;
  contact: Contact;
  onClose: () => void;
  hasGmailConnector: boolean;
  workspaceId: string | null;
  token: string | null;
}) {
  const [copied, setCopied] = useState(false);
  const [sending, setSending] = useState(false);
  const [sendSuccess, setSendSuccess] = useState(false);
  const [sendError, setSendError] = useState<string | null>(null);

  const handleCopy = () => {
    navigator.clipboard.writeText(`Subject: ${draft.subject}\n\n${draft.body}`);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleSend = async () => {
    if (!workspaceId || !token || sending || sendSuccess) return;
    setSending(true);
    setSendError(null);
    try {
      await apiClient.sendEmail(workspaceId, contact.id, {
        to: contact.email,
        subject: draft.subject,
        body: draft.body,
      }, token);
      setSendSuccess(true);
    } catch {
      setSendError("Send failed — check Gmail connection");
    } finally {
      setSending(false);
    }
  };

  return (
    <div
      className="fixed inset-0 bg-black/70 z-[60] flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-lg rounded-2xl border border-zinc-800 bg-zinc-950 overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-zinc-800 px-5 py-4">
          <div className="flex items-center gap-2">
            <Mail className="h-4 w-4 text-indigo-400" />
            <p className="text-sm font-semibold text-zinc-100">AI-Generated Email Draft</p>
          </div>
          <button onClick={onClose} className="text-zinc-400 hover:text-zinc-100 cursor-pointer">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="p-5 space-y-4">
          <div>
            <p className="text-[10px] text-zinc-500 font-mono uppercase tracking-widest mb-1">Subject</p>
            <p className="text-sm font-medium text-zinc-100 rounded-lg border border-zinc-800 bg-zinc-900 px-3 py-2">
              {draft.subject}
            </p>
          </div>
          <div>
            <p className="text-[10px] text-zinc-500 font-mono uppercase tracking-widest mb-1">Body</p>
            <div className="rounded-lg border border-zinc-800 bg-zinc-900 px-3 py-3 max-h-64 overflow-y-auto">
              <pre className="text-sm text-zinc-200 whitespace-pre-wrap font-sans leading-relaxed">
                {draft.body}
              </pre>
            </div>
          </div>

          <div className="flex gap-2">
            <Button variant="primary" className="flex-1 justify-center" onClick={handleCopy}>
              <Copy className="h-3.5 w-3.5" />
              {copied ? "Copied!" : "Copy to Clipboard"}
            </Button>
            {hasGmailConnector ? (
              <Button
                variant="secondary"
                className="flex-1 justify-center"
                onClick={handleSend}
                disabled={sending || sendSuccess}
              >
                {sending ? (
                  <><Loader2 className="h-3.5 w-3.5 animate-spin" /> Sending…</>
                ) : sendSuccess ? (
                  <><span className="text-emerald-400 font-bold">✓</span> Sent!</>
                ) : (
                  <><Mail className="h-3.5 w-3.5" /> Send via Gmail</>
                )}
              </Button>
            ) : (
              <Button variant="secondary" className="flex-1 justify-center opacity-40" disabled>
                <Mail className="h-3.5 w-3.5" />
                No Gmail
              </Button>
            )}
          </div>
          {sendError && (
            <p className="text-xs text-rose-400 text-center">{sendError}</p>
          )}
        </div>
      </div>
    </div>
  );
}

type DrawerTab = "overview" | "messages" | "timeline";

interface TimelineEvent {
  id: string;
  type: "message" | "call" | "deal_stage" | "activity";
  title: string;
  body: string;
  ts: string | null;
  meta: Record<string, unknown>;
}

function ContactDrawer({ contact, onClose, workspaceId, token, hasGmailConnector }: {
  contact: Contact;
  onClose: () => void;
  workspaceId: string | null;
  token: string | null;
  hasGmailConnector: boolean;
}) {
  const leadCfg = leadScoreConfig[contact.mlScore.label];
  const [activeTab, setActiveTab] = useState<DrawerTab>("overview");
  const [messages, setMessages] = useState<IngestedMessage[]>([]);
  const [messagesLoading, setMessagesLoading] = useState(false);
  const [composing, setComposing] = useState(false);
  const [emailDraft, setEmailDraft] = useState<EmailDraft | null>(null);
  const [composeError, setComposeError] = useState<string | null>(null);
  const enrichPoller = useJobPoller();
  const [logActivityOpen, setLogActivityOpen] = useState(false);
  const [flagConfirmOpen, setFlagConfirmOpen] = useState(false);
  const [briefing, setBriefing] = useState(false);
  const [briefText, setBriefText] = useState<string | null>(null);
  const [timeline, setTimeline] = useState<TimelineEvent[]>([]);
  const [timelineLoading, setTimelineLoading] = useState(false);

  useEffect(() => {
    if (activeTab !== "timeline" || !workspaceId || !token) return;
    setTimelineLoading(true);
    apiClient
      .getContactTimeline(workspaceId, contact.id, token)
      .then((data: TimelineEvent[]) => setTimeline(Array.isArray(data) ? data : []))
      .catch(() => setTimeline([]))
      .finally(() => setTimelineLoading(false));
  }, [activeTab, workspaceId, token, contact.id]);

  // Fetch messages when the Messages tab is opened
  useEffect(() => {
    if (activeTab !== "messages" || !workspaceId || !token) return;
    setMessagesLoading(true);
    apiClient
      .getMessages(workspaceId, token)
      .then((data: IngestedMessage[]) => {
        const linked = Array.isArray(data)
          ? data.filter((m) => m.contact_id === contact.id)
          : [];
        setMessages(linked);
      })
      .catch(() => setMessages([]))
      .finally(() => setMessagesLoading(false));
  }, [activeTab, workspaceId, token, contact.id]);

  return (
    <>
    <aside
      className="fixed right-0 top-0 h-full w-96 border-l border-zinc-800 bg-zinc-950 z-40 overflow-y-auto animate-slide-up"
      aria-label={`Contact details for ${contact.name}`}
    >
      <div className="sticky top-0 border-b border-zinc-800 bg-zinc-950/90 backdrop-blur z-10">
        <div className="flex items-center justify-between px-5 py-4">
          <p className="text-sm font-semibold text-zinc-100">Contact Details</p>
          <button
            onClick={onClose}
            className="text-zinc-400 hover:text-zinc-100 cursor-pointer transition-colors"
            aria-label="Close contact details"
          >
            ✕
          </button>
        </div>
        {/* Tabs */}
        <div className="flex border-t border-zinc-800">
          {(["overview", "timeline", "messages"] as const).map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={cn(
                "flex-1 py-2.5 text-xs font-medium transition-colors cursor-pointer",
                activeTab === tab
                  ? "border-b-2 border-indigo-500 text-indigo-400"
                  : "text-zinc-500 hover:text-zinc-300"
              )}
            >
              {tab === "overview" ? "Overview" : tab === "timeline" ? "Timeline" : "Messages"}
            </button>
          ))}
        </div>
      </div>

      <div className="p-5 space-y-6">
        {/* Identity — always shown */}
        <div className="flex items-center gap-4">
          <Avatar initials={contact.avatar} size="lg" />
          <div>
            <h2 className="text-base font-bold text-zinc-100">{contact.name}</h2>
            <p className="text-sm text-zinc-400">{contact.role} at {contact.company}</p>
            <p className="text-xs text-zinc-500 font-mono mt-1">{contact.email}</p>
          </div>
        </div>

        {activeTab === "overview" && (
          <>
            {/* ML Score Panel */}
            <Card className="space-y-3">
              <div className="flex items-center gap-2">
                <Brain className="h-4 w-4 text-indigo-400" aria-hidden="true" />
                <p className="text-xs font-semibold text-zinc-300">ML Score Analysis</p>
              </div>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className={cn("text-2xl font-bold font-mono", leadCfg.text)}>
                    {contact.mlScore.value}
                  </span>
                  <div className={cn("flex items-center gap-1 rounded-full px-2 py-0.5 text-xs", leadCfg.bg, leadCfg.text)}>
                    <span className={cn("h-1.5 w-1.5 rounded-full", leadCfg.dot)} />
                    {leadCfg.label}
                  </div>
                </div>
                <div className="flex items-center gap-1 text-xs text-zinc-500">
                  {trendIcon[contact.mlScore.trend]}
                  {contact.mlScore.trend === "up"
                    ? "Rising"
                    : contact.mlScore.trend === "down"
                    ? "Falling"
                    : "Stable"}
                </div>
              </div>
              <div className="space-y-1">
                <p className="text-[10px] text-zinc-500 font-mono uppercase tracking-widest">Signals</p>
                {contact.mlScore.signals.map((sig) => (
                  <div key={sig} className="flex items-center gap-2 text-xs text-zinc-300">
                    <span className="h-1 w-1 rounded-full bg-indigo-400 flex-shrink-0" />
                    {sig}
                  </div>
                ))}
              </div>
            </Card>

            {/* Semantic Tags */}
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <Sparkles className="h-4 w-4 text-indigo-400" aria-hidden="true" />
                <p className="text-xs font-semibold text-zinc-300">Semantic Classification</p>
              </div>
              {contact.semanticTags.map((tag) => (
                <div key={tag.label} className="flex items-center justify-between rounded-lg border border-zinc-800 bg-zinc-900 px-3 py-2">
                  <Badge variant={tag.color} size="sm">{tag.label}</Badge>
                  <div className="text-right">
                    <p className="text-xs font-mono text-zinc-300">{(tag.confidence * 100).toFixed(0)}%</p>
                    <p className="text-[10px] text-zinc-600">confidence</p>
                  </div>
                </div>
              ))}
            </div>

            {/* Stats */}
            <div className="grid grid-cols-2 gap-3">
              <Card className="text-center">
                <p className="text-xl font-bold font-mono text-zinc-100">
                  {contact.revenue > 0 ? formatCurrency(contact.revenue) : "—"}
                </p>
                <p className="text-xs text-zinc-500 mt-1">Total Revenue</p>
              </Card>
              <Card className="text-center">
                <p className="text-xl font-bold font-mono text-zinc-100">{contact.deals}</p>
                <p className="text-xs text-zinc-500 mt-1">Active Deals</p>
              </Card>
            </div>

            {/* Actions */}
            <div className="flex flex-col gap-2">
              <Button
                variant="primary"
                className="w-full justify-center"
                disabled={composing}
                onClick={async () => {
                  if (!workspaceId || !token) return;
                  setComposing(true);
                  setComposeError(null);
                  try {
                    const result = await apiClient.composeEmail(workspaceId, contact.id, token);
                    setEmailDraft({ subject: result.subject, body: result.body });
                  } catch {
                    setComposeError("Email composer unavailable — check API connection");
                  } finally {
                    setComposing(false);
                  }
                }}
              >
                {composing ? (
                  <><Loader2 className="h-3.5 w-3.5 animate-spin" /> Generating draft...</>
                ) : (
                  <><Mail className="h-3.5 w-3.5" /> Compose AI Email</>
                )}
              </Button>
              {composeError && (
                <p className="text-xs text-rose-400 text-center">{composeError}</p>
              )}
              <Button
                variant="secondary"
                className="w-full justify-center"
                disabled={enrichPoller.state === "pending" || enrichPoller.state === "started" || enrichPoller.state === "success"}
                onClick={async () => {
                  if (!workspaceId || !token) return;
                  try {
                    const res = await apiClient.enrichContact(workspaceId, contact.id, token);
                    if (res?.job_id) enrichPoller.start(res.job_id);
                  } catch { /* silent */ }
                }}
              >
                {enrichPoller.state === "pending" || enrichPoller.state === "started" ? (
                  <><Loader2 className="h-3.5 w-3.5 animate-spin" /> Enriching…</>
                ) : enrichPoller.state === "success" ? (
                  <><Sparkles className="h-3.5 w-3.5 text-[#00C896]" /> Enriched!</>
                ) : enrichPoller.state === "failure" ? (
                  <><Sparkles className="h-3.5 w-3.5 text-rose-400" /> Enrich Failed</>
                ) : (
                  <><Sparkles className="h-3.5 w-3.5" /> Auto-Enrich Contact</>
                )}
              </Button>
              <Button variant="secondary" className="w-full justify-center" onClick={() => setActiveTab("timeline")}>View Timeline</Button>
              <Button
                variant="secondary"
                className="w-full justify-center"
                disabled={briefing}
                onClick={async () => {
                  if (!workspaceId || !token) return;
                  setBriefing(true);
                  setBriefText(null);
                  try {
                    const res = await apiClient.getMeetingBrief(workspaceId, contact.id, token);
                    setBriefText(res.brief);
                  } catch { /* silent */ } finally {
                    setBriefing(false);
                  }
                }}
              >
                {briefing ? (
                  <><Loader2 className="h-3.5 w-3.5 animate-spin" /> Generating Brief…</>
                ) : (
                  <><Brain className="h-3.5 w-3.5" /> Pre-Meeting Brief</>
                )}
              </Button>
              <Button
                variant="secondary"
                className="w-full justify-center"
                onClick={() => setLogActivityOpen(true)}
              >
                <ClipboardList className="h-3.5 w-3.5" />
                Log Activity
              </Button>
              <Button
                variant="ghost"
                className="w-full justify-center text-rose-400 hover:text-rose-300 hover:bg-rose-500/10"
                onClick={() => setFlagConfirmOpen(true)}
              >
                Flag At-Risk
              </Button>
            </div>
          </>
        )}

        {/* Log Activity Modal */}
        {logActivityOpen && (
          <LogActivityModal
            contactName={contact.name}
            onClose={() => setLogActivityOpen(false)}
            onSubmit={({ type, note }) => {
              fetch("/api/activity", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                  type,
                  agent_name: "User",
                  description: note,
                  meta: `contact:${contact.id}`,
                  severity: "info",
                }),
              }).catch(() => {});
            }}
          />
        )}

        {/* Flag At-Risk Confirmation */}
        {flagConfirmOpen && (
          <ConfirmDialog
            title="Flag contact as at-risk?"
            description={`This will mark ${contact.name} as at-risk and alert assigned agents.`}
            actionLabel="Flag At-Risk"
            variant="warning"
            onConfirm={async () => {
              setFlagConfirmOpen(false);
              if (!workspaceId || !token) return;
              try {
                await apiClient.updateContactStatus(workspaceId, contact.id, "churned", token);
              } catch { /* silent — contact list will refresh on next visit */ }
            }}
            onClose={() => setFlagConfirmOpen(false)}
          />
        )}

        {activeTab === "messages" && (
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <Mail className="h-4 w-4 text-indigo-400" aria-hidden="true" />
              <p className="text-xs font-semibold text-zinc-300">Messages from this contact</p>
            </div>

            {messagesLoading ? (
              <div className="space-y-2">
                {[1, 2, 3].map((i) => (
                  <div key={i} className="h-16 rounded-xl border border-zinc-800 bg-zinc-900 animate-pulse" />
                ))}
              </div>
            ) : messages.length === 0 ? (
              <div className="flex flex-col items-center gap-3 py-10 text-center">
                <Mail className="h-8 w-8 text-zinc-700" />
                <p className="text-xs text-zinc-500">No messages from this contact yet.</p>
              </div>
            ) : (
              <div className="space-y-2">
                {messages.map((msg) => (
                  <div
                    key={msg.id}
                    className="rounded-xl border border-zinc-800 bg-zinc-900 px-3 py-2.5 space-y-1"
                  >
                    <p className="text-xs font-medium text-zinc-200 truncate">
                      {msg.subject ?? "(No subject)"}
                    </p>
                    <div className="flex items-center gap-2">
                      <span className="text-[10px] text-zinc-500 font-mono">
                        {formatRelative(msg.received_at)}
                      </span>
                      {msg.clarity_score && (
                        <Badge
                          variant={
                            msg.clarity_score.score >= 70
                              ? "emerald"
                              : msg.clarity_score.score >= 40
                              ? "amber"
                              : "rose"
                          }
                          size="sm"
                        >
                          <Brain className="h-2.5 w-2.5 mr-1" />
                          {msg.clarity_score.score}
                        </Badge>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {activeTab === "timeline" && (
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <Zap className="h-4 w-4 text-indigo-400" aria-hidden="true" />
              <p className="text-xs font-semibold text-zinc-300">Activity Timeline</p>
            </div>

            {timelineLoading ? (
              <div className="space-y-2">
                {[1, 2, 3].map((i) => (
                  <div key={i} className="h-14 rounded-xl border border-zinc-800 bg-zinc-900 animate-pulse" />
                ))}
              </div>
            ) : timeline.length === 0 ? (
              <div className="flex flex-col items-center gap-3 py-10 text-center">
                <Zap className="h-8 w-8 text-zinc-700" />
                <p className="text-xs text-zinc-500">No activity recorded yet.</p>
              </div>
            ) : (
              <div className="relative space-y-0">
                {timeline.map((evt, i) => {
                  const dotColor =
                    evt.type === "message" ? "bg-indigo-400" :
                    evt.type === "call" ? "bg-emerald-400" :
                    evt.type === "deal_stage" ? "bg-amber-400" :
                    "bg-zinc-500";
                  const typeLabel =
                    evt.type === "message" ? "Email" :
                    evt.type === "call" ? "Call" :
                    evt.type === "deal_stage" ? "Deal" :
                    "Activity";
                  return (
                    <div key={evt.id} className="flex gap-3">
                      <div className="flex flex-col items-center">
                        <span className={cn("mt-2 h-2.5 w-2.5 rounded-full flex-shrink-0", dotColor)} />
                        {i < timeline.length - 1 && (
                          <span className="flex-1 w-px bg-zinc-800 mt-1" />
                        )}
                      </div>
                      <div className="pb-4 min-w-0">
                        <div className="flex items-center gap-2 mb-0.5">
                          <span className="text-[10px] font-mono font-medium text-zinc-500 uppercase tracking-wider">{typeLabel}</span>
                          <span className="text-[10px] text-zinc-600 font-mono">{formatRelative(evt.ts)}</span>
                        </div>
                        <p className="text-xs font-medium text-zinc-200 truncate">{evt.title}</p>
                        {evt.body && (
                          <p className="text-[11px] text-zinc-500 mt-0.5 line-clamp-2">{evt.body}</p>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}
      </div>
    </aside>

    {/* Email composer modal — rendered outside aside so it can be full-screen */}
    {emailDraft && (
      <EmailComposerModal
        draft={emailDraft}
        contact={contact}
        onClose={() => setEmailDraft(null)}
        hasGmailConnector={hasGmailConnector}
        workspaceId={workspaceId}
        token={token}
      />
    )}

    {/* Pre-meeting brief modal */}
    {briefText && (
      <div
        className="fixed inset-0 bg-black/70 z-[60] flex items-center justify-center p-4"
        onClick={() => setBriefText(null)}
      >
        <div
          className="w-full max-w-lg rounded-2xl border border-zinc-800 bg-zinc-950 overflow-hidden"
          onClick={(e) => e.stopPropagation()}
        >
          <div className="flex items-center justify-between border-b border-zinc-800 px-5 py-4">
            <div className="flex items-center gap-2">
              <Brain className="h-4 w-4 text-indigo-400" />
              <p className="text-sm font-semibold text-zinc-100">Pre-Meeting Brief — {contact.name}</p>
            </div>
            <button onClick={() => setBriefText(null)} className="text-zinc-400 hover:text-zinc-100 cursor-pointer">
              <X className="h-4 w-4" />
            </button>
          </div>
          <div className="p-5 max-h-[70vh] overflow-y-auto">
            <pre className="text-sm text-zinc-200 whitespace-pre-wrap font-sans leading-relaxed">
              {briefText}
            </pre>
          </div>
          <div className="border-t border-zinc-800 px-5 py-3 flex justify-end">
            <Button
              variant="secondary"
              onClick={() => {
                navigator.clipboard.writeText(briefText);
              }}
            >
              <Copy className="h-3.5 w-3.5" /> Copy Brief
            </Button>
          </div>
        </div>
      </div>
    )}
  </>
  );
}

interface SemanticResult {
  id: string;
  name: string | null;
  email: string | null;
  company: string | null;
  role: string | null;
  status: string;
  ml_score: Record<string, unknown>;
  revenue: number;
  deal_count: number;
  similarity: number | null;
}

interface NewContactPayload { name: string; email: string; company: string; role: string; status: ContactStatus }

function NewContactModal({ onClose, onCreate }: { onClose: () => void; onCreate: (p: NewContactPayload) => Promise<void> }) {
  const [form, setForm] = useState<NewContactPayload>({ name: "", email: "", company: "", role: "", status: "lead" });
  const [saving, setSaving] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.name.trim()) return;
    setSaving(true);
    await onCreate(form);
    setSaving(false);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-4" onClick={onClose}>
      <div className="w-full max-w-md rounded-2xl border border-zinc-800 bg-zinc-950 shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b border-zinc-800 px-5 py-4">
          <p className="text-sm font-semibold text-zinc-100">New Contact</p>
          <button onClick={onClose} className="text-zinc-400 hover:text-zinc-100 transition-colors cursor-pointer"><X className="h-4 w-4" /></button>
        </div>
        <form onSubmit={handleSubmit} className="p-5 space-y-4">
          {([
            { label: "Full name *", key: "name", placeholder: "Sarah Chen" },
            { label: "Email", key: "email", placeholder: "sarah@example.com" },
            { label: "Company", key: "company", placeholder: "Acme Corp" },
            { label: "Role", key: "role", placeholder: "VP of Engineering" },
          ] as const).map(({ label, key, placeholder }) => (
            <div key={key}>
              <label className="block text-xs font-medium text-zinc-400 mb-1.5">{label}</label>
              <input
                type={key === "email" ? "email" : "text"}
                value={form[key]}
                onChange={(e) => setForm((f) => ({ ...f, [key]: e.target.value }))}
                placeholder={placeholder}
                className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3.5 py-2.5 text-sm text-zinc-100 placeholder-zinc-600 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 transition"
              />
            </div>
          ))}
          <div>
            <label className="block text-xs font-medium text-zinc-400 mb-1.5">Status</label>
            <select
              value={form.status}
              onChange={(e) => setForm((f) => ({ ...f, status: e.target.value as ContactStatus }))}
              className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3.5 py-2.5 text-sm text-zinc-100 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 transition"
            >
              {(["lead", "prospect", "customer", "churned"] as ContactStatus[]).map((s) => (
                <option key={s} value={s}>{s.charAt(0).toUpperCase() + s.slice(1)}</option>
              ))}
            </select>
          </div>
          <div className="flex gap-2 pt-1">
            <Button type="button" variant="secondary" className="flex-1 justify-center" onClick={onClose}>Cancel</Button>
            <Button type="submit" variant="primary" className="flex-1 justify-center" disabled={saving || !form.name.trim()}>
              {saving ? "Creating…" : "Create Contact"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default function ContactsPage() {
  const [search, setSearch] = useState("");
  const [filterStatus, setFilterStatus] = useState<ContactStatus | "all">("all");
  const [filterScore, setFilterScore] = useState<LeadScore | "all">("all");
  const [selected, setSelected] = useState<Contact | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [workspaceId, setWorkspaceId] = useState<string | null>(null);
  const [semanticMode, setSemanticMode] = useState(false);
  const [semanticResults, setSemanticResults] = useState<SemanticResult[]>([]);
  const [semanticLoading, setSemanticLoading] = useState(false);
  const [indexing, setIndexing] = useState(false);
  const [newContactOpen, setNewContactOpen] = useState(false);
  const [hasGmailConnector, setHasGmailConnector] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [bulkBusy, setBulkBusy] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const { contacts, createContact } = useContacts();

  useEffect(() => {
    if (process.env.NEXT_PUBLIC_DEMO_MODE === 'true') {
      setToken('demo-token');
      setWorkspaceId('demo-workspace-1');
      return;
    }
    const supabase = createBrowserClient();
    supabase.auth.getSession().then(({ data: { session } }) => {
      if (session) {
        setToken(session.access_token);
        setWorkspaceId(session.user.user_metadata?.workspace_id ?? null);
      }
    });
  }, []);

  useEffect(() => {
    if (!token || !workspaceId) return;
    apiClient.getConnectors(workspaceId, token).then((connectors: Array<{ provider: string }>) => {
      setHasGmailConnector(connectors.some((c) => c.provider === 'gmail'));
    }).catch(() => {});
  }, [token, workspaceId]);

  const handleSelect = useCallback((id: string, checked: boolean) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (checked) next.add(id); else next.delete(id);
      return next;
    });
  }, []);

  const handleSelectAll = useCallback((contacts: Contact[]) => {
    setSelectedIds((prev) => {
      if (prev.size === contacts.length) return new Set();
      return new Set(contacts.map((c) => c.id));
    });
  }, []);

  const handleBulkStatus = useCallback(async (status: ContactStatus) => {
    if (!workspaceId || !token || bulkBusy) return;
    setBulkBusy(true);
    await Promise.allSettled(
      [...selectedIds].map((id) => apiClient.updateContactStatus(workspaceId, id, status, token))
    );
    setSelectedIds(new Set());
    setBulkBusy(false);
  }, [workspaceId, token, selectedIds, bulkBusy]);

  const handleBulkEnrich = useCallback(async () => {
    if (!workspaceId || !token || bulkBusy) return;
    setBulkBusy(true);
    await Promise.allSettled(
      [...selectedIds].map((id) => apiClient.enrichContact(workspaceId, id, token))
    );
    setSelectedIds(new Set());
    setBulkBusy(false);
  }, [workspaceId, token, selectedIds, bulkBusy]);

  // Debounced semantic search
  useEffect(() => {
    if (!semanticMode || !workspaceId || !token || !search.trim()) {
      setSemanticResults([]);
      return;
    }
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(async () => {
      setSemanticLoading(true);
      try {
        const results = await apiClient.semanticSearchContacts(workspaceId, search.trim(), token);
        setSemanticResults(Array.isArray(results) ? results : []);
      } catch {
        setSemanticResults([]);
      } finally {
        setSemanticLoading(false);
      }
    }, 400);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [semanticMode, search, workspaceId, token]);

  const handleIndex = useCallback(async () => {
    if (!workspaceId || !token || indexing) return;
    setIndexing(true);
    try {
      await apiClient.triggerEmbedContacts(workspaceId, token);
    } finally {
      setTimeout(() => setIndexing(false), 3000);
    }
  }, [workspaceId, token, indexing]);

  const filtered = useMemo(() => {
    return contacts.filter((c) => {
      const matchSearch =
        !search ||
        c.name.toLowerCase().includes(search.toLowerCase()) ||
        c.company.toLowerCase().includes(search.toLowerCase()) ||
        c.email.toLowerCase().includes(search.toLowerCase());
      const matchStatus = filterStatus === "all" || c.status === filterStatus;
      const matchScore = filterScore === "all" || c.mlScore.label === filterScore;
      return matchSearch && matchStatus && matchScore;
    });
  }, [contacts, search, filterStatus, filterScore]);

  return (
    <div className="flex flex-col gap-6 p-6">
      <Header
        title="Contacts"
        subtitle={`${contacts.length} total · AI-classified`}
      />

      {/* Stats row */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {(["all", "lead", "prospect", "customer"] as const).map((status) => {
          const count =
            status === "all"
              ? contacts.length
              : contacts.filter((c) => c.status === status).length;
          return (
            <button
              key={status}
              onClick={() => setFilterStatus(status)}
              className={cn(
                "rounded-xl border px-4 py-3 text-left transition-all duration-200 cursor-pointer focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 focus:ring-offset-zinc-950",
                filterStatus === status
                  ? "border-indigo-500/40 bg-indigo-600/10"
                  : "border-zinc-800 bg-zinc-900 hover:border-zinc-700"
              )}
            >
              <p className="text-xl font-bold font-mono text-zinc-100">{count}</p>
              <p className="text-xs text-zinc-500 mt-0.5 capitalize">{status === "all" ? "Total" : status + "s"}</p>
            </button>
          );
        })}
      </div>

      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-52 max-w-sm">
          {semanticLoading ? (
            <Loader2 className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-indigo-400 animate-spin" />
          ) : semanticMode ? (
            <Sparkles className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-indigo-400" aria-hidden="true" />
          ) : (
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-zinc-500" aria-hidden="true" />
          )}
          <input
            type="search"
            placeholder={semanticMode ? "Semantic search: e.g. 'fintech exec with funding needs'…" : "Search by name, company, email…"}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className={cn(
              "w-full rounded-xl border bg-zinc-900 py-2 pl-9 pr-4 text-sm text-zinc-300 placeholder-zinc-600 outline-none transition-all duration-200",
              semanticMode
                ? "border-indigo-500/50 focus:border-indigo-400/70"
                : "border-zinc-800 focus:border-indigo-500/50 focus:shadow-glow-sm"
            )}
            aria-label="Search contacts"
          />
        </div>

        {/* Semantic mode toggle */}
        <button
          onClick={() => { setSemanticMode((v) => !v); setSearch(""); setSemanticResults([]); }}
          className={cn(
            "flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-medium transition-all duration-200 cursor-pointer",
            semanticMode
              ? "border-indigo-500/40 bg-indigo-600/10 text-indigo-400"
              : "border-zinc-800 bg-zinc-900 text-zinc-500 hover:border-zinc-700 hover:text-zinc-300"
          )}
          title="Toggle semantic (vector) search"
        >
          <Sparkles className="h-3 w-3" />
          AI Search
        </button>

        {/* Score filter — hidden in semantic mode */}
        {!semanticMode && (
          <div className="flex items-center gap-1">
            <Filter className="h-3.5 w-3.5 text-zinc-500" aria-hidden="true" />
            {(["all", "hot", "warm", "cold"] as const).map((score) => (
              <button
                key={score}
                onClick={() => setFilterScore(score)}
                className={cn(
                  "rounded-lg border px-3 py-1.5 text-xs font-medium transition-all duration-200 cursor-pointer",
                  filterScore === score
                    ? score === "hot"
                      ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-400"
                      : score === "warm"
                      ? "border-amber-500/40 bg-amber-500/10 text-amber-400"
                      : score === "cold"
                      ? "border-zinc-600 bg-zinc-700 text-zinc-300"
                      : "border-indigo-500/40 bg-indigo-600/10 text-indigo-400"
                    : "border-zinc-800 bg-zinc-900 text-zinc-500 hover:border-zinc-700 hover:text-zinc-300"
                )}
              >
                {score === "all" ? "All" : score.charAt(0).toUpperCase() + score.slice(1)}
              </button>
            ))}
          </div>
        )}

        {/* Index contacts button — only when semantic mode and authed */}
        {semanticMode && workspaceId && token && (
          <button
            onClick={handleIndex}
            disabled={indexing}
            className={cn(
              "flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-medium transition-all duration-200 cursor-pointer",
              indexing
                ? "border-zinc-700 text-zinc-600 cursor-not-allowed"
                : "border-zinc-700 bg-zinc-900 text-zinc-400 hover:border-indigo-500/40 hover:text-indigo-400"
            )}
            title="Build semantic embeddings for all contacts"
          >
            {indexing ? <Loader2 className="h-3 w-3 animate-spin" /> : <Zap className="h-3 w-3" />}
            {indexing ? "Indexing…" : "Index Contacts"}
          </button>
        )}

        <Button variant="cta" size="sm" className="ml-auto" onClick={() => setNewContactOpen(true)}>
          <UserPlus className="h-3.5 w-3.5" aria-hidden="true" />
          Add Contact
        </Button>
      </div>

      {/* Table */}
      <Card className="overflow-hidden p-0">
        <div className="overflow-x-auto">
          <table className="w-full" role="table" aria-label="Contacts table">
            <thead>
              <tr className="border-b border-zinc-800">
                <th scope="col" className="pl-4 py-3 w-8">
                  <button
                    onClick={() => handleSelectAll(filtered)}
                    className="text-zinc-500 hover:text-indigo-400 transition-colors"
                    aria-label="Select all"
                  >
                    {selectedIds.size > 0 && selectedIds.size === filtered.length
                      ? <CheckSquare className="h-4 w-4 text-indigo-400" />
                      : <Square className="h-4 w-4" />}
                  </button>
                </th>
                <th scope="col" className="px-4 py-3 text-left text-xs font-semibold text-zinc-500 uppercase tracking-wider">
                  Contact
                </th>
                <th scope="col" className="px-4 py-3 text-left text-xs font-semibold text-zinc-500 uppercase tracking-wider hidden md:table-cell">
                  Company
                </th>
                <th scope="col" className="px-4 py-3 text-left text-xs font-semibold text-zinc-500 uppercase tracking-wider hidden sm:table-cell">
                  Status
                </th>
                <th scope="col" className="px-4 py-3 text-left text-xs font-semibold text-zinc-500 uppercase tracking-wider hidden lg:table-cell">
                  <div className="flex items-center gap-1.5">
                    <Brain className="h-3.5 w-3.5 text-indigo-400" aria-hidden="true" />
                    ML Score
                  </div>
                </th>
                <th scope="col" className="px-4 py-3 text-left text-xs font-semibold text-zinc-500 uppercase tracking-wider hidden xl:table-cell">
                  <div className="flex items-center gap-1.5">
                    <Sparkles className="h-3.5 w-3.5 text-indigo-400" aria-hidden="true" />
                    Semantic Tags
                  </div>
                </th>
                <th scope="col" className="px-4 py-3 text-right text-xs font-semibold text-zinc-500 uppercase tracking-wider hidden md:table-cell">
                  Revenue
                </th>
                <th scope="col" className="px-4 py-3 text-right text-xs font-semibold text-zinc-500 uppercase tracking-wider">
                  {semanticMode ? "Match" : "Activity"}
                </th>
              </tr>
            </thead>
            <tbody>
              {semanticMode ? (
                !search.trim() ? (
                  <tr>
                    <td colSpan={8} className="px-4 py-12 text-center text-sm text-zinc-500">
                      <Sparkles className="h-5 w-5 text-indigo-500 mx-auto mb-2" />
                      Type a natural language query to search semantically.
                    </td>
                  </tr>
                ) : semanticLoading ? (
                  <tr>
                    <td colSpan={8} className="px-4 py-10 text-center">
                      <Loader2 className="h-5 w-5 text-indigo-400 mx-auto animate-spin" />
                    </td>
                  </tr>
                ) : semanticResults.length > 0 ? (
                  semanticResults.map((r) => {
                    const contact: Contact = {
                      id: r.id,
                      name: r.name ?? "Unknown",
                      email: r.email ?? "",
                      company: r.company ?? "",
                      role: r.role ?? "",
                      avatar: (r.name ?? "?").slice(0, 2).toUpperCase(),
                      status: (r.status as ContactStatus) || "lead",
                      mlScore: {
                        value: (r.ml_score as Record<string, number>)?.value ?? 50,
                        label: ((r.ml_score as Record<string, string>)?.label ?? "warm") as LeadScore,
                        trend: ((r.ml_score as Record<string, string>)?.trend ?? "stable") as "up" | "down" | "stable",
                        signals: [],
                      },
                      semanticTags: [],
                      revenue: r.revenue,
                      deals: r.deal_count,
                      lastActivity: "—",
                      createdAt: new Date().toISOString(),
                    };
                    return (
                      <ContactRow
                        key={r.id}
                        contact={contact}
                        onClick={() => setSelected(contact)}
                        similarity={r.similarity}
                        selected={selectedIds.has(r.id)}
                        onSelect={handleSelect}
                      />
                    );
                  })
                ) : (
                  <tr>
                    <td colSpan={8} className="px-4 py-12 text-center text-sm text-zinc-500">
                      No semantic matches found. Try indexing contacts first.
                    </td>
                  </tr>
                )
              ) : filtered.length > 0 ? (
                filtered.map((contact) => (
                  <ContactRow
                    key={contact.id}
                    contact={contact}
                    onClick={() => setSelected(contact)}
                    selected={selectedIds.has(contact.id)}
                    onSelect={handleSelect}
                  />
                ))
              ) : (
                <tr>
                  <td colSpan={8} className="px-4 py-12 text-center text-sm text-zinc-500">
                    No contacts match your filters.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        <div className="flex items-center justify-between border-t border-zinc-800 px-4 py-3">
          <p className="text-xs text-zinc-500 font-mono">
            {semanticMode
              ? semanticResults.length > 0
                ? `${semanticResults.length} semantic matches`
                : "Semantic search active"
              : `${filtered.length} of ${contacts.length} contacts`}
          </p>
          <div className="flex items-center gap-2">
            {semanticMode ? (
              <>
                <Sparkles className="h-3.5 w-3.5 text-indigo-400" aria-hidden="true" />
                <span className="text-xs text-indigo-400">Vector similarity search</span>
              </>
            ) : (
              <>
                <SlidersHorizontal className="h-3.5 w-3.5 text-zinc-500" aria-hidden="true" />
                <span className="text-xs text-zinc-500">AI-sorted by ML score</span>
              </>
            )}
          </div>
        </div>
      </Card>

      {/* Bulk action bar */}
      {selectedIds.size > 0 && (
        <BulkActionBar
          count={selectedIds.size}
          onStatusChange={handleBulkStatus}
          onEnrich={handleBulkEnrich}
          onClear={() => setSelectedIds(new Set())}
          busy={bulkBusy}
        />
      )}

      {/* Contact drawer overlay */}
      {selected && (
        <>
          <div
            className="fixed inset-0 bg-black/50 z-30"
            onClick={() => setSelected(null)}
            aria-hidden="true"
          />
          <ContactDrawer contact={selected} onClose={() => setSelected(null)} workspaceId={workspaceId} token={token} hasGmailConnector={hasGmailConnector} />
        </>
      )}

      {/* New Contact Modal */}
      {newContactOpen && (
        <NewContactModal
          onClose={() => setNewContactOpen(false)}
          onCreate={async (payload) => {
            await createContact(payload as Partial<Contact>);
            setNewContactOpen(false);
          }}
        />
      )}
    </div>
  );
}
