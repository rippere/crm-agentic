"use client";

import { useState, useEffect, useCallback } from "react";
import Header from "@/components/layout/Header";
import Card from "@/components/ui/Card";
import Badge from "@/components/ui/Badge";
import { apiClient } from "@/lib/api-client";
import { createBrowserClient } from "@/lib/supabase";
import { cn } from "@/lib/utils";
import {
  Activity, CheckCircle, AlertTriangle, Info, Loader2,
  Mail, Users, BarChart3, Bot, Trash2, Pencil,
} from "lucide-react";

interface ActivityEvent {
  id: string;
  type: string | null;
  agent_name: string | null;
  description: string | null;
  meta: string | null;
  severity: string;
  created_at: string;
}

const PAGE_SIZE = 20;

const EVENT_TYPES = [
  { value: "all", label: "All" },
  { value: "contact_created", label: "Contact Created" },
  { value: "contact_updated", label: "Contact Updated" },
  { value: "contact_deleted", label: "Contact Deleted" },
  { value: "deal_moved", label: "Deal Moved" },
  { value: "email_sent", label: "Email Sent" },
  { value: "agent_run", label: "Agent Run" },
];

const severityBadge: Record<string, { variant: "emerald" | "amber" | "indigo" | "rose" | "zinc"; icon: React.ReactNode }> = {
  success: { variant: "emerald", icon: <CheckCircle className="h-3 w-3" /> },
  warning: { variant: "amber",   icon: <AlertTriangle className="h-3 w-3" /> },
  info:    { variant: "indigo",  icon: <Info className="h-3 w-3" /> },
  error:   { variant: "rose",    icon: <AlertTriangle className="h-3 w-3" /> },
};

const typeIcon: Record<string, React.ReactNode> = {
  contact_created: <Users className="h-3.5 w-3.5 text-indigo-400" />,
  contact_updated: <Pencil className="h-3.5 w-3.5 text-amber-400" />,
  contact_deleted: <Trash2 className="h-3.5 w-3.5 text-rose-400" />,
  deal_moved:      <BarChart3 className="h-3.5 w-3.5 text-indigo-400" />,
  email_sent:      <Mail className="h-3.5 w-3.5 text-emerald-400" />,
  agent_run:       <Bot className="h-3.5 w-3.5 text-violet-400" />,
};

