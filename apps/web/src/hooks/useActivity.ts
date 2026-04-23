"use client";

import { useState, useEffect, useCallback } from "react";
import type { ActivityEvent } from "@/lib/types";
import type { ActivityEventRow } from "@/lib/supabase";

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
  const [events, setEvents] = useState<ActivityEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchActivity = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/api/activity?limit=${limit}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: ActivityEventRow[] = await res.json();
      setEvents(data.map(rowToEvent));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load activity");
    } finally {
      setLoading(false);
    }
  }, [limit]);

  useEffect(() => {
    fetchActivity();
    // Poll every 30 seconds for new events
    const interval = setInterval(fetchActivity, 30_000);
    return () => clearInterval(interval);
  }, [fetchActivity]);

  return { events, loading, error, refetch: fetchActivity };
}
