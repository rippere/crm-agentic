"use client";

import { useState, useEffect, useMemo } from "react";
import { createBrowserClient } from "@/lib/supabase";
import Header from "@/components/layout/Header";
import Card from "@/components/ui/Card";
import Badge from "@/components/ui/Badge";
import Avatar from "@/components/ui/Avatar";
import { apiClient } from "@/lib/api-client";
import { Search, Mail, X, CheckCircle, Clock, Brain, ListTodo } from "lucide-react";

interface Message {
  id: string;
  subject: string | null;
  sender_email: string | null;
  received_at: string | null;
  body_plain: string | null;
  processed: boolean;
  contact_id: string | null;
  clarity_score?: { score: number; rationale: string } | null;
  tasks?: Array<{ id: string; title: string; status: string }>;
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

function senderInitials(email: string | null): string {
  if (!email) return "?";
  const name = email.split("@")[0].replace(/[._-]/g, " ");
  return name
    .split(" ")
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() ?? "")
    .join("");
}

function ClarityBadge({ score }: { score: number }) {
  const variant = score >= 70 ? "emerald" : score >= 40 ? "amber" : "rose";
  return (
    <Badge variant={variant} size="sm">
      <Brain className="h-2.5 w-2.5 mr-1" />
      {score}
    </Badge>
  );
}

function MessageSkeleton() {
  return (
    <div className="flex items-center gap-3 px-4 py-3 border-b border-zinc-800 animate-pulse">
      <div className="h-8 w-8 rounded-full bg-zinc-800 flex-shrink-0" />
      <div className="flex-1 space-y-1.5">
        <div className="h-3 w-32 rounded bg-zinc-800" />
        <div className="h-2.5 w-48 rounded bg-zinc-800" />
      </div>
      <div className="h-2.5 w-12 rounded bg-zinc-800" />
    </div>
  );
}

function MessageDrawer({ message, onClose }: { message: Message; onClose: () => void }) {
  return (
    <aside
      className="fixed right-0 top-0 h-full w-[520px] border-l border-zinc-800 bg-zinc-950 z-40 overflow-y-auto"
      aria-label="Message details"
    >
      <div className="sticky top-0 flex items-center justify-between border-b border-zinc-800 bg-zinc-950/90 backdrop-blur px-5 py-4">
        <p className="text-sm font-semibold text-zinc-100 truncate pr-4">{message.subject ?? "(No subject)"}</p>
        <button
          onClick={onClose}
          className="text-zinc-400 hover:text-zinc-100 transition-colors cursor-pointer flex-shrink-0"
          aria-label="Close"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      <div className="p-5 space-y-5">
        {/* Meta */}
        <div className="flex items-center gap-3">
          <Avatar initials={senderInitials(message.sender_email)} size="sm" />
          <div className="min-w-0">
            <p className="text-sm font-medium text-zinc-200 truncate">{message.sender_email ?? "Unknown"}</p>
            <p className="text-xs text-zinc-500 font-mono">{formatRelative(message.received_at)}</p>
          </div>
          {message.processed && (
            <Badge variant="emerald" size="sm" className="ml-auto flex-shrink-0">
              <CheckCircle className="h-2.5 w-2.5 mr-1" />
              Processed
            </Badge>
          )}
        </div>

        {/* Clarity score */}
        {message.clarity_score && (
          <Card className="space-y-2">
            <div className="flex items-center gap-2">
              <Brain className="h-4 w-4 text-indigo-400" />
              <p className="text-xs font-semibold text-zinc-300">Clarity Score</p>
              <ClarityBadge score={message.clarity_score.score} />
            </div>
            {message.clarity_score.rationale && (
              <p className="text-xs text-zinc-400 leading-relaxed">{message.clarity_score.rationale}</p>
            )}
          </Card>
        )}

        {/* Linked contact */}
        {message.contact_id && (
          <div className="flex items-center gap-2 text-xs text-zinc-400">
            <CheckCircle className="h-3.5 w-3.5 text-emerald-400" />
            Linked to contact
          </div>
        )}

        {/* Extracted tasks */}
        {message.tasks && message.tasks.length > 0 && (
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <ListTodo className="h-4 w-4 text-indigo-400" />
              <p className="text-xs font-semibold text-zinc-300">Extracted Tasks ({message.tasks.length})</p>
            </div>
            {message.tasks.map((task) => (
              <div key={task.id} className="flex items-start gap-2 rounded-lg border border-zinc-800 bg-zinc-900 px-3 py-2">
                <span className="h-1.5 w-1.5 rounded-full bg-indigo-400 mt-1.5 flex-shrink-0" />
                <p className="text-xs text-zinc-300 leading-snug">{task.title}</p>
                <Badge variant="zinc" size="sm" className="ml-auto flex-shrink-0">{task.status}</Badge>
              </div>
            ))}
          </div>
        )}

        {/* Body */}
        <div className="space-y-2">
          <p className="text-[10px] text-zinc-500 font-mono uppercase tracking-widest">Message Body</p>
          <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-4 max-h-96 overflow-y-auto">
            <pre className="text-xs text-zinc-300 whitespace-pre-wrap font-sans leading-relaxed">
              {message.body_plain?.trim() || "(Empty body)"}
            </pre>
          </div>
        </div>
      </div>
    </aside>
  );
}

