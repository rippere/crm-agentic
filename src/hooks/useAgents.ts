"use client";

import { useState, useEffect, useCallback } from "react";
import type { Agent } from "@/lib/types";
import type { AgentRow } from "@/lib/supabase";

function rowToAgent(row: AgentRow): Agent {
  return {
    id: row.id,
    name: row.name,
    type: row.type as Agent["type"],
    status: row.status,
    description: row.description,
    model: row.model,
    accuracy: row.accuracy,
    tasksToday: row.tasks_today,
    metrics: row.metrics,
    lastRun: row.last_run,
    workflow: row.workflow,
  };
}

export function useAgents() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchAgents = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/agents");
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: AgentRow[] = await res.json();
      setAgents(data.map(rowToAgent));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load agents");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAgents();
  }, [fetchAgents]);

  const runAgent = async (id: string) => {
    const res = await fetch(`/api/agents/${id}/run`, { method: "POST" });
    if (!res.ok) throw new Error(await res.text());
    await fetchAgents();
    return res.json();
  };

  const updateAgent = async (id: string, payload: { status?: Agent["status"] }) => {
    const res = await fetch(`/api/agents/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(await res.text());
    await fetchAgents();
    return res.json();
  };

  return { agents, loading, error, refetch: fetchAgents, runAgent, updateAgent };
}
