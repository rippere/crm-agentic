"use client";

import { useState, useEffect, useCallback } from "react";
import { createBrowserClient } from "@/lib/supabase";
import type { ActivityEvent } from "@/lib/types";
import type { ActivityEventRow } from "@/lib/supabase";
import { isDemoMode } from "@/lib/demo-mode";
import { demoActivity } from "@/lib/demo-data";

function rowToEvent(row: ActivityEventRow): ActivityEvent {
  // Format relative timestamp
  const created = new Date(row.created_at);
  const diffMs = Date.now() - created.getTime();
  const diffMin = Math.floor(diffMs / 60000);
  const diffHr = Math.floor(diffMin / 60);

  let timestamp: string;
  if (diffMin < 1) timestamp = "Just now";
  else if (diffMin < 60) timestamp = `${diffMin} min ago`;
  else if (diffHr < 24) timestamp = `${diffHr} hour${diffHr > 1 ? "s" : ""} ago`;
  else timestamp = `${Math.floor(diffHr / 24)} day${Math.floor(diffHr / 24) > 1 ? "s" : ""} ago`;

  return {
    id: row.id,
    type: row.type as ActivityEvent["type"],
    agentName: row.agent_name,
    description: row.description,
    meta: row.meta || undefined,
    timestamp,
    severity: row.severity,
  };
}

export function useActivity(limit = 50) {
  const [events, setEvents] = useState<ActivityEvent[]>(
    isDemoMode ? demoActivity.slice(0, limit) : []
  );
  const [loading, setLoading] = useState(!isDemoMode);
  const [error, setError] = useState<string | null>(null);

  const fetchActivity = useCallback(async () => {
    if (isDemoMode) {
      setEvents(demoActivity.slice(0, limit));
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const supabase = createBrowserClient();
      const { data: { user } } = await supabase.auth.getUser();
      const workspaceId = user?.user_metadata?.workspace_id as string | undefined;
      if (!workspaceId) {
        setError("No workspace found");
        return;
      }

      const { data, error: fetchError } = await supabase
        .from("activity_events")
        .select("*")
        .eq("workspace_id", workspaceId)
        .order("created_at", { ascending: false })
        .limit(limit);

      if (fetchError) throw new Error(fetchError.message);
      setEvents((data ?? []).map((r: ActivityEventRow) => rowToEvent(r)));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load activity");
    } finally {
      setLoading(false);
    }
  }, [limit]);

  useEffect(() => {
    if (isDemoMode) return;

    let workspaceId: string | null = null;
    let channelCleanup: (() => void) | null = null;

    async function init() {
      await fetchActivity();

      const supabase = createBrowserClient();
      const { data: { user } } = await supabase.auth.getUser();
      workspaceId = user?.user_metadata?.workspace_id ?? null;
      if (!workspaceId) return;

      // Subscribe to Realtime INSERT events for this workspace
      const channel = supabase
        .channel("activity-realtime")
        .on(
          "postgres_changes",
          {
            event: "INSERT",
            schema: "public",
            table: "activity_events",
            filter: `workspace_id=eq.${workspaceId}`,
          },
          (payload) => {
            setEvents((prev) => [rowToEvent(payload.new as ActivityEventRow), ...prev]);
          }
        )
        .subscribe();

      channelCleanup = () => {
        supabase.removeChannel(channel);
      };
    }

    init();

    return () => {
      channelCleanup?.();
    };
  }, [fetchActivity]);

  return { events, loading, error, refetch: fetchActivity };
}
