"use client";

import { useState, useEffect, useCallback } from "react";
import { createBrowserClient } from "@/lib/supabase";
import { apiClient } from "@/lib/api-client";
import { isDemoMode } from "@/lib/demo-mode";
import { demoEscalationControls, demoAutonomy, demoEscalationQueue } from "@/lib/demo-data";

// Autonomous Lead Engine — Increment 2 operator control-plane hook (R15).
// Loads/mutates the per-stage auto/ask/off caps, the workspace autonomy master
// switch (fail-closed off — R12), and the escalation queue; and records post-call
// outcomes. Follows the useOutreach idiom: demo branch first, then the real API
// behind the shared auth (createBrowserClient getSession token + workspace_id).

export type StageMode = "auto" | "ask" | "off";

export interface StageControl {
  stage: string;
  mode: StageMode;
  config: Record<string, unknown>;
}

export interface QueueItem {
  enrollment_id: string;
  lead_id: string;
  lead_name: string | null;
  lead_company: string | null;
  stage: string | null;
  status: string;
  proposed_action: string | null;
  final_action: string | null;
  mode: string | null;
  sentiment: string | null;
  score: number | null;
  reason: string | null;
  needs_judgment: boolean;
  occurred_at: string | null;
}

export type CallOutcome = "converted" | "booked" | "callback" | "not_interested" | "no_answer";

async function getAuth() {
  const supabase = createBrowserClient();
  const { data: { session } } = await supabase.auth.getSession();
  const token = session?.access_token;
  const workspaceId = (session?.user?.app_metadata?.workspace_id ?? session?.user?.user_metadata?.workspace_id) as string | undefined;
  return { token, workspaceId };
}

export function useEscalation() {
  const [controls, setControls] = useState<StageControl[]>(
    isDemoMode ? (demoEscalationControls as StageControl[]) : [],
  );
  const [autonomyEnabled, setAutonomyEnabled] = useState<boolean>(
    isDemoMode ? demoAutonomy.autonomy_enabled : false,
  );
  const [queue, setQueue] = useState<QueueItem[]>(isDemoMode ? demoEscalationQueue : []);
  const [loading, setLoading] = useState(!isDemoMode);
  const [error, setError] = useState<string | null>(null);

  const refetch = useCallback(async () => {
    if (isDemoMode) {
      setControls(demoEscalationControls as StageControl[]);
      setAutonomyEnabled(demoAutonomy.autonomy_enabled);
      setQueue(demoEscalationQueue);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const { token, workspaceId } = await getAuth();
      if (!token || !workspaceId) {
        setError("No workspace found");
        return;
      }
      const [ctrls, auto, q] = await Promise.all([
        apiClient.getEscalationControls(workspaceId, token),
        apiClient.getAutonomy(workspaceId, token),
        apiClient.getEscalationQueue(workspaceId, token),
      ]);
      setControls((ctrls as StageControl[]) ?? []);
      setAutonomyEnabled(Boolean(auto?.autonomy_enabled));
      setQueue((q as QueueItem[]) ?? []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load escalation controls");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (isDemoMode) return;
    refetch();
  }, [refetch]);

  const setStageMode = useCallback(async (stage: string, mode: StageMode) => {
    if (isDemoMode) {
      setControls((prev) => prev.map((c) => (c.stage === stage ? { ...c, mode } : c)));
      return;
    }
    const { token, workspaceId } = await getAuth();
    if (!token || !workspaceId) throw new Error("Not authenticated");
    const updated = await apiClient.setStageControl(workspaceId, stage, mode, token);
    setControls((prev) => prev.map((c) => (c.stage === stage ? { ...c, ...(updated as StageControl) } : c)));
  }, []);

  const toggleAutonomy = useCallback(async (enabled: boolean) => {
    if (isDemoMode) {
      setAutonomyEnabled(enabled);
      return;
    }
    const { token, workspaceId } = await getAuth();
    if (!token || !workspaceId) throw new Error("Not authenticated");
    const res = await apiClient.setAutonomy(workspaceId, enabled, token);
    setAutonomyEnabled(Boolean(res?.autonomy_enabled));
  }, []);

  const recordOutcome = useCallback(async (leadId: string, outcome: CallOutcome, notes?: string) => {
    if (isDemoMode) {
      // Drop the handled item from the queue so the surface reflects the action.
      setQueue((prev) => prev.filter((q) => q.lead_id !== leadId));
      return apiClient.recordCallOutcome("demo-workspace-1", leadId, outcome, "", notes);
    }
    const { token, workspaceId } = await getAuth();
    if (!token || !workspaceId) throw new Error("Not authenticated");
    const res = await apiClient.recordCallOutcome(workspaceId, leadId, outcome, token, notes);
    await refetch();
    return res;
  }, [refetch]);

  return {
    controls,
    autonomyEnabled,
    queue,
    loading,
    error,
    refetch,
    setStageMode,
    toggleAutonomy,
    recordOutcome,
  };
}
