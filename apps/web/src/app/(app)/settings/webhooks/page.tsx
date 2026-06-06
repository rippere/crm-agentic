"use client";

import { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import Header from "@/components/layout/Header";
import Card from "@/components/ui/Card";
import Badge from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import { createBrowserClient } from "@/lib/supabase";
import { apiClient } from "@/lib/api-client";
import { ArrowLeft, RefreshCw, Webhook, CheckCircle, Clock, AlertCircle } from "lucide-react";
import { cn } from "@/lib/utils";

type WebhookLog = {
  id: string;
  workspace_id: string | null;
  source: string;
  event_type: string;
  status: string;
  payload_summary: string | null;
  job_id: string | null;
  error_detail: string | null;
  created_at: string;
};

type SourceFilter = "all" | "gmail" | "slack";
type StatusFilter = "all" | "received" | "queued" | "error";

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

function StatusIcon({ status }: { status: string }) {
  if (status === "queued") return <CheckCircle className="h-3.5 w-3.5 text-emerald-400" />;
  if (status === "error") return <AlertCircle className="h-3.5 w-3.5 text-rose-400" />;
  return <Clock className="h-3.5 w-3.5 text-zinc-400" />;
}

function StatusBadge({ status }: { status: string }) {
  if (status === "queued") return <Badge variant="emerald" size="sm">queued</Badge>;
  if (status === "error") return <Badge variant="rose" size="sm">error</Badge>;
  return <Badge variant="zinc" size="sm">received</Badge>;
}

function SourceBadge({ source }: { source: string }) {
  if (source === "gmail") return <Badge variant="indigo" size="sm">Gmail</Badge>;
  return <Badge variant="amber" size="sm">Slack</Badge>;
}

const SOURCE_TABS: { value: SourceFilter; label: string }[] = [
  { value: "all", label: "All" },
  { value: "gmail", label: "Gmail" },
  { value: "slack", label: "Slack" },
];

const STATUS_TABS: { value: StatusFilter; label: string }[] = [
  { value: "all", label: "All" },
  { value: "queued", label: "Queued" },
  { value: "received", label: "Received" },
  { value: "error", label: "Error" },
];

export default function WebhookLogsPage() {
  const [logs, setLogs] = useState<WebhookLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [token, setToken] = useState<string | null>(null);
  const [workspaceId, setWorkspaceId] = useState<string | null>(null);
  const [sourceFilter, setSourceFilter] = useState<SourceFilter>("all");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [offset, setOffset] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const LIMIT = 25;

  useEffect(() => {
    const supabase = createBrowserClient();
    supabase.auth.getSession().then(({ data: { session } }) => {
      if (!session) return;
      setToken(session.access_token);
      const wsId = (
        session.user.app_metadata?.workspace_id ??
        session.user.user_metadata?.workspace_id
      ) as string | undefined;
      if (wsId) setWorkspaceId(wsId);
    });
  }, []);

  const fetchLogs = useCallback(
    async (reset = false) => {
      if (!workspaceId || !token) return;
      const currentOffset = reset ? 0 : offset;
      try {
        const data = await apiClient.getWebhookLogs(workspaceId, token, {
          source: sourceFilter !== "all" ? sourceFilter : undefined,
          status: statusFilter !== "all" ? (statusFilter as "received" | "queued" | "error") : undefined,
          limit: LIMIT + 1,
          offset: currentOffset,
        });
        const page = data.slice(0, LIMIT);
        setHasMore(data.length > LIMIT);
        if (reset) {
          setLogs(page);
          setOffset(LIMIT);
        } else {
          setLogs((prev) => [...prev, ...page]);
          setOffset(currentOffset + LIMIT);
        }
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [workspaceId, token, sourceFilter, statusFilter, offset],
  );

  // Initial load + filter changes
  useEffect(() => {
    if (!workspaceId || !token) return;
    setLoading(true);
    setOffset(0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
    fetchLogs(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspaceId, token, sourceFilter, statusFilter]);

  const handleRefresh = async () => {
    setRefreshing(true);
    await fetchLogs(true);
  };

  const handleLoadMore = () => {
    fetchLogs(false);
  };

  return (
    <div className="flex flex-col gap-6 p-4 md:p-6 max-w-4xl">
      <div className="flex items-center gap-3">
        <Link
          href="/settings"
          className="flex items-center gap-1.5 text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          Settings
        </Link>
      </div>

      <Header
        title="Webhook Logs"
        subtitle="Gmail Pub/Sub and Slack Events API delivery history"
      />

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-4">
        <div className="flex items-center gap-1 bg-zinc-900 border border-zinc-800 rounded-lg p-1">
          {SOURCE_TABS.map((tab) => (
            <button
              key={tab.value}
              onClick={() => setSourceFilter(tab.value)}
              className={cn(
                "px-3 py-1 rounded-md text-xs font-medium transition-all",
                sourceFilter === tab.value
                  ? "bg-zinc-700 text-zinc-100"
                  : "text-zinc-500 hover:text-zinc-300",
              )}
            >
              {tab.label}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-1 bg-zinc-900 border border-zinc-800 rounded-lg p-1">
          {STATUS_TABS.map((tab) => (
            <button
              key={tab.value}
              onClick={() => setStatusFilter(tab.value)}
              className={cn(
                "px-3 py-1 rounded-md text-xs font-medium transition-all",
                statusFilter === tab.value
                  ? "bg-zinc-700 text-zinc-100"
                  : "text-zinc-500 hover:text-zinc-300",
              )}
            >
              {tab.label}
            </button>
          ))}
        </div>

        <div className="ml-auto">
          <Button variant="secondary" size="sm" onClick={handleRefresh} disabled={refreshing}>
            <RefreshCw className={cn("h-3.5 w-3.5", refreshing && "animate-spin")} />
            {refreshing ? "Refreshing…" : "Refresh"}
          </Button>
        </div>
      </div>

      {/* Log table */}
      <Card className="p-0 overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center h-40 text-zinc-500 text-sm">
            Loading…
          </div>
        ) : logs.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-40 gap-3">
            <Webhook className="h-8 w-8 text-zinc-700" />
            <p className="text-sm text-zinc-500">No webhook events recorded yet.</p>
            <p className="text-xs text-zinc-600">
              Events appear here after Gmail or Slack webhooks are received.
            </p>
          </div>
        ) : (
          <>
            {/* Header row */}
            <div className="grid grid-cols-[auto_1fr_auto_auto_auto] gap-x-4 px-4 py-2.5 border-b border-zinc-800 bg-zinc-900/50">
              <p className="text-[10px] font-semibold uppercase tracking-wider text-zinc-600">Source</p>
              <p className="text-[10px] font-semibold uppercase tracking-wider text-zinc-600">Event / Summary</p>
              <p className="text-[10px] font-semibold uppercase tracking-wider text-zinc-600">Job ID</p>
              <p className="text-[10px] font-semibold uppercase tracking-wider text-zinc-600">Status</p>
              <p className="text-[10px] font-semibold uppercase tracking-wider text-zinc-600">Time</p>
            </div>

            {logs.map((log) => (
              <div
                key={log.id}
                className="grid grid-cols-[auto_1fr_auto_auto_auto] gap-x-4 items-center px-4 py-3 border-b border-zinc-800/60 last:border-0 hover:bg-zinc-800/30 transition-colors group"
              >
                {/* Source */}
                <div className="flex items-center gap-1.5">
                  <StatusIcon status={log.status} />
                  <SourceBadge source={log.source} />
                </div>

                {/* Event / summary */}
                <div className="min-w-0">
                  <p className="text-xs font-mono text-zinc-300 truncate">{log.event_type}</p>
                  {log.payload_summary && (
                    <p className="text-[11px] text-zinc-500 truncate mt-0.5">{log.payload_summary}</p>
                  )}
                  {log.error_detail && (
                    <p className="text-[11px] text-rose-400 truncate mt-0.5">{log.error_detail}</p>
                  )}
                </div>

                {/* Job ID */}
                <div className="text-right">
                  {log.job_id ? (
                    <span className="font-mono text-[10px] text-zinc-500 group-hover:text-zinc-400">
                      {log.job_id.length > 16 ? `${log.job_id.slice(0, 16)}…` : log.job_id}
                    </span>
                  ) : (
                    <span className="text-[10px] text-zinc-700">—</span>
                  )}
                </div>

                {/* Status */}
                <div>
                  <StatusBadge status={log.status} />
                </div>

                {/* Time */}
                <div className="text-right">
                  <span
                    className="text-[11px] text-zinc-500"
                    title={new Date(log.created_at).toLocaleString()}
                  >
                    {relativeTime(log.created_at)}
                  </span>
                </div>
              </div>
            ))}

            {hasMore && (
              <div className="px-4 py-3 border-t border-zinc-800/60">
                <Button variant="secondary" size="sm" onClick={handleLoadMore} className="w-full">
                  Load more
                </Button>
              </div>
            )}
          </>
        )}
      </Card>

      {/* Info footer */}
      <p className="text-[11px] text-zinc-600 leading-relaxed">
        Logs are written when a Gmail Pub/Sub push notification or Slack Events API call is
        received. <strong className="text-zinc-500">queued</strong> means a Celery ingest task
        was dispatched. <strong className="text-zinc-500">received</strong> means the event was
        acknowledged but no task was enqueued (e.g. url_verification, unknown connector).{" "}
        <strong className="text-zinc-500">error</strong> indicates a delivery or processing failure.
      </p>
    </div>
  );
}
