"use client";

import { useState, useEffect, useCallback } from "react";
import { createBrowserClient } from "@/lib/supabase";
import { apiClient } from "@/lib/api-client";
import type { Agent } from "@/lib/types";
import type { AgentRow } from "@/lib/supabase";
import { isDemoMode } from "@/lib/demo-mode";
import { demoAgents } from "@/lib/demo-data";

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
  const [agents, setAgents] = useState<Agent[]>(isDemoMode ? demoAgents : []);
  const [loading, setLoading] = useState(!isDemoMode);
  const [error, setError] = useState<string | null>(null);

  const fetchAgents = useCallback(async () => {
    if (isDemoMode) {
      setAgents(demoAgents);
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const supabase = createBrowserClient();
      const { data: { session } } = await supabase.auth.getSession();
      const token = session?.access_token;
      if (!token) {
        setError("Not authenticated");
        return;
      }

      const data = await apiClient.listAgents(token);
      setAgents(Array.isArray(data) ? (data as AgentRow[]).map(rowToAgent) : []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load agents");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (isDemoMode) return;
    fetchAgents();
  }, [fetchAgents]);

  const runAgent = async (id: string) => {
    if (isDemoMode) return { id, status: "processing" };
    const supabase = createBrowserClient();
    const { data: { session } } = await supabase.auth.getSession();
    const token = session?.access_token;
    if (!token) throw new Error("Not authenticated");
    const result = await apiClient.triggerAgent(id, token);
    await fetchAgents();
    return result;
  };

  const updateAgent = async (id: string, payload: { status?: Agent["status"] }) => {
    if (isDemoMode) return { id, ...payload };
    const supabase = createBrowserClient();
    const { data: { session } } = await supabase.auth.getSession();
    const token = session?.access_token;
    if (!token) throw new Error("Not authenticated");
    const result = await apiClient.updateAgent(id, payload, token);
    await fetchAgents();
    return result;
  };

  return { agents, loading, error, refetch: fetchAgents, runAgent, updateAgent };
}