function formatRelative(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "Just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  if (days < 7) return `${days}d ago`;
  return new Date(dateStr).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

function EventRow({ event }: { event: ActivityEvent }) {
  const sev = severityBadge[event.severity] ?? severityBadge.info;
  const icon = (event.type && typeIcon[event.type]) ?? <Activity className="h-3.5 w-3.5 text-zinc-500" />;

  return (
    <div className="flex items-start gap-3 py-3 px-4 border-b border-zinc-800/60 last:border-0 hover:bg-zinc-800/20 transition-colors">
      <div className="mt-0.5 h-7 w-7 rounded-lg bg-zinc-800 flex items-center justify-center flex-shrink-0">
        {icon}
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex flex-wrap items-center gap-2 mb-0.5">
          <Badge variant={sev.variant} size="sm" className="gap-1">
            {sev.icon}
            {event.severity}
          </Badge>
          {event.type && (
            <span className="text-[10px] font-mono text-zinc-500 uppercase tracking-wider">
              {event.type.replace(/_/g, " ")}
            </span>
          )}
          {event.agent_name && (
            <span className="text-[10px] text-zinc-600">
              by {event.agent_name}
            </span>
          )}
        </div>
        <p className="text-sm text-zinc-200">{event.description ?? "—"}</p>
      </div>
      <time
        dateTime={event.created_at}
        className="text-[11px] text-zinc-500 font-mono flex-shrink-0 mt-0.5"
        title={new Date(event.created_at).toLocaleString()}
      >
        {formatRelative(event.created_at)}
      </time>
    </div>
  );
}

export default function ActivityPage() {
  const [events, setEvents] = useState<ActivityEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(true);
  const [token, setToken] = useState<string | null>(null);
  const [workspaceId, setWorkspaceId] = useState<string | null>(null);
  const [typeFilter, setTypeFilter] = useState("all");

  useEffect(() => {
    if (process.env.NEXT_PUBLIC_DEMO_MODE === "true") {
      setToken("demo-token");
      setWorkspaceId("demo-workspace-1");
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

  const loadEvents = useCallback(async (reset = false) => {
    if (!token || !workspaceId) return;
    const offset = reset ? 0 : events.length;
    const busy = reset ? setLoading : setLoadingMore;
    busy(true);
    try {
      const data = await apiClient.listActivity(workspaceId, token, {
        limit: PAGE_SIZE,
        offset,
        eventType: typeFilter !== "all" ? typeFilter : undefined,
      });
      if (reset) {
        setEvents(data);
      } else {
        setEvents((prev) => [...prev, ...data]);
      }
      setHasMore(data.length === PAGE_SIZE);
    } catch {
      if (reset) setEvents([]);
    } finally {
      busy(false);
    }
  }, [token, workspaceId, typeFilter, events.length]);

  // Initial load and filter change
  useEffect(() => {
    if (!token || !workspaceId) return;
    const doLoad = async () => {
      setLoading(true);
      try {
        const data = await apiClient.listActivity(workspaceId, token, {
          limit: PAGE_SIZE,
          offset: 0,
          eventType: typeFilter !== "all" ? typeFilter : undefined,
        });
        setEvents(data);
        setHasMore(data.length === PAGE_SIZE);
      } catch {
        setEvents([]);
      } finally {
        setLoading(false);
      }
    };
    doLoad();
  }, [token, workspaceId, typeFilter]);

  const handleLoadMore = useCallback(async () => {
    if (!token || !workspaceId || loadingMore) return;
    setLoadingMore(true);
    try {
      const data = await apiClient.listActivity(workspaceId, token, {
        limit: PAGE_SIZE,
        offset: events.length,
        eventType: typeFilter !== "all" ? typeFilter : undefined,
      });
      setEvents((prev) => [...prev, ...data]);
      setHasMore(data.length === PAGE_SIZE);
    } catch { /* silent */ }
    finally { setLoadingMore(false); }
  }, [token, workspaceId, events.length, typeFilter, loadingMore]);

  const typeCount: Record<string, number> = {};
  for (const e of events) {
    if (e.type) typeCount[e.type] = (typeCount[e.type] ?? 0) + 1;
  }

  return (
    <div className="flex flex-col gap-6 p-4 md:p-6">
      <Header
        title="Activity Log"
        subtitle={`Full workspace timeline · ${events.length} event${events.length !== 1 ? "s" : ""} loaded`}
      />

      {/* Type filter chips */}
      <div className="flex flex-wrap gap-2">
        {EVENT_TYPES.map((t) => (
          <button
            key={t.value}
            onClick={() => setTypeFilter(t.value)}
            className={cn(
              "flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium transition-all cursor-pointer",
              typeFilter === t.value
                ? "border-indigo-500/40 bg-indigo-600/10 text-indigo-400"
                : "border-zinc-800 bg-zinc-900 text-zinc-500 hover:border-zinc-700 hover:text-zinc-300"
            )}
          >
            {t.value !== "all" && typeIcon[t.value] && (
              <span className="opacity-70">{typeIcon[t.value]}</span>
            )}
            {t.label}
            {t.value !== "all" && typeCount[t.value] ? (
              <span className={cn(
                "rounded-full px-1.5 py-0.5 text-[10px] font-mono",
                typeFilter === t.value ? "bg-indigo-500/20 text-indigo-300" : "bg-zinc-800 text-zinc-500"
              )}>
                {typeCount[t.value]}
              </span>
            ) : null}
          </button>
        ))}
      </div>

      <Card className="p-0 overflow-hidden">
        {loading ? (
          <div className="space-y-0">
            {Array.from({ length: 8 }).map((_, i) => (
              <div key={i} className="flex items-start gap-3 py-3 px-4 border-b border-zinc-800/60">
                <div className="h-7 w-7 rounded-lg bg-zinc-800 animate-pulse flex-shrink-0" />
                <div className="flex-1 space-y-1.5">
                  <div className="h-3 w-24 rounded bg-zinc-800 animate-pulse" />
                  <div className="h-4 w-3/4 rounded bg-zinc-800 animate-pulse" />
                </div>
                <div className="h-3 w-16 rounded bg-zinc-800 animate-pulse flex-shrink-0" />
              </div>
            ))}
          </div>
        ) : events.length === 0 ? (
          <div className="flex flex-col items-center gap-3 py-16 text-center px-4">
            <Activity className="h-10 w-10 text-zinc-700" />
            <p className="text-sm text-zinc-400 font-medium">No activity yet</p>
            <p className="text-xs text-zinc-600 max-w-xs">
              {typeFilter !== "all"
                ? `No events of type "${typeFilter.replace(/_/g, " ")}" found.`
                : "Workspace activity events will appear here as agents run and contacts are updated."}
            </p>
          </div>
        ) : (
          <div>
            {events.map((event) => (
              <EventRow key={event.id} event={event} />
            ))}
          </div>
        )}

        {/* Load more */}
        {!loading && hasMore && (
          <div className="border-t border-zinc-800 px-4 py-3 flex justify-center">
            <button
              onClick={handleLoadMore}
              disabled={loadingMore}
              className="flex items-center gap-2 rounded-lg border border-zinc-700 px-4 py-2 text-xs font-medium text-zinc-400 hover:border-zinc-600 hover:text-zinc-200 disabled:opacity-50 transition"
            >
              {loadingMore ? (
                <><Loader2 className="h-3.5 w-3.5 animate-spin" /> Loading…</>
              ) : (
                "Load more events"
              )}
            </button>
          </div>
        )}

        {!loading && !hasMore && events.length > 0 && (
          <div className="border-t border-zinc-800 px-4 py-3 text-center">
            <p className="text-xs text-zinc-600 font-mono">All {events.length} events loaded</p>
          </div>
        )}
      </Card>
    </div>
  );
}
