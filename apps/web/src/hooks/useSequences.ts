"use client";

import { useState, useEffect, useCallback } from "react";
import { createBrowserClient } from "@/lib/supabase";
import { apiClient } from "@/lib/api-client";
import type { Sequence, SequenceStep } from "@/lib/types";
import type { SequenceRow, SequenceStepRow } from "@/lib/supabase";
import { isDemoMode } from "@/lib/demo-mode";
import { demoSequences } from "@/lib/demo-data";

function rowToStep(row: SequenceStepRow): SequenceStep {
  return {
    id: row.id,
    workspaceId: row.workspace_id,
    sequenceId: row.sequence_id,
    stepOrder: row.step_order,
    channel: row.channel,
    delayHours: row.delay_hours,
    subject: row.subject,
    bodyTemplate: row.body_template,
    requiresApproval: row.requires_approval,
    aiGenerate: row.ai_generate,
    createdAt: row.created_at,
    updatedAt: row.updated_at,
  };
}

function rowToSequence(row: SequenceRow & { steps?: SequenceStepRow[] }): Sequence {
  return {
    id: row.id,
    workspaceId: row.workspace_id,
    name: row.name,
    description: row.description,
    channel: row.channel,
    status: row.status,
    stepCount: row.step_count ?? 0,
    settings: row.settings ?? {},
    createdAt: row.created_at,
    updatedAt: row.updated_at,
    steps: Array.isArray(row.steps) ? row.steps.map(rowToStep) : undefined,
  };
}

async function getAuth() {
  const supabase = createBrowserClient();
  const { data: { session } } = await supabase.auth.getSession();
  const token = session?.access_token;
  const workspaceId = (session?.user?.app_metadata?.workspace_id ?? session?.user?.user_metadata?.workspace_id) as string | undefined;
  return { token, workspaceId };
}

// Build a fully-shaped Sequence from a create payload for local demo insertion.
function makeDemoSequence(data: Parameters<typeof apiClient.createSequence>[1]): Sequence {
  const now = new Date().toISOString();
  return {
    id: `demo-seq-${Date.now()}`,
    workspaceId: demoSequences[0]?.workspaceId ?? "demo-workspace",
    name: data.name,
    description: data.description ?? null,
    channel: (data.channel as Sequence["channel"]) ?? "email",
    status: (data.status as Sequence["status"]) ?? "draft",
    stepCount: 0,
    settings: data.settings ?? {},
    createdAt: now,
    updatedAt: now,
    steps: [],
  };
}

export function useSequences(opts?: { status?: string }) {
  const status = opts?.status;
  const [sequences, setSequences] = useState<Sequence[]>(isDemoMode ? demoSequences : []);
  const [loading, setLoading] = useState(!isDemoMode);
  const [error, setError] = useState<string | null>(null);

  const fetchSequences = useCallback(async () => {
    if (isDemoMode) {
      setSequences(status && status !== "all" ? demoSequences.filter((s) => s.status === status) : demoSequences);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const { token, workspaceId } = await getAuth();
      if (!workspaceId || !token) {
        setError("No workspace found");
        return;
      }
      const data = await apiClient.listSequences(workspaceId, token, status ? { status } : undefined);
      setSequences(Array.isArray(data) ? (data as SequenceRow[]).map(rowToSequence) : []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load sequences");
    } finally {
      setLoading(false);
    }
  }, [status]);

  useEffect(() => {
    if (isDemoMode) {
      setSequences(status && status !== "all" ? demoSequences.filter((s) => s.status === status) : demoSequences);
      return;
    }
    fetchSequences();
  }, [fetchSequences, status]);

  const getSequence = async (id: string): Promise<Sequence | null> => {
    if (isDemoMode) return demoSequences.find((s) => s.id === id) ?? null;
    const { token, workspaceId } = await getAuth();
    if (!workspaceId || !token) throw new Error("Not authenticated");
    const data = await apiClient.getSequence(workspaceId, id, token);
    return data ? rowToSequence(data as SequenceRow & { steps?: SequenceStepRow[] }) : null;
  };

  const createSequence = async (data: Parameters<typeof apiClient.createSequence>[1]) => {
    if (isDemoMode) {
      const sequence = makeDemoSequence(data);
      setSequences((prev) => [sequence, ...prev]);
      return { id: sequence.id };
    }
    const { token, workspaceId } = await getAuth();
    if (!workspaceId || !token) throw new Error("Not authenticated");
    const result = await apiClient.createSequence(workspaceId, data, token);
    await fetchSequences();
    return result;
  };

  const updateSequence = async (id: string, data: Parameters<typeof apiClient.updateSequence>[2]) => {
    if (isDemoMode) {
      setSequences((prev) =>
        prev.map((s) =>
          s.id === id
            ? {
                ...s,
                name: data.name ?? s.name,
                description: data.description ?? s.description,
                channel: (data.channel as Sequence["channel"]) ?? s.channel,
                status: (data.status as Sequence["status"]) ?? s.status,
                settings: data.settings ?? s.settings,
                updatedAt: new Date().toISOString(),
              }
            : s
        )
      );
      return { id };
    }
    const { token, workspaceId } = await getAuth();
    if (!workspaceId || !token) throw new Error("Not authenticated");
    const result = await apiClient.updateSequence(workspaceId, id, data, token);
    await fetchSequences();
    return result;
  };

  const saveSteps = async (id: string, steps: Parameters<typeof apiClient.saveSequenceSteps>[2]) => {
    if (isDemoMode) {
      const now = new Date().toISOString();
      const mapped: SequenceStep[] = steps.map((st, i) => ({
        id: `${id}-step-${i}`,
        workspaceId: demoSequences[0]?.workspaceId ?? "demo-workspace",
        sequenceId: id,
        stepOrder: st.step_order ?? i,
        channel: st.channel as SequenceStep["channel"],
        delayHours: st.delay_hours,
        subject: st.subject ?? null,
        bodyTemplate: st.body_template,
        requiresApproval: st.requires_approval,
        aiGenerate: st.ai_generate,
        createdAt: now,
        updatedAt: now,
      }));
      setSequences((prev) =>
        prev.map((s) => (s.id === id ? { ...s, steps: mapped, stepCount: mapped.length, updatedAt: now } : s))
      );
      return { id, step_count: steps.length, steps };
    }
    const { token, workspaceId } = await getAuth();
    if (!workspaceId || !token) throw new Error("Not authenticated");
    const result = await apiClient.saveSequenceSteps(workspaceId, id, steps, token);
    await fetchSequences();
    return result;
  };

  return { sequences, items: sequences, loading, error, refetch: fetchSequences, getSequence, createSequence, updateSequence, saveSteps };
}
