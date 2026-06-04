"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import Header from "@/components/layout/Header";
import Card from "@/components/ui/Card";
import { cn } from "@/lib/utils";
import { apiClient } from "@/lib/api-client";
import { createBrowserClient } from "@/lib/supabase";
import {
  Activity, CheckCircle, AlertTriangle, Info, Loader2, Filter,
} from "lucide-react";

const DEMO_MODE = process.env.NEXT_PUBLIC_DEMO_MODE === "true";
const PAGE_SIZE = 25;

interface ActivityRow {
  id: string;
  type: string | null;
  agent_name: string | null;
  description: string | null;
  meta: string | null;
  severity: string;
  created_at: string;
}

const severityIcon: Record<string, React.ReactNode> = {
  success: <CheckCircle className="h-4 w-4 flex-shrink-0 text-emerald-400" />,
  warning: <AlertTriangle className="h-4 w-4 flex-shrink-0 text-amber-400" />,
  info: <Info className="h-4 w-4 flex-shrink-0 text-indigo-400" />,
};

// Curated list of common event types for the filter bar. "all" clears the filter.
const TYPE_FILTERS: { value: string; label: string }[] = [
  { value: "all", label: "All" },
  { value: "contact_scored", label: "Scored" },
  { value: "tag_applied", label: "Tagged" },
  { value: "email_sent", label: "Emails" },
  { value: "deal_moved", label: "Deals" },
  { value: "deal_deleted", label: "Deletions" },
  { value: "contact_deleted", label: "Contact Removals" },
  { value: "call_summarized", label: "Calls" },
  { value: "agent_run", label: "Agent Runs" },
];

function formatTimestamp(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "Just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  if (days < 7) return `${days}d ago`;
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

export default function ActivityPage() {
  const [token, setToken] = useState<string | null>(null);
  const [workspaceId, setWorkspaceId] = useState<string | null>(null);
  const [authReady, setAuthReady] = useState(false);
  const [events, setEvents] = useState<ActivityRow[]>([]);
  const [typeFilter, setTypeFilter] = useState<string>("all");
  const [loading, setLoading] = useState(false);
  const [hasMore, setHasMore] = useState(true);
  const offsetRef = useRef(0);
  const sentinelRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (DEMO_MODE) {
      setToken("demo-token");
      setWorkspaceId("demo-workspace-1");
      setAuthReady(true);
      return;
    }
    const supabase = createBrowserClient();
    supabase.auth.getSession().then(({ data: { session } }) => {
      if (session) {
        setToken(session.access_token);
        setWorkspaceId(session.user.user_metadata?.workspace_id ?? null);
      }
      setAuthReady(true);
    });
  }, []);

  const loadMore = useCallback(async () => {
    if (!workspaceId || !token || loading || !hasMore) return;
    setLoading(true);
    try {
      const rows: ActivityRow[] = await apiClient.listActivity(workspaceId, token, {
        limit: PAGE_SIZE,
        offset: offsetRef.current,
        type: typeFilter === "all" ? undefined : typeFilter,
      });
      const batch = Array.isArray(rows) ? rows : [];
      offsetRef.current += batch.length;
      setEvents((prev) => [...prev, ...batch]);
      if (batch.length < PAGE_SIZE) setHasMore(false);
    } catch {
      setHasMore(false);
    } finally {
      setLoading(false);
    }
  }, [workspaceId, token, loading, hasMore, typeFilter]);

  // Reset and reload whenever the filter (or auth) changes
  useEffect(() => {
    if (!authReady || !workspaceId || !token) return;
    offsetRef.current = 0;
    setEvents([]);
    setHasMore(true);
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const rows: ActivityRow[] = await apiClient.listActivity(workspaceId, token, {
          limit: PAGE_SIZE,
          offset: 0,
          type: typeFilter === "all" ? undefined : typeFilter,
        });
        if (cancelled) return;
        const batch = Array.isArray(rows) ? rows : [];
        offsetRef.current = batch.length;
        setEvents(batch);
        if (batch.length < PAGE_SIZE) setHasMore(false);
      } catch {
        if (!cancelled) setHasMore(false);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [authReady, workspaceId, token, typeFilter]);

  // Infinite scroll via IntersectionObserver
  useEffect(() => {
    const node = sentinelRef.current;
    if (!node) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting) loadMore();
      },
      { rootMargin: "200px" }
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [loadMore]);

  return (
    <div className="flex flex-col gap-6 p-4 md:p-6">
      <Header
        title="Activity Log"
        subtitle="Full workspace event history"
      />

      {/* Type filter bar */}
      <div className="flex flex-wrap items-center gap-2">
        <Filter className="h-3.5 w-3.5 text-zinc-500" aria-hidden="true" />
        {TYPE_FILTERS.map((f) => (
          <button
            key={f.value}
            onClick={() => setTypeFilter(f.value)}
            className={cn(
              "rounded-lg border px-3 py-1.5 text-xs font-medium transition-all duration-200 cursor-pointer",
              typeFilter === f.value
                ? "border-indigo-500/40 bg-indigo-600/10 text-indigo-400"
                : "border-zinc-800 bg-zinc-900 text-zinc-500 hover:border-zinc-700 hover:text-zinc-300"
            )}
          >
            {f.label}
          </button>
        ))}
      </div>

      <Card className="p-0 overflow-hidden">
        <div className="divide-y divide-zinc-800">
          {events.length === 0 && !loading ? (
            <div className="flex flex-col items-center justify-center py-16 text-center">
              <Activity className="h-7 w-7 text-zinc-700 mb-3" aria-hidden="true" />
              <p className="text-sm text-zinc-500">No activity found</p>
              <p className="text-xs text-zinc-600 font-mono mt-1">
                {typeFilter === "all" ? "Events will appear here as agents run" : "No events match this filter"}
              </p>
            </div>
          ) : (
            events.map((event) => (
              <div
                key={event.id}
                className="flex items-start gap-3 px-4 py-3 hover:bg-zinc-800/40 transition-colors duration-150"
              >
                {severityIcon[event.severity] ?? severityIcon.info}
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-zinc-200 leading-snug">
                    {event.agent_name && (
                      <span className="font-medium text-indigo-400">{event.agent_name}</span>
                    )}{" "}
                    {event.description}
                  </p>
                  <div className="flex items-center gap-2 mt-1">
                    {event.type && (
                      <span className="text-[10px] font-mono uppercase tracking-wider text-zinc-600 rounded bg-zinc-800/60 px-1.5 py-0.5">
                        {event.type}
                      </span>
                    )}
                    {event.meta && (
                      <span className="text-[10px] text-zinc-500 font-mono truncate">{event.meta}</span>
                    )}
                  </div>
                </div>
                <span className="text-[10px] text-zinc-600 flex-shrink-0 font-mono whitespace-nowrap pt-0.5">
                  {formatTimestamp(event.created_at)}
                </span>
              </div>
            ))
          )}

          {/* Loading row + infinite-scroll sentinel */}
          {loading && (
            <div className="flex items-center justify-center py-6">
              <Loader2 className="h-5 w-5 text-indigo-400 animate-spin" />
            </div>
          )}
          {hasMore && !loading && <div ref={sentinelRef} className="h-px" aria-hidden="true" />}
          {!hasMore && events.length > 0 && (
            <p className="text-center text-[10px] text-zinc-600 font-mono py-4">End of activity log</p>
          )}
        </div>
      </Card>
    </div>
  );
}
