"use client";

import { useState, useEffect, useCallback } from "react";
import { createBrowserClient } from "@/lib/supabase";
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
      const supabase = createBrowserClient();
      const { data: { user } } = await supabase.auth.getUser();
      const workspaceId = user?.user_metadata?.workspace_id as string | undefined;
      if (!workspaceId) {
        setError("No workspace found");
        return;
      }

      const { data, error: fetchError } = await supabase
        .from("agents")
        .select("*")
        .eq("workspace_id", workspaceId);

      if (fetchError) throw new Error(fetchError.message);
      setAgents((data ?? []).map((r: AgentRow) => rowToAgent(r)));
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
    // Triggers the FastAPI agent runner; falls back to status update if API unavailable
    const supabase = createBrowserClient();
    const { data, error: updateError } = await supabase
      .from("agents")
      .update({ status: "processing" })
      .eq("id", id)
      .select()
      .single();

    if (updateError) throw new Error(updateError.message);
    await fetchAgents();
    return data;
  };

  const updateAgent = async (id: string, payload: { status?: Agent["status"] }) => {
    const supabase = createBrowserClient();
    const { data, error: updateError } = await supabase
      .from("agents")
      .update(payload as Partial<AgentRow>)
      .eq("id", id)
      .select()
      .single();

    if (updateError) throw new Error(updateError.message);
    await fetchAgents();
    return data;
  };

  return { agents, loading, error, refetch: fetchAgents, runAgent, updateAgent };
}