export default function InboxPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<Message | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [workspaceId, setWorkspaceId] = useState<string | null>(null);

  const isDemoMode = process.env.NEXT_PUBLIC_DEMO_MODE === 'true';

  useEffect(() => {
    if (isDemoMode) {
      apiClient.getMessages('demo-workspace-1', 'demo-token')
        .then((data) => setMessages(Array.isArray(data) ? data : []))
        .catch(() => setMessages([]))
        .finally(() => setLoading(false));
      return;
    }
    const supabase = createBrowserClient();
    supabase.auth.getSession().then(({ data: { session } }) => {
      if (session) {
        setToken(session.access_token);
        setWorkspaceId(session.user.user_metadata?.workspace_id ?? null);
      }
    });
  }, [isDemoMode]);

  useEffect(() => {
    if (isDemoMode) return; // already loaded above
    if (!workspaceId || !token) return;
    apiClient
      .getMessages(workspaceId, token)
      .then((data) => setMessages(Array.isArray(data) ? data : []))
      .catch(() => setMessages([]))
      .finally(() => setLoading(false));
  }, [workspaceId, token, isDemoMode]);

  const filtered = useMemo(() => {
    if (!search) return messages;
    const q = search.toLowerCase();
    return messages.filter(
      (m) =>
        m.sender_email?.toLowerCase().includes(q) ||
        m.subject?.toLowerCase().includes(q)
    );
  }, [messages, search]);

  return (
    <div className="flex flex-col gap-6 p-6">
      <Header
        title="Inbox"
        subtitle={`${messages.length} messages ingested`}
      />

      {/* Search */}
      <div className="relative max-w-sm">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-zinc-500" />
        <input
          type="search"
          placeholder="Search by sender or subject…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full rounded-xl border border-zinc-800 bg-zinc-900 py-2 pl-9 pr-4 text-sm text-zinc-300 placeholder-zinc-600 outline-none focus:border-indigo-500/50 transition-all"
        />
      </div>

      {/* Message list */}
      <Card className="overflow-hidden p-0">
        {loading ? (
          <>
            {[1, 2, 3, 4, 5].map((i) => <MessageSkeleton key={i} />)}
          </>
        ) : filtered.length === 0 ? (
          <div className="flex flex-col items-center gap-4 py-16 px-4 text-center">
            <div className="flex h-14 w-14 items-center justify-center rounded-2xl border border-zinc-800 bg-zinc-900">
              <Mail className="h-6 w-6 text-zinc-600" />
            </div>
            <div>
              <p className="text-sm font-medium text-zinc-300">No messages yet</p>
              <p className="text-xs text-zinc-500 mt-1">Connect Gmail to start ingesting.</p>
            </div>
          </div>
        ) : (
          <div className="divide-y divide-zinc-800">
            {filtered.map((msg) => (
              <button
                key={msg.id}
                className="w-full flex items-center gap-3 px-4 py-3 hover:bg-zinc-800/40 transition-colors text-left cursor-pointer"
                onClick={() => setSelected(msg)}
              >
                <Avatar initials={senderInitials(msg.sender_email)} size="sm" />
                <div className="flex-1 min-w-0">
                  <p className="text-xs text-zinc-400 truncate">{msg.sender_email ?? "Unknown"}</p>
                  <p className="text-sm text-zinc-200 truncate font-medium">{msg.subject ?? "(No subject)"}</p>
                </div>
                <div className="flex items-center gap-2 flex-shrink-0">
                  {msg.clarity_score && <ClarityBadge score={msg.clarity_score.score} />}
                  {msg.processed && (
                    <CheckCircle className="h-3.5 w-3.5 text-emerald-500" aria-label="Processed" />
                  )}
                  <span className="text-[10px] text-zinc-500 font-mono">
                    {formatRelative(msg.received_at)}
                  </span>
                </div>
              </button>
            ))}
          </div>
        )}
      </Card>

      {/* Drawer */}
      {selected && (
        <>
          <div
            className="fixed inset-0 bg-black/50 z-30"
            onClick={() => setSelected(null)}
            aria-hidden="true"
          />
          <MessageDrawer message={selected} onClose={() => setSelected(null)} />
        </>
      )}
    </div>
  );
}
